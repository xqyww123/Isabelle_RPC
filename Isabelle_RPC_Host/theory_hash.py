import asyncio
import os
import time
from typing import Any

import lmdb
import msgpack
import platformdirs
import xxhash
from Isabelle_RPC_Host import Connection, isabelle_remote_procedure

type theory_hash = bytes

def is_persistent(h: bytes) -> bool:
    """Check whether a theory hash is from a saved heap image (LSB of byte 0 = 0)."""
    return h[0] & 1 == 0


def theory_xxhash128(file_path: str, parent_hashes: list[bytes]) -> theory_hash:
    """Compute xxhash128 of a theory file combined with parent theory hashes.

    Returns:
        16-byte xxhash128 digest
    """
    h = xxhash.xxh128()
    with open(file_path, "rb") as f:
        h.update(f.read())
    for ph in parent_hashes:
        h.update(ph)
    return h.digest()


async def theory_name_of(connection: Connection, h: theory_hash) -> str | None:
    """Look up the long name of a theory given its hash.

    Returns None if the hash has not been seen in the current Isabelle runtime.
    """
    return await connection.callback("Theory_Hash.theory_name_of", h)


import atexit
import threading

_theory_hash_env: lmdb.Environment | None = None
_theory_hash_lock = threading.Lock()

def open_theory_hash_store() -> lmdb.Environment:
    global _theory_hash_env
    if _theory_hash_env is None:
        with _theory_hash_lock:
            if _theory_hash_env is None:
                cache_dir = platformdirs.user_cache_dir("Isabelle_Theory_Hash", "Qiyuan")
                os.makedirs(cache_dir, exist_ok=True)
                _theory_hash_env = lmdb.open(os.path.join(cache_dir, "theory_hash.lmdb"), map_size=1 << 30)
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
    (file_path, parent_hashes) = arg
    if isinstance(file_path, bytes):
        file_path = file_path.decode("utf-8")
    return theory_xxhash128(file_path, parent_hashes)
