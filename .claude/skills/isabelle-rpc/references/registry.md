# Registry: every built-in procedure and callback

Two vocabularies, opposite directions:

- **Procedure** — lives in Python, called by ML via `call_command`. Declared with
  `@isabelle_remote_procedure("name")`.
- **Callback** — lives in ML, called by Python via `await connection.callback("name", arg)`.
  Either *global* (registered once at ML load time) or *per-command* (passed in the command's
  `callback` list).

## Python procedures (ML calls these)

| Name | Defined at | Arg → Ret |
| --- | --- | --- |
| `heartbeat` | `rpc.py:371` | `unit → unit`. Pool health check. |
| `load_pymodule` | `rpc.py:378` | `string list → (string * string option) list`. Import modules; `SOME err` per failure. |
| `call_heartbeat_callback` | `rpc.py:404` | `unit → string`. Demo: calls back into ML `isabelle_heartbeat`. |
| `generate_uuids` | `rpc.py:429` | `int → bytes list` (16-byte each). |
| `run_python` | `run_python.py:22` | `string → string option`. Unsandboxed `exec`. |
| `Theory_Hash.store` | `theory_hash.py:66` | `(hash * string) list → unit`. Persists to LMDB. |
| `xxhash128_theory` | `theory_hash.py:77` | `(string * hash list) → hash`. xxhash128 of file bytes + parent hashes. |
| `position.offset_to_line_column` | `position.py:537` | `(file, symbol_offset) → (line, ascii_column)` |
| `position.line_column_to_offset` | `position.py:548` | `(file, line, column) → symbol_offset` |

ML-side wrappers: `Remote_Procedure_Calling.heartbeat_cmd` / `.load_cmd` / `.call_heartbeat_callback_cmd`,
`UUID.generate_cmd`, `Run_Python.run` / `.run_with`, `Theory_Hash.store_theory_hash`.

`run_python` wraps the source in `async def __aexec__(connection): …` and awaits it, so the
source may use `await` and `return`. `connection` is the only injected name. It passes
`callback = []`, so per-command callbacks (notably `Config.lookup`) are unavailable inside it.

## Global ML callbacks (always available)

Registered via `Theory.setup (Context.theory_map (register_global_callback …))`.

| Name | Defined at | Arg → Ret |
| --- | --- | --- |
| `isabelle_heartbeat` | `RPC.ML:422` | `unit → string` |
| `position.symbol_explode` | `RPC.ML:430` | `string → string list`. Isabelle symbol split. |
| `log` | `tracing.ML:24` | `(int, string) → unit`. Level `0=TRACING 1=WARNING 2=WRITELN`. |
| `dialogue` | `dialogue.ML:10` | `(string, string list) → string`. Blocks on a PIDE click. |
| `Theory_Hash.theory_name_of` | `theory_hash.ML:194` | `bytes → string option`. Reverse hash lookup; `None` if not hashed in this runtime. |

The `log` level encoding is duplicated in `Connection.LogType` (`rpc.py:183-187`) and must
stay `0/1/2`; `Isabelle_Log.unpack_log_type` raises `Unpack` on anything else.

## Per-command ML callbacks (you must pass them in `callback = [...]`)

Constructed by `make_*_callback` functions. None of them self-register.

| Name | Constructor |
| --- | --- |
| `Config.lookup` | `Config.make_config_lookup_callback : context_unpacker -> callback'` |
| `universal_key_of` | `Universal_Key.make_universal_key_callback[']` |
| `key_of_theorems` | `Universal_Key.make_key_of_theorems_callback'` |
| `Context.constants` | `Context_Callbacks.make_constants_callback` |
| `Context.theorems` | `Context_Callbacks.make_theorems_callback` |
| `Context.types` / `.classes` / `.locales` / `.methods` | `make_types_callback` etc. |
| `Context.theorem_collection` | `make_theorem_collection_callback` |
| `Context.introduction_rules` / `.elimination_rules` / `.induction_rules` / `.case_split_rules` | `make_*_rules_callback` |
| `Context.the_theory_long_name` | `make_theory_long_name_callback` |
| `Context.theory_long_name_and_path` | `make_theory_long_name_and_path_callback` |
| `Context.loaded_theory_hashes` | `make_loaded_theory_hashes_callback` |
| `Experience.constituents` | `make_experience_constituents_callback` |
| `Context.experiences` | `make_experiences_callback` |

They are wired up in [`semantic_store.ML`](https://github.com/xqyww123/Premise_Embedding/blob/master/Tools/semantic_store.ML)
(`make_entity_callbacks`, ~line 1014) and [`agent_server.ML:1391`](https://github.com/xqyww123/Isa-Mini/blob/main/Agent/agent_server.ML#L1391).
**Nothing in `Isabelle_RPC` itself registers them** — without that layer the names do not
exist on the wire.

### `context_unpacker`

`type context_unpacker = Context.generic MessagePackBinIO.Unpack.unpacker`

Every `Context.*` callback takes its context off the wire through one of these:

- `static_context_unpacker ctx` — reads a msgpack nil, yields a fixed context. Use when the
  context is pinned at server setup.
- The AoA agent supplies an unpacker that reads a state-id string and resolves the live proof
  state.

## `Config.lookup` in detail

```sml
val _ = Config.register_rpc_option "Semantic_Embedding.embedding_model" cfg   (* ML *)
```

```python
model = await connection.config_lookup("Semantic_Embedding.embedding_model")
```

Arg is `(ctxt, name)` — `ctxt` defaults to `None`, which ML resolves via
`Context.cases Proof_Context.init_global I`. An unregistered name is an ML `error` and
surfaces as `IsabelleError`. `register_rpc_option` is last-write-wins.

`Connection.semantic_vector_store` (monkey-patched by `Isabelle_Semantic_Embedding.semantics`,
outside this repo) is built on `config_lookup` and therefore inherits the per-command
requirement.
