(*
  RPC_Pretty.print_term rebuilds the display text from the inner-syntax XML, so it
  depends on the exact markup Isabelle emits.  Every constant of Main must print.
  Isabelle2026 nests one entity element per position of a name's history, so a
  constant made by a locale interpretation (sum.F) is marked up as nested entity
  elements; it must still print as that constant, typed the way print_term types a
  constant whose type variables no term variable pins.
*)
theory Test_Print_Term
  imports Main Isabelle_RPC.Remote_Procedure_Calling
begin

ML \<open>
local
fun assert msg b = if b then () else error ("Test_Print_Term: " ^ msg)

val cfg : RPC_Pretty.printing_config =
  {all_typ = false, bv_typ = false, constant_typ = false, free_typ = false,
   num_typ = false, sorting = false, show_type_P = NONE, show_sort_P = NONE}
val print = RPC_Pretty.print_term cfg \<^context>
val consts = Sign.consts_of \<^theory>
fun const c = Const (c, Consts.type_scheme consts c)

val failed = filter_out (can (print o const)) (Name_Space.get_names (Consts.space_of consts))
val sum_F = print (const \<^const_abbrev>\<open>sum.F\<close>)
in
val _ = assert ("constants that do not print: " ^ commas_quote failed) (null failed)
val _ = assert ("a constant with two positions prints as that constant, not " ^ quote sum_F)
  (String.isPrefix "(sum.F :: " sum_F)
end
\<close>

end
