(*  Title:      Tools/run_python.ML
    Author:     Qiyuan Xu (with AI assistance)

Execute Python source code via the RPC bridge.

The source string is wrapped in an async function on the Python side, so
`await` and `return` work naturally.  The connection object is available
as `connection` for calling back into Isabelle ML.

Examples:

    Run_Python.run "return str(1 + 2)"
    (* => SOME "3" *)

    Run_Python.run_with callbacks "return await connection.callback(...)"
    (* callbacks are available during this call *)

    Run_Python.run "x = 42"
    (* => NONE  (no return statement) *)
*)

signature RUN_PYTHON = sig
  (* Run with additional local callbacks available to the Python code. *)
  val run_with : Remote_Procedure_Calling.callback' list -> string -> string option
  (* Run with no local callbacks (only global callbacks are available). *)
  val run : string -> string option
end

structure Run_Python : RUN_PYTHON = struct

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

fun mk_cmd callbacks : (string, string option) Remote_Procedure_Calling.command = {
  name = "run_python",
  arg_schema = packString,
  ret_schema = unpackOption unpackString,
  callback = callbacks,
  timeout = NONE
}

end

fun run_with callbacks source =
  Remote_Procedure_Calling.call_command (mk_cmd callbacks) source

fun run source = run_with [] source

end
