#!/usr/bin/env python3
"""Tests for Isabelle_RPC_Host.unicode and the FileIndex offsets built on it — run with
`python3 test_unicode.py`.

Every machine-independent check here is mutation-tested: `python3 test_unicode.py
--self-check` re-runs the suite against deliberately broken copies of `unicode.py` and
`position.py` and fails unless each mutant is caught. The sweep of a phi-system checkout
is deliberately outside that: a mutant copy runs from a temporary directory, and a kill
must not depend on which corpora a machine happens to have. An earlier version of this
file had three table-driven sweeps that reported zero offenders even when
`pretty_unicode` converted nothing at all — they fed each symbol name in isolation, where
idempotence and round-tripping hold for any implementation whatsoever. Sweeps here run
against text with context, and the conversion itself is asserted directly rather than
inferred from its fixed points.

Coverage varies with the machine: the table is whatever `ISABELLE_SYMBOLS` resolves
to, so a host with no component registered has no private-use symbol to check. The
summary says so out loud rather than passing quietly, and the seed table below, with the
seed corpus swept under it, exercises every rendering class on every machine.
"""

import contextlib
import os
import subprocess
import sys
import tempfile
from itertools import accumulate

from Isabelle_RPC_Host import unicode as unicode_module
from Isabelle_RPC_Host.unicode import (
    pretty_unicode, pretty_unicode_indexed, symbol_explode, ascii_of_unicode,
    is_private_use, get_SYMBOLS, get_REVERSE_SYMBOLS, get_LETTER_SYMBOLS,
    get_SYMBOLS_AND_REVERSED, get_SYMBOL_FILES, SUBSUP_TRANS_TABLE, _load_symbols,
    _invert_fold)
from Isabelle_RPC_Host.paths import resolve_isabelle_path_list
from Isabelle_RPC_Host.position import (
    FileIndex, IsabellePosition, AsciiPosition, UnicodePosition, _file_index_cache)

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


def check_count(label, n):
    """A population size. Zero is not a failure of the code under test: it is a sweep
    that had nothing of this kind to look at, and says so."""
    if n > 0:
        print(f"  ok   {label}: {n}")
    else:
        print(f"  ----  {label}: NO DATA on this machine, nothing was checked")
        EMPTY.append(label)


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

# The other half of the pair `symbol_explode` and `_ESCAPE` make: the inputs that pin
# how `symbol_explode` bounds a name (a superset of `_ESCAPE`'s rule; nothing else in
# this file separates the two scans).
SYMBOL_SCANNING = [
    (r"\<1abc>", [r"\<", "1", "a", "b", "c", ">"]),            # a name may not begin with a digit
    (r"\<ab-c>", [r"\<ab", "-", "c", ">"]),                    # nor run through a non-letdig
    ("\\<\u00e9x>", [r"\<", "\u00e9", "x", ">"]),                   # nor begin with a non-ASCII letter
    (r"\<alpha \<beta>", [r"\<alpha", " ", r"\<beta>"]),      # a missing `>` is tolerated
]

# A table of our own, so that every rendering class below is exercised on every
# machine, whatever components are registered: two ordinary symbols (one named with a
# `_` and a digit), the three markers of the fold table, and a synthetic private-use
# symbol at U+E000.
SEED_SYMBOLS = """\\<alpha>   code: 0x0003b1  group: greek
\\<beta_2>  code: 0x0003b2  group: greek
\\<^sub>    code: 0x0021e9  group: control
\\<^sup>    code: 0x0021e7  group: control
\\<^bold>   code: 0x002759  group: control
\\<pua>     code: 0x00e000  font: Synthetic  group: letter
"""
OTHER_SEED = "\\<gamma>   code: 0x0003b3  group: greek\n"
# `\<alpha>` again at another code point and in another group: the later file wins.
OVERLAY_SEED = "\\<alpha>   code: 0x0003b3  group: letter\n"


