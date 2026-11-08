/*  Title:      Isabelle_RPC/src/scala/pide_loader.scala
    Author:     Qiyuan Xu

PIDE_Loader: load theories from source into the PIDE document of the session, as
Isabelle/jEdit and Headless do, and hand Isabelle/ML each theory's node and last command,
whose end state is the theory value (Tools/pide_loader.ML).  Only inside a
PIDE_Loader.Session, which owns the loader and its Resources.

The table holds exactly what the loader put into the document.  A node's text and its
loaded files are read from disk once, when the node enters the table, and stay unchanged
while it is held; the table changes together with the document edit that describes it,
uninterruptibly.  A node that loads cleanly stays required for the rest of the session
(pinned), so the theory value ML reads off its last command never changes.  At most one
node per long theory name.

Locking: the table is an immutable value.  Its only writers, submit and release, serialize
on the loader's lock and publish the new table when they commit.  Every reader reads the
published table and never takes the lock: Isabelle's change_parser (thy_syntax.scala:232
-> command.scala:447) and session manager (protocol.scala:352 -> command.scala:558) call
import_name while submit holds the lock and waits for them.
*/

package isabelle.isabelle_rpc

import isabelle._

import scala.annotation.tailrec
import scala.util.parsing.input.Reader


object PIDE_Loader {
  /* one per requested theory; node = "" for a theory of the session heap */
  sealed case class Loaded(theory: String, node: String, command: Document_ID.Command) {
    def encode: XML.Body = {
      import XML.Encode._
      triple(string, string, long)(theory, node, command)
    }
  }

  private val PIN: Long = 0L

  /* no PIDE markup reports for loaded nodes */
  val node_options: Options.Update = List(Options.Spec.make("pide_reports=false"))

  def get(session: isabelle.Session): Option[PIDE_Loader] =
    session match {
      case s: Session => Some(s.loader)
      case _ => None
    }

  def the(session: isabelle.Session): PIDE_Loader =
    get(session) getOrElse
      error("Theories are loaded only inside a PIDE_Loader.Session (Isabelle_RPC), not in " +
        session.getClass.getName)


  /* the session: its Resources, non-interactive, the loader as protocol handler
     (Isabelle's pattern: Headless.Session, JEdit_Session) */

  abstract class Session(
    options: Options,
    background: Sessions.Background,
    node_options: Options.Update = PIDE_Loader.node_options
  ) extends isabelle.Session {
    // a def: the super constructor reads it (session.scala:148)
    override def session_options: Options = options
    final override def interactive: Boolean = false
    final lazy val loader: PIDE_Loader = new PIDE_Loader(node_options)
    final override lazy val resources: Resources = new Resources(background, loader)
    init_protocol_handler(loader)
  }


  /* Resources: for a theory the loader holds, both disk questions (find_theory_node,
     with_thy_reader) are answered from the table; otherwise super */

  class Resources private[isabelle_rpc](background: Sessions.Background, loader: PIDE_Loader)
    extends isabelle.Resources(background, background, Logger.none)
  {
    /* a node is the file's canonical platform path, symlinks resolved, as in jEdit
       (jedit_resources.scala:52-65); Isabelle's default: File.symbolic_path
       (resources.scala:189-190) */
    override def append_path(prefix: String, source_path: Path): String = {
      val path = (Path.explode(File.standard_path(prefix)) + source_path).expand
      File.canonical(File.platform_file(path)).getPath.nn
    }

    /* read once: a held node's text as it entered the table
       (precedents: jedit_resources.scala:97-114, vscode_resources.scala:168-174) */
    override def with_thy_reader[A](name: Document.Node.Name, f: Reader[Char] => A): A =
      loader.held_text(name) match {
        case Some(text) => f(Scan.char_reader(text))
        case None => super.with_thy_reader(name, f)
      }

    /* an empty theory file is an error naming the theory; Isabelle's Thy.empty has no name
       (resources.scala:350) */
    override def check_thy(
      node_name: Document.Node.Name,
      reader: Reader[Char],
      more_options: Options.Update,
      initiators: List[Document.Node.Name],
      command: Boolean,
      strict: Boolean
    ): isabelle.Resources.Thy =
      if (node_name.is_theory && reader.source.length == 0) {
        isabelle.Resources.Thy(name = node_name, errors = List("Empty theory file"))
      }
      else super.check_thy(node_name, reader, more_options, initiators, command, strict)

    /* a held session theory keeps its node when its file is gone (Isabelle checks the disk,
       resources.scala:259); never a Draft name, whose file may lie in any folder */
    override def find_theory_node(theory: String): Option[Document.Node.Name] =
      (if (sessions_structure.defined(sessions_structure.theory_qualifier(theory)))
        loader.held_node(theory) else None) orElse super.find_theory_node(theory)

    /* a file is named by the folder it lies in, not by who asks: the name recorded when it
       entered the table, else S.<file name> for a folder of a known session S (find_theory,
       resources.scala:287-295), else Draft.<file name>; a heap theory's source file is the
       heap theory.  Isabelle's own import_name chooses the file. */
    override def import_name(qualifier: String, prefix: String, s: String): Document.Node.Name = {
      val name = super.import_name(qualifier, prefix, s)
      if (loaded_theory(name) || name.node == name.theory) name
      else {
        loader.held_name(name) getOrElse {
          find_theory(name.path.file) match {
            case Some(found) if loaded_theory(found) =>
              Document.Node.Name.loaded_theory(found.theory)
            case Some(found) => found
            case None =>
              Document.Node.Name(name.node,
                theory = Long_Name.qualify(Sessions.DRAFT, name.theory_base_name))
          }
        }
      }
    }
  }


