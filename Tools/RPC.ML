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

type ('a,'b) command = {
  name : string,
  arg_schema : 'a MessagePackBinIO.Pack.packer,
  ret_schema : 'b MessagePackBinIO.Unpack.unpacker,
  callback : (connection -> unit) option,
  timeout : Time.time option
}

val call_command' : ('a,'b) command -> connection -> 'a -> 'b
val call_command  : ('a,'b) command -> 'a -> 'b

val heartbeat_cmd : (unit, unit) command
val heartbeat : connection -> unit

val load_cmd : (string list, (string * string option) list) command
val load : string list -> unit

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


fun read (cin,_,timeout) packer =
  let open MessagePackBinIO.Unpack
      val timeout = !timeout
      val ((ret, err), cin') =
          (case timeout of SOME t => Timeout.apply t | NONE => I)
              (doUnpack (unpackPair (unpackOption packer, unpackOption unpackString))) (!cin)
   in cin := cin'
    ; case (ret, err)
        of (SOME ret, NONE) => ret
         | (_, SOME e) => raise Remote_Calling_Failure {func_name=NONE, message=e}
         | _ => error "Invalid connection protocal. This is a bug and please report to xqyww123@gmail.com"
  end

fun write (_,cout,_) packer data =
  let open MessagePackBinIO.Pack
   in doPack (packPair (packer, packUnit)) (data, ()) cout
    ; BinIO.StreamIO.flushOut cout
  end

fun write_error' (_,cout,_) packer {message, errobj} =
  let open MessagePackBinIO.Pack
   in doPack (packPair (packOption packUnit, packPair (packList packString, packer)))
             (NONE, (message, errobj)) cout
    ; BinIO.StreamIO.flushOut cout
  end

fun write_error conn exn =
      write_error' conn MessagePackBinIO.Pack.packUnit
                        {message=Runtime.exn_message_list exn, errobj=()}


type ('a,'b) command = {
  name : string,
  arg_schema : 'a MessagePackBinIO.Pack.packer,
  ret_schema : 'b MessagePackBinIO.Unpack.unpacker,
  callback : (connection -> unit) option,
  timeout : Time.time option
}


(** Command Interface **)

exception RPC_Fail of string

fun call_command' {name, arg_schema, ret_schema, callback, timeout} conn arg =
  let open MessagePackBinIO.Pack MessagePackBinIO.Unpack
      val _ = (#3 conn) := timeout
      val _ = write conn (packPair (packString, arg_schema)) (name, arg)
   in (case callback of SOME C => C conn | NONE => ())
    ; read conn ret_schema
  end handle MessagePackBinIO.Unpack.Unpack =>
      raise Remote_Calling_Failure {func_name=SOME name, message="Invalid response, protocal error"}
  

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

val heartbeat_cmd = {
  name = "heartbeat",
  arg_schema = packUnit,
  ret_schema = unpackUnit,
  callback = NONE,
  timeout = SOME (Time.fromSeconds 10)
}

fun heartbeat conn = call_command' heartbeat_cmd conn ()

val load_cmd = {
  name = "load_pymodule",
  arg_schema = packList packString,
  ret_schema = unpackPairList (unpackString, unpackOption unpackString),
  callback = NONE,
  timeout = SOME (Time.fromSeconds 30)
}

end

(** Connection Pool **)

val connection_pool : (connection * Time.time) list Synchronized.var
      = Synchronized.var "PyProxy.connection_pool" []
val connection_pool_cleaner_event : Event_Timer.request option Unsynchronized.ref
      = Unsynchronized.ref NONE

fun get_connection () =
  case Synchronized.change_result connection_pool (
        fn [] => (NONE, [])
         | (x,_)::L => (SOME x, L) )
    of SOME conn =>
          if can heartbeat conn then conn else get_connection ()
     | NONE => make_connection ()

val TTL = Time.fromSeconds 60
val TTL' = TTL + Time.fromSeconds 1

fun clean_connection_i conns =
  let val now = Time.now ()
      fun clean [] = []
        | clean ((x,t) :: L) =
            if now - t >= TTL
            then let val (cin,cout,_) = x
              in BinIO.StreamIO.closeOut cout
               ; BinIO.StreamIO.closeIn (!cin)
               ; clean L
             end
            else (x,t) :: L
   in clean conns
  end

fun clean_connection_action () =
  Synchronized.change connection_pool (fn L =>
    let val L' = clean_connection_i L
     in (case L' of [] => connection_pool_cleaner_event := NONE
          | (_, t) :: _ => connection_pool_cleaner_event :=
              SOME (Event_Timer.request {physical=false} (t + TTL') clean_connection_action) )
      ; L'
    end )

fun release_connection conn =
  Synchronized.change connection_pool (fn L =>
    let val L' = clean_connection_i L
        val now = Time.now ()
     in (case L' of [] => ()
          | _ =>
         case !connection_pool_cleaner_event
           of SOME _ => ()
            | NONE => connection_pool_cleaner_event :=
                SOME (Event_Timer.request {physical=false} (now + TTL') clean_connection_action))
      ; (conn, now) :: L'
    end)

fun call_command cmd arg =
  let val conn = get_connection ()
   in \<^try>\<open>call_command' cmd conn arg
      finally release_connection conn\<close>
  end

fun load packages =
  let val errs = call_command load_cmd packages
   in if exists (is_some o snd) errs
    then error (String.concat (maps (fn (_, NONE) => []
                  | (lib, SOME e) => ["Fail to load ", lib, ": ", e, "\n\n"]) errs))
    else ()
  end

end
