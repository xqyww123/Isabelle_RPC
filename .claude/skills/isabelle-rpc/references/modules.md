# Module map

`Remote_Procedure_Calling.thy` loads the ML files in this order — later ones depend on
earlier ones:

```
RPC.ML  UUID.ML  Term_Digest.ML  theory_hash.ML  Universal_Key.ML
config.ML  pretty.ML  inner_syntax_error.ML  context.ML
run_python.ML  tracing.ML  dialogue.ML
```

---

## `Tools/RPC.ML` — `Remote_Procedure_Calling : REMOTE_PROCEDURE_CALLING`

The transport. See `references/protocol.md`.

```sml
type connection = BinIO.StreamIO.instream Unsynchronized.ref
                * BinIO.StreamIO.outstream
                * Time.time option Unsynchronized.ref

exception Read_Timeout
exception Remote_Calling_Failure of {func_name: string option, message: string}

type ('a,'b) callback = { name: string,
                          arg_schema: 'a MessagePackBinIO.Unpack.unpacker,
                          ret_schema: 'b MessagePackBinIO.Pack.packer,
                          function: 'a -> 'b,
                          timeout: Time.time option }
type callback' = { name: string, action: connection -> int -> unit }

type ('a,'b) command = { name: string,
                         arg_schema: 'a MessagePackBinIO.Pack.packer,
                         ret_schema: 'b MessagePackBinIO.Unpack.unpacker,
                         callback: callback' list,
                         timeout: Time.time option }

val mk_callback : ('a,'b) callback -> callback'
val register_global_callback  : ('a,'b) callback -> Context.generic -> Context.generic
val register_global_callback' : callback' -> Context.generic -> Context.generic
val get_global_callback : string -> callback' option

val call_command  : ('a,'b) command -> 'a -> 'b
val call_command' : ('a,'b) command -> connection -> 'a -> 'b
val get_connection : unit -> connection
val release_connection : connection -> unit

val load : string list -> unit            (* import Python modules on the host *)
val trim_markup : string -> string
```

Also `read` / `write` / `write_error` / `write_error'` for raw stream access, and the
`heartbeat_cmd` / `load_cmd` / `call_heartbeat_callback_cmd` commands.

`exception RPC_Fail` is declared but absent from the signature and never raised.

---

## `Tools/Term_Digest.ML` — `Term_Digest : TERM_DIGEST`

FNV-1a structural hashing, pure ML, no I/O. 64-bit `digest` and 128-bit
`digest128 = Word64.word * Word64.word`.

```sml
val string / class / sort / typ / term / goal : … -> digest
val string128 / class128 / sort128 / typ128 / term128 / thm128 / goal128 : … -> digest128
val to_hex : digest -> string          val to_hex128 : digest128 -> string
val digest_hasher : digest -> word     val digest128_hasher : digest128 -> word
val digest128_to_array : digest128 -> Word8Array.array
```

- Stable across runs and machines (fixed constants, no randomization).
- **Not alpha-invariant** — `Abs` binder names are hashed. `term128` distinguishes
  alpha-equivalent terms; pair it with `eq = op =`, never `aconv`.
- `digest128_hasher` collapses 128 → native word by `lo XOR (hi >> 1)`. A bucket function,
  not an identity.
- `thm128` caches on the thm's name hint, confirming hits by structural equality on the prop
  (name hints are not unique across dynamic-collection members). Anonymous thms hash
  `Thm.prop_of` uncached.

## `Tools/theory_hash.ML` — `Theory_Hash : THEORY_HASH`

16-byte content hash of a theory. `type hash = Word8Vector.vector`.

```sml
exception Cannot_Hash of theory
val hash_of : theory -> hash
val hash_of_short : Context.generic -> string -> string * hash
val theory_of : hash -> theory option
val is_persistent : hash -> bool
val resolve_theory : Context.generic -> string -> theory
val store_theory_hash : theory -> unit
val to_hex : hash -> string
```

Two schemes, distinguished by the **LSB of byte 0**:

| bit | scheme | meaning |
| --- | --- | --- |
| `0` | xxhash128 of `.thy` bytes + parent hashes, computed in Python over RPC | persistent (from a heap image) |
| `1` | FNV-1a-128 of the long theory name, computed locally | transient (live in jEdit) |

