import errno
import msgpack as mp
import logging
import sys
import socket
import threading
import os
import tempfile
from typing import Callable, TypeAlias, Any, Optional
import importlib
import uuid

_thread_local = threading.local()


class ColorFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[94m',    # Blue
        'INFO': '\033[92m',     # Green
        'WARNING': '\033[93m',  # Yellow
        'ERROR': '\033[91m',    # Red
        'CRITICAL': '\033[95m', # Magenta
    }
    RESET = '\033[0m'

class DebugStream:
    """Wraps a stream and buffers all bytes read for debugging unpack failures."""

    def __init__(self, stream):
        self._stream = stream
        self._buffer = bytearray()

    def read(self, size: int = -1) -> bytes:
        data = self._stream.read(size) if size >= 0 else self._stream.read()
        self._buffer.extend(data)
        return data

    def readinto(self, b: bytearray) -> Optional[int]:
        n = self._stream.readinto(b)
        if n:
            self._buffer.extend(b[:n])
        return n

    def close(self):
        self._stream.close()

    def get_buffer_bytes(self) -> bytes:
        return bytes(self._buffer)

    def clear_buffer(self) -> None:
        """Clear buffer after successful read; keeps only the current message for error reporting."""
        self._buffer.clear()

    def __getattr__(self, name):
        return getattr(self._stream, name)


class IsabelleError(Exception):
    def __init__(self, errors : list[str], errobj: Any):
        self.errors = errors
        self.obj = errobj
        super().__init__(self.errors)


class Connection:
    @staticmethod
    def current() -> 'Connection | None':
        """Return the Connection for the current thread, or None if not in an RPC handler."""
        return getattr(_thread_local, 'connection', None)

    def __init__(self, socket: socket.socket, client_addr: tuple[str, int], server: 'Server'):
        self.sock = socket
        self.client_addr = client_addr
        self.server = server
        self.cout = self.sock.makefile('wb')
        raw_cin = self.sock.makefile('rb', buffering=0)
        self.debug_stream: DebugStream | None = DebugStream(raw_cin) if server.debugging else None
        self.cin = self.debug_stream if self.debug_stream else raw_cin
        self.unpack = mp.Unpacker(self.cin)

    def read(self) -> Any:
        (ret, err) = self.unpack.unpack()
        if err is not None:
            raise IsabelleError(*err)
        if self.debug_stream:
            self.debug_stream.clear_buffer()  # only keep failed message bytes for error log
        return ret

    def write(self, data: Any) -> None:
        """Send success response with tag 1: (1, result)."""
        mp.pack((1, data), self.cout)
        self.cout.flush()

    def write_error(self, error: Any) -> None:
        """Send error response with tag 2: (2, error_message)."""
        mp.pack((2, str(error)), self.cout)
        self.cout.flush()

    def callback(self, name: str, arg: Any) -> Any:
        """Call an Isabelle callback function with 2-phase protocol.

        Phase 1: Send callback name, wait for lookup confirmation
        Phase 2: If found, send argument and wait for execution result

        Args:
            name: The callback function name
            arg: The argument to pass to the callback

        Returns:
            The result returned by the callback

        Raises:
            IsabelleError: If the callback is not found or execution fails
        """
        def phase2_protocol(conn: 'Connection') -> Any:
            # Phase 2: Send argument
            mp.pack(arg, conn.cout)
            conn.cout.flush()

            # Read Phase 2 response: execution result
            (result, error) = conn.unpack.unpack()

            if error is not None:
                raise IsabelleError([error], None)

            if conn.debug_stream:
                conn.debug_stream.clear_buffer()

            return result

        return self.raw_callback(name, phase2_protocol)

    def config_lookup(self, name: str) -> Any:
        """Look up an Isabelle config option by name via the Config.lookup callback."""
        return self.callback("Config.lookup", name)

    def raw_callback(self, name: str, action: Callable[['Connection'], Any]) -> Any:
        """Start a raw callback with custom bidirectional protocol.

        Only performs Phase 1 (lookup). After successful lookup, both the ML
        callback' action and the Python action function run with raw connection
        access, enabling custom bidirectional protocols.

        Args:
            name: The ML callback name
            action: Python function that receives Connection for custom I/O

        Returns:
            Whatever the action function returns

        Raises:
            IsabelleError: If the callback is not found

        Example:
            def my_protocol(conn: Connection):
                conn.write((1, "command"))
                result = conn.read()
                return result

            result = connection.raw_callback("my_callback", my_protocol)
        """
        # Phase 1: Send callback name for lookup
        mp.pack((0, name), self.cout)
        self.cout.flush()

        # Read Phase 1 response: (result, error) tuple
        (phase1_result, phase1_error) = self.unpack.unpack()

        if phase1_error is not None:
            # Callback not found
            raise IsabelleError([phase1_error], None)

        # Phase 1 succeeded - ML callback is now running with connection access
        # Call Python action to interact with ML side via custom protocol
        return action(self)

    def close(self):
        try:
            self.cout.close()
        except:
            pass
        try:
            self.cin.close()
        except:
            pass
        try:
            self.sock.close()
        except:
            pass

    def __enter__(self) -> 'Connection':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False

    def is_peer_closed(self) -> bool:
        """True if the peer has closed the connection (no data and EOF)."""
        old = self.sock.getblocking()
        try:
            self.sock.setblocking(False)
            try:
                n = len(self.sock.recv(1, socket.MSG_PEEK))
                return n == 0
            except BlockingIOError:
                return False
        except OSError:
            return True
        finally:
            try:
                self.sock.setblocking(old)
            except OSError:
                pass