def seed_file(text=SEED_SYMBOLS):
    with tempfile.NamedTemporaryFile('w', suffix='.symbols', delete=False, encoding='utf-8') as f:
        f.write(text)
        return f.name


@contextlib.contextmanager
def seeded_table():
    """Serve the seed table through the module's own loader, then restore the real one."""
    path = seed_file()
    saved = unicode_module._TABLE
    try:
        unicode_module._TABLE = unicode_module._load_table([path])
        yield
    finally:
        unicode_module._TABLE = saved
        os.unlink(path)


# Cases for every rendering class: the source, its rendering, and where each of its
# symbols begins in the rendering (plus the sentinel). Under the seed table.
INDEXED_CASES = [
    ("private-use symbol",              r"a\<pua>b",                r"a\<pua>b",   [0, 1, 7, 8]),
    ("private-use fold operand",        r"\<^sub>\<pua>x",          "⇩\\<pua>x",   [0, 1, 7, 8]),
    ("ordinary symbol",                 r"\<alpha>",                "α",           [0, 1]),
    ("escape named with _ and a digit", r"a\<beta_2>b",             "aβb",         [0, 1, 2, 3]),
    ("foldable subscript, escape",      r"x\<^sub>i",               "xᵢ",          [0, 1, 1, 2]),
    ("foldable subscript, raw",         "x⇩i",                      "xᵢ",          [0, 1, 1, 2]),
    ("two folds on one line",           r"x\<^sub>i y\<^sub>i",     "xᵢ yᵢ",       [0, 1, 1, 2, 3, 4, 4, 5]),
    ("unfoldable subscript",            r"x\<^sub>Q",               "x⇩Q",         [0, 1, 2, 3]),
    ("bold fold",                       r"\<^bold>x",               "𝐱",           [0, 0, 1]),
    ("bold, no fold available",         r"\<^bold>1",               "❙1",          [0, 1, 2]),
    ("malformed escape",                r"\<alpha \<alpha>",        "\\<alpha α",  [0, 7, 8, 9]),
    # Of adjacent markers the later one applies, the displaced one is emitted literally.
    ("two adjacent markers",            r"x\<^sub>\<^sub>1",        "x⇩₁",         [0, 1, 2, 2, 3]),
    ("three adjacent markers",          r"x\<^sub>\<^sub>\<^sub>1", "x⇩⇩₁",        [0, 1, 2, 3, 3, 4]),
    ("adjacent markers of two kinds",   "x⇩⇧1",                     "x⇩¹",         [0, 1, 2, 2, 3]),
    ("bold then subscript marker",      "x❙⇩a",                     "x❙ₐ",         [0, 1, 2, 2, 3]),
    ("marker before a line break",      "x⇩\ny",                    "x⇩\ny",       [0, 1, 2, 3, 4]),
    ("CRLF",                            "a\r\nb",                   "a\nb",        [0, 1, 2, 3]),
]

# Running text in the seed table's alphabet, swept on every machine so that no sweep is
# empty and section 6.5's three counts are met; every marker is written as an escape,
# and the classes that need a raw marker are the seeded cases' business (sweep_index).
SEED_CORPUS = (
    "theory Seed\n"
    "  lemma \\<alpha>\\<^sub>1 = x\\<^sub>i y\\<^sub>i\n"
    "  \\<pua> f \\<^sub>\\<pua>x \\<^bold>x \\<^bold>1\n"
    "plain ascii line\r\n"
    "  \\<alpha \\<alpha> \\<beta_2>\\<^sub>2 x\\<^sub>Q\n"
    "  x\\<^sub>\\<^sub>1 x\\<^sub>\\<^sub>\\<^sub>1\n"
    "\n"
    "  \\<alpha>\\<^bold>\\<alpha> end\n"
)


