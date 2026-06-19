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

from typing import Any

from .rpc import Connection
from .position import IsabellePosition
from .universal_key import (EntityKind, universal_key,
                            RULE_ONLY_KINDS, RULE_ONLY_TAG_BYTES, theorem_sibling_key)

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
          limit: int = -1,
          target_type: str = "",
          ctxt: Any = None) -> tuple[list[entity_entry], list[str]]:
    """Returns (entries, warnings). limit<0 means no limit.
    Each entry is (universal_key, IsabellePosition | None).
    target_type: only honoured by induction/case-split rule callbacks; "" = no filter.
    """
    entries_raw, warnings = await connection.callback(callback_name,
                (ctxt, (theory, the_theory_only, exclude,
                 term_patterns, type_patterns, theories_include,
                 name_contains, limit, target_type)))
    entries: list[entity_entry] = []
    for k_raw, name, (file, line, offset) in entries_raw:
        entries.append((bytes(k_raw), name, _mk_pos(file, line, offset)))
    return entries, list(warnings)


def _is_default(theory: str | None, the_theory_only: bool, exclude: list[str],
                term_patterns: list[str], type_patterns: list[str],
                theories_include: list[str],
                name_contains: list[str] = [],
                limit: int = -1,
                target_type: str = "",
                ctxt: Any = None) -> bool:
    return (theory is None and not the_theory_only and not exclude
            and not term_patterns and not type_patterns and not theories_include
            and not name_contains and limit < 0 and not target_type
            and ctxt is None)


async def _cached_or_call(connection: Connection, attr: str, callback_name: str,
                    theory: str | None, the_theory_only: bool,
                    exclude: list[str],
                    term_patterns: list[str] = [],
                    type_patterns: list[str] = [],
                    theories_include: list[str] = [],
                    name_contains: list[str] = [],
                    limit: int = -1,
                    target_type: str = "",
                    ctxt: Any = None) -> tuple[list[entity_entry], list[str]]:
    """Returns (entries, warnings)."""
    if _is_default(theory, the_theory_only, exclude,
                   term_patterns, type_patterns, theories_include,
                   name_contains, limit, target_type, ctxt=ctxt):
        cached = getattr(connection, attr, None)
        if cached is None:
            entries, _ = await _call(connection, callback_name, None, False, [])
            setattr(connection, attr, entries)
            return entries, []
        return cached, []
    return await _call(connection, callback_name, theory, the_theory_only, exclude,
                 term_patterns, type_patterns, theories_include,
                 name_contains, limit, target_type, ctxt=ctxt)


async def _call_thm(connection: Connection, callback_name: str,
          theory: str | None, the_theory_only: bool,
          exclude: list[str],
          term_patterns: list[str] = [],
          type_patterns: list[str] = [],
          theories_include: list[str] = [],
          name_contains: list[str] = [],
          limit: int = -1,
          target_type: str = "",
          ctxt: Any = None) -> tuple[list[entity_entry], dict[universal_key, bool], list[str]]:
    """Like _call but for the theorem-like callbacks (Context.theorems and the four
    rule kinds), whose entries carry a 4th element is_local (true = proof-context-
    local). Returns (entries, is_local, warnings), where is_local maps each uk -> bool.
    limit<0 means no limit."""
    entries_raw, warnings = await connection.callback(callback_name,
                (ctxt, (theory, the_theory_only, exclude,
                 term_patterns, type_patterns, theories_include,
                 name_contains, limit, target_type)))
    entries: list[entity_entry] = []
    is_local: dict[universal_key, bool] = {}
    for k_raw, name, (file, line, offset), loc in entries_raw:
        k = bytes(k_raw)
        entries.append((k, name, _mk_pos(file, line, offset)))
        is_local[k] = bool(loc)
    return entries, is_local, list(warnings)


