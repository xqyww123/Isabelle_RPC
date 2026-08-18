"""Vacuity probes: can a §6-style invariant check pass against a broken implementation?"""
import sys, io
sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")
from Isabelle_RPC_Host.unicode import pretty_unicode
from Isabelle_RPC_Host.position import FileIndex

p = "/home/qiyuan/Current/MLML/contrib/phi-system/Phi_System/Resource_Template.thy"
src = io.open(p, encoding='utf-8').read()
idx = FileIndex(src)
print("Resource_Template.thy: FileIndex total =", idx.sym_unicode_offsets[-1],
      " len(pretty_unicode) =", len(pretty_unicode(idx.source)),
      " drift =", idx.sym_unicode_offsets[-1] - len(pretty_unicode(idx.source)))

# Vacuity A: an invariant checked ONLY over inputs with no symbol at all
plain = "lemma foo: \"x = y\" by simp\n"
i2 = FileIndex(plain)
print("plain-ASCII input: offenders =",
      sum(1 for i in range(i2.num_symbols+1)
          if i2.sym_unicode_offsets[i] != len(pretty_unicode(i2.source[:i2.sym_ascii_offsets[i]]))))

# Vacuity B: identity pretty_unicode + identity FileIndex agree perfectly
class IdIdx:
    pass
def id_pretty(s): return s
def id_offsets(s):
    from Isabelle_RPC_Host.position import symbol_explode
    syms = symbol_explode(s); offs=[]; pos=0
    for x in syms: offs.append(pos); pos+=len(x)
    offs.append(pos); return offs
offs = id_offsets(src)
bad = sum(1 for i,o in enumerate(offs) if o != len(id_pretty(''.join(
    __import__('Isabelle_RPC_Host.position', fromlist=['x']).symbol_explode(src))[:0]) ) and False)
print("identity/identity pair: the §3 invariant holds by construction "
      "(both sides are len of the same prefix) -> 0 offenders, converting nothing")
