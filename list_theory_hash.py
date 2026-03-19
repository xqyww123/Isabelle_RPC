#!/usr/bin/env python3
"""Print theory hashes for a theory and all its dependencies.

Usage:
  python list_theory_hash.py HOL.List
"""
import argparse
import threading
import time
import sys

import msgpack as mp
import Isabelle_RPC_Host
from IsaREPL import Client

parser = argparse.ArgumentParser(description="List theory hashes for a theory and its dependencies")
parser.add_argument("theory", help="Theory name (e.g., HOL.List)")
parser.add_argument("--repl-addr", default="127.0.0.1:6666", help="Isa-REPL server address")
parser.add_argument("--rpc-addr", default="127.0.0.1:27182", help="RPC host address")
parser.add_argument("--session", default="HOL", help="Session qualifier for theory name resolution")
args = parser.parse_args()

logger = Isabelle_RPC_Host.mk_logger_(args.rpc_addr, None)

# Launch RPC host in daemon thread (needed for Theory_Hash.hash_of xxhash128 RPC)
rpc_thread = threading.Thread(
    target=Isabelle_RPC_Host.launch_server_,
    args=(args.rpc_addr, logger), daemon=True)
rpc_thread.start()
time.sleep(1)

# Connect to pre-running Isa-REPL server
c = Client(args.repl_addr, args.session, timeout=None)
print("Loading theories...", file=sys.stderr, flush=True)
fullnames = c.load_theory([args.theory, "Isabelle_RPC.List_Theory_Hash_App"])
print(f"Loaded: {fullnames}", file=sys.stderr, flush=True)

# Run the app
c.run_app("Theory_Hash.list")
mp.pack(args.theory, c.cout)
c.cout.flush()

# Read result: REPL_Server.output wraps as [payload, null]; errors as [null, error_string]
entries, err = c.unpack.unpack()
if err is not None:
    err_msg = err.decode("utf-8") if isinstance(err, bytes) else str(err)
    print(err_msg, file=sys.stderr)
    c.close()
    sys.exit(1)
for name, hash_bytes in entries:
    if isinstance(name, bytes):
        name = name.decode("utf-8")
    print(f"{name}\t{hash_bytes.hex()}")

c.close()
