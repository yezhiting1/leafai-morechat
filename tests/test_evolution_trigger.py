import os
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent.evolution.executor as executor
import agent.evolution.trigger as trigger


class _FakeAgent:
    def __init__(self, turns=3):
        self.messages = []
        self.messages_lock = threading.Lock()
        self._evo_turns = turns
        self._evo_last_active = time.time() - 60


class _FakeBridge:
    def __init__(self, agent):
        self.agent = agent

    def iter_agent_instances(self, include_defaults=False):
        return [("default", "session-test", self.agent)]

    def get_cached_agent(self, session_id, agent_id="default"):
        return self.agent


def _enabled_config():
    return SimpleNamespace(enabled=True)


class EvolutionTriggerConcurrencyTest(unittest.TestCase):
    def test_busy_evolution_scan_preserves_trigger_turns(self):
        agent = _FakeAgent(turns=3)
        bridge = _FakeBridge(agent)
        scan_config = SimpleNamespace(min_turns=1, idle_seconds=0)

        with (
            patch.object(executor, "get_evolution_config", _enabled_config),
            patch.object(executor, "_running_count", executor._MAX_CONCURRENT),
        ):
            trigger._scan_once(bridge, scan_config)

            self.assertEqual(agent._evo_turns, 3)
            self.assertEqual(executor._running_count, executor._MAX_CONCURRENT)

    def test_admitted_evolution_consumes_turns_and_releases_slot(self):
        agent = _FakeAgent(turns=3)
        bridge = _FakeBridge(agent)

        with (
            patch.object(executor, "get_evolution_config", _enabled_config),
            patch.object(executor, "_running_count", 0),
        ):
            evolved = executor.run_evolution_for_session(bridge, "session-test")

            self.assertFalse(evolved)
            self.assertEqual(agent._evo_turns, 0)
            self.assertEqual(executor._running_count, 0)


if __name__ == "__main__":
    unittest.main()
