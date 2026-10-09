(*
  A callback whose argument read fails -- its arg_schema raises, or the bytes
  are not what the schema expects -- must end the hosting command with that
  error.  Nothing has advanced the input stream, so the message is still
  pending there.  Were mk_callback to answer Python and return instead of
  re-raising, the dispatch loop would read the pending message as a request:
  for the integer argument the command would die of "Invalid response,
  protocol error", with every later callback on the connection misparsed;
  for the string argument the loop would answer "Unknown callback" and the
  command would end with Python's traceback as the remote error, which quotes
  the same reader text.  Hence the check below matches the ERROR constructor.
  The next call must get a fresh connection.
*)
theory Test_Callback_Argument
  imports Isabelle_RPC.Remote_Procedure_Calling
begin

ML \<open>
local
open MessagePackBinIO.Pack MessagePackBinIO.Unpack Remote_Procedure_Calling

fun assert msg b = if b then () else error ("Test_Callback_Argument: " ^ msg)

(* The argument reader itself rejects odd numbers. *)
val half_of_even : callback' = mk_callback {
  name = "half_of_even",
  on_interrupt = Reraise,
  arg_schema = (fn ins =>
    let val (n, ins') = unpackInt ins
     in if n mod 2 = 0 then (n, ins') else error ("not even: " ^ Int.toString n) end),
  ret_schema = packInt,
  function = (fn n => n div 2),
  timeout = NONE
}

fun call arg =
  Run_Python.run_with [half_of_even]
    ("return await connection.callback('half_of_even', " ^ arg ^ ")")

fun ends_with_error text arg =
  (case Exn.capture_body (fn () => call arg) of
      Exn.Exn (ERROR msg) =>
        assert ("the command ends with the reader's error, not " ^ quote msg)
          (String.isSubstring text msg)
    | Exn.Exn exn => error ("Test_Callback_Argument: not the reader's error: " ^ Runtime.exn_message exn)
    | Exn.Res _ => error "Test_Callback_Argument: the command returned")
in
val _ = assert "a well-formed argument is answered" (call "4" = SOME "2")
val _ = ends_with_error "not even: 3" "3"
val _ = assert "the next call gets a fresh connection" (call "6" = SOME "3")
val _ = ends_with_error "Failed to unpack callback argument" "'three'"
val _ = assert "the next call gets a fresh connection" (call "8" = SOME "4")
end
\<close>

end