- **`hash_of` may block on RPC** for the persistent branch. Never call it while holding a lock.
- Its memo key is `Context.theory_identifier` — a runtime-local int. The reverse map
  `theory_of` only knows theories hashed in the current process, so Python's
  `theory_name_of` can legitimately return `None`.
- Python: `theory_hash.py` — `is_persistent`, `theory_xxhash128`, `async theory_name_of`,
  and a 1 GiB LMDB store at `platformdirs.user_cache_dir("Isabelle_Theory_Hash", "Qiyuan")`.

## `Tools/UUID.ML` — `UUID : UUID`

`type T = Word8Vector.vector` (exactly 16 bytes). `bytes_of` / `of_bytes` / `to_string`
(`8-4-4-4-12` hex, no RFC-4122 version/variant bits) / `generate_cmd` / `generate : int -> T list`.
Generation happens in Python (`generate_uuids`). **No call sites in this codebase.**

## `Tools/Universal_Key.ML` — `Universal_Key : UNIVERSAL_KEY`

A `universal_key` is raw bytes that identify an Isabelle entity **across sessions**, so
external stores (embedding DBs) survive restarts.

```
<theory_hash : 16 bytes> <tag : 1 byte> <payload>
```

| Shape | Layout |
| --- | --- |
| Theory | 16 bytes, no tag |
| Constant / Type / Class / Locale / Theorem_Collection / Method | 17 + `|name|`; payload = UTF-8 fully-qualified name |
| Theorem and the four rule kinds | always 32 bytes; payload = first 15 bytes of `Term_Digest.thm128` |

Tags: `0x01` Constant, `0x02` Theorem, `0x03` Type, `0x04` Class, `0x05` Locale,
`0x06` Theorem_Collection, `0x07` Method, `0x12` Intro, `0x22` Elim, `0x32` Induct,
`0x42` Case-split. Packed over the wire as msgpack *bin* (`packBytes`).

```sml
datatype entity_kind = ConstantK | TheoremK | TypeK | ClassK | LocaleK
                     | Theorem_CollectionK | MethodK
                     | IntroductionRuleK | EliminationRuleK
                     | InductionRuleK | CaseSplitRuleK

val key_of : thm_uk_cache option -> Context.generic -> entity -> universal_key
val key_of_theory' : theory -> universal_key
val key_of_theorem : thm_uk_cache option -> Context.generic -> xstring
                   -> universal_key * thm * bool * string   (* uk, thm, is_global, full_name *)
val retag_thm_key : universal_key -> Word8.word -> universal_key
val constituents_of : universal_key -> constituent list option
val thm_constituents : Context.generic -> thm -> Theory_Hash.hash * constituent list
val compute_constituents : Context.generic -> term -> Theory_Hash.hash * constituent list
val make_universal_key_callback' : thm_uk_cache option -> context_unpacker -> callback'
val make_key_of_theorems_callback' : thm_uk_cache option -> context_unpacker -> callback'
```

Critical invariants:

- **A theorem key's 16-byte prefix is NOT a theory hash.** It is the XOR of the *constituent*
  theories' hashes (the defining theories of every constant and type in `Thm.prop_of`),
  because a thm's true defining theory is unrecoverable. Never look it up as a theory, and
  **prefix range scans must skip thm/rule keys**.
- The defining theory is the leading qualifier of the qualified name (`HOL.conj → HOL`);
  unqualified Pure primitives belong to `Pure`.
- **WIP bit** = LSB of byte 0. For XOR keys it is OR'd across constituents, so a key is WIP
  iff any constituent is.
- `retag_thm_key` is O(1) and byte-identical to the corresponding `key_of_*_rule'`, but it
  deliberately does **not** write the constituents registry.
- `constituents_of` returns `NONE` for non-thm keys *and* for thm keys not built in this
  session — the registry is a session-local side effect of key construction.
- `pack_entity` on an anonymous thm errors (`Cannot pack anonymous thm (no name hint)`), yet
  `key_of_theorem'` works fine on one.
