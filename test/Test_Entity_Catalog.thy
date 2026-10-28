(*
  Entity_Catalog.answer (ENTITY_CATALOG_PLAN.md §8.2): the index set encoding
  and its choice, re-delivery of a reply the caller did not apply, the protocol
  error, and the intern key (uk, name, is_local).
*)
theory Test_Entity_Catalog
  imports Main Isabelle_RPC.Remote_Procedure_Calling
begin

ML \<open>
local
fun assert msg b = if b then () else error ("Test_Entity_Catalog: " ^ msg)

val consts = ["HOL.True", "HOL.False", "HOL.conj", "HOL.disj", "HOL.implies",
              "HOL.Not", "HOL.All", "HOL.Ex", "HOL.eq", "HOL.If"]
fun entry name =
  {uk = #1 (Universal_Key.key_of_constant (Context.Proof \<^context>) name), name = name,
   is_local = false}
val ten = map entry consts
fun indices_of (_, delivered, _) = map #2 delivered

val catalog = Entity_Catalog.new ()
val _ = assert "the first reply delivers all ten, in order"
          (indices_of (Entity_Catalog.answer catalog 0 ten []) = (0 upto 9))

(* the glossary's example: a catalog of 10, results {0..7, 9} *)
val (index_set, delivered, warnings) =
  Entity_Catalog.answer catalog 10 (map (nth ten) [0, 1, 2, 3, 4, 5, 6, 7, 9]) ["w"]
val _ = assert "Bitmap FF 40" (index_set = Entity_Catalog.Bitmap (Word8Vector.fromList [0wxFF, 0wx40]))
val _ = assert "nothing new to deliver" (null delivered)
val _ = assert "the warnings pass through" (warnings = ["w"])

(* one index (1 byte) is smaller than the bitmap (2 bytes); two are not *)
val (one, _, _) = Entity_Catalog.answer catalog 10 [nth ten 9] []
val _ = assert "Indices [9]" (one = Entity_Catalog.Indices [9])
val (two, _, _) = Entity_Catalog.answer catalog 10 [nth ten 9, nth ten 3] []
val _ = assert "two indices give the bitmap" (two = Entity_Catalog.Bitmap (Word8Vector.fromList [0wx10, 0wx40]))

(* n < length re-delivers [n, length) *)
val _ = assert "re-delivery of [4, 10)"
          (indices_of (Entity_Catalog.answer catalog 4 [nth ten 0] []) = (4 upto 9))

(* n > length is a protocol error, raised before anything is interned *)
val _ =
  (case Exn.capture_body (fn () =>
      Entity_Catalog.answer catalog 11 [entry "HOL.undefined"] []) of
    Exn.Exn (ERROR msg) => assert ("the protocol error names synced_length: " ^ msg)
                             (String.isSubstring "synced_length 11" msg)
  | Exn.Exn exn => error ("Test_Entity_Catalog: not ERROR: " ^ Runtime.exn_message exn)
  | Exn.Res _ => error "Test_Entity_Catalog: synced_length 11 was accepted")
val _ = assert "nothing was interned" (Entity_Catalog.length catalog = 10)

(* the intern key is (uk, name, is_local): the same uk twice more (D6) *)
val true_local = {uk = #uk (nth ten 0), name = "HOL.True", is_local = true}
val alias = {uk = #uk (nth ten 0), name = "HOL.True_alias", is_local = false}
val _ = assert "is_local = true is another entry" (Entity_Catalog.intern catalog true_local = 10)
val _ = assert "another name is another entry" (Entity_Catalog.intern catalog alias = 11)
val _ = assert "an interned entry keeps its index" (Entity_Catalog.intern catalog (nth ten 0) = 0)

(* an index list keeps the result order: in a catalog of 100, two indices
   (2 bytes) are smaller than the bitmap (13 bytes) *)
val big = Entity_Catalog.new ()
val hundred = map (fn i => {uk = #uk (nth ten (i mod 10)), name = "N" ^ string_of_int i,
                            is_local = false}) (0 upto 99)
val _ = Entity_Catalog.answer big 0 hundred []
val (unsorted, _, _) = Entity_Catalog.answer big 100 [nth hundred 50, nth hundred 7] []
val _ = assert "Indices [50, 7], not sorted" (unsorted = Entity_Catalog.Indices [50, 7])
in end
\<close>

end
