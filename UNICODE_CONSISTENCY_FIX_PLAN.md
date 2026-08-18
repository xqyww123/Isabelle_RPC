# Fixing the FileIndex / pretty_unicode divergence

Status: proposal, not applied. Written 2026-08-18 after a review of commits `eab47d6`
and `8b7325e` found a live regression.

## 0. Where things are, and how to run them

Everything here is in the `contrib/Isabelle_RPC` submodule, its own git repository, on
branch `master`. Read this section before §1 if you are picking the work up cold.

**Already committed, and the baseline this plan builds on:**

```
eab47d6  load the table Isabelle actually presents (ISABELLE_SYMBOLS, not a list
         rebuilt from ISABELLE_HOME); D44, a private-use code point is not
         substituted; get_SYMBOL_FILES()
8b7325e  recognise an escape by Isabelle's rule rather than scanning to the next '>'
f9e139c  make test_unicode.py able to fail, and prove it with a mutation self-check
```

**The files, and the lines that matter:**

```
Isabelle_RPC_Host/unicode.py     pretty_unicode and its two passes; the escape pattern;
                                 is_private_use; SUBSUP_TRANS_TABLE (142 hand-written
                                 entries -- no symbols file carries folding data)
Isabelle_RPC_Host/position.py    symbol_explode; FileIndex.__init__ (the duplicate
                                 rendering logic, roughly :95-155, with the two bare
                                 lookups at :110 and :120); the six conversions at :176+
test_unicode.py                  the suite, and `--self-check`, whose MUTANTS list
                                 currently hardcodes unicode.py as its target
```

**Running things:**

```bash
cd contrib/Isabelle_RPC
python3 test_unicode.py                # the suite
python3 test_unicode.py --self-check   # mutation check: every mutant must be killed
python3 test_paths.py
```

**The prerequisite §1's whole defect depends on.** The 135 private-use symbols come from
`contrib/phi-system/symbols-words`, which reaches `ISABELLE_SYMBOLS` only because
`contrib/phi-system` is registered as an Isabelle component — on this machine, by a line
in `~/.isabelle/Isabelle2025-2/etc/components`. Without that registration the table loads
439 entries instead of 624, holds no private-use symbol, and **the defect is invisible**:
`pretty_unicode(r'\<proc>')` returns the escape for the wrong reason (the symbol is
simply absent, the pre-`eab47d6` accident of §1), and the suite reports three checks as
NO DATA and exits 0. That is exactly the vacuous pass §6.5 warns about, reached by
following this section. Check what you have before trusting a green run:

```bash
contrib/Isabelle2025-2/bin/isabelle getenv ISABELLE_SYMBOLS   # must name phi-system
python3 -c "import sys; sys.path.insert(0,'contrib/Isabelle_RPC'); \
  from Isabelle_RPC_Host.unicode import get_SYMBOLS; print(len(get_SYMBOLS()))"   # 624
```

For an ad-hoc check, run from the **repository root**, not from `contrib/Isabelle_RPC`
(the paths below are relative to the root, and the `cd` in the block above is not in
force). `watchdog` must be importable — `position.py` imports it — which the editable
install in `.venv` provides here:

```python
import sys, os
sys.path.insert(0, "contrib/Isabelle_RPC")
os.environ.setdefault("ISABELLE_HOME", os.path.abspath("contrib/Isabelle2025-2"))
from Isabelle_RPC_Host.unicode import pretty_unicode
from Isabelle_RPC_Host.position import FileIndex, symbol_explode
```

**Corpora used by the measurements in this document**, stated precisely enough to
rebuild, because §8 step 1's acceptance names a file count. `.thy` and `.ML`, **excluding
`*.unicode.thy`** — that exclusion is what turns the raw counts into the ones quoted:
`contrib/phi-system` 352 raw, 323 after; `contrib/Isabelle2025-2/src` 3,024 raw, 2,601
after; plus the first 1,500 of `contrib/afp-2026-05-13/thys` **in `os.walk` order**,
which is filesystem-dependent and therefore not reproducible elsewhere. 323 + 2,601 +
1,500 = 4,424. If you cannot reproduce the AFP slice, say so and quote your own number
rather than this one; the diff's value is that it is 0, not that it is over 4,424 files.

**The review evidence** — including the reference indexed renderer the §3 invariant needs,
and the symbol-driven prototype this plan is to be built from — is in
`review-2026-08-18/`, with a README saying what each script established.

