import sys, io, os, time
sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")
from Isabelle_RPC_Host.unicode import pretty_unicode
from Isabelle_RPC_Host.position import symbol_explode
from sweep import pretty_unicode_indexed, walk

def offenders(src, offs):
    syms = symbol_explode(src); norm=''.join(syms); a=0; out=[]
    for i,s in enumerate(syms):
        if offs[i] != len(pretty_unicode(norm[:a])): out.append((i,s,offs[i]))
        a += len(s)
    return out, len(syms)

print("== literal §3 invariant vs a CORRECT (symbol-driven) implementation ==")
for t in [r"x\<^sub>1", r"\<forall>x", r"\<^bold>abc", r"A\<^sub>1 B\<^sup>2"]:
    r,offs = pretty_unicode_indexed(t)
    o,n = offenders(t, offs)
    print(f"  {t!r} -> {r!r}: {len(o)}/{n} offenders {o}")

print("\n== per-line over src/HOL/Algebra ==")
t0=time.time(); bad=tot=0; nf=0; ex=[]
for p in walk("/home/qiyuan/Current/MLML/contrib/Isabelle2025-2/src/HOL/Algebra"):
    nf+=1
    if nf>25: break
    for line in io.open(p, encoding='utf-8'):
        r,offs = pretty_unicode_indexed(line)
        o,n = offenders(line, offs); bad+=len(o); tot+=n
        if o and len(ex)<3: ex.append((os.path.basename(p), line.strip()[:60], o[:2]))
print(f"  {nf-1} files: {bad} offenders / {tot} symbols  ({time.time()-t0:.1f}s)")
for e in ex: print("   ", e)
