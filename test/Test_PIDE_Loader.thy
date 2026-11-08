theory Test_PIDE_Loader
  imports Isabelle_RPC.Remote_Procedure_Calling
begin

ML \<open>
fun assert_pide_loader b msg = if b then () else error ("Test_PIDE_Loader: " ^ msg)
\<close>

text \<open>Without a PIDE_Loader (a batch build): the lookups cover the heap only, an import
  list of heap theories is answered in ML, any other import fails naming the requirement.\<close>

ML \<open>
val _ = assert_pide_loader (PIDE_Loader.defined_theory "Main") "Main is defined"
val _ =
  assert_pide_loader (Context.theory_long_name (PIDE_Loader.get_theory "HOL.List") = "HOL.List")
    "get_theory HOL.List"
val _ = assert_pide_loader (is_none (PIDE_Loader.lookup_theory "Draft.No_Such_Theory"))
  "an unknown name is not found"
val _ = assert_pide_loader (PIDE_Loader.all_theories () = Build.all_theories ())
  "all_theories = the heap's"
val _ =
  assert_pide_loader
    (map Context.theory_long_name
      (PIDE_Loader.use_theories "HOL" Path.root ["Main", "HOL.List", "List"]) =
     ["Main", "HOL.List", "HOL.List"])
    "heap imports, in request order"
val _ = assert_pide_loader (null (PIDE_Loader.use_theories "HOL" Path.root [])) "no imports"
val _ =
  (PIDE_Loader.use_theories "HOL" Path.root ["Main", "No_Such_Theory"];
   assert_pide_loader false "a non-heap import must fail")
  handle ERROR msg =>
    assert_pide_loader (String.isSubstring "PIDE_Loader.Session" msg)
      ("the error names the requirement: " ^ msg)
\<close>

text \<open>T13: theory options of a theory begun with init_theory apply to that theory only.\<close>

ML \<open>
local
  val default = Options.default_bool "quick_and_dirty"
  val opts =
    [(("quick_and_dirty", Position.none), SOME (Value.print_bool (not default), Position.none))]
  fun quick_and_dirty thy =
    PIDE_Loader.with_theory_options (fn _ => Options.default_bool "quick_and_dirty")
      (Toplevel.make_state (SOME (Context.Theory thy)))
  val name = "Isabelle_RPC_Test.T13"

  val thy0 = Theory.begin_theory (name, Position.none) [\<^theory>]
  val {skip_theory, theory = thy1} = PIDE_Loader.init_theory opts thy0 ()
  val _ = assert_pide_loader (not skip_theory) "step 1: not skipped"
  val _ = assert_pide_loader (quick_and_dirty thy1 = not default) "step 1: the option applies"
  val _ =
    assert_pide_loader (Options.default_bool "quick_and_dirty" = default)
      "step 1: outside the theory the default holds"

  val parent = Theory.end_theory thy1
  val child = Theory.begin_theory (name ^ "_Child", Position.none) [parent]
  val _ =
    assert_pide_loader (quick_and_dirty child = default) "step 2: a child sees no options"

  val same = Theory.begin_theory (name, Position.none) [parent]
  val {theory = same1, ...} = PIDE_Loader.init_theory [] same ()
  val _ =
    assert_pide_loader (quick_and_dirty same1 = default)
      "step 3: a child of the same long name started with [] sees none"
in end
\<close>

end
