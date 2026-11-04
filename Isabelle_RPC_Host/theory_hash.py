import asyncio
import os
import time
from typing import Any

import lmdb
import msgpack
from Isabelle_RPC_Host import Connection, isabelle_remote_procedure
from Isabelle_RPC_Host.paths import semantic_DB_dir

# A theory hash: 16 bytes, computed in Isabelle/ML (Theory_Hash, in
# Performant_Isabelle_ML's library/theory_hash.ML), never here.
type theory_hash = bytes

def is_persistent(h: bytes) -> bool:
    """Check whether a theory hash is from a saved heap image (LSB of byte 0 = 0)."""
    return h[0] & 1 == 0


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
