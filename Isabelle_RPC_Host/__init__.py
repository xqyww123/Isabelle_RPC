from .rpc import (
    IsabelleError, Connection,
    RemoteProcedure, Remote_Procedures, isabelle_remote_procedure,
    Server,
    isabelle_home, mk_logger_, launch_server_, fork_and_launch__,
)
from .unicode import (get_SYMBOLS, get_REVERSE_SYMBOLS, get_SYMBOLS_AND_REVERSED,
                      pretty_unicode, unicode_of_ascii, ascii_of_unicode,
                      SUBSUP_TRANS_TABLE, SUBSUP_RESTORE_TABLE)
from .position import IsabellePosition, Position
from .universal_key import EntityKind, Entity, destruct_key, universal_key_of, universal_key
from . import theory_hash
from . import context
from . import dialogue

# @isabelle_remote_procedure("test_dialogue")
# def test_dialogue(arg, connection: Connection):
#     import Isabelle_RPC_Host.dialogue  # noqa: F811
#     answer = connection.dialogue("How are you?", ["Good", "Bad"])
#     if answer == "Good":
#         connection.writeln("Glad to hear that!")
#     else:
#         connection.writeln("Hope you feel better soon!")
#     return answer