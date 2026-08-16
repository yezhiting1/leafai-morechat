import json
import logging
import threading
import time
from types import SimpleNamespace

from bridge.context import Context
from bridge.reply import Reply, ReplyType
from agent.memory.conversation_store import ConversationStore
from channel.web import web_channel


WebChannel = dict(zip(
    web_channel.WebChannel.__code__.co_freevars,
    (cell.cell_contents for cell in web_channel.WebChannel.__closure__),
))["cls"]


def _channel(max_events=5000, max_bytes=4 * 1024 * 1024):
    channel = SimpleNamespace(
        sse_streams={},
        _sse_streams_lock=threading.RLock(),
        request_to_session={},
        request_to_agent={},
        SSE_REPLAY_MAX_EVENTS=max_events,
        SSE_REPLAY_MAX_BYTES=max_bytes,
        SSE_POST_DONE_TAIL_SECONDS=60,
        SSE_COMPLETED_TTL_SECONDS=60,
        SSE_IDLE_TIMEOUT_SECONDS=1800,
    )
    channel._publish_sse_event = lambda rid, event: WebChannel._publish_sse_event(
        channel, rid, event
    )
    channel._drop_sse_request = lambda rid: WebChannel._drop_sse_request(
        channel, rid
    )
    return channel


def _add_stream(channel, request_id):
    channel.sse_streams[request_id] = web_channel.SSEStreamState()


def _events(chunks):
    events, ids = [], []
    for chunk in chunks:
        for line in chunk.decode("utf-8").splitlines():
            if line.startswith("id: "):
                ids.append(int(line[4:]))
            elif line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return ids, events


def test_explicit_and_native_cursors_use_the_furthest_progress():
    assert web_channel._parse_sse_cursor("0", "12") == 12
    assert web_channel._parse_sse_cursor("15", "12") == 15
    assert web_channel._parse_sse_cursor("invalid", "7") == 7


def test_history_exposes_seq_for_merged_assistant_bubble(tmp_path):
    store = ConversationStore(tmp_path / "history.db")
    store.append_messages("session", [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": [{
            "type": "tool_use", "id": "tool-1", "name": "read", "input": {}
        }]},
        {"role": "user", "content": [{
            "type": "tool_result", "tool_use_id": "tool-1", "content": "ok"
        }]},
        {"role": "assistant", "content": "answer", "extras": {
            "audio": {"url": "/uploads/reply.wav"}
        }},
    ])

    messages = store.load_history_page("session")["messages"]

    assert [(item["role"], item["_seq"]) for item in messages] == [
        ("user", 0), ("assistant", 3)
    ]
    assert messages[-1]["extras"]["audio"]["url"] == "/uploads/reply.wav"


def test_reconnect_replays_only_events_after_cursor():
    channel = _channel()
    _add_stream(channel, "req")
    for content in ("a", "b", "c"):
        channel._publish_sse_event("req", {"type": "delta", "content": content})
    channel._publish_sse_event("req", {"type": "done", "content": "abc"})
    channel._publish_sse_event("req", {"type": "stream_end"})

    ids, events = _events(WebChannel.stream_response(channel, "req", after_seq=2))

    assert ids == [3, 4, 5]
    assert [event["seq"] for event in events] == [3, 4, 5]
    assert [event["type"] for event in events] == ["delta", "done", "stream_end"]


def test_delivery_interruption_does_not_remove_event_from_log():
    channel = _channel()
    _add_stream(channel, "req")
    channel._publish_sse_event("req", {"type": "delta", "content": "first"})
    channel._publish_sse_event("req", {"type": "delta", "content": "second"})

    first_connection = WebChannel.stream_response(channel, "req")
    ids, _ = _events([next(first_connection)])
    assert ids == [1]
    first_connection.close()

    channel._publish_sse_event("req", {"type": "done", "content": "firstsecond"})
    channel._publish_sse_event("req", {"type": "stream_end"})
    ids, events = _events(WebChannel.stream_response(channel, "req", after_seq=0))

    assert ids == [1, 2, 3, 4]
    assert [event["seq"] for event in events] == [1, 2, 3, 4]


def test_done_and_voice_attachment_are_replayable_until_stream_end():
    channel = _channel()
    _add_stream(channel, "req")
    channel._publish_sse_event("req", {"type": "done", "content": "answer"})
    channel._publish_sse_event("req", {"type": "voice_attach", "url": "/audio.mp3"})
    channel._publish_sse_event("req", {"type": "stream_end"})

    _, events = _events(WebChannel.stream_response(channel, "req", after_seq=1))

    assert [event["type"] for event in events] == ["voice_attach", "stream_end"]


def test_requests_have_independent_sequences_and_logs():
    channel = _channel()
    _add_stream(channel, "a")
    _add_stream(channel, "b")
    channel._publish_sse_event("a", {"type": "delta", "content": "A"})
    channel._publish_sse_event("b", {"type": "delta", "content": "B"})
    channel._publish_sse_event("a", {"type": "stream_end"})
    channel._publish_sse_event("b", {"type": "stream_end"})

    _, a_events = _events(WebChannel.stream_response(channel, "a"))
    _, b_events = _events(WebChannel.stream_response(channel, "b"))

    assert [event.get("content") for event in a_events if "content" in event] == ["A"]
    assert [event.get("content") for event in b_events if "content" in event] == ["B"]
    assert a_events[0]["seq"] == b_events[0]["seq"] == 1


