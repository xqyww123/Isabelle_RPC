"""Context entity enumeration over RPC.

``entities_of`` enumerates entities from the Isabelle context where the RPC was
initiated, or from a specific theory if ``theory`` is given.

Every call enumerates the LIVE context.  What travels is only new: each kind's
callback owns a catalog on the ML side (Entity_Catalog), the append-only
numbering of the entries its replies have returned in this request.  Python
keeps a mirror of it in ``connection.request_state`` and sends its length
(``synced_length``); a reply carries the indices of its results, as a bitmap or
an index list, and the catalog entries the mirror lacks.  Mirror and catalog both
end with the request.  (A per-connection cache keyed on "no filters, no ctxt"
was retired 2026-08-26: it had no invalidation; see
Semantic_Embedding/INFRA_FILTER_REWORK_PLAN.md §18.)

Args of ``entities_of``:
    theory: Long theory name (e.g. ``'HOL.List'``) to target. If ``None``,
        uses the context where the RPC was initiated.
    the_theory_only: If ``True``, return only entities defined in the target
        theory itself; otherwise all entities from the target theory and its
        ancestors. The ``theories_not_include`` parameter is ignored when this
        is ``True``.
    theories_not_include: Long theory names to exclude. Ignored when
        ``the_theory_only`` is ``True``.
    theories_include: Case-insensitive substrings matched against each entity's
        fully-qualified theory name; an entity is kept if its theory name
        contains any of them (short fragments and full names both work). Empty =
        no restriction. A substring matching no loaded theory yields a warning.

Additional filtering (only on applicable entity kinds):
    term_patterns: Isabelle term pattern strings for structural filtering.
        Empty list = no restriction. All patterns must match (conjunction).
        Only applicable to thm-like entities (theorems, intro/elim rules).
    type_patterns: Isabelle type pattern strings for type filtering.
        Empty list = no restriction. All patterns must match (conjunction).
        Applicable to thm-like entities and constants.
    name_contains: Case-insensitive substring filters on the fully qualified name.
        Empty list = no restriction. All substrings must match (conjunction).
        Applicable to all entity kinds.
"""

import asyncio
from typing import Any

from .rpc import Connection
from .unicode import ascii_of_unicode
from .universal_key import (EntityKind, universal_key,
                            RULE_ONLY_KINDS, RULE_ONLY_TAG_BYTES, theorem_sibling_key)

# (universal_key, full_name, is_local); is_local = proof-context-local, which
# drives the no-embedding default score downstream (always False outside the
# theorem and rule kinds)
type entity_entry = tuple[universal_key, str, bool]

# kind -> (callback, whether it takes term_patterns, type_patterns, target_type)
_CALLBACKS: dict[EntityKind, tuple[str, bool, bool, bool]] = {
    EntityKind.CONSTANT: ("Context.constants", False, True, False),
    EntityKind.THEOREM: ("Context.theorems", True, True, False),
    EntityKind.TYPE: ("Context.types", False, False, False),
    EntityKind.CLASS: ("Context.classes", False, False, False),
    EntityKind.LOCALE: ("Context.locales", False, False, False),
    EntityKind.THEOREM_COLLECTION: ("Context.theorem_collection", True, True, False),
    EntityKind.METHOD: ("Context.methods", False, False, False),
    EntityKind.INTRODUCTION_RULE: ("Context.introduction_rules", True, True, False),
    EntityKind.ELIMINATION_RULE: ("Context.elimination_rules", True, True, False),
    EntityKind.INDUCTION_RULE: ("Context.induction_rules", True, True, True),
    EntityKind.CASE_SPLIT_RULE: ("Context.case_split_rules", True, True, True),
}

_MIRRORS = "Isabelle_RPC_Host.context.mirrors"   # key in connection.request_state

# per byte value: the positions of its set bits, MSB first
_SET_BITS: tuple[tuple[int, ...], ...] = tuple(
    tuple(j for j in range(8) if b & (0x80 >> j)) for b in range(256))


class _Mirror:
    """The entries [0, len(entries)) of one kind's catalog; ``lock`` serializes the
    calls of that kind, so a reply is applied before the next one is asked for."""
    __slots__ = ("entries", "lock")

    def __init__(self) -> None:
        self.entries: list[entity_entry] = []
        self.lock = asyncio.Lock()


def _decode_indices(index_set: bytes | list[int]) -> list[int]:
    """A bitmap (bytes, MSB-first in a byte) or an index list, as indices."""
    if not isinstance(index_set, (bytes, bytearray)):
        return list(index_set)
    indices: list[int] = []
    for n, byte in enumerate(index_set):
        if byte:
            indices.extend(8 * n + j for j in _SET_BITS[byte])
    return indices


