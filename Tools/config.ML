(*
  Config RPC Extension: global registry for config options accessible from Python.

  Extends structure Config with:
  - A global registry mapping option names to Config.value T entries
  - A general callback for Python to look up any registered option by name
*)

signature CONFIG = sig
  include CONFIG
  val register_rpc_option : string -> Config.value Config.T -> unit
  val make_config_lookup_callback : Universal_Key.context_unpacker -> Remote_Procedure_Calling.callback'
end

structure Config : CONFIG = struct
  open Config

  (* Global registry: option name -> value T *)
  val registry : Config.value Config.T Strhashtab.table = Strhashtab.empty 32
  val registry_lock = Synchronized.var "Config.rpc_registry" ()

  fun register_rpc_option (name : string) (config : Config.value Config.T) : unit =
    Synchronized.change registry_lock (fn () =>
      (Strhashtab.update registry (name, config); ()))

  local open MessagePackBinIO.Pack in
  fun pack_value v =
    case v of
      Bool b   => packBool b
    | Int i    => packInt i
    | Real r   => packReal r
    | String s => packString s
  end

  fun make_config_lookup_callback (ctxt_unpack : Universal_Key.context_unpacker)
      : Remote_Procedure_Calling.callback' =
    Remote_Procedure_Calling.mk_callback {
      name = "Config.lookup",
      arg_schema = MessagePackBinIO.Unpack.unpackPair (ctxt_unpack,
                     MessagePackBinIO.Unpack.unpackString),
      ret_schema = pack_value,
      function = fn (context, name) =>
        let val ctxt = Context.cases Proof_Context.init_global I context
        in case Synchronized.change_result registry_lock
                 (fn () => (Strhashtab.lookup registry name, ())) of
            NONE => error ("Config.lookup: unknown option " ^ quote name)
          | SOME config => Config.get ctxt config
        end,
      timeout = NONE
    }

end
