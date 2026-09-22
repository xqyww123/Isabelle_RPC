#!/usr/bin/env python3
"""Tests for Isabelle_RPC_Host.unicode and the FileIndex offsets built on it — run with
`python3 test_unicode.py`.

Every check here is mutation-tested: `python3 test_unicode.py --self-check` re-runs
the suite against deliberately broken copies of `unicode.py` and `position.py` and
fails unless each mutant is caught. An earlier version of this file had three table-driven sweeps that
reported zero offenders even when `pretty_unicode` converted nothing at all — they
fed each symbol name in isolation, where idempotence and round-tripping hold for any
implementation whatsoever. Sweeps here run against text with context, and the
conversion itself is asserted directly rather than inferred from its fixed points.

Coverage varies with the machine: the table is whatever `ISABELLE_SYMBOLS` resolves
to, so a host with no component registered has no private-use symbol to check. The
summary says so out loud rather than passing quietly.
"""

import contextlib
import os
import subprocess
import sys
import tempfile

from Isabelle_RPC_Host import unicode as unicode_module
from Isabelle_RPC_Host.unicode import (
    pretty_unicode, pretty_unicode_indexed, ascii_of_unicode, is_private_use,
    get_SYMBOLS_AND_REVERSED, get_SYMBOL_FILES, SUBSUP_RESTORE_TABLE, _load_symbols)
from Isabelle_RPC_Host.paths import resolve_isabelle_path_list
from Isabelle_RPC_Host.position import FileIndex, symbol_explode

FAILURES = []
EMPTY = []


def check(label, actual, expected):
    if actual == expected:
        print(f"  ok   {label}: {actual!r}")
    else:
        print(f"  FAIL {label}: got {actual!r}, expected {expected!r}")
        FAILURES.append(label)


def check_all(label, bad, total):
    """A sweep. Reports the offenders, and complains if there were none to sweep."""
    if total == 0:
        print(f"  ----  {label}: NO DATA on this machine, nothing was checked")
        EMPTY.append(label)
    elif not bad:
        print(f"  ok   {label}: {total} checked, 0 offenders")
    else:
        print(f"  FAIL {label}: {len(bad)} of {total} — e.g. {bad[:5]}")
        FAILURES.append(label)


# U+DFFF is written as a lone surrogate on purpose: `ord` accepts it, so the lower
# boundary of the BMP area is testable even though the character is not valid text.
PRIVATE_USE_BOUNDARIES = [
    # Written as code points: a private-use character has no glyph, and a lone
    # surrogate is not valid text, so neither survives being typed into a literal.
    (0xD800, False), (0xDFFF, False),        # just below the BMP area, as close as reachable
    (0xE000, True),  (0xF8FF, True),         # the BMP area, both ends
    (0xF900, False),                         # just above
    (0xEFFFF, False), (0xF0000, True),       # plane 15, both sides of its lower edge
    (0xFFFFD, True),  (0xFFFFE, False),      # ... and its top: noncharacters stay out
    (0xFFFFF, False),
    (0x100000, True), (0x10FFFD, True),      # plane 16, likewise
    (0x10FFFE, False), (0x10FFFF, False),
    (ord("a"), False), (ord("⟹"), False),
]

# The inputs that distinguish Isabelle's rule for naming a symbol from a looser scan
# that runs to the next '>'. Nothing else in this file separates the two.
ESCAPE_SCANNING = [
    (r"\<alpha \<beta>", "\\<alpha β"),   # a malformed escape must not swallow a valid one
    (r"\< \<alpha>", "\\< α"),
    (r"\<\<alpha>", "\\<α"),
    (r"a \< b > c \<alpha>", "a \\< b > c α"),
    (r"\<1abc>", r"\<1abc>"),             # a name may not begin with a digit
    (r"\<>", r"\<>"),                     # nor be empty
]

# A table of our own, so that every rendering class below is exercised on every
# machine, whatever components are registered: one ordinary symbol, the markers, and a
# synthetic private-use symbol at U+E000.
SEED_SYMBOLS = """\\<alpha>   code: 0x0003b1  group: greek
\\<^sub>    code: 0x0021e9  group: control
\\<^bold>   code: 0x002759  group: control
\\<pua>     code: 0x00e000  font: Synthetic  group: letter
"""


def seed_file():
    with tempfile.NamedTemporaryFile('w', suffix='.symbols', delete=False, encoding='utf-8') as f:
        f.write(SEED_SYMBOLS)
        return f.name


