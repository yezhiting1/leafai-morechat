# encoding:utf-8
"""
Unit tests for on-demand MCP tool retrieval.

Covers the invariants the maintainer asked for in the feature review:
  * below threshold / degrade paths behave exactly like today (full injection),
  * the injected MCP tool set only ever grows within a run (never shrinks),
plus the pure selection helpers (query building, cosine, top-k, fallbacks).
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tools.mcp.tool_retrieval import (
    build_retrieval_query,
    cosine_similarity,
    select_mcp_tools,
)
from agent.tools.mcp.mcp_tool import McpTool


def _mcp_tool(name, description=""):
    """Build a real McpTool without needing a live MCP client."""
    return McpTool(
        client=None,
        tool_schema={"name": name, "description": description, "inputSchema": {}},
        server_name="test-server",
    )


class _FakeBuiltinTool:
    """Minimal stand-in for a built-in BaseTool."""

    def __init__(self, name):
        self.name = name
        self.description = f"builtin {name}"
        self.params = {"type": "object", "properties": {}}

    def get_json_schema(self):
        return {}


class _FakeToolManager:
    """Controls the vectors/query embeddings seen by the executor."""

    def __init__(self, tool_vectors, query_vectors):
        self._tool_vectors = tool_vectors
        self._query_vectors = list(query_vectors)
        self._call = 0

    def get_mcp_tool_vectors(self):
        return dict(self._tool_vectors)

    def embed_query(self, text):
        if self._call < len(self._query_vectors):
            vec = self._query_vectors[self._call]
        else:
            vec = self._query_vectors[-1] if self._query_vectors else None
        self._call += 1
        return vec


# --------------------------------------------------------------------------
# Pure helper: build_retrieval_query
# --------------------------------------------------------------------------

class TestBuildRetrievalQuery(unittest.TestCase):

    def test_empty_messages(self):
        self.assertEqual(build_retrieval_query([]), "")

    def test_extracts_text_blocks(self):
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "hello"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "world"}]},
        ]
        self.assertEqual(build_retrieval_query(messages), "hello\nworld")

    def test_skips_tool_result_and_tool_use(self):
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "do it"}]},
            {"role": "assistant", "content": [
                {"type": "tool_use", "name": "read", "input": {}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "content": "huge payload " * 100},
            ]},
        ]
        self.assertEqual(build_retrieval_query(messages), "do it")

    def test_string_content_supported(self):
        messages = [{"role": "user", "content": "plain string"}]
        self.assertEqual(build_retrieval_query(messages), "plain string")

    def test_respects_recent_window(self):
        messages = [
            {"role": "user", "content": [{"type": "text", "text": f"m{i}"}]}
            for i in range(10)
        ]
        # Only the last 3 messages should be kept.
        self.assertEqual(build_retrieval_query(messages, max_messages=3), "m7\nm8\nm9")


# --------------------------------------------------------------------------
# Pure helper: cosine_similarity
# --------------------------------------------------------------------------

class TestCosineSimilarity(unittest.TestCase):

    def test_identical_vectors(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)

    def test_orthogonal_vectors(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_degenerate_inputs(self):
        self.assertEqual(cosine_similarity([], [1.0]), 0.0)
        self.assertEqual(cosine_similarity([0.0, 0.0], [1.0, 1.0]), 0.0)
        self.assertEqual(cosine_similarity([1.0], [1.0, 0.0]), 0.0)


# --------------------------------------------------------------------------
# Pure helper: select_mcp_tools
# --------------------------------------------------------------------------

class TestSelectMcpTools(unittest.TestCase):

    def setUp(self):
        self.vectors = {
            "a": [1.0, 0.0, 0.0],
            "b": [0.0, 1.0, 0.0],
            "c": [0.0, 0.0, 1.0],
            "d": [0.9, 0.1, 0.0],
        }

    def test_returns_top_k(self):
        selected = select_mcp_tools([1.0, 0.0, 0.0], self.vectors, top_k=2,
                                    already_selected=set())
        self.assertEqual(selected, {"a", "d"})

    def test_union_only_grows_across_turns(self):
        """The core invariant: a later turn never drops earlier selections."""
        first = select_mcp_tools([1.0, 0.0, 0.0], self.vectors, top_k=2,
                                 already_selected=set())
        second = select_mcp_tools([0.0, 1.0, 0.0], self.vectors, top_k=1,
                                  already_selected=first)
        self.assertTrue(first.issubset(second))
        self.assertIn("b", second)

    def test_none_query_vector_falls_back(self):
        self.assertIsNone(select_mcp_tools(None, self.vectors, top_k=2,
                                           already_selected=set()))

    def test_empty_index_falls_back(self):
        self.assertIsNone(select_mcp_tools([1.0, 0.0, 0.0], {}, top_k=2,
                                           already_selected=set()))

    def test_dimension_mismatch_falls_back(self):
        mismatched = {"a": [1.0, 0.0]}  # dim 2 vs query dim 3
        self.assertIsNone(select_mcp_tools([1.0, 0.0, 0.0], mismatched, top_k=2,
                                           already_selected=set()))


# --------------------------------------------------------------------------
# Executor integration: AgentStream._select_tools_for_injection
# --------------------------------------------------------------------------

class TestSelectToolsForInjection(unittest.TestCase):
    """Exercise the executor decision without spinning up a real agent."""

    def _make_self(self, mcp_count, builtins=("read", "write", "bash")):
        from types import SimpleNamespace
        tools = {}
        for name in builtins:
            tools[name] = _FakeBuiltinTool(name)
        for i in range(mcp_count):
            name = f"mcp_{i}"
            tools[name] = _mcp_tool(name, f"tool number {i}")
        return SimpleNamespace(
            tools=tools,
            messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            _retrieved_mcp_names=set(),
        )

    def _call(self, fake_self):
        from agent.protocol.agent_stream import AgentStreamExecutor
        return AgentStreamExecutor._select_tools_for_injection(fake_self)

    def _conf(self, **overrides):
        cfg = {
            "mcp_tool_retrieval_enabled": True,
            "mcp_tool_retrieval_threshold": 20,
            "mcp_tool_retrieval_top_k": 2,
        }
        cfg.update(overrides)
        return cfg

    def test_disabled_returns_all_tools(self):
        fake = self._make_self(mcp_count=50)
        with patch("config.conf", return_value=self._conf(mcp_tool_retrieval_enabled=False)):
            result = self._call(fake)
        self.assertEqual(len(result), len(fake.tools))

    def test_below_threshold_returns_all_tools(self):
        """Maintainer scenario 1: below threshold → behavior unchanged."""
        fake = self._make_self(mcp_count=5)  # <= threshold 20
        with patch("config.conf", return_value=self._conf()):
            result = self._call(fake)
        self.assertEqual(len(result), len(fake.tools))

    def test_degrade_no_provider_returns_all_tools(self):
        """Maintainer scenario 2: no embedding provider → full injection."""
        fake = self._make_self(mcp_count=25)  # > threshold
        fake_tm = _FakeToolManager(tool_vectors={}, query_vectors=[None])
        with patch("config.conf", return_value=self._conf()), \
             patch("agent.tools.ToolManager", return_value=fake_tm):
            result = self._call(fake)
        self.assertEqual(len(result), len(fake.tools))

    def test_builtins_always_injected_and_set_grows(self):
        """Maintainer scenario 3: multi-turn MCP set only grows; builtins stay."""
        fake = self._make_self(mcp_count=25)
        # Deterministic vectors: mcp_0 wins turn 1, mcp_1 wins turn 2.
        tool_vectors = {f"mcp_{i}": [0.1, 0.1, 0.1] for i in range(25)}
        tool_vectors["mcp_0"] = [1.0, 0.0, 0.0]
        tool_vectors["mcp_1"] = [0.0, 1.0, 0.0]
        fake_tm = _FakeToolManager(
            tool_vectors=tool_vectors,
            query_vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        )
        with patch("config.conf", return_value=self._conf(mcp_tool_retrieval_top_k=1)), \
             patch("agent.tools.ToolManager", return_value=fake_tm):
            result1 = self._call(fake)
            names1 = {t.name for t in result1}
            result2 = self._call(fake)
            names2 = {t.name for t in result2}

        # Built-in tools present in both turns.
        for b in ("read", "write", "bash"):
            self.assertIn(b, names1)
            self.assertIn(b, names2)
        # Turn 1 selected mcp_0; turn 2 must still contain it (only-grows).
        self.assertIn("mcp_0", names1)
        self.assertIn("mcp_0", names2)
        self.assertIn("mcp_1", names2)
        self.assertTrue(fake._retrieved_mcp_names >= {"mcp_0", "mcp_1"})


if __name__ == "__main__":
    unittest.main()
