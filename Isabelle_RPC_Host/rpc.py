import asyncio
import contextvars
import errno
import msgpack as mp
import logging
import sys
import socket
import os
import tempfile
import threading
import traceback
from enum import IntEnum
from typing import Callable, TypeAlias, Any, Awaitable
import importlib
import uuid

from .paths import resolve_isabelle_var

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
        from .unicode import pretty_unicode
        self.errors = [pretty_unicode(e) for e in errors]
        self.obj = errobj
        super().__init__(self.errors)


class Connection:
    @staticmethod
    def current() -> 'Connection | None':
        """Return the Connection for the current task, or None if not in an RPC handler."""
        return _connection_var.get()

    @staticmethod
    def set_current(connection: 'Connection | None') -> None:
        """Bind *connection* as the ambient Connection for the current context.

        `handle_client` already does this once per socket, which is enough while
        everything runs as descendants of that task. It is NOT enough across an
        ASGI boundary: uvicorn starts each request in a fresh, empty
        contextvars.Context (unconditionally in 0.39-0.4x; opt-in via
        `reset_contextvars` from 0.51, default off), as a workaround for
        cpython#140947 -- so `current()` returns None inside a request handler
        however the outer binding was made. A server embedding one must re-bind
        at its request entry point; AoA does exactly this alongside its own
        `_session_var` (IsaMini/AoA/model.py bind_session_context).

        No token is returned and nothing is reset: the context this writes into
        is per-request and dies with it.
        """
        _connection_var.set(connection)

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

    async def config_lookup(self, name: str, ctxt: Any = None) -> Any:
        """Look up an Isabelle config option by name via the Config.lookup callback."""
        return await self.callback("Config.lookup", (ctxt, name))

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

    def __init__(self, addr: str, logger: logging.Logger, debugging: bool = False, *,
                 attached_token: str | None = None,
                 ready_file: str | None = None,
                 leak_guard: 'threading.Timer | None' = None):
        # The attached-mode extras are keyword-only WITH defaults: every pre-existing
        # positional caller (launcher.py, semantics_manage.py, debug launchers, tests,
        # _daemon_body__) keeps today's behavior -- in particular no leak guard and no
        # ready-file ever exist on the external-launch path (an armed guard there would
        # kill every external daemon at 300 s).  See RPC_EPHEMERAL_HOST_PLAN.md §3.6.
        self.addr = addr
        self.host, port_str = addr.split(':')
        self.port = int(port_str)
        self._server: asyncio.Server | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.running = False
        self.clients = {}
        self.logger = logger
        self.debugging = debugging
        self.attached_token = attached_token
        self.ready_file = ready_file
        self._leak_guard = leak_guard
        self._lifeline_connection: 'Connection | None' = None

    def _disarm_leak_guard(self) -> None:
        t = self._leak_guard
        self._leak_guard = None
        if t is not None:
            t.cancel()  # threading.Timer.cancel is thread-safe

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
                    func_task = asyncio.create_task(func(arg, connection))
                    reader_task = connection._reader_task
                    try:
                        if reader_task is not None and not reader_task.done():
                            done, _ = await asyncio.wait(
                                [func_task, reader_task],
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            if reader_task in done:
                                # Grace period: let func_task finish processing
                                # any already-resolved IsabelleError before cancelling.
                                try:
                                    await asyncio.wait_for(asyncio.shield(func_task), timeout=3)
                                except asyncio.TimeoutError:
                                    func_task.cancel()
                                    try:
                                        await func_task
                                    except (asyncio.CancelledError, Exception):
                                        pass
                                except (asyncio.CancelledError, Exception):
                                    pass
                                self.logger.info(f"From {client_addr}, cancelled {func_name} (connection closed)")
                                return
                            result = func_task.result()
                        else:
                            result = await func_task
                    except Exception as e:
                        tb = traceback.format_exception(e)
                        tb_str = "".join(tb)
                        self.logger.warning(f"From {client_addr}, error calling RPC function {func_name}:\n{tb_str}")
                        await connection.write_error(tb_str)
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
            if connection is self._lifeline_connection:
                # Redundant safety net behind attached_lifeline's own EOF wait (which
                # normally runs os._exit first): the lifeline is gone, this host must
                # not outlive its Isabelle process.
                self.logger.info("Lifeline connection closed - exiting (teardown path)")
                os._exit(0)

    async def run_server(self) -> None:
        if self.running:
            raise RuntimeError(f"Isabelle RPC Host {self.addr} is already running")

        self._loop = asyncio.get_running_loop()
        self._server = await asyncio.start_server(
            self.handle_client, self.host, self.port,
            reuse_address=True, backlog=8)
        self.running = True

        if self.ready_file is not None:
            # Attached mode (run_attached__): report the OS-assigned port atomically,
            # THEN run the component imports -- pinned ordering, see
            # RPC_EPHEMERAL_HOST_PLAN.md §3.1 step 4.  The temp file lives in the
            # ready-file's own directory (same directory => same filesystem => the
            # rename is atomic; a default tempfile location such as /tmp is routinely a
            # different filesystem, where os.replace raises EXDEV), and its '.tmp'
            # suffix keeps it outside the launcher's RPC_attached_*.info sweep glob.
            real_port = self._server.sockets[0].getsockname()[1]
            self.port = real_port
            self.addr = f"{self.host}:{real_port}"
            tmp = self.ready_file + ".tmp"
            with open(tmp, "w") as f:
                f.write(f"{real_port} {self.attached_token}")
            os.replace(tmp, self.ready_file)
            self.logger.info(f"Attached host bound on port {real_port}; ready-file written")
            # Component imports AFTER bind: they run synchronously on the event-loop
            # thread (1-40 s); ML's connection is held by the TCP backlog meanwhile and
            # its 60 s launch-path handshake timeout covers this window.
            _load_remote_procedures(self.logger)

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


@isabelle_remote_procedure("rpc_host_identity")
async def _rpc_host_identity_(arg, connection: Connection) -> 'str | None':
    """Return this host's launch token (None on an externally-launched host).

    The ML side compares it against the token it generated at launch to detect
    "the port I recorded got reused by somebody else" (RPC_EPHEMERAL_HOST_PLAN.md §3.3).
    A stored constant: this procedure cannot legitimately fail, which is why the ML
    side may treat ANY error reply as "not our host".
    """
    return connection.server.attached_token


@isabelle_remote_procedure("attached_lifeline")
async def _attached_lifeline_(arg, connection: Connection) -> None:
    """Claim this attached host's lifeline; park until the peer dies, then exit.

    Protocol (RPC_EPHEMERAL_HOST_PLAN.md §3.2): validate token -> disarm the leak
    guard -> write ONE success reply ourselves (the claim ack; this coroutine never
    returns, so handle_client's own reply-after-completion can never happen; the ML
    side reads exactly this one reply and never reads the socket again) -> await the
    connection's READER TASK under try/finally os._exit(0).

    Await the task, not connection.read(): the reader task's completion -- by the
    close sentinel, by ANY uncaught exception (e.g. garbage bytes killing the reader
    without a sentinel), or by cancellation -- is precisely the event "the ML process
    can never speak on this socket again".  Verified against the same-chunk
    request+FIN race and adversarial byte streams (2026-07-22 experiments).
    """
    server = connection.server
    token = server.attached_token
    if token is None or arg != token:
        raise RuntimeError(
            "attached_lifeline: claim rejected "
            "(not an attached host, or wrong token)")
    server._disarm_leak_guard()
    server._lifeline_connection = connection
    server.logger.info("Lifeline claimed")
    await connection.write(None)  # the claim ack
    t = connection._reader_task
    try:
        if t is not None:
            await t
    finally:
        server.logger.info("Lifeline dropped - exiting")
        os._exit(0)


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


def isabelle_home_user() -> str:
    home = resolve_isabelle_var("ISABELLE_HOME_USER")
    if not home:
        sys.stderr.write(
            "Cannot determine ISABELLE_HOME_USER: it is absent from the environment and "
            "`isabelle getenv` yielded nothing. (On Windows that fallback can never work: "
            "`isabelle` is a Cygwin shell script, which cmd cannot execute.)\n")
        sys.exit(1)
    return home

def _load_remote_procedures(logger: logging.Logger) -> None:
    home = isabelle_home_user()
    if not os.path.isdir(home):
        # The resolved home is not a directory at all — the settings value is broken
        # (on Windows this is what an unconverted POSIX path looks like). Loading no
        # components is a real failure here, not a normal state, and staying silent
        # would defer it to some later "unknown remote procedure" at call time.
        logger.error(
            f"ISABELLE_HOME_USER resolved to {home!r}, which is not a directory. "
            f"No RPC components can be loaded.")
        return
    rpc_components_path = os.path.join(home, 'etc', 'rpc_components')
    if not os.path.exists(rpc_components_path):
        # This file is an *optional* list of out-of-tree components. Its absence is
        # the normal case: the built-in procedures register themselves via the
        # @isabelle_remote_procedure decorator at import time, independently of it.
        logger.debug(
            f"No optional RPC component list at {rpc_components_path}; "
            f"{len(Remote_Procedures)} procedures are registered.")
        return
    logger.info(f"Loading RPC components from {rpc_components_path}")
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

def run_attached__() -> None:
    """Foreground, attached RPC host: no fork, no setsid, no detach.

    Entry point for Isabelle's ephemeral per-session launch
    (RPC_EPHEMERAL_HOST_PLAN.md; the ML side execs
    ``python -c "import Isabelle_RPC_Host; Isabelle_RPC_Host.run_attached__()"``).
    argv: <host:port -- port may be 0> <log_file> <ready_file> <token>

    The 300 s leak guard is armed HERE, first thing at entry -- before argv parsing
    and before bind, so even a launch that wedges pre-bind self-limits.  It is a
    daemon threading.Timer, NOT an event-loop timer: the synchronous component-import
    loop blocks the asyncio loop for its whole 1-40 s (or wedged-forever) duration --
    exactly the window the guard exists for -- during which a loop-based timer could
    never fire.  attached_lifeline disarms it via Timer.cancel() (thread-safe).
    """
    # ISABELLE_RPC_LEAK_GUARD_SECONDS exists for the test suite only (CI shortens it
    # to seconds to test the guard actually firing); production leaves it at 300.
    guard_seconds = float(os.environ.get("ISABELLE_RPC_LEAK_GUARD_SECONDS", "300"))
    guard = threading.Timer(guard_seconds, lambda: os._exit(1))
    guard.daemon = True
    guard.start()
    if len(sys.argv) != 5 or sys.argv[0] != "-c":
        sys.stderr.write("run_attached__ is an internal entry point; "
                         "argv: <addr> <log_file> <ready_file> <token>\n")
        sys.exit(1)
    addr, log_file, ready_file, token = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    try:
        logger = mk_logger_(addr, log_file)
        debugging = os.environ.get("ISABELLE_RPC_DEBUG", "").lower() in ("1", "true", "yes")
        server = Server(addr, logger, debugging,
                        attached_token=token, ready_file=ready_file, leak_guard=guard)
        with server:
            asyncio.run(server.run_server())
    except Exception:
        msg = traceback.format_exc()
        try:
            logger.critical("Attached RPC host failed", exc_info=True)  # type: ignore[possibly-undefined]
        except Exception:
            with open(log_file, "a") as f:
                f.write(f"CRITICAL: attached RPC host failed\n{msg}")
        os._exit(1)


def _daemon_body__(addr: str, log_file: str) -> None:
    """The daemon proper: record the PID, build the logger, serve forever.

    Runs in the ALREADY-DETACHED process, on every platform.  Extracted from
    fork_and_launch__ -- unchanged apart from the PID line, which gained its namespace
    tag in the same move -- so the POSIX grandchild and the Windows spawned child run the
    same code, and in particular so the recorded PID is the server's own on both, never
    the launcher's.
    """
    try:
        # Write PID file (fixed name per address, so each launch overwrites the previous)
        host_part, port_part = addr.rsplit(":", 1)
        pid_file = os.path.join(os.path.dirname(log_file), f"RPC_{host_part}_{port_part}.pid")
        # "<namespace> <pid>", not a bare pid.  The reader (RPC.ML kill_RPC_host) has to
        # pick between `kill` and `taskkill`, and that choice is decided by WHICH PYTHON
        # wrote this line, not by which platform Isabelle runs on.  A Cygwin python under
        # Windows takes the POSIX branch below and records a CYGWIN pid -- a small integer
        # from Cygwin's own allocator that names no Win32 process; `taskkill /F` on it
        # would force-terminate whatever unrelated native process happens to hold that
        # number.  os.name is exactly the discriminator, because it is also what selected
        # the branch.  Written by the daemon itself, so the two can never disagree.
        #
        # KNOWN, NOT FIXED HERE: in that same Cygwin-python-under-Windows configuration
        # the file also lands in the wrong DIRECTORY.  log_file is a native path (RPC.ML
        # passes File.platform_path), and posixpath.dirname("C:\\...\\RPC_x") is "", so
        # the join above writes into the cwd and RPC.ML's pid_file_path never finds it.
        # Pre-existing, and that configuration is already out of contract
        # (ISABELLE_RPC_PYTHON is meant to name a NATIVE interpreter); the only
        # consequence is that kill_RPC_host becomes a no-op, and an orphaned host is an
        # accepted outcome here.
        with open(pid_file, "w") as f:
            f.write(f"{os.name} {os.getpid()}")

        logger = mk_logger_(addr, log_file)
        debugging = os.environ.get("ISABELLE_RPC_DEBUG", "").lower() in ("1", "true", "yes")
        launch_server_(addr, logger, debugging)
    except Exception:
        import traceback
        msg = traceback.format_exc()
        try:
            logger.critical("RPC server failed to start", exc_info=True)  # type: ignore[possibly-undefined]
        except Exception:
            with open(log_file, "a") as f:
                f.write(f"CRITICAL: RPC server failed to start\n{msg}")
        os._exit(1)


def _spawn_detached_nt__(addr: str, log_file: str) -> None:
    """Windows counterpart of the double fork: re-spawn self detached, then return.

    Windows has no fork().  DETACHED_PROCESS is what setsid() buys: the child gets no
    console, so it belongs to no console process group and outlives the launcher.
    Windows has no parent-death propagation either, so it also outlives bash, the
    Isabelle build and the JVM.

    THE DEVNULL HANDLES ARE NOT COSMETIC -- they are why this cannot be a plain Popen.
    The caller is Isabelle's bundled Cygwin bash, and Isabelle/Scala reads bash's
    stdout/stderr pipes TO EOF *after* waitFor() returns (Pure/System/bash.scala,
    `out_lines.join`).  A child holding those write ends means EOF never arrives and
    Isabelle_System.bash_process blocks forever: bash has exited, the build hangs, and
    nothing anywhere reports an error.  close_fds=True (the default since 3.7, spelled
    out for the reader) keeps every other handle from leaking for the same reason.
    """
    import subprocess

    if not sys.executable:
        # `python -c` always has this; an embedded interpreter might not, and spawning
        # the wrong binary would be worse than saying so.
        sys.stderr.write(
            "Cannot launch the RPC host: sys.executable is empty, so this process "
            "cannot re-spawn itself as a detached daemon.\n")
        sys.exit(1)

    # argv again, so the child sees the same shape fork_and_launch__ is handed: one
    # convention, not two.
    #
    # Drop the cwd entry BEFORE the import.  Under -c the interpreter puts the cwd at the
    # front of sys.path, and cwd= below makes that the LOG directory -- an entry the
    # parent never had, ranked above everything, in a process that does lazy imports for
    # hours (the crash handler's `import traceback` among them).  A stray .py there would
    # shadow a stdlib module for the daemon only.  Dropping it leaves the legitimate
    # resolution to the PYTHONPATH set below, which reproduces the parent's own order.
    # (Python 3.11's -P flag does exactly this, but pyproject.toml floors at 3.10.)
    #
    # GUARDED, not a bare pop(0).  PYTHONSAFEPATH is inherited through env= below, and
    # when it is set the interpreter never prepends the cwd entry at all -- sys.path[0]
    # is then the FIRST PYTHONPATH entry, i.e. the launcher cwd this code injects to make
    # the import work.  An unconditional pop would delete exactly that and reintroduce the
    # import failure, in its worst shape: the parent still exits 0, so RPC.ML takes its
    # ok-branch, prints no diagnostic, and the user gets connect_retry's bare timeout.
    #
    # The test is `== ""` and nothing else.  "" is the literal signature of the entry -c
    # injects -- measured on CPython 3.10, 3.12 and 3.13, and unchanged by 3.11's
    # absolutisation, which covered the script-dir and -m cases but not -c.  Comparing
    # against os.getcwd() instead would be strictly worse on both platforms: it collapses
    # when the launcher's cwd IS the log dir (popping the injected entry -- the very
    # failure this guard exists to prevent), and on Windows the child's os.getcwd() is
    # canonicalised (drive-letter case, trailing separator, 8.3 vs long form) so the
    # string comparison is unreliable anyway.
    bootstrap = (
        "import sys\n"
        "if sys.path and sys.path[0] == '': sys.path.pop(0)\n"
        "from Isabelle_RPC_Host.rpc import _daemon_body__\n"
        "_daemon_body__(sys.argv[1], sys.argv[2])\n")

    try:
        subprocess.Popen(
            [sys.executable, "-c", bootstrap, addr, log_file],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            # stderr to the LOG FILE, not DEVNULL.  If the two-line bootstrap fails before
            # reaching _daemon_body__ -- a bad interpreter shim, a DLL/venv problem, an
            # import error -- DEVNULL would leave no trace anywhere: no log, no PID file,
            # and the parent still returns 0, so RPC.ML takes its ok-branch and never runs
            # the "which interpreter" diagnostic.  The user would see only connect_retry's
            # bare timeout 20-40 s later.  POSIX cannot have this blind spot because the
            # daemon IS the same process and its except handler always has the log file.
            # A regular file handle is not the bash pipe, so the EOF contract above is
            # equally satisfied.
            stderr=open(log_file, "a"),
            close_fds=True,
            # DETACHED_PROCESS: no console at all, hence also no window -- which is why
            # CREATE_NO_WINDOW is absent.  (It would merely be IGNORED alongside
            # DETACHED_PROCESS, not an error; the flag MSDN documents as conflicting is
            # CREATE_NEW_CONSOLE.  An earlier draft of this comment claimed an
            # ERROR_INVALID_PARAMETER that MSDN does not describe.)
            # CREATE_NEW_PROCESS_GROUP: makes "group root, not a member of the launcher's
            # group" explicit; a no-op given DETACHED_PROCESS, but free.
            creationflags=(subprocess.DETACHED_PROCESS |          # type: ignore[attr-defined]
                           subprocess.CREATE_NEW_PROCESS_GROUP),  # type: ignore[attr-defined]
            # PYTHONPATH, because cwd= below moves the child.  Under `-c`, sys.path[0] is
            # "" -- the CWD, re-resolved at EVERY import rather than fixed at startup, so
            # the hazard is dynamic.  (3.11 absolutised the script-dir and -m cases; `-c`
            # was not among them.  Measured on CPython 3.12.3.)  The child's cwd is not
            # the launcher's.
            # So a layout that resolves this package via the launcher's cwd (an editable
            # checkout, say) imports fine in the parent and fails in the child.  That
            # failure is the worst-shaped one available: the parent still exits 0, so
            # RPC.ML takes its ok-branch and never runs the "which interpreter"
            # diagnostic, leaving only connect_retry's bare timeout 20-40 s later.  POSIX
            # does not have this failure -- it chdir("/")s too, but this package was
            # already imported before the fork, so it is never re-resolved.  (Later
            # function-level imports there do re-resolve; they hit the stdlib.)
            #
            # PREPEND THE CWD ONLY.  Re-injecting all of sys.path would be actively worse:
            # PYTHONPATH is placed ahead of the interpreter's computed stdlib, so pushing
            # site-packages through it reorders the child's sys.path relative to the
            # parent's -- manufacturing the divergence this is meant to prevent -- and
            # sys.path also holds non-directory entries (PEP 660 __editable__ path-hook
            # keys) that are meaningless as PYTHONPATH.  Everything else the parent
            # resolved is reachable from the inherited environment already.
            #
            # cwd= does not merely invalidate the launcher's cwd entry, it SUBSTITUTES the
            # log dir for it -- which is why the bootstrap pops sys.path[0] and this
            # strips empty entries; between them the log dir reaches sys.path by neither
            # route.
            # EVERY INHERITED ENTRY IS ABSOLUTISED AGAINST THE LAUNCHER, and that is not
            # tidiness.  Python resolves a relative PYTHONPATH entry against the CWD, and
            # the child's CWD is the log dir.  Two shapes do it:
            #   ""  -- from a leading/trailing/doubled os.pathsep, which `export
            #          PYTHONPATH=:$PYTHONPATH` produces and which is common in the wild
            #   "." / "src" / "../lib" -- ordinary relative entries; PYTHONPATH=. is
            #          idiomatic
            # Either would put the log dir back on sys.path and silently undo the guarded
            # pop above.  abspath() resolves them against the LAUNCHER's cwd, which is
            # what the parent meant by them, and the `if p` drops the empty ones (abspath
            # would otherwise turn "" into the cwd rather than removing it).  Note a
            # truthiness test on the whole variable cannot see either shape -- the empty
            # entry lives INSIDE the value.
            #
            # ABSOLUTE ENTRIES ARE PASSED THROUGH UNTOUCHED, deliberately.  abspath is
            # normpath(join(cwd, p)), and for an already-absolute entry the join is a
            # no-op while normpath still collapses ".." LEXICALLY -- which is not how the
            # OS resolves ".." after a symlink.  `/opt/venvs/current/../shared` with
            # `current` a symlink into another tree would silently name a different
            # directory in the child than the parent imported from.  Only relative
            # entries need rewriting; absolute ones already mean the same thing in both
            # processes.
            #
            # (One shape this cannot express: a cwd containing os.pathsep -- legal in a
            # Windows filename -- would split into junk entries.  PYTHONPATH has no
            # escaping, so there is no fix at this layer.)
            env={**os.environ,
                 "PYTHONPATH": os.pathsep.join(
                     [os.getcwd()]
                     + [p if os.path.isabs(p) else os.path.abspath(p)
                        for p in os.environ.get("PYTHONPATH", "").split(os.pathsep)
                        if p])},
            # POSIX chdir("/")s so the daemon pins nothing.  On Windows a cwd holds a
            # directory HANDLE that blocks deletion or rename, so pinning the build tree
            # would be worse than on POSIX; the log directory is created by RPC.ML with
            # Isabelle_System.make_directory and is long-lived.  ("/" is not a usable
            # answer on Windows.)
            cwd=os.path.dirname(log_file) or None,
        )
    except OSError as e:
        # The parent CAN report this one, and must: it is the same class of failure the
        # POSIX branch reports from a failed os.fork, and RPC.ML turns a non-zero exit
        # into its "which interpreter" diagnostic.
        sys.stderr.write(f"Failed to spawn the detached RPC host: {e}\n")
        sys.exit(1)

    # Return 0 immediately.  Like the POSIX parent's os._exit(0), this claims only that
    # the handoff succeeded -- whether the server actually binds is established by
    # RPC.ML's connect_retry poll, identically on both platforms.


def fork_and_launch__():
    """
    Fork a daemon process to launch the server and exit the original process.
    """
    if len(sys.argv) != 3 or sys.argv[0] != "-c":
        sys.stderr.write("fork_and_launch__ is an internal function and should not be called directly")
    addr = sys.argv[1]
    log_file = sys.argv[2]

    # Windows has no fork().  Branch on os.name -- the convention this package already
    # uses (paths.py:31,78).  Not `hasattr(os, "fork")`, which names the missing
    # capability but lies about the replacement: the fallback needs the Win32 process
    # API, so any other fork-less target would be routed into a branch that cannot serve
    # it either.
    if os.name == "nt":
        _spawn_detached_nt__(addr, log_file)
        return

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

    _daemon_body__(addr, log_file)
