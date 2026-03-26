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

  An optional filter parameter allows callers to further restrict which entities
  are returned, applied after exclude_set/target_thy/the_theory_only filtering.
*)

signature CONTEXT_CALLBACKS = sig
  val make_constants_callback : (string -> bool) option -> Context.generic -> Remote_Procedure_Calling.callback'
  val make_theorems_callback : (string * thm -> bool) option -> Context.generic -> Remote_Procedure_Calling.callback'
  val make_types_callback : (string -> bool) option -> Context.generic -> Remote_Procedure_Calling.callback'
  val make_classes_callback : (string -> bool) option -> Context.generic -> Remote_Procedure_Calling.callback'
  val make_locales_callback : (string -> bool) option -> Context.generic -> Remote_Procedure_Calling.callback'
  val make_theory_long_name_callback : Context.generic -> Remote_Procedure_Calling.callback'
  val make_theory_long_name_and_path_callback : Context.generic -> Remote_Procedure_Calling.callback'
  (* The thm list extractor is supplied by the caller because Classical requires HOL,
     which is not available in this Pure-level file. *)
  val make_introduction_rules_callback :
    (Context.generic -> thm list) -> (string * thm -> bool) option ->
    Context.generic -> Remote_Procedure_Calling.callback'
  val make_elimination_rules_callback :
    (Context.generic -> thm list) -> (string * thm -> bool) option ->
    Context.generic -> Remote_Procedure_Calling.callback'
end

structure Context_Callbacks : CONTEXT_CALLBACKS = struct

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

val arg_schema = unpackTuple3 (unpackOption unpackString, unpackBool, unpackList unpackString)

fun resolve_ctx context target_thy_opt =
  case target_thy_opt of
    NONE => context
  | SOME name => Context.Theory (Theory_Hash.resolve_theory context name)

(* Debug: return (key, name) pairs instead of just keys.
   Uncomment pack_key_name, dedup_key_names, and the SOME(..., name) lines below,
   and change ret_schema to packList pack_key_name.
val pack_key_name = packPair (Universal_Key.pack_universal_key, packString)
fun dedup_key_names pairs =
  let val seen = Bytehashtab.empty (length pairs)
  in map_filter (fn (k, name) =>
      if Bytehashtab.defined seen k then NONE
      else (Bytehashtab.update seen (k, ()); SOME (k, name))) pairs
  end
*)

fun dedup_keys keys =
  let val seen = Bytehashtab.empty (length keys)
  in map_filter (fn k =>
      if Bytehashtab.defined seen k then NONE
      else (Bytehashtab.update seen (k, ()); SOME k)) keys
  end

fun ns_filter key_of space target_name exclude_set filter_opt =
  Name_Space.get_names space |> map_filter (fn name =>
    (let val entry = Name_Space.the_entry space name
     in if #concealed entry
           orelse Long_Name.is_hidden (Name_Space.intern space name) then NONE
        else
          let val thy_name = #theory_long_name entry
              val pass = case exclude_set of
                   NONE => thy_name = target_name
                 | SOME es => not (Strhashtab.defined es thy_name)
          in if not pass then NONE
             else case filter_opt of
                    NONE => SOME (key_of name)
                  | SOME f => if f name then SOME (key_of name) else NONE
          end
     end) handle ERROR _ => NONE)
  |> dedup_keys

fun make_constants_callback filter_opt (context : Context.generic)
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
      in ns_filter key_of space target_name exclude_set filter_opt end,
    timeout = NONE
  }

