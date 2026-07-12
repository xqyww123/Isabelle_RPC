#!/usr/bin/env python3
"""Tests for Isabelle_RPC_Host.paths — run with `python3 test_paths.py`.

The Windows branch is exercised by flipping `os.name`, which is enough because the
/cygdrive rule is pure string handling: it never touches `os.path` (that is exactly
why it survives a non-ASCII user name, and why it is reachable from a Linux test).
"""

import os
import sys

from Isabelle_RPC_Host.paths import platform_path

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
    print("== non-Windows: platform_path is a no-op ==")
    assert os.name != "nt", "this section assumes the test host is not Windows"
    for label, value, _ in CYGDRIVE_CASES:
        check(f"no-op {label}", platform_path(value), value)
    for label, value in NON_POSIX_CASES:
        check(f"no-op {label}", platform_path(value), value)
        check_idempotent(label, value)

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

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
