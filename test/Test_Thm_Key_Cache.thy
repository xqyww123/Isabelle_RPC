(*
  The cache of theorem keys by proposition (thm_uk_cache): propositions are matched
  exactly, bound-variable names included, as term128 hashes them, so an
  alpha-variant keeps a key of its own; a theorem key and a rule key of one
  proposition are kept apart by their tag.

  Kept apart from Test_Universal_Key because it needs Performant_Isabelle_ML's
  native library: keying a theorem reads the hashes of its theories, Pure's
  included (see Test_Cache_Scope).
*)
theory Test_Thm_Key_Cache
  imports Isabelle_RPC.Remote_Procedure_Calling
begin

ML \<open>
local

fun check msg b = if b then () else error ("Test_Thm_Key_Cache: " ^ msg)

val thy = \<^theory>
val context = Context.Theory thy
fun reflexive t = Thm.reflexive (Thm.global_cterm_of thy t)
val th_x = reflexive (Abs ("x", propT, Bound 0))
val th_y = reflexive (Abs ("y", propT, Bound 0))
val key = Universal_Key.key_of_theorem' NONE context

val _ =
  check "the two theorems are alpha-variants with keys of their own"
    (Thm.prop_of th_x aconv Thm.prop_of th_y andalso key th_x <> key th_y)

val cached = Universal_Key.key_of_theorem' (SOME (Universal_Key.new_thm_uk_cache ())) context
val kx = cached th_x
val ky = cached th_y
val _ =
  check "in one cache, each gets its own key, its uncached key"
    (kx = key th_x andalso ky = key th_y)
val _ = check "a repeated look-up returns the theorem's own key" (cached th_y = key th_y)

val cache = SOME (Universal_Key.new_thm_uk_cache ())
val k = Universal_Key.key_of_theorem' cache context th_x
val r = Universal_Key.key_of_introduction_rule' cache context th_x
val _ =
  check "a rule key of the same proposition is an entry of its own"
    (r = Universal_Key.retag_thm_key k 0wx12)

in end
\<close>

end