@contextlib.contextmanager
def seeded_table():
    """Serve the seed table through the module's own loader, then restore the real one."""
    path = seed_file()
    saved = unicode_module._TABLE
    try:
        symbols, reverse, _ = _load_symbols(path)
        unicode_module._TABLE = unicode_module._Table(
            symbols, reverse, str.maketrans(reverse), frozenset(), (path,))
        yield
    finally:
        unicode_module._TABLE = saved
        os.unlink(path)


# One case per rendering class: the source, its rendering, and where each of its
# symbols begins in the rendering (plus the sentinel). Under the seed table.
INDEXED_CASES = [
    ("private-use symbol",           r"a\<pua>b",                r"a\<pua>b",   [0, 1, 7, 8]),
    ("private-use fold operand",     r"\<^sub>\<pua>x",          "⇩\\<pua>x",   [0, 1, 7, 8]),
    ("ordinary symbol",              r"\<alpha>",                "α",           [0, 1]),
    ("foldable subscript, escape",   r"x\<^sub>i",               "xᵢ",          [0, 1, 1, 2]),
    ("foldable subscript, raw",      "x⇩i",                      "xᵢ",          [0, 1, 1, 2]),
    ("unfoldable subscript",         r"x\<^sub>Q",               "x⇩Q",         [0, 1, 2, 3]),
    ("bold fold",                    r"\<^bold>x",               "𝐱",           [0, 0, 1]),
    ("bold, no fold available",      r"\<^bold>1",               "❙1",          [0, 1, 2]),
    ("malformed escape",             r"\<alpha \<alpha>",        "\\<alpha α",  [0, 7, 8, 9]),
    ("two adjacent markers",         r"x\<^sub>\<^sub>1",        "x⇩⇩1",        [0, 1, 2, 3, 4]),
    ("three adjacent markers",       r"x\<^sub>\<^sub>\<^sub>1", "x⇩⇩₁",        [0, 1, 2, 3, 3, 4]),
    ("CRLF",                         "a\r\nb",                   "a\nb",        [0, 1, 2, 3]),
]


def check_indexed_cases():
    print("== the indexed view and FileIndex, one case per rendering class, seed table ==")
    with seeded_table():
        for label, src, rendering, offsets in INDEXED_CASES:
            symbols = symbol_explode(src)
            got_rendering, got_offsets = pretty_unicode_indexed(symbols)
            check(f"{label}: rendering", got_rendering, rendering)
            check(f"{label}: offsets", got_offsets, offsets)
            check(f"{label}: pretty_unicode is the same view", pretty_unicode(''.join(symbols)), rendering)
            check(f"{label}: FileIndex takes the offsets", list(FileIndex(src).sym_unicode_offsets), offsets)
        check("CRLF: pretty_unicode keeps a raw string's CR", pretty_unicode("a\r\nb"), "a\r\nb")

    print("== _load_symbols does not share state between calls ==")
    path = seed_file()
    try:
        first = _load_symbols(path)[0]
        second = _load_symbols(path)[0]
        check("two loads are distinct objects", first is second, False)
        check("a load holds only its own file", len(second), 4)
    finally:
        os.unlink(path)


def sweep_index(root):
    """The plan's invariant over every `.thy` under `root`, per line: FileIndex's
    offsets are the indexed view's, its sentinel is the rendering's length, offsets never
    decrease, and pretty_unicode is the same view. Also whole-file sentinels. Returns the
    offenders, the number of lines, and how often each rendering class was seen — a sweep
    that saw none of a class proves nothing about it."""
    symbols_table = get_SYMBOLS_AND_REVERSED()[0]
    private = {n for n, c in symbols_table.items() if is_private_use(c)}
    folded = set(SUBSUP_RESTORE_TABLE)
    offenders, lines = [], 0
    seen = {"private-use escapes": 0, "folds": 0, "symbols rendered differently": 0}
    for d, _, fs in os.walk(root):
        for f in sorted(fs):
            if not f.endswith('.thy') or f.endswith('.unicode.thy'):
                continue
            path = os.path.join(d, f)
            text = open(path, encoding='utf-8', errors='surrogateescape').read()
            whole = FileIndex(text)
            if whole.sym_unicode_offsets[-1] != len(pretty_unicode(whole.source)):
                offenders.append(path)
            for no, line in enumerate(text.split('\n'), 1):
                lines += 1
                idx = FileIndex(line)
                symbols = symbol_explode(idx.source)
                rendered, offsets = pretty_unicode_indexed(symbols)
                if not (list(idx.sym_unicode_offsets) == offsets
                        and offsets[-1] == len(rendered) == len(pretty_unicode(idx.source))
                        and all(a <= b for a, b in zip(offsets, offsets[1:]))):
                    offenders.append(f"{path}:{no}")
                seen["private-use escapes"] += sum(s in private for s in symbols)
                seen["folds"] += sum(ch in folded for ch in rendered)
                seen["symbols rendered differently"] += sum(
                    s in symbols_table and s not in private for s in symbols)
    return offenders, lines, seen


