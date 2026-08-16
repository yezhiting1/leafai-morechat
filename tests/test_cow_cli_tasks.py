import os
from types import SimpleNamespace

import plugins


_old_plugin_path = plugins.instance.current_plugin_path
plugins.instance.current_plugin_path = os.path.join(os.getcwd(), "plugins", "cow_cli")
try:
    from plugins.cow_cli.cow_cli import KNOWN_COMMANDS
finally:
    plugins.instance.current_plugin_path = _old_plugin_path

CowCliPlugin = plugins.instance.plugins["COW_CLI"]


class FakeTaskStore:
    def __init__(self, tasks):
        self.tasks = tasks

    def list_tasks(self):
        return list(self.tasks)


def _task(task_id, receiver, channel_type, enabled=True, notify_session_id=None):
    action = {
        "receiver": receiver,
        "channel_type": channel_type,
    }
    if notify_session_id:
        action["notify_session_id"] = notify_session_id
    return {
        "id": task_id,
        "name": f"Task {task_id}",
        "enabled": enabled,
        "schedule": {"type": "cron", "expression": "0 9 * * *"},
        "next_run_at": "2026-07-18T09:00:00",
        "action": action,
    }


def _event_context(channel_type, receiver, session_id):
    context = SimpleNamespace(
        kwargs={
            "channel_type": channel_type,
            "receiver": receiver,
            "session_id": session_id,
        }
    )
    context.get = context.kwargs.get
    return {"context": context}


def test_tasks_is_a_known_command_and_is_listed_in_help():
    plugin = CowCliPlugin()

    assert "tasks" in KNOWN_COMMANDS
    assert "/tasks" in plugin._cmd_help("", None)


def test_tasks_command_only_lists_tasks_owned_by_current_channel_and_receiver(monkeypatch):
    store = FakeTaskStore(
        [
            _task("mine", "user-1", "telegram"),
            _task("other-channel", "user-1", "feishu"),
            _task("other-user", "user-2", "telegram"),
        ]
    )
    monkeypatch.setattr(
        "agent.tools.scheduler.integration.get_task_store", lambda: store
    )
    plugin = CowCliPlugin()

    result = plugin._cmd_tasks(
        "", _event_context("telegram", "user-1", "session-1")
    )

    assert "mine" in result
    assert "other-channel" not in result
    assert "other-user" not in result


def test_tasks_command_uses_session_identity_without_channel_context(monkeypatch):
    store = FakeTaskStore(
        [
            _task("direct", "session-1", "web"),
            _task("notified", "chat-1", "feishu", notify_session_id="session-1"),
            _task("hidden", "session-2", "web"),
        ]
    )
    monkeypatch.setattr(
        "agent.tools.scheduler.integration.get_task_store", lambda: store
    )
    plugin = CowCliPlugin()

    result = plugin._cmd_tasks("", None, session_id="session-1")

    assert "direct" in result
    assert "notified" in result
    assert "hidden" not in result


def test_tasks_command_formats_empty_state(monkeypatch):
    monkeypatch.setattr(
        "agent.tools.scheduler.integration.get_task_store",
        lambda: FakeTaskStore([]),
    )
    plugin = CowCliPlugin()

    result = plugin._cmd_tasks(
        "", _event_context("slack", "channel-1", "session-1")
    )

    assert "task" in result.lower() or "任务" in result
