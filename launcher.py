#!/usr/bin/env python3
import Isabelle_RPC_Host
import logging
import sys

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        addr = sys.argv[1]
    else:
        addr = 'localhost:27182'
    
    # Check for log file argument
    log_file = None
    if len(sys.argv) > 2:
        log_file = sys.argv[2]
    logger = Isabelle_RPC_Host.mk_logger_(addr, log_file)
    Isabelle_RPC_Host._load_remote_procedures(logger)
    print(Isabelle_RPC_Host.Remote_Procedures)

    # Create and start the server
    with Isabelle_RPC_Host.Server(addr, logger) as server:
        server.run_server()