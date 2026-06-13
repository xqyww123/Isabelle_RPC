(*
  Context entity enumeration callbacks.

  Each callback generator takes a `context_unpacker` — a msgpack unpacker that
  reads context-identifying data from the callback argument stream and returns
  a Context.generic.  Static callers supply `static_context_unpacker ctx` which
  reads msgpack nil and returns the fixed context; the agent supplies an unpacker
  that reads a state-id string and resolves the current proof state.

  Each callback's wire argument is a pair  (ctxt_data, payload)  where
  ctxt_data is consumed by the unpacker and payload is:
    (target_theory: string option, the_theory_only: bool, exclude: string list,
     term_patterns: string list, type_patterns: string list,
     theories_include: string list, name_contains: string list, limit: int,
     target_type: string)

  - target_theory: if SOME, resolve that long theory name and enumerate entities
    from its context; if NONE, use the unpacked context.
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
  - theories_include: case-insensitive substrings matched against each entity's
    fully-qualified theory name (any match keeps it, i.e. disjunction; short
    fragments and full names both work). Empty = no restriction. A substring
    matching no loaded theory yields a warning.
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

  (* Name of a cached theorem entry. `Fixed`: a static fact's name+index
     (stable). `Member_of_Dynamic`: a member of a dynamic collection, carrying
     the collection's full name; its display name is computed live at query time
     as "coll(i)", where i is the member's position in the collection's CURRENT
     content (a stored index would go stale on collection mutation). *)
  datatype entry_name =
      Fixed             of Thm_Name.T
    | Member_of_Dynamic of string

  (* Cached theorem entry: pre-computed at theory-load time, used to skip
     entry_lookup / infra_filter / key_compute at query time.  `theories` are
     the constituent theory long-names of the proposition (post-XOR-refactor
     notion of theory membership), used for theory-scope query filtering. *)
  type cached_thm_entry = {
    uk: Universal_Key.universal_key,
    name: entry_name,
    pos: def_pos,
    thm: thm,
    theories: string list
  }

  (* The DB-storable name of an entry (no live index): `Fixed` -> its stable
     "name(i)" form; `Member_of_Dynamic` -> the bare collection name. *)
  val bare_name : entry_name -> string

  (* A msgpack unpacker that produces a Context.generic from the argument stream.
     Static callers read nil; agent callers read a state-id string. *)
  type context_unpacker = Universal_Key.context_unpacker
  val static_context_unpacker : Context.generic -> context_unpacker

  (* Exported utilities for building caches externally *)
  val entry_def_pos : {pos: Position.T, serial: serial, group: serial,
    suppress: bool list, theory_long_name: string, concealed: bool} -> def_pos
  val parse_patterns : Context.generic -> string list * string list -> term list * typ list * string list
  val mk_name_filter : string list -> string -> bool
  val mk_prop_pattern_matcher : Proof.context -> term list -> typ list -> term -> bool

  (* For a dynamic fact, return its current members in the given context;
     for a static fact or a missing name, NONE.  Generalizes the previous
     named_theorems-only handling to any dynamic fact (e.g. the raw
     add_thms_dynamic collection derivative_eq_intros). *)
  val dynamic_fact_members : Context.generic -> Facts.T -> string -> thm list option

  (* Coercion constants to ignore in transparent pattern matching.
     When a unary Const application (F $ X) has F in this set,
     the matcher treats it as just X.
     Mutable hash table — populate at session setup time via Strhashtab.update. *)
  val coercion_ignores : unit Strhashtab.table

  val make_constants_callback : (string -> bool) option -> context_unpacker -> Remote_Procedure_Calling.callback'
  (* cache_opt: when SOME (entries, facts), uses cached entries for global theorems
     and only runs the full pipeline on facts not in the cached Facts.T. *)
  val make_theorems_callback :
    (string * thm -> bool) option ->
    (cached_thm_entry list * Facts.T) option ->
    context_unpacker -> Remote_Procedure_Calling.callback'
  val make_types_callback : (string -> bool) option -> context_unpacker -> Remote_Procedure_Calling.callback'
  val make_classes_callback : (string -> bool) option -> context_unpacker -> Remote_Procedure_Calling.callback'
  val make_locales_callback : (string -> bool) option -> context_unpacker -> Remote_Procedure_Calling.callback'
  val make_theorem_collection_callback : (string -> bool) option -> context_unpacker -> Remote_Procedure_Calling.callback'
  val make_methods_callback : (string -> bool) option -> context_unpacker -> Remote_Procedure_Calling.callback'
  val make_theory_long_name_callback : context_unpacker -> Remote_Procedure_Calling.callback'
  val make_theory_long_name_and_path_callback : context_unpacker -> Remote_Procedure_Calling.callback'
  (* The thm list extractor is supplied by the caller because Classical requires HOL,
     which is not available in this Pure-level file. *)
  val make_introduction_rules_callback :
    (Context.generic -> thm list) -> (string * thm -> bool) option ->
    context_unpacker -> Remote_Procedure_Calling.callback'
  val make_elimination_rules_callback :
    (Context.generic -> thm list) -> (string * thm -> bool) option ->
    context_unpacker -> Remote_Procedure_Calling.callback'
  val make_induction_rules_callback :
    (Context.generic -> thm list) -> (string * thm -> bool) option ->
    context_unpacker -> Remote_Procedure_Calling.callback'
  val make_case_split_rules_callback :
    (Context.generic -> thm list) -> (string * thm -> bool) option ->
    context_unpacker -> Remote_Procedure_Calling.callback'
end

structure Context_Callbacks : CONTEXT_CALLBACKS = struct

type context_unpacker = Universal_Key.context_unpacker

val static_context_unpacker = Universal_Key.static_context_unpacker

type def_pos = string * int * int

datatype entry_name =
    Fixed             of Thm_Name.T
  | Member_of_Dynamic of string

type cached_thm_entry = {
  uk: Universal_Key.universal_key,
  name: entry_name,
  pos: def_pos,
  thm: thm,
  theories: string list
}

(* DB-storable name (no live index). *)
fun bare_name (Fixed nm)               = Thm_Name.print nm
  | bare_name (Member_of_Dynamic coll) = coll

(* Live display name for a query result.  `memo` (allocated per query) caches
   coll -> current member thms, so a dynamic collection is synthesized at most
   once per query even when several of its members are returned.  The member's
   index is its position in the collection's CURRENT content (1-based, like
   Isabelle fact selection `coll(i)`).  Returns NONE if the member is no longer
   present (the collection mutated since the prep-phase snapshot): such an entry
   is stale and the caller drops it from the results, rather than citing it by a
   bare collection name that would be ambiguous and un-resolvable to this thm. *)
