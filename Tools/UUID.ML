signature UUID = sig
  type T
  val bytes_of : T -> Word8Vector.vector
  val of_bytes : Word8Vector.vector -> T
  val to_string : T -> string
  val generate_cmd : (int, T list) Remote_Procedure_Calling.command
  val generate : int -> T list
end

structure UUID : UUID = struct

type T = Word8Vector.vector

fun of_bytes v =
  if Word8Vector.length v = 16 then v
  else error ("UUID.of_bytes: expected 16 bytes, got " ^ Int.toString (Word8Vector.length v))

fun bytes_of (u : T) = u

local
  val hex = "0123456789abcdef"
  fun byte_hex b =
    let val n = Word8.toInt b
    in String.implode [String.sub (hex, n div 16), String.sub (hex, n mod 16)]
    end
in
fun to_string (u : T) =
  let fun h i = byte_hex (Word8Vector.sub (u, i))
      val groups =
        [ String.concat (map h (0 upto 3))
        , String.concat (map h (4 upto 5))
        , String.concat (map h (6 upto 7))
        , String.concat (map h (8 upto 9))
        , String.concat (map h (10 upto 15))
        ]
  in String.concatWith "-" groups end
end

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

val generate_cmd : (int, T list) Remote_Procedure_Calling.command = {
  name = "generate_uuids",
  arg_schema = packInt,
  ret_schema = unpackList unpackBytes >> map of_bytes,
  callback = [],
  timeout = SOME (Time.fromSeconds 30)
}

end

fun generate n = Remote_Procedure_Calling.call_command generate_cmd n

end