def check_indexed_cases():
    print("== the indexed view and FileIndex, cases for every rendering class, seed table ==")
    with seeded_table():
        for label, src, rendering, offsets in INDEXED_CASES:
            symbols = symbol_explode(src)
            got_rendering, got_offsets = pretty_unicode_indexed(symbols)
            check(f"{label}: rendering", got_rendering, rendering)
            check(f"{label}: offsets", got_offsets, offsets)
            check(f"{label}: pretty_unicode is the same view", pretty_unicode(''.join(symbols)), rendering)
            check(f"{label}: FileIndex takes the offsets", list(FileIndex(src).sym_unicode_offsets), offsets)
        check("CRLF: pretty_unicode keeps a raw string's CR", pretty_unicode("a\r\nb"), "a\r\nb")
        check("CRLF: ascii_line is the folded line body", FileIndex("a\r\nb\r\nc").ascii_line(2), "b")

        print("== the table's accessors are projections of one record, seed table ==")
        symbols, reverse, trans, letters = get_SYMBOLS_AND_REVERSED()
        check("symbols", symbols is get_SYMBOLS(), True)
        check("reverse", reverse is get_REVERSE_SYMBOLS(), True)
        check("letters", letters is get_LETTER_SYMBOLS(), True)
        check("the translation table", "\u03b1".translate(trans), r"\<alpha>")
        check("the letter class is the letter and greek groups",
              sorted(letters), [r"\<alpha>", r"\<beta_2>", r"\<pua>"])

    print("== symbol_explode bounds a name by Isabelle's rule ==")
    for src, expected in SYMBOL_SCANNING:
        check(repr(src), symbol_explode(src), expected)

    print("== _load_symbols does not share state between calls ==")
    first_file, second_file = seed_file(), seed_file(OTHER_SEED)
    try:
        first = _load_symbols(first_file)[0]
        second = _load_symbols(second_file)[0]
        check("two loads are distinct objects", first is second, False)
        check("a load holds only its own file", sorted(second), [r"\<gamma>"])
    finally:
        os.unlink(first_file)
        os.unlink(second_file)

    print("== a later symbol file overrides an earlier one ==")
    base, overlay = seed_file(), seed_file(OVERLAY_SEED)
    try:
        layered = unicode_module._load_table([base, overlay])
        check("the later file wins", layered.symbols[r"\<alpha>"], "\u03b3")
        check("the earlier file's other symbols survive", r"\<pua>" in layered.symbols, True)
        check("the later file's group wins", r"\<alpha>" in layered.letters, True)
    finally:
        os.unlink(base)
        os.unlink(overlay)

    print("== the fold's inverse ==")
    check("a table inverts", _invert_fold({"\u21e9a": "\u2090"}), {"\u2090": "\u21e9a"})
    try:
        _invert_fold({"\u21e9a": "\u2090", "\u21e7a": "\u2090"})
        check("a collision is refused", "no error", "RuntimeError")
    except RuntimeError:
        check("a collision is refused", "RuntimeError", "RuntimeError")

    print("== positions ==")
    check("an empty line's end offset is its own symbol",
          FileIndex("a\n\nb").end_of_line_offset(2), 3)
    check("the subclass factories return their own class",
          [type(AsciiPosition.from_s("f:1:2")), type(UnicodePosition.unpack((1, 2, 0, (b"", "f", 0))))],
          [AsciiPosition, UnicodePosition])
    # An unknown offset (Isabelle's 0) keeps the line and gets no column, without
    # reading the file: the index cache stays untouched.
    with tempfile.NamedTemporaryFile('w', suffix='.thy', delete=False, encoding='utf-8') as f:
        f.write("a\nb\nc\n")
    try:
        unknown = IsabellePosition(2, 0, f.name)
        check("an unknown offset has no column", str(unknown.to_unicode_position()), f"{f.name}:2")
        check("and asks for no index", os.path.realpath(f.name) in _file_index_cache, False)
    finally:
        os.unlink(f.name)


def theory_files(root):
    """(path, text) for every `.thy` under `root` but the `.unicode.thy` mirrors."""
    for d, dirs, fs in os.walk(root):
        dirs.sort()          # the offenders a failing sweep names come out in one order
        for f in sorted(fs):
            if f.endswith('.thy') and not f.endswith('.unicode.thy'):
                path = os.path.join(d, f)
                with open(path, encoding='utf-8') as fh:
                    yield path, fh.read()