def main():
    symbols, reverse, _, _ = get_SYMBOLS_AND_REVERSED()
    print(f"== symbol table: {len(symbols)} symbols with a code point, from "
          f"{len(get_SYMBOL_FILES())} file(s) ==")
    for path in get_SYMBOL_FILES():
        print(f"     {path}")

    # The table must be the one Isabelle presents, component files included -- not a
    # list rebuilt from ISABELLE_HOME, which sees the distribution alone. Comparing
    # against the settings variable keeps this true on any machine, whatever is
    # registered there.
    print("== the loaded files are the ones ISABELLE_SYMBOLS names ==")
    declared = resolve_isabelle_path_list("ISABELLE_SYMBOLS")
    if declared:
        check("file list", list(get_SYMBOL_FILES()), declared)
    else:
        print("  ----  NO DATA: ISABELLE_SYMBOLS is not resolvable here")
        EMPTY.append("file list")

    print("== is_private_use boundaries ==")
    for cp, expected in PRIVATE_USE_BOUNDARIES:
        check(f"U+{cp:04X}", is_private_use(chr(cp)), expected)

    print("== named symbols convert ==")
    for name, expected in ((r"\<Longrightarrow>", "⟹"), (r"\<forall>", "∀"),
                           (r"\<Rightarrow>", "⇒")):
        if name in symbols:
            check(name, pretty_unicode(name), expected)
        else:
            check(f"{name} present in table", False, True)

    print("== sub/superscript folding ==")
    check("subscript", pretty_unicode(r"x\<^sub>i"), "xᵢ")
    check("superscript", pretty_unicode(r"y\<^sup>T"), "yᵀ")
    check("bold", pretty_unicode(r"\<^bold>x"), "𝐱")

    print("== an escape is recognised by Isabelle's rule, not by scanning to '>' ==")
    for src, expected in ESCAPE_SCANNING:
        check(repr(src), pretty_unicode(src), expected)

    print("== an unknown escape is left alone ==")
    check("unknown", pretty_unicode(r"\<no_such_symbol_here>"), r"\<no_such_symbol_here>")

    check_indexed_cases()

    # The real corpus, as corroboration of the seeded cases above: phi-system, when it is
    # checked out beside this repository. Its count of each class must be positive, or
    # the sweep ran on text that could not have exercised the fix.
    corpus = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "phi-system")
    print("== FileIndex agrees with the rendering on every line of phi-system ==")
    if os.path.isdir(corpus):
        offenders, lines, seen = sweep_index(corpus)
        check_all("FileIndex offsets", offenders, lines)
        for cls, count in seen.items():
            check(f"the sweep saw {cls}", count > 0, True)
    else:
        print("  ----  NO DATA: no phi-system checkout beside this repository")
        EMPTY.append("FileIndex offsets")

    # The sweeps below assert the conversion itself. Checking only its fixed points
    # is what made the previous version of this file vacuous: a bare `\<name>` maps
    # either to itself or to one character, and both are fixed points under any
    # implementation, so idempotence and round-tripping held for all of them.
    ordinary = {n: c for n, c in symbols.items() if not is_private_use(c)}
    print("== every ordinary symbol converts to its code point ==")
    check_all("converts", [n for n, c in ordinary.items() if pretty_unicode(n) != c],
              len(ordinary))

    private = [n for n, c in symbols.items() if is_private_use(c)]
    print("== every private-use symbol keeps its escape ==")
    check_all("private-use kept as escape",
              [n for n in private if pretty_unicode(n) != n], len(private))

    # In context, so that the surrounding text can be disturbed and the fold pass has
    # something to act on. `f {} g\<^sub>1` embeds each name between real tokens.
    context = lambda n: "f " + n + r" g\<^sub>1"
    print("== pretty_unicode is idempotent, in context ==")
    check_all("idempotent",
              [n for n in symbols
               if pretty_unicode(pretty_unicode(context(n))) != pretty_unicode(context(n))],
              len(symbols))

    print("== ascii_of_unicode(pretty_unicode(x)) == x, in context ==")
    # Only where the reverse map points back at the name: two symbols may share a code
    # point, and then the reverse direction can only choose one of them.
    lossless = [n for n, c in symbols.items() if reverse.get(c) == n]
    check_all("round trip",
              [n for n in lossless if ascii_of_unicode(pretty_unicode(context(n))) != context(n)],
              len(lossless))

    print("== a raw private-use character is named, and that names settles ==")
    if private:
        name = sorted(private)[0]
        char = symbols[name]
        check("reverse names it", ascii_of_unicode(char), name)
        check("and pretty leaves that alone", pretty_unicode(ascii_of_unicode(char)), name)
    else:
        print("  ----  NO DATA: no private-use symbol in this table")
        EMPTY.append("private-use round trip")

    print()
    if EMPTY:
        print(f"NOTE: {len(EMPTY)} check(s) had no data on this machine: "
              f"{', '.join(EMPTY)}")
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("All checks passed.")
    return 0


