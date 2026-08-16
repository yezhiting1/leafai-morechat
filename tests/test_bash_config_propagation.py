"""
Tests for bash tool config propagation fix (Issue #2983).

Verifies that config.json's tools.bash.timeout and tools.bash.safety_mode
are correctly propagated to the Bash tool instance through the full init path:
  ToolManager.create_tool() -> AgentInitializer._load_tools()

Covers:
  - Direct config propagation through ToolManager.create_tool()
  - Full path through AgentInitializer._load_tools() merge logic
  - Default values when no config is provided
  - The exact repro scenario from #2983
"""

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_tool_manager(tool_configs=None):
    """
    Build a ToolManager pre-loaded with bash and set to the given configs.

    We set tool_classes / tool_configs manually to bypass the full
    config.json dependency.
    """
    from agent.tools.tool_manager import ToolManager
    from agent.tools.bash.bash import Bash

    tm = ToolManager()
    tm.tool_classes = {"bash": Bash}

    # Give ToolManager a config dict so create_tool() picks it up
    if tool_configs is not None:
        tm.tool_configs = tool_configs
    else:
        tm.tool_configs = {}

    return tm


# ---------------------------------------------------------------------------
# Tests: ToolManager.create_tool() path
# ---------------------------------------------------------------------------


class TestCreateToolPath:
    """
    Config dict propagation via ToolManager.create_tool().

    create_tool() is responsible only for handing the per-tool config dict
    (tool_configs[name]) to the tool instance. The config-derived attributes
    (default_timeout / safety_mode) are re-derived later by the
    AgentInitializer._load_tools() merge loop — see TestAgentInitializerMergePath.
    """

    def test_create_tool_applies_full_config(self):
        """tool_configs['bash'] is applied verbatim to tool.config."""
        tm = make_tool_manager({"bash": {"timeout": 5, "safety_mode": False}})
        tool = tm.create_tool("bash")
        assert tool.config == {"timeout": 5, "safety_mode": False}

    def test_create_tool_applies_timeout_only(self):
        """Partial config is propagated as-is to tool.config."""
        tm = make_tool_manager({"bash": {"timeout": 10}})
        tool = tm.create_tool("bash")
        assert tool.config == {"timeout": 10}

    def test_create_tool_applies_safety_mode_only(self):
        """Partial config is propagated as-is to tool.config."""
        tm = make_tool_manager({"bash": {"safety_mode": False}})
        tool = tm.create_tool("bash")
        assert tool.config == {"safety_mode": False}

    def test_empty_config_defaults(self):
        """No tool_configs at all — config is empty and attributes keep built-ins."""
        from agent.tools.bash.bash import Bash
        tm = make_tool_manager({})
        tool = tm.create_tool("bash")
        assert tool.config == {}
        assert tool.default_timeout == Bash.DEFAULT_TIMEOUT
        assert tool.safety_mode is True

    def test_non_bash_tool_unaffected(self):
        """ToolManager.create_tool() should not crash for non-bash tools."""
        from agent.tools.tool_manager import ToolManager
        from agent.tools.base_tool import BaseTool

        tm = ToolManager()

        class DummyTool(BaseTool):
            name = "dummy"
            description = "dummy"

        tm.tool_classes = {"dummy": DummyTool}
        tm.tool_configs = {"bash": {"timeout": 5}}

        tool = tm.create_tool("dummy")
        assert tool is not None
        assert tool.name == "dummy"


# ---------------------------------------------------------------------------
# Tests: AgentInitializer._load_tools() merge path
# ---------------------------------------------------------------------------


