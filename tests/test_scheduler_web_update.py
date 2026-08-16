"""Regression tests for scheduler edits made through the Web console."""

import json
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from agent.tools.scheduler.task_store import TaskStore

# Keep this unit test independent from the optional web.py dependency.
if "web" not in sys.modules:
    web_stub = types.ModuleType("web")
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

from channel.web import web_channel

SchedulerUpdateHandler = web_channel.SchedulerUpdateHandler


def _store_task(tmp_path, action):
    store = TaskStore(str(tmp_path / "scheduler" / "tasks.json"))
    store.add_task({
        "id": "task-1",
        "name": "maintenance",
        "enabled": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "next_run_at": (datetime.now() + timedelta(hours=1)).isoformat(),
        "schedule": {"type": "interval", "seconds": 3600},
        "action": action,
    })
    return store


def _post_update(tmp_path, payload):
    with patch("channel.web.web_channel._require_auth"), \
         patch("channel.web.web_channel.web.header"), \
         patch("channel.web.web_channel.web.data", return_value=json.dumps(payload).encode()), \
         patch("channel.web.web_channel._get_workspace_root", return_value=str(tmp_path)):
        return json.loads(SchedulerUpdateHandler().POST())


def test_web_manual_run_is_authenticated_and_delegates_to_scheduler():
    assert hasattr(web_channel, "SchedulerRunHandler")

    service = Mock()
    with patch("channel.web.web_channel._require_auth") as require_auth, \
         patch("channel.web.web_channel.web.header"), \
         patch("channel.web.web_channel.web.data", return_value=b'{"task_id":"task-1"}'), \
         patch("agent.tools.scheduler.integration.get_scheduler_service", return_value=service):
        response = json.loads(web_channel.SchedulerRunHandler().POST())

    require_auth.assert_called_once_with()
    service.run_task_now.assert_called_once_with("task-1")
    assert response == {
        "status": "success",
        "message": "Task 'task-1' queued for immediate execution",
    }


def test_web_manual_run_rejects_unavailable_scheduler():
    assert hasattr(web_channel, "SchedulerRunHandler")

    with patch("channel.web.web_channel._require_auth"), \
         patch("channel.web.web_channel.web.header"), \
         patch("channel.web.web_channel.web.data", return_value=b'{"task_id":"task-1"}'), \
         patch("agent.tools.scheduler.integration.get_scheduler_service", return_value=None):
        response = json.loads(web_channel.SchedulerRunHandler().POST())

    assert response == {
        "status": "error",
        "message": "Scheduler service is not running",
    }


def test_manual_run_is_exposed_by_explicit_web_and_desktop_controls():
    root = Path(__file__).parents[1]
    web_source = (root / "channel/web/web_channel.py").read_text(encoding="utf-8")
    web_console = (root / "channel/web/static/js/console.js").read_text(encoding="utf-8")
    desktop_client = (root / "desktop/src/renderer/src/api/client.ts").read_text(encoding="utf-8")
    desktop_page = (root / "desktop/src/renderer/src/pages/TasksPage.tsx").read_text(encoding="utf-8")

    assert "'/api/scheduler/run', 'SchedulerRunHandler'" in web_source
    assert "function runTaskNow(task, button)" in web_console
    assert "fetch('/api/scheduler/run'" in web_console
    web_run = web_console[web_console.index("function runTaskNow(task, button)"):]
    assert "showConfirmDialog({" in web_run[:2500]
    assert "async runTask(taskId: string)" in desktop_client
    assert "'/api/scheduler/run'" in desktop_client
    assert "const runNow = async ()" in desktop_page
    assert "window.confirm(t('task_run_confirm'))" in desktop_page


def test_web_edit_preserves_hidden_agent_action_fields(tmp_path):
    store = _store_task(tmp_path, {
        "type": "agent_task",
        "task_description": "refresh the index",
        "receiver": "user-1",
        "receiver_name": "User",
        "is_group": False,
        "channel_type": "feishu",
        "notify_session_id": "session-1",
        "silent": True,
        "delivery_extension": {"trace": True},
    })

    result = _post_update(tmp_path, {
        "task_id": "task-1",
        "name": "renamed maintenance",
        "action": {
            "type": "agent_task",
            "task_description": "refresh both indexes",
            "receiver": "user-1",
            "channel_type": "feishu",
        },
    })

    assert result["status"] == "success"
    action = store.get_task("task-1")["action"]
    assert action["task_description"] == "refresh both indexes"
    assert action["silent"] is True
    assert action["notify_session_id"] == "session-1"
    assert action["delivery_extension"] == {"trace": True}


def test_switch_to_message_drops_agent_only_fields(tmp_path):
    store = _store_task(tmp_path, {
        "type": "agent_task",
        "task_description": "refresh the index",
        "receiver": "user-1",
        "channel_type": "web",
        "notify_session_id": "session-1",
        "silent": True,
    })

    result = _post_update(tmp_path, {
        "task_id": "task-1",
        "action": {
            "type": "send_message",
            "content": "Index refresh reminder",
            "receiver": "user-1",
            "channel_type": "web",
        },
    })

    assert result["status"] == "success"
    action = store.get_task("task-1")["action"]
    assert action["content"] == "Index refresh reminder"
    assert "task_description" not in action
    assert "silent" not in action
    assert action["notify_session_id"] == "session-1"
