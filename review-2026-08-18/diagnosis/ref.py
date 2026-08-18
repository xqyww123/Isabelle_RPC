"""Reference indexed renderer: reproduces pretty_unicode's two regex passes with
offset tracking, so we can say where symbol i's rendering begins in pretty_unicode(t).

Written for this review only. Verified against pretty_unicode by string equality.
"""
import re
import sys

sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")

from Isabelle_RPC_Host.unicode import (
    get_SYMBOLS, SUBSUP_TRANS_TABLE, is_private_use, pretty_unicode,
)
from Isabelle_RPC_Host.position import symbol_explode, FileIndex

SYMBOL_PATTERN = r"\\<\^?[A-Za-z][A-Za-z0-9_']*>"
FOLD_PATTERN = r'⇩.|⇧.|❙.'


def _pass1(src):
    """Symbol pass. Returns (out, map1) where map1[o] is the offset in `out`
    corresponding to src offset o (monotone, len(src)+1 entries)."""
    SYMBOLS = get_SYMBOLS()
    out = []
    map1 = [0] * (len(src) + 1)
    pos = 0          # src cursor
    olen = 0         # length of `out` so far
    for m in re.finditer(SYMBOL_PATTERN, src):
        # literal run [pos, m.start())
        for k in range(pos, m.start()):
            map1[k] = olen + (k - pos)
        out.append(src[pos:m.start()])
        olen += m.start() - pos
        sym = m.group(0)
        ch = SYMBOLS.get(sym)
        if ch is None or (len(ch) == 1 and is_private_use(ch)):
            rendered = sym
        else:
            rendered = ch
        # every src offset inside the match collapses onto the match's start
        for k in range(m.start(), m.end()):
            map1[k] = olen
        out.append(rendered)
        olen += len(rendered)
        pos = m.end()
    for k in range(pos, len(src) + 1):
        map1[k] = olen + (k - pos)
    out.append(src[pos:])
    return ''.join(out), map1


def _pass2(mid):
    """Fold pass. Returns (out, map2) with len(mid)+1 entries."""
    out = []
    map2 = [0] * (len(mid) + 1)
    pos = 0
    olen = 0
    for m in re.finditer(FOLD_PATTERN, mid):
        for k in range(pos, m.start()):
            map2[k] = olen + (k - pos)
        out.append(mid[pos:m.start()])
        olen += m.start() - pos
        sym = m.group(0)
        rendered = SUBSUP_TRANS_TABLE.get(sym, sym)
        if rendered is sym or rendered == sym:
            # unchanged: offsets inside stay identity
            for k in range(m.start(), m.end()):
                map2[k] = olen + (k - m.start())
        else:
            # merged into one char: marker and operand both start at olen
            for k in range(m.start(), m.end()):
                map2[k] = olen
        out.append(rendered)
        olen += len(rendered)
        pos = m.end()
    for k in range(pos, len(mid) + 1):
        map2[k] = olen + (k - pos)
    out.append(mid[pos:])
    return ''.join(out), map2


def reference_offsets(src):
    """(rendered, offsets) where offsets[i] is where Isabelle symbol i of `src`
    begins in `rendered`; offsets has num_symbols+1 entries (sentinel = len)."""
    mid, map1 = _pass1(src)
    fin, map2 = _pass2(mid)
    assert fin == pretty_unicode(src), "reference renderer disagrees with pretty_unicode"
    syms = symbol_explode(src)
    offs = []
    a = 0
    for s in syms:
        offs.append(map2[map1[a]])
        a += len(s)
    offs.append(map2[map1[len(src)]])
    return fin, offs


def compare(src):
    """Compare FileIndex against the reference on CR-folded text.
    Returns (idx, ref_offsets, list of (symbol_index, fileindex_off, ref_off))."""
    idx = FileIndex(src)
    folded = idx.source
    fin, ref = reference_offsets(folded)
    fi = list(idx.sym_unicode_offsets)
    bad = []
    n = min(len(fi), len(ref))
    for i in range(n):
        if fi[i] != ref[i]:
            bad.append((i, fi[i], ref[i]))
    if len(fi) != len(ref):
        bad.append(('LENGTH', len(fi), len(ref)))
    return idx, fin, ref, bad
