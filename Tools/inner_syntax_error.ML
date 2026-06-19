(* Inner_Syntax_Error: turn an opaque Isabelle inner-syntax parse error into a
   precise, agent-facing message that brackets the failing token with 【 】.

   Mechanism: Isabelle's `Syntax.read_*` on a bare string carries Position.none,
   so the error renders `at ""` with no offset.  Feeding the SAME string as a
   positioned `Input.source` (via `Syntax.implode_input`) makes the parser emit a
   `<position offset=k end_offset=k' id=ID>` in the error message (symbol-indexed,
   1-based).  We extract that offset and splice 【 】 around the failing token in the
   original string, showing only a unique window around it.  The error body also
   carries (under the SAME id) a `<token_range>` per token (each spanning that
   token's real offsets) and a trailing `<bad offset="1">`; filtering by element
   NAME = "position" — not by id/offset — is what isolates the one wanted element.

   IMPORTANT: positioned input perturbs schematic type-variable indices (e.g. a
   type-check error prints ??'a13 instead of ??'a), so it must NEVER be used to
   produce the value a proof consumes.  The real read/op always runs on the PLAIN
   string; positioned input is used ONLY as a throwaway probe to locate a parse
   failure.  Only inner-syntax PARSE errors carry a position; type/check errors
   and "unexpected end of input" do not, and are passed through unchanged. *)

signature INNER_SYNTAX_ERROR = sig
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

val pointer =
  arrow ^ " parse failed; the offending token is wrapped in " ^ lbrack ^ " " ^ rbrack ^ ": "

fun ignored_prefix noun =
  noun ^ " pattern was ignored " ^ emdash ^ " results are NOT filtered by it."

(* --- offset extraction (filter by element NAME = position) --------------- *)

(* First <position> element whose id satisfies id_ok and which carries an
   offset; returns (id, offset, end_offset).  end_offset defaults to offset+1. *)
fun parse_offset id_ok msg =
  let
    fun search [] = NONE
      | search (XML.Text _ :: rest) = search rest
      | search (XML.Elem ((name, props), body) :: rest) =
          if name = Markup.positionN then
            let val pos = Position.of_properties props in
              case (Position.id_of pos, Position.offset_of pos) of
                (SOME id, SOME off) =>
                  if id_ok id
                  then SOME (id, off, the_default (off + 1) (Position.end_offset_of pos))
                  else search (body @ rest)
              | _ => search (body @ rest)
            end
          else search (body @ rest)
  in search (YXML.parse_body msg) end

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
          (YXML.parse_body msg)))

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

(* off/eoff are 1-based symbol indices; returns SOME marked-window or NONE
   when out of range / empty (P15). *)
fun mark_window text (off, eoff) =
  let
    val syms = Symbol.explode text
    val n = length syms
    val lo = off - 1
  in
    if lo < 0 orelse lo >= n then NONE
    else
      let
        val hi = Int.max (lo + 1, Int.min (eoff - 1, n))
        val full = implode syms
        fun uniq (a, b) = count_substr (implode (sublist (syms, a, b))) full = 1
        fun expand (a, b) =
          if (b - a >= 16 andalso uniq (a, b)) orelse (a <= 0 andalso b >= n)
          then (a, b)
          else expand (Int.max (0, a - 1), Int.min (n, b + 1))
        val (a, b) = expand (lo, hi)
        val pre  = if a > 0 then ellipsis else ""
        val post = if b < n then ellipsis else ""
        val mid =
          implode (sublist (syms, a, lo)) ^ lbrack ^
          implode (sublist (syms, lo, hi)) ^ rbrack ^
          implode (sublist (syms, hi, b))
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
