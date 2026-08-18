import sys, io, timeit, re
sys.path.insert(0, "/home/qiyuan/Current/MLML/contrib/Isabelle_RPC")
from Isabelle_RPC_Host.unicode import pretty_unicode
from sweep import pretty_unicode_indexed
NEEDS = re.compile(r'\\<|[⇩⇧❙]')
def guarded(s):
    if not NEEDS.search(s):
        return s, list(range(len(s)+1))
    return pretty_unicode_indexed(s)
short = r"\<forall>x. P x \<Longrightarrow> \<exists>y. Q y\<^sub>1"
plain = "lemma foo: \"x = y\" by simp" * 4
big = io.open("/home/qiyuan/Current/MLML/contrib/phi-system/Phi_System/Resource_Template.thy", encoding="utf-8").read()
for label, s, n in (("short goal string", short, 20000), ("plain ASCII", plain, 20000), ("35k-char thy", big, 20)):
    a = timeit.timeit(lambda: pretty_unicode(s), number=n)
    c = timeit.timeit(lambda: guarded(s), number=n)
    print(f"{label:18s} regex {a/n*1e6:8.1f} us   guarded symbol-driven {c/n*1e6:8.1f} us   ratio {c/a:.1f}x")