## 1. The defect

`Isabelle_RPC_Host/position.py`'s `FileIndex` computes, for every Isabelle symbol in a
source file, the column it occupies **in the Unicode rendering of that file**. The
Unicode rendering is produced by `pretty_unicode`. The two must agree exactly, or a
position computed from one addresses the wrong character in the other.

They no longer agree. `FileIndex.__init__` (`position.py:105-129`) decides what a
symbol renders as with a bare `SYMBOLS.get(sym, sym)`. `pretty_unicode` now applies
D44: a symbol whose code point is private-use is left as its literal `\<name>`. Before
`eab47d6` the 135 private-use symbols were not in the loaded table at all, so both
sides left `\<proc>` as seven characters and agreed by accident. Now `FileIndex`
counts it as one character and `pretty_unicode` still emits seven.

Measured on `contrib/phi-system/Phi_System/Resource_Template.thy:156`:

```
'Itself': FileIndex col=15  actual col=21   drift -6
'Rel'   : FileIndex col=54  actual col=66   drift -12
'Normal': FileIndex col=59  actual col=71   drift -12
```

Six columns per preceding private-use symbol on the line.

**Live consumer.** `Semantic_Embedding/hover.py:321` (`idx.isabelle_to_unicode`) and
`:231-233` (`mk_definition_tool` → `to_unicode_position`), both reached from the
deformalization loop at `semantic_interpretation.py:1160-1161` with `unicode=True`.
The interpreting model is handed `<file>.unicode.thy:line:column`, where the file is
rendered by `pretty_unicode` and the column by `FileIndex`.

**Blast radius.** 100 of 55,772 `.thy` sources carry a private-use escape: 94 in
phi-System, and — worth noting, because it shows the leak is not confined to
phi-System's own tree — and 2 in the `src/Doc` of each of the three distribution trees
present here (`Isabelle2025-2`, `Isabelle2024`, `Isabelle2024_bak`), affected only
because phi-System's `symbols-words` is registered on this machine. The ASCII-coordinate
procedures (`position.py:537-555`) are unaffected, and structurally so: the merge
branch's ASCII bookkeeping is byte-identical to the fall-through path.

The damage is **outbound only**. `unicode_to_isabelle`, `unicode_to_ascii` and
`UnicodePosition.to_isabelle_position` have no caller anywhere in the tree, and the hover
and definition tools take `{file, line, symbol}` with no column at all. An earlier draft
said the inbound direction was the worse of the two; there is no inbound direction in
use.

### 1b. A second divergence class — and our rendering is wrong against Isabelle

`pretty_unicode`'s fold pass is `re.sub('\u21e9.|\u21e7.|\u2759.', ...)`. Two markers in a row
**match**, are returned unchanged, and the scan resumes past **both**, so the second
marker never folds with what follows: `\\<^sub>\\<^sub>1` renders `\u21e9\u21e91`. `FileIndex`'s
loop, on a failed merge, advances by **one** symbol and retries. The two therefore
disagree on any run of adjacent markers, and the regex's answer depends on the run's
parity, which is an artefact of non-overlapping matching rather than a rule.

**Isabelle renders it the other way, and we are the ones who are wrong.** Two independent
renderers in the distribution implement "the latest control wins, and the one it
displaced is emitted literally":

```scala
// src/Tools/jEdit/src/syntax_style.scala:133
if (control_style(sym).isDefined) control_sym = sym      // displaced control is never hidden

// src/Pure/General/html.scala:239
if (is_control(sym)) { output_symbol(ctrl); ctrl = sym } // displaced control is emitted
```

So Isabelle gives `\u21e9` + `\u2081` — two cells — where we give three. This is zero-instance
(a tree-wide search for two adjacent markers over every `.thy` and `.ML` returns 0
files), and it predates both commits under review. It matters here because it decides
the shape of the fix: a remedy that preserves our current behaviour hard-codes a
divergence from the prover, and one that removes the duplication by rebuilding the fold
on Isabelle's own rule repairs it for free.

Two rules Isabelle applies that neither of our implementations models, recorded so they
are not mistaken for new: jEdit declines to style an operand carrying its own `font:`
declaration — which all 135 phi-System private-use symbols do — and declines
non-`is_controllable` operands. Our fold coincides only because `SUBSUP_TRANS_TABLE`'s
alphabet happens to avoid both cases.

