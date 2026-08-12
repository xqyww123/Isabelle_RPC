(*
  Regression tests for the universal key's constituent theories
  (BUG_UNIVERSAL_KEY_SHORT_NAME.md, fix plan §A.9).

  Sibling theories are begun programmatically so that the process holds several
  DIFFERENT theories with the SAME base name `Foo` -- the situation the AFP puts
  1,652 of its 10,614 theories in, and the one the defect could not tell apart.
  Each declares a type `t` and a constant `c`, so all carry the internal names
  `Foo.t` and `Foo.c`.

  Everything here stays inside those WIP theories: their hashes are FNV of their
  long names (theory_hash.ML), so no test here needs the Python RPC host that
  Theory_Hash.hash_of uses for loaded theories.  Test_Cache_Scope covers what
  cannot be reached without one.
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

(* 3. The answer comes from the name space, not from the reading context.  In every
      check above the reading theory IS the declaring theory, so the empty-name
      fallback (default_thy_long_name) would return the asserted string too.  Read
      A's constant from a theory that merely imports A and the two answers part. *)
val thy_a2 = Theory.begin_theory ("UK_Test_A2.Bar", Position.none) [thy_a]
val _ =
  check "A's constituents follow the reading context rather than the name space"
    (names_of thy_a2 const_a = ["UK_Test_A.Foo"])

(* 4. Order independence.  Two cones untouched so far, read youngest first: a memo
      keyed on anything but the cone would answer with whichever was read first. *)
val (thy_c, const_c) = mk_foo "UK_Test_C.Foo"
val (thy_d, const_d) = mk_foo "UK_Test_D.Foo"
val _ =
  check "the answers depend on the order the cones are read in"
    (names_of thy_d const_d = ["UK_Test_D.Foo"] andalso
     names_of thy_c const_c = ["UK_Test_C.Foo"])

(* 5. Exactness: no name was left out of the XOR, and no entry fell back to the
      reading context's own theory. *)
val _ =
  check "the computation was not exact over the fixture"
    (forall (fn r => #skipped r = 0 andalso not (#empty_name_fallback r))
       [report_of thy_a const_a, report_of thy_b const_b,
        report_of thy_a2 const_a])

(* 6. The cache scope.  A joins this theory's pair and claims the base name `Foo`;
      B then finds `Foo` claimed by a different long name and must fork.  A2 adds
      only the unclaimed base name `Bar`, so it stays on A's pair.  That the
      theories were begun at all is the termination test: a fork returns SOME, so
      Theory.apply_wrappers re-runs the hook, and the loop stops only because the
      re-application finds the whole cone already accounted for. *)
val _ =
  check "the cache scope is not observable"
    (is_some (Universal_Key.cache_scope_id \<^theory>))
val _ =
  check "A did not join this theory's pair"
    (Universal_Key.cache_scope_id thy_a = Universal_Key.cache_scope_id \<^theory>)
val _ =
  check "B did not fork the cache off A"
    (Universal_Key.cache_scope_id thy_b <> Universal_Key.cache_scope_id thy_a)
val _ =
  check "A2 forked although it collides with nothing"
    (Universal_Key.cache_scope_id thy_a2 = Universal_Key.cache_scope_id thy_a)

in
val _ = writeln "Test_Universal_Key: all checks passed"
end
\<close>

end
