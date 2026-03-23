(*  Title:      Tools/dialogue.ML
    Author:     Qiyuan

Interactive dialogue via PIDE Active.dialog — Python can ask users
questions with clickable options in the output panel.
*)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

val _ = Theory.setup (Context.theory_map (
  Remote_Procedure_Calling.register_global_callback {
    name = "dialogue",
    arg_schema = unpackPair (unpackString, unpackList unpackString),
    ret_schema = packString,
    function = fn (question, options) =>
      let
        val (text, promise) = Active.dialog_text ()
        val opts_str = String.concatWith "  " (map text options)
        val _ = writeln (question ^ "\n" ^ opts_str)
        val ret = Future.join promise
      in ret end,
    timeout = NONE
  }))

end
