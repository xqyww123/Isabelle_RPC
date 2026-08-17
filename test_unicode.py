#!/usr/bin/env python3
"""Tests for Isabelle_RPC_Host.unicode — run with `python3 test_unicode.py`.

The interesting property is the private-use rule: a symbol whose code point lies in a
Private Use Area is left as its `\\<name>` escape, because the code point means only what
the font declaring it draws and nothing at all elsewhere. Everything here is driven off
the loaded symbol table rather than a hand-written list, so the file says the same thing
on a machine where no component contributes private-use symbols — it just tests less.
"""

import sys

from Isabelle_RPC_Host.unicode import (
    pretty_unicode, ascii_of_unicode, is_private_use,
    get_SYMBOLS_AND_REVERSED, get_SYMBOL_FILES)

FAILURES = []


def check(label, actual, expected):
    if actual == expected:
        print(f"  ok   {label}: {actual!r}")
    else:
        print(f"  FAIL {label}: got {actual!r}, expected {expected!r}")
        FAILURES.append(label)


def check_all(label, bad, total):
    """Report a table-driven sweep: `bad` is the list of offenders out of `total`."""
    if not bad:
        print(f"  ok   {label}: {total} checked, 0 offenders")
    else:
        print(f"  FAIL {label}: {len(bad)} of {total} — e.g. {bad[:5]}")
        FAILURES.append(label)


PRIVATE_USE_BOUNDARIES = [
    ("", True),    ("", True),      # BMP area, first and last
    ("퟿", False),                          # just below (a surrogate would be worse)
    ("豈", False),                          # just above: CJK compatibility
    ("\U000f0000", True), ("\U000ffffd", True),  # plane 15
    ("\U00100000", True), ("\U0010fffd", True),  # plane 16
    ("\U0010ffff", False),                      # noncharacter, not private use
    ("a", False), ("⟹", False),
]


def main():
    symbols, reverse, _, _ = get_SYMBOLS_AND_REVERSED()
    print(f"== symbol table: {len(symbols)} symbols with a code point, from "
          f"{len(get_SYMBOL_FILES())} file(s) ==")
    for path in get_SYMBOL_FILES():
        print(f"     {path}")

    print("== is_private_use boundaries ==")
    for ch, expected in PRIVATE_USE_BOUNDARIES:
        check(f"U+{ord(ch):04X}", is_private_use(ch), expected)

    print("== a distribution symbol still converts ==")
    # These are in every Isabelle etc/symbols; if one ever is not, the test should say so
    # rather than silently pass.
    for name, expected in ((r"\<Longrightarrow>", "⟹"), (r"\<forall>", "∀"),
                           (r"\<Rightarrow>", "⇒")):
        if name in symbols:
            check(name, pretty_unicode(name), expected)
        else:
            check(f"{name} present in table", False, True)

    print("== sub/superscript folding is untouched by the private-use rule ==")
    check("subscript", pretty_unicode(r"x\<^sub>i"), "xᵢ")
    check("superscript", pretty_unicode(r"y\<^sup>T"), "yᵀ")

    print("== an unknown escape is left alone ==")
    check("unknown", pretty_unicode(r"\<no_such_symbol_here>"), r"\<no_such_symbol_here>")

    print("== every private-use symbol keeps its escape ==")
    private = [n for n, c in symbols.items() if len(c) == 1 and is_private_use(c)]
    check_all("private-use kept as escape",
              [n for n in private if pretty_unicode(n) != n], len(private))
    # A blank line of its own, because zero is a legitimate result here and the reader
    # should not mistake it for the test having been skipped.
    print(f"       ({len(private)} private-use symbols in this table)")

    print("== pretty_unicode is idempotent on every symbol ==")
    check_all("idempotent",
              [n for n in symbols if pretty_unicode(pretty_unicode(n)) != pretty_unicode(n)],
              len(symbols))

    print("== ascii_of_unicode(pretty_unicode(name)) == name ==")
    # Only for symbols the reverse map points back at: two symbols may share a code
    # point, and then the reverse direction can only choose one of them.
    lossless = [n for n, c in symbols.items() if reverse.get(c) == n]
    check_all("round trip",
              [n for n in lossless if ascii_of_unicode(pretty_unicode(n)) != n],
              len(lossless))

    print("== a raw private-use character is named by the reverse direction ==")
    if private:
        name = sorted(private)[0]
        char = symbols[name]
        check("reverse names it", ascii_of_unicode(char), name)
        # and the result must be a fixed point, or the two directions would not settle
        check("and pretty leaves that alone", pretty_unicode(ascii_of_unicode(char)), name)
    else:
        print("  --   skipped: no private-use symbol in this table")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
