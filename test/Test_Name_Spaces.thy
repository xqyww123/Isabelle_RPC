(*
  The two measurements the fix plan (§A.9) requires to be re-derived rather than
  quoted.  Both are pinned as assertions: batch output is not shown by
  `isabelle build`, so a number that is only printed is a number nobody reads.
*)
theory Test_Name_Spaces
  imports Isabelle_RPC.Remote_Procedure_Calling "HOL-Library.Multiset"
begin

ML \<open>
local

val context = Context.Theory \<^theory>

(* 1. hash_of_long prefers Thy_Info's registry; key_of_ns_entity keeps using
      resolve_theory.  Over Main's cone the two must name the same theory value —
      if they ever did not, one long name would carry two content hashes.
      Measured 2026-08-12: 99 theories, 0 disagreements. *)
val main_cone = Theory.nodes_of \<^theory>\<open>Main\<close> |> map Context.theory_long_name

val disagreements =
  filter (fn long =>
    case Thy_Info.lookup_theory long of
      NONE => true
    | SOME thy =>
        Context.theory_identifier thy
          <> Context.theory_identifier (Theory_Hash.resolve_theory context long))
  main_cone

val _ =
  if null disagreements then ()
  else error ("Test_Name_Spaces: Thy_Info and resolve_theory disagree on " ^
              string_of_int (length disagreements) ^ " of " ^
              string_of_int (length main_cone) ^ " theories of Main's cone: " ^
              commas_quote disagreements)

(* 2. compute_constituents keeps one `seen` table per name space.  A single shared
      table would be wrong for any name carried by both spaces: whichever the walk
      met first would suppress the other.  Measured 2026-08-12 over
      HOL-Library.Multiset: Quickcheck_Exhaustive.unknown, Product_Type.prod,
      Sum_Type.sum, Int.int. *)
val multiset = \<^theory>\<open>Multiset\<close>
val shared =
  inter (op =)
    (Name_Space.get_names (Consts.space_of (Sign.consts_of multiset)))
    (Name_Space.get_names (Sign.type_space multiset))

val _ =
  if length shared = 4 then ()
  else error ("Test_Name_Spaces: " ^ string_of_int (length shared) ^
              " names are carried by both the constant and the type space of " ^
              "HOL-Library.Multiset, not the 4 measured: " ^ commas_quote shared)

in
val _ = writeln "Test_Name_Spaces: all checks passed"
end
\<close>

end
