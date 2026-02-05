import msgpack as mp
import logging
import sys
import socket
import threading
import os
from typing import Callable, TypeAlias, Any
import importlib

class ColorFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[94m',    # Blue
        'INFO': '\033[92m',     # Green
        'WARNING': '\033[93m',  # Yellow
        'ERROR': '\033[91m',    # Red
        'CRITICAL': '\033[95m', # Magenta
    }
    RESET = '\033[0m'

class IsabelleError(Exception):
    def __init__(self, errors : list[str], errobj: Any):
        self.errors = errors
        self.obj = errobj
        super().__init__(self.errors)


class Connection:
    def __init__(self, socket: socket.socket, client_addr: tuple[str, int], server: 'Server'):
        self.sock = socket
        self.client_addr = client_addr
        self.server = server
        self.cout = self.sock.makefile('wb')
        self.cin = self.sock.makefile('rb', buffering=0)
        self.unpack = mp.Unpacker(self.cin)
    
    def read(self) -> Any:
        (ret, err) = self.unpack.unpack()
        if err is not None:
            raise IsabelleError(*err)
        return ret
    
    def write(self, data: Any) -> None:
        mp.pack((data, None), self.cout)
        self.cout.flush()
    
    def write_error(self, error: Any) -> None:
        mp.pack((None, str(error)), self.cout)
        self.cout.flush()
    
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
            while self.running:
                try:
                    try:
                        (func_name, arg) = connection.read()
                    except mp.UnpackException as e:
                        self.logger.error(f"From {client_addr}, invalid RPC request")
                        connection.write_error("Invalid RPC request")
                        return
                    try:
                        func = Remote_Procedures[func_name]
                    except KeyError:
                        self.logger.error(f"From {client_addr}, unknown RPC function {func_name}")
                        connection.write_error(f"Unknown procedure {func_name}")
                        continue
                    if self.debugging:
                        result = func(arg, connection)
                    else:
                        try:
                            result = func(arg, connection)
                        except Exception as e:
                            self.logger.warning(f"From {client_addr}, error calling RPC function {func_name}: {e}")
                            connection.write_error(e)
                            continue
                    connection.write(result)
                except Exception as e:
                    if self.debugging:
                        import traceback
                        traceback.print_exc()
                        self.logger.error(f"From {client_addr}, error handling RPC request: {e}")
                        raise
                    else:
                        self.logger.error(f"From {client_addr}, error handling RPC request: {e}")
                        return

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
            self.logger.info(f"Start")
            
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

# Example usage
def _heartbeat_(arg, connection : Connection) -> None:
    connection.server.logger.info(f"Heartbeat from {connection.client_addr}")
    return None

Remote_Procedures["heartbeat"] = _heartbeat_

def _load_remote_procedures_(arg, connection : Connection):
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

Remote_Procedures["load_pymodule"] = _load_remote_procedures_

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
    launch_server_(addr, logger)
