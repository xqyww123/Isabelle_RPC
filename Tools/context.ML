(*
  Context entity enumeration callbacks.

  Each callback generator captures a Context.generic and returns a callback
  that takes:
    (target_theory: string option, the_theory_only: bool, exclude: string list,
     term_patterns: string list, type_patterns: string list,
     theories_include: string list, name_contains: string list, limit: int)

  - target_theory: if SOME, resolve that long theory name and enumerate entities
    from its context; if NONE, use the captured context.
  - the_theory_only: if true, return only entities defined in the target theory
    itself; otherwise all entities from the target theory and its ancestors.
    The exclude list is ignored in this case.
  - exclude: long theory names (e.g. "HOL.List") whose entities to exclude.
  - term_patterns: Isabelle term pattern strings. Empty = no restriction.
    All patterns must match (conjunction). Uses higher-order pattern matching
    via matches_subterm on entity propositions. Only applicable to thm-like entities.
  - type_patterns: Isabelle type pattern strings. Empty = no restriction.
    All patterns must match (conjunction). Uses Sign.typ_instance on subtypes.
    Applicable to thm-like entities (types in proposition) and constants (constant type).
  - theories_include: theory names (short or fully qualified). Empty = no restriction.
    If non-empty, only return entities defined in these theories.
  - name_contains: case-insensitive substrings. Empty = no restriction.
    All substrings must match (conjunction).
  - limit: maximum number of results. <0 means no limit.

  An optional filter parameter allows callers to further restrict which entities
  are returned, applied after exclude_set/target_thy/the_theory_only filtering.
*)

signature CONTEXT_CALLBACKS = sig
  (* Definition position: (file_path, line, symbol_offset).
     file_path is the standardized absolute path (empty string if unknown).
     line is the 1-based line number (0 if unknown).
     symbol_offset is the Isabelle symbol offset from file start (0 if unknown). *)
  type def_pos = string * int * int

  (* Cached theorem entry: pre-computed at theory-load time, used to skip
     entry_lookup / infra_filter / key_compute at query time. *)
  type cached_thm_entry = {
    uk: Universal_Key.universal_key,
    name: string,
    thy_name: string,
    pos: def_pos,
    thm: thm
  }

  (* Exported utilities for building caches externally *)
  val entry_def_pos : {pos: Position.T, serial: serial, group: serial,
    suppress: bool list, theory_long_name: string, concealed: bool} -> def_pos
  val parse_patterns : Context.generic -> string list * string list -> term list * typ list * string list
  val mk_name_filter : string list -> string -> bool
  val mk_prop_pattern_matcher : Proof.context -> term list -> typ list -> term -> bool

  val make_constants_callback : (string -> bool) option -> Context.generic -> Remote_Procedure_Calling.callback'
  (* cache_opt: when SOME (entries, facts), uses cached entries for global theorems
     and only runs the full pipeline on facts not in the cached Facts.T. *)
  val make_theorems_callback :
    (string * thm -> bool) option ->
    (cached_thm_entry list * Facts.T) option ->
    Context.generic -> Remote_Procedure_Calling.callback'
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
  val make_induction_rules_callback :
    (Context.generic -> thm list) -> (string * thm -> bool) option ->
    Context.generic -> Remote_Procedure_Calling.callback'
  val make_case_split_rules_callback :
    (Context.generic -> thm list) -> (string * thm -> bool) option ->
    Context.generic -> Remote_Procedure_Calling.callback'
end

structure Context_Callbacks : CONTEXT_CALLBACKS = struct

type def_pos = string * int * int

type cached_thm_entry = {
  uk: Universal_Key.universal_key,
  name: string,
  thy_name: string,
  pos: def_pos,
  thm: thm
}


(* Extract definition position (file, line, symbol_offset) from a Name_Space entry.
   File paths are expanded (e.g. ~~/src/HOL/HOL.thy → /path/to/Isabelle/src/HOL/HOL.thy).
   Returns ("", 0, 0) when the position is unknown (e.g. ID-based positions from live PIDE). *)
fun entry_def_pos entry =
  let val pos = #pos entry
      val file = the_default "" (Position.file_of pos)
      val file' = if file = "" then "" else File.standard_path (Path.explode file)
  in (file',
      the_default 0 (Position.line_of pos),
      the_default 0 (Position.offset_of pos))
  end

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


(* --- Pattern matching utilities (from find_theorems.ML) --- *)

