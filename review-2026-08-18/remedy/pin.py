import sys, io
sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")
from Isabelle_RPC_Host.unicode import pretty_unicode
from Isabelle_RPC_Host.position import FileIndex
from sweep import pretty_unicode_indexed

for p in sys.argv[1:]:
    src = io.open(p, encoding='utf-8').read()
    idx = FileIndex(src)
    lines = idx.source.split('\n')
    print("==", p)
    for ln, text in enumerate(lines, 1):
        fi = FileIndex(text)
        if fi.sym_unicode_offsets[-1] != len(pretty_unicode(text)):
            print(f"  line {ln}: FileIndex={fi.sym_unicode_offsets[-1]} pretty={len(pretty_unicode(text))}")
            print(f"    src   : {text.strip()[:160]!r}")
            print(f"    regex : {pretty_unicode(text).strip()[:160]!r}")
            print(f"    symdrv: {pretty_unicode_indexed(text)[0].strip()[:160]!r}")