# --- mutation self-check -----------------------------------------------------------
# A test that cannot fail is worse than no test. Each mutant below is a plausible way
# to break `unicode.py` or `position.py`; the suite must reject every one of them.

UNICODE_PY = "Isabelle_RPC_Host/unicode.py"
POSITION_PY = "Isabelle_RPC_Host/position.py"
MUTANTS = [
    ("conversion is the identity", UNICODE_PY,
     "    return _render(src)[0]",
     "    return src"),
    ("the loose escape pattern is restored", UNICODE_PY,
     '_ESCAPE = re.compile(r"\\\\<\\^?[A-Za-z][A-Za-z0-9_\']*>")',
     "_ESCAPE = re.compile(r'\\\\<[^>]+>')"),
    ("the private-use rule is deleted", UNICODE_PY,
     "    if char is None or is_private_use(char):",
     "    if char is None:"),
    ("the sub/superscript fold is skipped", UNICODE_PY,
     "    out, folds = _sub_recording(_FOLD, _fold, mid)",
     "    out, folds = mid, []"),
    ("only the distribution's symbol file is read", UNICODE_PY,
     '    symbol_files = resolve_isabelle_path_list("ISABELLE_SYMBOLS")',
     '    symbol_files = []'),
    ("the recording step is skipped", UNICODE_PY,
     "        records.append((match.start(), match.end(), len(out)))",
     "        pass"),
    ("an offset inside a match that changed length is not moved to its start", UNICODE_PY,
     "        if record and record[0] < off and record[2] != record[1] - record[0]:",
     "        if False:"),
    # The one that decides whether this work removed the duplication: FileIndex back to
    # computing its own offsets, first without rendering, then with the bare table
    # lookup the old code had.
    ("FileIndex computes its own offsets", POSITION_PY,
     "        _, unicode_offsets = pretty_unicode_indexed(symbols)",
     "        unicode_offsets = [sum(map(len, symbols[:k])) for k in range(len(symbols) + 1)]"),
    ("FileIndex renders by a bare table lookup", POSITION_PY,
     "        _, unicode_offsets = pretty_unicode_indexed(symbols)",
     "        unicode_offsets = [sum(len(__import__('Isabelle_RPC_Host.unicode', fromlist=['get_SYMBOLS'])"
     ".get_SYMBOLS().get(s, s)) for s in symbols[:k]) for k in range(len(symbols) + 1)]"),
]


def self_check():
    import io, shutil
    here = os.path.dirname(os.path.abspath(__file__))
    survived = []
    for label, file, old, new in MUTANTS:
        tmp = tempfile.mkdtemp(prefix="mutcheck_")
        try:
            shutil.copytree(os.path.join(here, "Isabelle_RPC_Host"),
                            os.path.join(tmp, "Isabelle_RPC_Host"))
            shutil.copy(os.path.abspath(__file__), tmp)
            target = os.path.join(tmp, file)
            src = io.open(target, encoding="utf-8").read()
            if src.count(old) != 1:
                print(f"  ????  {label}: mutation site not found — this self-check is stale")
                survived.append(label)
                continue
            io.open(target, "w", encoding="utf-8").write(src.replace(old, new))
            r = subprocess.run([sys.executable, os.path.basename(__file__)],
                               cwd=tmp, capture_output=True, text=True)
            if r.returncode == 0:
                print(f"  SURVIVED  {label}")
                survived.append(label)
            else:
                print(f"  killed    {label}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print()
    if survived:
        print(f"SELF-CHECK FAILED: {len(survived)} mutant(s) survived: {', '.join(survived)}")
        return 1
    print(f"Self-check passed: all {len(MUTANTS)} mutants killed.")
    return 0


def test_unicode_suite():
    """pytest entry point — `python -m pytest test_unicode.py` collected nothing before."""
    assert main() == 0


if __name__ == "__main__":
    sys.exit(self_check() if "--self-check" in sys.argv else main())
