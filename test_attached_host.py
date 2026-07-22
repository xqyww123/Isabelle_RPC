"""Cross-platform tests for the attached (ephemeral) RPC host.

No Isabelle required: hosts are spawned via ``sys.executable`` exactly the way the
ML side does (RPC_EPHEMERAL_HOST_PLAN.md §3.1), and the client side speaks the wire
protocol over a raw socket.  This is the CI-side evidence for the plan's §5
cross-platform matrix — on Windows in particular: NTFS ``os.replace`` atomicity of
the ready-file, RST-on-process-termination driving the lifeline (the load-bearing
Windows assumption), and the daemon-thread leak guard.

Run with pytest, or directly: ``python test_attached_host.py``.
"""

import msgpack
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# Generous bounds: CI runners are slow and noisy.
READY_TIMEOUT = 30.0
EXIT_TIMEOUT = 15.0


def _spawn(tmpdir: str, token: str, env_extra: dict | None = None):
    """Spawn run_attached__ the way RPC.ML does; return (proc, port, log_path)."""
    log = os.path.join(tmpdir, f"RPC_attached_{token}.log")
    ready = os.path.join(tmpdir, f"RPC_attached_{token}.info")
    env = {**os.environ,
           "PYTHONPATH": HERE + os.pathsep + os.environ.get("PYTHONPATH", ""),
           # The real launch script always exports ISABELLE_HOME_USER; mirror that.
           # Without it, _load_remote_procedures -> isabelle_home_user() sys.exit(1)s
           # right after the ready-file is written (no Isabelle on CI runners), and
           # every connect gets ECONNREFUSED.  Pointing it at the tmpdir also isolates
           # the tests from the developer machine's real etc/rpc_components.
           "ISABELLE_HOME_USER": tmpdir}
    if env_extra:
        env.update(env_extra)
    errf = open(log, "a")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c",
             "import Isabelle_RPC_Host\nIsabelle_RPC_Host.run_attached__()",
             "127.0.0.1:0", log, ready, token],
            env=env, stdout=subprocess.DEVNULL, stderr=errf)
    finally:
        errf.close()  # the child inherited the fd; keeping ours open pins the file on Windows
    deadline = time.monotonic() + READY_TIMEOUT
    while time.monotonic() < deadline:
        if os.path.exists(ready):
            break
        if proc.poll() is not None:
            raise AssertionError(
                f"host died at launch (rc={proc.returncode}):\n" + open(log).read())
        time.sleep(0.05)
    else:
        proc.kill()
        raise AssertionError("ready-file never appeared:\n" + open(log).read())
    port_s, tok = open(ready).read().split()
    assert tok == token, f"ready-file token {tok!r} != {token!r}"
    assert not os.path.exists(ready + ".tmp"), "temp file left behind"
    os.remove(ready)  # what the ML side does after parsing
    return proc, int(port_s), log


def _rpc(sock: socket.socket, name: str, arg):
    """One request, one tagged reply, like RPC.ML's write + read_tagged."""
    sock.sendall(msgpack.packb((0, (name, arg))))
    unp = msgpack.Unpacker()
    while True:
        data = sock.recv(65536)
        if not data:
            raise ConnectionResetError("peer closed")
        unp.feed(data)
        for msg in unp:
            return msg


def _wait_exit(proc: subprocess.Popen, what: str, timeout: float = EXIT_TIMEOUT) -> int:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        rc = proc.poll()
        if rc is not None:
            print(f"  {what}: host exited rc={rc} after {time.monotonic() - t0:.2f}s")
            return rc
    proc.kill()
    raise AssertionError(f"{what}: host still alive after {timeout}s")


def _stop(proc: subprocess.Popen):
    """Hard-stop and REAP: kill() alone races Windows tempdir cleanup (WinError 32)."""
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _assert_alive(proc: subprocess.Popen, what: str):
    assert proc.poll() is None, f"{what}: host died unexpectedly (rc={proc.returncode})"


def test_identity_and_ready_file():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        proc, port, _ = _spawn(d, "tokA")
        try:
            with socket.create_connection(("127.0.0.1", port)) as s:
                tag, tok = _rpc(s, "rpc_host_identity", None)
                assert (tag, tok) == (0, "tokA")
        finally:
            _stop(proc)


def test_lifeline_clean_close():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        proc, port, _ = _spawn(d, "tokB")
        try:
            s = socket.create_connection(("127.0.0.1", port))
            tag, _ack = _rpc(s, "attached_lifeline", "tokB")
            assert tag == 0, "claim must be acked with a tag-0 reply"
            time.sleep(0.2)
            _assert_alive(proc, "after claim")
            s.close()
            assert _wait_exit(proc, "clean lifeline EOF") == 0
        finally:
            _stop(proc)


