"""Isabelle logging via RPC callback — tracing, warning, writeln.

Monkey-patches ``Connection`` with logging methods that call back into
Isabelle/ML to print messages in Isabelle's output panel.

These methods are added to ``Connection`` at import time:
    - ``connection.tracing(msg)`` — debug-level tracing output
    - ``connection.warning(msg)`` — warning message
    - ``connection.writeln(msg)`` — normal output
"""

from enum import IntEnum
from .rpc import Connection


class LogType(IntEnum):
    """Log level tags matching ``Isabelle_Log.log_type`` in tracing.ML."""
    TRACING = 0
    WARNING = 1
    WRITELN = 2


def _tracing(self: Connection, msg: str) -> None:  # type: ignore
    """Print a tracing message in Isabelle's output.

    Args:
        msg: The message to print.
    """
    self.callback("log", (int(LogType.TRACING), msg))


def _warning(self: Connection, msg: str) -> None:  # type: ignore
    """Print a warning message in Isabelle's output.

    Args:
        msg: The message to print.
    """
    self.callback("log", (int(LogType.WARNING), msg))


def _writeln(self: Connection, msg: str) -> None:  # type: ignore
    """Print a normal message in Isabelle's output.

    Args:
        msg: The message to print.
    """
    self.callback("log", (int(LogType.WRITELN), msg))


Connection.tracing = _tracing  # type: ignore
Connection.warning = _warning  # type: ignore
Connection.writeln = _writeln  # type: ignore
