(*
  Theory_Hash_Store: the write path of the theory-hash registry, and the two
  callbacks through which Python asks this process about a theory hash.

  The hashes themselves are Theory_Hash, in Performant_Isabelle_ML
  (library/theory_hash.ML): computed natively, no RPC.  What stays here needs RPC:
    - store_theory_hash: for a theory and all its ancestors, send (hash, long name)
      to Python, which records them in the registry theory_hash.lmdb, so that a
      hash in a universal key can be named without this process;
    - the global callbacks "Theory_Hash.theory_name_of" and
      "Theory_Hash.process_serial_of" (RPC wire names, kept).

  A structure of its own, not a second Theory_Hash: Isabelle merges the ML tables
  of a theory's parents first-parent-wins (ml_env.ML:78-86), so a same-name
  Theory_Hash here would be lost by any theory whose first parent reaches
  Performant_Isabelle_ML but not this session (Minilang_AoA imports Minilang
  first).  The name follows the store's own: Python's open_theory_hash_store and
  the procedure "Theory_Hash.store".
*)

signature THEORY_HASH_STORE = sig
  val store_theory_hash : theory -> unit
end

structure Theory_Hash_Store : THEORY_HASH_STORE = struct

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

val store_cmd : ((Theory_Hash.hash * string) list, unit) Remote_Procedure_Calling.command = {
  name = \<^unchecked_name>\<open>Theory_Hash.store\<close>,
  arg_schema = packList (packPair (packBytes, packString)),
  ret_schema = unpackUnit,
  callback = [],
  timeout = SOME (Time.fromSeconds 60)
}

end

fun store_theory_hash thy =
  let
    val entries = Theory.nodes_of thy
      |> map (fn t => (Theory_Hash.hash_of t, Context.theory_long_name t))
  in
    Remote_Procedure_Calling.call_command store_cmd entries
  end

end

val _ = Theory.setup (Context.theory_map (
  Remote_Procedure_Calling.register_global_callback {
    name = \<^unchecked_name>\<open>Theory_Hash.theory_name_of\<close>,
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = MessagePackBinIO.Unpack.unpackBytes,
    ret_schema = MessagePackBinIO.Pack.packOption MessagePackBinIO.Pack.packString,
    function = fn h =>
      Option.map Context.theory_long_name (Theory_Hash.theory_of h),
    timeout = NONE
  }
  #> Remote_Procedure_Calling.register_global_callback {
    (* The WIP theory-status skip pair (process id, theory serial) of the
       loaded theory behind a hash -- for Python paths (the embed side) that
       hold only a theory hash.  NB the value-passing discipline
       (CHECK_OUTDATE_PLAN.md §3.4): the serial is read off the theory VALUE
       this process most recently hashed under `h` (theory_of's table), which
       is the value whose entities the pipeline enumerated; interpret-side ML
       callers do not use this callback at all -- they read the serial off the
       theory value already in hand. *)
    name = \<^unchecked_name>\<open>Theory_Hash.process_serial_of\<close>,
    on_interrupt = Remote_Procedure_Calling.Reraise,
    arg_schema = MessagePackBinIO.Unpack.unpackBytes,
    ret_schema = MessagePackBinIO.Pack.packOption
      (MessagePackBinIO.Pack.packPair
        (MessagePackBinIO.Pack.packString, MessagePackBinIO.Pack.packInt)),
    function = fn h =>
      Option.map (fn thy => (Theory_Hash.process_id (), Context.theory_identifier thy))
        (Theory_Hash.theory_of h),
    timeout = NONE
  }))
