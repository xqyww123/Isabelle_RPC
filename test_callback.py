"""
Test module for Isabelle RPC callback mechanism.

This module demonstrates how Python remote procedures can call back
into Isabelle/ML functions during execution.
"""

from Isabelle_RPC_Host import isabelle_remote_procedure, Connection


@isabelle_remote_procedure("call_heartbeat_callback")
async def call_heartbeat_callback(arg, connection: Connection):
    """
    Test function that calls the Isabelle heartbeat callback.

    This demonstrates the basic callback mechanism:
    1. Python RPC is called from Isabelle
    2. Python calls back to Isabelle's "isabelle_heartbeat" callback
    3. Returns the heartbeat message

    Args:
        arg: Unit value (ignored)
        connection: The RPC connection

    Returns:
        The heartbeat message string from Isabelle
    """
    # Call the Isabelle heartbeat callback
    heartbeat_msg = await connection.callback("isabelle_heartbeat", None)

    # Return the message
    return heartbeat_msg


@isabelle_remote_procedure("test_callback_add")
async def test_callback_add(arg, connection: Connection):
    """
    Test function that uses callbacks to perform addition in Isabelle.

    Args:
        arg: A list of integers
        connection: The RPC connection

    Returns:
        The sum computed by calling the Isabelle 'add_two_numbers' callback
    """
    if not isinstance(arg, list) or len(arg) != 2:
        raise ValueError("Expected a list of two integers")

    a, b = arg
    # Call back to Isabelle to perform the addition
    result = await connection.callback("add_two_numbers", [a, b])

    return result


@isabelle_remote_procedure("test_callback_string_process")
async def test_callback_string_process(arg, connection: Connection):
    """
    Test function that uses callbacks to process strings in Isabelle.

    Args:
        arg: A string
        connection: The RPC connection

    Returns:
        The processed string from Isabelle
    """
    # Call back to Isabelle to reverse the string
    reversed_str = await connection.callback("reverse_string", arg)

    # Call back to Isabelle to convert to uppercase
    upper_str = await connection.callback("to_uppercase", reversed_str)

    return upper_str


@isabelle_remote_procedure("test_multiple_callbacks")
async def test_multiple_callbacks(arg, connection: Connection):
    """
    Test function that makes multiple callbacks.

    Args:
        arg: An integer
        connection: The RPC connection

    Returns:
        A list of results from multiple callbacks
    """
    results = []

    # Call the increment callback multiple times
    value = arg
    for i in range(5):
        value = await connection.callback("increment", value)
        results.append(value)

    return results


@isabelle_remote_procedure("test_getenv")
async def test_getenv(arg, connection: Connection):
    """Roundtrip for Connection.getenv (standing global "getenv" callback).

    Returns [ISABELLE_HOME_USER as seen through the callback,
             the default for a variable set nowhere] — the ML side asserts
    the first against its own getenv and the second against the literal.
    """
    home_user = await connection.getenv("ISABELLE_HOME_USER")
    fallback = await connection.getenv("SURELY_UNSET_VAR_1D8F0C", "fallback-default")
    return [home_user, fallback]


@isabelle_remote_procedure("test_dialogue")
async def test_dialogue(arg, connection: Connection):
    import Isabelle_RPC_Host.dialogue  # noqa: F811
    answer = await connection.dialogue("How are you?", ["Good", "Bad"])
    if answer is None:
        # No attached frontend can answer dialogs (the no-responder sentinel):
        # under Isa-REPL/build/headless the question is not even shown.
        await connection.writeln("(no frontend can answer dialogs here)")
        return "<no-responder>"
    if answer == "Good":
        await connection.writeln("Glad to hear that!")
    else:
        await connection.writeln("Hope you feel better soon!")
    return answer