**The duplication has drifted three times, not once.** Before `8b7325e`,
`pretty_unicode`'s loose `\\<[^>]+>` disagreed with `symbol_explode` on malformed
escapes — `\\<alpha \\<beta>` rendered to 15 characters where `FileIndex` counted 9.
That commit closed the gap **incidentally**, from `FileIndex`'s point of view by luck.
So: one divergence opened by `eab47d6`, one closed by accident, one latent throughout.

## 2. The root cause, which is not the private-use rule

"What does this symbol render as under `pretty_unicode`" is implemented **twice**:

- `unicode.py:pretty_unicode` — two regex passes over the whole string.
- `position.py:FileIndex.__init__` — a symbol-by-symbol loop that reimplements both the
  table lookup *and* the sub/superscript fold (`position.py:116-129`).

D44 was added to the first and not the second. Any future change to rendering will
break the same way. A fix that only adds the private-use rule to `FileIndex` repairs
today's symptom and leaves the mechanism intact.

## 3. The invariant the fix must establish

**Not the obvious one.** A first draft of this plan proposed

```
FileIndex(t).sym_unicode_offsets[i] == len(pretty_unicode(t[:ascii_offset_of(i)]))
```

and that is **false on correct code**. `pretty_unicode` is not prefix-monotone:
truncating a source between a sub/superscript marker and its operand un-folds the pair,
so the rendered prefix is one character longer than the matching slice of the full
rendering. Measured:

```
t = 'x\\<^sub>i'      pretty_unicode(t)      = 'xᵢ'
                      pretty_unicode(t[:8])  = 'x⇩'   (2 chars)
                      FileIndex offset of 'i' = 1     -> the check reports FAIL
```

Folds are everywhere in Isabelle sources, so that instrument flags correct behaviour on
essentially every real file. It is recorded here because it is the natural thing to
write and it is wrong.

The invariant that is actually true:

> Render the **whole** text once. For each symbol `i`, `sym_unicode_offsets[i]` is the
> offset **within that single rendering** at which symbol `i`'s contribution begins.

Two practical notes, both learned by getting them wrong. Compare against `idx.source`,
not the raw file text: `symbol_explode` normalises `\\r\\n` to `\\n` and a CRLF file
otherwise fails spuriously. And check per line, not per file — the naive whole-file form
is O(n^2) and times out at 120 s on one tree, where the per-line form costs 0.01 s per
100 lines.

The strongest cheap form of the invariant is `sym_unicode_offsets[-1] ==
len(pretty_unicode(idx.source))`: well-posed everywhere, and sufficient to catch the
class of §1 and the class of §1b.

## 4. Four ways to fix it

### Option A — add the private-use rule to `FileIndex`

Smallest possible change: two call sites, `SYMBOLS.get(sym, sym)` becomes a lookup that
honours D44.

*For*: minimal, obviously correct for the reported symptom, no risk to `pretty_unicode`.
*Against*: leaves two implementations of one decision. The next rendering change breaks
it again. Does not address the fold logic, which is also duplicated.

### Option B — extract the per-symbol decision, keep the two loops

Export one function from `unicode.py`:

```python
def rendered_symbol(sym: str) -> str:
    """What `pretty_unicode` renders this one Isabelle symbol as, before folding."""
```

`pretty_unicode`'s `replace_symbol` and `FileIndex`'s two lookups both call it. The
sub/superscript fold stays duplicated, but is pinned by the §3 invariant test.

*For*: removes the duplication that actually broke, small and reviewable, no change to
`pretty_unicode`'s scanning or folding behaviour.
*Against*: the fold remains duplicated; only a test keeps it honest.

### Option C — one symbol-driven renderer, reporting its own alignment

Replace `pretty_unicode`'s two `re.sub` passes with a single pass over
`symbol_explode`'s output that renders each symbol and records where it lands:

```python
def pretty_unicode_indexed(src) -> tuple[str, list[int]]:
    """The rendering, and where each symbol of `src` begins in it."""
```

**Indexed by symbol, one entry per symbol** — `offsets[i]` is where the rendering of
`symbol_explode(src)[i]` begins in the returned string. Not by character offset: an
earlier draft's wording ("where each input offset lands") implied a per-character map,
and the prototype this is seeded from (`review-2026-08-18/remedy/sweep.py`) builds it per
symbol. `FileIndex` wants per symbol, so does §3's invariant. Say in the docstring
whether a trailing sentinel is appended; `position.py:149-150` appends two today.

