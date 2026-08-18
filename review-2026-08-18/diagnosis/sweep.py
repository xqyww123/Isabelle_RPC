import os, re, sys, collections
sys.path.insert(0, "/tmp/claude-1002/-home-qiyuan-Current-MLML/191c16f2-3fa2-4e2b-b337-d141aea09fc8/scratchpad/fixrev_diagnosis")
from ref import compare, reference_offsets
from Isabelle_RPC_Host.unicode import get_SYMBOLS, is_private_use, pretty_unicode
from Isabelle_RPC_Host.position import symbol_explode, FileIndex

SYMBOLS = get_SYMBOLS()
PRIVATE = {k for k, v in SYMBOLS.items() if len(v) == 1 and is_private_use(v)}
MARKERS = ('⇩', '⇧', '❙')


def classify(src, idx, ref, bad):
    """Attribute each divergence to a class by inspecting the first bad symbol."""
    syms = symbol_explode(idx.source)
    classes = set()
    for entry in bad:
        if entry[0] == 'LENGTH':
            classes.add('array-length')
            continue
        i = entry[0]
        # walk back to the first symbol whose *width* differs from the reference
        # (offset drift is cumulative; the culprit is where the delta first changes)
        classes.add('drift')
    # find culprits: symbols where (ref[i+1]-ref[i]) != (fi[i+1]-fi[i])
    fi = list(idx.sym_unicode_offsets)
    culprits = []
    n = min(len(fi), len(ref)) - 1
    for i in range(n):
        if (fi[i+1] - fi[i]) != (ref[i+1] - ref[i]):
            culprits.append(i)
    out = set()
    for i in culprits:
        s = syms[i]
        if s in PRIVATE:
            out.add('private-use symbol')
        elif SYMBOLS.get(s, s) in MARKERS or s in MARKERS:
            nxt = syms[i+1] if i + 1 < len(syms) else ''
            nu = SYMBOLS.get(nxt, nxt)
            if nu in MARKERS:
                out.add('marker followed by marker (regex consumption)')
            else:
                out.add('marker other')
        else:
            out.add(f'other: {s!r}')
    return out, culprits


def sweep(paths, label):
    total = 0
    failed = []
    classcount = collections.Counter()
    examples = {}
    for p in paths:
        try:
            with open(p, 'r', encoding='utf-8') as f:
                raw = f.read()
        except (UnicodeDecodeError, OSError):
            continue
        total += 1
        try:
            idx, fin, ref, bad = compare(raw)
        except AssertionError as e:
            classcount['reference-renderer-mismatch'] += 1
            failed.append(p)
            continue
        if bad:
            failed.append(p)
            cls, culprits = classify(raw, idx, ref, bad)
            for c in cls:
                classcount[c] += 1
                examples.setdefault(c, (p, culprits[:3]))
    print(f"=== {label}: {len(failed)}/{total} files fail the offset check")
    for c, n in classcount.most_common():
        print(f"    {c}: {n} files   e.g. {examples.get(c)}")
    return failed, total


def find(root, ext='.thy'):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('.git',)]
        for fn in filenames:
            if fn.endswith(ext) and not fn.endswith('.unicode.thy'):
                yield os.path.join(dirpath, fn)


if __name__ == '__main__':
    phi = sorted(find('/home/qiyuan/Current/MLML/contrib/phi-system'))
    f1, t1 = sweep(phi, 'phi-system .thy')
    hol = sorted(find('/home/qiyuan/Current/MLML/contrib/Isabelle2025-2/src/HOL'))
    print(f"(HOL total {len(hol)}; sampling every 4th)")
    f2, t2 = sweep(hol[::4], 'Isabelle2025-2 src/HOL sample')
    with open(os.path.join(os.path.dirname(__file__), 'failed_files.txt'), 'w') as f:
        for p in f1 + f2:
            f.write(p + '\n')
