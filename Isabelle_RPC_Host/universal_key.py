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

    @property
    def label(self) -> str:
        return _ENTITY_LABELS[self]

    @staticmethod
    def from_label(label: str) -> 'EntityKind':
        return _LABEL_TO_ENTITY[label]

EntityKind.ALL = [EntityKind.CONSTANT, EntityKind.THEOREM, EntityKind.TYPE,  # type: ignore
                  EntityKind.CLASS, EntityKind.LOCALE]

_ENTITY_LABELS = {
    EntityKind.CONSTANT: "constant",
    EntityKind.THEOREM: "lemma",
    EntityKind.TYPE: "type",
    EntityKind.CLASS: "typeclass",
    EntityKind.LOCALE: "locale",
}

_LABEL_TO_ENTITY = {v: k for k, v in _ENTITY_LABELS.items()}

class Entity(NamedTuple):
    theory: theory_hash
    kind: EntityKind
    name: str | theorem_digest | None
    

def is_WIP(key: universal_key) -> bool:
    """Check whether a universal key is from a WIP (non-persistent) theory.

    WIP theory hashes have LSB of byte 0 set to 1.
    """
    return key[0] & 1 == 1


def destruct_key(key: universal_key) -> Entity:
    """Destructure a universal key into its component parts.

    Theory keys are 16 bytes (just the theory hash).
    Entity keys: <theory_hash (16 bytes)> <tag (1 byte)> <entity (variable)>
    - Theorem keys: 32 bytes (15-byte digest payload)
    - Other keys: 17 + len(name) bytes (UTF-8 name payload)
    """
    if len(key) < 16:
        raise ValueError(f"Universal key too short: {len(key)} bytes")
    theory = key[:16]
    if len(key) == 16:
        return Entity(theory=theory, kind=EntityKind.THEORY, name=None)
    kind = EntityKind(key[16])
    payload = key[17:]
    if kind == EntityKind.THEOREM:
        name = bytes(payload)  # raw 15-byte digest
    else:
        name = payload.decode("utf-8")
    return Entity(theory=theory, kind=kind, name=name)


def universal_key_of(connection: Connection, kind: EntityKind, name: str) -> bytes:
    """Request the universal key for an Isabelle entity via callback."""
    return connection.callback("universal_key_of", (int(kind), name))
