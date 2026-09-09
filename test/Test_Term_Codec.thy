(*
  Round trips of the raw term codec (RPC_Term_Codec, Tools/pretty.ML) through both
  instances, RPC_Pretty (BinIO) and RPC_Pretty_Bytes (BytesIO), and of a runtime
  symbol, which must travel as its identifier: the decoded term is a symbol whose
  dest_symbol is the original identifier, and the wire holds the identifier, not
  the constant names of the per-process numeral.
*)
theory Test_Term_Codec
  imports Isabelle_RPC.Remote_Procedure_Calling
begin

ML \<open>
local
  val symT = Type ("SSymb.symbol", [])
  val s1 = Phi_Tool_Symbol.mk_symbol "Test_Term_Codec.alpha"
  val s2 = Phi_Tool_Symbol.mk_symbol "Test_Term_Codec.beta"
  val t = Abs ("x", TFree ("'a", ["HOL.type"]),
            Const ("f", TVar (("'b", 3), []) --> symT) $ Bound 0 $ s2
              $ Var (("v", 2), symT) $ Free ("y", symT) $ s1)

  fun bytes_encode tm =
    let val out = BytesIO.mkOutstream ()
        val _ = RPC_Pretty_Bytes.pack_raw_term tm out
     in BytesIO.toBytes out end
  fun bytes_rt tm = fst (RPC_Pretty_Bytes.unpack_raw_term (BytesIO.fromBytes (bytes_encode tm)))

  fun binio_rt tm =
    let val path = OS.FileSys.tmpName ()
        val out = BinIO.openOut path
        val _ = RPC_Pretty.pack_raw_term tm (BinIO.getOutstream out)
        val _ = BinIO.closeOut out
        val ins = BinIO.openIn path
        val (tm', _) = RPC_Pretty.unpack_raw_term (BinIO.getInstream ins)
        val _ = BinIO.closeIn ins
        val _ = OS.FileSys.remove path
     in tm' end

  fun assert msg b = if b then () else error ("Test_Term_Codec: " ^ msg)
  val wire = Byte.bytesToString (bytes_encode s2)
in
  val _ = assert "BytesIO round trip" (bytes_rt t = t)
  val _ = assert "BinIO round trip" (binio_rt t = t)
  val _ = assert "symbol round trip"
            (Phi_Tool_Symbol.dest_symbol (bytes_rt s2) = SOME "Test_Term_Codec.beta")
  val _ = assert "wire carries the identifier"
            (String.isSubstring "Test_Term_Codec.beta" wire andalso not (String.isSubstring "SSymb" wire))
end
\<close>

end
