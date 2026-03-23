(*
  Context entity enumeration callbacks.

  Each callback generator captures a Context.generic and returns a callback
  that takes (target_theory: string option, the_theory_only: bool, exclude: string list):

  - target_theory: if SOME, resolve that long theory name and enumerate entities
    from its context; if NONE, use the captured context.
  - the_theory_only: if true, return only entities defined in the target theory
    itself; otherwise all entities from the target theory and its ancestors.
    The exclude list is ignored in this case.
  - exclude: long theory names (e.g. "HOL.List") whose entities to exclude.
*)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

val arg_schema = unpackTuple3 (unpackOption unpackString, unpackBool, unpackList unpackString)

fun resolve_ctx context target_thy_opt =
  case target_thy_opt of
    NONE => context
  | SOME name => Context.Theory (Theory_Hash.resolve_theory context name)

fun is_hidden space name =
  Long_Name.is_hidden (Name_Space.intern space name)

fun ns_filter key_of space target_name exclude_set =
  Name_Space.get_names space |> map_filter (fn name =>
    if Name_Space.is_concealed space name orelse is_hidden space name then NONE
    else (let val entry = Name_Space.the_entry space name
              val thy_name = #theory_long_name entry
          in case exclude_set of
               NONE => if thy_name = target_name then SOME (key_of name) else NONE
             | SOME es => if Strhashtab.defined es thy_name then NONE
                          else SOME (key_of name)
          end) handle ERROR _ => NONE)

fun make_constants_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.constants",
    arg_schema = arg_schema,
    ret_schema = packList Universal_Key.pack_universal_key,
    function = fn (target_thy_opt, the_theory_only, exclude) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = Universal_Key.key_of_constant ctx
        val space = Consts.space_of (Context.cases Sign.consts_of Proof_Context.consts_of ctx)
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
      in ns_filter key_of space target_name exclude_set end,
    timeout = NONE
  }

fun make_theorems_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.theorems",
    arg_schema = arg_schema,
    ret_schema = packList Universal_Key.pack_universal_key,
    function = fn (target_thy_opt, the_theory_only, exclude) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val thy = Context.theory_of ctx
        val target_name = Context.theory_long_name thy
        val ctxt = Context.cases Proof_Context.init_global I ctx
        val facts = Proof_Context.facts_of ctxt
        val fact_space = Facts.space_of facts
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set   exclude)
      in Facts.dest_static false [] facts
         |> maps (fn (name, thms) =>
           if Name_Space.is_concealed fact_space name
              orelse is_hidden fact_space name then []
           else
           let val dominated = case try (Name_Space.the_entry fact_space) name of
                   SOME e =>
                     (case exclude_set of
                        NONE => #theory_long_name e <> target_name
                      | SOME es => Strhashtab.defined es (#theory_long_name e))
                 | NONE => the_theory_only
           in if dominated then []
              else map (fn thm => Universal_Key.key_of_theorem' ctx
                                    (Thm.transfer thy thm)) thms
           end)
      end,
    timeout = NONE
  }

fun make_types_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.types",
    arg_schema = arg_schema,
    ret_schema = packList Universal_Key.pack_universal_key,
    function = fn (target_thy_opt, the_theory_only, exclude) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = Universal_Key.key_of_type ctx
        val space = Context.cases Sign.type_space Proof_Context.type_space ctx
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
      in ns_filter key_of space target_name exclude_set end,
    timeout = NONE
  }

fun make_classes_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.classes",
    arg_schema = arg_schema,
    ret_schema = packList Universal_Key.pack_universal_key,
    function = fn (target_thy_opt, the_theory_only, exclude) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = Universal_Key.key_of_class ctx
        val space = Context.cases Sign.class_space Proof_Context.class_space ctx
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
      in ns_filter key_of space target_name exclude_set end,
    timeout = NONE
  }

fun make_locales_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.locales",
    arg_schema = arg_schema,
    ret_schema = packList Universal_Key.pack_universal_key,
    function = fn (target_thy_opt, the_theory_only, exclude) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = Universal_Key.key_of_locale ctx
        val space = Locale.locale_space (Context.theory_of ctx)
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
      in ns_filter key_of space target_name exclude_set end,
    timeout = NONE
  }

fun make_theory_long_name_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  let val name = Context.theory_long_name (Context.theory_of context)
  in
    Remote_Procedure_Calling.mk_callback {
      name = "Context.theory_long_name",
      arg_schema = unpackUnit,
      ret_schema = packString,
      function = fn () => name,
      timeout = NONE
    }
  end

end
