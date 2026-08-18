# Evidence behind UNICODE_CONSISTENCY_FIX_PLAN.md

Scripts two reviewers wrote on 2026-08-18 while checking the plan. Kept because every
figure the plan quotes came from one of them, and because `remedy/sweep.py` carries the
symbol-driven prototype the fix is to be built from.

They hardcode `/home/qiyuan/Current/MLML/contrib/Isabelle_RPC` on `sys.path`; fix that
before running them elsewhere. They are throwaway review code, not maintained.

## diagnosis/ — is the bug what the plan says it is

- `ref.py` — **the instrument.** Replays `pretty_unicode`'s two regex passes with offset
  tracking, so "where does symbol *i*'s rendering begin" is answerable, and asserts its
  own output equals `pretty_unicode`'s. The plan's §3 invariant needs exactly this.
- `cases.py` — one input per rendering class, each checked against `ref.py`.
- `sweep.py` — the same check over whole corpora; `failed_files.txt` is its output.
- `fuzz.py` — 4,000 random strings, failures minimised by symbol deletion. Produced 11
  minimal signatures, all reducible to the plan's two classes; no third class exists.

## remedy/ — is the proposed cure right

- `sweep.py` — **the symbol-driven prototype**, and the 4,424-file diff against
  `pretty_unicode` that found 0 content differences. `phi.out`, `hol.out`, `afp.out` are
  its per-corpus results.
- `exp1.py` — the adjacent-marker behaviour, and its parity.
- `exp2.py` — escape-pass equivalence: every table key matches the strict pattern, and
  every non-matching `\<`-initial token is not a key.
- `bench.py`, `bench2.py` — the 21x on symbol-free ASCII and the fast-path guard.
- `optb.py` — the measurement that killed the plan's first proposed mutant: with D44
  deleted from a shared rendering function, the two consumers still agree.
- `seed.py` — seeding a synthetic three-symbol table so the tests do not depend on which
  Isabelle components are registered.
- `vac.py`, `vac2.py`, `inv.py`, `inv2.py`, `pin.py`, `exp3.py`, `exp4.py` — the vacuity
  probes and the ill-posedness of the first draft's invariant.
