(*
  Context entity enumeration callbacks.

  Each callback generator captures a Context.generic and returns a callback
  that, when called with no argument, returns the list of universal keys
  for all entities of that kind available in the context.
*)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

fun make_constants_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  let
    val key_of = Universal_Key.key_of_constant context
    val space = Consts.space_of (Context.cases Sign.consts_of Proof_Context.consts_of context)
  in
    Remote_Procedure_Calling.mk_callback {
      name = "Context.constants",
      arg_schema = unpackUnit,
      ret_schema = packList Universal_Key.pack_universal_key,
      function = fn () => Name_Space.get_names space |> map key_of,
      timeout = NONE
    }
  end

fun make_theorems_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  let
    val thy = Context.theory_of context
    val ctxt = Context.cases Proof_Context.init_global I context
    val facts = Proof_Context.facts_of ctxt
  in
    Remote_Procedure_Calling.mk_callback {
      name = "Context.theorems",
      arg_schema = unpackUnit,
      ret_schema = packList Universal_Key.pack_universal_key,
      function = fn () =>
        Facts.dest_static false [] facts
        |> maps (fn (_, thms) =>
          map (fn thm => Universal_Key.key_of_theorem' context
                           (Thm.transfer thy thm)) thms),
      timeout = NONE
    }
  end

fun make_types_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  let
    val key_of = Universal_Key.key_of_type context
    val space = Context.cases Sign.type_space Proof_Context.type_space context
  in
    Remote_Procedure_Calling.mk_callback {
      name = "Context.types",
      arg_schema = unpackUnit,
      ret_schema = packList Universal_Key.pack_universal_key,
      function = fn () => Name_Space.get_names space |> map key_of,
      timeout = NONE
    }
  end

fun make_classes_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  let
    val key_of = Universal_Key.key_of_class context
    val space = Context.cases Sign.class_space Proof_Context.class_space context
  in
    Remote_Procedure_Calling.mk_callback {
      name = "Context.classes",
      arg_schema = unpackUnit,
      ret_schema = packList Universal_Key.pack_universal_key,
      function = fn () => Name_Space.get_names space |> map key_of,
      timeout = NONE
    }
  end

fun make_locales_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  let
    val key_of = Universal_Key.key_of_locale context
    val space = Locale.locale_space (Context.theory_of context)
  in
    Remote_Procedure_Calling.mk_callback {
      name = "Context.locales",
      arg_schema = unpackUnit,
      ret_schema = packList Universal_Key.pack_universal_key,
      function = fn () => Name_Space.get_names space |> map key_of,
      timeout = NONE
    }
  end

end
