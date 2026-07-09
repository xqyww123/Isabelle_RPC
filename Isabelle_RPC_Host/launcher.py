#!/usr/bin/env python3
"""Entry point of the Isabelle RPC host server."""
import asyncio
import logging
import os
import sys

import Isabelle_RPC_Host


def main():
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        addr = sys.argv[1]
    else:
        addr = os.environ.get('RPC_Host', '127.0.0.1:27182')

    # Check for log file argument
    log_file = None
    if len(sys.argv) > 2:
        log_file = sys.argv[2]
    logger = Isabelle_RPC_Host.mk_logger_(addr, log_file)
    Isabelle_RPC_Host._load_remote_procedures(logger)
    print(Isabelle_RPC_Host.Remote_Procedures)

    # Create and start the server
    with Isabelle_RPC_Host.Server(addr, logger) as server:
        asyncio.run(server.run_server())


if __name__ == "__main__":
    main()
