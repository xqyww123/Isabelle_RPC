(*
  The one test of the constituents cache's contents (fix plan §A.6, acceptance
  item 5): a fork must not let the forking theory read the entries the colliding
  theory wrote.

  Kept apart from Test_Universal_Key because it cannot avoid the Python RPC host.
  The cache is only written by thm_constituents, which needs a thm; a thm's
  proposition has type `prop`, which Pure declares; and Theory_Hash.hash_of takes
  its RPC branch for any loaded theory, Pure included.  There is no proposition
  that avoids Pure.
*)
theory Test_Cache_Scope
  imports Isabelle_RPC.Remote_Procedure_Calling
begin

ML \<open>
local

fun check msg b = if b then () else error ("Test_Cache_Scope: " ^ msg)

(* A sibling theory with base name Foo, declaring the constant Foo.c :: prop.
   Both siblings therefore carry the SAME internal name and the SAME thm128. *)
fun mk_foo long_name =
  let
    val thy0 = Theory.begin_theory (long_name, Position.none) [\<^theory>]
    val (const, thy1) =
      Sign.declare_const_global ((Binding.name "c", propT), NoSyn) thy0
  in (thy1, const) end

fun constituents_of_const thy const =
  map #1 (#2 (Universal_Key.thm_constituents (Context.Theory thy)
                (Thm.assume (Thm.global_cterm_of thy const))))

val (thy_a, const_a) = mk_foo "UK_Cache_A.Foo"
val names_a = constituents_of_const thy_a const_a          (* writes the cache entry *)

val _ =
  check "A's constituents do not name A"
    (member (op =) names_a "UK_Cache_A.Foo")

(* Beginning B collides on the base name Foo and forks.  The entry A just wrote
   names a theory of base name Foo, so the purge must drop it. *)
val (thy_b, const_b) = mk_foo "UK_Cache_B.Foo"
val _ =
  check "B did not fork the cache off A"
    (Universal_Key.cache_scope_id thy_b <> Universal_Key.cache_scope_id thy_a)

val names_b = constituents_of_const thy_b const_b

val _ =
  check "B read A's cached constituents back -- the fork did not purge the entry"
    (not (member (op =) names_b "UK_Cache_A.Foo"))
val _ =
  check "B's constituents do not name B"
    (member (op =) names_b "UK_Cache_B.Foo")

(* The entry that survives a purge must be the one naming no colliding theory:
   Pure is a constituent of both propositions and its base name is not Foo. *)
val _ =
  check "Pure is not a constituent of either proposition"
    (member (op =) names_a "Pure" andalso member (op =) names_b "Pure")

(* And the RPC branch really did run: a persistent hash is xxhash128 of the file,
   computed by the Python host.  If this ever reports false, the test has quietly
   stopped covering the branch every AFP theory takes. *)
val _ =
  check "Pure was hashed by the WIP branch, so no RPC round trip happened"
    (Theory_Hash.is_persistent (Theory_Hash.hash_of \<^theory>\<open>Pure\<close>))

in
val _ = writeln "Test_Cache_Scope: all checks passed"
end
\<close>

end