- `unpack_entity` always yields the `Named_*` constructor, never the thm-carrying one — a
  thm entity does not round-trip.
- `Theorem` and `Named_Theorem` share kind int 2; each rule shares a tag with its `Named_`
  variant.

Python (`universal_key.py`): `EntityKind` (IntEnum), `Entity` (NamedTuple), `destruct_key`,
`async universal_key_of`, `async universal_key_and_name_of`, `async key_of_theorems`,
`UndefinedEntity`, plus `is_WIP` / `is_thm_rule_key` / `xor_theory_prefix`.

`EntityKind.EXPERIENCE = 8` exists **only on the Python side** — the ML `entity` datatype has
no such constructor, and `unpack_entity_kind` raises `Unpack` on 8. Do not send kind 8 to
`universal_key_of`. `EntityKind.ALL` deliberately excludes `THEORY` and `EXPERIENCE`.

`UndefinedEntity` translation keys off the message prefix `"Undefined "` — other ML `error`s
(out-of-range fact index, unknown kind) surface as a raw `IsabelleError`.

## `Tools/context.ML` — `Context_Callbacks : CONTEXT_CALLBACKS`

Read-only enumeration of a context's entities, exposed as per-command callbacks. Registers
nothing itself.

Common arg (`unpackTuple9`, preceded by the context):

```
(target_theory : string option, the_theory_only : bool, exclude : string list,
 term_patterns : string list, type_patterns : string list,
 theories_include : string list, name_contains : string list,
 limit : int,               (* < 0 = unlimited *)
 target_type : string)      (* "" = no filter *)
```

Two return shapes: `([(uk, name, (file,line,offset))], warnings)`, or — for `theorems` and the
four rule kinds — `([(uk, name, pos, is_local)], warnings)`.

Behavioural traps:

- **`theorem_collection` returns a 2-tuple** (no `is_local`); `theorems` and the rule kinds
  return 3.
- **`target_type` is honoured only by `induction_rules` and `case_split_rules`.** Silently
  ignored elsewhere; a bad value warns rather than errors.
- **`term_patterns` do nothing for constants** (only `type_patterns`, matched against the
  constant's type constraint). Types/classes/locales/methods ignore all patterns.
- **Multiple `term_patterns` / `type_patterns` / `name_contains` are ANDed**, but
  `theories_include` substrings are ORed.
- `the_theory_only = true` makes `exclude` / `theories_not_include` inert.
- `limit` caps **per kind**, not the aggregate.
- Python caches only the *fully default* query (no filters, `limit < 0`, `ctxt is None`);
  any filter bypasses the cache.
- Cross-kind dedup: a dynamic-collection rule member is stored under both a Theorem key
  (`0x02`) and a rule key. When a query asks for `THEOREM` **and** ≥1 rule kind, the Theorem
  face is suppressed.

**Named-theorem bundle gate.** `Context.theorem_collection` enumerates dynamic facts
(`named_theorems`, `add_thms_dynamic` collections such as `derivative_eq_intros`). With
patterns present, a bundle survives iff **at least one** member's proposition matches. (It was
originally "≥ half"; loosened because bundles like `continuous_intros` have 313 heterogeneous
members and a proportional gate hid exactly the useful ones.) The Python docstring in
`context.py` still says "≥ half" — **stale; the ML is authoritative.**

**`parse_patterns`** parses each pattern individually, so one bad pattern doesn't sink the
rest. Cascade per term pattern: raw, then `(s)`, `s('a)`, `s ?x`, `?x s ?y`. Last resort,
`deschematize` rewrites every schematic-variable token to `_` and retries; a pattern rescued
this way is **kept**, with a warning. Diagnostics are marked up by `Inner_Syntax_Error`.

**Two opposite failure policies over the same parser:** the query path *ignores* an
unparseable pattern (warn + drop); `Experience.constituents` **fail-fasts** with an `error`,
because silently ignoring a goal pattern would write a wrong experience record.

**Experience memory.** `Experience.constituents` maps goal patterns to the maximal antichain
of defining theories (Python XORs those hashes into the key prefix). `Context.experiences`
scores candidates by hit rate over query patterns using a *relaxed* matcher — type-agnostic,
coercion-transparent (peels constants registered in `coercion_ignores`), bidirectional,
subterm. `Context.loaded_theory_hashes` returns the current theory + all ancestors so Python
can tell which experiences are available.

