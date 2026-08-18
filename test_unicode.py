#!/usr/bin/env python3
"""Tests for Isabelle_RPC_Host.unicode — run with `python3 test_unicode.py`.

Every check here is mutation-tested: `python3 test_unicode.py --self-check` re-runs
the suite against deliberately broken copies of `unicode.py` and fails unless each
mutant is caught. An earlier version of this file had three table-driven sweeps that
reported zero offenders even when `pretty_unicode` converted nothing at all — they
fed each symbol name in isolation, where idempotence and round-tripping hold for any
implementation whatsoever. Sweeps here run against text with context, and the
conversion itself is asserted directly rather than inferred from its fixed points.

Coverage varies with the machine: the table is whatever `ISABELLE_SYMBOLS` resolves
to, so a host with no component registered has no private-use symbol to check. The
summary says so out loud rather than passing quietly.
"""

import subprocess
import sys

from Isabelle_RPC_Host.unicode import (
    pretty_unicode, ascii_of_unicode, is_private_use,
    get_SYMBOLS_AND_REVERSED, get_SYMBOL_FILES)
from Isabelle_RPC_Host.paths import resolve_isabelle_path_list

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
# to break `unicode.py`; the suite must reject every one of them.

MUTANTS = [
    ("conversion is the identity",
     "    return re.sub(subscript_pattern, replace_subsupscript, re.sub(pattern, replace_symbol, src))",
     "    return src"),
    ("the loose escape pattern is restored",
     '    pattern = r"\\\\<\\^?[A-Za-z][A-Za-z0-9_\']*>"',
     "    pattern = r'\\\\<[^>]+>'"),
    ("the private-use rule is deleted",
     "        if char is None or (len(char) == 1 and is_private_use(char)):",
     "        if char is None:"),
    ("the sub/superscript fold is skipped",
     "    return re.sub(subscript_pattern, replace_subsupscript, re.sub(pattern, replace_symbol, src))",
     "    return re.sub(pattern, replace_symbol, src)"),
    ("only the distribution's symbol file is read",
     '    symbol_files = resolve_isabelle_path_list("ISABELLE_SYMBOLS")',
     '    symbol_files = []'),
]


def self_check():
    import io, os, shutil, tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    survived = []
    for label, old, new in MUTANTS:
        tmp = tempfile.mkdtemp(prefix="mutcheck_")
        try:
            shutil.copytree(os.path.join(here, "Isabelle_RPC_Host"),
                            os.path.join(tmp, "Isabelle_RPC_Host"))
            shutil.copy(os.path.abspath(__file__), tmp)
            target = os.path.join(tmp, "Isabelle_RPC_Host", "unicode.py")
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
