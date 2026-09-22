# Fixing the FileIndex / pretty_unicode divergence

Status: implemented in `3360162` and revised under the adversarial review of 2026-09-22
(the paragraphs below). Written 2026-08-18
after a review of commits `eab47d6` and `8b7325e` found a live regression; the shape
(Option D, §5: keep the regex substitution and record positions while it runs) was
chosen by the author that day ("我强烈建议走法一，原始的方案", "很好。请改方案"). On
2026-09-21 the author put this plan first among the items queued after the guard cache
work ("是的，我们先看这个"), kept the shape ("好"), and asked for one read-only light
re-check by an Opus agent before any code ("要的"). The citations below were re-checked
against the tree on 2026-09-21: the code has not changed since `f9e139c`, and the defect
is still live (whole-file check on `Resource_Template.thy`: `FileIndex` ends at 35,187
where the rendering has 35,857 characters; 57 of its 835 lines are off). For the
record: on 2026-09-14 the drafter described the shape to the author as a symbol-by-symbol
renderer, which is Option C, rejected in §4; that was a departure from the ruling above,
reported to the author on 2026-09-21; the ruling stands.

2026-09-22: the light re-check (`ai-artifacts/UNICODE_PLAN_RECHECK_2026-09-21.md`) came
back ISSUES. The author ruled the indexed function's contract as §4 D now states it — one
private core, two views, the indexed view taking the symbol sequence ("好") — and ruled
that performance at this scale is not a criterion ("如果你是在担心性能的话这点问题根本不值得
担心！请重点考虑可维护性与实现的优雅性！"); everything that is not a design change, and
everything about acceptance, is the drafter's ("只有对设计的改变需要跟我讨论", "与验收相关的
可以你自己决定"). On that authority the drafter withdrew the fallback-order remedy (§6b,
§7, §8 step 6) and the `build/lib` deletion (§6.7, §8 step 6), and applied the re-check's
citation and wording corrections.

**IMPLEMENTED 2026-09-22** (the commit carrying this paragraph), §8 steps 1–7, with these
acceptances observed: `pretty_unicode` byte-identical over the 4,506 files of §0 (per-file
digests before and after); `pretty_unicode(''.join(symbols)) ==
pretty_unicode_indexed(symbols)[0]`, the whole-file sentinel and `FileIndex`'s agreement
with the indexed view on all 4,506; `position.py` references none of `SYMBOLS`,
`SUBSUP_TRANS_TABLE` or a fold condition; the suite's seeded cases cover the twelve
rendering classes of §6.6 and its phi-system sweep passes on 68,148 lines with its three
§6.5 counts — private-use escapes, folds, symbols rendered differently — all positive;
run against the parent commit's `FileIndex`, that suite fails (three seeded cases, 107 of
the 160 files and 7,464 of the 68,148 lines); `--self-check` kills all nine mutants,
including `FileIndex` restored to its own computation and to the bare table lookup, every
kill coming from the seeded cases (the sweep runs outside the mutant copies); on
`Resource_Template.thy:156` both hover routes now place `Itself`, `Rel` and `Normal` at
columns 21 (and 40), 66 and 71, where the rendered line has them.

**REVIEWED 2026-09-22** (a two-round adversarial review, 60 agents; the record is
`ai-artifacts/UNICODE_REVIEW_2026-09-22.md`): the judge ruled MET_ON_CONDITION — the fix
correct and in the ruled shape, its net short in five places: §6 item 2's corpus arm
compared lengths where the item asks for the renderings; §6.5's device against an empty
sweep had not shipped, so a machine without phi-system beside the repository went green
without sweeping; §6 item 9's third clause was false as worded; and the six coordinate
conversions and `FileIndex`'s ASCII bookkeeping had no test. The author granted both
proposals put to him ("赞同你的建议", 2026-09-22): the recording keeps only the matches a
replacement rewrote, so the convention of §4 D has two cases instead of three; and §1b is
fixed in a follow-up commit — the fold pattern becomes a marker followed by a non-marker,
Isabelle's own rule, with no rendering in 14,500 sources and 9,913 checked-in mirrors
changing. The judge's conditions and 30 of the 31 items he assigned to the drafter are
applied in the four commits that follow `3360162` (`615cb01` the conditions and the
shape; `601df27` the derived restore table; `6c1ee40` `symbol_explode` moved beside the
escape pattern; `2ad1f09` §1b); the 31st, C22, is deferred to §7; the 13 he dismissed are
not to be re-raised. The review's own record says which is which.