`mk_prop_pattern_matcher`'s leading `int` is an **expensive-match budget** and is load-bearing:
the theorems engine passes 200; the bundle gate passes `max(1,|term_pats|) * |members|`. Over
an unbounded library list, an unbounded budget means a full library search.

## `Tools/pretty.ML` — `RPC_Pretty : RPC_PRETTY`

Rendering and raw AST serialization for terms/types/thms.

```sml
type pp_name = string
val pack_raw_term / unpack_raw_term : term …      (* tags: Const=3 Free=4 Var=5 Bound=6 Abs=7 App=8 *)
val pack_raw_typ  / unpack_raw_typ  : typ …       (* tags: Type=0 TFree=1 TVar=2 *)
val string_of_term : pp_name -> Context.generic -> term -> string
val term_packer / typ_packer : pp_name -> Context.generic -> … packer
val thm_packer : pp_name -> Context.generic -> thm packer
val print_term : printing_config -> Proof.context -> term -> string
val print_typ  : printing_config -> Proof.context -> typ  -> string
val s_expression : term -> string
val trim_markup : string -> string
```

`pp_name` accepted by `string_of_term`: `sexpr`, `natural`, `oridinary`/`pretty`,
`type`/`typed_pretty`, `type_sort`, `type_nv`/`typed-nv_pretty`, and probabilistic training
formats `T4S4`, `T4S4nv`, `T2S3`, `T2S3nv`. `term_packer`/`typ_packer` accept a **narrower**
set (`sexpr`, `pretty`, `typed_pretty`, plus `typed-nv_pretty` for types) and error otherwise.

- The `*_nv` variants are currently identical to their non-`nv` counterparts (the
  `Printer.show_types_nv` lines are commented out), and `type_sort` does not actually show
  sorts.
- `print_term`/`print_typ` force `show_markup = true` and reconstruct display text from the
  inner-syntax XML. That path carries an Isabelle2025-2 compatibility layer (transparent
  wrappers, `entity kind="fixed"`) and is brittle against markup changes.

**Floating type variables.** A type variable occurring in no term variable's type — reachable
only through a polymorphic `Const` — is invisible under the type-suppressing default. E.g.
`filterlim harm at_top sequentially` with `harm :: nat ⇒ 'a` and `'a` unpinned prints as bare
`harm`, hiding that the goal is under-constrained and unprovable. `print_term` now computes
the floating set, picks a minimal set of carrier constants by greedy set cover (preferring
non-head, wider-coverage, leftmost occurrences), and annotates those. Self-gating: no floating
tvar ⇒ byte-identical output to before. Term-only — `print_typ` never surfaces them.

## `Tools/inner_syntax_error.ML` — `Inner_Syntax_Error : INNER_SYNTAX_ERROR`

Turns an opaque inner-syntax parse error (which renders `at ""` with no offset when reading
from a bare string) into a message that splices a `【parsing fails here】` marker at the failing
token.

```sml
val read_positioned       : (Proof.context -> string -> 'a) -> Proof.context -> string -> 'a
val read_positioned_list  : (Proof.context -> string list -> 'a) -> …
val read_positioned_typed : (Proof.context -> (typ * string) list -> 'a) -> …
val guard   : (unit -> string option) -> (unit -> 'a) -> 'a
val format  : {ignored: string option} -> (string -> string option) -> string -> string option
val marker_strings : (Proof.context -> string -> 'b) -> Proof.context -> string list -> string option
val positioned : string -> string
val sentinel_id : string
```

The three `read_positioned*` wrappers are drop-in replacements for `Syntax.read_*`: identical
on success and on non-parse errors, marked-up only on a parse failure.

How it works: on failure it *re-parses* a positioned copy of the string (a throwaway probe),
reads the `<position offset=…>` out of the error's YXML, and marks a unique, whitespace-snapped
context window of ≥26 symbols around it.

- **The positioned probe must never produce a proof-consumed value** — positioned input
  perturbs schematic type-variable indices (`??'a` → `??'a13`).
