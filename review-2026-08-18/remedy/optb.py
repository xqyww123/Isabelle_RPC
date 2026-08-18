"""Simulate Option B (shared rendered_symbol) and the plan's proposed mutant."""
import sys, io, re
sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")
from Isabelle_RPC_Host.unicode import get_SYMBOLS, is_private_use, SUBSUP_TRANS_TABLE
from Isabelle_RPC_Host.position import symbol_explode
S = get_SYMBOLS()
STRICT = r"\\<\^?[A-Za-z][A-Za-z0-9_']*>"

def make(d44: bool):
    def rendered_symbol(sym):
        c = S.get(sym)
        if c is None: return sym
        if d44 and len(c) == 1 and is_private_use(c): return sym
        return c
    def pretty(src):                       # unchanged regex pretty_unicode, using rendered_symbol
        a = re.sub(STRICT, lambda m: rendered_symbol(m.group(0)), src)
        return re.sub(r'⇩.|⇧.|❙.', lambda m: SUBSUP_TRANS_TABLE.get(m.group(0), m.group(0)), a)
    def offsets(src):                      # unchanged FileIndex loop, using rendered_symbol
        syms = symbol_explode(src); offs=[]; n=len(syms); i=0; pos=0
        while i < n:
            u = rendered_symbol(syms[i]) if syms[i].startswith('\\<') else syms[i]
            if len(u)==1 and u in '⇩⇧❙' and i+1<n:
                nx = syms[i+1]
                v = rendered_symbol(nx) if nx.startswith('\\<') else nx
                if len(v)==1 and (u+v) in SUBSUP_TRANS_TABLE:
                    offs.append(pos); offs.append(pos); pos+=1; i+=2; continue
            offs.append(pos); pos+=len(u); i+=1
        offs.append(pos); return offs, pos
    return pretty, offsets

for label, d44 in (("Option B, D44 present", True), ("MUTANT: D44 deleted from rendered_symbol", False)):
    pretty, offsets = make(d44)
    print(f"-- {label}")
    for p in ["/home/qiyuan/Current/MLML/contrib/phi-system/Phi_System/Resource_Template.thy",
              "/home/qiyuan/Current/MLML/contrib/Isabelle2025-2/src/Doc/Implementation/Prelim.thy"]:
        src = io.open(p, encoding='utf-8').read()
        norm = ''.join(symbol_explode(src))
        _, tot = offsets(src)
        print(f"     {p.split('/')[-1]:26s} FileIndex-total={tot} len(pretty)={len(pretty(norm))} "
              f"{'AGREE' if tot==len(pretty(norm)) else 'DISAGREE'}")
    print(f"     double-sub  regex={pretty(r'\<^sub>\<^sub>1')!r}  loop-total={offsets(r'\<^sub>\<^sub>1')[1]}"
          f"  -> {'AGREE' if offsets(r'\<^sub>\<^sub>1')[1]==len(pretty(r'\<^sub>\<^sub>1')) else 'DISAGREE'}")
