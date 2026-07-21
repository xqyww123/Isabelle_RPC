theory Remote_Procedure_Calling
  imports Performant_Isabelle_ML.Performant_Isabelle_ML
begin

(* mlmsgpack now loaded by the Performant_Isabelle_ML base session (relocated there). *)
ML_file \<open>Tools/RPC.ML\<close>
ML_file \<open>Tools/UUID.ML\<close>
ML_file \<open>Tools/Term_Digest.ML\<close>
ML_file \<open>Tools/theory_hash.ML\<close>
ML_file \<open>Tools/Universal_Key.ML\<close>
ML_file \<open>Tools/config.ML\<close>
ML_file \<open>Tools/pretty.ML\<close>
ML_file \<open>Tools/inner_syntax_error.ML\<close>
ML_file \<open>Tools/context.ML\<close>
ML_file \<open>Tools/run_python.ML\<close>
ML_file \<open>Tools/tracing.ML\<close>
ML_file \<open>Tools/dialogue.ML\<close>


end