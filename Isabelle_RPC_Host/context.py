"""Context entity enumeration — cached universal key lists per connection."""

from .rpc import Connection
from .universal_key import EntityKind, universal_key


def _cached(connection: Connection, attr: str, callback_name: str) -> list[universal_key]:
    cached = getattr(connection, attr, None)
    if cached is None:
        cached = [bytes(k) for k in connection.callback(callback_name, None)]
        setattr(connection, attr, cached)
    return cached


def constants(connection: Connection) -> list[universal_key]:
    return _cached(connection, "_ctx_constants", "Context.constants")


def theorems(connection: Connection) -> list[universal_key]:
    return _cached(connection, "_ctx_theorems", "Context.theorems")


def types(connection: Connection) -> list[universal_key]:
    return _cached(connection, "_ctx_types", "Context.types")


def classes(connection: Connection) -> list[universal_key]:
    return _cached(connection, "_ctx_classes", "Context.classes")


def locales(connection: Connection) -> list[universal_key]:
    return _cached(connection, "_ctx_locales", "Context.locales")


_KIND_TO_FUNC = {
    EntityKind.CONSTANT: constants,
    EntityKind.THEOREM: theorems,
    EntityKind.TYPE: types,
    EntityKind.CLASS: classes,
    EntityKind.LOCALE: locales,
}

def entities_of(connection: Connection, kinds: list[EntityKind]) -> list[universal_key]:
    result: list[universal_key] = []
    for kind in kinds:
        func = _KIND_TO_FUNC.get(kind)
        if func is not None:
            result.extend(func(connection))
    return result