  /* Scala functions (registered in RPC_Functions) */

  private def encode_loaded(loaded: List[Loaded]): List[Bytes] =
    loaded.map(l => Bytes(YXML.string_of_body(l.encode)))

  object Use_Theories_Fun extends Scala.Fun("isabelle_rpc.use_theories", thread = true) {
    val here = Scala_Project.here
    override def invoke(session: isabelle.Session, args: List[Bytes]): List[Bytes] =
      args.map(_.text) match {
        case qualifier :: master_dir :: theories =>
          encode_loaded(PIDE_Loader.the(session).use_theories(qualifier, master_dir, theories))
        case _ => error("Bad arguments for isabelle_rpc.use_theories")
      }
  }

  object Pinned_Theory_Fun extends Scala.Fun("isabelle_rpc.pinned_theory") {
    val here = Scala_Project.here
    override def invoke(session: isabelle.Session, args: List[Bytes]): List[Bytes] =
      args.map(_.text) match {
        case List(theory) => encode_loaded(get(session).flatMap(_.pinned_theory(theory)).toList)
        case _ => error("Bad arguments for isabelle_rpc.pinned_theory")
      }
  }

  object Pinned_Theories_Fun extends Scala.Fun("isabelle_rpc.pinned_theories") {
    val here = Scala_Project.here
    override def invoke(session: isabelle.Session, args: List[Bytes]): List[Bytes] =
      get(session).map(_.pinned_theories).getOrElse(Nil).map(Bytes(_))
  }

  object Loader_Check_Fun extends Scala.Fun("isabelle_rpc.loader_check", thread = true)
    with Scala.Single_Fun
  {
    val here = Scala_Project.here
    override def invoke(session: isabelle.Session, args: List[Bytes]): List[Bytes] =
      List(Bytes(PIDE_Loader.the(session).check))
  }

  /* the conditions of a theory header, as Isabelle/Scala evaluates them for a node header
     (command.scala:446-448): argument the long theory name and the header options, result
     the encoded Resources.Thy */
  object Eval_Conditions_Fun extends Scala.Fun("isabelle_rpc.eval_conditions")
    with Scala.Single_Fun
  {
    val here = Scala_Project.here
    override def invoke(session: isabelle.Session, args: List[Bytes]): List[Bytes] = {
      val (theory, options) = {
        import XML.Decode._
        pair(string, list(pair(string, option(string))))(
          YXML.parse_body(YXML.Source(args.head.text)))
      }
      if (theory.isEmpty) error("isabelle_rpc.eval_conditions: empty theory name")
      val thy =
        isabelle.Resources.Thy(name = Document.Node.Name.loaded_theory(theory),
          options = options.map({ case (a, b) => Options.Spec(a, value = b) }))
      List(Bytes(YXML.string_of_body(
        isabelle.Resources.Thy.encode(thy.eval_conditions(session.conditions)))))
    }
  }
}