def sweep_index(texts):
    """What the sweep establishes over every (name, text) in `texts`, per file and per
    line; each property is named, and a failing line says which of them broke.

    The FileIndex conjunct is true by construction (FileIndex stores what the indexed
    view returns) and is the guard against a FileIndex deciding for itself; the others
    are the sweep's content. Returns (file offenders, files), (line offenders, lines),
    the number of slices compared, and section 6.5's three counts — private-use
    escapes, folds, symbols rendered differently — because a sweep that met none of one
    of them proves nothing about it. Section 6.6's rendering classes are the seeded
    cases' business; no corpus supplies them all."""
    symbols_table = get_SYMBOLS()
    private = {n for n, c in symbols_table.items() if is_private_use(c)}
    markers = {pair[0] for pair in SUBSUP_TRANS_TABLE}
    folded = set(SUBSUP_TRANS_TABLE.values())
    file_offenders, files, line_offenders, lines, slices = [], 0, [], 0, 0
    seen = {"private-use escapes": 0, "folds": 0, "symbols rendered differently": 0}
    for name, text in texts:
        files += 1
        whole = FileIndex(text)
        body = whole.source.split('\n')
        held = [
            ("the ASCII sentinel is the source's length",
             whole.sym_ascii_offsets[-1] == len(whole.source)),
            ("the unicode sentinel is the rendering's length",
             whole.sym_unicode_offsets[-1] == len(pretty_unicode(whole.source))),
            ("the lines reassemble the source",
             [whole.ascii_line(no) for no in range(1, whole.num_lines + 1)] == body),
        ]
        if broke := [what for what, holds in held if not holds]:
            file_offenders.append(f"{name} ({'; '.join(broke)})")
        for no, line in enumerate(body, 1):
            lines += 1
            idx = FileIndex(line)
            symbols = symbol_explode(idx.source)
            rendered, offsets = pretty_unicode_indexed(symbols)
            starts = list(accumulate(map(len, symbols), initial=0))
            at = {s: i for i, s in enumerate(starts)}
            first = whole.ascii_to_isabelle(no, 1)
            renders = [pretty_unicode(s) for s in symbols]
            own = [j for j in range(len(symbols))
                   if renders[j] not in markers and (j == 0 or renders[j - 1] not in markers)]
            slices += len(own)
            held = [
                ("FileIndex stores the indexed view's offsets",
                 list(idx.sym_unicode_offsets) == offsets),
                ("the view's sentinel is its rendering's length", offsets[-1] == len(rendered)),
                ("pretty_unicode is the same view", rendered == pretty_unicode(idx.source)),
                ("offsets never decrease", all(a <= b for a, b in zip(offsets, offsets[1:]))),
                ("every _ESCAPE match is exactly one symbol",
                 all(m.start() in at and starts[at[m.start()] + 1] == m.end()
                     for m in unicode_module._ESCAPE.finditer(idx.source))),
                ("a symbol away from a fold owns its slice of the rendering",
                 all(rendered[offsets[j]:offsets[j + 1]] == renders[j] for j in own)),
                ("isabelle_to_unicode places every symbol",
                 all(whole.isabelle_to_unicode(first + j) == (no, offsets[j] + 1)
                     for j in range(len(symbols)))),
                ("ascii_to_unicode places every symbol",
                 all(whole.ascii_to_unicode(no, starts[j] + 1) == (no, offsets[j] + 1)
                     for j in range(len(symbols)))),
                ("isabelle_to_ascii places every symbol",
                 all(whole.isabelle_to_ascii(first + j) == (no, starts[j] + 1)
                     for j in range(len(symbols)))),
                ("unicode_to_isabelle inverts isabelle_to_unicode",
                 all(whole.unicode_to_isabelle(no, offsets[j] + 1) == first + j for j in own)),
                ("unicode_to_ascii inverts ascii_to_unicode",
                 all(whole.unicode_to_ascii(no, offsets[j] + 1) == (no, starts[j] + 1) for j in own)),
            ]
            if broke := [what for what, holds in held if not holds]:
                line_offenders.append(f"{name}:{no} ({'; '.join(broke)})")
            seen["private-use escapes"] += sum(s in private for s in symbols)
            seen["folds"] += sum(ch in folded for ch in rendered)
            seen["symbols rendered differently"] += sum(
                s in symbols_table and s not in private for s in symbols)
    return (file_offenders, files), (line_offenders, lines), slices, seen


