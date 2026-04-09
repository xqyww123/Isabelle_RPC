"""Context entity enumeration — cached universal key lists per connection.

Each function enumerates entities from the Isabelle context where the RPC
was initiated, or from a specific theory if ``theory`` is given.

Args common to all entity functions:
    theory: Long theory name (e.g. ``'HOL.List'``) to target. If ``None``,
        uses the context where the RPC was initiated.
    the_theory_only: If ``True``, return only entities defined in the target
        theory itself; otherwise all entities from the target theory and its
        ancestors. The ``theories_not_include`` parameter is ignored when this
        is ``True``.
    theories_not_include: Long theory names to exclude. Ignored when
        ``the_theory_only`` is ``True``.
    theories_include: Theory names (short or fully qualified). Empty = no restriction.
        If non-empty, only return entities defined in these theories.

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

from .rpc import Connection
from .position import IsabellePosition
from .universal_key import EntityKind, universal_key

# (universal_key, full_name, definition_position_or_None)
type entity_entry = tuple[universal_key, str, IsabellePosition | None]

# # Debug reverse map: universal_key → readable name
# _debug_key_names: dict[bytes, str] = {}
#
# def debug_key_name(uk: universal_key) -> str | None:
#     """Look up readable name for a universal key (debug only)."""
#     return _debug_key_names.get(uk)


def _mk_pos(file: str, line: int, offset: int) -> IsabellePosition | None:
    """Convert ML position triple to IsabellePosition, or None if unknown."""
    if not file or not offset:
        return None
    return IsabellePosition(line, offset, file)


async def _call(connection: Connection, callback_name: str,
          theory: str | None, the_theory_only: bool,
          exclude: list[str],
          term_patterns: list[str] = [],
          type_patterns: list[str] = [],
          theories_include: list[str] = [],
          name_contains: list[str] = [],
          limit: int = -1) -> tuple[list[entity_entry], list[str]]:
    """Returns (entries, warnings). limit<0 means no limit.
    Each entry is (universal_key, IsabellePosition | None).
    """
    entries_raw, warnings = await connection.callback(callback_name,
                (theory, the_theory_only, exclude,
                 term_patterns, type_patterns, theories_include,
                 name_contains, limit))
    entries: list[entity_entry] = []
    for k_raw, name, (file, line, offset) in entries_raw:
        entries.append((bytes(k_raw), name, _mk_pos(file, line, offset)))
    return entries, list(warnings)


def _is_default(theory: str | None, the_theory_only: bool, exclude: list[str],
                term_patterns: list[str], type_patterns: list[str],
                theories_include: list[str],
                name_contains: list[str] = [],
                limit: int = -1) -> bool:
    return (theory is None and not the_theory_only and not exclude
            and not term_patterns and not type_patterns and not theories_include
            and not name_contains and limit < 0)


async def _cached_or_call(connection: Connection, attr: str, callback_name: str,
                    theory: str | None, the_theory_only: bool,
                    exclude: list[str],
                    term_patterns: list[str] = [],
                    type_patterns: list[str] = [],
                    theories_include: list[str] = [],
                    name_contains: list[str] = [],
                    limit: int = -1) -> tuple[list[entity_entry], list[str]]:
    """Returns (entries, warnings)."""
    if _is_default(theory, the_theory_only, exclude,
                   term_patterns, type_patterns, theories_include,
                   name_contains, limit):
        cached = getattr(connection, attr, None)
        if cached is None:
            entries, _ = await _call(connection, callback_name, None, False, [])
            setattr(connection, attr, entries)
            return entries, []
        return cached, []
    return await _call(connection, callback_name, theory, the_theory_only, exclude,
                 term_patterns, type_patterns, theories_include,
                 name_contains, limit)


async def constants(connection: Connection, theory: str | None = None,
              the_theory_only: bool = False,
              theories_not_include: list[str] = [],
              type_patterns: list[str] = [],
              theories_include: list[str] = [],
              name_contains: list[str] = [],
              limit: int = -1) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all constants.
    Only type_patterns apply (constants have no proposition; term patterns are ignored).
    """
    return await _cached_or_call(connection, "_ctx_constants", "Context.constants",
                           theory, the_theory_only, theories_not_include,
                           [], type_patterns, theories_include,
                           name_contains, limit)


async def theorems(connection: Connection, theory: str | None = None,
             the_theory_only: bool = False,
             theories_not_include: list[str] = [],
             term_patterns: list[str] = [],
             type_patterns: list[str] = [],
             theories_include: list[str] = [],
             name_contains: list[str] = [],
             limit: int = -1) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all theorems."""
    return await _cached_or_call(connection, "_ctx_theorems", "Context.theorems",
                           theory, the_theory_only, theories_not_include,
                           term_patterns, type_patterns, theories_include,
                           name_contains, limit)


async def types(connection: Connection, theory: str | None = None,
          the_theory_only: bool = False,
          theories_not_include: list[str] = [],
          theories_include: list[str] = [],
          name_contains: list[str] = [],
          limit: int = -1) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all types.
    Pattern parameters are not applicable to types.
    """
    return await _cached_or_call(connection, "_ctx_types", "Context.types",
                           theory, the_theory_only, theories_not_include,
                           [], [], theories_include,
                           name_contains, limit)