def test_same_chunk_claim_plus_fin_race():
    """The dominant ordering when the client dies at claim time (plan §3.2)."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        proc, port, _ = _spawn(d, "tokC")
        try:
            s = socket.create_connection(("127.0.0.1", port))
            s.sendall(msgpack.packb((0, ("attached_lifeline", "tokC"))))
            s.close()
            assert _wait_exit(proc, "same-chunk claim+FIN") == 0
        finally:
            _stop(proc)


def test_wrong_token_rejected_then_claimable():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        proc, port, _ = _spawn(d, "tokD")
        try:
            s = socket.create_connection(("127.0.0.1", port))
            tag, _err = _rpc(s, "attached_lifeline", "WRONG")
            assert tag == 1, "wrong token must be rejected with a tag-1 error"
            time.sleep(0.3)
            _assert_alive(proc, "after rejected claim")
            s2 = socket.create_connection(("127.0.0.1", port))
            tag, _ack = _rpc(s2, "attached_lifeline", "tokD")
            assert tag == 0
            s2.close()
            s.close()
            assert _wait_exit(proc, "claim-after-rejection EOF") == 0
        finally:
            _stop(proc)


def test_garbage_after_claim():
    """Reader death without a close sentinel — what forces the task-await form."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        proc, port, _ = _spawn(d, "tokE")
        try:
            s = socket.create_connection(("127.0.0.1", port))
            tag, _ack = _rpc(s, "attached_lifeline", "tokE")
            assert tag == 0
            s.sendall(b"\xc1\xc1\xc1\xc1")  # 0xc1: invalid msgpack byte
            s.close()
            assert _wait_exit(proc, "garbage-after-claim") == 0
        finally:
            _stop(proc)


_CLIENT = textwrap.dedent("""
    import msgpack, socket, sys, time
    port, token = int(sys.argv[1]), sys.argv[2]
    s = socket.create_connection(("127.0.0.1", port))
    s.sendall(msgpack.packb((0, ("attached_lifeline", token))))
    u = msgpack.Unpacker()
    while True:
        d = s.recv(65536)
        u.feed(d)
        for _m in u:
            print("CLAIMED", flush=True)
            time.sleep(600)
""")


def test_killed_client_process_drops_lifeline():
    """SIGKILL/TerminateProcess of the lifeline holder must kill the host.

    This is the design's central promise ("the host dies with its Isabelle process,
    on every exit path") reduced to its OS kernel core: forced process termination
    closes the socket (FIN on POSIX, RST on Windows handle cleanup) and the host's
    reader sees it.  On Windows CI this is the only automated evidence for that.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        proc, port, _ = _spawn(d, "tokF")
        client = None
        try:
            client = subprocess.Popen(
                [sys.executable, "-c", _CLIENT, str(port), "tokF"],
                stdout=subprocess.PIPE, text=True)
            assert client.stdout is not None
            line = client.stdout.readline().strip()
            assert line == "CLAIMED", f"client failed to claim: {line!r}"
            time.sleep(0.2)
            _assert_alive(proc, "while client holds the lifeline")
            client.kill()  # SIGKILL / TerminateProcess — no cleanup runs in the client
            assert _wait_exit(proc, "client hard-killed") == 0
        finally:
            if client:
                _stop(client)
            _stop(proc)


def test_leak_guard_fires_when_never_claimed():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        proc, _port, _ = _spawn(d, "tokG",
                                env_extra={"ISABELLE_RPC_LEAK_GUARD_SECONDS": "2"})
        try:
            t0 = time.monotonic()
            rc = _wait_exit(proc, "leak guard (2 s, never claimed)", timeout=20)
            assert rc == 1, f"guard exit code must be 1, got {rc}"
            assert time.monotonic() - t0 >= 1.0, "guard fired implausibly early"
        finally:
            _stop(proc)


def test_leak_guard_disarmed_by_claim():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        proc, port, _ = _spawn(d, "tokH",
                               env_extra={"ISABELLE_RPC_LEAK_GUARD_SECONDS": "2"})
        try:
            s = socket.create_connection(("127.0.0.1", port))
            tag, _ack = _rpc(s, "attached_lifeline", "tokH")
            assert tag == 0
            time.sleep(3.5)  # well past the shortened guard
            _assert_alive(proc, "claimed host must outlive the guard deadline")
            s.close()
            assert _wait_exit(proc, "post-guard clean EOF") == 0
        finally:
            _stop(proc)


def test_external_server_path_untouched():
    """The back-compat contract (plan §3.6): no guard/ready machinery unless
    run_attached__ passes it — an external Server() must never self-terminate."""
    import logging
    sys.path.insert(0, HERE)
    from Isabelle_RPC_Host import Server, run_attached__  # noqa: F401  (export check)
    srv = Server("127.0.0.1:0", logging.getLogger("x"))
    assert srv.attached_token is None
    assert srv.ready_file is None
    assert srv._leak_guard is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        print(f"== {fn.__name__}")
        fn()
    print(f"ALL {len(fns)} TESTS PASSED")
