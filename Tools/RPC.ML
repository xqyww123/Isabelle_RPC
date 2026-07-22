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

val trim_markup: string -> string
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

fun trim_markup msg =
  let fun auto _ [] = []
        | auto acc (#"\005" :: L) = auto (not acc) L
        | auto true (x :: L) = x :: auto true L
        | auto false (_ :: L) = auto false L
   in String.implode (auto true (String.explode msg))
  end

type connection = BinIO.StreamIO.instream Unsynchronized.ref
                * BinIO.StreamIO.outstream
                * Time.time option Unsynchronized.ref (*read timeout*)

exception Read_Timeout
exception Remote_Calling_Failure of {func_name: string option, message: string}

(** TCP **)

(* RPC_EPHEMERAL_HOST_PLAN.md v3.3: "whoever launches the host owns its lifetime".
   RPC_Host set   -> Fixed: external launch, external lifecycle; Isabelle only connects,
                     and errors if nothing listens.  Isabelle NEVER launches at a
                     configured address (v2's fixed-addr auto-launch is abolished, and
                     AUTO_START_RPC_SERVER with it -- the variable is ignored).
   RPC_Host unset -> Ephemeral: a per-ML-process attached host on an OS-assigned port,
                     lifetime-bound to this process (JVM reap + TCP lifeline + leak
                     guard).  The old 127.0.0.1:27182 default is gone. *)
datatype addr_mode = Fixed of string * string | Ephemeral

fun addr_mode () =
  (case getenv "RPC_Host" of
    "" => Ephemeral
  | addr =>
      (case space_explode ":" addr of
        [h, p] => Fixed (h, p)
      | _ => error ("Invalid RPC address: " ^ addr ^ ". Should be `host:port`.")))

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

(* Which Python runs the RPC host.

   ISABELLE_RPC_PYTHON wins outright when set.  Isabelle ships no Python and defines no
   ISABELLE_PYTHON convention -- searched in etc/settings and lib/scripts/getsettings --
   so this does not shadow anything of its own.  It is the same shape as
   ISABELLE_VECTOR_SO in Semantic_Embedding: an explicit override first, discovery second.

   The probe below is WRONG BY CONSTRUCTION on Windows and is kept only as the non-conda
   fallback.  Isabelle_System.bash_process runs under Isabelle's BUNDLED CYGWIN bash, so
   `command -v python3` resolves against the Cygwin PATH and finds a Cygwin interpreter --
   which cannot even have our host installed, because Cygwin CPython reports platform tags
   like cygwin_3_x_x_x86_64 and cannot install a win_amd64 wheel.  The symptom is
   `ModuleNotFoundError: No module named 'Isabelle_RPC_Host'` at launch.

   LAZY, and that is the load-bearing part.  As a top-level `val` this was evaluated when
   RPC.ML loaded -- i.e. during `isabelle build Isabelle_RPC` -- and the result was frozen
   into the session heap.  Isabelle's session digest is content-based, so changing an
   environment variable does not invalidate that heap: a user who read the error below,
   set ISABELLE_RPC_PYTHON and re-ran would get the identical failure, from the value
   baked in at build time.  simd_vector.ML:47 wraps the same getenv-then-discover shape in
   Lazy.lazy for exactly this reason; an earlier draft of this fix copied its ordering and
   not its deferral, which is the half that matters.

   Deliberately NOT verified here.  Checking that the candidate can `import
   Isabelle_RPC_Host` would cost a subprocess on every first use, and it could not repair
   anything -- there is no second candidate to fall back to.  The check earns its keep
   only once a launch has already failed, so it lives in launch_RPC_host's error path,
   where it turns an opaque traceback into an actionable message. *)
val python_cmd = Lazy.lazy (fn () =>
  let val configured = getenv "ISABELLE_RPC_PYTHON"
   in if configured <> "" then configured
      else
        let val check_python =
              Isabelle_System.bash_process (Bash.script "command -v python3 || command -v python")
            val py_path = Process_Result.out check_python |> Library.trim_line
         in if py_path = "" then "python3"  (* fallback *)
            else py_path
        end
  end)

(* CAUTION: the make_directory here is a BUILD-TIME side effect, frozen into session
   heaps exactly like a top-level python probe would be (see python_cmd above).  On a
   machine running distributed prebuilt heaps it may never have run.  Only the PATH
   value below may be relied on; the attached-launch script re-creates the directory
   with `mkdir -p` at every launch. *)
val log_dir = (Path.variable "ISABELLE_HOME_USER" + Path.basic "log")
           |> Isabelle_System.make_directory


fun parse_addr (h,p) =
   let fun err () = error ("Bad address " ^ h ^ ":" ^ p)
       val host = case NetHostDB.getByName h of SOME host => host | NONE => err ()
       val port = case Int.fromString p of SOME port => port | NONE => err ()
    in INetSock.toAddr (NetHostDB.addr host, port)
   end

fun connect_retry addr remaining =
  if remaining <= 0
  then error (String.concat
           ["Fail to connect to RPC host on ", #1 addr, ":", #2 addr,
            " after launch (timed out)."])
  else
    let val sock = INetSock.TCP.socket ()
        val addr' = parse_addr addr
     in if Socket.connectNB (sock, addr')
        then (tracing (String.concat ["RPC Host on ", #1 addr, ":", #2 addr, " is ready."]); sock)
        else let
          val {wrs, exs, ...} = Socket.select {
              rds = [],
              wrs = [Socket.sockDesc sock],
              exs = [Socket.sockDesc sock],
              timeout = SOME (Time.fromSeconds 1) }
         in case (wrs, exs)
              of (_::_, []) =>
                  if Socket.Ctl.getERROR sock
                  then (Socket.close sock; OS.Process.sleep (Time.fromSeconds 1);
                        connect_retry addr (remaining - 1))
                  else (tracing (String.concat ["RPC Host on ", #1 addr, ":", #2 addr, " is ready."]); sock)
               | _ => (Socket.close sock; OS.Process.sleep (Time.fromSeconds 1);
                       connect_retry addr (remaining - 1))
        end
    end

val launch_lock : unit Synchronized.var = Synchronized.var "RPC.launch_lock" ()

(** Ephemeral attached-host state (RPC_EPHEMERAL_HOST_PLAN.md v3.3, §3.4)

  ONE Synchronized.var holds the whole record -- the lifeline lives INSIDE it, so
  "close the old lifeline whenever the record is replaced or cleared" holds by
  construction, and every invalidation is token-conditional: a stale clear can never
  close a newer record's lifeline.  The lifeline is kept as a sock_desc (for the
  zero-timeout liveness poll) plus a closing closure, which avoids spelling the
  concrete socket type.

  Heap inheritance: this var's contents get saved into session heaps.  The pid stamp
  (ML_Pid.get () of the LAUNCHING process) detects that: a mismatch means the record
  was inherited -- treat as absent, and NEVER close its socket (the embedded fd number
  may alias an unrelated open file in this process). **)

type attached_host =
  {pid: int, addr: string * string, token: string,
   lifeline_desc: Socket.sock_desc, close_lifeline: unit -> unit}

val attached_host : attached_host option Synchronized.var =
  Synchronized.var "RPC.attached_host" NONE

(* Not a credential (threat model: accidental cross-connection on localhost).  The pid
   field doubles as the log-sweep liveness key (launch script) and makes heap-sibling
   serial collisions harmless. *)
fun new_token () =
  string_of_int (ML_Pid.get ()) ^ "-" ^ serial_string () ^ "-" ^
  LargeInt.toString (Time.toMicroseconds (Time.now ()))

fun attached_file ext token =
  log_dir + Path.basic ("RPC_attached_" ^ token ^ "." ^ ext)

fun read_attached_state () =
  (case Synchronized.value attached_host of
    NONE => NONE
  | SOME s => if #pid s = ML_Pid.get () then SOME s else NONE)

fun install_attached (s : attached_host) =
  Synchronized.change attached_host (fn prev =>
    ( (case prev of
        SOME p => if #pid p = ML_Pid.get () then #close_lifeline p () else ()
      | NONE => ())
    ; SOME s))

fun invalidate_attached_if token =
  Synchronized.change attached_host (fn
      SOME s =>
        if #token s = token andalso #pid s = ML_Pid.get ()
        then (#close_lifeline s (); NONE)
        else SOME s   (*stale invalidation: a newer record must survive untouched*)
    | NONE => NONE)

(* The host side is write-silent after the claim ack, so ANY readability on the
   lifeline means EOF/RST means our host is dead; an errored select on a stale
   descriptor counts as dead too.  This is the tiebreaker that resolves indeterminate
   handshake outcomes (§3.3): it distinguishes "host died, port squatted by a silent
   or garbage-speaking foreigner" (relaunch) from "own host merely busy/stalled"
   (keep state, never kill-by-relaunch). *)
fun lifeline_dead (s : attached_host) =
  (case Socket.select {rds = [#lifeline_desc s], wrs = [], exs = [],
                       timeout = SOME Time.zeroTime}
     of {rds = [], ...} => false
      | _ => true)
  handle OS.SysErr _ => true

fun ephemeral_log_hint () =
  (case read_attached_state () of
    SOME s => "\nThe session's ephemeral RPC host may have died; its log:\n    " ^
              File.platform_path (attached_file "log" (#token s))
  | NONE => "")

fun try_connect addr =
  let val sock = INetSock.TCP.socket ()
      val addr' = parse_addr addr
   in if Socket.connectNB (sock, addr')
      then SOME sock
      else let
        val {wrs, exs, ...} = Socket.select {
            rds = [],
            wrs = [Socket.sockDesc sock],
            exs = [Socket.sockDesc sock],
            timeout = SOME (Time.fromSeconds 5) }
       in case (wrs, exs)
            of (_::_, []) =>
                if Socket.Ctl.getERROR sock
                then (Socket.close sock; NONE)
                else SOME sock
             | _ => (Socket.close sock; NONE)
      end
  end

fun mk_conn socket : connection =
  let val (cin, cout) = make_streams_timeout socket
   in (Unsynchronized.ref cin, cout, Unsynchronized.ref NONE)
  end

fun close_connection (conn : connection) =
  let val (cin, cout, _) = conn
   in BinIO.StreamIO.closeOut cout
    ; BinIO.StreamIO.closeIn (!cin)
  end

(*make_connection is defined AFTER the tagged-IO layer (it needs the identity
  handshake); see "Ephemeral attached-host launch" below.*)

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
                        {message=map trim_markup (Runtime.exn_message_list exn), errobj=()}


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
                  (cb_id, (NONE, SOME (String.concatWith "\n" (map trim_markup (Runtime.exn_message_list exn))))) cout
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
      raise Remote_Calling_Failure {func_name=SOME name,
        message="Invalid response, protocol error" ^ ephemeral_log_hint ()}
  

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

(** Ephemeral attached-host launch (RPC_EPHEMERAL_HOST_PLAN.md v3.3, §3.1-§3.3)

  Lock discipline: everything here that creates a connection while `launch_lock` is
  held is hand-built from the raw socket (try_connect/connect_retry + mk_conn) --
  never via get_connection/make_connection, whose paths re-enter this machinery and
  would self-deadlock the non-reentrant mutex. **)

local open MessagePackBinIO.Pack MessagePackBinIO.Unpack in

datatype identity_verdict = Ours | Not_Ours | Indeterminate of exn

(* Structural outcome classification, no string matching (§3.3): a healthy own host
   cannot error this call (rpc_host_identity returns a stored constant), so ANY tag-1
   reply -- "Unknown procedure" from an old wheel, a rejection from a foreign RPC host,
   an externally-launched host's NONE token -- means "not our host".  Timeouts and
   protocol garbage are indeterminate; the caller resolves them with the
   lifeline-liveness tiebreaker. *)
fun check_identity expected_token timeout conn =
  ( (#3 conn) := SOME timeout
  ; (case (write conn (packPair (packString, packUnit)) ("rpc_host_identity", ());
           read_tagged (unpackOption unpackString) conn) of
      User_Response (SOME tok) => if tok = expected_token then Ours else Not_Ours
    | User_Response NONE => Not_Ours
    | Remote_Error _ => Not_Ours
    | Callback_Request _ => Not_Ours)
    handle Timeout.TIMEOUT t => Indeterminate (Timeout.TIMEOUT t)
         | Read_Timeout => Indeterminate Read_Timeout
         | Unpack => Indeterminate
             (Remote_Calling_Failure {func_name = SOME "rpc_host_identity",
                                      message = "protocol error during identity handshake"})
         | exn as IO.Io _ => Indeterminate exn
         | exn as OS.SysErr _ => Indeterminate exn )

(* Validate the stored record on a fresh connection (§3.3 reconnect path, 10 s).
   SOME conn = live own host; NONE = definitively not ours (record invalidated,
   token-conditionally).  Indeterminate + dead lifeline -> not ours; indeterminate +
   live lifeline -> KEEP the state and re-raise to the caller: never kill-by-relaunch
   a merely busy host (documented event-loop stalls reach 17-179 s). *)
fun validate_attached (s : attached_host) : connection option =
  (case try_connect (#addr s) of
    NONE => (invalidate_attached_if (#token s); NONE)
  | SOME sock =>
      let val conn = mk_conn sock
       in (case check_identity (#token s) (Time.fromSeconds 10) conn of
            Ours => SOME conn
          | Not_Ours =>
              (close_connection conn; invalidate_attached_if (#token s); NONE)
          | Indeterminate exn =>
              if lifeline_dead s
              then (close_connection conn; invalidate_attached_if (#token s); NONE)
              else (close_connection conn; Exn.reraise exn))
      end)

fun do_launch_attached () : connection =
  let
    val token = new_token ()
    val ready_file = attached_file "info" token
    val log_path = attached_file "log" token
    val log_dir_p = Bash.string (File.platform_path log_dir)
    (*attempt-local acquisitions: step-7 cleanup is scoped to THIS attempt -- an
      Interrupt can be delivered at lock-body entry (a thread interrupted while queued
      on launch_lock), and an unscoped cleanup would destroy a sibling's fresh host*)
    val acquired : attached_host option Unsynchronized.ref = Unsynchronized.ref NONE
    val installed = Unsynchronized.ref false
    val holder_outcome : Process_Result.T Exn.result option Synchronized.var =
          Synchronized.var "RPC.holder_outcome" NONE

    val script = String.concat
      [ (*created at EVERY launch: log_dir's make_directory side effect is heap-frozen*)
        "mkdir -p ", log_dir_p, "\n"
      , "export ISABELLE_HOME=", Bash.string (getenv "ISABELLE_HOME"), "\n"
      , "export ISABELLE_HOME_USER=", Bash.string (getenv "ISABELLE_HOME_USER"), "\n"
        (*stale-file sweep, POSIX only (Cygwin kill(1) cannot probe native pids).
          Ready-files older than 10 min are crashed predecessors' debris -- the age
          bound protects concurrent siblings' in-flight ready-files (launch_lock is
          per-process; this directory is shared).  Logs older than 7 days go only if
          the ML pid leading their token is dead (kill -0; false keep on pid reuse is
          harmless -- never unlink a live session's log).*)
      , "case \"$(uname -s 2>/dev/null)\" in CYGWIN*|MSYS*) : ;; *)\n"
      , "  find ", log_dir_p,
           " -maxdepth 1 -name 'RPC_attached_*.info' -mmin +10 -delete 2>/dev/null\n"
      , "  for f in $(find ", log_dir_p,
           " -maxdepth 1 -name 'RPC_attached_*.log' -mtime +7 2>/dev/null); do\n"
      , "    p=$(basename \"$f\"); p=${p#RPC_attached_}; p=${p%%-*}\n"
      , "    kill -0 \"$p\" 2>/dev/null || rm -f \"$f\"\n"
      , "  done ;;\n"
      , "esac\n"
      , "exec ", Bash.string (Lazy.force python_cmd)
      , " -c \"import Isabelle_RPC_Host\nIsabelle_RPC_Host.run_attached__()\" "
      , Bash.string "127.0.0.1:0", " "
      , Bash.string (File.platform_path log_path), " "
      , Bash.string (File.platform_path ready_file), " "
      , Bash.string token
        (*BOTH stdio streams to the log: an attached child's inherited pipes would
          otherwise accumulate in JVM heap for the host's whole life and be lost at
          its os._exit*)
      , " >> ", Bash.string (File.platform_path log_path), " 2>&1" ]

    fun fail_diagnosis reason =
      let val py = Lazy.force python_cmd
          (*attribute reference, not a bare import: a plain `import Isabelle_RPC_Host`
            SUCCEEDS on an old wheel and would hide the version skew*)
          val probe = Isabelle_System.bash_process (Bash.script
            (Bash.string py ^
             " -c 'import Isabelle_RPC_Host; Isabelle_RPC_Host.run_attached__'"))
          val hint =
            if Process_Result.ok probe then ""
            else "\n\nThe interpreter used was:\n    " ^ py ^
                 "\nand probing it failed with:\n" ^ Process_Result.err probe ^
                 (if getenv "ISABELLE_RPC_PYTHON" <> "" then
                    "\nThat interpreter came from ISABELLE_RPC_PYTHON; point it at one\
                    \ that has an Isabelle_RPC_Host wheel >= 0.4.0 installed\
                    \ (run_attached__ must exist)."
                  else
                    "\nIt was discovered with `command -v python3` under Isabelle's bash\
                    \ (Cygwin on Windows -- it finds a Cygwin interpreter rather than the\
                    \ native one wheels are installed into).  Set ISABELLE_RPC_PYTHON to\
                    \ an interpreter with an Isabelle_RPC_Host wheel >= 0.4.0.")
          val log_tail =
            (case try File.read log_path of
              SOME s =>
                let val lines = split_lines s
                    val tail =
                      if length lines > 20
                      then List.drop (lines, length lines - 20) else lines
                 in "\n\nHost log tail (" ^ File.platform_path log_path ^ "):\n" ^
                    cat_lines tail
                end
            | NONE => "")
       in error ("Failed to launch the attached RPC host: " ^ reason ^ hint ^ log_tail)
      end

    fun launch_body () =
      let
        (*holder thread: blocks in bash_process for the host's whole life; forked with
          default params = uninterruptible, so no spurious interrupt can kill the host.
          Its result is recorded so the poll below fails fast on instant death instead
          of burning the 40 s budget.  When the host eventually dies, bash_process
          returns and the thread ends -- holders never accumulate.*)
        val _ = Isabelle_Thread.fork (Isabelle_Thread.params "rpc_attached_host_holder")
                  (fn () =>
                    let val res = Exn.capture (fn () =>
                          Isabelle_System.bash_process (Bash.script script)) ()
                     in Synchronized.change holder_outcome (K (SOME res)) end)
        fun poll 0 = fail_diagnosis "timed out waiting for the ready-file"
          | poll n =
              if File.exists ready_file then ()
              else if is_some (Synchronized.value holder_outcome)
              then fail_diagnosis "the launched python exited before binding"
              else (OS.Process.sleep (Time.fromSeconds 1); poll (n - 1))
        val _ = poll 40
        val (port, token') =
          (case File.read ready_file |> String.tokens Char.isSpace of
            [port, tok] => (port, tok)
          | _ => fail_diagnosis "malformed ready-file")
        val _ = token' = token orelse fail_diagnosis "ready-file token mismatch"
        val _ = try File.rm ready_file
        val addr = ("127.0.0.1", port)
        val sock = connect_retry addr 20
        val conn = mk_conn sock
        (*60 s launch-path handshake: must cover the <= 40 s component-import window
          that run_attached__ places AFTER bind (our connection sits in the TCP backlog
          meanwhile)*)
        val _ =
          (case check_identity token (Time.fromSeconds 60) conn of
            Ours => ()
          | _ => (close_connection conn;
                  fail_diagnosis "the launched host failed the identity handshake"))
        (*lifeline: tight uninterruptible bubble around connect-then-record, so an
          async Interrupt between the two cannot orphan a claimed lifeline*)
        val lsock =
          Thread_Attributes.uninterruptible (fn _ => fn () =>
            let val s =
                  (case try_connect addr of
                    SOME s => s
                  | NONE => raise Fail "lifeline connect failed")
                val host : attached_host =
                  {pid = ML_Pid.get (), addr = addr, token = token,
                   lifeline_desc = Socket.sockDesc s,
                   close_lifeline = fn () => Socket.close s handle OS.SysErr _ => ()}
             in acquired := SOME host; s end) ()
        val lconn = mk_conn lsock
        val _ = (#3 lconn) := SOME (Time.fromSeconds 60)
        val _ = write lconn (packPair (packString, packString))
                      ("attached_lifeline", token)
        val _ =
          (case read_tagged unpackUnit lconn of
            User_Response () => ()   (*the claim ack; the host never writes again*)
          | Remote_Error err => raise Fail ("lifeline claim rejected: " ^ err)
          | Callback_Request _ => raise Fail "lifeline claim was not acked")
        (*install is the LAST act: on any earlier failure the state var still holds
          nothing of this attempt's*)
        val _ = install_attached (the (! acquired))
        val _ = installed := true
        val _ = tracing ("Attached RPC host ready on 127.0.0.1:" ^ port ^
                         "  Log: " ^ File.platform_path log_path)
       in conn end
  in
    \<^try>\<open>launch_body ()
    catch exn =>
      ( (*attempt-scoped cleanup (uninterruptible handler): close only THIS attempt's
          lifeline; the state var was never touched unless install succeeded*)
        (if ! installed then ()
         else (case ! acquired of SOME h => #close_lifeline h () | NONE => ()))
      ; (try File.rm ready_file; ())
      ; Exn.reraise exn)\<close>
  end

fun ephemeral_connection () =
  let
    fun revalidate () =
      (case read_attached_state () of
        SOME s => validate_attached s
      | NONE => NONE)
  in
    (case revalidate () of   (*fast path, outside the lock*)
      SOME conn => conn
    | NONE =>
        Synchronized.change_result launch_lock (fn () =>
          ((case revalidate () of   (*step 0: in-lock re-check -- replaces the old
                                      addr-keyed try_connect double-check, which has
                                      no addr to probe before a launch*)
             SOME conn => conn
           | NONE => do_launch_attached ()), ())))
  end

end

fun make_connection () : connection =
  (case addr_mode () of
    Fixed (h, p) =>
      (case try_connect (h, p) of
        SOME sock => mk_conn sock
      | NONE =>
          error ("RPC_Host=" ^ h ^ ":" ^ p ^ " is set but nothing is listening.\n\
            \Setting RPC_Host means the host is launched and managed externally:\
            \ start it with `isabelle-rpc-host` or\n\
            \  python -c 'import Isabelle_RPC_Host; Isabelle_RPC_Host.fork_and_launch__()' " ^
            h ^ ":" ^ p ^ " <log-file>\n\
            \or unset RPC_Host to get an automatic per-session host."))
  | Ephemeral => ephemeral_connection ())

(** Connection Pool **)

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
