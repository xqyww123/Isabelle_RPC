(*
  Standing global callback: let the Python RPC host read this Isabelle
  process's environment/settings variables.

  The host is a long-lived daemon whose own os.environ is frozen at its
  start; the connected Isabelle re-sources etc/settings at every restart,
  so its view is authoritative for user configuration (e.g. API keys).
  Note this exposes the WHOLE Isabelle process environment — settings
  variables and whatever the launching shell exported alike; the two are
  indistinguishable once settings have been sourced.

  ML getenv yields "" for unset variables; the Python side treats "" as
  unset and falls back to its own process environment.
*)

val _ = Theory.setup (Context.theory_map (
  Remote_Procedure_Calling.register_global_callback {
    name = "getenv",
    arg_schema = MessagePackBinIO.Unpack.unpackString,
    ret_schema = MessagePackBinIO.Pack.packString,
    function = getenv,
    timeout = NONE
  }))
