"""Tool calls whose arguments never arrived.

An empty argument string parses into an empty dict, so the call used to reach
the tool and come back as "path parameter is required" - pointing the model at
a parameter it never got to send, which it then tries to fix by resending the
same oversized call.
"""

from agent.protocol.agent_stream import (
    AgentStreamExecutor,
    _cut_off_message,
    _parse_tool_args,
)
from agent.tools.bash.bash import Bash
from agent.tools.write.write import Write


def _executor():
    """Executor with just enough wired up to run _execute_tool's guards."""
    executor = object.__new__(AgentStreamExecutor)
    executor.tools = {"write": Write({"cwd": "/tmp"}), "bash": Bash({"cwd": "/tmp"})}
    executor._record_tool_result = lambda *args, **kwargs: None
    return executor


def test_empty_args_at_the_token_limit_report_truncation():
    args, error = _parse_tool_args("", "length", "write")
    assert args == {}
    assert "cut off by the output token limit" in error


def test_empty_args_without_a_truncation_signal_are_left_to_the_executor():
    assert _parse_tool_args("", "tool_calls", "bash") == ({}, None)


def test_missing_required_params_are_not_reported_as_a_missing_field():
    result = _executor()._execute_tool({"id": "1", "name": "write", "arguments": {}})

    assert result["status"] == "error"
    assert "no arguments at all" in result["result"]
    assert "path, content" in result["result"]
    # The old wording sent the model chasing a single parameter.
    assert "path parameter is required" not in result["result"]


def test_tool_without_required_params_is_not_blocked():
    assert _executor()._required_params("bash") == []


def test_unknown_tool_falls_through_to_the_not_found_path():
    assert _executor()._required_params("nope") == []


def test_split_advice_only_goes_to_the_file_writing_tools():
    assert "use edit rather than" in _cut_off_message("the output token limit", "write")
    assert "use edit rather than" not in _cut_off_message("the output token limit", "bash")
