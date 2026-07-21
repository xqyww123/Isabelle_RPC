---
name: isabelle-rpc
description: How to use Isabelle_RPC — call async Python procedures from Isabelle/ML over MessagePack/TCP, and call back into ML from Python. Covers the command/callback API, the multiplexed wire protocol, procedure registration, and the Tools/ modules (Universal_Key, context queries, Theory_Hash, RPC_Pretty, Inner_Syntax_Error, position/unicode).
---

# Isabelle_RPC: call Python from Isabelle/ML

Isabelle/ML calls Python procedures; Python may call back into ML *during* a call.
For the opposite direction (Python drives Isabelle) use **Isa-REPL** instead.

**Location:** repository root · **Protocol:** MessagePack over TCP · **Default address:** `127.0.0.1:27182`

> **The Python side is fully `async`.** Every procedure is an `async def`; every
> `connection.*` call must be `await`ed. A plain `def` procedure will not work.

## Session setup

```isabelle
theory My_Theory
  imports Remote_Procedure_Calling   (* session Isabelle_RPC *)
begin
```

`ROOT`: `session Isabelle_RPC = Performant_Isabelle_ML + theories Remote_Procedure_Calling`.
The MessagePack library (`mlmsgpack`) lives in the **base** session, at
[`Performant_Isabelle_ML/contrib/mlmsgpack/mlmsgpack.sml`](https://github.com/xqyww123/Performant_Isabelle_ML/blob/main/contrib/mlmsgpack/mlmsgpack.sml) — not under this project.

After editing any `.ML` file here, just restart the RPC/REPL server; no `isabelle build` needed.

## Starting the host

You usually do **not** start it by hand. On the first `call_command`, ML auto-launches a
daemonized host (double-fork) and retries the connection for ~20 s.

| Knob | Effect |
| --- | --- |
| `RPC_Host` | Address, e.g. `export RPC_Host=127.0.0.1:9999`. Default `127.0.0.1:27182`. |
| `AUTO_START_RPC_SERVER=0` \| `false` | Disable auto-launch; ML errors out instead. |
| `ISABELLE_RPC_DEBUG=1` \| `true` \| `yes` | Debug mode: capture the byte stream and dump it on an unpack error. Only honoured on the auto-launched path. |

Logs and the PID file land in `$ISABELLE_HOME_USER/log/` as `RPC_<host>_<port>*`.
Manual start: `python launcher.py [addr] [log_file]`, or the installed
console script `isabelle-rpc-host` (pip package `isabelle-rpc`).

## Writing a procedure (Python)

```python
from Isabelle_RPC_Host import isabelle_remote_procedure, Connection

@isabelle_remote_procedure("compute_sum")        # the name ML calls
async def compute_sum(arg, connection: Connection) -> int:
    await connection.writeln(f"summing {len(arg)} ints")   # prints in Isabelle's output
    return sum(arg)
```

`arg` is the unpacked MessagePack payload; the return value is packed back to ML.
Raising any exception sends the traceback to ML as a `Remote_Calling_Failure`.

## Calling it (Isabelle/ML)

```sml
open MessagePackBinIO.Pack MessagePackBinIO.Unpack

val compute_sum_cmd : (int list, int) Remote_Procedure_Calling.command = {
  name       = "compute_sum",
  arg_schema = packList packInt,          (* ML -> Python *)
  ret_schema = unpackInt,                 (* Python -> ML *)
  callback   = [],                        (* a LIST, not an option *)
  timeout    = SOME (Time.fromSeconds 30) (* read timeout, NONE = block forever *)
}

val n = Remote_Procedure_Calling.call_command compute_sum_cmd [1,2,3,4]   (* = 10 *)
```

`call_command` borrows a pooled connection, releases it on success and closes it on
exception. The idiomatic style in this codebase is to inline the record at the call site
(see [`semantic_store.ML`](https://github.com/xqyww123/Premise_Embedding/blob/master/Tools/semantic_store.ML)).

For an explicit connection: `get_connection ()` → `call_command' cmd conn arg` → `release_connection conn`.

## Making the procedure reachable

The host only knows procedures whose module has been imported. Two ways:

1. **From ML (what this codebase does):**
   `Remote_Procedure_Calling.load ["Isabelle_Semantic_Embedding"]` — tells the running host
   to `import` that package, which registers its `@isabelle_remote_procedure` functions.
   Raises on import failure.
2. **At host startup:** list one module name per line in `$ISABELLE_HOME_USER/etc/rpc_components`.
   (Present but effectively unused here — everything goes through `load`.)

## Callbacks: Python → ML, mid-call

```sml
val my_callback : (string, int) Remote_Procedure_Calling.callback = {
  name       = "my_callback",
  arg_schema = unpackString,   (* Python -> ML: an UNpacker *)
  ret_schema = packInt,        (* ML -> Python: a packer   *)
  function   = String.size,
  timeout    = NONE
}
```

Two registration scopes:

```sml
(* Global — visible to every command, forever *)
val _ = Theory.setup (Context.theory_map
          (Remote_Procedure_Calling.register_global_callback my_callback))

(* Per-command — only during calls of this command; shadows a global of the same name *)
val my_cmd = { name = "my_rpc", arg_schema = packUnit, ret_schema = unpackString,
               callback = [Remote_Procedure_Calling.mk_callback my_callback],
               timeout = SOME (Time.fromSeconds 10) }
```

```python
@isabelle_remote_procedure("my_rpc")
async def my_rpc(arg, connection: Connection):
    n = await connection.callback("my_callback", "hello")   # n = 5
    return f"callback returned {n}"
```

Callbacks may be in flight concurrently — each gets its own channel tag.

### `Connection` helpers

| Method | Backing ML callback |
| --- | --- |
| `await conn.writeln/warning/tracing(msg)` | `log` (global) |
| `await conn.callback(name, arg)` | any registered callback |
| `await conn.dialogue(question, options) -> str` | `dialogue` (global) — **blocks on a PIDE click; hangs headless** |
| `await conn.config_lookup(name, ctxt=None)` | `Config.lookup` (**per-command only**) |
| `await conn.getenv(name, default=None)` | `getenv` (global) — Isabelle-process env first (`""` = unset), then host `os.environ`; degrades to host env against pre-getenv heaps |
| `Connection.current()` | the current task's connection, or `None` |

`conn.server.logger` writes to the host log file, not to Isabelle.

## MessagePack schemas

Packers (ML → Python) and unpackers (Python → ML) mirror each other:

`packUnit` `packBool` `packInt` `packReal` `packString` `packBytes` `packList s`
`packOption s` `packPair (s1,s2)` `packPairList (s1,s2)` `packTuple3` … **`packTuple12`**
`packVector` `packArray` `packWord64`
— and the `unpack*` counterparts, likewise up to `unpackTuple12`.

- `packString` ↔ Python `str`; `packBytes` ↔ Python `bytes` (msgpack *bin*). Universal keys use `packBytes`.
- `packPairList` ↔ a list of 2-tuples (Python may hand back a dict's items).
- Full list: [`mlmsgpack.sml`](https://github.com/xqyww123/Performant_Isabelle_ML/blob/main/contrib/mlmsgpack/mlmsgpack.sml).

## Errors and timeouts

| ML | meaning |
| --- | --- |
| `Remote_Calling_Failure of {func_name, message}` | Python raised, or protocol error |
| `Read_Timeout` | `timeout` in the command elapsed while reading |

Python sees ML errors as `IsabelleError(errors: list[str], obj)`.
(`exception RPC_Fail` exists in `RPC.ML` but is not exported and never raised — ignore it.)

## Gotchas

- **`callback` is a `callback' list`.** `callback = NONE` does not typecheck; use `[]`.
- **Python procedures must be `async def`**, and `connection.callback(...)` must be `await`ed.
- **`register_global_callback` is a mutable global side effect.** Its
  `Context.generic -> Context.generic` type is cosmetic (it returns `I`); the callback is
  installed when the ML file loads, regardless of which theory you thread it through. Names
  collide silently — last registration wins.
- **`Config.lookup` is not global.** It is a `callback'` you must put in a command's
  `callback` list. Anything calling `conn.config_lookup` from a command that omits it will
  fail — including `run_python`, which passes `[]` by default.
- **`run_python` is an unsandboxed `exec`** of ML-supplied source in the host process.
- **`dialogue` blocks** on an interactive PIDE click; never use it in batch runs.
- **The pooled connection is heartbeated** before reuse; a dead one purges the whole pool.

## Where to look next

| File | Contents |
| --- | --- |
| `references/protocol.md` | Tagged wire protocol, 2-phase callback handshake, connection pool, host lifecycle |
| `references/registry.md` | Every built-in procedure and callback, with wire schemas |
| `references/modules.md` | The `Tools/*.ML` and `Isabelle_RPC_Host/*.py` module map with exact signatures |

Real call sites to imitate: [`semantic_store.ML`](https://github.com/xqyww123/Premise_Embedding/blob/master/Tools/semantic_store.ML) (ML side),
[`premise_selection.py`](https://github.com/xqyww123/Premise_Embedding/blob/master/Isabelle_Semantic_Embedding/premise_selection.py) (Python side),
[`agent_server.ML`](https://github.com/xqyww123/Isa-Mini/blob/main/Agent/agent_server.ML).

The top-level `test_*.py` / `test_*.ML` / `*.md` files in the repository root are
untracked scratch and may be stale — prefer the sources above.