class PIDE_Loader private[isabelle_rpc](node_options: Options.Update)
  extends Session.Protocol_Handler
{
  private val _session = Synchronized[Option[Session]](None)
  private def session: Session = _session.value getOrElse error("PIDE_Loader: no session")

  /* wake-up stamp, bumped on every change of the document */
  private val stamp = Synchronized(0L)
  private val consumer =
    Session.Consumer[Session.Commands_Changed]("PIDE_Loader") { _ => stamp.change(_ + 1) }

  override def init(session: Session): Unit = {
    _session.change(_ => Some(session))
    session.commands_changed += consumer
  }

  override def exit(state: Document.State): Unit =
    _session.value.foreach(_.commands_changed -= consumer)


  /* the table */

  private sealed case class Node(
    name: Document.Node.Name,           // with the long theory name decided at entry
    thy: isabelle.Resources.Thy,
    text: String,                       // as read when the node entered the table
    files: List[Document.Node.Name],    // its loaded files
    required: Set[Long],                // request ids; PIN = loaded cleanly
    version: Long                       // the document version that inserted it
  ) {
    def pinned: Boolean = required(PIDE_Loader.PIN)
  }

  private sealed case class Table(
    nodes: Map[Document.Node.Name, Node] = Map.empty,   // Node.Name equality: by node only
    blobs: Map[Document.Node.Name, Document.Blobs.Item] = Map.empty
  ) {
    lazy val theories: Map[String, Node] =
      nodes.valuesIterator.map(node => node.name.theory -> node).toMap
    def doc_blobs: Document.Blobs = Document.Blobs(blobs)
  }

  private val writer = new Object                  // serializes submit and release
  @volatile private var table: Table = Table()     // the last committed table
  private val counter = Counter.make()

  private[isabelle_rpc] def held_name(name: Document.Node.Name): Option[Document.Node.Name] =
    table.nodes.get(name).map(_.name)
  private[isabelle_rpc] def held_node(theory: String): Option[Document.Node.Name] =
    table.theories.get(theory).map(_.name)
  private[isabelle_rpc] def held_text(name: Document.Node.Name): Option[String] =
    table.nodes.get(name).map(_.text)

  /* headless.scala:484-491 (Headless.Resources.Theory.make_edits) */
  private def node_edits(node: Node, text_edits: List[Text.Edit], required: Boolean)
    : List[Document.Edit_Text] =
    List(
      node.name -> Document.Node.Thy(node.thy),
      node.name -> Document.Node.Edits(text_edits),
      node.name -> Document.Node.Perspective(required, Text.Perspective.empty,
        Document.Node.Overlays.empty))

  /* send edits; the id of a version that contains them */
  private def update(blobs: Document.Blobs, edits: List[Document.Edit_Text]): Option[Long] =
    if (edits.isEmpty) None
    else {
      session.update(blobs, edits)
      Some(session.get_state().history.tip.version.join.id)
    }

  /* at most one node per long theory name: two files under one name are refused, naming both */
  private def duplicate(msg: String, theory: String): Nothing =
    error(msg +
      (if (Long_Name.qualifier(theory) == Sessions.DRAFT)
        "\nA theory file outside every known session is named Draft.<file name>;" +
        " make its session known (e.g. with option -d) to name it after that session"
       else ""))


  /* enter request id: join the nodes already in the table, insert the others; on error the
     table and the document stay unchanged (inside use_theories' uninterruptible region) */

  private def submit(id: Long, import_names: List[Document.Node.Name])
    : (List[Document.Node.Name], Document.Node.Name.Graph[Unit]) =
    writer.synchronized {
      val st = table
      val resources = session.resources
      val dependencies =
        resources.dependencies(session.conditions, import_names.map(_ -> Position.none))
          .check_errors
      val names = dependencies.theories

      for ((theory, ns) <- names.groupBy(_.theory) if ns.length > 1)
        duplicate("Theory " + quote(theory) + " requested from several files: " +
          commas_quote(ns.map(_.node)), theory)
      for {
        name <- names if !st.nodes.isDefinedAt(name)
        other <- st.theories.get(name.theory)
      } duplicate("Theory " + quote(name.theory) + " is already loaded from " +
          quote(other.name.node) + ", cannot load it from " + quote(name.node), name.theory)

      /* headless.scala:655-663 (load_theories), loaded files from the same text */
      val inserted =
        for (name <- names if !st.nodes.isDefinedAt(name)) yield {
          val text = File.read(name.path)
          val thy =
            resources.check_thy(name, Scan.char_reader(text), more_options = node_options)
              .eval_conditions(session.conditions)
          val syntax = dependencies.get_syntax(name)
          val spans = syntax.parse_spans(Symbol.decode(text)).filter(_.is_load_command(syntax))
          Node(name, thy, text, resources.loaded_files(syntax, name, spans), Set(id), 0L)
        }
      /* headless.scala:519-534 (State.update_blobs, blob_edits); a failed read names the
         first new theory that loads the file */
      val new_blobs =
        inserted.flatMap(node => node.files.map(_ -> node.name.theory))
          .distinctBy(_._1).filterNot(p => st.blobs.isDefinedAt(p._1)).map { (file, theory) =>
            val bytes =
              try { Bytes.read(file.path) }
              catch {
                case ERROR(msg) =>
                  cat_error(msg, "The error(s) above occurred for theory " + quote(theory))
              }
            val text = bytes.text
            file -> Document.Blobs.Item(bytes, text, Symbol.Text_Chunk(text), changed = true)
          }
      val edits =
        inserted.flatMap(node => node_edits(node, Text.Edit.inserts(0, node.text), true)) :::
        new_blobs.flatMap({ case (file, blob) =>
          List(file -> Document.Node.Blob(blob),
            file -> Document.Node.Edits(Text.Edit.inserts(0, blob.source))) })

      val version = update(Document.Blobs(st.blobs ++ new_blobs), edits)
      val joined =
        for (name <- names; node <- st.nodes.get(name))
          yield node.name -> node.copy(required = node.required + id)
      table = st.copy(
        nodes = st.nodes ++ joined ++
          inserted.map(node => node.name -> node.copy(version = version.get)),
        blobs = st.blobs ++ new_blobs.map({ case (file, blob) => file -> blob.unchanged }))
      (names, dependencies.theory_graph)
    }


  /* leave request id: pin the nodes that loaded cleanly; purge the nodes nobody requires any
     more (their text leaves the document, with every command state), and forget the files no
     remaining node loads */

  private def release(id: Long, ok: Set[Document.Node.Name]): Unit =
    writer.synchronized {
      val st = table
      val changed =
        for (node <- st.nodes.valuesIterator.toList if node.required(id))
          yield node.copy(required =
            node.required - id ++ (if (ok(node.name)) Set(PIDE_Loader.PIN) else Set.empty))
      val purged = changed.filter(_.required.isEmpty)
      val nodes1 =
        st.nodes ++ changed.map(node => node.name -> node) -- purged.map(_.name)
      val files1 = nodes1.valuesIterator.flatMap(_.files).toSet
      update(st.doc_blobs,
        purged.flatMap(node => node_edits(node, Text.Edit.removes(0, node.text), false)))
      table = st.copy(nodes = nodes1, blobs = st.blobs.filter(p => files1(p._1)))
    }


  /* waiting: until every command of every node has terminated, with its forks.
     Consolidation (presentation hooks) is not waited for: the session requests it once per
     round, and a lost round leaves a node unconsolidated for good. */

  private def min_version(names: List[Document.Node.Name]): Long =
    names.flatMap(table.nodes.get(_).map(_.version)).minOption.getOrElse(0L)

  /* the latest assigned version, if it carries the edits of version min (ids decrease; the
     tip is often unassigned during a big load: every consolidation round adds a version) */
  private def latest_stable(st: Document.State, min: Long): Option[Document.Version] = {
    val version = st.recent_stable.version.get_finished
    if (version.id <= min) Some(version) else None
  }

  private def await(theories: List[Document.Node.Name])
    : (Document.State, Document.Version, Map[Document.Node.Name, Document_Status.Node_Status]) =
  {
    val min = min_version(theories)

    def wait(stamp0: Long): Unit =
      stamp.timed_access(_ => Some(Time.now() + Time.seconds(0.5)),
        s => if (s != stamp0) Some(((), s)) else None)

    // a terminated node stays terminated: nothing edits a node while it is in the table
    @tailrec def loop(done: Map[Document.Node.Name, Document_Status.Node_Status])
      : (Document.State, Document.Version, Map[Document.Node.Name, Document_Status.Node_Status]) =
    {
      val stamp0 = stamp.value
      val st = session.get_state()
      latest_stable(st, min) match {
        case Some(version) =>
          val now = Date.now()
          val done1 =
            done ++ theories.filterNot(done.isDefinedAt)
              .map(name => name -> Document_Status.Node_Status.make(now, st, version, name))
              .filter(_._2.terminated)
          if (theories.forall(done1.isDefinedAt)) (st, version, done1)
          else { wait(stamp0); loop(done1) }
        case None => wait(stamp0); loop(done)
      }
    }
    loop(Map.empty)
  }

  private def clean_status(s: Document_Status.Node_Status): Boolean =
    s.ok && s.finalized && s.terminated && !s.canceled

  /* nodes that loaded cleanly and whose imports did, too (a child of a failed node still runs
     in PIDE, on the parent's recovered end state) */
  private def clean(
    theories: List[Document.Node.Name],
    graph: Document.Node.Name.Graph[Unit],
    status: Document.Node.Name => Option[Document_Status.Node_Status]
  ): Set[Document.Node.Name] =
    theories.foldLeft(Set.empty[Document.Node.Name]) {   // imports come first
      case (ok, name) =>
        val parents_ok =
          graph.imm_preds(name).forall(p => session.resources.loaded_theory(p) || ok(p))
        if (parents_ok && status(name).exists(clean_status)) ok + name else ok
    }

  /* after an interrupt of await: what has loaded cleanly so far */
  private def clean_now(
    theories: List[Document.Node.Name],
    graph: Document.Node.Name.Graph[Unit]
  ): Set[Document.Node.Name] = {
    val st = session.get_state()
    latest_stable(st, min_version(theories)) match {
      case Some(version) =>
        val now = Date.now()
        val status =
          theories.map(name => name -> Document_Status.Node_Status.make(now, st, version, name))
        clean(theories, graph, status.toMap.get)
      case None => Set.empty
    }
  }

  private def errors(st: Document.State, name: Document.Node.Name): List[String] =
    for ((elem, pos) <- st.snapshot(node_name = name).messages if Protocol.is_error(elem))
    yield XML.content(Pretty.formatted(List(elem))) + Position.here(pos)

  private def loaded(st: Table, name: Document.Node.Name, version: Document.Version)
    : PIDE_Loader.Loaded =
    if (session.resources.loaded_theory(name)) {
      PIDE_Loader.Loaded(name.theory, "", Document_ID.none)
    }
    else {
      PIDE_Loader.Loaded(st.nodes(name).name.theory, name.node,
        version.nodes(name).commands.last.id)
    }


  /* main entry: import strings resolved as Isabelle resolves them under the qualifier and the
     master directory; results in request order.  submit and release run in one
     uninterruptible region, in which only await is interruptible (scala.ML:44-66). */

  def use_theories(
    qualifier: String,
    master_dir: String,
    theories: List[String]
  ): List[PIDE_Loader.Loaded] = {
    val resources = session.resources
    val import_names = theories.map(resources.import_name(qualifier, master_dir, _))
    val st0 = table

    if (import_names.forall(n => resources.loaded_theory(n) || st0.nodes.get(n).exists(_.pinned))) {
      val version = session.get_state().recent_stable.version.get_finished
      import_names.map(loaded(st0, _, version))
    }
    else Isabelle_Thread.uninterruptible {
      val id = counter()
      val (names, graph) = submit(id, import_names)
      val result = Exn.capture { Isabelle_Thread.interruptible { await(names) } }
      val ok =
        result match {
          case Exn.Res((_, _, status)) => clean(names, graph, status.get)
          case Exn.Exn(_) => clean_now(names, graph)
        }
      release(id, ok)
      val (st, version, _) = Exn.release(result)
      val bad = names.filterNot(ok)
      if (bad.nonEmpty) {
        val msgs = bad.flatMap(errors(st, _))
        error(cat_lines(
          ("Failed to load theories " + commas_quote(bad.map(_.theory))) ::
            (if (msgs.isEmpty) List("(no error message: theory not finished)") else msgs)))
      }
      val tab = table
      import_names.map(loaded(tab, _, version))
    }
  }


  /* by long theory name, without loading: pinned nodes only */

  def pinned_theory(theory: String): Option[PIDE_Loader.Loaded] = {
    val st = table
    st.theories.get(theory).filter(_.pinned).map(node =>
      loaded(st, node.name, session.get_state().recent_stable.version.get_finished))
  }

  def pinned_theories: List[String] =
    table.nodes.valuesIterator.filter(_.pinned).map(_.name.theory).toList.sorted


  /* the table against the latest document version; meaningful only when no load is in
     flight */

  def check: String = {
    val st = table
    val version = session.get_state().history.tip.version.join
    val resources = session.resources
    val doc_nodes =
      (for {
        (name, node) <- version.nodes.iterator
        if name.is_theory && !resources.loaded_theory(name) &&
          (node.perspective.required || node.commands.nonEmpty)
      } yield name -> node).toMap
    val problems =
      (for {
        node <- st.nodes.valuesIterator.toList
        problem <-
          doc_nodes.get(node.name) match {
            case None => Some("in table, not in document")
            case Some(doc) =>
              val src = doc.commands.iterator.map(_.source).mkString
              if (!doc.perspective.required) Some("not required in document")
              else if (src != node.text) Some("text differs")
              else None
          }
      } yield node.name.theory + ": " + problem) :::
      (for (name <- doc_nodes.keys.toList if !st.nodes.isDefinedAt(name))
        yield name.theory + ": in document, not in table")
    "table=" + st.nodes.size + " document=" + doc_nodes.size +
      (if (problems.isEmpty) " CONSISTENT" else " INCONSISTENT " + problems.mkString("; "))
  }
}
