(*
  Theory Hash: 16-byte content hashing for Isabelle theories.

  For theories from saved heap images:
    xxhash128 of the .thy file content combined with parent hashes,
    computed via Python RPC. LSB of byte 0 is cleared (= 0).

  For non-loaded theories (e.g., being processed in jEdit):
    FNV-1a 128-bit hash of the long theory name, computed locally.
    LSB of byte 0 is set (= 1).

  The LSB convention allows downstream code to distinguish which
  hash scheme produced the value.
*)

signature THEORY_HASH = sig
  type hash = Word8Vector.vector  (* 16 bytes, xxhash128 *)
  exception Cannot_Hash of theory
  val hash_of : theory -> hash
  val theory_of : hash -> theory option
  val is_persistent : hash -> bool
  val hasher : hash -> word
  val to_hex : hash -> string
end

structure Theory_Hash : THEORY_HASH = struct

type hash = Word8Vector.vector

exception Cannot_Hash of theory

(* RPC command: (file_path, parent_hashes) -> hash *)
local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

val xxhash128_cmd : (string * hash list, hash) Remote_Procedure_Calling.command = {
  name = "xxhash128_theory",
  arg_schema = packPair (packString, packList packBytes),
  ret_schema = unpackBytes,
  callback = [],
  timeout = SOME (Time.fromSeconds 60)
}

end

val hasher = Hashers.bitvec

(* Cache: theory identifier -> hash *)
val cache : hash Inttab.table Synchronized.var =
  Synchronized.var "Theory_Hash.cache" Inttab.empty

(* Reverse map: hash -> theory *)
structure Hash_Tab = Hash_Table(
  type key = hash
  val hash = hasher
  val eq = op = : hash * hash -> bool)

val hash_to_thy : theory Hash_Tab.table Synchronized.var =
  Synchronized.var "Theory_Hash.hash_to_thy" (Hash_Tab.empty 64)

fun theory_of h =
  Synchronized.change_result hash_to_thy (fn tab => (Hash_Tab.lookup tab h, tab))

(* Convert 16-byte hash to 32-char hex string *)
local
  val hex = "0123456789abcdef"
  fun byte_hex b =
    let val n = Word8.toInt b
    in String.implode [String.sub (hex, n div 16), String.sub (hex, n mod 16)]
    end
in
fun to_hex (h : hash) =
  String.concat (List.tabulate (Word8Vector.length h, fn i =>
    byte_hex (Word8Vector.sub (h, i))))
end

fun is_persistent (h : hash) : bool =
  Word8.andb (Word8Vector.sub (h, 0), 0w1) = 0w0

fun get_theory_file_path thy =
  let
    val thy_name = Context.theory_long_name thy
    val master_dir = Resources.master_directory thy
    val thy_base = Long_Name.base_name thy_name
    val thy_file = Path.ext "thy" (master_dir + Path.basic thy_base)
    val expanded_path = File.full_path master_dir thy_file
  in
    File.platform_path expanded_path
  end

fun hash_of thy =
  let
    val id = Context.theory_identifier thy
  in
    case Synchronized.change_result cache (fn tab =>
      case Inttab.lookup tab id of
        SOME h => (SOME h, tab)
      | NONE => (NONE, tab)) of
      SOME h => h
    | NONE =>
        let
          val name = Context.theory_long_name thy

          val h =
            if Resources.loaded_theory name then
              let
                (* Get file path; check existence *)
                val file_path = \<^try>\<open>get_theory_file_path thy
                  catch _ => raise Cannot_Hash thy\<close>
                val _ =
                  if File.is_file (Path.explode file_path) then ()
                  else raise Cannot_Hash thy

                (* Recursively hash parent theories *)
                val parent_hashes = map hash_of (Theory.parents_of thy)

                (* RPC call to Python *)
                val h = Remote_Procedure_Calling.call_command xxhash128_cmd
                          (file_path, parent_hashes)

                val _ =
                  if Word8Vector.length h = 16 then ()
                  else raise Cannot_Hash thy
              in
                (* Clear LSB of byte 0 to mark as heap-image hash *)
                Word8Vector.update (h, 0,
                  Word8.andb (Word8Vector.sub (h, 0), 0wxFE))
              end
            else
              let
                (* FNV-1a 128-bit hash of theory name, set LSB *)
                val arr = Term_Digest.digest128_to_array (Term_Digest.string128 name)
                val _ = Word8Array.update (arr, 0,
                  Word8.orb (Word8Array.sub (arr, 0), 0w1))
              in Word8Array.vector arr end

          (* Cache the result *)
          val _ = Synchronized.change cache (Inttab.update (id, h))
          val _ = Synchronized.change hash_to_thy (fn tab => (Hash_Tab.update tab (h, thy); tab))
        in h end
  end

end

val _ = Theory.setup (Context.theory_map (
  Remote_Procedure_Calling.register_global_callback {
    name = "Theory_Hash.theory_name_of",
    arg_schema = MessagePackBinIO.Unpack.unpackBytes,
    ret_schema = MessagePackBinIO.Pack.packOption MessagePackBinIO.Pack.packString,
    function = fn h =>
      Option.map Context.theory_long_name (Theory_Hash.theory_of h),
    timeout = NONE
  }))
