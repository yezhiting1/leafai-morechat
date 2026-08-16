"""Regression tests for silent scheduled agent tasks."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools.scheduler.integration import _execute_agent_task
from agent.tools.scheduler.scheduler_tool import SchedulerTool


class _Context(dict):
    kwargs = {}


class _TaskStore:
    def __init__(self):
        self.added = []

    def add_task(self, task):
        self.added.append(task)


class _AgentBridge:
    def __init__(self, content="maintenance complete"):
        self.content = content
        self.calls = []

    def agent_reply(self, task_description, **kwargs):
        self.calls.append((task_description, kwargs))
        return SimpleNamespace(content=self.content)


class TestSchedulerSilentMode(unittest.TestCase):
    def test_schema_exposes_silent_for_agent_tasks(self):
        silent = SchedulerTool.params["properties"]["silent"]

        self.assertEqual(silent["type"], "boolean")
        self.assertFalse(silent["default"])

    def test_create_persists_silent_on_agent_task(self):
        tool = SchedulerTool({"channel_type": "web"})
        store = _TaskStore()
        tool.task_store = store
        tool.current_context = _Context(
            receiver="user-1",
            session_id="session-1",
            isgroup=False,
        )

        result = tool.execute(
            {
                "action": "create",
                "name": "refresh token",
                "ai_task": "refresh the token",
                "schedule_type": "interval",
                "schedule_value": "3000",
                "silent": True,
            }
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(len(store.added), 1)
        self.assertIs(store.added[0]["action"]["silent"], True)

    def test_silent_agent_task_executes_without_delivery(self):
        bridge = _AgentBridge()
        task = {
            "id": "task-1",
            "action": {
                "type": "agent_task",
                "task_description": "rotate logs",
                "receiver": "user-1",
                "is_group": False,
                "channel_type": "web",
                "silent": True,
            },
        }

        with patch("channel.channel_factory.create_channel") as create_channel:
            result = _execute_agent_task(task, bridge)

        self.assertTrue(result)
        self.assertEqual(len(bridge.calls), 1)
        create_channel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