async def _enumerate(connection: Connection, kind: EntityKind, theory: str | None,
                     the_theory_only: bool, exclude: list[str], term_patterns: list[str],
                     type_patterns: list[str], theories_include: list[str],
                     name_contains: list[str], limit: int, target_type: str,
                     ctxt: Any) -> tuple[list[entity_entry], list[str]]:
    """One kind's entities and warnings, through its mirror.  The only reader and
    writer of the mirrors.  Each ``name_contains`` pattern is normalized via
    ``ascii_of_unicode`` (the ML filter compares ASCII-notation names)."""
    callback, terms, types, target = _CALLBACKS[kind]
    # created with no await in between, so concurrent first calls share one
    mirrors: dict[EntityKind, _Mirror] = connection.request_state.setdefault(_MIRRORS, {})
    mirror = mirrors.get(kind)
    if mirror is None:
        mirror = mirrors[kind] = _Mirror()
    async with mirror.lock:
        synced_length = len(mirror.entries)
        index_set, delivered, warnings = await connection.callback(callback,
            (ctxt, (theory, the_theory_only, exclude,
                    term_patterns if terms else [], type_patterns if types else [],
                    theories_include, [ascii_of_unicode(p) for p in name_contains],
                    limit, target_type if target else "", synced_length)))
        if any(index != expected
               for expected, (_, _, _, index) in enumerate(delivered, synced_length)):
            raise RuntimeError(f"{callback}: the delivered entries do not continue the "
                               f"mirror at {synced_length} without a gap")
        mirror.entries.extend((bytes(uk), name, bool(is_local))
                              for uk, name, is_local, _ in delivered)
        if (isinstance(index_set, (bytes, bytearray))
                and len(index_set) != (len(mirror.entries) + 7) // 8):
            raise RuntimeError(f"{callback}: a bitmap of {len(index_set)} bytes over a "
                               f"catalog of {len(mirror.entries)} entries")
        entries = mirror.entries
        return [entries[i] for i in _decode_indices(index_set)], list(warnings)


async def entities_of(connection: Connection, kinds: list[EntityKind],
                theory: str | None = None,
                the_theory_only: bool = False,
                theories_not_include: list[str] = [],
                term_patterns: list[str] = [],
                type_patterns: list[str] = [],
                theories_include: list[str] = [],
                name_contains: list[str] = [],
                limit: int = -1,
                target_type: str = "",
                ctxt: Any = None) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all entities of the given kinds.

    Each entry is (universal_key, full name, is_local).  is_local is whether the
    entity is proof-context-local; theorems AND all four rule kinds set it (a
    library/classical-net rule is False; a proof-local theorem or an
    empty-owning-theory rule fact is True); every other kind gives False.
    The entries form a set: their order carries no meaning.

    Pattern parameters are forwarded only to entity kinds that support them:
    term_patterns → theorems, all four rule kinds (intro/elim/induction/case-split),
      theorem collections.
    type_patterns → theorems, constants, all four rule kinds, theorem collections.
    target_type → induction/case-split rules only (silently ignored otherwise).
    theories_include, name_contains, limit → all kinds.
    Warnings include notices about undeclared free variables in term patterns.
    limit<0 (default -1) means no limit; limit>0 caps each per-kind RPC call.
    """
    import logging as _logging
    import time as _time
    _perf_log = _logging.getLogger("perf.entities_of")
    _t_total = _time.perf_counter()
    result: list[entity_entry] = []
    all_warnings: list[str] = []
    for kind in kinds:
        if kind not in _CALLBACKS:
            continue
        _t_kind = _time.perf_counter()
        entries, warnings = await _enumerate(connection, kind, theory, the_theory_only,
                                             theories_not_include, term_patterns,
                                             type_patterns, theories_include,
                                             name_contains, limit, target_type, ctxt)
        _perf_log.info("entities_of: kind=%s %.3fs (%d entries)",
                       kind.name, _time.perf_counter() - _t_kind, len(entries))
        result.extend(entries)
        all_warnings.extend(warnings)

    # Query-aware cross-kind dedup (decision 8): a dynamic-collection rule member is
    # stored under BOTH a Theorem key (tag 0x02) and a rule key (0x12/0x22/0x32/0x42),
    # which differ only in the tag byte (key[16]).  A rule member is "really" a rule;
    # it surfaces as a theorem only when its rule kind was NOT requested.  So when this
    # query targets BOTH theorems and at least one rule kind, suppress the Theorem face
    # of every rule entry actually present (its rule kind was queried and it passed) by
    # removing the sibling Theorem key (same bytes, tag -> 0x02).  No rule entry present
    # => nothing suppressed; theorems-only or rules-only queries are untouched.
    if EntityKind.THEOREM in kinds and any(k in kinds for k in RULE_ONLY_KINDS):
        suppress: set[universal_key] = set()
        for uk, _name, _is_local in result:
            if len(uk) == 32 and uk[16] in RULE_ONLY_TAG_BYTES:
                suppress.add(theorem_sibling_key(uk))
        if suppress:
            result = [e for e in result if e[0] not in suppress]

    _perf_log.info("entities_of: total %.3fs (%d entries)", _time.perf_counter() - _t_total, len(result))
    return result, all_warnings


async def theory_long_name(connection: Connection, ctxt: Any = None) -> str:
    """Return the long theory name of the Isabelle context where the RPC was initiated.

    Args:
        connection: Active Isabelle RPC connection.
        ctxt: Optional context (e.g. state_id) to pass to Isabelle.
    """
    cached = getattr(connection, "_theory_long_name", None)
    if cached is None:
        cached = await connection.callback("Context.the_theory_long_name", ctxt)
        connection._theory_long_name = cached  # type: ignore
    return cached
