"""Several calls to one parallel-safe tool in a single turn.

Tools run in the order the model asked for them, which is what most of them
need. A model handed two independent jobs expresses that as two calls, though,
and for a tool whose whole point is that its calls are independent, running the
second only after the first finishes doubles the wait for nothing.
"""

import threading
import time

from agent.protocol.agent_stream import AgentStreamExecutor
from agent.tools.base_tool import BaseTool, ToolResult


class _SlowTool(BaseTool):
    name = "slow"
    params = {"type": "object", "properties": {"tag": {"type": "string"}}}
    delay = 0.3

    def __init__(self):
        # Shared by every shallow copy, so a run can record the instance it
        # actually executed on.
        self.instances = []

    def execute(self, params):
        self.instances.append(self)
        time.sleep(self.delay)
        return ToolResult.success(params["tag"])


class _SlowParallelTool(_SlowTool):
    name = "slow_parallel"
    parallel_safe = True


def _executor(tool):
    executor = object.__new__(AgentStreamExecutor)
    executor.tools = {tool.name: tool}
    executor.model = None
    executor.agent = None
    executor.cancel_event = None
    executor._record_tool_result = lambda *a, **kw: None
    executor._check_consecutive_failures = lambda *a, **kw: (False, None, False)
    executor._emit_event = lambda *a, **kw: None
    return executor


def _calls(name, count):
    return [
        {"id": f"call_{i}", "name": name, "arguments": {"tag": f"t{i}"}}
        for i in range(count)
    ]


def test_parallel_safe_calls_run_at_the_same_time():
    tool = _SlowParallelTool()
    executor = _executor(tool)

    started = time.time()
    results = executor._run_parallel_calls(_calls(tool.name, 3))
    elapsed = time.time() - started

    assert sorted(results) == ["call_0", "call_1", "call_2"]
    assert [results[k]["result"] for k in sorted(results)] == ["t0", "t1", "t2"]
    # Serial would be 3 * delay; anything under two delays can only be overlap.
    assert elapsed < tool.delay * 2


def test_each_parallel_call_gets_its_own_tool_instance():
    """The loop drives tools by assignment - it sets cancel_event and
    progress_callback before a call and clears them after - so two concurrent
    calls sharing one instance would disarm and cross-report each other."""
    tool = _SlowParallelTool()
    executor = _executor(tool)

    executor._run_parallel_calls(_calls(tool.name, 2))

    assert len(tool.instances) == 2
    first, second = tool.instances
    assert first is not second
    assert tool not in tool.instances


def test_ordinary_tools_keep_running_in_order():
    tool = _SlowTool()
    executor = _executor(tool)

    assert executor._run_parallel_calls(_calls(tool.name, 3)) == {}
    assert tool.instances == []


def test_a_lone_call_is_left_to_the_caller():
    """Nothing to overlap with, so it stays on the calling thread rather than
    paying for a pool and losing the loop's cancel checkpoint around it."""
    tool = _SlowParallelTool()
    executor = _executor(tool)

    assert executor._run_parallel_calls(_calls(tool.name, 1)) == {}
    assert tool.instances == []


def test_a_failing_call_does_not_take_its_siblings_down():
    class _Flaky(_SlowParallelTool):
        def execute(self, params):
            self.instances.append(self)
            if params["tag"] == "t0":
                raise RuntimeError("boom")
            return ToolResult.success(params["tag"])

    tool = _Flaky()
    executor = _executor(tool)

    results = executor._run_parallel_calls(_calls(tool.name, 2))

    assert len(results) == 2
    assert results["call_1"]["result"] == "t1"


def test_two_calls_are_in_flight_together():
    """Proves the overlap without leaning on wall-clock timing: the barrier
    only lets a call through once its sibling is inside as well, so were these
    run one after another both would fail on it."""
    barrier = threading.Barrier(2, timeout=3)
    threads = []

    class _Rendezvous(_SlowParallelTool):
        def execute(self, params):
            threads.append(threading.current_thread())
            barrier.wait()
            return ToolResult.success(params["tag"])

    executor = _executor(_Rendezvous())
    results = executor._run_parallel_calls(_calls("slow_parallel", 2))

    assert [r["status"] for r in results.values()] == ["success", "success"]
    assert threading.current_thread() not in threads