async def classes(connection: Connection, theory: str | None = None,
            the_theory_only: bool = False,
            theories_not_include: list[str] = [],
            theories_include: list[str] = [],
            name_contains: list[str] = [],
            limit: int = -1) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all type classes.
    Pattern parameters are not applicable to classes.
    """
    return await _cached_or_call(connection, "_ctx_classes", "Context.classes",
                           theory, the_theory_only, theories_not_include,
                           [], [], theories_include,
                           name_contains, limit)


async def locales(connection: Connection, theory: str | None = None,
            the_theory_only: bool = False,
            theories_not_include: list[str] = [],
            theories_include: list[str] = [],
            name_contains: list[str] = [],
            limit: int = -1) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all locales.
    Pattern parameters are not applicable to locales.
    """
    return await _cached_or_call(connection, "_ctx_locales", "Context.locales",
                           theory, the_theory_only, theories_not_include,
                           [], [], theories_include,
                           name_contains, limit)


async def introduction_rules(connection: Connection, theory: str | None = None,
                       the_theory_only: bool = False,
                       theories_not_include: list[str] = [],
                       term_patterns: list[str] = [],
                       type_patterns: list[str] = [],
                       theories_include: list[str] = [],
                       name_contains: list[str] = [],
                       limit: int = -1) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all introduction rules."""
    return await _cached_or_call(connection, "_ctx_intro_rules", "Context.introduction_rules",
                           theory, the_theory_only, theories_not_include,
                           term_patterns, type_patterns, theories_include,
                           name_contains, limit)


async def elimination_rules(connection: Connection, theory: str | None = None,
                      the_theory_only: bool = False,
                      theories_not_include: list[str] = [],
                      term_patterns: list[str] = [],
                      type_patterns: list[str] = [],
                      theories_include: list[str] = [],
                      name_contains: list[str] = [],
                      limit: int = -1) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all elimination rules."""
    return await _cached_or_call(connection, "_ctx_elim_rules", "Context.elimination_rules",
                           theory, the_theory_only, theories_not_include,
                           term_patterns, type_patterns, theories_include,
                           name_contains, limit)


_KIND_TO_FUNC = {
    EntityKind.CONSTANT: constants,
    EntityKind.THEOREM: theorems,
    EntityKind.TYPE: types,
    EntityKind.CLASS: classes,
    EntityKind.LOCALE: locales,
    EntityKind.INTRODUCTION_RULE: introduction_rules,
    EntityKind.ELIMINATION_RULE: elimination_rules,
}

async def entities_of(connection: Connection, kinds: list[EntityKind],
                theory: str | None = None,
                the_theory_only: bool = False,
                theories_not_include: list[str] = [],
                term_patterns: list[str] = [],
                type_patterns: list[str] = [],
                theories_include: list[str] = [],
                name_contains: list[str] = [],
                limit: int = -1) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all entities of the given kinds.

    Each entry is (universal_key, IsabellePosition | None).  The position is
    None for entities with unknown positions (e.g. from live PIDE with
    ID-based positions).

    Pattern parameters are forwarded only to entity kinds that support them:
    term_patterns → theorems, intro/elim rules only.
    type_patterns → theorems, intro/elim rules, constants.
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
        func = _KIND_TO_FUNC.get(kind)
        if func is None:
            continue
        _t_kind = _time.perf_counter()
        # Pass only the parameters each function accepts
        if kind in (EntityKind.TYPE, EntityKind.CLASS, EntityKind.LOCALE):
            entries, warnings = await func(connection, theory, the_theory_only,
                                  theories_not_include,
                                  theories_include=theories_include,
                                  name_contains=name_contains,
                                  limit=limit)
        elif kind == EntityKind.CONSTANT:
            entries, warnings = await func(connection, theory, the_theory_only,
                                  theories_not_include,
                                  type_patterns=type_patterns,
                                  theories_include=theories_include,
                                  name_contains=name_contains,
                                  limit=limit)
        else:
            # THEOREM, INTRODUCTION_RULE, ELIMINATION_RULE
            entries, warnings = await func(connection, theory, the_theory_only,
                                  theories_not_include,
                                  term_patterns=term_patterns,
                                  type_patterns=type_patterns,
                                  theories_include=theories_include,
                                  name_contains=name_contains,
                                  limit=limit)
        _perf_log.info("entities_of: kind=%s %.3fs (%d entries)",
                       kind.name, _time.perf_counter() - _t_kind, len(entries))
        result.extend(entries)
        all_warnings.extend(warnings)
    _perf_log.info("entities_of: total %.3fs (%d entries)", _time.perf_counter() - _t_total, len(result))
    return result, all_warnings


async def theory_long_name(connection: Connection) -> str:
    """Return the long theory name of the Isabelle context where the RPC was initiated.

    Args:
        connection: Active Isabelle RPC connection.
    """
    cached = getattr(connection, "_theory_long_name", None)
    if cached is None:
        cached = await connection.callback("Context.the_theory_long_name", None)
        connection._theory_long_name = cached  # type: ignore
    return cached
