# Brief for the second-round review: the fixes after the adversarial review of 3360162

## What is under review
Five commits in `/home/qiyuan/Current/MLML/contrib/Isabelle_RPC`, applied on top of
`3360162` after the first review (`ai-artifacts/UNICODE_REVIEW_2026-09-22.md`, the judge's
verdict MET_ON_CONDITION with 33 upheld items and 13 dismissed):

- `615cb01` the judge's conditions, the drafter's items, the author's first grant
- `601df27` `SUBSUP_RESTORE_TABLE` derived from the fold table (C12)
- `6c1ee40` `symbol_explode` moved beside the escape pattern (C38)
- `2ad1f09` the fold of adjacent markers follows Isabelle (C37, the author's second grant)
- the plan-only commit after it: the four named in the status paragraph, C22 deferred to §7

Their combined diff and messages: `ai-artifacts/UNICODE_REVIEW2_INPUT_2026-09-22.patch`.
Read the first review's brief too (`ai-artifacts/UNICODE_REVIEW_BRIEF_2026-09-22.md`): the
ruled design, the run instructions and the hard rules there still bind.

## The author's rulings since the first review (2026-09-22)
- "只记录实际被改写的匹配" — record only the matches a replacement rewrote; the interior
  convention has two cases ("赞同你的建议").
- Fix §1b as its own commit: the fold pattern is a marker followed by a non-marker, never
  a line break ("赞同你的建议").
- The 2026-08-18 review scripts stay frozen; the README says so ("我无意见").
- Standing: performance at this scale is not a criterion; maintainability and elegance
  decide; only design changes go to the author.

## Disposition of the first review's upheld items (verify each, do not trust)
| item | what was done | where |
|---|---|---|
| C1 | seeded case "two folds on one line"; mutant "ignores the shift before it" | 615cb01 test_unicode.py |
| C2 | SEED_CORPUS in the seed alphabet swept unconditionally under seeded_table(); sweep_index over (name, text) pairs; theory_files producer | 615cb01 |
| C3 | per-symbol slice conjunct away from folds, slices counted, docstring reworded | 615cb01 |
| C4 | _sub_recording records only rewritten matches; _map_offsets two cases; plan §4 D, §6.9 | 615cb01 |
| C5 | annotations on _render, pretty_unicode, pretty_unicode_indexed | 615cb01 |
| C6 | _map_offsets docstring reworded | 615cb01 |
| C7, C34 | named 4-tuple projection; every internal read by field | 615cb01 |
| C8 | markers derived from the fold table with re.escape | 615cb01 (operand class changed in 2ad1f09) |
| C10 | _Record namedtuple; `mapped`; precondition in the docstring | 615cb01 |
| C11 | _load_table(symbol_files=None); fixture through the loader; mutant re-anchored; plan §6.5 | 615cb01 |
| C12 | restore table derived, injectivity enforced | 601df27 |
| C15 | --self-check runs an unmutated copy first; docstrings and plan say the sweep is outside mutation testing | 615cb01 |
| C16 | conversions asserted per line (isabelle_to_unicode, ascii_to_unicode); mutant on _line_start_unicode | 615cb01 |
| C17 | two different seed files; sorted(second) == [\<gamma>] | 615cb01 |
| C20 | accumulate/extend in FileIndex.__init__; whole-file ASCII sentinel and ascii_line reassembly; mutant "line starts are not recorded" | 615cb01 |
| C21 | CRLF ascii_line check; mutant | 615cb01 |
| C22 | DEFERRED to plan §7 (drafter's decision) | 615cb01 plan |
| C24 | citations by statement | 615cb01 plan |
| C25 | plan §6.5; README frozen note | 615cb01 |
| C26 | _load_symbols pure; _load_table layers with update(); test kept | 615cb01 |
| C27 | rendered == pretty_unicode(idx.source) per line | 615cb01 |
| C28 | status line; pre-fix-tree note | 615cb01 plan |
| C33 | invariant stated on pretty_unicode_indexed and symbol_explode; per-line check; seed symbol \<beta_2>; mutant | 615cb01, 6c1ee40 |
| C35 | position.py mutants linear and self-contained | 615cb01 |
| C36 | strict UTF-8 with a context manager | 615cb01 |
| C37 | fold pattern `[markers][^markers\n]`; seeded cases for two kinds of marker and a marker before a line break; plan §1b, §4 D, §6.3, §8 step 2 | 2ad1f09 |
| C38 | symbol_explode in unicode.py; tokens.py imports it from there; the deferred import hoisted; position.py re-exports | 6c1ee40 |
| C39 | _sub_recording docstring | 615cb01 |
| C42 | two populations with their own denominators; plan numbers | 615cb01 |
| C43 | "three counts" wording; plan | 615cb01 |
| C45 | cross-references instead of "94" | 615cb01 plan |
| C46 | module docstring reflowed; `\<alpha \<beta>` single backslashes in the comment | 615cb01 |

## Observed by the drafter after the four commits (verify)
pretty_unicode byte-identical over the 4,506-file corpus after every commit including
2ad1f09 (no adjacent markers in the corpus); the suite passes with the phi-system sweep
(68,148 lines) and without it; `--self-check` kills all fourteen mutants in about six
seconds; the suite fails against the parent commit's FileIndex with no corpus present
(three seeded cases and the seed-corpus sweep); every import order of the package is
cycle-free; test_paths.py passes.

## What this round must answer
1. Is every upheld item resolved as the judge's fix plan specified, or better? Name any
   item resolved differently and say whether the difference is an improvement, a
   regression, or a departure that needs the author.
2. Did the fixes introduce any new defect, hack, or inelegance? Judge the shape as it
   now stands, not the diff alone.
3. Do the acceptance conditions of plan §6 and §8, as amended, now hold?
4. Is anything in the plan or the docstrings now false?
The hard rules of the first brief apply (read-only, no isabelle build, English, evidence
with file:line or a command and its output, nitpicks labelled honestly).