fun expand_abs t =
  let
    val m = Term.maxidx_of_term t + 1;
    val vs = strip_abs_vars t;
    val ts = map_index (fn (k, (_, T)) => Var ((Name.aT, m + k), T)) vs;
  in betapplys (t, ts) end;

fun get_names t = Term.add_const_names t (Term.add_free_names t []);

fun matches_subterm ctxt (pat, obj) =
  let
    val thy = Proof_Context.theory_of ctxt;
    fun matches obj ctxt' = Pattern.matches thy (pat, obj) orelse
      (case obj of
        Abs _ =>
          let val ((_, t'), ctxt'') = Variable.dest_abs obj ctxt'
          in matches t' ctxt'' end
      | t $ u => matches t ctxt' orelse matches u ctxt'
      | _ => false);
  in matches obj ctxt end;


(* --- Pattern filter construction --- *)

(* Resolve theories_include names to a set of long names.
   Returns (include_set_opt, warnings).
   - names = [] → (NONE, []) meaning "no restriction"
   - all names unresolved → (SOME empty_set, warnings) meaning "zero matches"
   - Unknown names produce warnings but do not abort. *)
fun resolve_include_set context names =
  if null names then (NONE, [])
  else
    let
      fun resolve_one name =
        let val long = Context.theory_long_name
                         (Theory_Hash.resolve_theory context name)
        in (SOME long, NONE) end
        handle ERROR _ =>
          (NONE,
           SOME ("Unknown theory " ^ quote name ^
                 " in theories_include; skipped"))
      val pairs = map resolve_one names
      val longs = map_filter #1 pairs
      val warnings = distinct (op =) (map_filter #2 pairs)
    in (SOME (Strhashtab.make_set longs), warnings) end

(* Parse term and type pattern strings. Returns (term list, typ list, warnings).
   Empty input lists produce empty output lists (= no restriction).
   Warns when term patterns contain undeclared free variables
   (which likely indicate misspelled constant names).
   Parse errors (ERROR, Par_Exn) are caught and returned as warnings
   with YXML markup stripped. *)
fun parse_patterns context (term_pat_strs, type_pat_strs) =
  if null term_pat_strs andalso null type_pat_strs then ([], [], [])
  else
    let val ctxt = Context.cases Proof_Context.init_global I context
        val ctxt_pat = Proof_Context.set_mode Proof_Context.mode_pattern ctxt
        fun handle_parse_exn exn =
          case Par_Exn.dest exn of
            SOME exns =>
              let val msgs = map_filter (fn ERROR msg => SOME msg | _ => NONE) exns
              in if length msgs = length exns
                 then map RPC_Pretty.trim_markup msgs
                 else Exn.reraise exn
              end
          | NONE =>
              (case exn of
                ERROR msg => [RPC_Pretty.trim_markup msg]
              | _ => Exn.reraise exn)
        val (term_pats, term_parse_warnings) =
          \<^try>\<open>(map (Syntax.read_term ctxt_pat) term_pat_strs, [])
          catch exn => ([], handle_parse_exn exn)\<close>
        val warnings = term_parse_warnings @
          (if null term_pats then []
           else maps (fn (pat_str, pat) =>
             let val undeclared = filter (not o Variable.is_declared ctxt)
                                         (Term.add_free_names pat [])
             in if null undeclared then []
                else let val plural = length undeclared > 1
                     in [String.concat [
                         "Term pattern ", quote pat_str,
                         " contains undeclared free variable",
                         if plural then "s: " else ": ",
                         commas_quote undeclared, ". ",
                         if plural then "They are likely misspelled constants."
                         else "It is likely a misspelled constant."]]
                     end
             end) (term_pat_strs ~~ term_pats))
        val (type_pats, type_parse_warnings) =
          \<^try>\<open>(map (Syntax.read_typ ctxt_pat) type_pat_strs, [])
          catch exn => ([], handle_parse_exn exn)\<close>
    in (term_pats, type_pats, warnings @ type_parse_warnings)
    end

(* Collect type constructor names from a type. *)
fun get_type_con_names (Type (name, Ts)) acc = fold get_type_con_names Ts (insert (op =) name acc)
  | get_type_con_names _ acc = acc

(* Collect all type constructor names occurring in a term. *)
fun get_type_con_names_of_term t =
  let val acc = Unsynchronized.ref ([] : string list)
  in Term.fold_types (fn T => fn () => acc := get_type_con_names T (!acc)) t ();
     !acc
  end

(* Pre-compute type pattern info: (parsed_type, constructor_names_in_pattern). *)
fun mk_type_pat_infos type_pats =
  map (fn typat => (typat, get_type_con_names typat [])) type_pats

(* Check if a type matches a type pattern via typ_instance, with constructor-name pre-filter. *)
fun type_matches_in_term typ_inst (type_pat_infos : (typ * string list) list) prop =
  let val term_type_con_names = get_type_con_names_of_term prop
  in List.all (fn (typat, pat_type_cons) =>
       subset (op =) (pat_type_cons, term_type_con_names)
       andalso Term.exists_type (fn T =>
         Term.exists_subtype (fn ty =>
           typ_inst (ty, typat) handle TYPE _ => false) T) prop)
     type_pat_infos
  end

(* Check if a single type matches all type patterns via typ_instance, with constructor-name pre-filter. *)
fun type_matches_in_type typ_inst (type_pat_infos : (typ * string list) list) T =
  let val type_con_names = get_type_con_names T []
  in List.all (fn (typat, pat_type_cons) =>
       subset (op =) (pat_type_cons, type_con_names)
       andalso Term.exists_subtype (fn ty =>
         typ_inst (ty, typat) handle TYPE _ => false) T)
     type_pat_infos
  end

(* Build a prop filter from parsed term/type patterns.
   Returns (term -> bool). Always true when both lists are empty. *)
fun mk_prop_pattern_matcher ctxt (term_pats : term list) (type_pats : typ list) : term -> bool =
  if null term_pats andalso null type_pats then (fn _ => true)
  else
    let val thy = Proof_Context.theory_of ctxt
        val typ_inst = Sign.typ_instance thy
        val term_pat_infos = map (fn pat =>
          let val pat' = (expand_abs o Envir.eta_contract) pat
          in (pat', get_names pat') end) term_pats
        val type_pat_infos = mk_type_pat_infos type_pats
    in fn prop =>
      let val prop_names = get_names prop
      in List.all (fn (pat', pat_consts) =>
           subset (op =) (pat_consts, prop_names)
           andalso matches_subterm ctxt (pat', prop)) term_pat_infos
         andalso type_matches_in_term typ_inst type_pat_infos prop
      end
    end

(* Build a thm filter from parsed term/type patterns.
   Returns (thm -> bool). Always true when both lists are empty. *)
fun mk_thm_pattern_matcher ctxt term_pats type_pats : thm -> bool =
  let val prop_matcher = mk_prop_pattern_matcher ctxt term_pats type_pats
  in fn thm => prop_matcher (Thm.full_prop_of thm) end

(* Build a constant-name filter from parsed type patterns.
   Only type_pats apply; term_pats are ignored for constants.
   Returns (string -> bool). Always true when type_pats is empty. *)
fun mk_const_pattern_matcher ctx (type_pats : typ list) : string -> bool =
  if null type_pats then (fn _ => true)
  else
    let val thy = Context.theory_of ctx
        val typ_inst = Sign.typ_instance thy
        val consts = Context.cases Sign.consts_of Proof_Context.consts_of ctx
        val type_pat_infos = mk_type_pat_infos type_pats
    in fn name =>
      (let val T = Consts.the_constraint consts name
       in type_matches_in_type typ_inst type_pat_infos T
       end) handle ERROR _ => false
    end


(* --- name_contains filter: case-insensitive substring match on fully qualified name --- *)

fun mk_name_filter [] = (fn _ : string => true)
  | mk_name_filter pats =
      let val pats_lower = map (String.map Char.toLower) pats
      in fn name =>
        let val name_lower = String.map Char.toLower name
        in List.all (fn pat => String.isSubstring pat name_lower) pats_lower end
      end

(* --- ns_filter: shared for constants, types, classes, locales --- *)

fun ns_filter limit key_of space target_name exclude_set include_set extra_filter filter_opt =
  let
    val names = Name_Space.get_names space
    val seen = Bytehashtab.empty 128
    fun collect [] acc _ = rev acc
      | collect _ acc 0 = rev acc
      | collect (name :: rest) acc remaining =
          let val result =
            (let val entry = Name_Space.the_entry space name
             in if #concealed entry
                   orelse Long_Name.is_hidden (Name_Space.intern space name) then NONE
                else
                  let val thy_name = #theory_long_name entry
                      val pass = case exclude_set of
                           NONE => thy_name = target_name
                         | SOME es => not (Strhashtab.defined es thy_name)
                      val pass_include = case include_set of
                           NONE => true
                         | SOME is => Strhashtab.defined is thy_name
                  in if not pass orelse not pass_include then NONE
                     else if not (extra_filter name) then NONE
                     else
                       let val pass_filter = case filter_opt of
                               NONE => true | SOME f => f name
                       in if not pass_filter then NONE
                          else SOME (key_of name, name, entry_def_pos entry)
                       end
                  end
             end) handle ERROR _ => NONE
          in case result of
               NONE => collect rest acc remaining
             | SOME (k, nm, pos) =>
                 if Bytehashtab.defined seen k then collect rest acc remaining
                 else (Bytehashtab.update seen (k, ());
                       collect rest ((k, nm, pos) :: acc) (remaining - 1))
          end
  in collect names [] limit end


(* --- Entity enumeration callbacks --- *)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

val arg_schema = unpackTuple8 (unpackOption unpackString, unpackBool,
      unpackList unpackString, unpackList unpackString,
      unpackList unpackString, unpackList unpackString,
      unpackList unpackString (* name_contains *),
      unpackInt (* limit, <0 = no limit *))

val pack_pos = packTuple3 (packString, packInt, packInt)

val ret_schema = packPair (
  packList (packTuple3 (Universal_Key.pack_universal_key, packString, pack_pos)),
  packList packString (* warnings *))

fun make_constants_callback filter_opt (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.constants",
    arg_schema = arg_schema,
    ret_schema = ret_schema,
    function = fn (target_thy_opt, the_theory_only, exclude,
                    _, type_pat_strs, theories_include, name_contains, limit) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = #1 o Universal_Key.key_of_constant ctx
        val space = Consts.space_of (Context.cases Sign.consts_of Proof_Context.consts_of ctx)
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_set, include_warnings) = resolve_include_set context theories_include
        val (_, type_pats, warnings) = parse_patterns context ([], type_pat_strs)
        val const_pat_filter = mk_const_pattern_matcher ctx type_pats
        val name_filter = mk_name_filter name_contains
        val keys = ns_filter limit key_of space target_name exclude_set include_set
                    (fn name => const_pat_filter name andalso name_filter name) filter_opt
      in (keys, include_warnings @ warnings) end,
    timeout = NONE
  }

fun make_theorems_callback filter_opt cache_opt (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.theorems",
    arg_schema = arg_schema,
    ret_schema = ret_schema,
    function = fn (target_thy_opt, the_theory_only, exclude,
                    term_pat_strs, type_pat_strs, theories_include, name_contains, limit) =>
      let
        val t_start = Time.now ()
        val ctx = resolve_ctx context target_thy_opt
        val thy = Context.theory_of ctx
        val target_name = Context.theory_long_name thy
        val facts = Context.cases Global_Theory.facts_of Proof_Context.facts_of ctx
        val fact_space = Facts.space_of facts
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_set, include_warnings) = resolve_include_set context theories_include
        val ctxt = Context.cases Proof_Context.init_global I ctx
        val (term_pats, type_pats, warnings) = parse_patterns ctx (term_pat_strs, type_pat_strs)
        val prop_matches = mk_prop_pattern_matcher ctxt term_pats type_pats
        val name_filter = mk_name_filter name_contains
        val seen = Bytehashtab.empty 128

        (* --- Uncached path: facts not covered by cache --- *)
        val uncached_facts = case cache_opt of
            NONE => Facts.dest_static false [] facts
          | SOME (_, cached_facts) => Facts.dest_static false [cached_facts] facts

        val t_dest = Time.now ()
        val _ = tracing (String.concat [
          "[perf.theorems_cb] uncached_facts: ",
          Int.toString (length uncached_facts), " (",
          Int.toString (Time.toMilliseconds (Time.- (t_dest, t_start))), "ms)"])

        val t_loop = Time.now ()
        val (uncached_entries, _) = fold (fn (name, thms) => fn (acc, remaining) =>
           if remaining = 0 then (acc, 0)
           else
           let val entry = try (Name_Space.the_entry fact_space) name
           in case entry of
                NONE => (acc, remaining)
              | SOME e =>
                  if #concealed e
                     orelse Long_Name.is_hidden (Name_Space.intern fact_space name)
                  then (acc, remaining)
                  else
                  let val thy_name = #theory_long_name e
                      val dominated = case exclude_set of
                           NONE => thy_name <> target_name
                         | SOME es => Strhashtab.defined es thy_name
                      val included = case include_set of
                           NONE => true
                         | SOME is => Strhashtab.defined is thy_name
                  in if dominated orelse not included then (acc, remaining)
                     else if not (name_filter name) then (acc, remaining)
                     else
                       let val epos = entry_def_pos e
                       in fold (fn thm => fn (acc, remaining) =>
                       if remaining = 0 then (acc, 0)
                       else
                       let val thm' = Thm.transfer thy thm
                       in if not (prop_matches (Thm.full_prop_of thm')) then (acc, remaining)
                          else
                            let val pass_filter = case filter_opt of
                                  NONE => true
                                | SOME f => f (name, thm')
                            in if not pass_filter then (acc, remaining)
                               else
                                 let val k = Universal_Key.key_of_theorem' NONE ctx thm'
                                 in if Bytehashtab.defined seen k then (acc, remaining)
                                    else (Bytehashtab.update seen (k, ());
                                          ((k, name, epos) :: acc, remaining - 1))
                                 end
                            end
                       end) thms (acc, remaining)
                       end
                  end
           end) uncached_facts ([], limit)

        val t_uncached = Time.now ()
        val _ = tracing (String.concat [
          "[perf.theorems_cb] uncached_loop: ",
          Int.toString (Time.toMilliseconds (Time.- (t_uncached, t_loop))), "ms (",
          Int.toString (length uncached_entries), " entries)"])

        (* --- Cached path: apply only query-specific filters --- *)
        (* limit < 0 means unlimited; otherwise subtract what uncached already consumed *)
        val remaining_after_uncached =
          if limit < 0 then ~1 else Int.max (0, limit - length uncached_entries)
        val cached_entries = case cache_opt of
            NONE => []
          | SOME (cached, _) =>
              if remaining_after_uncached = 0 then []
              else
              let val (results, _) = fold (fn (entry : cached_thm_entry) => fn (acc, remaining) =>
                    if remaining = 0 then (acc, 0)
                    else
                    let val ethy = #thy_name entry
                        val dominated = case exclude_set of
                             NONE => ethy <> target_name
                           | SOME es => Strhashtab.defined es ethy
                        val included = case include_set of
                             NONE => true
                           | SOME is => Strhashtab.defined is ethy
                    in if dominated orelse not included then (acc, remaining)
                       else if not (name_filter (#name entry)) then (acc, remaining)
                       else if not (prop_matches (Thm.full_prop_of (#thm entry))) then (acc, remaining)
                       else if Bytehashtab.defined seen (#uk entry) then (acc, remaining)
                       else (Bytehashtab.update seen (#uk entry, ());
                             ((#uk entry, #name entry, #pos entry) :: acc, remaining - 1))
                    end) cached ([], remaining_after_uncached)
              in results end

        val t_cached = Time.now ()
        val _ = tracing (String.concat [
          "[perf.theorems_cb] cached_loop: ",
          Int.toString (Time.toMilliseconds (Time.- (t_cached, t_uncached))), "ms (",
          Int.toString (length cached_entries), " entries from ",
          Int.toString (case cache_opt of NONE => 0 | SOME (c, _) => length c),
          " cached)"])

        val entries = rev uncached_entries @ rev cached_entries

        val t_end = Time.now ()
        val _ = tracing (String.concat [
          "[perf.theorems_cb] total: ",
          Int.toString (Time.toMilliseconds (Time.- (t_end, t_start))), "ms (",
          Int.toString (length entries), " entries)"])
      in (entries, include_warnings @ warnings) end,
    timeout = NONE
  }

fun make_types_callback filter_opt (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.types",
    arg_schema = arg_schema,
    ret_schema = ret_schema,
    function = fn (target_thy_opt, the_theory_only, exclude, _, _, theories_include, name_contains, limit) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = #1 o Universal_Key.key_of_type ctx
        val space = Context.cases Sign.type_space Proof_Context.type_space ctx
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_set, include_warnings) = resolve_include_set context theories_include
      in (ns_filter limit key_of space target_name exclude_set include_set (mk_name_filter name_contains) filter_opt, include_warnings) end,
    timeout = NONE
  }

fun make_classes_callback filter_opt (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.classes",
    arg_schema = arg_schema,
    ret_schema = ret_schema,
    function = fn (target_thy_opt, the_theory_only, exclude, _, _, theories_include, name_contains, limit) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = #1 o Universal_Key.key_of_class ctx
        val space = Context.cases Sign.class_space Proof_Context.class_space ctx
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_set, include_warnings) = resolve_include_set context theories_include
      in (ns_filter limit key_of space target_name exclude_set include_set (mk_name_filter name_contains) filter_opt, include_warnings) end,
    timeout = NONE
  }

fun make_locales_callback filter_opt (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.locales",
    arg_schema = arg_schema,
    ret_schema = ret_schema,
    function = fn (target_thy_opt, the_theory_only, exclude, _, _, theories_include, name_contains, limit) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = #1 o Universal_Key.key_of_locale ctx
        val space = Locale.locale_space (Context.theory_of ctx)
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_set, include_warnings) = resolve_include_set context theories_include
      in (ns_filter limit key_of space target_name exclude_set include_set (mk_name_filter name_contains) filter_opt, include_warnings) end,
    timeout = NONE
  }

fun make_theory_long_name_callback (context : Context.generic)
    : Remote_Procedure_Calling.callback' =
  let val name = Context.theory_long_name (Context.theory_of context)
  in
    Remote_Procedure_Calling.mk_callback {
      name = "Context.the_theory_long_name",
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
    ret_schema = ret_schema,
    function = fn (target_thy_opt, the_theory_only, exclude,
                    term_pat_strs, type_pat_strs, theories_include, name_contains, limit) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val thy = Context.theory_of ctx
        val target_base = Context.theory_base_name thy
        val target_prefix = target_base ^ "."
        val thms = extract_thms ctx
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_set, include_warnings) = resolve_include_set context theories_include
        val fact_space = Facts.space_of
              (Context.cases Global_Theory.facts_of Proof_Context.facts_of ctx)
        val seen : unit Strhashtab.table = Strhashtab.empty 128
        val key_seen = Bytehashtab.empty 128
        val ctxt = Context.cases Proof_Context.init_global I ctx
        val (term_pats, type_pats, warnings) = parse_patterns ctx (term_pat_strs, type_pat_strs)
        val thm_matches = mk_thm_pattern_matcher ctxt term_pats type_pats
        val name_filter = mk_name_filter name_contains
        val (entries, _) = fold (fn thm => fn (acc, remaining) =>
          if remaining = 0 then (acc, 0)
          else
          let val thm = Thm.transfer thy thm
          in if not (Thm.has_name_hint thm) then (acc, remaining)
             else
          let val name = Thm.get_name_hint thm
          in if Strhashtab.defined seen name then (acc, remaining)
             else
               let
                 val entry_opt = try (Name_Space.the_entry fact_space) name
                 val thy_name_of = case entry_opt of
                     SOME e => (case #theory_long_name e of "" => NONE | tn => SOME tn)
                   | NONE => NONE
                 val pass = case exclude_set of
                     NONE => String.isPrefix target_prefix name
                   | SOME es => (case thy_name_of of
                         SOME tn => not (Strhashtab.defined es tn)
                       | NONE => true)
                 val pass_include = case include_set of
                     NONE => true
                   | SOME is => (case thy_name_of of
                         SOME tn => Strhashtab.defined is tn
                       | NONE => true)
               in if not pass orelse not pass_include then (acc, remaining)
                  else if not (name_filter name) then (acc, remaining)
                  else if not (thm_matches thm) then (acc, remaining)
                  else
                    let val pass_filter = case filter_opt of
                          NONE => true
                        | SOME f => f (name, thm)
                    in if not pass_filter then (acc, remaining)
                       else
                         let val k = key_of ctx thm
                             val epos = case entry_opt of
                                 SOME e => entry_def_pos e | NONE => ("", 0, 0)
                         in (Strhashtab.update seen (name, ());
                             if Bytehashtab.defined key_seen k then (acc, remaining)
                             else (Bytehashtab.update key_seen (k, ());
                                   ((k, name, epos) :: acc, remaining - 1)))
                         end
                    end
               end
          end
          end) thms ([], limit)
      in (rev entries, include_warnings @ warnings) end,
    timeout = NONE
  }
in
fun make_introduction_rules_callback extract_thms =
  make_rules_callback "Context.introduction_rules"
    (Universal_Key.key_of_introduction_rule' NONE) extract_thms
fun make_elimination_rules_callback extract_thms =
  make_rules_callback "Context.elimination_rules"
    (Universal_Key.key_of_elimination_rule' NONE) extract_thms
fun make_induction_rules_callback extract_thms =
  make_rules_callback "Context.induction_rules"
    (Universal_Key.key_of_induction_rule' NONE) extract_thms
fun make_case_split_rules_callback extract_thms =
  make_rules_callback "Context.case_split_rules"
    (Universal_Key.key_of_case_split_rule' NONE) extract_thms
end

end (*local*)

end
