theory Remote_Procedure_Calling
  imports HOL.HOL
begin

ML_file \<open>contrib/mlmsgpack/mlmsgpack-aux.sml\<close>
ML_file \<open>contrib/mlmsgpack/realprinter-packreal.sml\<close>
ML_file \<open>contrib/mlmsgpack/mlmsgpack.sml\<close>
ML_file \<open>Tools/RPC.ML\<close>


ML \<open>Remote_Procedure_Calling.call_command Remote_Procedure_Calling.heartbeat_cmd ()\<close>
ML \<open>Remote_Procedure_Calling.call_command Remote_Procedure_Calling.call_heartbeat_callback_cmd ()\<close>

end