async def _cached_or_call_thm(connection: Connection, attr: str, callback_name: str,
                    theory: str | None, the_theory_only: bool,
                    exclude: list[str],
                    term_patterns: list[str] = [],
                    type_patterns: list[str] = [],
                    theories_include: list[str] = [],
                    name_contains: list[str] = [],
                    limit: int = -1,
                    target_type: str = "",
                    ctxt: Any = None) -> tuple[list[entity_entry], dict[universal_key, bool], list[str]]:
    """Theorem-like variant of _cached_or_call. Caches the (entries, is_local) pair
    under connection.<attr> on the default query (no filters, no ctxt).  Dedicated
    helper so the shared _cached_or_call (which stores bare entry lists for the
    pattern-less kinds) stays untouched."""
    if _is_default(theory, the_theory_only, exclude,
                   term_patterns, type_patterns, theories_include,
                   name_contains, limit, target_type, ctxt=ctxt):
        cached = getattr(connection, attr, None)
        if cached is None:
            entries, is_local, _ = await _call_thm(connection, callback_name, None, False, [])
            setattr(connection, attr, (entries, is_local))
            return entries, is_local, []
        entries, is_local = cached
        return entries, is_local, []
    return await _call_thm(connection, callback_name, theory, the_theory_only, exclude,
                 term_patterns, type_patterns, theories_include,
                 name_contains, limit, target_type, ctxt=ctxt)


async def constants(connection: Connection, theory: str | None = None,
              the_theory_only: bool = False,
              theories_not_include: list[str] = [],
              type_patterns: list[str] = [],
              theories_include: list[str] = [],
              name_contains: list[str] = [],
              limit: int = -1,
              ctxt: Any = None) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all constants.
    Only type_patterns apply (constants have no proposition; term patterns are ignored).
    """
    return await _cached_or_call(connection, "_ctx_constants", "Context.constants",
                           theory, the_theory_only, theories_not_include,
                           [], type_patterns, theories_include,
                           name_contains, limit, ctxt=ctxt)


async def theorems(connection: Connection, theory: str | None = None,
             the_theory_only: bool = False,
             theories_not_include: list[str] = [],
             term_patterns: list[str] = [],
             type_patterns: list[str] = [],
             theories_include: list[str] = [],
             name_contains: list[str] = [],
             limit: int = -1,
             ctxt: Any = None) -> tuple[list[entity_entry], dict[universal_key, bool], list[str]]:
    """Return (entries, is_local, warnings) for all theorems. is_local maps each
    uk -> whether the theorem is proof-context-local (drives the no-embedding
    default score downstream)."""
    return await _cached_or_call_thm(connection, "_ctx_theorems", "Context.theorems",
                           theory, the_theory_only, theories_not_include,
                           term_patterns, type_patterns, theories_include,
                           name_contains, limit, ctxt=ctxt)


async def types(connection: Connection, theory: str | None = None,
          the_theory_only: bool = False,
          theories_not_include: list[str] = [],
          theories_include: list[str] = [],
          name_contains: list[str] = [],
          limit: int = -1,
          ctxt: Any = None) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all types.
    Pattern parameters are not applicable to types.
    """
    return await _cached_or_call(connection, "_ctx_types", "Context.types",
                           theory, the_theory_only, theories_not_include,
                           [], [], theories_include,
                           name_contains, limit, ctxt=ctxt)


async def classes(connection: Connection, theory: str | None = None,
            the_theory_only: bool = False,
            theories_not_include: list[str] = [],
            theories_include: list[str] = [],
            name_contains: list[str] = [],
            limit: int = -1,
            ctxt: Any = None) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all type classes.
    Pattern parameters are not applicable to classes.
    """
    return await _cached_or_call(connection, "_ctx_classes", "Context.classes",
                           theory, the_theory_only, theories_not_include,
                           [], [], theories_include,
                           name_contains, limit, ctxt=ctxt)


async def locales(connection: Connection, theory: str | None = None,
            the_theory_only: bool = False,
            theories_not_include: list[str] = [],
            theories_include: list[str] = [],
            name_contains: list[str] = [],
            limit: int = -1,
            ctxt: Any = None) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all locales.
    Pattern parameters are not applicable to locales.
    """
    return await _cached_or_call(connection, "_ctx_locales", "Context.locales",
                           theory, the_theory_only, theories_not_include,
                           [], [], theories_include,
                           name_contains, limit, ctxt=ctxt)


