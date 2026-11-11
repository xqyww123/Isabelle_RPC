(*  Title:      Isabelle_RPC/Tools/pide_loader.ML
    Author:     Qiyuan Xu

Theories loaded through the PIDE document of a PIDE_Loader.Session
(src/scala/pide_loader.scala), with the read interface of Build over one scope: the heap
theories and the pinned theories (loaded cleanly from source, held for the rest of the
process).

  - A loaded theory becomes visible when its request ends.
  - Code running at load time resolves names against its own context.
  - Every function that may call Scala -- use_theories, lookup_theory (and so
    defined_theory, get_theory) on a memo miss, all_theories, the init function of
    init_theory -- must never run on the protocol thread, which delivers Scala's answer:
    a protocol command handler forks first.

Theories begun by the REPL itself (init_theory) get the header options and the
`condition` of PIDE's document nodes: init_theory and with_theory_options.
*)

signature PIDE_LOADER =
sig
  val use_theories: string -> Path.T -> string list -> theory list
  val all_theories: unit -> string list
  val lookup_theory: string -> theory option
  val defined_theory: string -> bool
  val get_theory: string -> theory
  val init_theory: Options.update_pos -> theory -> Toplevel.init
  val with_theory_options: (Toplevel.state -> 'a) -> Toplevel.state -> 'a
  val is_document_message: Properties.T -> bool
end;

structure PIDE_Loader: PIDE_LOADER =
struct

(* theory values of pinned nodes, by long name: they never change, names are unique *)

val pinned =
  Synchronized.var \<^unchecked_name>\<open>PIDE_Loader.pinned\<close> (Symtab.empty: theory Symtab.table);

(*(theory, node, command): node = "" for a heap theory*)
val decode_loaded = YXML.parse_body #> let open XML.Decode in triple string string int end;

fun node_theory (name, node, command) =
  if node = "" then Build.get_theory name
  else
    (case Symtab.lookup (Synchronized.value pinned) name of
      SOME thy => thy
    | NONE =>
        (case Document.command_exec (Document.state ()) node command of
          SOME (eval, _) =>
            let
              val thy = Toplevel.end_theory Position.none (Command.eval_result_state eval);
              val _ = Thm.consolidate_theory thy;
            in
              Synchronized.change_result pinned (fn tab =>
                (case Symtab.lookup tab name of
                  SOME thy' => (thy', tab)
                | NONE => (thy, Symtab.update (name, thy) tab)))
            end
        | NONE => error ("PIDE_Loader: no execution for theory " ^ quote name)));


(* loading *)

(*the \<^scala> names stay checked: the session must not build without its jar*)
fun load qualifier master_dir imports =
  \<^scala>\<open>isabelle_rpc.use_theories\<close>
    (qualifier :: File.absolute_path master_dir :: imports)
  |> map (node_theory o decode_loaded);

(*on a Future worker, wait by Future.join, not inside Scala.function: a join marks the
  worker as waiting (future.ML:86), so the document's node tasks still find a worker.
  The caller is interruptible only inside the join, the loader thread only inside f, so the
  promise is always fulfilled and an interrupted join always cancels the load (scala.ML:44-66)*)
fun on_plain_thread f =
  if is_none (Future.worker_task ()) then f ()
  else
    Thread_Attributes.uninterruptible_body (fn run =>
      let
        val result = Future.promise_name \<^unchecked_name>\<open>PIDE_Loader.use_theories\<close> I;
        val thread =
          Isabelle_Thread.fork (Isabelle_Thread.params "PIDE_Loader") (fn () =>
            Future.fulfill_result result (Exn.capture_body (Future.interruptible_task f)));
      in
        (case Exn.capture_body (fn () => run Future.join result) of
          Exn.Res res => res
        | Exn.Exn exn =>
           (if Exn.is_interrupt exn then Isabelle_Thread.interrupt_thread thread else ();
            Exn.reraise exn))
      end);

(*all or nothing: if every import is a heap theory, answer in ML; otherwise Scala answers
  every import in place (it may turn a path into a heap theory)*)
fun use_theories qualifier master_dir imports =
  let
    val names =
      map (fn s => #theory_name (Resources.import_name qualifier master_dir s)) imports;
  in
    if forall Resources.loaded_theory names then map Build.get_theory names
    else on_plain_thread (fn () => load qualifier master_dir imports)
  end;


(* lookups by name: never loading *)

fun pinned_theory name =
  (case Symtab.lookup (Synchronized.value pinned) name of
    SOME thy => SOME thy
  | NONE =>
      \<^scala>\<open>isabelle_rpc.pinned_theory\<close> [name]
      |> try the_single |> Option.map (node_theory o decode_loaded));

fun lookup_theory name =
  (case Build.lookup_theory name of
    SOME thy => SOME thy
  | NONE => pinned_theory name);

val defined_theory = is_some o lookup_theory;

fun get_theory name =
  (case lookup_theory name of
    SOME thy => thy
  | NONE => error ("Theory loader: undefined entry for theory " ^ quote name));

fun all_theories () =
  Build.all_theories () @ \<^scala>\<open>isabelle_rpc.pinned_theories\<close> [];


(* header options of theories begun by the REPL: PIDE's document.ML:118, :638-646 *)

(*the theory options with the long name of the theory that stored them*)
structure Theory_Options = Theory_Data
(
  type T = (string * Options.update) option;
  val empty = NONE;
  val merge = fst;
);

fun init_theory header_options thy () =
  let
    val name = Context.theory_long_name thy;
    val decoded =
      (name, Options.update_no_pos header_options)
      |> let open XML.Encode in pair string (list (pair string (option string))) end
      |> YXML.string_of_body
      |> \<^scala>\<open>isabelle_rpc.eval_conditions\<close>
      |> YXML.parse_body |> Resources.decode_thy |> Resources.check_thy_errors;
    val ctxt = Proof_Context.init_global thy;
    val default = Options.the_process_default ();
    val _ =
      header_options |> List.app (fn spec =>
        ignore (Completion.check_option_value ctxt spec default));
    val _ = Resources.skipping_theory warning decoded;
    val thy' = Theory_Options.put (SOME (name, Options.update_no_pos (#options decoded))) thy;
  in {skip_theory = Resources.skip_theory decoded, theory = thy'} end;

fun theory_options thy =
  (case Theory_Options.get thy of
    SOME (name, options) => if name = Context.theory_long_name thy then options else []
  | NONE => []);

(*f st under the theory options of st, as PIDE wraps command execution (command.ML:249,
  :287-289); wrap one step, not a loop of steps*)
fun with_theory_options f st =
  Options.permissive_thread_update
    (case try Toplevel.theory_of st of
      SOME thy => theory_options thy
    | NONE => []) f st;


(* messages of the document: the routing rule of standard_message (isabelle_process.ML:98-105)
   and of Session (session.scala:757-761) *)

fun is_document_message props =
  is_some (Position.id_of
    (if exists Markup.position_property props then Position.of_properties props
     else Position.thread_data ()));

end;
