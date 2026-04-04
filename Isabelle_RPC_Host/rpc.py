import asyncio
import contextvars
import errno
import msgpack as mp
import logging
import sys
import socket
import os
import tempfile
from enum import IntEnum
from typing import Callable, TypeAlias, Any, Awaitable
import importlib
import uuid

_connection_var: contextvars.ContextVar['Connection | None'] = contextvars.ContextVar('_connection_var', default=None)


class ColorFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '',            # Default (no color)
        'INFO': '\033[92m',     # Green
        'WARNING': '\033[1;33m',# Bold Yellow
        'ERROR': '\033[1;31m',  # Bold Red
        'CRITICAL': '\033[1;35m', # Bold Magenta
    }
    RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        color = self.COLORS.get(record.levelname, '')
        if color:
            return f"{color}{msg}{self.RESET}"
        return msg


class IsabelleError(Exception):
    def __init__(self, errors : list[str], errobj: Any):
        self.errors = errors
        self.obj = errobj
        super().__init__(self.errors)


class Connection:
    @staticmethod
    def current() -> 'Connection | None':
        """Return the Connection for the current task, or None if not in an RPC handler."""
        return _connection_var.get()

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 client_addr: tuple[str, int], server: 'Server'):
        self.reader = reader
        self.writer = writer
        self.sock: socket.socket = writer.get_extra_info('socket')
        self.client_addr = client_addr
        self.server = server
        self.unpack = mp.Unpacker()  # feed mode: no stream, manually feed bytes
        self._debug_buffer: bytearray | None = bytearray() if server.debugging else None
        # Multiplexed callback protocol (tag 0 = success, 1 = error, N>1 = callback)
        self._next_callback_id = 2
        self._pending: dict[int, asyncio.Future[Any]] = {}  # callback_id → Future
        self._user_channel: asyncio.Queue[tuple[int, Any]] = asyncio.Queue()  # (tag, payload)
        self._reader_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()  # serialize writes to the socket

    async def _feed_and_unpack(self) -> Any:
        """Read bytes from StreamReader, feed to Unpacker, return next msgpack object."""
        while True:
            try:
                return self.unpack.unpack()
            except mp.OutOfData:
                data = await self.reader.read(65536)
                if not data:
                    raise ConnectionResetError("peer closed connection")
                if self._debug_buffer is not None:
                    self._debug_buffer.extend(data)
                self.unpack.feed(data)

    async def _start_reader(self) -> None:
        """Start the background reader task that dispatches messages by tag."""
        self._reader_task = asyncio.create_task(self._reader_loop())

    async def _reader_loop(self) -> None:
        """Read (tag, payload) messages and dispatch by tag."""
        try:
            while True:
                (tag, payload) = await self._feed_and_unpack()
                if tag <= 1:  # user channel (0 = data, 1 = error)
                    await self._user_channel.put((tag, payload))
                else:  # callback channel N > 1
                    future = self._pending.pop(tag, None)
                    if future is not None and not future.done():
                        future.set_result(payload)
        except (ConnectionResetError, BrokenPipeError, OSError):
            # Connection closed — unblock any pending waiters
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(ConnectionResetError("peer closed connection"))
            self._pending.clear()
            await self._user_channel.put(None)  # sentinel to unblock read()

    def _stop_reader(self) -> None:
        """Cancel the background reader task."""
        if self._reader_task is not None:
            self._reader_task.cancel()
            self._reader_task = None

    async def read(self) -> Any:
        """Read next RPC request from user channel (tag 0) or raise on error (tag 1)."""
        msg = await self._user_channel.get()
        if msg is None:
            raise ConnectionResetError("peer closed connection")
        (tag, payload) = msg
        if tag == 1:  # remote error
            raise IsabelleError(*payload)
        if self._debug_buffer is not None:
            self._debug_buffer.clear()
        return payload

    async def write(self, data: Any) -> None:
        """Send success response: (0, result)."""
        async with self._write_lock:
            self.writer.write(mp.packb((0, data)))  # type: ignore[arg-type]
            await self.writer.drain()

    async def write_error(self, error: Any) -> None:
        """Send error response: (1, error_string)."""
        async with self._write_lock:
            self.writer.write(mp.packb((1, str(error))))  # type: ignore[arg-type]
            await self.writer.drain()

    async def callback(self, name: str, arg: Any) -> Any:
        """Call an Isabelle callback function with 2-phase multiplexed protocol.

        Each callback gets a unique ID (tag > 0). The reader task routes
        responses by tag, so multiple callbacks can be in-flight concurrently
        and callbacks can be called from within isabelle_remote_procedure handlers.

        The write lock is held across both phases to prevent interleaving
        of concurrent callbacks — Isabelle's dispatch_loop reads phase 1
        then immediately reads phase 2, so they must be adjacent in the
        byte stream.  The await for the phase-1 ack is safe inside the
        lock because responses arrive via the independent _reader_loop.
        """
        loop = asyncio.get_running_loop()
        cb_id = self._next_callback_id
        self._next_callback_id += 1

        async with self._write_lock:
            # Phase 1: Send (cb_id, name), wait for lookup confirmation
            phase1_future: asyncio.Future[Any] = loop.create_future()
            self._pending[cb_id] = phase1_future
            self.writer.write(mp.packb((cb_id, name)))  # type: ignore[arg-type]
            await self.writer.drain()
            (phase1_result, phase1_error) = await phase1_future

            if phase1_error is not None:
                raise IsabelleError([phase1_error], None)

            # Phase 2: Send (cb_id, arg), wait for execution result
            phase2_future: asyncio.Future[Any] = loop.create_future()
            self._pending[cb_id] = phase2_future
            self.writer.write(mp.packb((cb_id, arg)))  # type: ignore[arg-type]
            await self.writer.drain()

        (result, error) = await phase2_future

        if error is not None:
            raise IsabelleError([error], None)

        if self._debug_buffer is not None:
            self._debug_buffer.clear()

        return result

    async def config_lookup(self, name: str) -> Any:
        """Look up an Isabelle config option by name via the Config.lookup callback."""
        return await self.callback("Config.lookup", name)

    # -- Isabelle logging via "log" callback ----------------------------------

    class LogType(IntEnum):
        """Log level tags matching ``Isabelle_Log.log_type`` in tracing.ML."""
        TRACING = 0
        WARNING = 1
        WRITELN = 2

    async def tracing(self, msg: str) -> None:
        """Print a tracing message in Isabelle's output."""
        self.server.logger.debug(msg)
        await self.callback("log", (int(self.LogType.TRACING), msg))

    async def warning(self, msg: str) -> None:
        """Print a warning message in Isabelle's output."""
        self.server.logger.warning(msg)
        await self.callback("log", (int(self.LogType.WARNING), msg))

    async def writeln(self, msg: str) -> None:
        """Print a normal message in Isabelle's output."""
        self.server.logger.info(msg)
        await self.callback("log", (int(self.LogType.WRITELN), msg))

    def close(self):
        try:
            self.writer.close()
        except:
            pass

    async def __aenter__(self) -> 'Connection':
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False