Everything below this paragraph, from §0 on, describes the tree as it stood before the
fix (`f9e139c`): its line numbers and names — `FileIndex.__init__` at `position.py:82-154`,
the bare lookups, `SYMBOLS_CACHE` — are the ones `3360162` changed. Read it as the record
of what was wrong and why the fix has this shape; for the tree as it stands, read the code.

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
Isabelle_RPC_Host/position.py    symbol_explode; FileIndex.__init__ (:82-154, the
                                 duplicate rendering logic, with the two bare lookups
                                 at :110 and :120, the fold branch at :115-138 and its
                                 fall-through at :140-146); the six conversions at :178+
test_unicode.py                  the suite, and `--self-check`, whose MUTANTS list
                                 currently hardcodes unicode.py as its target
../Semantic_Embedding/Isabelle_Semantic_Embedding/hover.py
                                 the live consumer (:231-232 and :321), see §1
```

Line numbers in this document were re-checked on 2026-09-21 (the Semantic_Embedding
package had moved into its `Isabelle_Semantic_Embedding/` directory since 2026-08-18).

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
on 2026-09-22 `contrib/phi-system` 486 raw, 405 after; `contrib/Isabelle2025-2/src`
3,768 raw, 2,601 after; plus the first 1,500 of `contrib/afp-2026-05-13/thys` **in
`os.walk` order**, which is filesystem-dependent and therefore not reproducible
elsewhere. 405 + 2,601 + 1,500 = 4,506 (on 2026-08-18 the counts were 352/323 and
3,024/2,601, total 4,424). If you cannot reproduce the AFP slice, say so and quote your
own number rather than this one; the diff's value is that it is 0, not that it is over
a particular number of files.

**The review evidence** is in `review-2026-08-18/`, with a README saying what each
script established. `diagnosis/ref.py` is the instrument behind the §3 invariant (it
replays the two regex passes with offset tracking); `remedy/sweep.py` is the
symbol-driven prototype of Option C, which §4 rejects — evidence, not the shape to build.

## 1. The defect

`Isabelle_RPC_Host/position.py`'s `FileIndex` computes, for every Isabelle symbol in a
source file, the column it occupies **in the Unicode rendering of that file**. The
Unicode rendering is produced by `pretty_unicode`. The two must agree exactly, or a
position computed from one addresses the wrong character in the other.

They no longer agree. `FileIndex.__init__` (`position.py:82-154`) decides what a
symbol renders as with a bare `SYMBOLS.get(sym, sym)` (`:110`, `:120`). `pretty_unicode` now applies
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

Six columns per preceding private-use symbol on this line: the drift is the escape's
length minus one, and every private-use escape on the line is a seven-character name
such as `\<proc>`.

**Live consumer.** `Semantic_Embedding/Isabelle_Semantic_Embedding/hover.py:321`
(`idx.isabelle_to_unicode`) and `:231-232` (`mk_definition_tool` → `to_unicode_position`),
both reached from the deformalization loop at `semantic_interpretation.py:1844-1845`
with `unicode=True` (paths and lines as of 2026-09-21).
The interpreting model is handed `<file>.unicode.thy:line:column`, where the file is
rendered by `pretty_unicode` and the column by `FileIndex`.

**Blast radius.** On 2026-08-18, 100 of 55,772 `.thy` sources carried a private-use
escape: 94 in phi-System (re-measured 2026-09-22: 107 of phi-System's 160 `.thy`
sources, the `.unicode.thy` mirrors excluded), and — worth noting, because it shows the
leak is not confined to
phi-System's own tree — and 2 in the `src/Doc` of each of the three distribution trees
present on 2026-08-18 (`Isabelle2025-2`, `Isabelle2024`, `Isabelle2024_bak`; the last is
no longer present under that name), affected only
because phi-System's `symbols-words` is registered on this machine. The ASCII-coordinate
procedures (`position.py:537-556`) are unaffected, and structurally so: the merge
branch's ASCII bookkeeping is byte-identical to the fall-through path.

The damage is **outbound only**. `unicode_to_isabelle`, `unicode_to_ascii` and
`UnicodePosition.to_isabelle_position` have no caller anywhere in the tree, and the hover
and definition tools take `{file, line, symbol}` with no column at all. An earlier draft
said the inbound direction was the worse of the two; there is no inbound direction in
use.

### 1b. A second divergence class, fixed on 2026-09-22

`pretty_unicode`'s fold pass is `re.sub('\u21e9.|\u21e7.|\u2759.', ...)`. The `.` is *any* character,
and a second marker is a character, so two markers in a row match as a pair, fail to
appear in the fold table, are returned unchanged — and `re.sub` resumes **past both**, so
the second marker never folds with what follows. Traced:

```
x\\<^sub>1            pass 1 -> 'x\u21e91'    regex matches ['\u21e91']         -> 'x\u2081'
x\\<^sub>\\<^sub>1    pass 1 -> 'x\u21e9\u21e91'   regex matches ['\u21e9\u21e9']         -> 'x\u21e9\u21e91'
x\\<^sub>\\<^sub>\\<^sub>1     -> 'x\u21e9\u21e9\u21e91'  matches ['\u21e9\u21e9', '\u21e91'] -> 'x\u21e9\u21e9\u2081'
```

One marker folds, two do not, three fold the last — a parity artefact of non-overlapping
matching rather than a rule. `FileIndex`, walking symbol by symbol and advancing by one
on a failed merge, retries the second marker and gets a different answer. That is the
second way the two implementations disagree, and it predates both commits under review.

**Isabelle renders it the other way.** Two renderers in the distribution implement "the
latest control wins, and the one it displaced is emitted literally":

```scala
// src/Tools/jEdit/src/syntax_style.scala:133
if (control_style(sym).isDefined) control_sym = sym      // displaced control is never hidden
// src/Pure/General/html.scala:239
if (is_control(sym)) { output_symbol(ctrl); ctrl = sym } // displaced control is emitted
```

So Isabelle gives `\u21e9` + `\u2081` where we give `\u21e9\u21e91`.

**Fixed on 2026-09-22**, in the commit after the review, on the review's proposal and the
author's grant ("赞同你的建议"): the fold pattern is a marker followed by a non-marker (and
never a line break), so of two adjacent markers the later one applies and the displaced
one is emitted literally, as Isabelle renders them — `x\<^sub>\<^sub>1` renders `x⇩₁`.
Measured before the change: no rendering in 14,500 sources of this tree and 9,913
checked-in `.unicode.thy` mirrors contains two adjacent markers, so nothing observable
moved, and §6 item 3's byte-identity holds with that one stated exception. The fix is a
two-character change inside Option D; the 2026-08-18 belief that it needed Option C was
what kept it out. **Until then it was recorded, not fixed**, for three reasons that were
sound at the time, in order of weight. It is **lossless**: measured, `pretty_unicode` then
`ascii_of_unicode` returns `x\\<^sub>\\<^sub>1` exactly, and the rendering is a fixed
point — nothing is destroyed, one fold is merely not applied. It occurs **nowhere**: a
tree-wide search for two adjacent markers over every `.thy` and `.ML` returns 0 files.
And it is a different kind of thing from §1: §1 is *two of our implementations
disagreeing with each other*, which misdirects the positions in every phi-System theory
§1 counts, where
this is *our one implementation differing from the prover* on a construction that never
arises. An earlier draft used this to reject the remedy §5 now recommends. That was
wrong, and §5 says why.

Two rules Isabelle applies that neither of our implementations models, recorded so they
are not mistaken for new: jEdit declines to style an operand carrying its own `font:`
declaration — which all 135 phi-System private-use symbols do — and declines
non-`is_controllable` operands. Our fold coincides only because `SUBSUP_TRANS_TABLE`'s
alphabet happens to avoid both cases.

## 2. The root cause, which is not the private-use rule

"What does this symbol render as under `pretty_unicode`" is implemented **twice**:

- `unicode.py:pretty_unicode` — two regex passes over the whole string.
- `position.py:FileIndex.__init__` — a symbol-by-symbol loop that reimplements both the
  table lookup *and* the sub/superscript fold (`position.py:115-138`).

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

### Option C — rewrite the renderer to walk symbol by symbol

Replace the two `re.sub` passes with one pass over `symbol_explode`'s output, rendering
each symbol and recording where it lands. Considered at length and rejected; kept here
because it is the shape everyone reaches for and its costs are not obvious.

Two behaviour changes come with it, both consequences of walking rather than matching:
§1b's fold is repaired (`\\<^sub>\\<^sub>1` starts rendering `\u21e9\u2081`), and the renderer
inherits `symbol_explode`'s normalisation of `\r\n` to `\n`.

*Against, and this is what decides it*:

- **It needs an equivalence argument, where Option D needs none.** Measured 0 content
  differences over 4,424 files, which is good evidence and still only evidence.
- **Cost.** Walking every character in Python where a regex engine walked them in C:
  measured 18.7x on symbol-free ASCII (21x in an earlier run, the figure the review
  README quotes), and — the case that matters — **18.6x on realistic
  goal text**, 220 characters with one `\\<And>` in it. `pretty_unicode` runs per hover
  message, per error string and per goal in the AoA loop.
- **A fast-path guard does not rescue it.** Skipping the slow path for text with no `\\<`
  and no marker sounds sufficient and is not: the strings this function sees in the agent
  loop contain escapes *by construction* — that is why they are being converted. Measured
  on the realistic goal above, the guard changes nothing at all (76.7 us either way).
  Over 40,000 real source lines it turns a 7x average regression into 3.5x. A performance
  special case in the middle of a correctness fix, buying half of a problem it created.
- **It makes `FileIndex` slower than the code it replaces**, because the source is
  exploded twice — once by the renderer, once by `FileIndex` for its ASCII offsets.
  Measured on a 44k-character file: 11.1 ms today, 14.2 ms at best, 18.2 ms as worded.

A fourth shape was measured during review and is recorded for completeness: find the
interesting positions with a regex and walk only those, passing the plain text between
them through untouched. It is faster than the code we have (`FileIndex` construction 5.3
ms against 11.1 ms) and needs no guard, because symbol-free text is simply the case with
no interesting positions. It costs about 45 lines against Option D's 25, most of it a
marker/operand state machine, and it still needs the equivalence argument. Worth
reopening only if the renderer ever has to change behaviour for another reason.

### Option D — record positions while the existing substitution runs

**The recommendation.** `re.sub` calls its replacement function once per match with a
match object, which carries `start()` and `end()` — where the match was in the input —
and the function's return value has a known length. So each pass can record, per match
it rewrote, "input from here to here became output of this length at this position", and
from those records compute where every input offset lands in the output.

The substitution logic is untouched. The replacement function returns exactly what it
returned before; one line is added beside it that writes down what happened.

One private core does the rendering; the two public functions are views of it:

```python
def _render(text: str) -> tuple[str, list]:
    """The two `re.sub` passes exactly as today. Each replacement callback also
    records (input start, input end, output length) for each match it rewrote."""

