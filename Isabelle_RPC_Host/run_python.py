"""Run Python source code via Isabelle RPC.

The ML side sends a Python source code string; the Python side executes it
inside an async function with access to the active Isabelle ``connection``.

Usage from ML::

    Run_Python.run "return str(1 + 2)"          (* => SOME "3" *)
    Run_Python.run "x = 42"                     (* => NONE *)
    Run_Python.run "return await connection.callback('Config.lookup', 'name')"

The source is wrapped in ``async def __aexec__(connection): ...`` so
``await`` and ``return`` work naturally.  The result is converted to a
string; ``None`` (or no explicit ``return``) yields ML ``NONE``.
"""

import textwrap

from .rpc import Connection, isabelle_remote_procedure


@isabelle_remote_procedure("run_python")
async def _run_python(source: str | bytes, connection: Connection) -> str | None:
    if isinstance(source, bytes):
        source = source.decode("utf-8")

    indented = textwrap.indent(source.strip(), "    ")
    wrapper = f"async def __aexec__(connection):\n{indented}\n"

    namespace: dict = {}
    exec(compile(wrapper, "<run_python>", "exec"), namespace)
    result = await namespace["__aexec__"](connection)

    if result is None:
        return None
    return str(result)
