#!/usr/bin/env python3
"""Tests for Isabelle_RPC_Host.paths — run with `python3 test_paths.py`.

The Windows branch is exercised by flipping `os.name`, which is enough because the
/cygdrive rule is pure string handling: it never touches `os.path` (that is exactly
why it survives a non-ASCII user name, and why it is reachable from a Linux test).
"""

import os
import sys

from Isabelle_RPC_Host.paths import platform_path, resolve_isabelle_path_list

FAILURES = []


def check(label, actual, expected):
    if actual == expected:
        print(f"  ok   {label}: {actual!r}")
    else:
        print(f"  FAIL {label}: got {actual!r}, expected {expected!r}")
        FAILURES.append(label)


def check_idempotent(label, value):
    once = platform_path(value)
    twice = platform_path(once)
    if once == twice:
        print(f"  ok   idempotent {label}: {value!r} -> {once!r}")
    else:
        print(f"  FAIL idempotent {label}: {value!r} -> {once!r} -> {twice!r}")
        FAILURES.append(f"idempotent {label}")


CYGDRIVE_CASES = [
    ("plain", "/cygdrive/c/isa/Isabelle2025-2", "C:\\isa\\Isabelle2025-2"),
    # The reason this module exists: ISABELLE_HOME_USER is C:\Users\<name>\..., and a
    # non-ASCII user name must survive. It does here precisely because we convert by
    # string rules rather than decoding a subprocess's output with the ANSI code page.
    ("non-ascii user", "/cygdrive/c/Users/张三/.isabelle/Isabelle2025-2",
     "C:\\Users\\张三\\.isabelle\\Isabelle2025-2"),
    ("bare drive root", "/cygdrive/c", "C:\\"),
    ("uppercase drive", "/cygdrive/D/x", "D:\\x"),
    ("trailing slash", "/cygdrive/c/isa/", "C:\\isa\\"),
]

NON_POSIX_CASES = [
    ("already native", "C:\\isa\\Isabelle2025-2"),
    ("empty", ""),
    ("relative", "etc/symbols"),
]


def main():
    # The no-op section only means anything on a POSIX host; skip it on Windows rather
    # than fail there — Windows is the platform this module exists for, so its own test
    # had better run there.
    if os.name != "nt":
        print("== non-Windows: platform_path is a no-op ==")
        for label, value, _ in CYGDRIVE_CASES:
            check(f"no-op {label}", platform_path(value), value)
        for label, value in NON_POSIX_CASES:
            check(f"no-op {label}", platform_path(value), value)
            check_idempotent(label, value)
    else:
        print("== non-Windows no-op section: skipped (host is Windows) ==")

    print("== simulated Windows: /cygdrive string rule ==")
    real_name = os.name
    os.name = "nt"  # the /cygdrive branch is pure string handling, so this suffices
    try:
        for label, value, expected in CYGDRIVE_CASES:
            check(label, platform_path(value), expected)
            check_idempotent(label, value)
        for label, value in NON_POSIX_CASES:
            # Not POSIX-looking, so untouched even on Windows.
            check(f"untouched {label}", platform_path(value), value)
            check_idempotent(f"win {label}", value)
    finally:
        os.name = real_name

    print("== resolve_isabelle_path_list ==")
    # ISABELLE_SYMBOLS is the case this exists for: Isabelle appends to it, so the
    # list carries the distribution's file, an optional user overlay marked "?", and
    # one entry per component that declares extra symbols.
    VAR = "TEST_ISABELLE_PATH_LIST"
    # Every case sets the variable to a non-empty value: unset or empty falls through
    # to `isabelle getenv` (empty means "not really set", as elsewhere in this module),
    # which is slow and asks about a variable Isabelle does not define. What these
    # exercise is the splitting.
    LIST_CASES = [
        ("single", "/isa/etc/symbols", ["/isa/etc/symbols"]),
        ("optional stripped", "/isa/etc/symbols:/home/u/.isabelle/etc/symbols?",
         ["/isa/etc/symbols", "/home/u/.isabelle/etc/symbols"]),
        ("component appended", "/isa/etc/symbols:/home/u/.isabelle/etc/symbols?:/c/symbols:/c/symbols-words",
         ["/isa/etc/symbols", "/home/u/.isabelle/etc/symbols", "/c/symbols", "/c/symbols-words"]),
        ("bare ? dropped", "/isa/etc/symbols:?", ["/isa/etc/symbols"]),
        ("empty segments dropped", ":/isa/etc/symbols::", ["/isa/etc/symbols"]),
    ]
    saved = os.environ.pop(VAR, None)
    try:
        for label, value, expected in LIST_CASES:
            os.environ[VAR] = value
            check(label, resolve_isabelle_path_list(VAR), expected)
    finally:
        os.environ.pop(VAR, None)
        if saved is not None:
            os.environ[VAR] = saved

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
