import sys
sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")
from Isabelle_RPC_Host.unicode import pretty_unicode
from Isabelle_RPC_Host.position import FileIndex, symbol_explode

def invariant_offenders(t):
    """Plan §3: FileIndex(t).sym_unicode_offsets[i] == len(pretty_unicode(t[:ascii_off_i]))"""
    idx = FileIndex(t)
    bad = []
    for i in range(idx.num_symbols + 1):
        a = idx.sym_ascii_offsets[i]
        want = len(pretty_unicode(idx.source[:a]))
        got = idx.sym_unicode_offsets[i]
        if want != got:
            bad.append((i, a, got, want))
    return idx, bad

cases = {
 "double sub (fold consumption)": r"\<^sub>\<^sub>1",
 "triple sub":                    r"\<^sub>\<^sub>\<^sub>1",
 "single sub":                    r"\<^sub>1",
 "double bold":                   r"\<^bold>\<^bold>a",
 "private-use (phi kw)":          r"\<proc> x",
 "ordinary":                      r"\<forall>x. x \<longrightarrow> x",
 "CRLF":                          "a\r\nb\r\n",
 "sub at EOL":                    "x\\<^sub>\ny",
 "malformed escape":              r"\<alpha \<beta>",
 "empty escape":                  r"\<> \<^> \<1abc>",
 "unterminated":                  r"\<alph",
}
for label, t in cases.items():
    idx, bad = invariant_offenders(t)
    print(f"{label:32s} src={t!r}")
    print(f"{'':32s} pretty={pretty_unicode(t)!r}  FileIndex total={idx.sym_unicode_offsets[-1]} len(pretty)={len(pretty_unicode(idx.source))}")
    if bad:
        print(f"{'':32s} *** {len(bad)} OFFENDER(S): (i, ascii_off, fileindex, pretty) {bad[:6]}")
    else:
        print(f"{'':32s} ok")