RemoteProcedure: TypeAlias = Callable[[Any, 'Connection'], Awaitable[Any]]
Remote_Procedures: dict[str, RemoteProcedure] = {}

def isabelle_remote_procedure(name: str):
    def decorator(func: Callable[[Any, 'Connection'], Awaitable[Any]]):
        Remote_Procedures[name] = func
        return func
    return decorator

class Server:

    def __init__(self, addr: str, logger: logging.Logger, debugging: bool = False):
        self.addr = addr
        self.host, port_str = addr.split(':')
        self.port = int(port_str)
        self._server: asyncio.Server | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.running = False
        self.clients = {}
        self.logger = logger
        self.debugging = debugging

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle a client connection."""
        client_addr = writer.get_extra_info('peername')
        connection = Connection(reader, writer, client_addr, self)
        await connection._start_reader()
        token = _connection_var.set(connection)
        try:
            while self.running:
                try:
                    try:
                        (func_name, arg) = await connection.read()
                    except mp.UnpackException as e:
                        buf = bytes(connection._debug_buffer) if connection._debug_buffer is not None else None
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
                        await connection.write_error("Invalid RPC request")
                        return
                    try:
                        func = Remote_Procedures[func_name]
                    except KeyError:
                        self.logger.error(f"From {client_addr}, unknown RPC function {func_name}")
                        await connection.write_error(f"Unknown procedure {func_name}")
                        continue
                    try:
                        result = await func(arg, connection)
                    except Exception as e:
                        self.logger.warning(f"From {client_addr}, error calling RPC function {func_name}: {e}")
                        await connection.write_error(e)
                        if self.debugging:
                            raise
                        continue
                    await connection.write(result)
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
            connection._stop_reader()
            _connection_var.reset(token)
            connection.close()

    async def run_server(self) -> None:
        if self.running:
            raise RuntimeError(f"Isabelle RPC Host {self.addr} is already running")

        self._loop = asyncio.get_running_loop()
        self._server = await asyncio.start_server(
            self.handle_client, self.host, self.port,
            reuse_address=True, backlog=8)
        self.running = True

        self.logger.info(f"Start" + (" (debug mode: binary capture on unpack errors)" if self.debugging else ""))

        async with self._server:
            await self._server.serve_forever()

    def stop_server(self) -> None:
        """Stop the TCP server."""
        self.logger.info(f"Stopping server {self.addr}...")
        self.running = False
        if self._server:
            self._server.close()
        self.logger.info(f"Server {self.addr} stopped")

    def __enter__(self) -> 'Server':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.stop_server()
        return False

# Built-in remote procedures

@isabelle_remote_procedure("heartbeat")
async def _heartbeat_(arg, connection: Connection) -> None:
    """Built-in heartbeat RPC for connection health checks."""
    #connection.server.logger.info(f"Heartbeat from {connection.client_addr}")
    return None


@isabelle_remote_procedure("load_pymodule")
async def _load_remote_procedures_(arg, connection: Connection):
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
async def _call_heartbeat_callback_(arg, connection: Connection) -> str:
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
    heartbeat_msg = await connection.callback("isabelle_heartbeat", None)

    logger.info(f"Received heartbeat: {heartbeat_msg}")
    return heartbeat_msg


@isabelle_remote_procedure("generate_uuids")
async def _generate_uuids_(arg, connection: Connection):
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
        asyncio.run(server.run_server())

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
