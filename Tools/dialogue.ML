(*  Title:      Tools/dialogue.ML
    Author:     Qiyuan

Interactive dialogue via PIDE Active.dialog -- Python can ask users questions
with clickable options in the output panel.

The only mechanism in the whole Isabelle tree that ever answers an
Active.dialog is Isabelle/jEdit's click handler, so before asking we probe the
attached frontend (Scala function "isabelle_rpc.frontend_identity", shipped by
this component's jar) and return NONE -- the no-responder sentinel -- when
nobody could answer: under Isa-REPL, isabelle build, VSCode, headless PIDE or
a bare ML process the old unconditional Future.join hung forever
(DIALOGUE_RESPONDER_DETECTION_PLAN.md).  The Python caller maps NONE to None
and falls back to its warning path.

Policy override: the system option isabelle_rpc_dialogue (etc/options of this
component; "auto" | "present" | "absent") is read fresh on every call --
options are re-initialized from the launch environment at process start, so
nothing survives via session heaps.  It governs only THIS callback;
run_semantic_interpretation consults the probe directly.
*)

structure Dialogue =
struct

(* Probe triple: (Q2 dialogue_capable, Q1 interactive (three-valued),
   raw Session class name / absence reason).  Q1 is Some only on positive
   identification; unknown frontends get NONE.  Exported: upper layers
   (run_semantic_interpretation) branch on Q1/Q2 themselves. *)
fun frontend_identity () : bool * bool option * string =
  (* Exn.result, not Exn.capture: an interrupt must re-reach the caller, never
     be folded into "not capable" (Exn.capture normalizes but still returns
     interrupts as Exn). *)
  case Exn.result (fn () =>
         Scala.function1 "isabelle_rpc.frontend_identity" "") () of
    Exn.Res reply =>
      let
        val (capable, (interactive, cls)) =
          YXML.parse_body reply
          |> XML.Decode.pair XML.Decode.bool
               (XML.Decode.pair (XML.Decode.option XML.Decode.bool)
                  XML.Decode.string)
      in (capable, interactive, cls) end
  | Exn.Exn e =>
      if Exn.is_interrupt e then Exn.reraise e
      else
        (case e of
          Fail _ =>
            (* Scala present but the function unknown (component not
               registered / broken jar): the prober itself is absent, no
               verdict on Q1; Q2 folds to false (asking needs certainty). *)
            (false, NONE, "component-missing")
        | _ =>
            (* No Scala process at all (bare ML_process): positive evidence
               that no interactive frontend exists. *)
            (false, SOME false, "no-scala"))

fun dialogue_capable () = #1 (frontend_identity ())

(* No caching anywhere: dialogue fires only on the rare ask path, one
   millisecond-scale Scala round trip per call -- and a cache would be frozen
   into session heaps (the RPC.ML:237 bug class). *)
fun responder_attached () =
  case try Options.default_string "isabelle_rpc_dialogue" of
    SOME "present" => true
  | SOME "absent" => false
  | _ => dialogue_capable ()
    (* "auto", unknown values, and an UNDECLARED option (component not
       registered = failed installation, hardened not promised): fall back to
       the probe -- the safe direction. *)

end

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

val _ = Theory.setup (Context.theory_map (
  Remote_Procedure_Calling.register_global_callback {
    name = "dialogue",
    arg_schema = unpackPair (unpackString, unpackList unpackString),
    ret_schema = packOption packString,
    function = fn (question, options) =>
      let
        fun ask () =
          SOME (let
            val (text, promise) = Active.dialog_text ()
            val opts_str = String.concatWith "  " (map text options)
            val _ = writeln (question ^ "\n" ^ opts_str)
          in Future.join promise end)
      in
        (* ONE probe per call, shared by the decision and the trace (the
           over-design audit found the previous shape probed a second time
           just for the tracing line -- and re-introduced the probe under
           policy "absent", the very round trip that policy exists to save).
           Same semantics as Dialogue.responder_attached, inlined so the
           probe triple is in hand for the trace. *)
        case try Options.default_string "isabelle_rpc_dialogue" of
          SOME "present" => ask ()
        | SOME "absent" =>
            (tracing "dialogue: policy absent -- returning the sentinel"; NONE)
        | _ =>
            let val (capable, interactive, cls) = Dialogue.frontend_identity ()
            in
              if capable then ask ()
              else
                (tracing ("dialogue: no responder (interactive=" ^
                   (case interactive of NONE => "unknown"
                    | SOME b => Value.print_bool b) ^ ", frontend=" ^ cls ^
                   ") -- returning the sentinel");
                 NONE)
            end
      end,
    timeout = NONE  (* NB dead field: mk_callback never applies it (RPC.ML:440) *)
  }))

end
