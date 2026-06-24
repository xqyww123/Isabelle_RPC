signature RPC_PRETTY = sig

type pp_name = string

val trim_markup : string -> string

val pack_raw_term : term MessagePackBinIO.Pack.packer
val unpack_raw_term : term MessagePackBinIO.Unpack.unpacker
val pack_raw_typ : typ MessagePackBinIO.Pack.packer
val unpack_raw_typ : typ MessagePackBinIO.Unpack.unpacker

val string_of_term : pp_name -> Context.generic -> term -> string
val term_string : Context.generic -> term MessagePackBinIO.Pack.packer
val s_expression : term -> string
val s_expression_packer : term MessagePackBinIO.Pack.packer
val s_expr_typ : typ -> string list -> string list

val term_packer : pp_name -> Context.generic -> term MessagePackBinIO.Pack.packer
val typ_packer  : pp_name -> Context.generic -> typ  MessagePackBinIO.Pack.packer
val pos_packer  : Position.T MessagePackBinIO.Pack.packer

type printing_config = {
        all_typ: bool, bv_typ: bool, constant_typ: bool,
        free_typ: bool, num_typ: bool, sorting: bool,
        show_type_P: real option (*probabilistically show types, under the control of the above flags*),
        show_sort_P: real option (*probabilistically show sorts, under the control of the above flags*)
     }

val print_term   : printing_config -> Proof.context -> term -> string
val print_typ    : printing_config -> Proof.context -> typ  -> string

val string_of_var : indexname -> string
val thm_packer : pp_name -> Context.generic -> thm MessagePackBinIO.Pack.packer

end

structure RPC_Pretty : RPC_PRETTY = struct

type printing_config = {
        all_typ: bool, bv_typ: bool, constant_typ: bool,
        free_typ: bool, num_typ: bool, sorting: bool,
        show_type_P: real option (*probabilistically show types, under the control of the above flags*),
        show_sort_P: real option (*probabilistically show sorts, under the control of the above flags*)
     }
exception XML_DUMP_FAIL of XML.tree