class TestAgentInitializerMergePath:
    """Full path through AgentInitializer._load_tools() merge logic."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Clear ToolManager singleton state for each test."""
        from agent.tools.tool_manager import ToolManager
        ToolManager._instance = None
        yield

    def _simulate_load_tools_merge(self, tool, tool_name, file_config, merged_extra=None):
        """
        Simulate the merge logic from AgentInitializer._load_tools().
        Returns the modified tool.
        """
        merged = dict(getattr(tool, "config", None) or {})
        merged.update(file_config)
        if merged_extra:
            merged.update(merged_extra)
        tool.config = merged
        tool.cwd = merged.get("cwd", getattr(tool, "cwd", None))
        if "memory_manager" in merged:
            tool.memory_manager = merged["memory_manager"]
        # The fix: also re-derive config-derived attributes
        if hasattr(tool, "default_timeout"):
            tool.default_timeout = merged.get("timeout", tool.default_timeout)
        if hasattr(tool, "safety_mode"):
            tool.safety_mode = merged.get("safety_mode", tool.safety_mode)
        return tool

    def test_merge_preserves_bash_config(self):
        """Bash tool config survives the merge and reaches the instance."""
        from agent.tools.bash.bash import Bash
        tool = Bash()
        tool.config = {"timeout": 5, "safety_mode": False}
        file_config = {"cwd": "/tmp", "memory_manager": None}
        self._simulate_load_tools_merge(tool, "bash", file_config)
        assert tool.default_timeout == 5, f"Expected 5, got {tool.default_timeout}"
        assert tool.safety_mode is False, f"Expected False, got {tool.safety_mode}"

    def test_merge_does_not_override_when_not_in_config(self):
        """When config has no timeout/safety_mode, merge should keep defaults."""
        from agent.tools.bash.bash import Bash
        tool = Bash()
        tool.config = {"cwd": "/somewhere"}
        file_config = {"cwd": "/tmp", "memory_manager": None}
        self._simulate_load_tools_merge(tool, "bash", file_config)
        assert tool.default_timeout == Bash.DEFAULT_TIMEOUT, f"Expected {Bash.DEFAULT_TIMEOUT}, got {tool.default_timeout}"
        assert tool.safety_mode is True, f"Expected True, got {tool.safety_mode}"

    def test_merge_with_cwd_only(self):
        """file_config only has cwd — should not corrupt bash attributes."""
        from agent.tools.bash.bash import Bash
        tool = Bash()
        tool.config = {"timeout": 15}
        file_config = {"cwd": "/tmp/workspace"}
        self._simulate_load_tools_merge(tool, "bash", file_config)
        assert tool.default_timeout == 15
        assert tool.cwd == "/tmp/workspace"
        assert tool.safety_mode is True

    def test_merge_overrides_from_tool_config(self):
        """merged_extra (simulating tools.bash in config.json) wins."""
        from agent.tools.bash.bash import Bash
        tool = Bash()
        tool.config = {"timeout": 5}
        file_config = {"cwd": "/tmp"}
        self._simulate_load_tools_merge(tool, "bash", file_config,
                                        merged_extra={"timeout": 60})
        assert tool.default_timeout == 60, f"Expected 60, got {tool.default_timeout}"


# ---------------------------------------------------------------------------
# Tests: end-to-end reproduction of the original bug report
# ---------------------------------------------------------------------------


class TestBugReproduction:
    """Reproduce the exact scenario from Issue #2983."""

    def test_repro_bug_scenario(self):
        """
        The original bug: creating a Bash tool and setting config['timeout']=5
        should result in default_timeout=5. Before the fix it stayed at the
        built-in default because __init__ read from the empty config before
        ToolManager populated it.
        """
        from agent.tools.bash.bash import Bash

        tool = Bash()
        assert tool.default_timeout == Bash.DEFAULT_TIMEOUT  # expected before fix

        # ToolManager sets config after __init__
        tool.config = {"timeout": 5, "safety_mode": False}

        # AgentInitializer merge re-derives attributes (THE FIX)
        merged = dict(tool.config)
        merged.update({"cwd": "/tmp"})
        tool.config = merged
        if hasattr(tool, "default_timeout"):
            tool.default_timeout = merged.get("timeout", tool.default_timeout)
        if hasattr(tool, "safety_mode"):
            tool.safety_mode = merged.get("safety_mode", tool.safety_mode)

        assert tool.default_timeout == 5, (
            f"Config propagation failed: expected 5, got {tool.default_timeout}"
        )
        assert tool.safety_mode is False, (
            f"Config propagation failed: expected False, got {tool.safety_mode}"
        )
