signature REMOTE_PROCEDURE_CALLING = sig

type connection = BinIO.StreamIO.instream Unsynchronized.ref
                * BinIO.StreamIO.outstream
                * Time.time option Unsynchronized.ref (*read timeout*)

exception Read_Timeout
exception Remote_Calling_Failure of {func_name: string option, message: string}

val read : connection -> 'a MessagePackBinIO.Unpack.unpacker -> 'a
val write : connection -> 'a MessagePackBinIO.Pack.packer -> 'a -> unit
val write_error : connection -> exn -> unit
val write_error': connection -> 'a MessagePackBinIO.Pack.packer -> {message: string list, errobj: 'a} -> unit

type ('a,'b) callback = {
  name: string,
  arg_schema: 'a MessagePackBinIO.Unpack.unpacker,
  ret_schema: 'b MessagePackBinIO.Pack.packer,
  function: 'a -> 'b,
  timeout: Time.time option
}
type callback' = {name: string, action: connection -> int -> unit}

val mk_callback: ('a,'b) callback -> callback'
val register_global_callback: ('a,'b) callback -> Context.generic -> Context.generic
val register_global_callback': callback' -> Context.generic -> Context.generic
val get_global_callback: string -> callback' option

type ('a,'b) command = {
  name : string,
  arg_schema : 'a MessagePackBinIO.Pack.packer,
  ret_schema : 'b MessagePackBinIO.Unpack.unpacker,
  callback : callback' list,
  timeout : Time.time option
}

val call_command' : ('a,'b) command -> connection -> 'a -> 'b
val call_command  : ('a,'b) command -> 'a -> 'b

val heartbeat_cmd : (unit, unit) command
val heartbeat : connection -> unit

val load_cmd : (string list, (string * string option) list) command
val load : string list -> unit

val call_heartbeat_callback_cmd : (unit, string) command

(*Auxiliary*)
val get_connection : unit -> connection
val release_connection : connection -> unit
end

structure Remote_Procedure_Calling : REMOTE_PROCEDURE_CALLING = struct

type connection = BinIO.StreamIO.instream Unsynchronized.ref
                * BinIO.StreamIO.outstream
                * Time.time option Unsynchronized.ref (*read timeout*)

exception Read_Timeout
exception Remote_Calling_Failure of {func_name: string option, message: string}

(** TCP **)

fun get_addr () =
  let val addr = getenv "RPC_Host"
      val addr = if addr = "" then "127.0.0.1:27182" else addr
   in case space_explode ":" addr of [h, p] => (h,p)
    | _ => error ("Invalid RPC address: " ^ addr ^ ". Should be `host:port`.")
  end

fun make_streams_timeout socket =
  let
    val (host, port) = INetSock.fromAddr (Socket.Ctl.getSockName socket);
    val name = NetHostDB.toString host ^ ":" ^ string_of_int port;
    val read_timeout = Unsynchronized.ref NONE

    fun close_permissive socket =
          Socket.close socket handle OS.SysErr _ => ();

    fun recvVecWithTimeout (sock, size) =
        let val {rds, ...} = Socket.select {
              rds = [Socket.sockDesc sock],
              wrs = [],
              exs = [],
              timeout = !read_timeout
            }
        in if null rds then raise Read_Timeout
           else case Socket.recvVecNB (sock, size)
                  of NONE => recvVecWithTimeout (sock, size)
                   | SOME ret => ret
        end
    fun recvArrWithTimeout (sock, size) =
        let val {rds, ...} = Socket.select {
              rds = [Socket.sockDesc sock],
              wrs = [],
              exs = [],
              timeout = !read_timeout
            }
        in if null rds then raise Read_Timeout
           else case Socket.recvArrNB (sock, size)
                  of NONE => recvArrWithTimeout (sock, size)
                   | SOME ret => ret
        end

    val rd =
      BinPrimIO.RD {
        name = name,
        chunkSize = 4096,
        readVec = SOME (fn n => recvVecWithTimeout (socket, n)),
        readArr = SOME (fn buffer => recvArrWithTimeout (socket, buffer)),
        readVecNB = NONE,
        readArrNB = NONE,
        block = NONE,
        canInput = NONE,
        avail = fn () => NONE,
        getPos = NONE,
        setPos = NONE,
        endPos = NONE,
        verifyPos = NONE,
        close = fn () => close_permissive socket,
        ioDesc = NONE
      };

    val wr =
      BinPrimIO.WR {
        name = name,
        chunkSize = 4096,
        writeVec = SOME (fn buffer => Socket.sendVec (socket, buffer)),
        writeArr = SOME (fn buffer => Socket.sendArr (socket, buffer)),
        writeVecNB = NONE,
        writeArrNB = NONE,
        block = NONE,
        canOutput = NONE,
        getPos = NONE,
        setPos = NONE,
        endPos = NONE,
        verifyPos = NONE,
        close = fn () => close_permissive socket,
        ioDesc = NONE
      };

    val in_stream =
      BinIO.StreamIO.mkInstream (rd, Word8Vector.fromList []);

    val out_stream =
      BinIO.StreamIO.mkOutstream (wr, IO.BLOCK_BUF);

  in (in_stream, out_stream) end

val python_cmd =
  let val check_python = Isabelle_System.bash_process (Bash.script "command -v python3 || command -v python")
      val py_path = Process_Result.out check_python |> Library.trim_line
   in if py_path = "" then "python3"  (* fallback *)
      else py_path
  end

fun launch_RPC_host (host,port) =
  let val log_dir = (Path.variable "ISABELLE_HOME_USER" + Path.basic "log")
                 |> Isabelle_System.make_directory
      fun mk_log_file () =
        let val result = Isabelle_System.bash_process (Bash.script "date '+%Y%m%d_%H%M%S'")
            val _ = Process_Result.check result
            val name = String.concat ["RPC_", host, "_", port, Process_Result.out result]
            val path = log_dir + Path.basic name
         in if File.exists path then mk_log_file () else path
        end
      val log_path = mk_log_file ()
      val script = String.concat
        [ python_cmd
        , " -c \"import Isabelle_RPC_Host\nIsabelle_RPC_Host.fork_and_launch__()\" "
        , Bash.string (host ^ ":" ^ port), " "
        , Bash.string (File.platform_path log_path) ]

      val _ = tracing (String.concat ["Lauching RPC Host on ", host, ":", port, "...  Log: ",
                                      File.platform_path log_path])
      val result = Isabelle_System.bash_process (Bash.script script)
   in if Process_Result.ok result
      then ()
      else error ( "Fail to launch the RPC Host on " ^ host ^ ":" ^ port ^ "\n\n"
                 ^ Process_Result.err result)
  end

fun connect_agent_socket can_launch =
  let val addr = get_addr ()
      val sock = INetSock.TCP.socket ()

      fun parse_addr (h,p) =
         let fun err () = error ("Bad address " ^ h ^ ":" ^ p)
             val host = case NetHostDB.getByName h of SOME host => host | NONE => err ()
             val port = case Int.fromString p of SOME port => port | NONE => err ()
          in INetSock.toAddr (NetHostDB.addr host, port)
         end
      val addr' = parse_addr addr

   in if Socket.connectNB (sock, addr')
    then sock
    else let
      val timeout = SOME (Time.fromSeconds 5)
      val {wrs, exs, ...} = Socket.select {
          rds = [],
          wrs = [Socket.sockDesc sock],
          exs = [Socket.sockDesc sock],
          timeout = timeout
      }
      fun handle_err () = (
          Socket.close sock;
          if can_launch
          then ( launch_RPC_host addr
               ; connect_agent_socket false )
          else error ("Fail to either connect or launch the RPC host on " ^ #1 addr ^ ":" ^ #2 addr) )
     in case (wrs, exs)
          of (_::_, []) => (* Ready for writing - check for errors *)
              let val errorOccurred = Socket.Ctl.getERROR sock
               in if errorOccurred
                  then handle_err ()
                  else sock
              end
           | _ => handle_err ()
    end
  end

fun make_connection () : connection =
  let val socket = connect_agent_socket true
      val (cin,cout) = make_streams_timeout socket
   in (Unsynchronized.ref cin, cout, Unsynchronized.ref NONE)
  end

(** IO Infrastructure **)

(** Tagged Message I/O for Multiplexed Callback Protocol **)
(*
  Wire protocol — every message is (tag : int, payload):
    tag = 0   → user channel (RPC request / success response)
    tag = 1   → remote error
    tag = N>1 → callback channel N (request/response pair)

  User channel payloads:
    ML → Python:  (0, (func_name, arg))         RPC request
    Python → ML:  (0, result)                    success response
    Python → ML:  (1, error_string)              error response

  Callback channel payloads (Python ↔ ML):
    Phase 1:  (N, callback_name)                 request
              (N, ((), None) | (None, err))       response
    Phase 2:  (N, arg)                           request
              (N, (result, None) | (None, err))   response
*)

datatype 'a tagged_message =
    Callback_Request of int * string  (* callback_id, callback_name *)
  | User_Response of 'a
  | Remote_Error of string

fun read_tagged unpacker (cin, _, timeout) =
  let open MessagePackBinIO.Unpack
      val timeout_val = !timeout
      val (msg, cin') =
          (case timeout_val of SOME t => Timeout.apply t | NONE => I)
              (doUnpack (unpackPair_dep' unpackInt (fn tag =>
                case tag of
                    0 => (* User channel: (0, result) *)
                      (fn s => let val (result, s') = unpacker s
                               in (User_Response result, s') end)
                  | 1 => (* Remote error: (1, error_message) *)
                      (fn s => let val (err, s') = unpackString s
                               in (Remote_Error err, s') end)
                  | n => (* Callback channel n: (n, name) *)
                      (fn s => let val (name, s') = unpackString s
                               in (Callback_Request (n, name), s') end)
              ))) (!cin)
   in cin := cin'
    ; msg
  end

fun read conn packer =
  case read_tagged packer conn of
      User_Response result => result
    | Remote_Error err =>
        raise Remote_Calling_Failure {func_name = NONE, message = err}
    | Callback_Request _ =>
        raise Remote_Calling_Failure {func_name = NONE, message = "Unexpected callback request when expecting user response"}

fun write (_,cout,_) packer data =
  let open MessagePackBinIO.Pack
   in doPack (packPair (packInt, packer)) (0, data) cout
    ; BinIO.StreamIO.flushOut cout
  end

fun write_error' (_,cout,_) packer {message, errobj} =
  let open MessagePackBinIO.Pack
   in doPack (packPair (packInt, packPair (packList packString, packer)))
             (1, (message, errobj)) cout
    ; BinIO.StreamIO.flushOut cout
  end

fun write_error conn exn =
      write_error' conn MessagePackBinIO.Pack.packUnit
                        {message=Runtime.exn_message_list exn, errobj=()}


(** Callback Registry **)

type ('a,'b) callback = {
  name: string,
  arg_schema: 'a MessagePackBinIO.Unpack.unpacker,
  ret_schema: 'b MessagePackBinIO.Pack.packer,
  function: 'a -> 'b,
  timeout: Time.time option
}

type callback' = {name: string, action: connection -> int -> unit}
  (* action conn callback_id: read Phase 2 arg, execute, send tagged response *)

val global_callbacks : callback' Strhashtab.table = Strhashtab.empty 64
val global_callbacks_lock = Synchronized.var "RPC.global_callbacks" ()

fun register_global_callback' (cb : callback') : Context.generic -> Context.generic =
  (Synchronized.change global_callbacks_lock (fn () =>
    (Strhashtab.update global_callbacks (#name cb, cb); ())); I)

fun get_global_callback (name : string) : callback' option =
  Synchronized.change_result global_callbacks_lock (fn () =>
    (Strhashtab.lookup global_callbacks name, ()))

fun mk_callback ({name, arg_schema, ret_schema, function, timeout} : ('a,'b) callback) : callback' =
  {name = name,
   action = fn conn => fn cb_id => \<^try>\<open>
     let open MessagePackBinIO.Pack MessagePackBinIO.Unpack
         val (cin, cout, _) = conn
         (* Phase 2: Read (cb_id, arg) pair *)
         val ((_, cb_arg), cin') = doUnpack (unpackPair (unpackInt, arg_schema)) (!cin)
                           handle Unpack => error "Failed to unpack callback argument"
         val _ = cin := cin'
         val result = function cb_arg
         (* Send (cb_id, (Some result, None)) *)
      in doPack (packPair (packInt, packPair (packOption ret_schema, packOption packString)))
                (cb_id, (SOME result, NONE)) cout
       ; BinIO.StreamIO.flushOut cout
     end catch exn =>
       let open MessagePackBinIO.Pack
           val (_, cout, _) = conn
        in doPack (packPair (packInt, packPair (packOption ret_schema, packOption packString)))
                  (cb_id, (NONE, SOME (String.concatWith "\n" (Runtime.exn_message_list exn)))) cout
         ; BinIO.StreamIO.flushOut cout
       end\<close>}

fun register_global_callback (callback : ('a,'b) callback) : Context.generic -> Context.generic =
  register_global_callback' (mk_callback callback)

(** Built-in Callbacks **)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

val heartbeat_callback : (unit, string) callback = {
  name = "isabelle_heartbeat",
  arg_schema = unpackUnit,
  ret_schema = packString,
  function = (fn () => "Isabelle heartbeat: " ^ Time.toString (Time.now ())),
  timeout = NONE
}

val symbol_explode_callback : (string, string list) callback = {
  name = "position.symbol_explode",
  arg_schema = unpackString,
  ret_schema = packList packString,
  function = fn text => Symbol_Pos.explode (text, Position.none) |> map fst,
  timeout = NONE
}

val _ = Theory.setup (Context.theory_map (
  register_global_callback heartbeat_callback
  #> register_global_callback symbol_explode_callback))

end

(** Callback Dispatcher **)

fun lookup_callback (local_tab : callback' Strhashtab.table) (name : string) : callback' option =
  (case Strhashtab.lookup local_tab name of
      SOME cb => SOME cb
    | NONE => get_global_callback name)

fun dispatch_loop conn local_tab func_name ret_schema =
  (case read_tagged ret_schema conn of
      Callback_Request (cb_id, name) =>
        ((case lookup_callback local_tab name of
              SOME {action, ...} =>
                let open MessagePackBinIO.Pack
                    val (_, cout, _) = conn
                    val _ = doPack (packPair (packInt, packPair (packUnit, packOption packString)))
                                   (cb_id, ((), NONE)) cout
                    val _ = BinIO.StreamIO.flushOut cout
                 in action conn cb_id
                end
            | NONE =>
                let open MessagePackBinIO.Pack
                    val (_, cout, _) = conn
                    val _ = doPack (packPair (packInt, packPair (packOption packUnit, packOption packString)))
                                   (cb_id, (NONE, SOME ("Unknown callback: " ^ name))) cout
                    val _ = BinIO.StreamIO.flushOut cout
                 in () end)
        ; dispatch_loop conn local_tab func_name ret_schema)
    | User_Response result => result
    | Remote_Error err =>
        raise Remote_Calling_Failure {func_name = SOME func_name, message = err})

type ('a,'b) command = {
  name : string,
  arg_schema : 'a MessagePackBinIO.Pack.packer,
  ret_schema : 'b MessagePackBinIO.Unpack.unpacker,
  callback : callback' list,
  timeout : Time.time option
}


(** Command Interface **)

exception RPC_Fail of string

fun call_command' {name, arg_schema, ret_schema, callback, timeout} conn arg =
  let open MessagePackBinIO.Pack MessagePackBinIO.Unpack
      val local_tab = Strhashtab.empty (length callback)
      val _ = List.app (fn cb => Strhashtab.update local_tab (#name cb, cb)) callback
      val _ = (#3 conn) := timeout
      val _ = write conn (packPair (packString, arg_schema)) (name, arg)
   in dispatch_loop conn local_tab name ret_schema
  end handle MessagePackBinIO.Unpack.Unpack =>
      raise Remote_Calling_Failure {func_name=SOME name, message="Invalid response, protocol error"}
  

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

val heartbeat_cmd = {
  name = "heartbeat",
  arg_schema = packUnit,
  ret_schema = unpackUnit,
  callback = [],
  timeout = SOME (Time.fromSeconds 10)
}

fun heartbeat conn = call_command' heartbeat_cmd conn ()

val load_cmd = {
  name = "load_pymodule",
  arg_schema = packList packString,
  ret_schema = unpackPairList (unpackString, unpackOption unpackString),
  callback = [],
  timeout = SOME (Time.fromSeconds 30)
}

val call_heartbeat_callback_cmd = {
  name = "call_heartbeat_callback",
  arg_schema = packUnit,
  ret_schema = unpackString,
  callback = [],
  timeout = SOME (Time.fromSeconds 10)
}

end

(** Connection Pool **)

fun close_connection conn =
  let val (cin, cout, _) = conn
   in BinIO.StreamIO.closeOut cout
    ; BinIO.StreamIO.closeIn (!cin)
  end

val connection_pool : connection list Synchronized.var
      = Synchronized.var "RPC.connection_pool" []

fun get_connection () =
  case Synchronized.change_result connection_pool (
        fn [] => (NONE, [])
         | x::L => (SOME x, L) )
    of SOME conn =>
          if can heartbeat conn
          then conn
          else ( close_connection conn
               ; List.app close_connection
                   (Synchronized.change_result connection_pool (fn L => (L, [])))
               ; make_connection () )
     | NONE => make_connection ()

fun release_connection conn =
  Synchronized.change connection_pool (fn L => conn :: L)

fun call_command cmd arg =
  let val conn = get_connection ()
      val normal = Unsynchronized.ref false
   in \<^try>\<open>
        let val result = call_command' cmd conn arg
            val _ = normal := true
         in result end
      finally
        if !normal
        then release_connection conn
        else close_connection conn
      \<close>
  end

fun load packages =
  let val errs = call_command load_cmd packages
   in if exists (is_some o snd) errs
    then error (String.concat (maps (fn (_, NONE) => []
                  | (lib, SOME e) => ["Fail to load ", lib, ": ", e, "\n\n"]) errs))
    else ()
  end

end