fun trim_markup msg =
  let fun auto _ [] = []
        | auto acc (#"\005" :: L) = auto (not acc) L
        | auto true (x :: L) = x :: auto true L
        | auto false (_ :: L) = auto false L
   in String.implode (auto true (String.explode msg))
  end

fun is_number s =
  if s = "."
  then false
  else let
      val len = String.size s
      val i = Unsynchronized.ref 0
      val ret = Unsynchronized.ref true
   in while !ret andalso !i < len do
        let val c = String.sub (s, !i)
         in ( if c = #"." orelse c = #"-" orelse c = #"~" orelse Char.isDigit c
            then ()
            else ret := false )
          ; i := !i + 1
        end
     ; !ret
  end


fun random () =
  let val m = 0w2147483647  (* 2^31 - 1 *)
      val a = 0w16807       (* multiplier *)
      val seed = Unsynchronized.ref (a * Word64.fromLargeInt (Time.toNanoseconds (Time.now())) mod m)
  in fn () =>
        let val s = !seed
            val next = (a * s) mod m
         in seed := next;
            Real.fromInt (Word64.toInt next) / 2147483647.0
        end
  end


fun print_xml {bv_typ, num_typ, free_typ, constant_typ, all_typ, sorting, show_type_P, show_sort_P}
              {floating, selected, sort_names} body =
  let val show_type =
            case show_type_P of SOME P => let val rand = random ()
                                           in fn () => rand () <= P
                                          end
                              | NONE => K true
      val bv_typ = bv_typ orelse all_typ
      val sorting =
            if sorting
            then (case show_sort_P of SOME P => let val rand = random ()
                                                 in fn () => rand () <= P
                                                end
                                    | NONE => K true)
            else K false
      val num_typ = num_typ orelse all_typ
      val free_typ = free_typ orelse all_typ
      val constant_typ = constant_typ orelse all_typ

      open XML
      type ty = tree
      datatype IR = TEXT of string
                  | TYPING of ty * IR list
                  | SORTING of ty * IR list
                  | NUMBER of string
                  | FREE of string
                  | BOUND of string
                  | CONSTANT of {name: string, full_name: string}
                  | CLASS of {name: string, full_name: string}
                  | TYPE  of {name: string, full_name: string}

      (* Isabelle2025-2 nests inner-syntax markup (Markup.tconst/const/...)
         inside entity/tfree/... wrappers, e.g.
         <entity kind="type_name" ...><tconst>nat</tconst></entity>.
         Unwrap the whole Markup family (tclass tconst tfree tvar const
         free skolem bound var improper numeral) transparently. *)
      val transparent_wrappers =
        ["block", "delimiter", "literal", "tclass", "tconst", "tfree",
         "tvar", "const", "free", "skolem", "bound", "var", "improper",
         "numeral"]
      fun one_str (x as Elem ((name, _), [y])) =
            if member (op =) transparent_wrappers name then one_str y
            else raise XML_DUMP_FAIL x
        | one_str (Text s) = s
        | one_str x = raise XML_DUMP_FAIL x

      val lookup = AList.lookup (op =)
      val lookup' = the_default "" oo lookup
      fun dump_xml (Text s) ret =
            if is_number s
            then NUMBER s :: ret
            else TEXT s :: ret
        | dump_xml (Elem (("break", _), _)) ret = TEXT " " :: ret
        | dump_xml (Elem (("tfree", _), [x])) ret = FREE (one_str x) :: ret
        | dump_xml (Elem (("tvar", _), [x])) ret = FREE (one_str x) :: ret
        | dump_xml (Elem (("free", _), [x])) ret = FREE (one_str x) :: ret
        | dump_xml (Elem (("bound", _), [x])) ret = BOUND (one_str x) :: ret
        | dump_xml (origin as Elem (("entity", attrs), [x])) ret =
           (case lookup attrs "kind"
              of SOME "class" => CLASS {name = one_str x, full_name = lookup' attrs "name"}
               | SOME "constant" =>
                    let val name = one_str x
                     in case name
                     of "0" => NUMBER "0"
                      | "1" => NUMBER "1"
                      | _ => CONSTANT {name = name, full_name = lookup' attrs "name"}
                    end
               | SOME "type_name" => TYPE {name = one_str x, full_name = lookup' attrs "name"}
               (* Isabelle2025-2 wraps fixed variables in entity markup
                  (<entity kind="fixed"><free>x</free></entity>); 2024 emitted
                  the bare <free> element. *)
               | SOME "fixed" => FREE (one_str x)
               | _ => raise XML_DUMP_FAIL origin
           ) :: ret
        | dump_xml (Elem (("xml_elem", [("xml_name", "typing")]), [typ, term])) ret =
            TYPING (typ, dump_xml term []) :: ret
        | dump_xml (Elem (("xml_elem", [("xml_name", "sorting")]), [typ, term])) ret =
            SORTING (typ, dump_xml term []) :: ret
        | dump_xml (Elem (_, children)) ret = fold dump_xml children ret

      (* tfree/tvar names occurring textually inside an XML type tree *)
      fun xml_tvar_names tree =
        let fun txt (Text s) = s | txt (Elem (_, [c])) = txt c | txt _ = ""
            fun go (t as Elem ((nm, _), cs)) acc =
                  if nm = "tfree" orelse nm = "tvar" then txt t :: acc else fold go cs acc
              | go (Text _) acc = acc
        in go tree [] end

      fun dump_ir ir =
        let fun pass [] ret = ret
              | pass (TYPING (ty, [NUMBER tm]) :: oth) ret =
                  if num_typ andalso show_type ()
                  then "(" :: tm :: " :: " :: dump_ir (dump_xml ty []) @ ")"
                           :: pass oth ret
                  else tm :: pass oth ret
              | pass (TYPING (ty, [FREE tm]) :: oth) ret =
                  if free_typ andalso show_type ()
                  then "(" :: tm :: " :: " :: dump_ir (dump_xml ty []) @ ")"
                    :: pass oth ret
                  else tm :: pass oth ret
              | pass (TYPING (ty, [CONSTANT {name, full_name}]) :: oth) ret =
                  (* show a constant's type when constant_typ asks for it OR when
                     it is a selected carrier of a floating type variable (a tvar
                     anchored to no term variable -- otherwise invisible). *)
                  if (constant_typ orelse
                       (member (op =) selected full_name
                        andalso exists (member (op =) floating) (xml_tvar_names ty)))
                     andalso show_type ()
                  then "(" :: name :: " :: " :: dump_ir (dump_xml ty []) @ ")"
                    :: pass oth ret
                  else name :: pass oth ret
              | pass (TYPING (ty, [BOUND tm]) :: CONSTANT {name=".",...} :: oth) ret =
                  if bv_typ andalso show_type ()
                  then "(" :: tm :: " :: " :: dump_ir (dump_xml ty []) @ ")."
                           :: pass oth ret
                  else tm :: "." :: pass oth ret
              | pass (TYPING (ty, [BOUND tm]) :: TEXT "." :: oth) ret =
                  if bv_typ andalso show_type ()
                  then "(" :: tm :: " :: " :: dump_ir (dump_xml ty []) @ ")."
                           :: pass oth ret
                  else tm :: "." :: pass oth ret
              | pass (TEXT s :: oth) ret = s :: pass oth ret
              | pass (TYPING (ty, tm) :: oth) ret =
                  if all_typ andalso show_type ()
                  then "(" :: pass tm [] @ " :: " :: dump_ir (dump_xml ty []) @ ")"
                           :: pass oth ret
                  else pass (tm @ oth) ret
              | pass (SORTING (s, tm) :: oth) ret =
                  (* keep a sort when sorting asks for it OR when this tvar is a
                     floating one with a NON-trivial sort (sort_names). *)
                  if sorting () orelse
                     (case tm of [FREE nm] => member (op =) sort_names nm | _ => false)
                  then "(" :: pass tm [] @ " :: " :: dump_ir (dump_xml s []) @ ")"
                           :: pass oth ret
                  else pass (tm @ oth) ret
              | pass (NUMBER s :: oth) ret = s :: pass oth ret
              | pass (FREE s :: oth) ret = s :: pass oth ret
              | pass (BOUND s :: oth) ret = s :: pass oth ret
              | pass (CONSTANT {name, ...} :: oth) ret = name :: pass oth ret
              | pass (CLASS {name, ...} :: oth) ret = name :: pass oth ret
              | pass (TYPE {name, ...} :: oth) ret = name :: pass oth ret
         in pass (rev ir) []
        end
   in String.concat (dump_ir (fold dump_xml body []))
  end

(* A "floating" type variable is one that occurs in NO term variable's type
   (Free/Var/bound), i.e. it exists only because of a polymorphic CONSTANT and is
   therefore invisible in the default type-suppressing rendering -- the silent
   under-constraint that makes e.g. `filterlim harm at_top sequentially` (harm ::
   nat => 'a, 'a unpinned) look fine yet be unprovable.  We surface it by:
     - selecting a minimal set of carrier constants (head-excluding greedy cover)
       whose printed types make every floating tvar appear at least once, and
     - showing the sort of a floating tvar only when it is non-trivial.
   No floating tvar  ==>  empty result  ==>  rendering is unchanged (self-gating).
   TFree names match the markup directly; TVar (schematic, in stored/library
   lemmas) is rendered to its display form via `string_of_vname` to match. *)
val no_floating = {floating = [] : string list, selected = [] : string list,
                   sort_names = [] : string list}

fun floating_info t =
  let
    val all_tv =
      Term.add_tfrees t [] @ map (apfst Term.string_of_vname) (Term.add_tvars t [])
  in
    if null all_tv then no_floating   (* fast path: no type variables at all *)
    else
    let
      fun tvs_of_typ T =
        Term.add_tfreesT T [] @ map (apfst Term.string_of_vname) (Term.add_tvarsT T [])
      fun names_of_typ T = map fst (tvs_of_typ T)
      fun anch (Free (_,T)) acc = fold (insert (op =)) (names_of_typ T) acc
        | anch (Var (_,T)) acc  = fold (insert (op =)) (names_of_typ T) acc
        | anch (Abs (_,T,b)) acc = anch b (fold (insert (op =)) (names_of_typ T) acc)
        | anch (f $ x) acc = anch x (anch f acc)
        | anch _ acc = acc
      val anchored = anch t []
      val floating0 = filter (fn (n,_) => not (member (op =) anchored n)) all_tv
      val floating = map fst floating0
      (* a sort is trivial iff it is a subset of {type} (the universal HOL sort) *)
      val sort_names =
        map fst (filter (fn (_,s) => not (subset (op =) (s, ["HOL.type"]))) floating0)
      fun inter' xs ys = filter (fn x => member (op =) ys x) xs
      (* carrier constant occurrences in L-to-R order, tagged with whether THIS
         occurrence sits in function/head position (applied to >= 1 argument). *)
      val carriers =
        let val acc = Unsynchronized.ref []
            fun go applied (Const (c,T)) =
                  let val cov = inter' floating (names_of_typ T)
                  in if null cov then () else acc := (c, cov, applied) :: !acc end
              | go _ (Abs (_,_,b)) = go false b
              | go _ (f $ x) = (go true f; go false x)
              | go _ _ = ()
        in go false t; rev (!acc) end
      val carriers_i = map_index I carriers
      (* greedy set cover; prefer (1) non-head occurrence, (2) wider coverage,
         (3) leftmost.  Heads remain a last resort, never excluded outright. *)
      fun select remaining acc =
        if null remaining then rev acc else
        let val cands = map_filter (fn (i,(c,cov,ap)) =>
                  let val g = inter' remaining cov
                  in if null g then NONE else SOME (i, c, cov, length g, ap) end) carriers_i
        in if null cands then rev acc
           else let val (_,c,cov,_,_) =
                      hd (sort (fn ((i1,_,_,g1,a1),(i2,_,_,g2,a2)) =>
                            if a1 <> a2 then bool_ord (a1,a2)
                            else if g1 <> g2 then int_ord (g2,g1)
                            else int_ord (i1,i2)) cands)
                in select (filter (fn x => not (member (op =) cov x)) remaining) (c::acc) end
        end
      val selected = select floating []
    in {floating = floating, selected = selected, sort_names = sort_names} end
  end

fun print_term cfg ctxt =
  let val ctxt = ctxt
        |> Config.put Printer.show_markup true
        |> Config.put Printer.show_types false
        |> Config.put Printer.show_sorts false
   in fn term =>
        print_xml cfg (floating_info term)
          (YXML.parse_body (Syntax.string_of_term ctxt term))
  end

fun print_typ cfg ctxt =
  let val ctxt = ctxt
        |> Config.put Printer.show_markup true
        |> Config.put Printer.show_types false
        |> Config.put Printer.show_sorts false
   in fn typ => print_xml cfg no_floating (YXML.parse_body (Syntax.string_of_typ ctxt typ))
  end


type pp_name = string

local open MessagePackBinIO.Pack  MessagePackBinIO.Unpack in

fun pack_raw_typ (Type data) =
      packPair (packInt, packPair (packString, packList pack_raw_typ)) (0, data)
  | pack_raw_typ (TFree data) =
      packPair (packInt, packPair (packString, packList packString)) (1, data)
  | pack_raw_typ (TVar ((n,i),s)) =
      packPair (packInt, packTuple3 (packString, packInt, packList packString)) (2, (n,i,s))

fun unpack_raw_typ s =
      unpackPair_dep' unpackInt (
        fn 0 => unpackPair (unpackString, unpackList unpack_raw_typ)
             #> apfst Type
         | 1 => unpackPair (unpackString, unpackList unpackString)
             #> apfst TFree
         | 2 => unpackTuple3 (unpackString, unpackInt, unpackList unpackString)
             #> apfst (fn (n,i,s) => TVar ((n,i),s))
         | _ => raise Unpack) s

fun pack_raw_term (Const data) =
      packPair (packInt, packPair (packString, pack_raw_typ)) (3, data)
  | pack_raw_term (Free data) =
      packPair (packInt, packPair (packString, pack_raw_typ)) (4, data)
  | pack_raw_term (Var ((n,i),t)) =
      packPair (packInt, packTuple3 (packString, packInt, pack_raw_typ)) (5, (n,i,t))
  | pack_raw_term (Bound data) =
      packPair (packInt, packInt) (6, data)
  | pack_raw_term (Abs data) =
      packPair (packInt, packTuple3 (packString, pack_raw_typ, pack_raw_term)) (7, data)
  | pack_raw_term (A $ B) =
      packPair (packInt, packPair (pack_raw_term, pack_raw_term)) (8, (A,B))

fun unpack_raw_term s =
      unpackPair_dep' unpackInt (
        fn 3 => unpackPair (unpackString, unpack_raw_typ)
             #> apfst Const
         | 4 => unpackPair (unpackString, unpack_raw_typ)
             #> apfst Free
         | 5 => unpackTuple3 (unpackString, unpackInt, unpack_raw_typ)
             #> apfst (fn (n,i,s) => Var ((n,i),s))
         | 6 => unpackInt #> apfst Bound
         | 7 => unpackTuple3 (unpackString, unpack_raw_typ, unpack_raw_term)
             #> apfst Abs
         | 8 => unpackPair (unpack_raw_term, unpack_raw_term)
             #> apfst (fn (A,B) => A $ B)
         | _ => raise Unpack) s

end

local open MessagePackBinIO.Pack in

fun string_of_var (s,i) =
      if i = ~1 then s
      else if size(s) = 0 orelse Char.isDigit (String.sub (s, size(s)-1))
      then "?" ^ s ^ "." ^ string_of_int i
      else "?" ^ s  ^ string_of_int i

val pack_var = packString o string_of_var

fun pos_packer pos =
  let open MessagePackBinIO.Unpack MessagePackBinIO.Pack
      val {line, offset, end_offset, props} = Position.dest pos
      val {label, file, id} = props
   in packTuple4 (packInt, packInt, packInt, packTuple3 (packString, packString, packString))
      (line, offset, end_offset, (label, file, id))
  end

fun term_string ctxt =
  packString o trim_markup o Context.cases Syntax.string_of_term_global Syntax.string_of_term ctxt

fun s_expr_typ (TFree (name, sort)) ret = "(var " :: name :: fold_rev (fn C => fn L => " "::C::L) sort (")"::ret)
  | s_expr_typ (TVar  (name, sort)) ret = "(var " :: string_of_var name :: fold_rev (fn C => fn L => " "::C::L) sort (")"::ret)
  | s_expr_typ (Type  (name, typs)) ret =
      if null typs
      then name::ret
      else "(" :: name :: fold_rev (fn T => fn L => " " :: s_expr_typ T L) typs (")"::ret)

fun s_expr ret bvs ctxt term =
  let val (head, args) = Term.strip_comb term
      val nopara = null args andalso (case head of Bound _ => true | _ => false)
      val ret = if nopara then ret else ")" :: ret
   in (
    case head
      of Const (name, ty) => (name :: " " :: s_expr_typ ty (out_args ret bvs ctxt args))
       | Free (name, ty) => ("var " :: name :: " " :: s_expr_typ ty (out_args ret bvs ctxt args))
       | Var (name, ty) => ("var " :: string_of_var name :: " " :: s_expr_typ ty (out_args ret bvs ctxt args))
       | Abs (triple as (name, ty,body)) =>
          if null args
          then let val (name',ctxt') = Name.variant name ctxt
                in ("(\<lambda> " :: name :: " " :: s_expr_typ ty (" " :: s_expr (")"::ret) (name'::bvs) ctxt' body))
               end
          else s_expr (out_args ret bvs ctxt args) bvs ctxt (Abs triple)
       | Bound i => (nth bvs i :: " " :: out_args ret bvs ctxt args)
       | _ $ _ => error "impossible")
   |> (fn L => if nopara then L else "(" :: L)
  end
and out_args ret bvs ctxt args = fold_rev (fn x => fn ret => (" " :: s_expr ret bvs ctxt x)) args ret

fun s_expression term = String.concat (s_expr [] [] Name.context term)
val s_expression_packer = packString o s_expression

(*
  Term Formatting Options
  ========================

  The string_of_term function provides multiple formatting options for pretty-printing
  Isabelle terms. Each format is identified by a string name and configures the Isabelle
  pretty printer with different settings.

  Fully Qualified Name: RPC_Pretty.string_of_term : string -> Context.generic -> term -> string

  Usage from Isabelle/ML:
    val formatter = RPC_Pretty.string_of_term "pretty"
    val term_str = formatter ctxt my_term

  Available Formats:

  1. "sexpr" - S-expression format showing full internal term structure
     Example: (Const "Groups.plus" (Type "fun" [...]))

  2. "natural" - Uses context's natural printing settings (show_markup = false)
     Example: x + y  (depends on context configuration)

  3. "oridinary" (alias: "pretty") - Standard pretty-printing without type annotations
     Config: show_types=false, show_sorts=false, show_types_nv=false
     Example: x + y

  4. "pretty" - Alias for "oridinary"

  5. "type" (alias: "typed_pretty") - Pretty-printing with type annotations
     Config: show_types=true, show_sorts=false, show_types_nv=false
     Example: (x + y) :: nat

  6. "typed_pretty" - Alias for "type"

  7. "type_sort" - Intended for types with sorts (currently identical to "type")
     Config: show_types=true, show_sorts=false, show_types_nv=false
     NOTE: This appears to be incomplete; show_sorts should be true for sort annotations
     Example: (x + y) :: nat  (sorts not shown)

  8. "type_nv" (alias: "typed-nv_pretty") - Types shown on non-variables too
     Config: show_types=true, show_sorts=false, show_types_nv=true
     Example: (x + y) :: nat  (with more type annotations on subterms)

  9. "typed-nv_pretty" - Alias for "type_nv"

  10. "T4S4" - Probabilistic format: 40% chance types, 40% chance sorts (for training data)
      Config: show_types (40% prob), show_sorts (40% prob if types shown), show_types_nv=false
      Example: Randomly either "x + y" or "(x + y) :: nat" or "(x + y) :: nat::type"

  11. "T4S4nv" - Like T4S4 but with show_types_nv = show_types
      Config: show_types (40% prob), show_sorts (40% prob), show_types_nv = show_types

  12. "T2S3" - Probabilistic format: 20% chance types, 30% chance sorts (for training data)
      Config: show_types (20% prob), show_sorts (30% prob if types shown), show_types_nv=false

  13. "T2S3nv" - Like T2S3 but with show_types_nv = show_types
      Config: show_types (20% prob), show_sorts (30% prob), show_types_nv = show_types

  Recommended for User-Facing Output: "pretty", "typed_pretty", "sexpr"
  Recommended for ML Training Data: "T4S4", "T4S4nv", "T2S3", "T2S3nv"
*)

fun string_of_term "sexpr" = (fn _ => s_expression)
  | string_of_term "natural" = (fn ctxt =>
      let val ctxt = Config.put_generic Printer.show_markup false ctxt
       in Context.cases Syntax.string_of_term_global Syntax.string_of_term ctxt
       #> trim_markup
      end)
  | string_of_term "oridinary" = (fn ctxt =>
      let val ctxt = ctxt
                |> Config.put_generic Printer.show_types false
                |> Config.put_generic Printer.show_sorts false
             (* |> Config.put_generic Printer.show_types_nv false *)
                |> Config.put_generic Printer.show_markup false
                |> Config.put_generic Printer.show_structs false
                |> Config.put_generic Printer.show_question_marks true
             (* |> Config.put_generic Printer.show_brackets false *)
       in Context.cases Syntax.string_of_term_global Syntax.string_of_term ctxt
       #> trim_markup
      end)
  | string_of_term "pretty" = string_of_term "oridinary"
  | string_of_term "type" = (fn ctxt =>
      let val ctxt = ctxt
                |> Config.put_generic Printer.show_types true
                |> Config.put_generic Printer.show_sorts false
             (*|> Config.put_generic Printer.show_types_nv false *)
                |> Config.put_generic Printer.show_markup false
                |> Config.put_generic Printer.show_structs false
                |> Config.put_generic Printer.show_question_marks true
             (* |> Config.put_generic Printer.show_brackets false *)
       in Context.cases Syntax.string_of_term_global Syntax.string_of_term ctxt
       #> trim_markup
      end)
  | string_of_term "typed_pretty" = string_of_term "type"
  | string_of_term "type_sort" = (fn ctxt =>
      let val ctxt = ctxt
                |> Config.put_generic Printer.show_types true
                |> Config.put_generic Printer.show_sorts false
             (* |> Config.put_generic Printer.show_types_nv false *)
                |> Config.put_generic Printer.show_markup false
                |> Config.put_generic Printer.show_structs false
                |> Config.put_generic Printer.show_question_marks true
             (* |> Config.put_generic Printer.show_brackets false *)
       in Context.cases Syntax.string_of_term_global Syntax.string_of_term ctxt
       #> trim_markup
      end)
  | string_of_term "type_nv" = (fn ctxt =>
      let val ctxt = ctxt
                |> Config.put_generic Printer.show_types true
                |> Config.put_generic Printer.show_sorts false
             (* |> Config.put_generic Printer.show_types_nv true *)
                |> Config.put_generic Printer.show_markup false
                |> Config.put_generic Printer.show_structs false
                |> Config.put_generic Printer.show_question_marks true
             (* |> Config.put_generic Printer.show_brackets false *)
       in Context.cases Syntax.string_of_term_global Syntax.string_of_term ctxt
       #> trim_markup
      end)
  | string_of_term "typed-nv_pretty" = string_of_term "type_nv"
  | string_of_term "T4S4" =
      let val rand = random ()
       in fn ctxt =>
      let val show_type = rand () <= 0.4
          val show_sort = show_type andalso rand () <= 0.4
          val ctxt = ctxt
                |> Config.put_generic Printer.show_types show_type
                |> Config.put_generic Printer.show_sorts show_sort
             (* |> Config.put_generic Printer.show_types_nv false *)
                |> Config.put_generic Printer.show_markup false
                |> Config.put_generic Printer.show_structs false
                |> Config.put_generic Printer.show_question_marks true
             (* |> Config.put_generic Printer.show_brackets false *)
       in Context.cases Syntax.string_of_term_global Syntax.string_of_term ctxt
       #> trim_markup
      end
      end
  | string_of_term "T4S4nv" =
      let val rand = random ()
       in fn ctxt =>
      let val show_type = rand () <= 0.4
          val show_sort = show_type andalso rand () <= 0.4
          val ctxt = ctxt
                |> Config.put_generic Printer.show_types show_type
                |> Config.put_generic Printer.show_sorts show_sort
             (* |> Config.put_generic Printer.show_types_nv show_type *)
                |> Config.put_generic Printer.show_markup false
                |> Config.put_generic Printer.show_structs false
                |> Config.put_generic Printer.show_question_marks true
             (* |> Config.put_generic Printer.show_brackets false *)
       in Context.cases Syntax.string_of_term_global Syntax.string_of_term ctxt
       #> trim_markup
      end
      end
  | string_of_term "T2S3" =
      let val rand = random ()
       in fn ctxt =>
      let val show_type = rand () <= 0.2
          val show_sort = show_type andalso rand () <= 0.3
          val ctxt = ctxt
                |> Config.put_generic Printer.show_types show_type
                |> Config.put_generic Printer.show_sorts show_sort
             (* |> Config.put_generic Printer.show_types_nv false *)
                |> Config.put_generic Printer.show_markup false
                |> Config.put_generic Printer.show_structs false
                |> Config.put_generic Printer.show_question_marks true
             (* |> Config.put_generic Printer.show_brackets false *)
       in Context.cases Syntax.string_of_term_global Syntax.string_of_term ctxt
       #> trim_markup
      end
      end
  | string_of_term "T2S3nv" =
      let val rand = random ()
       in fn ctxt =>
      let val show_type = rand () <= 0.2
          val show_sort = show_type andalso rand () <= 0.3
          val ctxt = ctxt
                |> Config.put_generic Printer.show_types show_type
                |> Config.put_generic Printer.show_sorts show_sort
             (* |> Config.put_generic Printer.show_types_nv show_type *)
                |> Config.put_generic Printer.show_markup false
                |> Config.put_generic Printer.show_structs false
                |> Config.put_generic Printer.show_question_marks true
             (* |> Config.put_generic Printer.show_brackets false *)
       in Context.cases Syntax.string_of_term_global Syntax.string_of_term ctxt
       #> trim_markup
      end
      end
  | string_of_term name = (fn _ =>
      error ("Unknown term printer " ^ name
              ^ ". Known printers: ['sexpr', 'pretty', 'typed_pretty']"))


fun term_packer "sexpr" _ = s_expression_packer
  | term_packer "pretty" ctxt = term_string ctxt
(*  | term_packer "typed-nv_pretty" ctxt =
      let val ctxt = Config.put_generic Printer.show_types true ctxt
                  |> Config.put_generic Printer.show_types_nv true
       in term_string ctxt
      end *)
  | term_packer "typed_pretty" ctxt =
      let val ctxt = Config.put_generic Printer.show_types true ctxt
       in term_string ctxt
      end
  | term_packer name _ =
      error ("Unknown term printer " ^ name
              ^ ". Known printers: ['sexpr', 'pretty', 'typed_pretty']")

fun pretty_typ ctxt =
      packString o trim_markup o Context.cases Syntax.string_of_typ_global Syntax.string_of_typ ctxt

fun typ_packer "sexpr" _ = (fn typ => packString (String.concat (s_expr_typ typ [])))
  | typ_packer "pretty" ctxt = pretty_typ ctxt
  | typ_packer "typed_pretty" ctxt = pretty_typ ctxt
  | typ_packer "typed-nv_pretty" ctxt = pretty_typ ctxt
  | typ_packer name _ =
      error ("Unknown typ printer " ^ name ^ ". Known printers: ['sexpr', 'pretty']")

fun thm_packer s_expr ctxt = term_packer s_expr ctxt o Thm.prop_of

end

end
