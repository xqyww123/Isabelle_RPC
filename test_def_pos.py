#!/usr/bin/env python3
"""Tests for IsabellePosition.from_def_pos, the decoder of ML's
Context_Callbacks.def_pos triple (file, line, offset) -- run with
`python3 test_def_pos.py`.
"""

import sys

from Isabelle_RPC_Host.position import IsabellePosition

FAILURES = []


def check(label, actual, expected):
    if actual == expected:
        print(f"  ok   {label}: {actual!r}")
    else:
        print(f"  FAIL {label}: got {actual!r}, expected {expected!r}")
        FAILURES.append(label)


def main():
    check("unknown", IsabellePosition.from_def_pos(("", 0, 0)), None)
    check("no offset", IsabellePosition.from_def_pos(("/a/T.thy", 7, 0)), None)
    check("no file", IsabellePosition.from_def_pos(("", 7, 120)), None)
    check("known", IsabellePosition.from_def_pos(("/a/T.thy", 7, 120)),
          IsabellePosition(7, 120, "/a/T.thy"))
    check("msgpack list", IsabellePosition.from_def_pos(["/a/T.thy", 7, 120]),
          IsabellePosition(7, 120, "/a/T.thy"))
    if FAILURES:
        print(f"{len(FAILURES)} failed: {FAILURES}")
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