`pretty_unicode(src)` becomes its first component, so there is exactly one
implementation. `FileIndex` reads the offsets and decides nothing: the table lookup, the
D44 rule and the entire fold loop leave `position.py`.

**Measured byte-identical to the current renderer on every real file.** A prototype was
diffed against `pretty_unicode` over **4,424 files** — 323 phi-System, 2,601
`Isabelle2025-2/src`, a 1,500-file AFP sample, `.thy` and `.ML`: **0 content
differences**. The only construction on which the two disagree is §1b's adjacent
markers, which occurs in no file in the tree, and there the symbol-driven form is the
one that agrees with Isabelle.

The escape pass is *provably* equivalent, not merely equal on a sample: all 624 table
keys match `unicode.py`'s escape pattern (§0), every match is exactly one
`symbol_explode` token, and every `\\<`-initial token that is not a match (`\\<`, `\\<>`,
`\\<^>`, `\\<alph`) is not a table key, so both leave it alone.

*For*: divergence stops being something a test must catch and becomes something that
cannot be expressed. §1b dissolves, and dissolves in Isabelle's favour. Any future
rendering rule reaches `FileIndex` for free.

*Against*, and both are real:

- **Cost.** Symbol-driven rendering is 21x slower than the regex on symbol-free ASCII
  and 10x on a whole file. `pretty_unicode` runs per hover message, per error string and
  per goal in the AoA loop, so this is not academic. A one-line fast-path guard for text
  containing no `\\<` and no marker brings ASCII back to 1.6x; the whole-file case stays
  at 10x (0.8 ms to 8.6 ms), which lands only on `.unicode.thy` generation — a few
  hundred files, once — and on `FileIndex` construction, which already pays for
  `symbol_explode`.
- **Line endings.** `symbol_explode` normalises `\\r\\n` and `\\r` to `\\n`; the regex
  renderer does not. Building on `symbol_explode` therefore changes line endings, and
  that must be **decided**, not inherited. Note it is already a live inconsistency:
  `FileIndex.source` is CR-folded while the `.unicode.thy` mirror is not, so deciding it
  makes the two agree for the first time. Zero CRLF files in the 4,424 measured.

### Option D — instrument the existing regex, and keep it

A cheaper variant: keep both `re.sub` passes and have their callbacks record where each
input offset lands, using `match.start()` and `match.end()`. Prototyped, about 25 lines,
output byte-identical to `pretty_unicode` by construction, and it removes the
duplication just as completely.

Rejected because it removes the duplication while **preserving §1b's divergence from the
prover**. It is numbered separately rather than called a variant of C because the two
reach opposite conclusions, and a name one word away from the chosen option is a trap
for whoever reads this next. It would leave two pieces of code agreeing precisely on a rendering that
Isabelle does not produce. If the point of unifying is to have one right answer rather
than two consistent ones, this is the wrong half to keep.

## 5. Recommendation

**Option C.**

Two drafts got here by different wrong roads, and both are worth recording because both
are the natural thing to reach for again.

The first rejected C outright, on the assumption that reporting offsets required
replacing the regex passes with a symbol-driven loop whose equivalence could not be
inspected. That framed the choice as "structural safety, bought with a risky rewrite of
the most widely called function in this module". The equivalence turned out to be
measurable rather than inspectable — 4,424 files, 0 content differences — so the risk
was priced from ignorance.

The second reached for Option D, which is genuinely zero-risk, and would have frozen a
rendering the prover does not produce.

What decides it is the history in §1b: this duplication has drifted three times and none
of the three was caught by a test. One was found by a review, one was closed by
accident, and one is still latent. Option B leaves the mechanism in place and appoints a
test as its guard; the evidence is that a test has never been what guards it. Option A
repairs the symptom only.

Option B remains the fallback if §6 cannot be satisfied — but then
§6 must be repaired as it stands, its proposed mutant replaced (it is inert, see §6.4),
and §1b either fixed separately or recorded as an accepted divergence from Isabelle with
an argument for why it stays at zero instances.

## 6. What must be true before this is called done

1. **One implementation.** `pretty_unicode(src)` is defined as
   `pretty_unicode_indexed(src)[0]`, and `position.py` no longer references `SYMBOLS`,
   `SUBSUP_TRANS_TABLE`, or any fold condition. The §3 invariant then holds by
   construction rather than by test — which is what makes the vacuity problem below
   shrink instead of needing to be defended against.