async def theorem_collection(connection: Connection, theory: str | None = None,
            the_theory_only: bool = False,
            theories_not_include: list[str] = [],
            term_patterns: list[str] = [],
            type_patterns: list[str] = [],
            theories_include: list[str] = [],
            name_contains: list[str] = [],
            limit: int = -1,
            ctxt: Any = None) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all theorem collections (dynamic facts:
    named_theorems and raw add_thms_dynamic collections like derivative_eq_intros).
    term_patterns/type_patterns keep a collection only when >= half of its non-infra
    members have a proposition matching the pattern (ML-side, see
    make_theorem_collection_callback); empty patterns are a no-op.
    """
    return await _cached_or_call(connection, "_ctx_theorem_collection", "Context.theorem_collection",
                           theory, the_theory_only, theories_not_include,
                           term_patterns, type_patterns, theories_include,
                           name_contains, limit, ctxt=ctxt)


async def methods(connection: Connection, theory: str | None = None,
            the_theory_only: bool = False,
            theories_not_include: list[str] = [],
            theories_include: list[str] = [],
            name_contains: list[str] = [],
            limit: int = -1,
            ctxt: Any = None) -> tuple[list[entity_entry], list[str]]:
    """Return (entries, warnings) for all proof methods.
    Pattern parameters are not applicable to methods.
    """
    return await _cached_or_call(connection, "_ctx_methods", "Context.methods",
                           theory, the_theory_only, theories_not_include,
                           [], [], theories_include,
                           name_contains, limit, ctxt=ctxt)


async def introduction_rules(connection: Connection, theory: str | None = None,
                       the_theory_only: bool = False,
                       theories_not_include: list[str] = [],
                       term_patterns: list[str] = [],
                       type_patterns: list[str] = [],
                       theories_include: list[str] = [],
                       name_contains: list[str] = [],
                       limit: int = -1,
                       ctxt: Any = None) -> tuple[list[entity_entry], dict[universal_key, bool], list[str]]:
    """Return (entries, is_local, warnings) for all introduction rules. is_local maps
    each uk -> whether the rule is proof-context-local (drives the no-embedding
    default score downstream)."""
    return await _cached_or_call_thm(connection, "_ctx_intro_rules", "Context.introduction_rules",
                           theory, the_theory_only, theories_not_include,
                           term_patterns, type_patterns, theories_include,
                           name_contains, limit, ctxt=ctxt)


async def elimination_rules(connection: Connection, theory: str | None = None,
                      the_theory_only: bool = False,
                      theories_not_include: list[str] = [],
                      term_patterns: list[str] = [],
                      type_patterns: list[str] = [],
                      theories_include: list[str] = [],
                      name_contains: list[str] = [],
                      limit: int = -1,
                      ctxt: Any = None) -> tuple[list[entity_entry], dict[universal_key, bool], list[str]]:
    """Return (entries, is_local, warnings) for all elimination rules. is_local maps
    each uk -> whether the rule is proof-context-local."""
    return await _cached_or_call_thm(connection, "_ctx_elim_rules", "Context.elimination_rules",
                           theory, the_theory_only, theories_not_include,
                           term_patterns, type_patterns, theories_include,
                           name_contains, limit, ctxt=ctxt)


async def induction_rules(connection: Connection, theory: str | None = None,
                    the_theory_only: bool = False,
                    theories_not_include: list[str] = [],
                    term_patterns: list[str] = [],
                    type_patterns: list[str] = [],
                    theories_include: list[str] = [],
                    name_contains: list[str] = [],
                    limit: int = -1,
                    target_type: str = "",
                    ctxt: Any = None) -> tuple[list[entity_entry], dict[universal_key, bool], list[str]]:
    """Return (entries, is_local, warnings) for all induction rules. is_local maps
    each uk -> whether the rule is proof-context-local.
    target_type: if non-empty, restrict to rules whose target type unifies with it
    (bidirectional Sign.typ_instance; wildcards allowed)."""
    return await _cached_or_call_thm(connection, "_ctx_induct_rules", "Context.induction_rules",
                           theory, the_theory_only, theories_not_include,
                           term_patterns, type_patterns, theories_include,
                           name_contains, limit, target_type, ctxt=ctxt)


async def case_split_rules(connection: Connection, theory: str | None = None,
                     the_theory_only: bool = False,
                     theories_not_include: list[str] = [],
                     term_patterns: list[str] = [],
                     type_patterns: list[str] = [],
                     theories_include: list[str] = [],
                     name_contains: list[str] = [],
                     limit: int = -1,
                     target_type: str = "",
                     ctxt: Any = None) -> tuple[list[entity_entry], dict[universal_key, bool], list[str]]:
    """Return (entries, is_local, warnings) for all case-split rules. is_local maps
    each uk -> whether the rule is proof-context-local.
    target_type: if non-empty, restrict to rules whose target type unifies with it
    (bidirectional Sign.typ_instance; wildcards allowed)."""
    return await _cached_or_call_thm(connection, "_ctx_case_split_rules", "Context.case_split_rules",
                           theory, the_theory_only, theories_not_include,
                           term_patterns, type_patterns, theories_include,
                           name_contains, limit, target_type, ctxt=ctxt)


_KIND_TO_FUNC = {
    EntityKind.CONSTANT: constants,
    EntityKind.THEOREM: theorems,
    EntityKind.TYPE: types,
    EntityKind.CLASS: classes,
    EntityKind.LOCALE: locales,
    EntityKind.THEOREM_COLLECTION: theorem_collection,
    EntityKind.METHOD: methods,
    EntityKind.INTRODUCTION_RULE: introduction_rules,
    EntityKind.ELIMINATION_RULE: elimination_rules,
    EntityKind.INDUCTION_RULE: induction_rules,
    EntityKind.CASE_SPLIT_RULE: case_split_rules,
}

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
                ctxt: Any = None) -> tuple[list[entity_entry], dict[universal_key, bool], list[str]]:
    """Return (entries, is_local, warnings) for all entities of the given kinds.

    Each entry is (universal_key, IsabellePosition | None).  The position is
    None for entities with unknown positions (e.g. from live PIDE with
    ID-based positions).  is_local maps a uk -> whether it is proof-context-local;
    theorems AND all four rule kinds populate it (a library/classical-net rule is
    false; a proof-local theorem or an empty-owning-theory rule fact is true).

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
    is_local: dict[universal_key, bool] = {}
    all_warnings: list[str] = []
    for kind in kinds:
        func = _KIND_TO_FUNC.get(kind)
        if func is None:
            continue
        _t_kind = _time.perf_counter()
        # Pass only the parameters each function accepts
        if kind in (EntityKind.TYPE, EntityKind.CLASS, EntityKind.LOCALE,
                    EntityKind.METHOD):
            entries, warnings = await func(connection, theory, the_theory_only,
                                  theories_not_include,
                                  theories_include=theories_include,
                                  name_contains=name_contains,
                                  limit=limit,
                                  ctxt=ctxt)
        elif kind == EntityKind.THEOREM_COLLECTION:
            # Collections take term/type patterns (half-member-match gate) but, unlike
            # the THEOREM/rule kinds, return a 2-tuple with no is_local map.
            entries, warnings = await func(connection, theory, the_theory_only,
                                  theories_not_include,
                                  term_patterns=term_patterns,
                                  type_patterns=type_patterns,
                                  theories_include=theories_include,
                                  name_contains=name_contains,
                                  limit=limit,
                                  ctxt=ctxt)
        elif kind == EntityKind.CONSTANT:
            entries, warnings = await func(connection, theory, the_theory_only,
                                  theories_not_include,
                                  type_patterns=type_patterns,
                                  theories_include=theories_include,
                                  name_contains=name_contains,
                                  limit=limit,
                                  ctxt=ctxt)
        elif kind in (EntityKind.INDUCTION_RULE, EntityKind.CASE_SPLIT_RULE):
            # induction/case-split rules return the per-uk is_local map and take target_type
            entries, kind_is_local, warnings = await func(connection, theory, the_theory_only,
                                  theories_not_include,
                                  term_patterns=term_patterns,
                                  type_patterns=type_patterns,
                                  theories_include=theories_include,
                                  name_contains=name_contains,
                                  limit=limit,
                                  target_type=target_type,
                                  ctxt=ctxt)
            is_local.update(kind_is_local)
        else:
            # THEOREM, INTRODUCTION_RULE, ELIMINATION_RULE: all return the per-uk
            # is_local map; none take target_type
            entries, kind_is_local, warnings = await func(connection, theory, the_theory_only,
                                  theories_not_include,
                                  term_patterns=term_patterns,
                                  type_patterns=type_patterns,
                                  theories_include=theories_include,
                                  name_contains=name_contains,
                                  limit=limit,
                                  ctxt=ctxt)
            is_local.update(kind_is_local)
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
        for uk, _name, _pos in result:
            if len(uk) == 32 and uk[16] in RULE_ONLY_TAG_BYTES:
                suppress.add(theorem_sibling_key(uk))
        if suppress:
            result = [e for e in result if e[0] not in suppress]
            for uk in suppress:
                is_local.pop(uk, None)

    _perf_log.info("entities_of: total %.3fs (%d entries)", _time.perf_counter() - _t_total, len(result))
    return result, is_local, all_warnings


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
