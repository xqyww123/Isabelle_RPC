"""Is the plan's literal §3 invariant sound against a CORRECT implementation?

  sym_unicode_offsets[i] == len(pretty_unicode(source[:sym_ascii_offsets[i]]))

Oracle offsets come from the symbol-driven prototype in sweep.py, which is
byte-identical to pretty_unicode on 4424 real files.
"""
import sys, io, os
sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")
from Isabelle_RPC_Host.unicode import pretty_unicode
from Isabelle_RPC_Host.position import symbol_explode
from sweep import pretty_unicode_indexed, walk


def literal_invariant_offenders(src, offs):
    syms = symbol_explode(src)
    norm = ''.join(syms)
    a = 0
    bad = 0
    first = None
    for i, s in enumerate(syms):
        want = len(pretty_unicode(norm[:a]))
        if offs[i] != want:
            bad += 1
            if first is None:
                first = (i, s, offs[i], want, norm[max(0, a - 12):a + 12])
        a += len(s)
    return bad, len(syms), first


for label, t in [("x sub 1", r"x\<^sub>1"),
                 ("plain", r"\<forall>x"),
                 ("bold", r"\<^bold>abc")]:
    r, offs = pretty_unicode_indexed(t)
    print(label, t, "->", repr(r), literal_invariant_offenders(t, offs))

print()
root = sys.argv[1] if len(sys.argv) > 1 else "/home/qiyuan/Current/MLML/contrib/Isabelle2025-2/src/HOL/Algebra"
tot_bad = tot_sym = nfiles = 0
for p in walk(root):
    nfiles += 1
    if nfiles > 40:
        break
    src = io.open(p, encoding='utf-8').read()
    _, offs = pretty_unicode_indexed(src)
    b, n, first = literal_invariant_offenders(src, offs)
    tot_bad += b
    tot_sym += n
    if b and tot_bad == b:
        print("first offender in", os.path.basename(p), first)
print(f"\nliteral §3 invariant vs a CORRECT implementation over {nfiles-1} files: "
      f"{tot_bad} offenders out of {tot_sym} symbols")