RemoteProcedure: TypeAlias = Callable[[Any, Connection], Any]
Remote_Procedures: dict[str, RemoteProcedure] = {}

def isabelle_remote_procedure(name: str):
    def decorator(func: Callable[[Any, Connection], Any]):
        Remote_Procedures[name] = func
        return func
    return decorator

class Server:

    def __init__(self, addr: str, logger: logging.Logger, debugging: bool = False):
        self.addr = addr
        self.host, port_str = addr.split(':')
        self.port = int(port_str)
        self.socket = None
        self.running = False
        self.clients = {}
        self.logger = logger
        self.debugging = debugging

    def handle_client(self, client_socket: socket.socket, client_addr: tuple[str, int]) -> None:
        """Handle a client connection."""
        with Connection(client_socket, client_addr, self) as connection:
            _thread_local.connection = connection
            try:
                while self.running:
                    try:
                        try:
                            (func_name, arg) = connection.read()
                        except mp.UnpackException as e:
                            if connection.is_peer_closed():
                                self.logger.debug(f"From {client_addr}, connection closed by peer")
                                return
                            buf = connection.debug_stream.get_buffer_bytes() if connection.debug_stream else None
                            err_details = f"{type(e).__name__}: {e}"
                            if hasattr(e, 'unpacked') and hasattr(e, 'extra'):
                                err_details += f" (unpacked={e.unpacked!r}, extra_bytes_hex={e.extra.hex()!s})" # type: ignore
                            elif hasattr(connection.unpack, 'tell'):
                                try:
                                    err_details += f" (stream_pos={connection.unpack.tell()})"
                                except Exception:
                                    pass
                            if buf is not None:
                                try:
                                    fd, dump_path = tempfile.mkstemp(suffix='.bin', prefix='isabelle_rpc_unpack_error_')
                                    with os.fdopen(fd, 'wb') as f:
                                        f.write(buf)
                                    err_details += f" [debug: binary written to {dump_path}]"
                                except Exception as dump_err:
                                    err_details += f" [debug: failed to write binary: {dump_err}]"
                            self.logger.error(f"From {client_addr}, invalid RPC request: {err_details}")
                            connection.write_error("Invalid RPC request")
                            return
                        try:
                            func = Remote_Procedures[func_name]
                        except KeyError:
                            self.logger.error(f"From {client_addr}, unknown RPC function {func_name}")
                            connection.write_error(f"Unknown procedure {func_name}")
                            continue
                        try:
                            result = func(arg, connection)
                        except Exception as e:
                            self.logger.warning(f"From {client_addr}, error calling RPC function {func_name}: {e}")
                            connection.write_error(e)
                            if self.debugging:
                                raise
                            continue
                        connection.write(result)
                    except ConnectionResetError as e:
                        self.logger.debug(f"From {client_addr}, connection reset by peer: {e}")
                        return
                    except BrokenPipeError as e:
                        self.logger.debug(f"From {client_addr}, broken pipe (peer closed): {e}")
                        return
                    except OSError as e:
                        if e.errno == errno.ECONNRESET:
                            self.logger.debug(f"From {client_addr}, connection reset by peer (ECONNRESET): {e}")
                            return
                        if e.errno == errno.EPIPE:
                            self.logger.debug(f"From {client_addr}, broken pipe (EPIPE, peer closed): {e}")
                            return
                        raise
                    except Exception as e:
                        if self.debugging:
                            import traceback
                            traceback.print_exc()
                            self.logger.error(f"From {client_addr}, error handling RPC request: {e}")
                            raise
                        else:
                            self.logger.error(f"From {client_addr}, error handling RPC request: {e}")
                            return
            finally:
                _thread_local.connection = None

    def stop_server(self) -> None:
        """Stop the TCP server."""
        self.logger.info(f"Stopping server {self.addr}...")
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.logger.info(f"Server {self.addr} stopped")

    def run_server(self) -> None:
        if self.running:
            raise RuntimeError(f"Isabelle RPC Host {self.addr} is already running")
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(8)
            self.running = True

            # Create thread pool executor for handling client connections
            self.logger.info(f"Start" + (" (debug mode: binary capture on unpack errors)" if self.debugging else ""))

            while self.running:
                try:
                    client_socket, client_addr = self.socket.accept()
                    self.logger.debug(f"New client connected from {client_addr}")
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_addr)
                    )
                    client_thread.daemon = True
                    client_thread.start()

                except socket.error as e:
                    if self.running:
                        self.logger.error(f"Socket error: {e}")

        except Exception as e:
            self.logger.error(f"Failed to start: {e}")

    def __enter__(self) -> 'Server':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.stop_server()
        return False

