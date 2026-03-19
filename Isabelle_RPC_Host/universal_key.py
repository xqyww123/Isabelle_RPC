from enum import IntEnum
from typing import NamedTuple
from .rpc import Connection
from .theory_hash import theory_hash

type universal_key = bytes
type theorem_digest = bytes

class EntityKind(IntEnum):
    THEORY = 0
    CONSTANT = 1
    THEOREM = 2
    TYPE = 3
    CLASS = 4
    LOCALE = 5

class Entity(NamedTuple):
    theory: theory_hash
    kind: EntityKind
    name: str | theorem_digest | None
    

def destruct_key(key: universal_key) -> Entity:
    """Destructure a universal key into its component parts.

    Key format: <theory_hash (16 bytes)> <tag (1 byte)> <entity (variable)>
    - Theory keys: 17 bytes (empty payload, name=None)
    - Theorem keys: 32 bytes (15-byte digest payload)
    - Other keys: 17 + len(name) bytes (UTF-8 name payload)
    """
    if len(key) < 17:
        raise ValueError(f"Universal key too short: {len(key)} bytes")
    theory = key[:16]
    kind = EntityKind(key[16])
    payload = key[17:]
    if kind == EntityKind.THEORY:
        name = None
    elif kind == EntityKind.THEOREM:
        name = bytes(payload)  # raw 15-byte digest
    else:
        name = payload.decode("utf-8")
    return Entity(theory=theory, kind=kind, name=name)


def universal_key_of(connection: Connection, kind: EntityKind, name: str) -> bytes:
    """Request the universal key for an Isabelle entity via callback."""
    return connection.callback("universal_key_of", (int(kind), name))
