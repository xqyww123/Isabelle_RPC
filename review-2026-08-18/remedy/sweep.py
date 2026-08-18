import sys, os, io
sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")
from Isabelle_RPC_Host.unicode import pretty_unicode, get_SYMBOLS, is_private_use, SUBSUP_TRANS_TABLE
from Isabelle_RPC_Host.position import symbol_explode, FileIndex

S = get_SYMBOLS()

def rendered_symbol(sym):
    if sym.startswith('\\<'):
        c = S.get(sym)
        if c is None or (len(c) == 1 and is_private_use(c)):
            return sym
        return c
    return sym

def pretty_unicode_indexed(src):
    syms = symbol_explode(src); out = []; offs = []; n = len(syms); i = 0; pos = 0
    while i < n:
        u = rendered_symbol(syms[i])
        if len(u) == 1 and u in '⇩⇧❙' and i + 1 < n:
            v = rendered_symbol(syms[i + 1])
            if len(v) == 1 and (u + v) in SUBSUP_TRANS_TABLE:
                offs.append(pos); offs.append(pos)
                out.append(SUBSUP_TRANS_TABLE[u + v]); pos += 1; i += 2; continue
        offs.append(pos); out.append(u); pos += len(u); i += 1
    offs.append(pos)
    return ''.join(out), offs

def walk(root):
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d != '.git']
        for f in fn:
            if f.endswith(('.thy', '.ML')) and not f.endswith('.unicode.thy'):
                yield os.path.join(dp, f)

def sweep(root, limit=None):
    n = cr = content = lenbad = 0; ex_c = []; ex_l = []
    for p in walk(root):
        if limit and n >= limit:
            break
        try:
            src = io.open(p, encoding='utf-8').read()
        except Exception:
            continue
        n += 1
        a = pretty_unicode(src); b, _ = pretty_unicode_indexed(src)
        if a != b:
            if a.replace('\r\n', '\n').replace('\r', '\n') == b:
                cr += 1
            else:
                content += 1
                if len(ex_c) < 3:
                    ex_c.append(p)
        idx = FileIndex(src)
        want = len(pretty_unicode(idx.source))
        if idx.sym_unicode_offsets[-1] != want:
            lenbad += 1
            if len(ex_l) < 3:
                ex_l.append((os.path.relpath(p, root), idx.sym_unicode_offsets[-1], want))
    print(f"{root}\n  files={n} | CR-only diff={cr} | CONTENT diff={content} {ex_c}"
          f" | FileIndex-total mismatch={lenbad} {ex_l}", flush=True)

if __name__ == "__main__":
    sweep(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
