import sys, re
sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")
from Isabelle_RPC_Host.unicode import pretty_unicode, get_SYMBOLS, is_private_use, SUBSUP_TRANS_TABLE
from Isabelle_RPC_Host.position import symbol_explode

S = get_SYMBOLS()
strict = re.compile(r"\\<\^?[A-Za-z][A-Za-z0-9_']*>\Z")
bad_keys = [k for k in S if not strict.match(k)]
print("symbol-table keys NOT matching the strict escape regex:", len(bad_keys), bad_keys[:20])

# Prototype Option C: symbol-driven, jEdit-faithful ("latest control wins")
def rendered_symbol(sym):
    if sym.startswith('\\<'):
        c = S.get(sym)
        if c is None or (len(c) == 1 and is_private_use(c)):
            return sym
        return c
    return sym

def pretty_unicode_indexed(src):
    syms = symbol_explode(src)
    out = []
    offs = []
    n = len(syms)
    i = 0
    pos = 0
    while i < n:
        u = rendered_symbol(syms[i])
        if len(u) == 1 and u in '\u21e9\u21e7\u2759' and i + 1 < n:
            v = rendered_symbol(syms[i+1])
            if len(v) == 1 and (u + v) in SUBSUP_TRANS_TABLE:
                offs.append(pos); offs.append(pos)
                out.append(SUBSUP_TRANS_TABLE[u+v])
                pos += 1
                i += 2
                continue
        offs.append(pos)
        out.append(u)
        pos += len(u)
        i += 1
    offs.append(pos)
    return ''.join(out), offs

for c in [r"\<^sub>\<^sub>1", r"\<^sub>\<^sub>\<^sub>1", r"\<^bold>\<^bold>a", r"\<proc> x"]:
    r, o = pretty_unicode_indexed(c)
    print(f"{c!r}: regex={pretty_unicode(c)!r}  symbol-driven={r!r}")
