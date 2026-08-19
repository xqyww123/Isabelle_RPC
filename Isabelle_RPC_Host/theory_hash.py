import asyncio
import os
import time
from typing import Any

import lmdb
import msgpack
import xxhash
from Isabelle_RPC_Host import Connection, isabelle_remote_procedure
from Isabelle_RPC_Host.paths import semantic_DB_dir

type theory_hash = bytes

def is_persistent(h: bytes) -> bool:
    """Check whether a theory hash is from a saved heap image (LSB of byte 0 = 0)."""
    return h[0] & 1 == 0


def theory_xxhash128(
    long_name: str, file_path: str, parent_hashes: list[bytes]
) -> theory_hash:
    """Compute xxhash128 of a theory's long name and file, combined with parent hashes.

    The long name is in the digest so that two theories sharing a base name --
    and, when one .thy is loaded under two long names, sharing the file itself --
    get distinct identities.  The NUL separator makes the name/file boundary
    unambiguous: a theory long name cannot contain one.

    Parents contribute their own hashes under this same scheme, so the name
    propagates down the ancestor DAG.

    Clearing byte 0's LSB (the "from a heap image" marker) happens HERE and
    nowhere else: the store-migration script imports this function, and a
    one-byte disagreement between it and the live code would silently mis-key
    the whole store.

    Returns:
        16-byte xxhash128 digest
    """
    h = xxhash.xxh128()
    h.update(long_name.encode("utf-8"))
    h.update(b"\0")
    with open(file_path, "rb") as f:
        h.update(f.read())
    for ph in parent_hashes:
        h.update(ph)
    d = bytearray(h.digest())
    d[0] &= 0xFE
    return bytes(d)


async def theory_name_of(connection: Connection, h: theory_hash) -> str | None:
    """Look up the long name of a theory given its hash.

    Returns None if the hash has not been seen in the current Isabelle runtime.
    """
    return await connection.callback("Theory_Hash.theory_name_of", h)


import atexit
import threading

_theory_hash_env: lmdb.Environment | None = None
_theory_hash_lock = threading.Lock()

THEORY_HASH_MAP_SIZE = 1 << 30

def open_theory_hash_store() -> lmdb.Environment:
    global _theory_hash_env
    if _theory_hash_env is None:
        with _theory_hash_lock:
            if _theory_hash_env is None:
                cache_dir = semantic_DB_dir()
                os.makedirs(cache_dir, exist_ok=True)
                _theory_hash_env = lmdb.open(os.path.join(cache_dir, "theory_hash.lmdb"),
                                             map_size=THEORY_HASH_MAP_SIZE)
                try:
                    # Attached RPC hosts die by os._exit/SIGKILL as a matter of design,
                    # leaving stale reader-table slots (default 126) behind; each new
                    # opener reaps its predecessors' corpses or the table eventually
                    # fills up (MDB_READERS_FULL).  See RPC_EPHEMERAL_HOST_PLAN.md, H0.
                    _theory_hash_env.reader_check()
                except lmdb.Error:
                    pass
                atexit.register(_close_theory_hash_store)
    return _theory_hash_env

def _close_theory_hash_store() -> None:
    global _theory_hash_env
    with _theory_hash_lock:
        if _theory_hash_env is not None:
            _theory_hash_env.close()
            _theory_hash_env = None


@isabelle_remote_procedure("Theory_Hash.store")
async def _store_theory_hashes(arg: Any, connection: Connection) -> None:
    env = open_theory_hash_store()
    now = int(time.time())
    with env.begin(write=True) as txn:
        for hash_bytes, name in arg:
            if isinstance(name, bytes):
                name = name.decode("utf-8")
            txn.put(bytes(hash_bytes), msgpack.packb([name, now]))  # type: ignore


@isabelle_remote_procedure("xxhash128_theory")
async def _theory_xxhash128(arg: Any, connection: Connection) -> theory_hash:
    (long_name, file_path, parent_hashes) = arg
    if isinstance(long_name, bytes):
        long_name = long_name.decode("utf-8")
    if isinstance(file_path, bytes):
        file_path = file_path.decode("utf-8")
    return theory_xxhash128(long_name, file_path, parent_hashes)
