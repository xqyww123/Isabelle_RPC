(*
  The catalog of one entity enumeration callback (ENTITY_CATALOG_PLAN.md §4.1).

  An append-only numbering of the (uk, name, is_local) entries the callback's
  replies have returned so far.  The callback's maker creates it empty; it lives
  as long as the callback, which is built for one call_command.  Python holds a
  mirror of the prefix it has received and sends its length (synced_length);
  each reply carries the indices of its results and the entries the mirror lacks.

  No locks: dispatch_loop serves one callback at a time per call_command.
*)

signature ENTITY_CATALOG =
sig
  type entry = {uk : Universal_Key.universal_key, name : string, is_local : bool}

  type T
  val new : unit -> T

  val length : T -> int
  (* the index of the entry equal in (uk, name, is_local); appended when absent *)
  val intern : T -> entry -> int
  (* the entries with index >= n, ascending *)
  val entries_from : T -> int -> (entry * int) list

  (* Bitmap: ceil (length / 8) bytes over [0, length), MSB-first in a byte *)
  datatype index_set = Bitmap of Word8Vector.vector | Indices of int list
  type reply = index_set * (entry * int) list * string list
  (* answer catalog n results warnings: n > length raises (protocol error);
     n < length re-delivers [n, length), a reply the caller did not apply.
     Interns each result in order and encodes their indices as the smaller of
     Bitmap and Indices (in result order, never sorted). *)
  val answer : T -> int -> entry list -> string list -> reply

  val pack_index_set : index_set MessagePackBinIO.Pack.packer
  val pack_reply : reply MessagePackBinIO.Pack.packer
end

structure Entity_Catalog : ENTITY_CATALOG =
struct

type entry = {uk : Universal_Key.universal_key, name : string, is_local : bool}

datatype T = Catalog of {
  entries : entry Dynamic_Array.T,                  (* index = position *)
  by_uk : (entry * int) list Bytehashtab.table}

fun new () = Catalog {entries = Dynamic_Array.empty 16, by_uk = Bytehashtab.empty 16}

fun length (Catalog {entries, ...}) = Dynamic_Array.length entries

fun intern (Catalog {entries, by_uk}) (e : entry) =
  let val same_uk = the_default [] (Bytehashtab.lookup by_uk (#uk e))
  in
    (case find_first (fn (e', _) => #name e' = #name e andalso #is_local e' = #is_local e) same_uk of
      SOME (_, i) => i
    | NONE =>
        let val i = Dynamic_Array.length entries
        in Dynamic_Array.push (entries, e); Bytehashtab.update by_uk (#uk e, (e, i) :: same_uk); i end)
  end

fun entries_from (Catalog {entries, ...}) n =
  map (fn i => (Dynamic_Array.sub (entries, i), i)) (n upto Dynamic_Array.length entries - 1)

datatype index_set = Bitmap of Word8Vector.vector | Indices of int list
type reply = index_set * (entry * int) list * string list

(* bytes of a non-negative int in msgpack *)
fun int_width i =
  if i < 0x80 then 1 else if i < 0x100 then 2 else if i < 0x10000 then 3
  else if i div 0x10000 div 0x10000 = 0 then 5 else 9

fun bitmap len indices =
  let
    val bits = Word8Array.array ((len + 7) div 8, 0w0)
    fun set i =
      Word8Array.update (bits, i div 8,
        Word8.orb (Word8Array.sub (bits, i div 8), Word8.<< (0w1, Word.fromInt (7 - i mod 8))))
  in List.app set indices; Word8Array.vector bits end

fun answer catalog n results warnings =
  let
    val len0 = length catalog
    val _ = if n > len0 then
              error ("Entity_Catalog: synced_length " ^ string_of_int n ^
                     " exceeds the catalog length " ^ string_of_int len0)
            else ()
    val indices = map (intern catalog) results
    val len = length catalog
    val index_set =
      if fold (fn i => fn s => s + int_width i) indices 0 < (len + 7) div 8
      then Indices indices else Bitmap (bitmap len indices)
  in (index_set, entries_from catalog n, warnings) end

local open MessagePackBinIO.Pack in

fun pack_index_set (Bitmap bits) = packBytes bits
  | pack_index_set (Indices indices) = packList packInt indices

val pack_reply =
  packTuple3 (pack_index_set,
    packList (packTuple4 (Universal_Key.pack_universal_key, packString, packBool, packInt)
              o (fn ({uk, name, is_local}, i) => (uk, name, is_local, i))),
    packList packString)

end

end