2. **Equivalence is measured, and the measurement is committed.** The 4,424-file diff
   against the current renderer is a test in the tree, not a number in this document. It
   costs about three minutes and it is the only thing that turns "equivalent rewrite"
   into a checked claim.

3. **Two behaviour changes are stated as changes, not discovered later.**
   - `\\<^sub>\\<^sub>1` starts rendering `\u21e9\u2081` instead of `\u21e9\u21e91`. That is what Isabelle
     does (§1b); test it, and record that it is zero-instance in 4,424 files so no
     stored artefact moves.
   - Line endings: decide explicitly whether the renderer inherits `symbol_explode`'s
     CR folding. Whichever way, `FileIndex.source` and the `.unicode.thy` mirror must
     end up agreeing, which they do not today.

4. **Mutants that actually exercise the new test.** `self_check()` currently hardcodes
   its target as `unicode.py` and needs a per-mutant file field, because the mutants
   that matter live in `position.py`:
   - `FileIndex` restored to computing its own offsets. **If this survives, the fix has
     not removed the duplication** and nothing else in the suite will say so.
   - the fold pass deleted from the renderer, and the D44 rule deleted from it.

   Note the mutant an earlier draft proposed — deleting D44 from the shared rendering
   function — is **inert against the invariant**: a mutation inside shared code is
   structurally invisible to a test that compares two consumers of it. Measured: with
   D44 deleted, `FileIndex` and the renderer still agree, at 35,187 where the truth is
   35,857. That mutant is killed by the pre-existing direct private-use check, and credit
   belongs there.

5. **Three routes to vacuity closed.** This file has already shipped vacuous sweeps once.
   - *No data passes.* `check_all` records `EMPTY` and `main()` still returns 0, so on a
     machine with no component registered every private-use check is skipped and the run
     is green. Make it fatal for the classes this fix is about.
   - *All-ASCII input.* `FileIndex` on symbol-free text yields 0 offenders under every
     implementation including the identity. Assert **positive counts**: the corpus must
     have contained at least one private-use escape, N folds, and N symbols whose
     rendering differs from themselves. Fail if any count is zero. This is the cheapest
     anti-vacuity device available and no draft has had it.
   - *Machine dependence.* Seed `SYMBOLS_CACHE` from a three-line temporary symbols file
     through the existing `_load_symbols` — one ordinary symbol, `\\<^sub>`, one synthetic
     private-use symbol at U+E000 — so every rendering class is exercised unconditionally
     and the real-corpus sweep becomes corroboration rather than the only source of the
     case. About eight lines, verified to work.

6. **A fast-path guard**, with the benchmark recorded beside it, so the next reader does
   not rediscover the 21x on symbol-free text.

7. **Hand-written cases for every rendering class**, since no corpus supplies them all:
   private-use symbol, private-use symbol as a fold operand, ordinary component symbol,
   foldable subscript in escape and raw form, unfoldable subscript, bold fold, bold with
   no fold available, malformed escape, adjacent fold markers of length two and three,
   and CRLF.

8. **Scope correction to item 1.** Item 1 asks that `position.py` stop deciding what a
   symbol renders as. Read as "the only place in the tree", it is false for one further
   reason: `contrib/Isabelle_RPC/build/lib/` holds a complete **pre-D44** copy of this
   package (`unicode.py:195` is still the bare lookup). It is not on `sys.path` today, but
   it is what a build artefact ships. Delete it.

   An earlier draft added a second item here, that
   `Semantic_Embedding/premise_selection.py:173` shadows the imported `pretty_unicode`.
   It does not: `:45` imports it as `_pretty_unicode`, and `:174` calls that as the
   wrapper's first line. A deliberate alias-and-wrap. Nothing to do.

9. **`hover.py`'s two call sites re-verified** against a real phi-System file: the column
   handed to the model addresses the symbol it names.

10. **The interior-offset convention documented on the function**, not only here: when a
    symbol renders to a different length, offsets strictly inside it map to its start.
    `FileIndex` only queries symbol boundaries, so it never meets the convention, but an
    unwary caller could.

## 6b. Hygiene on the lines this fix touches

Four defects sit on or beside the code being rewritten. They are listed here rather than
in §7 because doing them separately means editing the same lines twice, and because the
first exists only to prop up an API this fix is already changing.

