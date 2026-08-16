"""Regression tests for session rows resurrected by a late reply persist."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.memory.conversation_store import ConversationStore


def _store(tmpdir):
    return ConversationStore(Path(tmpdir) / "index.db")


def _titles(store):
    return {s["session_id"]: s["title"] for s in store.list_sessions()["sessions"]}


def test_reply_does_not_resurrect_deleted_session():
    """A reply landing after the user deleted the session must be dropped."""
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        sid = "session_ghost"

        # Turn starts: the user message is persisted eagerly.
        store.append_messages(
            sid,
            [{"role": "user", "content": [{"type": "text", "text": "打开文档"}]}],
            channel_type="web",
        )
        assert _titles(store) == {sid: "打开文档"}

        # User deletes the session while the agent is still running.
        store.clear_session(sid)

        # Reply lands afterwards: assistant + tool_result only, no user text.
        stored = store.append_messages(
            sid,
            [
                {"role": "assistant", "content": [{"type": "text", "text": "已打开"}]},
                {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]},
            ],
            channel_type="web",
            create_if_missing=False,
        )

        assert stored is False
        assert _titles(store) == {}


def test_reply_still_persists_for_a_live_session():
    """The guard must not drop replies for sessions that still exist."""
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        sid = "session_live"

        store.append_messages(
            sid,
            [{"role": "user", "content": [{"type": "text", "text": "打开文档"}]}],
            channel_type="web",
        )
        stored = store.append_messages(
            sid,
            [{"role": "assistant", "content": [{"type": "text", "text": "已打开"}]}],
            channel_type="web",
            create_if_missing=False,
        )

        assert stored is True
        assert _titles(store) == {sid: "打开文档"}
        assert store.list_sessions()["sessions"][0]["msg_count"] == 2


def test_new_session_is_still_created_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        store = _store(tmp)
        stored = store.append_messages(
            "session_new",
            [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            channel_type="web",
        )
        assert stored is True
        assert _titles(store) == {"session_new": "hi"}


if __name__ == "__main__":
    test_reply_does_not_resurrect_deleted_session()
    test_reply_still_persists_for_a_live_session()
    test_new_session_is_still_created_by_default()
    print("all passed")
