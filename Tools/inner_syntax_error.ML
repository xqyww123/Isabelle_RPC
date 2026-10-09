(* Inner_Syntax_Error: turn an opaque Isabelle inner-syntax parse error into a
   precise, agent-facing message that marks the failing spot with a
   【parsing fails here】 marker.

   Mechanism: Isabelle's `Syntax.read_*` on a bare string carries Position.none,
   so the error renders `at ""` with no offset.  Feeding the SAME string as a
   positioned `Input.source` (via `Syntax.implode_input`) makes the parser emit a
   `<position offset=k end_offset=k' id=ID>` in the error message (symbol-indexed,
   1-based).  We extract that offset and splice a 【parsing fails here】 marker at
   the failing token's start in the original string, showing only a unique,
   word-aligned window around it.  The error body also
   carries (under the SAME id) a `<token_range>` per token (each spanning that
   token's real offsets) and a trailing `<bad offset="1">`; filtering by element
   NAME = "position" — not by id/offset — is what isolates the one wanted element.

   IMPORTANT: positioned input perturbs schematic type-variable indices (e.g. a
   type-check error prints ??'a13 instead of ??'a), so it must NEVER be used to
   produce the value a proof consumes.  The real read/op always runs on the PLAIN
   string; positioned input is used ONLY as a throwaway probe to locate a parse
   failure.  Only inner-syntax PARSE errors carry a position; type/check errors
   and "unexpected end of input" do not, and are passed through unchanged.

   The position markup, and hence the marker, appears only under the PIDE
   print mode (Print_Mode.PIDE), which the REPL, PIDE and build all set. *)

signature INNER_SYNTAX_ERROR = sig
  (* The pieces for another reader that marks its own failures the same way
     (AoA's reader of method text): the marker, which a caller also uses to
     compare a marked message exactly; the window of the text around a 1-based
     symbol range with the marker spliced in; and the LAST <position> of an
     error message (an outer-syntax error names the cut's start first and the
     offending token last). *)
  val marker : string
  val mark_window : string -> int * int -> string option
  val last_offset : (string -> bool) -> string -> (int * int) option
  val sentinel_id : string
  val positioned_id : string -> string -> string
  val positioned : string -> string
  (* format {ignored} lookup raw_error_message:
       lookup maps a position-id back to the ORIGINAL (un-imploded) string.
       ignored = SOME noun prepends "<noun> pattern was ignored ..." (the query
       path: noun is "Term"/"Type"); NONE prepends nothing.
       Returns SOME marked-message when the error carries a usable <position>
       under one of lookup's ids, else NONE (caller keeps the original text). *)
  val format : {ignored: string option} -> (string -> string option) -> string -> string option
  (* marker_strings rd ctxt strs: parse each string POSITIONED with `rd` (a probe
     only); return the first 【 】-marked message among them, or NONE. *)
  val marker_strings : (Proof.context -> string -> 'b) -> Proof.context -> string list -> string option
  (* guard reprobe f: run the REAL op `f` on plain input; on an all-ERROR failure
     consult `reprobe` for a marker, else re-raise the original exn untouched. *)
  val guard : (unit -> string option) -> (unit -> 'a) -> 'a
  (* Drop-in wrappers: run the real read on the PLAIN string(s); only a parse
     failure is re-probed positioned for the marker (success / type-check errors
     stay byte-identical). The list/typed variants keep JOINT type inference. *)
  val read_positioned :
    (Proof.context -> string -> 'a) -> Proof.context -> string -> 'a
  val read_positioned_list :
    (Proof.context -> string list -> 'a) -> Proof.context -> string list -> 'a
  val read_positioned_typed :
    (Proof.context -> (typ * string) list -> 'a) -> Proof.context -> (typ * string) list -> 'a
end

structure Inner_Syntax_Error : INNER_SYNTAX_ERROR = struct

val sentinel_id = "Minilang.inner_syntax"

(* --- positioned input --------------------------------------------------- *)

fun positioned_id id s =
  Syntax.implode_input (Input.source true s (Position.id id, Position.none))

fun positioned s = positioned_id sentinel_id s

(* --- UTF-8 markers (built at runtime; raw glyphs are illegal in .ML) ----- *)

fun utf8_of_codepoint cp =
  if cp < 0x80 then implode [chr cp]
  else if cp < 0x800 then
    implode (map chr [0xC0 + (cp div 64), 0x80 + (cp mod 64)])
  else if cp < 0x10000 then
    implode (map chr [0xE0 + (cp div 4096),
                      0x80 + ((cp div 64) mod 64),
                      0x80 + (cp mod 64)])
  else
    implode (map chr [0xF0 + (cp div 262144),
                      0x80 + ((cp div 4096) mod 64),
                      0x80 + ((cp div 64) mod 64),
                      0x80 + (cp mod 64)])

val lbrack   = utf8_of_codepoint 0x3010   (* 【 *)
val rbrack   = utf8_of_codepoint 0x3011   (* 】 *)
val ellipsis = utf8_of_codepoint 0x2026   (* … *)
val arrow    = utf8_of_codepoint 0x21B3   (* ↳ *)
val emdash   = utf8_of_codepoint 0x2014   (* — *)

(* single self-explanatory marker spliced at the failing token's start *)
val marker = lbrack ^ "parsing fails here" ^ rbrack

val pointer = arrow ^ " "

fun ignored_prefix noun =
  noun ^ " pattern was ignored " ^ emdash ^ " results are NOT filtered by it."

(* --- offset extraction (filter by element NAME = position) --------------- *)

(* A message that is not well-formed YXML -- one that quotes raw chr 5 / chr 6
   from the text that failed -- decodes to its plain text: no position, no
   markup, so locating a failure never raises. *)
fun decode msg = YXML.parse_body msg handle Fail _ => [XML.Text msg]

(* Every <position> element whose id satisfies id_ok and which carries an
   offset, in document order, each as (id, offset, end_offset); end_offset
   defaults to offset+1. *)
fun parse_offsets id_ok msg =
  let
    fun search [] = []
      | search (XML.Text _ :: rest) = search rest
      | search (XML.Elem ((name, props), body) :: rest) =
          (if name = Markup.positionN then
             let val pos = Position.of_properties props in
               case (Position.id_of pos, Position.offset_of pos) of
                 (SOME id, SOME off) =>
                   if id_ok id then [(id, off, the_default (off + 1) (Position.end_offset_of pos))] else []
               | _ => []
             end
           else []) @ search (body @ rest)
  in search (decode msg) end

fun parse_offset id_ok msg = try hd (parse_offsets id_ok msg)

fun last_offset id_ok msg =
  Option.map (fn (_, off, eoff) => (off, eoff)) (try List.last (parse_offsets id_ok msg))

(* --- clean prose: YXML text minus no_report/position subtrees ------------ *)

fun collect_text skip (XML.Text s) = s
  | collect_text skip (XML.Elem ((name, _), body)) =
      if skip name then "" else String.concat (map (collect_text skip) body)

fun rstrip s =
  let fun drop (#" " :: r) = drop r
        | drop (#"\n" :: r) = drop r
        | drop (#"\t" :: r) = drop r
        | drop r = r
  in String.implode (rev (drop (rev (String.explode s)))) end

fun clean_prose msg =
  rstrip (String.concat (map (collect_text
            (fn n => n = Markup.no_reportN orelse n = Markup.positionN))
          (decode msg)))

(* --- unique window + 【 】 splice ---------------------------------------- *)

fun count_substr pat s =
  let val pl = size pat and sl = size s in
    if pl = 0 then 0
    else
      let fun go i acc =
            if i + pl > sl then acc
            else go (i + 1) (if String.substring (s, i, pl) = pat then acc + 1 else acc)
      in go 0 0 end
  end

fun sublist (xs, a, b) = List.take (List.drop (xs, a), b - a)

(* off/eoff are 1-based symbol indices; returns SOME marked-window, or NONE
   when off is out of range (P15).  off = n + 1 marks the end of the text,
   where an outer-syntax reader finds its end-of-input failures. *)
fun mark_window text (off, eoff) =
  let
    val syms = Symbol.explode text
    val n = length syms
    val lo = off - 1
  in
    if lo < 0 orelse lo > n then NONE
    else
      let
        val hi = Int.min (n, Int.max (lo + 1, eoff - 1))
        val full = implode syms
        fun uniq (a, b) = count_substr (implode (sublist (syms, a, b))) full = 1
        fun expand (a, b) =
          if (b - a >= 26 andalso uniq (a, b)) orelse (a <= 0 andalso b >= n)
          then (a, b)
          else expand (Int.max (0, a - 1), Int.min (n, b + 1))
        (* widen each end to a whitespace boundary so no word is bisected;
           only grows the window, so uniqueness is preserved *)
        fun snap_left a =
          if a > 0 andalso not (Symbol.is_blank (nth syms (a - 1)))
          then snap_left (a - 1) else a
        fun snap_right b =
          if b < n andalso not (Symbol.is_blank (nth syms b))
          then snap_right (b + 1) else b
        val (a0, b0) = expand (lo, hi)
        val a = snap_left a0
        val b = snap_right b0
        val pre  = if a > 0 then ellipsis else ""
        val post = if b < n then ellipsis else ""
        val mid =
          implode (sublist (syms, a, lo)) ^ marker ^ implode (sublist (syms, lo, b))
      in SOME (pre ^ mid ^ post) end
  end

(* --- top-level formatting ----------------------------------------------- *)

fun format {ignored} lookup msg =
  case parse_offset (is_some o lookup) msg of
    NONE => NONE
  | SOME (id, off, eoff) =>
      (case lookup id of
        NONE => NONE
      | SOME orig =>
          (case mark_window orig (off, eoff) of
            NONE => NONE
          | SOME windowed =>
              SOME ((case ignored of SOME noun => ignored_prefix noun ^ "\n" | NONE => "")
                    ^ clean_prose msg ^ "\n  " ^ pointer ^ windowed)))

(* --- exception plumbing -------------------------------------------------- *)

(* SOME msgs iff exn is a bare ERROR or a Par_Exn whose inner exns are all
   ERROR; NONE otherwise (so non-ERROR, incl. Interrupt, is never reformatted). *)
fun dest_errors exn =
  case Par_Exn.dest exn of
    SOME exns =>
      let val msgs = map_filter (fn ERROR m => SOME m | _ => NONE) exns in
        if not (null exns) andalso length msgs = length exns then SOME msgs else NONE
      end
  | NONE => (case exn of ERROR m => SOME [m] | _ => NONE)

fun with_ids xs = List.tabulate (length xs, fn i => sentinel_id ^ "#" ^ string_of_int i)

(* Probe one string by parsing it POSITIONED under `id`; SOME marked-message if it
   carries a usable inner-syntax position, else NONE.  Used ONLY to locate a parse
   failure — never to produce the value the proof uses. *)
fun probe1 rd ctxt (id, s) =
  case Exn.capture (fn () => rd ctxt (positioned_id id s)) () of
    Exn.Res _ => NONE
  | Exn.Exn e =>
      (case dest_errors e of
        NONE => NONE
      | SOME msgs => get_first (format {ignored = NONE} (fn id' => if id' = id then SOME s else NONE)) msgs)

fun marker_strings rd ctxt strs =
  get_first (probe1 rd ctxt) (with_ids strs ~~ strs)

(* Run the REAL operation `f` on the PLAIN string(s) (uncontaminated); only on an
   all-ERROR failure consult `reprobe` for a 【 】 marker.  Non-ERROR (incl.
   Interrupt) and unmarkable errors (type/check, end-of-input) propagate unchanged. *)
fun guard reprobe f =
  case Exn.capture f () of
    Exn.Res r => r
  | Exn.Exn exn =>
      (case dest_errors exn of
        NONE => Exn.reraise exn
      | SOME _ => (case reprobe () of SOME better => error better | NONE => Exn.reraise exn))

fun read_positioned read ctxt s =
  guard (fn () => marker_strings read ctxt [s]) (fn () => read ctxt s)

fun read_positioned_list read ctxt ss =
  guard (fn () => marker_strings (fn ctxt' => fn s => read ctxt' [s]) ctxt ss)
        (fn () => read ctxt ss)

(* The probe drops the real type constraint (uses dummyT) — safe: a type
   constraint cannot move a grammar-level parse failure, and on any divergence
   `guard` falls through to the untouched original error.  Invariant for all
   list/typed probes: each string is probed INDIVIDUALLY, which reproduces only
   per-string PARSE errors; a joint type-inference (check) error carries no
   <position>, so `marker_strings` returns NONE and the original error stands. *)
fun read_positioned_typed read ctxt tss =
  guard (fn () => marker_strings (fn ctxt' => fn s => read ctxt' [(dummyT, s)]) ctxt (map snd tss))
        (fn () => read ctxt tss)
end
