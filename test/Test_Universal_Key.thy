(*
  Regression tests for the universal key's constituent theories
  (BUG_UNIVERSAL_KEY_SHORT_NAME.md, fix plan §A.9).

  Two sibling theories are begun programmatically so that the process holds two
  DIFFERENT theories with the SAME base name `Foo` -- the situation the AFP puts
  1,652 of its 10,614 theories in, and the one the defect could not tell apart.
  Each declares a type `t` and a constant `c`, so both carry the internal names
  `Foo.t` and `Foo.c`.

  Everything here stays inside those two WIP theories: their hashes are FNV of
  their long names (theory_hash.ML), so no test needs the Python RPC host that
  Theory_Hash.hash_of uses for loaded theories.
*)
theory Test_Universal_Key
  imports Isabelle_RPC.Remote_Procedure_Calling
begin

ML \<open>
local

fun fail msg = error ("Test_Universal_Key: " ^ msg)
fun check msg b = if b then () else fail msg

(* A sibling theory with base name Foo, declaring Foo.t and Foo.c. *)
fun mk_foo long_name =
  let
    val thy0 = Theory.begin_theory (long_name, Position.none) [\<^theory>]
    val thy1 = Sign.add_types_global [(Binding.name "t", 0, NoSyn)] thy0
    val (const, thy2) =
      Sign.declare_const_global
        ((Binding.name "c", Term.Type (Sign.full_name thy1 (Binding.name "t"), [])), NoSyn) thy1
  in (thy2, const) end

val (thy_a, const_a) = mk_foo "UK_Test_A.Foo"
val (thy_b, const_b) = mk_foo "UK_Test_B.Foo"

fun names_of thy t = map #1 (#2 (Universal_Key.compute_constituents (Context.Theory thy) t))
fun report_of thy t = #3 (Universal_Key.compute_constituents (Context.Theory thy) t)
fun prefix_of thy t = #1 (Universal_Key.compute_constituents (Context.Theory thy) t)

(* The internal names really do collide -- without this the rest proves nothing. *)
val _ =
  check "the two theories do not share the constant's internal name"
    (case (const_a, const_b) of
       (Const (na, _), Const (nb, _)) => na = nb andalso na = "Foo.c"
     | _ => false)

(* 1. Regression.  A's cone is read first, which under the old code pinned the base
      name `Foo` to UK_Test_A.Foo for the whole process; B's constituents then came
      back naming A.  Each context must now name its own theory. *)
val _ = check "A's constituents are not UK_Test_A.Foo" (names_of thy_a const_a = ["UK_Test_A.Foo"])
val _ = check "B's constituents are not UK_Test_B.Foo" (names_of thy_b const_b = ["UK_Test_B.Foo"])

(* 2. The two prefixes differ, so the two theories' analogous facts get different keys. *)
val _ =
  check "the two theories produce the same XOR prefix"
    (prefix_of thy_a const_a <> prefix_of thy_b const_b)

(* 3. Order independence: reading B first and A second gives the same answers. *)
val _ =
  check "the answers depend on the order the two cones are read in"
    (names_of thy_b const_b = ["UK_Test_B.Foo"] andalso
     names_of thy_a const_a = ["UK_Test_A.Foo"])

(* 4. Exactness: no name was left out of the XOR, and no entry fell back to the
      reading context's own theory. *)
val _ =
  check "the computation was not exact over the fixture"
    (forall (fn r => #skipped r = 0 andalso not (#empty_name_fallback r))
       [report_of thy_a const_a, report_of thy_b const_b])

(* 5. The cache scope.  Both theories inherit this one's pair; A claims the base
      name `Foo`, so B must fork rather than share a cache whose keys cannot tell
      Foo.c-in-A from Foo.c-in-B.  That the theories were begun at all is the
      termination test: the at_begin hook returns SOME on its first pass, so
      Theory.apply_wrappers re-runs it, and only the "this claim is mine" test
      stops the loop. *)
val _ =
  check "the cache scope is not observable"
    (is_some (Universal_Key.cache_scope_id \<^theory>))
val _ =
  check "B did not fork the cache off A"
    (Universal_Key.cache_scope_id thy_a <> Universal_Key.cache_scope_id thy_b)
val _ =
  check "A did not inherit this theory's cache"
    (Universal_Key.cache_scope_id thy_a = Universal_Key.cache_scope_id \<^theory>)

in
val _ = writeln "Test_Universal_Key: all checks passed"
end
\<close>

end
