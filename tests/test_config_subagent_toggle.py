"""Switching sub agents off from the console.

The setting lives under a `subagent` object rather than as a flat key, which
the config API had no way to express, and it is read when the Agent picks its
tools - so a switch that only reached the config file would appear to do
nothing until a restart.
"""

import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

# Keep this unit test independent from the optional web.py dependency. The
# real package is preferred when present: a stub left in sys.modules stands in
# for it in every test that imports the web channel afterwards, and answers
# only for the attributes it happens to declare.
try:
    import web  # noqa: F401
except ImportError:
    web_stub = types.ModuleType("web")
    web_stub.ctx = types.SimpleNamespace(env={})
    web_stub.HTTPError = type("HTTPError", (Exception,), {})
    web_stub.cookies = lambda: {}
    web_stub.header = lambda *args, **kwargs: None
    web_stub.data = lambda: b"{}"
    web_stub.input = lambda **kwargs: types.SimpleNamespace(**kwargs)
    web_stub.setcookie = lambda *args, **kwargs: None
    web_stub.seeother = lambda *args, **kwargs: Exception("seeother")
    web_stub.notfound = lambda *args, **kwargs: Exception("notfound")
    web_stub.badrequest = lambda *args, **kwargs: Exception("badrequest")
    web_stub.application = lambda *args, **kwargs: types.SimpleNamespace(wsgifunc=lambda: None)
    web_stub.httpserver = types.SimpleNamespace(
        LogMiddleware=type("LogMiddleware", (), {"log": lambda *args, **kwargs: None}),
        StaticMiddleware=lambda app: app,
        WSGIServer=lambda *args, **kwargs: types.SimpleNamespace(serve_forever=lambda: None),
    )
    sys.modules["web"] = web_stub

from agent.subagent import SubagentSettings
from agent.tools.subagent import SubagentTool
from channel.web import web_channel

ROOT = Path(__file__).parents[1]


def _post(tmp_path, updates, stored=None, runtime=None):
    """Run one config save against a config.json in tmp_path."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(stored or {}), encoding="utf-8")
    live = runtime if runtime is not None else {}

    with patch("channel.web.web_channel._require_auth"), \
         patch("channel.web.web_channel.web.header"), \
         patch("channel.web.web_channel.web.data",
               return_value=json.dumps({"updates": updates}).encode()), \
         patch("channel.web.web_channel.conf", return_value=live), \
         patch("channel.web.web_channel.get_data_root", return_value=str(tmp_path)), \
         patch("channel.web.web_channel._read_config_file_for_write",
               return_value=json.loads(config_path.read_text(encoding="utf-8"))):
        response = json.loads(web_channel.ConfigHandler().POST())

    return response, json.loads(config_path.read_text(encoding="utf-8")), live


def test_the_switch_reaches_the_nested_setting(tmp_path):
    response, saved, live = _post(tmp_path, {"subagent_enabled": False})

    assert response["status"] == "success"
    assert saved["subagent"]["enabled"] is False
    # And the running process, so the next turn already sees it.
    assert live["subagent"]["enabled"] is False


def test_the_rest_of_the_section_survives_the_switch(tmp_path):
    """The console sends the one switch it owns. Assigning the section would
    silently reset limits the user set by hand."""
    stored = {"subagent": {"enabled": True, "max_concurrent": 8, "timeout_seconds": 900}}

    _, saved, _ = _post(tmp_path, {"subagent_enabled": False}, stored=stored)

    assert saved["subagent"] == {"enabled": False, "max_concurrent": 8, "timeout_seconds": 900}


def test_turning_it_back_on_is_just_as_much_a_save(tmp_path):
    stored = {"subagent": {"enabled": False}}

    _, saved, _ = _post(tmp_path, {"subagent_enabled": True}, stored=stored)

    assert saved["subagent"]["enabled"] is True


def test_an_unknown_key_alongside_it_is_still_refused(tmp_path):
    response, saved, _ = _post(tmp_path, {"not_a_setting": 1})

    assert response["status"] == "error"
    assert "subagent" not in saved


def test_sub_agents_are_on_when_nothing_says_otherwise():
    """What an install that has never heard of the setting gets."""
    with patch("config.conf", return_value={}):
        assert SubagentSettings.from_config().enabled is True


def test_the_tool_follows_the_setting_without_a_restart():
    tool = SubagentTool({"cwd": "/tmp"})

    with patch("config.conf", return_value={"subagent": {"enabled": False}}):
        assert tool.is_available() is False
    with patch("config.conf", return_value={"subagent": {"enabled": True}}):
        assert tool.is_available() is True


def test_an_unavailable_tool_is_not_offered_to_the_model():
    """The guard inside the tool only fires once the model has already called
    it - a turn spent, and an error where an answer should be."""
    from agent.protocol.agent_stream import AgentStreamExecutor

    executor = object.__new__(AgentStreamExecutor)
    tool = SubagentTool({"cwd": "/tmp"})
    executor.tools = {"subagent": tool}

    with patch("config.conf", return_value={"subagent": {"enabled": False}}):
        assert executor._select_tools_for_injection() == []
    with patch("config.conf", return_value={"subagent": {"enabled": True}}):
        assert executor._select_tools_for_injection() == [tool]


def test_a_broken_availability_check_does_not_cost_the_agent_the_tool():
    from agent.tools.base_tool import is_tool_available

    class _Broken:
        name = "broken"

        def is_available(self):
            raise RuntimeError("nope")

    assert is_tool_available(_Broken()) is True


def test_the_switch_is_exposed_by_both_consoles():
    web_source = (ROOT / "channel/web/web_channel.py").read_text(encoding="utf-8")
    web_markup = (ROOT / "channel/web/chat.html").read_text(encoding="utf-8")
    web_console = (ROOT / "channel/web/static/js/console.js").read_text(encoding="utf-8")
    desktop_page = (ROOT / "desktop/src/renderer/src/pages/settings/BasicSettings.tsx").read_text(encoding="utf-8")

    assert '"subagent_enabled": ("subagent", "enabled")' in web_source
    assert 'id="cfg-subagent"' in web_markup
    assert "subagent_enabled: document.getElementById('cfg-subagent').checked" in web_console
    assert "subagent_enabled: subagent" in desktop_page
    # Absent means on, so neither console may read it as a bare truthy check.
    assert "data.subagent_enabled !== false" in web_console
    assert "data.subagent_enabled !== false" in desktop_page