fun make_theorems_callback filter_opt (context : Context.generic)
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
        val facts = Context.cases Global_Theory.facts_of Proof_Context.facts_of ctx
        val fact_space = Facts.space_of facts
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
      in Facts.dest_static false [] facts
         |> maps (fn (name, thms) =>
           let val entry = try (Name_Space.the_entry fact_space) name
           in case entry of
                NONE => []
              | SOME e =>
                  if #concealed e
                     orelse Long_Name.is_hidden (Name_Space.intern fact_space name) then []
                  else
                  let val dominated = case exclude_set of
                           NONE => #theory_long_name e <> target_name
                         | SOME es => Strhashtab.defined es (#theory_long_name e)
                  in if dominated then []
                     else map_filter (fn thm =>
                       let val thm' = Thm.transfer thy thm
                       in case filter_opt of
                            NONE => SOME (Universal_Key.key_of_theorem' ctx thm')
                          | SOME f => if f (name, thm')
                                      then SOME (Universal_Key.key_of_theorem' ctx thm')
                                      else NONE
                       end) thms
                  end
           end)
         |> dedup_keys
      end,
    timeout = NONE
  }

fun make_types_callback filter_opt (context : Context.generic)
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
      in ns_filter key_of space target_name exclude_set filter_opt end,
    timeout = NONE
  }

fun make_classes_callback filter_opt (context : Context.generic)
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
      in ns_filter key_of space target_name exclude_set filter_opt end,
    timeout = NONE
  }

fun make_locales_callback filter_opt (context : Context.generic)
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
      in ns_filter key_of space target_name exclude_set filter_opt end,
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

fun make_theory_long_name_and_path_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  let
    fun theory_long_name_and_path name =
      let
        val thy = Theory_Hash.resolve_theory context name
        val thy_name = Context.theory_long_name thy
        val master_dir = Resources.master_directory thy
        val thy_base = Long_Name.base_name thy_name
        val thy_file = Path.ext "thy" (master_dir + Path.basic thy_base)
        val file_path = File.platform_path (File.full_path master_dir thy_file)
      in (thy_name, file_path) end
  in
    Remote_Procedure_Calling.mk_callback {
      name = "Context.theory_long_name_and_path",
      arg_schema = unpackString,
      ret_schema = packPair (packString, packString),
      function = theory_long_name_and_path,
      timeout = NONE
    }
  end

(* Introduction / elimination rule callbacks.
   The extract_thms function is provided by the caller (requires Classical from HOL). *)
local
fun make_rules_callback cb_name key_of extract_thms filter_opt (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = cb_name,
    arg_schema = arg_schema,
    ret_schema = packList Universal_Key.pack_universal_key,
    function = fn (target_thy_opt, the_theory_only, exclude) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val thy = Context.theory_of ctx
        val target_base = Context.theory_base_name thy
        val target_prefix = target_base ^ "."
        val thms = extract_thms ctx
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val seen : unit Strhashtab.table = Strhashtab.empty 128
      in
        map_filter (fn thm =>
          let val thm = Thm.transfer thy thm
              val name = Thm.derivation_name thm
          in if name = "" orelse Strhashtab.defined seen name then NONE
             else
               let
                 val thy_name_of = case Thm.derivation_id thm of
                     SOME {theory_name, ...} =>
                       if theory_name = "" then NONE else SOME theory_name
                   | NONE => NONE
                 val pass = case exclude_set of
                     NONE => String.isPrefix target_prefix name
                   | SOME es => (case thy_name_of of
                         SOME tn => not (Strhashtab.defined es tn)
                       | NONE => true)
               in if not pass then NONE
                  else (Strhashtab.update seen (name, ());
                        case filter_opt of
                          NONE => SOME (key_of ctx thm)
                        | SOME f => if f (name, thm) then SOME (key_of ctx thm)
                                    else NONE)
               end
          end) thms
        |> dedup_keys
      end,
    timeout = NONE
  }
in
fun make_introduction_rules_callback extract_thms =
  make_rules_callback "Context.introduction_rules"
    Universal_Key.key_of_introduction_rule' extract_thms
fun make_elimination_rules_callback extract_thms =
  make_rules_callback "Context.elimination_rules"
    Universal_Key.key_of_elimination_rule' extract_thms
end

end (*local*)

end
