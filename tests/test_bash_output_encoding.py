# encoding:utf-8
"""
Regression test for the Bash tool spilling large output to a temp file.

When a command's output exceeds DEFAULT_MAX_BYTES the full output is written to
a temp file. That file must be opened with encoding='utf-8'; otherwise it falls
back to the platform locale encoding (e.g. cp936/GBK on Chinese Windows), which
raises UnicodeEncodeError for output containing emoji or other characters not
representable in that codepage. The exception previously propagated out and
turned an otherwise-successful command (exit code 0) into a tool error, losing
all of its output.
"""
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools.bash.bash import Bash


def test_large_non_locale_output_is_saved_as_utf8(tmp_path):
    tool = Bash({"cwd": str(tmp_path), "safety_mode": False})

    # Emit ~80KB (> 50KB DEFAULT_MAX_BYTES) of an emoji so the tool spills the
    # full output to a temp file. Raw UTF-8 bytes are written from the child so
    # the command line stays pure ASCII and the child's own stdout encoding is
    # irrelevant.
    code = "import sys; sys.stdout.buffer.write((chr(0x1F389) * 20000).encode('utf-8'))"
    command = f'"{sys.executable}" -c "{code}"'

    real_named_temp_file = tempfile.NamedTemporaryFile
    captured = {}

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real_named_temp_file(*args, **kwargs)

    temp_file_path = None
    try:
        with patch(
            "agent.tools.bash.bash.tempfile.NamedTemporaryFile", side_effect=spy
        ):
            result = tool.execute({"command": command, "timeout": 60})

        # Command succeeded, so the tool must not report an error.
        assert result.status == "success", result.result

        # The temp file must be opened as UTF-8 (the actual fix).
        assert captured.get("encoding") == "utf-8"

        # And the emoji must round-trip through the saved file.
        temp_file_path = result.result["details"]["full_output_path"]
        with open(temp_file_path, encoding="utf-8") as f:
            assert "\U0001f389" in f.read()
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