**Two module globals cache one thing.** `get_SYMBOLS_AND_REVERSED()` returns a 4-tuple,
and `get_SYMBOL_FILES()` reads from a *second* global, `SYMBOL_FILES_CACHE`, whose
docstring explains that the tuple could not grow because "callers unpack that by arity".
Two callers do: `Semantic_Embedding/site/prototype/tokenize_prototype.py:13` and
`test_unicode.py:78`. An earlier draft of this section claimed there was one, and that it
was the prototype D43 has superseded — that argument does not survive the second caller,
which is inside this package and is the suite §8 step 5 extends.

The defect is real anyway: one load produces one state, cached in two places that nothing
keeps in step. The remedy that breaks no caller is to cache **one** record internally —
symbols, reverse, translation table, letter symbols, files — and let
`get_SYMBOLS_AND_REVERSED()` project the existing 4-tuple out of it. Positional access
and arity-unpacking keep working, `get_SYMBOL_FILES()` reads the same record as everyone
else, and the parallel global goes.

**A guard that cannot fail, reading as though it defends something.** In
`pretty_unicode`'s `replace_symbol`, `len(char) == 1 and is_private_use(char)`. Every
value in the table comes from `chr()`, so the length is always 1 — measured, the set of
distinct value lengths is exactly `{1}`. Drop the guard, and if the property is worth
relying on, assert it once where the table is built rather than re-testing it per
substitution.

**Mutable default arguments in `_load_symbols`.** `def _load_symbols(path, symbols={},
reverse_symbols={}, groups={})`. Measured: two successive calls without explicit
dictionaries return the *same* object, holding both files' symbols — 489 entries after
loading two files of 50 and 439. Latent only because the one in-tree caller always
passes explicit dictionaries.

**The fallback consults the environment last.** When `ISABELLE_SYMBOLS` is not in the
environment, `resolve_isabelle_path_list` shells out to whichever `isabelle` is first on
`PATH` before anything looks at `ISABELLE_HOME`, so an explicitly set `ISABELLE_HOME` is
ignored. Harmless today — both distributions' tables are identical — and wrong in
ordering. The environment's explicit value should win over a subprocess's opinion.

## 7. The other findings, and what each needs

Reported by the same review; none is this urgent, and each is separable.

**`get_SYMBOL_FILES()` reports requested paths, not files read.** The list includes a
file that does not exist on this machine, and paths are not content: two machines can
report identical provenance for different tables. Its docstring tells consumers to
"refuse a mismatch", which they cannot do with this record. The fix is a **content
digest** beside the path list. This is load-bearing for the search site's D45, which puts an asset digest in the index
namespace name, so it should be settled with that decision rather than patched here. Its
other former motivation, the stale mirrors, has been dismissed — the digest is wanted for
D45 regardless.

**`.unicode.thy` mirror staleness — dismissed by the user, 2026-08-18, do not re-raise.**
The measurement stands: 21 phi-System mirrors differ from what `pretty_unicode` produces
today, and 4 of them (`Phi_BI/{Algebras,Arrow_st,Len_Intvl,Map_of_Tree}`) will never
self-correct, because `theory_structure.py:25-36` regenerates only when the `.thy` is
newer and the symbol table is not part of that test. It is recorded here so that the
next review does not report it as new. It is not to be fixed.

**EXPERIENCE document text moves with nothing to invalidate.** `document_text.py:73-74`
applies `pretty_unicode` to stored ASCII `goal_patterns` at read time, so the embedded
text can change while the stored bytes do not. 180 records, 0 affected today. Fix
belongs with whatever handles asset versioning; record it, do not chase it now.

**`【 】` is no longer symbol-free.** `Tools/inner_syntax_error.ML:78` uses U+3010/U+3011
as an in-band marker, and `\<lblbrace>`/`\<rblbrace>` now map to them. Latent: the ML
side works on ASCII before Python sees it. Needs a different marker eventually, or a
documented reason it cannot collide.

