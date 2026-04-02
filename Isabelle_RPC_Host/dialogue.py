"""Interactive dialogue via PIDE Active.dialog.

Monkey-patches ``Connection`` with a ``dialogue`` method that displays
a question with clickable options in Isabelle's output panel and blocks
until the user clicks one.

Usage::

    answer = await connection.dialogue("Continue?", ["Yes", "No"])
    # answer is "Yes" or "No"
"""

from .rpc import Connection


async def _dialogue(self: Connection, question: str, options: list[str]) -> str:  # type: ignore
    """Show a dialogue in Isabelle's output panel with clickable options.

    Blocks until the user clicks one of the options.

    Args:
        question: The question text displayed to the user.
        options: List of option strings rendered as clickable buttons.

    Returns:
        The option string the user clicked.
    """
    return await self.callback("dialogue", (question, options))


Connection.dialogue = _dialogue  # type: ignore
