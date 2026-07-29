/*  Title:      Isabelle_RPC/src/scala/frontend_identity.scala
    Author:     Qiyuan Xu

Frontend identity: two INDEPENDENT properties of the frontend attached to this
Isabelle/ML process (DIALOGUE_RESPONDER_DETECTION_PLAN.md).

  Q2 dialogue_capable: can an Active.dialog question ever be answered here?
     The only sender of Document.dialog_result in the whole Isabelle tree is
     jEdit's click handler (Tools/jEdit/src/active.scala), owned by the PIDE
     plugin instance -- so the answer is exact: jEdit attached, or not.

  Q1 interactive: is an interactive EDITOR driving this process?  Three-valued
     (Option[Boolean]): Some only on positive identification, None when the
     frontend is unknown -- the prober asserts nothing it has no evidence for.

Classification is by Session subclass package prefix ONLY, never by exact
class name: jEdit and build instantiate ANONYMOUS Session subclasses
(main_plugin.scala `new JEdit_Session(...) {`; build_job.scala
`new Build_Session(progress) {`), so exact names are unstable by construction.
*/

package isabelle.isabelle_rpc

import isabelle._


object Frontend_Identity extends Scala.Fun("isabelle_rpc.frontend_identity", thread = true)
  with Scala.Single_Fun
{
  val here = Scala_Project.here

  override def invoke(session: Session, args: List[Bytes]): List[Bytes] = {
    val cls = session.getClass.getName
    val dialogue_capable =
      cls.startsWith("isabelle.jedit.") ||       // anonymous subclass stays in-package
      isabelle.jedit.PIDE._plugin != null         // the answering mechanism's own host
    val interactive: Option[Boolean] =
      if (dialogue_capable || cls.startsWith("isabelle.vscode.")) Some(true)
      else if (cls.startsWith("isabelle.Build_Job") ||   // build (incl. Isa-REPL)
               cls.startsWith("isabelle.Headless"))       // server / dump / update
        Some(false)
      else None                                   // unknown frontend: no verdict
    val body =
      XML.Encode.pair(XML.Encode.bool,
        XML.Encode.pair(XML.Encode.option(XML.Encode.bool), XML.Encode.string))(
        (dialogue_capable, (interactive, cls)))
    List(Bytes(YXML.string_of_body(body)))
  }
}

class RPC_Functions extends Scala.Functions(Frontend_Identity)
