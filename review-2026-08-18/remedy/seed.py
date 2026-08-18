"""Can a test make the private-use path machine-independent by seeding the cache?"""
import sys, io, os, tempfile
sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")
import Isabelle_RPC_Host.unicode as U

d = tempfile.mkdtemp()
f = os.path.join(d, "symbols")
io.open(f, "w", encoding="utf-8").write(
    "\\<Rightarrow>   code: 0x0021D2  group: operator\n"
    "\\<^sub>         code: 0x0021E9  group: control\n"
    "\\<zzz_fake_pua> code: 0x00E000  font: FakeFont  group: fake\n")
S, R, G = U._load_symbols(f, {}, {}, {})
U.SYMBOLS_CACHE = (S, R, str.maketrans(R), frozenset())
print("seeded table:", S)
print("pretty(private-use)  :", repr(U.pretty_unicode(r"a\<zzz_fake_pua>b")))
print("pretty(ordinary)     :", repr(U.pretty_unicode(r"a\<Rightarrow>b")))
print("pretty(sub fold)     :", repr(U.pretty_unicode(r"x\<^sub>1")))
from Isabelle_RPC_Host.position import FileIndex
idx = FileIndex(r"a\<zzz_fake_pua>b")
print("FileIndex total      :", idx.sym_unicode_offsets[-1],
      " len(pretty) :", len(U.pretty_unicode(idx.source)))