def pretty_unicode(src: str) -> str:
    return _render(src)[0]            # byte-identical to today, CR handling included

def pretty_unicode_indexed(symbols: list[str]) -> tuple[str, list[int]]:
    """The rendering of ''.join(symbols), and where each symbol begins in it.
    `symbols` is `symbol_explode`'s output. `offsets` has len(symbols) + 1
    entries, the last equal to len(rendering)."""
```

`FileIndex` already holds the symbol sequence — it explodes the source for its ASCII
offsets and line starts — so it hands that sequence over and reads the offsets back,
deciding nothing: the table lookup, the D44 rule and the whole fold loop leave
`position.py`.

**Indexed by symbol, one entry per symbol** — `offsets[i]` is where the rendering of
`symbols[i]` begins in the returned string. Taking the symbol sequence rather than a
string is what makes the line-ending pitfall impossible instead of remembered:
`symbol_explode` folds `\r\n` to `\n`, so the indexed view can only ever render the text
`FileIndex` holds, and there is no second string for the two to disagree about.
`pretty_unicode` keeps taking the raw string, so its CR handling does not move (§6.3).

The 2026-08-18 draft had the indexed function take a string, explode it itself, and
serve as the definition of `pretty_unicode`. The light re-check of 2026-09-21 measured
what that costs — the per-character `symbol_explode` walk on every `pretty_unicode`
call — and the author ruled on 2026-09-22 that cost at this scale is not a criterion and
that maintainability and elegance decide. The shape above was chosen on those grounds:
one core, the contract stated at the symbol level, the pitfall removed by construction.

Prototyped on 2026-08-18 and again by the re-check on 2026-09-21 — about 60 lines with
the offset composition, not the 25 first estimated. Verified output byte-identical to
`pretty_unicode` on every case tried, and **necessarily so** — it is the same code path
with a recording step beside it, not a reimplementation:

```
'x\\<^sub>i'        symbol offsets [0, 1, 1]
'a\\<proc>b'        symbol offsets [0, 1, 8]
'\\<^bold>x y'      symbol offsets [0, 0, 1, 2]
'\\< \\<alpha>'     symbol offsets [0, 2, 3]
```

The second line is §1's defect: the private-use symbol keeps its seven characters, so `b`
is at offset 8 where `FileIndex` says 2. The mechanism is right about it without being
told D44 exists, because it records what the substitution did rather than deciding again
what it should have done.

*For*: no behaviour change, so no equivalence argument and no corpus diff to keep
forever. No guard and no benchmark, because nothing about the scanning changes. The
duplication is removed as completely as by Option C.

*Against*: nothing, since 2026-09-22. Until then it preserved §1b's difference from
Isabelle, which §1b explained was acceptable — lossless, round-trips exactly, zero
instances — and §5 explains why an earlier draft was wrong to reject Option D over it;
in the end §1b's fix was a two-character change to the fold pattern inside Option D.

*The interior-offset convention*, internal to `pretty_unicode_indexed` (as ruled on
2026-09-22, replacing a three-case rule that told a rewritten match from an untouched one
by its length — sound only because the fold table happens to map two characters to one,
which nothing stated): only the matches a replacement rewrote are recorded; every offset
moves with the length changes of the rewritten matches before it; and an offset strictly
**inside** a rewritten match lands at that match's output start, the match being one
unit. Symbol boundaries do fall inside matches — a fold operand begins inside the fold
match (`x\<^sub>i`: the operand `i` lands on the folded character, giving `[0, 1, 1]`);
after a private-use symbol the fold regex matches the marker plus the escape's backslash
and leaves it as it is, which records nothing, so `\<^sub>\<proc>` keeps every symbol
where it is. The convention is what turns match records into per-symbol offsets; it
lives inside the function, and no caller meets it.

## 5. Recommendation

**Option D.**

Three drafts reached three different answers, and the wrong turns are worth recording
because each is the natural thing to reach for again.

The first rejected any change to `pretty_unicode` on the assumption that reporting
offsets required rewriting it, and priced a risk it had not measured.

The second chose Option D, then abandoned it on discovering §1b — our fold differs from
Isabelle's on adjacent markers — reasoning that unifying on a rendering the prover does
not produce keeps the wrong half.

The third chose Option C, and would have paid an 18x regression on the traffic this
function actually sees, plus a guard that measurement shows buys nothing on that traffic,
plus a `FileIndex` slower than the one it replaces, plus a permanent corpus diff in the
tree to stand in for an equivalence it cannot have structurally.

What settles it is that the second draft's objection compares two different magnitudes.
The defect being fixed is **two of our implementations disagreeing with each other**,
which sends the interpreting model to the wrong column in every one of those files. §1b
is **our
one implementation differing from the prover** on a construction that occurs in no file,
loses no information, and round-trips exactly. Trading a real fix that changes no
behaviour for the second is trading a measured regression for a difference nobody can
observe.

Option D also has a property none of the others do: **its equivalence is structural, not
measured.** Options B and C must argue that a reimplementation matches; D returns the
same bytes because it runs the same code. Every acceptance criterion below is lighter for
that reason.

Option C remains the fallback if implementation shows the recording step cannot be made
to work — and if it is ever taken, §1b's fold repair and the CR normalisation come with
it and must be stated, not discovered.

## 6. What must be true before this is called done

1. **One implementation.** `pretty_unicode` and `pretty_unicode_indexed` are both views
   of the one private core `_render` (§4 D); neither performs a substitution of its own;
   and `position.py` no longer references `SYMBOLS`, `SUBSUP_TRANS_TABLE`, or any fold
   condition. The §3 invariant then holds by construction rather than by test — which
   is what makes the vacuity problem below shrink instead of needing to be defended
   against.

2. **Equivalence is structural, and one line checks it.** Both public functions must be
   thin projections of `_render`, so there is one code path and no second renderer to
   keep in step. Assert `pretty_unicode(''.join(symbols)) ==
   pretty_unicode_indexed(symbols)[0]` once over the corpus and the hand cases — true by
   construction, run as the check that nobody has given one view a substitution of its
   own; do not commit a diff against a frozen copy of the old renderer, which would put a
   second implementation of the rendering decision in the test suite forever — the
   structure this fix exists to abolish.

3. **No behaviour change, and that is checkable.** `pretty_unicode`'s output must be
   byte-identical before and after, on the corpus and on §6.6's hand cases — with one
   exception stated and measured since 2026-09-22: two adjacent fold markers render as
   Isabelle does (§1b), a construction the corpus does not contain. The existing CR
   handling stays exactly as it is (`pretty_unicode` still takes the raw string; only
   the indexed view takes `symbol_explode`'s output); if it moves, the recording step
   has been written as a reimplementation and step 1 is not done.

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
   - *Machine dependence.* Serve a five-line temporary symbols file through the module's
     own loader (`_load_table([path])` into `_TABLE`, the suite's `seeded_table()`) — two
     ordinary symbols, the markers, one synthetic private-use symbol at U+E000 — so every
     rendering class is exercised unconditionally, and sweep a corpus written in that
     alphabet under it, so the positive counts and the empty-sweep rule hold on every
     machine; the real-corpus sweep becomes corroboration rather than the only source of
     the case.

6. **Hand-written cases for every rendering class**, since no corpus supplies them all:
   private-use symbol, private-use symbol as a fold operand, ordinary component symbol,
   foldable subscript in escape and raw form, unfoldable subscript, bold fold, bold with
   no fold available, malformed escape, adjacent fold markers of length two and three,
   and CRLF.

7. **Scope correction to item 1.** Item 1 asks that `position.py` stop deciding what a
   symbol renders as. Read as "the only place in the tree", it is false in one harmless
   way: `contrib/Isabelle_RPC/build/lib/` and `dist/` hold setuptools build artefacts of
   this package, the `build/lib` copy pre-D44 (`unicode.py:195` is still the bare
   lookup). They are git-ignored, off `sys.path`, and regenerated by the next
   `python -m build`, so "no copy survives outside the source tree" is neither
   achievable nor testable and is not an acceptance condition (the drafter's decision of
   2026-09-22 under "与验收相关的可以你自己决定"; a 2026-08-18 draft said "delete it" and
   made that step 6's acceptance). Deleting them is local hygiene with no lasting
   effect; the only real exposure is someone putting `build/lib` on `sys.path`, which
   nothing does.

   An earlier draft added a second item here, that
   `Semantic_Embedding/premise_selection.py:173` shadows the imported `pretty_unicode`.
   It does not: `:45` imports it as `_pretty_unicode`, and `:174` calls that as the
   wrapper's first line. A deliberate alias-and-wrap. Nothing to do.

8. **`hover.py`'s two call sites re-verified** against a real phi-System file: the column
   handed to the model addresses the symbol it names.

9. **The interior-offset convention documented on the function**, not only here: the
    rule of §4 D (every offset moves with the rewritten matches before it; one inside a
    rewritten match lands at that match's output start), written where the records
    become offsets. It is internal to `pretty_unicode_indexed`, and the docstring says
    so, so nobody builds a second consumer of the raw records.

## 6b. Hygiene on the lines this fix touches

Three defects sit on or beside the code being rewritten (a fourth, listed on
2026-08-18, is withdrawn at the end of this section). They are listed here rather than
in §7 because doing them separately means editing the same lines twice, and because the
first exists only to prop up an API this fix is already changing.

**Two module globals cache one thing.** `get_SYMBOLS_AND_REVERSED()` returns a 4-tuple,
and `get_SYMBOL_FILES()` reads from a *second* global, `SYMBOL_FILES_CACHE`, whose
docstring explains that the tuple could not grow because "callers unpack that by arity".
Two callers do: the `symbols, reverse, _, _ = get_SYMBOLS_AND_REVERSED()` in
`test_unicode.py`'s `main()`, inside this package and in the suite §8 step 5 extends, and `contrib/isasearch-web/site/prototype/tokenize_prototype.py:13` (moved
there from Semantic_Embedding since 2026-08-18; `subtoken_rule.py:6` beside it indexes
the tuple positionally). One of them lives outside this package, which is one more
reason the tuple's shape must not change.

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

**The fallback's consultation order is right and stays — withdrawn.** The 2026-08-18
draft listed a fourth defect here ("the fallback consults the environment last … the
environment's explicit value should win over a subprocess's opinion") and, in §7 and §8
step 6, the remedy "consult `ISABELLE_HOME` before shelling out". That remedy would
reopen `eab47d6`: `$ISABELLE_HOME/etc/symbols` alone yields 439 entries where
`ISABELLE_SYMBOLS` yields 624, and §0's own recipe sets `ISABELLE_HOME` without
`ISABELLE_SYMBOLS`. The design review of 2026-08-18 objected to exactly this and the
text was never corrected; the light re-check of 2026-09-21 confirmed it by measurement,
and the drafter withdrew all three mentions on 2026-09-22 ("只有对设计的改变需要跟我讨论").
Today's order (`paths.py:95-116`, `unicode.py:74-90`) — environment `ISABELLE_SYMBOLS`,
then `isabelle getenv ISABELLE_SYMBOLS`, and only when both are empty environment
`ISABELLE_HOME`, then `isabelle getenv ISABELLE_HOME` — prefers the environment only
within one variable and never a less complete source. Nothing to change.

## 7. The other findings, and what each needs

Reported by the same review; none is this urgent, and each is separable.

**`get_SYMBOL_FILES()` reports requested paths, not files read.** The list includes a
file that does not exist on this machine, and paths are not content: two machines can
report identical provenance for different tables. Its docstring tells consumers to
"refuse a mismatch", which they cannot do with this record. The fix is a **content
digest** beside the path list. This belongs with the search site's D45
(`contrib/isasearch-web/docs/SEMANTIC_SEARCH_SITE_PLAN.md:721`): D45 ships the
tokenizer's data as one stamped asset built from this table's files; its other half, a
digest in the index namespace name, was revoked on 2026-08-20. Whether the stamp needs a
content digest is D45's question, so it is settled there rather than patched here. Its
other former motivation, the stale mirrors, has been dismissed.

**`.unicode.thy` mirror staleness — dismissed by the user, 2026-08-18, do not re-raise.**
The measurement stands: 21 phi-System mirrors differ from what `pretty_unicode` produces
today, and 4 of them (`Phi_BI/{Algebras,Arrow_st,Len_Intvl,Map_of_Tree}`) will never
self-correct, because `theory_structure.py:28-29` regenerates only when the `.thy` is
newer and the symbol table is not part of that test. It is recorded here so that the
next review does not report it as new. It is not to be fixed.

**EXPERIENCE document text moves with nothing to invalidate.** `document_text.py:73-74`
applies `pretty_unicode` to stored ASCII `goal_patterns` at read time, so the embedded
text can change while the stored bytes do not. 180 records, 0 affected today. Fix
belongs with whatever handles asset versioning; record it, do not chase it now.

**`【 】` is no longer symbol-free.** `Tools/inner_syntax_error.ML:78-79` (in this
repository) uses U+3010/U+3011 as an in-band marker, and `\<lblbrace>`/`\<rblbrace>`
(`contrib/phi-system/symbols:20-21`) now map to them. Latent: the ML
side works on ASCII before Python sees it. Needs a different marker eventually, or a
documented reason it cannot collide.

**`get_LETTER_SYMBOLS()` has no test against `Pure/General/symbol.ML`'s letter list**
(review item C22 of 2026-09-22, pre-existing, low priority): the comment in `_load_table`
argues that the union of the `letter` and `greek` groups over-approximates
`Symbol.is_letter_symbol`, and a tightening of that union would pass the suite. The
review's fix — parse `letter_symbols` out of the ML file and assert each is in the set,
with a mutant — is deferred by the drafter; do it with the other items here.

**Latent parsing gaps in `_load_symbols`**, all zero-instance on this machine: a symbol
redefined across files leaves a stale `REVERSE_SYMBOLS` entry; only the first `group:`
field of a line is read where Isabelle collects all of them (48 lines in the
distribution carry two); a non-permissive missing file is skipped silently where
Isabelle errors; and the function's mutable default arguments would accumulate across
calls. Fix together, with a test per item.

**Two other symbol tables in the tree stayed at 439** while this one moved to 624:
`Isabelle-MCP/src/isabelle_mcp/utils/isabelle_symbols.py` (whose docstring at `:129`
claims it reads `ISABELLE_SYMBOLS` while `:130-133` read `ISABELLE_HOME` and
`ISABELLE_HOME_USER`) and `AutoCorrode/ir/repl.py:307-309` (reads
`$ISABELLE_HOME/etc/symbols`). `Isabelle_RPC_Host/tokens.py:17` is a different thing, a
hardcoded letter list, that likewise never sees a component's symbols. Not caused by
these commits; now divergent because of them.


## 8. Build order

Each step is finished when its acceptance holds, not before. Steps 1 and 2 are the fix;
3 through 7 are what stop it rotting.

**1. `_render` and `pretty_unicode_indexed` in `unicode.py`.** Keep both `re.sub`
passes exactly as they are, inside one private function `_render(text)`. In each
replacement function, beside the `return`, record the match's `start()`, `end()` and
the replacement's length. `pretty_unicode(src)` returns `_render(src)[0]`.
`pretty_unicode_indexed(symbols)` renders `''.join(symbols)` through `_render`, then
maps each symbol's start (the prefix sums of the symbol lengths) and the final sentinel
through the first pass's records and then the second's, by the three-case convention of
§4 D; the composition is one helper applied twice. About 60 lines in all (the re-check's
prototype of 2026-09-21; `diagnosis/ref.py` is the older instrument).

Clear §6b's first two defects in the same edit, since both sit on these lines: cache one
record so the parallel `SYMBOL_FILES_CACHE` global can go, and drop the `len(char) == 1`
guard.

**This step breaks three of the four existing mutants' anchors.** `test_unicode.py`'s
MUTANTS list anchors each mutant on an exact source line: "the private-use rule is
deleted" on `if char is None or (len(char) == 1 and is_private_use(char)):`
(`test_unicode.py:184`), gone once the guard goes; two mutants (`:178`, `:187`) on the
final `return re.sub(subscript_pattern, …, re.sub(pattern, …, src))` (`unicode.py:248`),
which moves into `_render`; and the fourth anchor (`unicode.py:232`) moves with it. When
an anchor no longer matches, `self_check` prints "mutation site not found — this
self-check is stale" and counts the mutant as **survived**. Re-anchor all of them in the
same commit. The one-record refactor keeps the 4-tuple's shape (§6b), so
the arity unpack in `test_unicode.py`'s `main()` and `tokenize_prototype.py:13` keep
working; run the former to see that they do.

*Accepted when* `pretty_unicode`'s output is byte-identical before and after over the
corpora of §0 and §6.6's hand cases — not as evidence of an equivalent rewrite, which is
not what this is, but as a check that the recording step was not accidentally written as
one — and `pretty_unicode(''.join(symbols)) == pretty_unicode_indexed(symbols)[0]`
holds over the same inputs.

**2. Nothing to decide about behaviour.** Option D changes none; the one behaviour change
in this work, §1b's fold, is a separate commit the author granted. The existing CR
handling stays as it is. The indexed view takes the symbol sequence, so
the line-ending question of the 2026-08-18 draft cannot arise; there is nothing to
remember here.

**3. Strip `FileIndex`.** It hands `pretty_unicode_indexed` the symbols it already
exploded, stores the offsets it gets back, and implements nothing about rendering; its
own bookkeeping (ASCII offsets, line starts) stays.

*Accepted when* `position.py` references neither `SYMBOLS` nor `SUBSUP_TRANS_TABLE` nor
any fold condition, and `grep` says so.

**4. The invariant test.** §3's form, per line, against `idx.source`. Carry **all three**
of §6.5's anti-vacuity devices, not two: the positive-count assertions, the seeded
synthetic table, and making an empty sweep fatal — `check_all` records `EMPTY` and
`main()` still returns 0 today, which is how a machine with no component registered goes
green. Add §6.6's hand-written rendering classes here; no corpus supplies them
all. Document §6.9's interior-offset convention on `pretty_unicode_indexed` while you
are in it.

*Accepted when* it fails against the code as it stood before step 1 — check this by
running it against the parent commit, not by reasoning about it.

**5. Extend `self_check`.** Give `MUTANTS` a per-file field, then add the mutants of
§6.4. The one that decides whether this work succeeded is `FileIndex` restored to
computing its own offsets.

*Accepted when* every mutant is killed and the suite still passes unmutated.

**6. The remaining hygiene.** Clear §6b's third defect, the mutable defaults in
`_load_symbols`. (The `build/lib` deletion and the fallback-order change that stood here
until 2026-09-22 are withdrawn; §6.7 and the end of §6b say why.)

*Accepted when* `_load_symbols` has a test showing that two calls without explicit
dictionaries do not share state.

**7. Re-verify the consumer.** `hover.py`'s two call sites against a real phi-System
file: the column handed to the model addresses the symbol it names.

*Accepted when* a location string produced end to end points at the right token.

### Not in this order, and why

The `get_SYMBOL_FILES` provenance record wants a content digest rather than a path list
(§7). It is deliberately not here: the question belongs to the search site's D45 (its
stamped asset; the namespace-name half of D45 was revoked on 2026-08-20), and settling
it twice would produce two answers. `.unicode.thy`
mirror staleness is dismissed and is not to be fixed. The remaining §7 items are latent,
zero-instance, and separable; do them together, with a test each, whenever convenient.
