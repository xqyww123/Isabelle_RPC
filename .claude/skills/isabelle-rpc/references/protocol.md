# Wire protocol, connections, and host lifecycle

Source of truth: `Tools/RPC.ML` (ML client) and
`Isabelle_RPC_Host/rpc.py` (Python server).

## Tagged message framing

Every message on the socket is a MessagePack pair `(tag : int, payload)`
(`RPC.ML:298-315`).

| tag | channel |
| --- | --- |
| `0` | user channel — RPC request, or success response |
| `1` | remote error |
| `N > 1` | callback channel `N` |

```
User channel
  ML → Py   (0, (func_name, arg))     RPC request
  Py → ML   (0, result)               success
  Py → ML   (1, error_string)         failure  →  Remote_Calling_Failure
  ML → Py   (1, (messages, errobj))   failure  →  IsabelleError
```

`call_command'` writes `(0, (name, arg))`, then enters `dispatch_loop`, which keeps reading
tagged messages until it sees a `User_Response` (`RPC.ML:451-473`).

## Two-phase callback handshake

A callback occupies one channel tag for its whole lifetime. Python allocates a fresh
`cb_id` starting at 2 and increments (`rpc.py:61,147`).

```
Phase 1   Py → ML   (cb_id, callback_name)          "does this callback exist?"
          ML → Py   (cb_id, ((), None))             found
          ML → Py   (cb_id, (None, "Unknown callback: …"))
Phase 2   Py → ML   (cb_id, arg)
          ML → Py   (cb_id, (Some result, None))
          ML → Py   (cb_id, (None, error_string))
```

Why two phases: ML must know *which* callback's `arg_schema` to unpack the argument with
before it can read the argument at all.

Concurrency invariants:

- Python holds `_write_lock` across **both** phases (`rpc.py:150-165`). ML's `dispatch_loop`
  reads phase 1 then immediately reads phase 2, so the two must be adjacent in the byte
  stream. Awaiting the phase-1 ack inside the lock is safe because responses arrive on the
  independent `_reader_loop` task.
- A background `_reader_loop` (`rpc.py:84-101`) demultiplexes by tag: tags ≤ 1 go to
  `_user_channel`, tag `N > 1` resolves the pending future for `cb_id = N`. Hence several
  callbacks may be in flight at once, and a callback may be invoked from inside an RPC
  handler.
- On connection loss every pending future gets `ConnectionResetError` and a `None` sentinel
  unblocks `read()`.

Callback lookup is **local-first**: the command's own `callback` list shadows a global of the
same name (`lookup_callback`, `RPC.ML:446-449`).

## Errors

| Direction | Carrier |
| --- | --- |
| Python raised | full traceback string → ML `Remote_Calling_Failure {func_name = SOME name, message}` |
| ML raised inside a callback | `Runtime.exn_message_list`, markup-stripped → Python `IsabelleError` |
| unknown procedure | `write_error("Unknown procedure …")`, connection stays open |
| bad MessagePack from ML | logged, `write_error("Invalid RPC request")`, connection closed |

`trim_markup` (`RPC.ML:57-62`) strips text between `\005` (ENQ) control markers before an ML
error crosses the wire.

`Read_Timeout` is raised by the ML socket reader when the command's `timeout` elapses; the
timeout is stored in the connection's third slot and re-set on every `call_command'`
(`RPC.ML:492`).

If the server dies mid-call, `handle_client` gives the handler a 3-second grace period to
observe an already-resolved `IsabelleError` before cancelling it (`rpc.py:285-299`).

## Connections and the pool

```sml
type connection = BinIO.StreamIO.instream Unsynchronized.ref
                * BinIO.StreamIO.outstream
                * Time.time option Unsynchronized.ref   (* read timeout *)
```

- `get_connection ()` pops a pooled connection and **heartbeats it**. On failure it closes
  that connection *and drains the entire pool*, then dials a fresh one (`RPC.ML:540-551`).
- `release_connection` pushes it back.
- `call_command` wraps the pair: release on normal return, `close_connection` on exception
  (`RPC.ML:556-568`). Never return a connection to the pool after an error — a half-consumed
  response would desync the next caller.

The read side uses `Socket.select` with the timeout ref, so a hung server surfaces as
`Read_Timeout` rather than a permanent block.

## Host lifecycle (since 0.4.0: RPC_EPHEMERAL_HOST_PLAN.md)

`make_connection` branches on `addr_mode ()`:

- **Fixed** (`RPC_Host` set): `try_connect` (5 s) → use, or an actionable error. Isabelle
  never launches at a configured address; `AUTO_START_RPC_SERVER` is retired/ignored.
- **Ephemeral** (`RPC_Host` unset): consult the per-process state record
  `{pid, addr, token, lifeline}` (pid stamp discards heap-inherited records without
  closing their socket) → validate a live record with the `rpc_host_identity` token
  handshake (10 s; any tag-1 error = not ours; timeout/protocol errors are resolved by a
  zero-timeout readability poll of the lifeline — readable = EOF = host dead) → else
  launch under `launch_lock` (with an in-lock state re-check first).

The ephemeral launch (`do_launch_attached`): a holder thread blocks in `bash_process` on
a script that `mkdir -p`s the log dir, sweeps stale `RPC_attached_*` files (POSIX only),
and `exec`s

```
python -c "import Isabelle_RPC_Host
Isabelle_RPC_Host.run_attached__()" 127.0.0.1:0 <log> <ready_file> <token> >> <log> 2>&1
```

`run_attached__` arms a 300 s daemon-thread leak guard at entry, binds port 0, atomically
writes `"<port> <token>"` to the ready-file, runs the component imports, then serves. ML
polls the ready-file (fast-failing via the holder's outcome var if the python dies
instantly), connects, does the 60 s identity handshake, then claims the lifeline: an
`attached_lifeline` call whose reply is written by the procedure itself (it never
returns — it disarms the guard, acks once, then awaits the connection's reader task and
`os._exit(0)`s when it completes, i.e. the instant this Isabelle process dies).

`fork_and_launch__` (the classic double-fork daemon, unchanged) is now used **only by
external launches** (CLI/scripts); the ML side never calls it. It still writes the
per-address pid file; attached hosts write none.

`launcher.py`'s `main()` does **not** daemonize; it runs the server in the foreground. The two
entry points differ in `argv` shape: `main()` takes `[prog, addr, log_file]`,
`fork_and_launch__` expects `["-c", addr, log_file]`.

At startup the host imports every non-comment line of `$ISABELLE_HOME_USER/etc/rpc_components`
(`_load_remote_procedures`, `rpc.py:444-456`). `isabelle_home_user()` falls back to
`isabelle getenv -b ISABELLE_HOME_USER` when the env var is unset.

## Debug mode

`ISABELLE_RPC_DEBUG=1` sets `Server.debugging`, which:

- buffers raw incoming bytes and, on an `UnpackException`, dumps them to a
  `isabelle_rpc_unpack_error_*.bin` tempfile and logs the path (`rpc.py:250-268`);
- re-raises handler exceptions instead of swallowing them.
