local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in
val _ = REPL_Server.register_app "Theory_Hash.list" (fn (cin, cout, state) =>
  let
    val thy_name = let val (ret, cin') = doUnpack unpackString (!cin)
                   in cin := cin'; ret end
    val thy = Thy_Info.get_theory thy_name
    val entries = Theory.nodes_of thy
      |> map (fn t => (Context.theory_long_name t, Theory_Hash.hash_of t))
  in
    REPL_Server.output cout
      (packList (packPair (packString, packBytes))) entries;
    BinIO.StreamIO.flushOut cout;
    state
  end)
end