fun resolve_name _ _ (Fixed nm) _ = SOME (Thm_Name.print nm)
  | resolve_name memo ctxt (Member_of_Dynamic coll) thm =
      let
        val thms =
          case Strhashtab.lookup memo coll of
            SOME ts => ts
          | NONE =>
              let
                val facts = Context.cases Global_Theory.facts_of Proof_Context.facts_of ctxt
                val ts = case Facts.lookup ctxt facts coll of
                           SOME {thms, ...} => thms | NONE => []
              in Strhashtab.update memo (coll, ts); ts end
      in
        case find_index (fn t => Thm.prop_of t aconv Thm.prop_of thm) thms of
          ~1 => NONE
        | i => SOME (coll ^ "(" ^ string_of_int (i + 1) ^ ")")
      end


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

val coercion_ignores : unit Strhashtab.table = Strhashtab.empty 8

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


(* --- Coercion-transparent pattern matching ---
   Copied from PLPR_Pattern (Performant_Isabelle_ML/library/pattern.ML),
   modified to: (a) ignore types, (b) skip coercion wrappers in coercion_ignores. *)

local
  open Pattern (* for MATCH exception, Unif exception *)

  fun idx_t [] j     = raise Unif
    | idx_t(i::is) j = if (i:int) =j then length is else idx_t is j;

  fun mkabs_t (binders,is,t)  =
      let fun mk(i::is) = let val (x,T) = nth binders i
                          in Abs(x,T,mk is) end
            | mk []     = t
      in mk is end;

  fun ints_of_t []             = []
    | ints_of_t (Bound i ::bs) =
        let val is = ints_of_t bs
        in if member (op =) is i then raise Pattern else i::is end
    | ints_of_t _              = raise Pattern;

  fun downto0_t (i :: is, n) = i = n andalso downto0_t (is, n - 1)
    | downto0_t ([], n) = n = ~1;

  fun mapbnd_t f =
      let fun mpb d (Bound(i))     = if i < d then Bound(i) else Bound(f(i-d)+d)
            | mpb d (Abs(s,T,t))   = Abs(s,T,mpb(d+1) t)
            | mpb d ((u1 $ u2))    = (mpb d u1)$(mpb d u2)
            | mpb _ atom           = atom
      in mpb 0 end;

  fun app_t (s,(i::is)) = app_t (s$Bound(i),is)
    | app_t (s,[])      = s;

  fun red_t (Abs(_,_,s)) (i::is) js = red_t s is (i::js)
    | red_t t            []      [] = t
    | red_t t            is      jn = app_t (mapbnd_t (fn k => nth jn k handle Subscript => k) t,is);

  val incr_t = mapbnd_t (fn i => i+1);

  (* First-order matching — type-agnostic, coercion-transparent.
     Copied from PLPR_Pattern.first_order_match with typ_match removed. *)
  fun first_order_match_transparent (ignores : unit Strhashtab.table)
        fixed_bounds bv_tys (t,u) env =
    let
      val bs = Inttab.make_set (loose_bnos u)
      fun mtch bv_tys lev (instsp as (tyinsts,insts)) = fn
          (Var(ixn,T), t)  =>
            if forall (Inttab.defined bs) (loose_bnos t)
            then (case Envir.lookup1 insts (ixn, T) of
                    NONE => (tyinsts, Vartab.update_new (ixn, (T, t)) insts)
                  | SOME u => if Envir.aeconv (t, u) then instsp else raise MATCH)
            else raise MATCH
        | (Free (a,_), Free (b,_)) =>
            if a=b then instsp else raise MATCH
        | (Const (a,_), Const (b,_))  =>
            if a=b then instsp else raise MATCH
        | (Bound i, Bound j)  =>  if  i=j  then  instsp  else raise MATCH
        | (Abs(_,_,t), Abs(_,U,u))  =>
            mtch bv_tys lev instsp (t,u)
        | (f$t, g$u) =>
            (mtch bv_tys lev (mtch bv_tys lev instsp (f,g)) (t, u)
             handle MATCH =>
               (case g of Const(name,_) =>
                  if Strhashtab.defined ignores name
                  then mtch bv_tys lev instsp (f$t, u)
                  else raise MATCH
                | _ => raise MATCH)
             handle MATCH =>
               (case f of Const(name,_) =>
                  if Strhashtab.defined ignores name
                  then mtch bv_tys lev instsp (t, g$u)
                  else raise MATCH
                | _ => raise MATCH))
        | (t, Abs(_,T,u))  => mtch (T::bv_tys) (lev+1) instsp ((incr_t t)$(Bound 0), u)
        | _ => raise MATCH
    in mtch bv_tys 0 env (t,u) end;

  (* Higher-order pattern matching — type-agnostic, coercion-transparent.
     Copied from PLPR_Pattern.match with typ_match removed. *)
  fun match_transparent (ignores : unit Strhashtab.table)
        (fixed_bounds : int -> bool) bvs (po as (pat,obj)) envir =
  let
    val len_initial = length bvs
    fun match_bind_t(itms,binders,ixn,T,is,t) =
      let val len = length binders
          val diff = len - len_initial
          val js = loose_bnos t
                |> filter (fn i => i < diff orelse not (fixed_bounds (i - diff)))
      in if null is
         then if null js then Vartab.update_new (ixn, (T, t)) itms else raise MATCH
         else if subset (op =) (js, is)
              then let val t' = if downto0_t(is, diff - 1) then t
                                else mapbnd_t (idx_t is) t
                   in Vartab.update_new (ixn, (T, mkabs_t (binders, is, t'))) itms end
              else raise MATCH
      end

    fun mtch binders (pat,obj) (env as (iTs,itms)) =
      case pat of
        Abs(ns,Ts,ts) =>
          (case obj of
             Abs(nt,Tt,tt) => mtch ((nt,Tt)::binders) (ts,tt) env
           | _ => let val Tt = Envir.subst_type iTs Ts
                  in mtch((ns,Tt)::binders) (ts,(incr_t obj)$Bound(0)) env end)
      | _ => (case obj of
                Abs(nt,Tt,tt) =>
                  mtch((nt,Tt)::binders) ((incr_t pat)$Bound(0),tt) env
              | _ => cases(binders,env,pat,obj))

    and cases(binders,env as (iTs,itms),pat,obj) =
      let val (ph,pargs) = strip_comb pat
          fun rigrig1(iTs,oargs) = fold (mtch binders) (pargs~~oargs) (iTs,itms)
            handle ListPair.UnequalLengths => raise MATCH
          fun rigrig2((a:string,_),(b,_),oargs) =
                if a <> b then raise MATCH
                else rigrig1(iTs, oargs)
      in case ph of
           Var(ixn,T) =>
             let val is = ints_of_t pargs
             in case Envir.lookup1 itms (ixn, T) of
                  NONE => (iTs,match_bind_t(itms,binders,ixn,T,is,obj))
                | SOME u => if Envir.aeconv (obj, red_t u is []) then env
                            else raise MATCH
             end
         | _ =>
             let val (oh,oargs) = strip_comb obj
             in (case (ph,oh) of
                   (Const c,Const d) => rigrig2(c,d,oargs)
                 | (Free f,Free g)   => rigrig2(f,g,oargs)
                 | (Bound i,Bound j) => if i<>j then raise MATCH
                                        else rigrig1(iTs,oargs)
                 | (Abs _, _)        => raise Pattern
                 | (_, Abs _)        => raise Pattern
                 | _                 => raise MATCH)
             handle MATCH =>
               (case (oh, oargs) of
                  (Const(name,_), [inner]) =>
                    if Strhashtab.defined ignores name
                    then cases(binders, env, pat, inner)
                    else raise MATCH
                | _ => raise MATCH)
             handle MATCH =>
               (case (ph, pargs) of
                  (Const(name,_), [inner]) =>
                    if Strhashtab.defined ignores name
                    then cases(binders, env, inner, obj)
                    else raise MATCH
                | _ => raise MATCH)
             end
      end;

    val bvtys = map snd bvs
  in mtch bvs po envir
     handle Pattern =>
       first_order_match_transparent ignores (K true) bvtys po envir
  end;

in

fun matches_transparent ignores fixed_bounds bvs po =
  (match_transparent ignores fixed_bounds bvs po (Vartab.empty, Vartab.empty); true)
  handle MATCH => false
       | TYPE _ => false

fun matches_subterm_transparent ctxt ignores (pat, obj) =
  let
    fun try_match obj ctxt' =
      matches_transparent ignores (K true) [] (pat, obj) orelse
      (case obj of
        Abs _ =>
          let val ((_, t'), ctxt'') = Variable.dest_abs obj ctxt'
          in try_match t' ctxt'' end
      | t $ u => try_match t ctxt' orelse try_match u ctxt'
      | _ => false);
  in try_match obj ctxt end

end (* local *)


(* --- Pattern filter construction --- *)

(* Build a theories_include filter: case-insensitive substring match on a
   theory's fully-qualified (long) name. A theory passes if its long name
   contains ANY of the given substrings (OR). Returns (thy_name -> bool,
   warnings).
   - names = [] → ((fn _ => true), []) meaning "no restriction".
   - Substring match on the long name accepts both short fragments
     ("Transcendental") and fully-qualified names ("HOL.Transcendental").
   - Each substring that matches no loaded theory (the current theory or any
     ancestor) yields a warning, so a typo surfaces instead of silently
     filtering everything out. It does not abort the query. *)
fun mk_include_filter context names =
  if null names then ((fn _ : string => true), [])
  else
    let
      val pats_lower = map (String.map Char.toLower) names
      val pred = fn thy_name =>
        let val lower = String.map Char.toLower thy_name
        in List.exists (fn pat => String.isSubstring pat lower) pats_lower end
      val thy = Context.theory_of context
      val loaded_lower =
        map (String.map Char.toLower o Context.theory_long_name)
            (thy :: Theory.ancestors_of thy)
      val warnings =
        distinct (op =)
          (map_filter (fn (orig, pat) =>
             if List.exists (fn nm => String.isSubstring pat nm) loaded_lower
             then NONE
             else SOME ("No loaded theory name contains " ^ quote orig ^
                        " in theories_include; skipped"))
           (names ~~ pats_lower))
    in (pred, warnings) end

(* Parse term and type pattern strings. Returns (term list, typ list, warnings).
   Empty input lists produce empty output lists (= no restriction).
   Warns when term patterns contain undeclared free variables
   (which likely indicate misspelled constant names).
   Each pattern is parsed individually so one bad pattern does not discard the
   rest.  On parse failure, a cascade of fallbacks is tried:
     1. "(" ^ s ^ ")"      — bare operators: ≤ / < / * via operator section (≤)
     2. s ^ "('a)"         — type-argument syntax: CARD, TYPE, OFCLASS, …
                              ('a is generalized to schematic in pattern mode)
     3. s ^ " ?x"          — prefix unary syntax
     4. "?x " ^ s ^ " ?y"  — infix binary syntax
   If all fail, the pattern is dropped with a warning (reporting the original
   error). *)
fun parse_patterns context (term_pat_strs, type_pat_strs) =
  if null term_pat_strs andalso null type_pat_strs then ([], [], [])
  else
    let val ctxt = Context.cases Proof_Context.init_global I context
        val ctxt_pat = Proof_Context.set_mode Proof_Context.mode_pattern ctxt
        fun format_parse_exn exn =
          case Par_Exn.dest exn of
            SOME exns =>
              let val msgs = map_filter (fn ERROR msg => SOME msg | _ => NONE) exns
              in if length msgs = length exns
                 then String.concatWith "\n" (map RPC_Pretty.trim_markup msgs)
                 else Exn.reraise exn
              end
          | NONE =>
              (case exn of
                ERROR msg => RPC_Pretty.trim_markup msg
              | _ => Exn.reraise exn)
        fun try_read s =
          Exn.capture (Syntax.read_term ctxt_pat) s
        fun try_read_term s =
          (case try_read s of
            Exn.Res t => Exn.Res t
          | Exn.Exn exn =>
              let val attempts =
                    ["(" ^ s ^ ")",
                     s ^ "('a)",
                     s ^ " ?x",
                     "?x " ^ s ^ " ?y"]
              in case get_first (fn a => case try_read a of Exn.Res t => SOME t | _ => NONE) attempts of
                  SOME t => Exn.Res t
                | NONE => Exn.Exn exn
              end)
        val (term_pairs, term_parse_warnings) =
          fold_rev (fn pat_str => fn (pairs, warns) =>
            case try_read_term pat_str of
              Exn.Res pat => ((pat_str, pat) :: pairs, warns)
            | Exn.Exn exn => (pairs, format_parse_exn exn :: warns))
          term_pat_strs ([], [])
        val term_pats = map snd term_pairs
        val warnings = term_parse_warnings @
          (maps (fn (pat_str, pat) =>
             let val undeclared = filter (not o Variable.is_declared ctxt)
                                         (Term.add_free_names pat [])
             in if null undeclared then []
                else let val plural = length undeclared > 1
                         val wildcards = commas_quote (map (fn s => "?" ^ s) undeclared)
                     in [String.concat [
                         "Term pattern ", quote pat_str,
                         " contains undeclared free variable",
                         if plural then "s: " else ": ",
                         commas_quote undeclared, ". Use ", wildcards,
                         if plural then " to express named wildcards."
                         else " to express a named wildcard."]]
                     end
             end) term_pairs)
        val (type_pats, type_parse_warnings) =
          \<^try>\<open>(map (Syntax.read_typ ctxt_pat) type_pat_strs, [])
          catch exn => ([], [format_parse_exn exn])\<close>
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
   Returns (term -> bool). Always true when both lists are empty.
   Uses coercion-transparent matching: coercion wrappers in coercion_ignores
   are skipped, and type matching is ignored. A budget limits the number of
   transparent matching attempts to avoid excessive work. *)
fun mk_prop_pattern_matcher ctxt (term_pats : term list) (type_pats : typ list) : term -> bool =
  if null term_pats andalso null type_pats then (fn _ => true)
  else
    let val thy = Proof_Context.theory_of ctxt
        val typ_inst = Sign.typ_instance thy
        val ignores = coercion_ignores
        val has_ignores = not (Strhashtab.is_empty ignores)
        val term_pat_infos = map (fn pat =>
          let val pat' = (expand_abs o Envir.eta_contract) pat
              val names = get_names pat'
              val names_effective =
                if not has_ignores then names
                else filter (fn n => not (Strhashtab.defined ignores n)) names
          in (pat', names_effective) end) term_pats
        val type_pat_infos = mk_type_pat_infos type_pats
        val budget = Unsynchronized.ref 200
    in fn prop =>
      let val prop_names = get_names prop
      in List.all (fn (pat', names_effective) =>
           subset (op =) (names_effective, prop_names)
           andalso not (null names_effective)
           andalso !budget > 0
           andalso (budget := !budget - 1;
                    matches_subterm_transparent ctxt ignores (pat', prop))
         ) term_pat_infos
         andalso type_matches_in_term typ_inst type_pat_infos prop
      end
    end

(* Build a thm filter from parsed term/type patterns.
   Returns (thm -> bool). Always true when both lists are empty. *)
fun mk_thm_pattern_matcher ctxt term_pats type_pats : thm -> bool =
  let val prop_matcher = mk_prop_pattern_matcher ctxt term_pats type_pats
  in fn thm => prop_matcher (Thm.full_prop_of thm) end

(* Permissive: returns types of *all* schematic Vars in the rule's prop, not
   only the inducted-on variable.  A more targeted extraction (e.g. only the
   conclusion's last arg) would miss case-split rules whose conclusion is a
   bare ?P, miss mutual induction with multiple eigen-vars, and miss rules
   whose major premise has constraint shape (well_founded ?r ⟹ ...).  The
   downstream filter is bidirectional unification, so extra candidate types
   only widen the match and never produce false negatives. *)
fun rule_target_types thm : typ list =
  let
    val prop = Thm.full_prop_of thm
    val vars = Term.fold_aterms
                 (fn t as Var _ => cons t | _ => I) prop []
  in distinct (op =) (map (#2 o Term.dest_Var) vars) end
  handle THM _ => [] | TERM _ => []

(* Build a target-type filter for induction / case-split rules. NONE = no filter
   (always true). SOME qT = keep rule iff some Var-type in the rule unifies with
   qT in either direction (bidirectional Sign.typ_instance handles wildcards on
   both sides). *)
fun mk_target_type_filter _   NONE      = (fn _ : thm => true)
  | mk_target_type_filter ctx (SOME qT) =
      let val thy = Context.theory_of ctx
          val typ_inst = Sign.typ_instance thy
          fun unifies rT =
            (typ_inst (qT, rT) handle TYPE _ => false)
            orelse (typ_inst (rT, qT) handle TYPE _ => false)
      in fn thm => List.exists unifies (rule_target_types thm) end

(* "" => no filter (NONE).  Parse failure => no filter + warning (so the
   agent learns the type string was malformed instead of silently getting
   unfiltered results). *)
fun parse_target_type context "" = (NONE, [])
  | parse_target_type context s =
      let val ctxt = Context.cases Proof_Context.init_global I context
          val ctxt_pat = Proof_Context.set_mode Proof_Context.mode_pattern ctxt
      in
        \<^try>\<open>(SOME (Syntax.read_typ ctxt_pat s), [])
        catch _ =>
          (NONE, ["target_type " ^ quote s ^ " could not be parsed; filter ignored."])\<close>
      end

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

(* For a dynamic fact, return its current members; for a static fact or a
   missing name, NONE.  Facts.lookup evaluates the registered dynamic function,
   so this works uniformly for named_theorems and raw add_thms_dynamic
   collections (e.g. derivative_eq_intros). *)
fun dynamic_fact_members context facts name =
  case Facts.lookup context facts name of
    SOME {dynamic = true, thms} => SOME thms
  | _ => NONE

(* --- ns_filter: shared for constants, types, classes, locales --- *)

fun ns_filter limit key_of space target_name exclude_set include_pred extra_filter filter_opt =
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
                      val pass_include = include_pred thy_name
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

val arg_schema = unpackTuple9 (unpackOption unpackString, unpackBool,
      unpackList unpackString, unpackList unpackString,
      unpackList unpackString, unpackList unpackString,
      unpackList unpackString (* name_contains *),
      unpackInt (* limit, <0 = no limit *),
      unpackString (* target_type, "" = no filter; only used by induction/case-split rules *))

val pack_pos = packTuple3 (packString, packInt, packInt)

val ret_schema = packPair (
  packList (packTuple3 (Universal_Key.pack_universal_key, packString, pack_pos)),
  packList packString (* warnings *))

(* Theorems carry an extra per-entry `is_local` bool: true when emitted by the
   query-time uncached path (a fact in the query context but not in the global
   snapshot — i.e. proof-context-local), false for globally-cached facts. *)
val ret_schema_thm = packPair (
  packList (packTuple4 (Universal_Key.pack_universal_key, packString, pack_pos, packBool)),
  packList packString (* warnings *))

fun make_constants_callback filter_opt (ctxt_unpack : context_unpacker)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.constants",
    arg_schema = unpackPair (ctxt_unpack, arg_schema),
    ret_schema = ret_schema,
    function = fn (context, (target_thy_opt, the_theory_only, exclude,
                    _, type_pat_strs, theories_include, name_contains, limit, _)) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = #1 o Universal_Key.key_of_constant ctx
        val space = Consts.space_of (Context.cases Sign.consts_of Proof_Context.consts_of ctx)
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_pred, include_warnings) = mk_include_filter context theories_include
        val (_, type_pats, warnings) = parse_patterns context ([], type_pat_strs)
        val const_pat_filter = mk_const_pattern_matcher ctx type_pats
        val name_filter = mk_name_filter name_contains
        val keys = ns_filter limit key_of space target_name exclude_set include_pred
                    (fn name => const_pat_filter name andalso name_filter name) filter_opt
      in (keys, include_warnings @ warnings) end,
    timeout = NONE
  }

fun make_theorems_callback filter_opt cache_opt (ctxt_unpack : context_unpacker)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.theorems",
    arg_schema = unpackPair (ctxt_unpack, arg_schema),
    ret_schema = ret_schema_thm,
    function = fn (context, (target_thy_opt, the_theory_only, exclude,
                    term_pat_strs, type_pat_strs, theories_include, name_contains, limit, _)) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val thy = Context.theory_of ctx
        val target_name = Context.theory_long_name thy
        val facts = Context.cases Global_Theory.facts_of Proof_Context.facts_of ctx
        val fact_space = Facts.space_of facts
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_pred, include_warnings) = mk_include_filter context theories_include
        val ctxt = Context.cases Proof_Context.init_global I ctx
        val (term_pats, type_pats, warnings) = parse_patterns ctx (term_pat_strs, type_pat_strs)
        val prop_matches = mk_prop_pattern_matcher ctxt term_pats type_pats
        val name_filter = mk_name_filter name_contains
        val seen = Bytehashtab.empty 128
        (* per-query memo for live display-name resolution: coll -> member thms *)
        val name_memo : thm list Strhashtab.table = Strhashtab.empty 16

        (* --- Uncached path: facts not covered by cache --- *)
        val uncached_facts = case cache_opt of
            NONE => Facts.dest_static false [] facts
          | SOME (_, cached_facts) => Facts.dest_static false [cached_facts] facts

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
                  if not (name_filter name) then (acc, remaining)
                  else
                       let val epos = entry_def_pos e
                       in fold (fn thm => fn (acc, remaining) =>
                       if remaining = 0 then (acc, 0)
                       else
                       let val thm' = Thm.transfer thy thm
                           (* theory-scope filter on constituent theories (per thm) *)
                           val ct = map #1 (#2 (Universal_Key.thm_constituents ctx thm'))
                           val dominated = case exclude_set of
                                NONE => not (null ct) andalso not (member (op =) ct target_name)
                              | SOME es => not (null ct) andalso forall (fn c => Strhashtab.defined es c) ct
                           val included = null ct orelse exists include_pred ct
                       in if dominated orelse not included then (acc, remaining)
                          else if not (prop_matches (Thm.full_prop_of thm')) then (acc, remaining)
                          else
                            let val pass_filter = case filter_opt of
                                  NONE => true
                                | SOME f => f (name, thm')
                            in if not pass_filter then (acc, remaining)
                               else
                                 let val k = Universal_Key.key_of_theorem' NONE ctx thm'
                                 in if Bytehashtab.defined seen k then (acc, remaining)
                                    else (Bytehashtab.update seen (k, ());
                                          (* uncached = in query context, not in the
                                             global snapshot => proof-context-local *)
                                          ((k, name, epos, true) :: acc, remaining - 1))
                                 end
                            end
                       end) thms (acc, remaining)
                       end
           end) uncached_facts ([], limit)

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
                    let val ct = #theories entry
                        val dominated = case exclude_set of
                             NONE => not (null ct) andalso not (member (op =) ct target_name)
                           | SOME es => not (null ct) andalso forall (fn c => Strhashtab.defined es c) ct
                        val included = null ct orelse exists include_pred ct
                    in if dominated orelse not included then (acc, remaining)
                       else if not (name_filter (bare_name (#name entry))) then (acc, remaining)
                       else if not (prop_matches (Thm.full_prop_of (#thm entry))) then (acc, remaining)
                       else if Bytehashtab.defined seen (#uk entry) then (acc, remaining)
                       else (case resolve_name name_memo ctx (#name entry) (#thm entry) of
                               (* stale member: gone from its collection since the
                                  snapshot => drop it, keep `remaining` so the slot
                                  goes to the next valid candidate. *)
                               NONE => (acc, remaining)
                             | SOME nm =>
                                 (Bytehashtab.update seen (#uk entry, ());
                                  (* cached = global fact (in the snapshot) => not local *)
                                  ((#uk entry, nm, #pos entry, false) :: acc, remaining - 1)))
                    end) cached ([], remaining_after_uncached)
              in results end

        val entries = rev uncached_entries @ rev cached_entries
      in (entries, include_warnings @ warnings) end,
    timeout = NONE
  }

fun make_types_callback filter_opt (ctxt_unpack : context_unpacker)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.types",
    arg_schema = unpackPair (ctxt_unpack, arg_schema),
    ret_schema = ret_schema,
    function = fn (context, (target_thy_opt, the_theory_only, exclude, _, _, theories_include, name_contains, limit, _)) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = #1 o Universal_Key.key_of_type ctx
        val space = Context.cases Sign.type_space Proof_Context.type_space ctx
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_pred, include_warnings) = mk_include_filter context theories_include
      in (ns_filter limit key_of space target_name exclude_set include_pred (mk_name_filter name_contains) filter_opt, include_warnings) end,
    timeout = NONE
  }

fun make_classes_callback filter_opt (ctxt_unpack : context_unpacker)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.classes",
    arg_schema = unpackPair (ctxt_unpack, arg_schema),
    ret_schema = ret_schema,
    function = fn (context, (target_thy_opt, the_theory_only, exclude, _, _, theories_include, name_contains, limit, _)) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = #1 o Universal_Key.key_of_class ctx
        val space = Context.cases Sign.class_space Proof_Context.class_space ctx
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_pred, include_warnings) = mk_include_filter context theories_include
      in (ns_filter limit key_of space target_name exclude_set include_pred (mk_name_filter name_contains) filter_opt, include_warnings) end,
    timeout = NONE
  }

fun make_locales_callback filter_opt (ctxt_unpack : context_unpacker)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.locales",
    arg_schema = unpackPair (ctxt_unpack, arg_schema),
    ret_schema = ret_schema,
    function = fn (context, (target_thy_opt, the_theory_only, exclude, _, _, theories_include, name_contains, limit, _)) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = #1 o Universal_Key.key_of_locale ctx
        val space = Locale.locale_space (Context.theory_of ctx)
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_pred, include_warnings) = mk_include_filter context theories_include
      in (ns_filter limit key_of space target_name exclude_set include_pred (mk_name_filter name_contains) filter_opt, include_warnings) end,
    timeout = NONE
  }

fun make_theorem_collection_callback filter_opt (ctxt_unpack : context_unpacker)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.theorem_collection",
    arg_schema = unpackPair (ctxt_unpack, arg_schema),
    ret_schema = ret_schema,
    function = fn (context, (target_thy_opt, the_theory_only, exclude, _, _, theories_include, name_contains, limit, _)) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = #1 o Universal_Key.key_of_theorem_collection ctx
        val ctxt = Context.cases Proof_Context.init_global I ctx
        val facts = Proof_Context.facts_of ctxt
        val space = Facts.space_of facts
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_pred, include_warnings) = mk_include_filter context theories_include
        val name_filter = mk_name_filter name_contains
        (* Any dynamic fact is a theorem collection (a named_theorems or a raw
           add_thms_dynamic collection like derivative_eq_intros); Facts.is_dynamic
           is a cheap, no-content prefilter that identifies all of them. *)
        val extra_filter = fn name =>
          name_filter name andalso Facts.is_dynamic facts name
      in (ns_filter limit key_of space target_name exclude_set include_pred extra_filter filter_opt, include_warnings) end,
    timeout = NONE
  }

fun make_methods_callback filter_opt (ctxt_unpack : context_unpacker)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.methods",
    arg_schema = unpackPair (ctxt_unpack, arg_schema),
    ret_schema = ret_schema,
    function = fn (context, (target_thy_opt, the_theory_only, exclude, _, _, theories_include, name_contains, limit, _)) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val target_name = Context.theory_long_name (Context.theory_of ctx)
        val key_of = #1 o Universal_Key.key_of_method ctx
        val space = Method.method_space ctx
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_pred, include_warnings) = mk_include_filter context theories_include
      in (ns_filter limit key_of space target_name exclude_set include_pred (mk_name_filter name_contains) filter_opt, include_warnings) end,
    timeout = NONE
  }

fun make_theory_long_name_callback (ctxt_unpack : context_unpacker)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.the_theory_long_name",
    arg_schema = ctxt_unpack,
    ret_schema = packString,
    function = fn context =>
      Context.theory_long_name (Context.theory_of context),
    timeout = NONE
  }

fun make_theory_long_name_and_path_callback (ctxt_unpack : context_unpacker)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = "Context.theory_long_name_and_path",
    arg_schema = unpackPair (ctxt_unpack, unpackString),
    ret_schema = packPair (packString, packString),
    function = fn (context, name) =>
      let
        val thy = Theory_Hash.resolve_theory context name
        val thy_name = Context.theory_long_name thy
        val master_dir = Resources.master_directory thy
        val thy_base = Long_Name.base_name thy_name
        val thy_file = Path.ext "thy" (master_dir + Path.basic thy_base)
        val file_path = File.platform_path (File.full_path master_dir thy_file)
      in (thy_name, file_path) end,
    timeout = NONE
  }

(* Introduction / elimination rule callbacks.
   The extract_thms function is provided by the caller (requires Classical from HOL). *)
local
fun make_rules_callback cb_name key_of extract_thms filter_opt (ctxt_unpack : context_unpacker)
    : Remote_Procedure_Calling.callback' =
  Remote_Procedure_Calling.mk_callback {
    name = cb_name,
    arg_schema = unpackPair (ctxt_unpack, arg_schema),
    ret_schema = ret_schema,
    function = fn (context, (target_thy_opt, the_theory_only, exclude,
                    term_pat_strs, type_pat_strs, theories_include, name_contains, limit,
                    target_type_str)) =>
      let
        val ctx = resolve_ctx context target_thy_opt
        val thy = Context.theory_of ctx
        val target_base = Context.theory_base_name thy
        val target_prefix = target_base ^ "."
        val thms = extract_thms ctx
        val exclude_set = if the_theory_only then NONE
                          else SOME (Strhashtab.make_set exclude)
        val (include_pred, include_warnings) = mk_include_filter context theories_include
        val fact_space = Facts.space_of
              (Context.cases Global_Theory.facts_of Proof_Context.facts_of ctx)
        val seen : unit Strhashtab.table = Strhashtab.empty 128
        val key_seen = Bytehashtab.empty 128
        val ctxt = Context.cases Proof_Context.init_global I ctx
        val (term_pats, type_pats, warnings) = parse_patterns ctx (term_pat_strs, type_pat_strs)
        val thm_matches = mk_thm_pattern_matcher ctxt term_pats type_pats
        val (target_type_opt, target_type_warnings) = parse_target_type ctx target_type_str
        val target_type_filter = mk_target_type_filter ctx target_type_opt
        val name_filter = mk_name_filter name_contains
        val (entries, _) = fold (fn thm => fn (acc, remaining) =>
          if remaining = 0 then (acc, 0)
          else
          let val thm = Thm.transfer thy thm
          in if not (Thm.has_name_hint thm) then (acc, remaining)
             else
          let
            val name = Thm.get_name_hint thm
            val name_str = Thm_Name.print name
          in if Strhashtab.defined seen name_str then (acc, remaining)
             else
               let
                 (* the_entry is keyed on the bare fact name, not the index *)
                 val entry_opt = try (Name_Space.the_entry fact_space) (#1 name)
                 val thy_name_of = case entry_opt of
                     SOME e => (case #theory_long_name e of "" => NONE | tn => SOME tn)
                   | NONE => NONE
                 val pass = case exclude_set of
                     NONE => String.isPrefix target_prefix name_str
                   | SOME es => (case thy_name_of of
                         SOME tn => not (Strhashtab.defined es tn)
                       | NONE => true)
                 val pass_include = case thy_name_of of
                     SOME tn => include_pred tn
                   | NONE => true
                 (* Filters ordered cheap-to-expensive: target_type_filter walks
                    the whole prop with bidir typ_instance per schematic Var,
                    so push it after the infra filter_opt. *)
                 fun check_filter_opt () = case filter_opt of
                       NONE => true
                     | SOME f => f (name_str, thm)
               in if not pass orelse not pass_include then (acc, remaining)
                  else if not (name_filter name_str) then (acc, remaining)
                  else if not (check_filter_opt ()) then (acc, remaining)
                  else if not (thm_matches thm) then (acc, remaining)
                  else if not (target_type_filter thm) then (acc, remaining)
                  else
                    let val k = key_of ctx thm
                        val epos = case entry_opt of
                            SOME e => entry_def_pos e | NONE => ("", 0, 0)
                    in (Strhashtab.update seen (name_str, ());
                        if Bytehashtab.defined key_seen k then (acc, remaining)
                        else (Bytehashtab.update key_seen (k, ());
                              ((k, name_str, epos) :: acc, remaining - 1)))
                    end
               end
          end
          end) thms ([], limit)
      in (rev entries, include_warnings @ warnings @ target_type_warnings) end,
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
