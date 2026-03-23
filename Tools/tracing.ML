signature ISABELLE_LOG = sig
  datatype log_type = TRACING | WARNING | WRITELN
  val pack_log_type : log_type MessagePackBinIO.Pack.packer
  val unpack_log_type : log_type MessagePackBinIO.Unpack.unpacker
end

structure Isabelle_Log : ISABELLE_LOG = struct

datatype log_type = TRACING | WARNING | WRITELN

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

fun pack_log_type TRACING = packInt 0
  | pack_log_type WARNING = packInt 1
  | pack_log_type WRITELN = packInt 2

val unpack_log_type : log_type unpacker = fn ins =>
  let val (k, ins') = unpackInt ins
  in (case k of
        0 => TRACING | 1 => WARNING | 2 => WRITELN
      | _ => raise Unpack, ins')
  end

val _ = Theory.setup (Context.theory_map (
  Remote_Procedure_Calling.register_global_callback {
    name = "log",
    arg_schema = unpackPair (unpack_log_type, unpackString),
    ret_schema = packUnit,
    function = fn (level, msg) =>
      (case level of
        TRACING => tracing msg
      | WARNING => warning msg
      | WRITELN => writeln msg),
    timeout = NONE
  }))

end (*local*)

end
