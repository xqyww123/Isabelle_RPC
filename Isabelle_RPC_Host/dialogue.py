"""Interactive dialogue via PIDE Active.dialog.

Monkey-patches ``Connection`` with a ``dialogue`` method that displays
a question with clickable options in Isabelle's output panel and blocks
until the user clicks one.

The only frontend that can ever answer such a dialog is Isabelle/jEdit;
the ML side probes the attached frontend first and returns the
no-responder sentinel (``None`` here) when nobody could answer -- under
Isa-REPL, ``isabelle build``, VSCode, headless PIDE or a bare ML process
the question is never even displayed, instead of hanging forever.

Usage::

    answer = await connection.dialogue("Continue?", ["Yes", "No"])
    # answer is "Yes" or "No" -- or None when no frontend could answer;
    # the caller decides how to degrade (typically: warn and do nothing).
    # None is distinct from the user actively declining!
"""

from .rpc import Connection


async def _dialogue(self: Connection, question: str,
                    options: list[str]) -> 'str | None':  # type: ignore
    """Show a dialogue in Isabelle's output panel with clickable options.

    Blocks until the user clicks one of the options -- if a responder
    exists.

    Args:
        question: The question text displayed to the user.
        options: List of option strings rendered as clickable buttons.

    Returns:
        The option string the user clicked, or ``None`` when no attached
        frontend can answer dialogs (the question was not shown at all).
    """
    return await self.callback("dialogue", (question, options))


Connection.dialogue = _dialogue  # type: ignore