**An explicitly set `ISABELLE_HOME` is no longer honoured** when `ISABELLE_SYMBOLS` is
absent from the environment, because the fallback shells out to whatever `isabelle` is
first on `PATH`. Harmless today (both distributions' tables are identical) but wrong.
Fix: consult `ISABELLE_HOME` before shelling out.

**Latent parsing gaps in `_load_symbols`**, all zero-instance on this machine: a symbol
redefined across files leaves a stale `REVERSE_SYMBOLS` entry; only the first `group:`
field of a line is read where Isabelle collects all of them (48 lines in the
distribution carry two); a non-permissive missing file is skipped silently where
Isabelle errors; and the function's mutable default arguments would accumulate across
calls. Fix together, with a test per item.

**Three other symbol tables in the tree stayed at 439** while this one moved to 624:
`Isabelle-MCP/.../isabelle_symbols.py` (whose docstring claims it reads
`ISABELLE_SYMBOLS` and does not), `AutoCorrode/ir/repl.py`, and `tokens.py`'s hardcoded
letter list. Not caused by these commits; now divergent because of them.


## 8. Build order

Each step is finished when its acceptance holds, not before. Steps 1 and 2 are the fix;
3 through 7 are what stop it rotting.

**1. `pretty_unicode_indexed` in `unicode.py`.** One pass over `symbol_explode`'s output,
rendering each symbol and recording where it lands. Seed it from
`review-2026-08-18/remedy/sweep.py`, whose `rendered_symbol` is the per-symbol decision
already written and already diffed. Define `pretty_unicode(src)` as its first component
so that only one implementation exists. Add the fast-path guard for text containing no
`\\<` and no marker, and put the benchmark next to it in a comment.

Clear §6b's first two defects in the same edit, since both sit on these lines: cache one
record so the parallel `SYMBOL_FILES_CACHE` global can go, and drop the `len(char) == 1`
guard.

**Dropping that guard breaks an existing mutant.** `test_unicode.py`'s MUTANTS list
anchors "the private-use rule is deleted" on the exact source line
`if char is None or (len(char) == 1 and is_private_use(char)):`. Once the guard goes the
anchor no longer matches, `self_check` prints "mutation site not found — this self-check
is stale" and counts that mutant as **survived**. Re-anchor it in the same commit.

*Accepted when* the 4,424-file byte-identity diff against the pre-change renderer passes
with 0 content differences, and the benchmark is recorded. Keep the pre-change renderer
around for the duration of this step — you cannot diff against something you have
already deleted.

**2. The two behaviour changes, decided and written down.** `\\<^sub>\\<^sub>1` starts
rendering `\u21e9\u2081`, which is what Isabelle does (§1b). Line endings: decide whether the
renderer inherits `symbol_explode`'s CR folding, and make `FileIndex.source` and the
`.unicode.thy` mirror agree either way — they do not today.

*Accepted when* both are stated in the commit message and covered by a hand-written case.

**3. Strip `FileIndex`.** It consumes the offsets and implements nothing.

*Accepted when* `position.py` references neither `SYMBOLS` nor `SUBSUP_TRANS_TABLE` nor
any fold condition, and `grep` says so.

**4. The invariant test.** §3's form, per line, against `idx.source`. Carry **all three**
of §6.5's anti-vacuity devices, not two: the positive-count assertions, the seeded
synthetic table, and making an empty sweep fatal — `check_all` records `EMPTY` and
`main()` still returns 0 today, which is how a machine with no component registered goes
green. Add §6.7's eleven hand-written rendering classes here; no corpus supplies them
all. Document §6.10's interior-offset convention on the function while you are in it.

*Accepted when* it fails against the code as it stood before step 1 — check this by
running it against the parent commit, not by reasoning about it.

**5. Extend `self_check`.** Give `MUTANTS` a per-file field, then add the mutants of
§6.4. The one that decides whether this work succeeded is `FileIndex` restored to
computing its own offsets.

*Accepted when* every mutant is killed and the suite still passes unmutated.

**6. Scope cleanup.** Delete `contrib/Isabelle_RPC/build/lib/`, which holds a complete
pre-D44 copy of this package. Clear §6b's remaining two: the mutable defaults in
`_load_symbols`, and the fallback's consultation order.

*Accepted when* no copy of this package survives outside the source tree, and
`_load_symbols` and the fallback each have a test.

**7. Re-verify the consumer.** `hover.py`'s two call sites against a real phi-System
file: the column handed to the model addresses the symbol it names.

*Accepted when* a location string produced end to end points at the right token.

### Not in this order, and why

The `get_SYMBOL_FILES` provenance record wants a content digest rather than a path list
(§7). It is deliberately not here: the same digest is what the search site's D45 needs
for its namespace name, and settling it twice would produce two answers. `.unicode.thy`
mirror staleness is dismissed and is not to be fixed. The remaining §7 items are latent,
zero-instance, and separable; do them together, with a test each, whenever convenient.
