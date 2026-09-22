# Brief for the adversarial review of commit 3360162 (Isabelle_RPC), 2026-09-22

## What is under review
The commit `3360162` in the repository `/home/qiyuan/Current/MLML/contrib/Isabelle_RPC`
(its full diff: `git show 3360162`; the copy the agents were handed was a temporary
file, not kept). It implements the
plan `UNICODE_CONSISTENCY_FIX_PLAN.md` (read §1–§6, §6b, §8; §0 says how to run things),
after the plan's light re-check `ai-artifacts/UNICODE_PLAN_RECHECK_2026-09-21.md`.

Files changed: `Isabelle_RPC_Host/unicode.py`, `Isabelle_RPC_Host/position.py`,
`Isabelle_RPC_Host/__init__.py`, `test_unicode.py`, and the plan's status paragraph.

## The defect it fixes, in one paragraph
Two functions must agree: `pretty_unicode` renders Isabelle's ASCII notation
(`\<Longrightarrow>` → `⟹`) with two `re.sub` passes (escapes to characters, then the
sub/superscript fold `⇩i` → `ᵢ`); `FileIndex` (position.py) computes, per source symbol,
the column it occupies in that rendering, for the hover/definition tools that hand the
interpreting model `<file>.unicode.thy:line:column`. "What does this symbol render as"
was implemented twice; rule D44 (a symbol whose code point is private-use keeps its
`\<name>` escape) reached only `pretty_unicode`, so columns drifted by the escape's
length minus one after every phi-system keyword symbol.

## The design as ruled by the author (not up for re-litigation; relaxations may be PROPOSED)
- Keep the regex substitution and record positions while it runs (Option D of the plan;
  ruled 2026-08-18, kept 2026-09-22). A symbol-by-symbol renderer (Option C) is rejected.
- One private core `_render(text)` runs the two passes exactly as before and records
  `(start, end, output length)` per match; `pretty_unicode(src)` is its first component
  and stays byte-identical, CR handling included; `pretty_unicode_indexed(symbols)` takes
  `symbol_explode`'s output and returns the rendering plus one offset per symbol (n+1
  entries, the last the rendering's length). `FileIndex` hands over the symbols it already
  exploded and decides nothing about rendering. (Ruled 2026-09-22: "好".)
- Performance at this scale is NOT a criterion ("如果你是在担心性能的话这点问题根本不值得担心！
  请重点考虑可维护性与实现的优雅性！", 2026-09-22). Maintainability and elegance decide.
- §1b (our fold of two adjacent markers differs from Isabelle's) is recorded, not fixed;
  the `.unicode.thy` mirror staleness is dismissed; the fallback-order remedy and the
  `build/lib` deletion were withdrawn on 2026-09-22 (see the plan's §6b end and §6.7).
- `get_SYMBOLS_AND_REVERSED()` keeps returning a 4-tuple: callers unpack it by arity
  (`test_unicode.py:78`, `contrib/isasearch-web/site/prototype/tokenize_prototype.py:13`).
- The author welcomes proposals of the form "if constraint X were relaxed slightly, the
  code would become much more elegant" — state the constraint, the relaxation, the gain.

## Acceptance conditions the judge must rule on
Plan §6 items 1–9 and §8 steps 1–7 (each step's "Accepted when"). The commit's plan
paragraph "IMPLEMENTED 2026-09-22" lists what the drafter observed; verify, do not trust.

## How to run things (read-only with respect to the repository)
- Repository root `/home/qiyuan/Current/MLML`; Python: `.venv/bin/python` from that root,
  with `sys.path.insert(0, "contrib/Isabelle_RPC")` and
  `os.environ.setdefault("ISABELLE_HOME", os.path.abspath("contrib/Isabelle2025-2"))`.
  The symbol table must load 624 entries (phi-system is a registered component here).
- The suite: `cd contrib/Isabelle_RPC && ../../.venv/bin/python test_unicode.py`
  (about a minute; sweeps phi-system's .thy files); `--self-check` runs it once per
  mutant (about ten minutes) — run it only if your lens needs it.
- Consumers to consider: `contrib/Semantic_Embedding/Isabelle_Semantic_Embedding/hover.py:231-232,:321`,
  `.../premise_selection.py:45,:173-174`, `.../document_text.py:73-74`,
  `.../theory_structure.py:28-29`, `contrib/isasearch-web/site/prototype/*.py`,
  `contrib/Isa-Mini/IsaMini/AoA/*.py` (pretty_unicode callers), `Isabelle_RPC_Host/rpc.py:42-43`.
- The 4,506-file corpus digest before/after and the parent-commit run live only in the
  drafter's scratchpad; rebuild your own evidence if you need it.

## Hard rules for every agent
- Do not edit or create any file under `/home/qiyuan/Current/MLML`. No git command that
  changes state (no add/commit/stash/checkout/reset/clean). `git show`, `git log`, `git diff`
  are fine. Scripts go to your own scratchpad directory.
- NEVER run `isabelle build` in any form; do not start Isabelle or a REPL. You do not need
  Isabelle for this review.
- Work in English. Use the plan's own names; do not coin terms. Every claim carries a
  file:line or a command and its output. Distinguish a defect from a taste; label nitpicks
  as such rather than dressing them up.
