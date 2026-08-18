import sys
sys.path.insert(0, "/tmp/claude-1002/-home-qiyuan-Current-MLML/191c16f2-3fa2-4e2b-b337-d141aea09fc8/scratchpad/fixrev_diagnosis")
from ref import compare, reference_offsets
from Isabelle_RPC_Host.unicode import pretty_unicode
from Isabelle_RPC_Host.position import symbol_explode, FileIndex

CASES = [
    ("private-use symbol",              r"a\<proc>b"),
    ("private-use symbol 2",            r"a\<transforms>b"),
    ("ordinary component symbol",       r"a\<big_ast>b"),
    ("plain distribution symbol",       r"a\<Rightarrow>b"),
    ("foldable subscript, escape",      r"x\<^sub>i"),
    ("foldable subscript, raw",         "x⇩i"),
    ("subscript no fold entry",         r"x\<^sub>Q"),
    ("bold with fold",                  r"\<^bold>a"),
    ("bold without fold",               r"\<^bold>1"),
    ("two markers in a row",            r"\<^sub>\<^sub>1"),
    ("two markers raw",                 "⇩⇩1"),
    ("sub then sup",                    r"\<^sub>\<^sup>1"),
    ("three markers",                   r"\<^sub>\<^sub>\<^sub>1"),
    ("marker + multi-char render",      r"\<^sub>\<nosuchsymbolhere>"),
    ("marker + private-use",            r"\<^sub>\<proc>"),
    ("marker at end of input",          r"x\<^sub>"),
    ("marker at end of line",           "x\\<^sub>\n1"),
    ("marker then newline raw",         "x⇩\n1"),
    ("unterminated escape",             r"a\<alpha b"),
    ("malformed escape swallow",        r"\<alpha \<beta>"),
    ("empty escape",                    r"a\<>b"),
    ("caret only",                      r"a\<^>b"),
    ("double caret",                    r"a\<^^a>b"),
    ("CRLF",                            "line1\r\nx\\<^sub>i\r\n"),
    ("bare CR",                         "a\rb"),
    ("private-use at line start",       "\\<proc> foo\nbar"),
]

for name, src in CASES:
    idx, fin, ref, bad = compare(src)
    status = "OK " if not bad else "BAD"
    print(f"[{status}] {name}")
    print(f"      src      = {src!r}")
    print(f"      rendered = {fin!r}")
    print(f"      symbols  = {symbol_explode(idx.source)}")
    print(f"      FileIndex= {list(idx.sym_unicode_offsets)}")
    print(f"      reference= {ref}")
    if bad:
        print(f"      diffs (sym_idx, fileindex, reference) = {bad}")
    print()
