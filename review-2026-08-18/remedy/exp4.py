import sys, os, io
sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")
from Isabelle_RPC_Host.unicode import pretty_unicode
from Isabelle_RPC_Host.position import FileIndex
from exp3 import pretty_unicode_indexed

roots = ["/home/qiyuan/Current/MLML/contrib/phi-system",
         "/home/qiyuan/Current/MLML/contrib/Isabelle2025-2/src",
         "/home/qiyuan/Current/MLML/contrib/afp-2026-05-13/thys"]
files = []
for r in roots:
    for dp, dn, fn in os.walk(r):
        dn[:] = [d for d in dn if d not in ('.git',)]
        for f in fn:
            if f.endswith(('.thy', '.ML')) and not f.endswith('.unicode.thy'):
                files.append(os.path.join(dp, f))
print("files:", len(files))

n_cr = n_folddiff = n_len_mismatch = 0
ex_fold = []
ex_len = []
n_inv_offend_files = 0
inv_examples = []
checked = 0
for p in files:
    try:
        src = io.open(p, encoding='utf-8').read()
    except Exception:
        continue
    checked += 1
    a = pretty_unicode(src)
    b, offs = pretty_unicode_indexed(src)
    if a != b:
        if a.replace('\r\n', '\n').replace('\r', '\n') == b:
            n_cr += 1
        else:
            n_folddiff += 1
            if len(ex_fold) < 5: ex_fold.append(p)
    # FileIndex total-length invariant, on the normalized source
    idx = FileIndex(src)
    want = len(pretty_unicode(idx.source))
    if idx.sym_unicode_offsets[-1] != want:
        n_len_mismatch += 1
        if len(ex_len) < 5: ex_len.append((p, idx.sym_unicode_offsets[-1], want))

print(f"checked {checked}")
print(f"  regex vs symbol-driven differ only by CR normalization : {n_cr}")
print(f"  regex vs symbol-driven differ in CONTENT (fold etc.)   : {n_folddiff}  {ex_fold}")
print(f"  FileIndex total != len(pretty_unicode(source))          : {n_len_mismatch}  {ex_len}")