def report_sweep(result, label, complete):
    """`complete`: the corpus is ours and must exhibit every class; a machine's own
    corpus that supplies none of one says NO DATA for it instead."""
    (file_offenders, files), (line_offenders, lines), slices, seen = result
    check_all(f"{label}: whole files", file_offenders, files)
    check_all(f"{label}: lines", line_offenders, lines)
    for what, n in [("slices compared", slices), *((f"{cls} seen", c) for cls, c in seen.items())]:
        if complete:
            check(f"{label}: {what}", n > 0, True)
        else:
            check_count(f"{label}: {what}", n)


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

    print("== the sweep over the seed corpus, seed table ==")
    with seeded_table():
        report_sweep(sweep_index([("seed corpus", SEED_CORPUS)]), "seed corpus", complete=True)

    # The real corpus, as corroboration of the seeded cases: phi-system, when it is
    # checked out beside this repository.
    corpus = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "phi-system")
    print("== the sweep over phi-system, the real table ==")
    if not os.path.isdir(corpus):
        print("  (no phi-system checkout beside this repository)")
    report_sweep(sweep_index(theory_files(corpus)), "phi-system", complete=False)   # an absent root walks empty

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
    ("the fold takes an adjacent marker as its operand", UNICODE_PY,
     '_FOLD = re.compile(f"[{_MARKERS}][^{_MARKERS}\\n]")',
     '_FOLD = re.compile(f"[{_MARKERS}].")'),
    ("the fold's inverse does not check injectivity", UNICODE_PY,
     "    if len(inverse) != len(table):",
     "    if False:"),
    ("the 4-tuple is projected in the wrong order", UNICODE_PY,
     "    return (t.symbols, t.reverse, t.trans, t.letters)",
     "    return (t.symbols, t.reverse, t.letters, t.trans)"),
    ("the letter class drops the greek group", UNICODE_PY,
     "    LETTER_SYMBOLS = frozenset(s for s, g in GROUPS.items() if g in ('letter', 'greek'))",
     "    LETTER_SYMBOLS = frozenset(s for s, g in GROUPS.items() if g == 'letter')"),
    ("an earlier symbol file overrides a later one", UNICODE_PY,
     "    for file in symbol_files:",
     "    for file in reversed(symbol_files):"),
    ("a name may begin with a digit", UNICODE_PY,
     "            if j < n and text[j].isascii() and text[j].isalpha():",
     "            if j < n and text[j].isascii() and text[j].isalnum():"),
    ("only the distribution's symbol file is read", UNICODE_PY,
     '        symbol_files = resolve_isabelle_path_list("ISABELLE_SYMBOLS")',
     '        symbol_files = []'),
    ("the recording step is skipped", UNICODE_PY,
     "            records.append(_Record(match.start(), match.end(), len(out)))",
     "            pass"),
    ("an offset inside a rewritten match is not moved to its start", UNICODE_PY,
     "        if here and here.start < off:",
     "        if False:"),
    ("an offset inside a rewritten match ignores the shift before it", UNICODE_PY,
     "            mapped.append(here.start + shift)",
     "            mapped.append(here.start)"),
    # The one that decides whether this work removed the duplication: FileIndex back to
    # computing its own offsets, first without rendering, then with the bare table
    # lookup the old code had.
    ("FileIndex computes its own offsets", POSITION_PY,
     "        _, unicode_offsets = pretty_unicode_indexed(symbols)",
     "        unicode_offsets = [0]\n"
     "        for _s in symbols:\n"
     "            unicode_offsets.append(unicode_offsets[-1] + len(_s))"),
    ("FileIndex renders by a bare table lookup", POSITION_PY,
     "        _, unicode_offsets = pretty_unicode_indexed(symbols)",
     "        from .unicode import get_SYMBOLS\n"
     "        _t = get_SYMBOLS()\n"
     "        unicode_offsets = [0]\n"
     "        for _s in symbols:\n"
     "            unicode_offsets.append(unicode_offsets[-1] + len(_t.get(_s, _s)))"),
    ("FileIndex.source is the raw source, CR and all", POSITION_PY,
     "        self.source = ''.join(symbols)",
     "        self.source = source"),
    ("line starts are not recorded", POSITION_PY,
     "        ascii_lines.extend(sym_ascii[i + 1] for i, sym in enumerate(symbols) if sym == '\\n')",
     "        pass"),
    # `_line_start_unicode` serves the four conversions that read or take a unicode column.
    ("the unicode line start is the ASCII line start", POSITION_PY,
     "        return self.sym_unicode_offsets[sym_idx]",
     "        return self.ascii_line_offsets[line - 1]"),
    ("a column is counted from the file start", POSITION_PY,
     "        return offset - line_start + 1",
     "        return offset + 1"),
    ("a column is read from the file start", POSITION_PY,
     "        return line_start + column - 1",
     "        return column - 1"),
    ("an unknown offset is looked up", POSITION_PY,
     "        if self.raw_offset < 1:\n            return UnicodePosition(self.line, 0, self.file)\n",
     ""),
    ("symbol_explode stops a name at '_' and digits", UNICODE_PY,
     "                while j < n and (text[j].isascii() and (text[j].isalnum() or text[j] in \"_'\")):",
     "                while j < n and (text[j].isascii() and text[j].isalpha()):"),
]


