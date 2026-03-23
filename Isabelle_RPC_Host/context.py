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
"""

from .rpc import Connection
from .universal_key import EntityKind, universal_key


def _call(connection: Connection, callback_name: str,
          theory: str | None, the_theory_only: bool,
          exclude: list[str]) -> list[universal_key]:
    return [bytes(k) for k in
            connection.callback(callback_name, (theory, the_theory_only, exclude))]


def _is_default(theory: str | None, the_theory_only: bool, exclude: list[str]) -> bool:
    return theory is None and not the_theory_only and not exclude


def _cached_or_call(connection: Connection, attr: str, callback_name: str,
                    theory: str | None, the_theory_only: bool,
                    exclude: list[str]) -> list[universal_key]:
    if _is_default(theory, the_theory_only, exclude):
        cached = getattr(connection, attr, None)
        if cached is None:
            cached = _call(connection, callback_name, None, False, [])
            setattr(connection, attr, cached)
        return cached
    return _call(connection, callback_name, theory, the_theory_only, exclude)


def constants(connection: Connection, theory: str | None = None,
              the_theory_only: bool = False,
              theories_not_include: list[str] = []) -> list[universal_key]:
    """Return universal keys of all constants.

    Args:
        connection: Active Isabelle RPC connection.
        theory: Long theory name to target, or ``None`` for the current context.
        the_theory_only: If ``True``, only entities from the target theory;
            otherwise all entities from the target theory and its ancestors.
        theories_not_include: Long theory names to exclude.
    """
    return _cached_or_call(connection, "_ctx_constants", "Context.constants",
                           theory, the_theory_only, theories_not_include)


def theorems(connection: Connection, theory: str | None = None,
             the_theory_only: bool = False,
             theories_not_include: list[str] = []) -> list[universal_key]:
    """Return universal keys of all theorems.

    Args:
        connection: Active Isabelle RPC connection.
        theory: Long theory name to target, or ``None`` for the current context.
        the_theory_only: If ``True``, only entities from the target theory;
            otherwise all entities from the target theory and its ancestors.
        theories_not_include: Long theory names to exclude.
    """
    return _cached_or_call(connection, "_ctx_theorems", "Context.theorems",
                           theory, the_theory_only, theories_not_include)


def types(connection: Connection, theory: str | None = None,
          the_theory_only: bool = False,
          theories_not_include: list[str] = []) -> list[universal_key]:
    """Return universal keys of all types.

    Args:
        connection: Active Isabelle RPC connection.
        theory: Long theory name to target, or ``None`` for the current context.
        the_theory_only: If ``True``, only entities from the target theory;
            otherwise all entities from the target theory and its ancestors.
        theories_not_include: Long theory names to exclude.
    """
    return _cached_or_call(connection, "_ctx_types", "Context.types",
                           theory, the_theory_only, theories_not_include)


def classes(connection: Connection, theory: str | None = None,
            the_theory_only: bool = False,
            theories_not_include: list[str] = []) -> list[universal_key]:
    """Return universal keys of all type classes.

    Args:
        connection: Active Isabelle RPC connection.
        theory: Long theory name to target, or ``None`` for the current context.
        the_theory_only: If ``True``, only entities from the target theory;
            otherwise all entities from the target theory and its ancestors.
        theories_not_include: Long theory names to exclude.
    """
    return _cached_or_call(connection, "_ctx_classes", "Context.classes",
                           theory, the_theory_only, theories_not_include)


def locales(connection: Connection, theory: str | None = None,
            the_theory_only: bool = False,
            theories_not_include: list[str] = []) -> list[universal_key]:
    """Return universal keys of all locales.

    Args:
        connection: Active Isabelle RPC connection.
        theory: Long theory name to target, or ``None`` for the current context.
        the_theory_only: If ``True``, only entities from the target theory;
            otherwise all entities from the target theory and its ancestors.
        theories_not_include: Long theory names to exclude.
    """
    return _cached_or_call(connection, "_ctx_locales", "Context.locales",
                           theory, the_theory_only, theories_not_include)


_KIND_TO_FUNC = {
    EntityKind.CONSTANT: constants,
    EntityKind.THEOREM: theorems,
    EntityKind.TYPE: types,
    EntityKind.CLASS: classes,
    EntityKind.LOCALE: locales,
}

def entities_of(connection: Connection, kinds: list[EntityKind],
                theory: str | None = None,
                the_theory_only: bool = False,
                theories_not_include: list[str] = []) -> list[universal_key]:
    """Return universal keys of all entities of the given kinds.

    Args:
        connection: Active Isabelle RPC connection.
        kinds: Entity kinds to include.
        theory: Long theory name to target, or ``None`` for the current context.
        the_theory_only: If ``True``, only entities from the target theory;
            otherwise all entities from the target theory and its ancestors.
        theories_not_include: Long theory names to exclude.
    """
    result: list[universal_key] = []
    for kind in kinds:
        func = _KIND_TO_FUNC.get(kind)
        if func is not None:
            result.extend(func(connection, theory, the_theory_only, theories_not_include))
    return result


def theory_long_name(connection: Connection) -> str:
    """Return the long theory name of the Isabelle context where the RPC was initiated.

    Args:
        connection: Active Isabelle RPC connection.
    """
    cached = getattr(connection, "_theory_long_name", None)
    if cached is None:
        cached = connection.callback("Context.theory_long_name", None)
        connection._theory_long_name = cached  # type: ignore
    return cached
