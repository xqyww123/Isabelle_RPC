from enum import IntEnum
from typing import Any, NamedTuple
from .rpc import Connection, IsabelleError
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
    INTRODUCTION_RULE = 0x12
    ELIMINATION_RULE = 0x22
    INDUCTION_RULE = 0x32
    CASE_SPLIT_RULE = 0x42

    @property
    def label(self) -> str:
        return _ENTITY_LABELS[self]

    @staticmethod
    def from_label(label: str) -> 'EntityKind':
        return _LABEL_TO_ENTITY[label]

EntityKind.ALL = [EntityKind.CONSTANT, EntityKind.THEOREM, EntityKind.TYPE,  # type: ignore
                  EntityKind.CLASS, EntityKind.LOCALE,
                  EntityKind.INTRODUCTION_RULE, EntityKind.ELIMINATION_RULE,
                  EntityKind.INDUCTION_RULE, EntityKind.CASE_SPLIT_RULE]

_ENTITY_LABELS = {
    EntityKind.CONSTANT: "constant",
    EntityKind.THEOREM: "lemma",
    EntityKind.TYPE: "type",
    EntityKind.CLASS: "typeclass",
    EntityKind.LOCALE: "locale",
    EntityKind.INTRODUCTION_RULE: "introduction rule",
    EntityKind.ELIMINATION_RULE: "elimination rule",
    EntityKind.INDUCTION_RULE: "induction rule",
    EntityKind.CASE_SPLIT_RULE: "case-split rule",
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
    if kind in (EntityKind.THEOREM, EntityKind.INTRODUCTION_RULE, EntityKind.ELIMINATION_RULE,
                EntityKind.INDUCTION_RULE, EntityKind.CASE_SPLIT_RULE):
        name = bytes(payload)  # raw 15-byte digest
    else:
        name = payload.decode("utf-8")
    return Entity(theory=theory, kind=kind, name=name)


class UndefinedEntity(Exception):
    """Raised when an Isabelle entity cannot be found."""
    def __init__(self, kind: EntityKind, name: str, message: str):
        self.kind = kind
        self.name = name
        super().__init__(f"Undefined {kind.label}: {name!r}")


async def universal_key_and_name_of(
    connection: Connection, kind: EntityKind, name: str, ctxt: Any = None
) -> tuple[universal_key, str]:
    """Request the universal key and resolved full name for an Isabelle entity.

    The ML callback interns the given xname and returns both the universal key
    and the fully-qualified name. Callers that need the canonical full name
    (e.g. to avoid using a user-provided short name as an entity identifier)
    should prefer this over ``universal_key_of``.
    """
    try:
        uk, full_name = await connection.callback("universal_key_of", (ctxt, (int(kind), name)))
        return (bytes(uk), full_name)
    except IsabelleError as e:
        msg = e.errors[0] if e.errors else str(e)
        if msg.startswith("Undefined "):
            raise UndefinedEntity(kind, name, msg)
        raise


async def universal_key_of(connection: Connection, kind: EntityKind, name: str, ctxt: Any = None) -> universal_key:
    """Request the universal key for an Isabelle entity via callback."""
    uk, _ = await universal_key_and_name_of(connection, kind, name, ctxt=ctxt)
    return uk