# Built-in remote procedures

@isabelle_remote_procedure("heartbeat")
def _heartbeat_(arg, connection: Connection) -> None:
    """Built-in heartbeat RPC for connection health checks."""
    connection.server.logger.info(f"Heartbeat from {connection.client_addr}")
    return None


@isabelle_remote_procedure("load_pymodule")
def _load_remote_procedures_(arg, connection: Connection):
    """
    Load Python modules to register additional RPC procedures.

    Args:
        arg: Module name (string) or list of module names

    Returns:
        Dictionary mapping module names to error messages (None if successful)
    """
    logger = connection.server.logger
    if isinstance(arg, str):
        arg = [arg]
    errors = {}
    for target in arg:
        logger.info(f"Loading RPC component: {target}")
        try:
            importlib.import_module(target)
            errors[target] = None
        except Exception as e:
            logger.error(f"Failed to load RPC component: {target}: {e}")
            errors[target] = str(e)
    return errors


@isabelle_remote_procedure("call_heartbeat_callback")
def _call_heartbeat_callback_(arg, connection: Connection) -> str:
    """
    Call the Isabelle heartbeat callback.

    This is an example RPC that demonstrates the callback mechanism:
    Python receives an RPC call and calls back to Isabelle's heartbeat callback.

    Args:
        arg: Unused (unit value)
        connection: The RPC connection

    Returns:
        The heartbeat message from Isabelle
    """
    logger = connection.server.logger
    logger.info(f"Calling isabelle_heartbeat callback from {connection.client_addr}")

    # Call the Isabelle heartbeat callback
    heartbeat_msg = connection.callback("isabelle_heartbeat", None)

    logger.info(f"Received heartbeat: {heartbeat_msg}")
    return heartbeat_msg


@isabelle_remote_procedure("generate_uuids")
def _generate_uuids_(arg, connection: Connection):
    count = int(arg)
    return [uuid.uuid4().bytes for _ in range(count)]


def isabelle_home() -> str:
    isabelle_home = os.environ.get("ISABELLE_HOME_USER")
    if not isabelle_home:
        isabelle_home = os.popen("isabelle getenv -b ISABELLE_HOME_USER").read().strip()
    if not isabelle_home:
        sys.stderr.write("Environment variable ISABELLE_HOME_USER is not set. Cannot determine Isabelle home directory.")
        sys.exit(1)
    return isabelle_home

def _load_remote_procedures(logger: logging.Logger) -> None:
    home = isabelle_home()
    rpc_components_path = os.path.join(home, 'etc', 'rpc_components')
    logger.info(f"Loading RPC components from {rpc_components_path}")
    if not os.path.exists(rpc_components_path):
        return
    with open(rpc_components_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            logger.info(f"Loading RPC component: {line}")
            importlib.import_module(line)

def mk_logger_(addr: str, log_file: str | None) -> logging.Logger:
    # Configure logging
    logger = logging.getLogger(__name__)
    logger.propagate = False  # Prevent duplicate logging to root logger
    if log_file:
        file_handler = logging.FileHandler(log_file)
        #file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            f'%(asctime)s - Isabelle RPC Host {addr} - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(file_handler)
    else:
        stream_handler = logging.StreamHandler(sys.stderr)
        #stream_handler.setLevel(logging.DEBUG)
        color_formatter = ColorFormatter(f'%(asctime)s - Isabelle RPC Host {addr} - %(levelname)s - %(message)s')
        stream_handler.setFormatter(color_formatter)
        logger.addHandler(stream_handler)
    logger.setLevel(logging.DEBUG)
    return logger

def launch_server_(addr: str, logger: logging.Logger, debugging: bool = False) -> None:
    _load_remote_procedures(logger)
    with Server(addr, logger, debugging) as server:
        server.run_server()

def fork_and_launch__():
    """
    Fork a daemon process to launch the server and exit the original process.
    """
    if len(sys.argv) != 3 or sys.argv[0] != "-c":
        sys.stderr.write("fork_and_launch__ is an internal function and should not be called directly")
    addr = sys.argv[1]
    log_file = sys.argv[2]

    # First fork
    try:
        pid = os.fork()
        if pid > 0:
            # Parent process exits
            os._exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #1 failed: {e}\n")
        sys.exit(1)

    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)

    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            # First child process exits
            os._exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #2 failed: {e}\n")
        sys.exit(1)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()

    si = open(os.devnull, 'r')
    so = open(os.devnull, 'a+')
    se = open(os.devnull, 'a+')

    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())

    # Close file descriptors
    si.close()
    so.close()
    se.close()

    logger = mk_logger_(addr, log_file)
    debugging = os.environ.get("ISABELLE_RPC_DEBUG", "").lower() in ("1", "true", "yes")
    launch_server_(addr, logger, debugging)

