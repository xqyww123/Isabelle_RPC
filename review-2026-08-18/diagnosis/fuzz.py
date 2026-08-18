import random, sys, collections
sys.path.insert(0, "/tmp/claude-1002/-home-qiyuan-Current-MLML/191c16f2-3fa2-4e2b-b337-d141aea09fc8/scratchpad/fixrev_diagnosis")
from ref import compare
from Isabelle_RPC_Host.unicode import get_SYMBOLS, is_private_use
from Isabelle_RPC_Host.position import symbol_explode

S = get_SYMBOLS()
PRIV = [k for k, v in S.items() if len(v) == 1 and is_private_use(v)]
NORMAL = [k for k, v in S.items() if not (len(v) == 1 and is_private_use(v))]
ALPHABET = (
    [r'\<^sub>', r'\<^sup>', r'\<^bold>', '⇩', '⇧', '❙'] * 6 +
    list('abxQ019_ \n>') * 3 +
    [r'\<', r'\<>', r'\<^>', r'\<alpha', '\\', '\r', '\r\n'] +
    random.sample(NORMAL, 40) + random.sample(PRIV, 20)
)

random.seed(20260818)
classes = collections.Counter()
minimal = {}


def minimise(src):
    """Shrink a failing string by deleting alphabet-sized chunks."""
    cur = src
    changed = True
    while changed:
        changed = False
        syms = symbol_explode(cur)
        for i in range(len(syms)):
            cand = ''.join(syms[:i] + syms[i+1:])
            if not cand:
                continue
            try:
                _, _, _, bad = compare(cand)
            except Exception:
                continue
            if bad:
                cur = cand
                changed = True
                break
    return cur


def key_of(src):
    """A coarse signature of the failure: which symbol classes are present."""
    syms = symbol_explode(src)
    k = []
    for s in syms:
        if s in PRIV:
            k.append('PRIV')
        elif S.get(s, s) in ('⇩', '⇧', '❙'):
            k.append('MARK')
        else:
            k.append(repr(s))
    return tuple(k)


fails = 0
N = 4000
for t in range(N):
    src = ''.join(random.choice(ALPHABET) for _ in range(random.randint(1, 14)))
    try:
        _, _, _, bad = compare(src)
    except AssertionError:
        print("REFERENCE RENDERER DISAGREES:", repr(src))
        continue
    if bad:
        fails += 1
        m = minimise(src)
        k = key_of(m)
        classes[k] += 1
        minimal.setdefault(k, m)

print(f"{fails}/{N} random strings fail; {len(classes)} minimal signatures")
for k, n in classes.most_common(30):
    print(f"  {n:5d}  {k}   e.g. {minimal[k]!r}")