- Only genuine *parse* errors carry a position. Type/check errors and "unexpected end of
  input" pass through untouched.
- Non-`ERROR` exceptions (notably `Interrupt`) are never reformatted.
- Offsets are 1-based **symbol** indices, not bytes.
- `read_positioned_typed` deliberately probes with `dummyT`, dropping the real type
  constraint — safe, because a type constraint cannot move a grammar-level parse failure, and
  `guard` falls back to the untouched original error on any divergence.

## `Tools/config.ML` — `Config : CONFIG`

Extends the stock `Config` with an RPC-visible option registry.

```sml
val register_rpc_option : string -> Config.value Config.T -> unit
val make_config_lookup_callback : Universal_Key.context_unpacker -> callback'
```

See `references/registry.md` for the `Config.lookup` wire contract.

## `Tools/tracing.ML`, `Tools/dialogue.ML`, `Tools/run_python.ML`

- `Isabelle_Log` — `datatype log_type = TRACING | WARNING | WRITELN` (wire `0/1/2`), backing
  the global `log` callback.
- `dialogue.ML` — global `dialogue` callback via `Active.dialog_text`. Blocks on `Future.join`.
- `Run_Python` — `val run : string -> string option`, `val run_with : callback' list -> string -> string option`.

---

## Python-only modules

### `position.py`

Three coordinate systems, all 1-based:

| System | Unit |
| --- | --- |
| **symbol offset** (`raw_offset`) | index into `symbol_explode(source)` — `\<forall>` is **one** symbol. This is what Isabelle/ML reports. |
| **ASCII line/column** | characters of the symbol-escape source — `\<forall>` occupies 8 columns |
| **Unicode line/column** | rendered characters — `∀` occupies 1; sub/superscript modifiers occupy 0 |

`FileIndex(source)` precomputes the three offset arrays and provides all six conversions
(`isabelle_to_ascii`, `ascii_to_isabelle`, `unicode_to_ascii`, …). `get_file_index(path)` is a
realpath-keyed cache invalidated by a `watchdog` observer over at most 64 directories (LRU);
beyond that, stale indexes can be served.

**Column-free addressing** — locate a token by name instead of counting columns:

```python
offsets = idx.symbol_offsets(line, "∀")   # or "\\<forall>", or "Suc"
```

Returns file-global 1-based symbol offsets, respecting Isabelle token boundaries (`x` does not
match inside `xs`) and skipping `(* … *)` comments. Also `ascii_line(line)` and
`end_of_line_offset(line)`.

`IsabellePosition(line, raw_offset, file)` is offset-based and is what ML emits.
`Position(line, column, file)` (and `AsciiPosition` / `UnicodePosition`) is column-based.
Convert between the families through a `FileIndex`, which needs the file on disk.
`Position.offset_of` is a *different*, naive char offset that reads the file as latin-1 — don't
mix it with the `FileIndex` machinery.

Only `IsabellePosition` and `Position` are re-exported from the package; import `FileIndex`,
`symbol_explode`, `get_file_index`, `AsciiPosition`, `UnicodePosition` from
`Isabelle_RPC_Host.position`.

### `unicode.py`

Isabelle symbol ↔ Unicode. The tables are parsed from `$ISABELLE_HOME/etc/symbols` and
`$ISABELLE_HOME_USER/etc/symbols` (located by shelling out to `isabelle getenv`), cached once
per process.

- `pretty_unicode(src)` / `unicode_of_ascii(src)` — `\<forall>` → `∀`, then merge
  sub/superscript pairs (`⇩1` → `₁`). Unknown symbols pass through.
- `ascii_of_unicode(src)` — the inverse. **Order matters**: restore sub/superscripts first,
  then reverse-map symbols.
- If `isabelle` is not on `PATH`, the tables come out empty and conversions **silently no-op**.

### `tokens.py`

A simplified Isabelle lexer over symbol-escape text, used by `FileIndex.symbol_offsets`.
`tokenize_isabelle_line` skips nestable `(* … *)` comments but **deliberately keeps strings and
cartouches**, since their inner syntax carries the entities a hover targets. `\<lambda>` is
classified as an operator, not a letter.