def test_concurrent_readers_each_receive_the_complete_log():
    channel = _channel()
    _add_stream(channel, "req")
    channel._publish_sse_event("req", {"type": "delta", "content": "a"})

    readers_ready = threading.Barrier(3)
    results = [None, None]

    def read_stream(index):
        chunks = []
        stream = WebChannel.stream_response(channel, "req")
        chunks.append(next(stream))
        readers_ready.wait()
        chunks.extend(stream)
        results[index] = _events(chunks)

    readers = [
        threading.Thread(target=read_stream, args=(index,))
        for index in range(2)
    ]
    for reader in readers:
        reader.start()
    readers_ready.wait(timeout=2)

    channel._publish_sse_event("req", {"type": "delta", "content": "b"})
    channel._publish_sse_event("req", {"type": "done", "content": "ab"})
    channel._publish_sse_event("req", {"type": "stream_end"})

    for reader in readers:
        reader.join(timeout=2)
        assert not reader.is_alive()

    first_ids, first_events = results[0]
    second_ids, second_events = results[1]
    assert first_ids == second_ids == [1, 2, 3, 4]
    assert [item["type"] for item in first_events] == [
        "delta", "delta", "done", "stream_end"
    ]
    assert first_events == second_events


def test_expired_cursor_requires_resync_when_count_limit_evicts_events():
    channel = _channel(max_events=2)
    _add_stream(channel, "req")
    for content in ("a", "b", "c"):
        channel._publish_sse_event("req", {"type": "delta", "content": content})

    ids, events = _events(WebChannel.stream_response(channel, "req", after_seq=0))

    assert ids == []
    assert events == [{
        "type": "resync_required",
        "reason": "event_cursor_expired",
        "after_seq": 0,
        "first_available_seq": 2,
    }]


def test_byte_limit_also_evicts_old_events():
    channel = _channel(max_events=100, max_bytes=160)
    _add_stream(channel, "req")
    for _ in range(4):
        channel._publish_sse_event("req", {"type": "delta", "content": "x" * 80})

    state = channel.sse_streams["req"]
    assert len(state.events) == 1
    assert state.events[0][0]["seq"] == 4


def test_late_event_drop_is_visible_in_logs(caplog):
    channel = _channel()
    _add_stream(channel, "req")
    channel._publish_sse_event("req", {"type": "stream_end"})

    with caplog.at_level(logging.WARNING):
        published = channel._publish_sse_event(
            "req", {"type": "voice_attach", "url": "/audio.mp3"}
        )

    assert not published
    assert "dropped SSE event for complete stream req" in caplog.text


def test_overdue_done_is_bounded_by_stream_end():
    channel = _channel()
    _add_stream(channel, "req")
    channel._publish_sse_event("req", {"type": "done", "content": "answer"})
    state = channel.sse_streams["req"]
    state.main_done_at = time.time() - 61

    _, events = _events(WebChannel.stream_response(channel, "req"))

    assert [item["type"] for item in events] == ["done", "stream_end"]
    assert state.stream_complete


def test_janitor_finalizes_done_then_reclaims_completed_log():
    channel = _channel()
    _add_stream(channel, "req")
    channel._publish_sse_event("req", {"type": "done", "content": "answer"})
    state = channel.sse_streams["req"]
    now = time.time()
    state.main_done_at = now - 61

    assert WebChannel._sweep_sse_streams(channel, now) == 0
    assert state.stream_complete

    state.completed_at = now - 61
    assert WebChannel._sweep_sse_streams(channel, now) == 1
    assert "req" not in channel.sse_streams


def _send_channel(tts_pending=False):
    channel = _channel()
    channel.NOT_SUPPORT_REPLYTYPE = []
    channel.session_queues = {}
    channel.request_to_session["req"] = "session"
    channel.request_to_agent["req"] = "agent"
    channel._session_queue_key = lambda session_id, agent_id=None: session_id
    channel._fetch_latest_pair_seqs = lambda *args: {
        "user_seq": 1, "bot_seq": 2
    }
    channel._maybe_dispatch_auto_tts = lambda *args: tts_pending
    _add_stream(channel, "req")
    context = Context(kwargs={
        "request_id": "req", "agent_id": "agent", "session_id": "session"
    })
    return channel, context


def test_duplicate_file_does_not_close_text_stream_waiting_for_tts():
    channel, context = _send_channel(tts_pending=True)
    WebChannel.send(channel, Reply(ReplyType.TEXT, "answer"), context)
    state = channel.sse_streams["req"]
    assert state.main_done
    assert not state.stream_complete

    WebChannel.send(channel, Reply(ReplyType.FILE, "file://result.txt"), context)

    assert not state.stream_complete
    assert [item[0]["type"] for item in state.events] == ["done"]


def test_duplicate_file_without_text_does_not_end_an_unfinished_stream():
    channel, context = _send_channel()

    WebChannel.send(channel, Reply(ReplyType.FILE, "file://result.txt"), context)

    state = channel.sse_streams["req"]
    assert not state.main_done
    assert not state.stream_complete
    assert list(state.events) == []


def test_file_with_own_text_publishes_done_before_stream_end():
    channel, context = _send_channel()
    reply = Reply(ReplyType.FILE, "file://result.txt")
    reply.text_content = "answer with file"

    WebChannel.send(channel, reply, context)

    state = channel.sse_streams["req"]
    assert [item[0]["type"] for item in state.events] == ["done", "stream_end"]
