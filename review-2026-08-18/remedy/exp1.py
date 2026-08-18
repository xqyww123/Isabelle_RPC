import sys, os
sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")
from Isabelle_RPC_Host.unicode import pretty_unicode, get_SYMBOLS, ascii_of_unicode
from Isabelle_RPC_Host.position import FileIndex, symbol_explode

S = get_SYMBOLS()
print("table size:", len(S))
print("sub ->", repr(S.get(r"\<^sub>")), "sup ->", repr(S.get(r"\<^sup>")), "bold ->", repr(S.get(r"\<^bold>")))

cases = [
  r"\<^sub>\<^sub>1",
  r"\<^sub>\<^sub>\<^sub>1",
  r"\<^sub>1",
  r"\<^sup>\<^sup>2",
  r"\<^bold>\<^bold>a",
  r"\<^sub>\<^bold>a",
  r"\<^bold>\<^sub>1",
  "⇩⇩" + "1",         # raw chars
  r"x\<^sub>\<^sub>1 y",
]
for c in cases:
    print(repr(c), "->", repr(pretty_unicode(c)))
