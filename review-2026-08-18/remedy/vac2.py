import sys, io, time
sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")
from Isabelle_RPC_Host.unicode import pretty_unicode
from Isabelle_RPC_Host.position import FileIndex, symbol_explode

p = "/home/qiyuan/Current/MLML/contrib/phi-system/Phi_System/Resource_Template.thy"
src = io.open(p, encoding='utf-8').read()
idx = FileIndex(src)
print("Resource_Template.thy: FileIndex total =", idx.sym_unicode_offsets[-1],
      "| len(pretty_unicode) =", len(pretty_unicode(idx.source)),
      "| drift =", idx.sym_unicode_offsets[-1] - len(pretty_unicode(idx.source)))

# cost of the literal §3 invariant on ONE 100-line file
lines = idx.source.split('\n')[:100]
t0 = time.time()
for ln in lines:
    fi = FileIndex(ln)
    for i in range(fi.num_symbols + 1):
        len(pretty_unicode(ln[:fi.sym_ascii_offsets[i]]))
print(f"literal §3 over 100 lines of one file: {time.time()-t0:.2f}s")

# Vacuity: an all-ASCII corpus
plain = "lemma foo: \"x = y\" by simp\n" * 20
i2 = FileIndex(plain)
bad = sum(1 for i in range(i2.num_symbols+1)
          if i2.sym_unicode_offsets[i] != len(pretty_unicode(i2.source[:i2.sym_ascii_offsets[i]])))
print("all-ASCII corpus offenders:", bad, "of", i2.num_symbols+1, "(passes against ANY implementation)")