def self_check():
    import io, shutil
    here = os.path.dirname(os.path.abspath(__file__))

    def run_copy(mutation=None):
        """The suite on a fresh copy of the package, with one source line replaced."""
        tmp = tempfile.mkdtemp(prefix="mutcheck_")
        try:
            shutil.copytree(os.path.join(here, "Isabelle_RPC_Host"),
                            os.path.join(tmp, "Isabelle_RPC_Host"))
            shutil.copy(os.path.abspath(__file__), tmp)
            if mutation:
                file, old, new = mutation
                target = os.path.join(tmp, file)
                src = io.open(target, encoding="utf-8").read()
                io.open(target, "w", encoding="utf-8").write(src.replace(old, new))
            return subprocess.run([sys.executable, os.path.basename(__file__)],
                                  cwd=tmp, capture_output=True, text=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def anchored_once(file, old):
        return io.open(os.path.join(here, file), encoding="utf-8").read().count(old) == 1

    # The copies run from a temporary directory; the suite must pass there unmutated,
    # or no verdict below means anything.
    clean = run_copy()
    if clean.returncode != 0:
        print((clean.stdout + clean.stderr)[-3000:])
        print("SELF-CHECK ABORTED: the unmutated copy fails, so no mutant verdict is trustworthy")
        return 1
    survived = []
    for label, file, old, new in MUTANTS:
        if not anchored_once(file, old):
            print(f"  ????  {label}: mutation site not found — this self-check is stale")
            survived.append(label)
            continue
        r = run_copy((file, old, new))
        # A kill is a check that failed, not any non-zero exit: a mutant copy that
        # cannot even run says nothing about the suite.
        if "FAIL" in r.stdout:
            print(f"  killed    {label}")
        elif r.returncode == 0:
            print(f"  SURVIVED  {label}")
            survived.append(label)
        else:
            print(f"  ????  {label}: the mutant copy did not run — {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'no output'}")
            survived.append(label)
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
