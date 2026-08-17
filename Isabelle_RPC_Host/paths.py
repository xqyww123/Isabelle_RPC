"""Isabelle settings paths, in the form the platform Python actually runs on wants.

On Windows, Isabelle's settings layer runs inside a bundled Cygwin, so the values it
exports are a mix of forms::

    ISABELLE_ROOT      = C:\\isa\\Isabelle2025-2                             [native]
    CYGWIN_ROOT        = C:\\isa\\Isabelle2025-2\\contrib\\cygwin            [native]
    ISABELLE_HOME      = /cygdrive/c/isa/Isabelle2025-2                      [POSIX]
    ISABELLE_HOME_USER = /cygdrive/c/Users/x/.isabelle/Isabelle2025-2        [POSIX]

A *native* Windows Python — which is what the ML launcher spawns — cannot hand the
POSIX ones to ``open`` or ``os.path``: they silently resolve to nothing, so RPC
components fail to register and the symbol table comes up empty.  Turning such a
value into ``C:\\isa\\Isabelle2025-2`` is all this module does.

On Linux and macOS every function here is a no-op.
"""

import os
import subprocess

_CYGDRIVE = "/cygdrive/"


def platform_path(path: str) -> str:
    """Normalize an Isabelle settings path to this platform's native form.

    Idempotent: for every branch the result is a fixed point, so callers may apply
    this more than once (they do — see `resolve_isabelle_var`).
    """
    if os.name != "nt" or not path or not path.startswith("/"):
        return path  # not Windows, empty, or already native

    # /cygdrive/<drive>/... is the form that actually matters — ISABELLE_HOME_USER,
    # the one variable Isabelle exports with no native counterpart, always takes it.
    # Convert it by string rules, never by shelling out: the value came from
    # os.environ, which native Windows Python decoded from the UTF-16 environment
    # block, so it is already correct text. Routing it through a subprocess instead
    # would decode cygpath's UTF-8 output with the ANSI code page, and a non-ASCII
    # user name (C:\Users\张三\...) would come back as mojibake — reintroducing the
    # very bug this module exists to fix.
    if path.startswith(_CYGDRIVE) and len(path) >= len(_CYGDRIVE) + 1:
        drive = path[len(_CYGDRIVE)]
        rest = path[len(_CYGDRIVE) + 1:].lstrip("/").replace("/", "\\")
        return f"{drive.upper()}:\\{rest}"  # "/cygdrive/c" -> "C:\"

    # Anything else is a path inside the Cygwin tree (/usr/bin, /home/x, ...), whose
    # mapping only Cygwin knows. Only here do we pay for a subprocess — and we read
    # it as bytes, because `text=True` would decode with the ANSI code page.
    # CYGWIN_ROOT is itself exported in native form, so locating cygpath needs no
    # prior conversion: there is no bootstrap problem here.
    cygwin_root = os.environ.get("CYGWIN_ROOT")
    cygpath = os.path.join(cygwin_root, "bin", "cygpath.exe") if cygwin_root else "cygpath"
    try:
        completed = subprocess.run([cygpath, "-w", path], capture_output=True)
        native = os.fsdecode(completed.stdout).strip()
        if native and os.path.isabs(native):
            return native
    except (OSError, ValueError):
        # OSError: cygpath missing or unrunnable. ValueError: a decoding failure
        # (UnicodeDecodeError is a ValueError, not an OSError) must not escape and
        # take the host down with an error that has nothing to do with paths.
        pass

    if cygwin_root:  # best effort: assume the Cygwin root is the mount point
        return os.path.join(cygwin_root, path.lstrip("/").replace("/", "\\"))
    return path


def _raw_isabelle_var(name: str) -> str:
    """The settings value as Isabelle exports it, with no path conversion applied.

    Prefer the process environment (which the ML launcher exports when it starts the
    RPC host), and only fall back to querying the `isabelle` executable — which is
    slow and, more importantly, silently yields "" when Isabelle failed to start or
    is not on PATH. Returns "" if neither source has a value.
    """
    value = os.environ.get(name)
    if value:
        return value
    try:
        # Read the output as bytes and decode it ourselves. `os.popen` would hand back
        # a text-mode pipe decoded with the locale encoding — the ANSI code page on
        # Windows — while `isabelle` emits UTF-8, so a non-ASCII user name would come
        # back as mojibake. That branch is unreachable today only because `isabelle` is
        # not on the native PATH there; shipping an isabelle.bat would make it live.
        # `shell=True` stays: on Windows only cmd resolves a .bat.
        completed = subprocess.run(f"isabelle getenv -b {name}", shell=True, capture_output=True)
        return os.fsdecode(completed.stdout).strip()
    except (OSError, ValueError):
        return ""


def resolve_isabelle_var(name: str) -> str:
    """Resolve an Isabelle settings variable, in this platform's native path form."""
    if os.name == "nt" and name == "ISABELLE_HOME":
        # Isabelle exports the native form of ISABELLE_HOME under this name already
        # (getsettings: ISABELLE_ROOT="$(platform_path "$ISABELLE_HOME")"), and it is
        # authoritative about its own mount table. ISABELLE_HOME_USER has no such
        # counterpart, which is why the general path above exists.
        native_home = os.environ.get("ISABELLE_ROOT")
        if native_home:
            return native_home
    return platform_path(_raw_isabelle_var(name))


def resolve_isabelle_path_list(name: str) -> list:
    """Resolve a colon-separated Isabelle settings path list, in native path form.

    Isabelle builds such lists by appending, so that a component's `etc/settings` can
    extend one: ISABELLE_SYMBOLS is how phi-System adds its own symbol files to the
    distribution's. Reading the variable is therefore the only way to see the symbol
    table Isabelle itself presents; reconstructing it from ISABELLE_HOME sees the
    distribution alone.

    A trailing "?" marks an entry Isabelle treats as optional (the user overlay
    carries one). It is stripped here, because a caller skips a missing file anyway.

    Split before converting: `platform_path` takes ONE path. On Windows every element
    arrives in POSIX form — the list is computed inside the bundled Cygwin — so the
    ":" separator is unambiguous there and no native "C:\\..." can be cut in half.
    """
    out = []
    for entry in _raw_isabelle_var(name).split(":"):
        if entry.endswith("?"):
            entry = entry[:-1]
        if entry:
            out.append(platform_path(entry))
    return out
