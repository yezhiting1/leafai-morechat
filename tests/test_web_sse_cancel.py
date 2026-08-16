"""SSE teardown after a user cancel."""

import json
import threading
import time
from types import SimpleNamespace

from channel.web import web_channel


WebChannel = dict(zip(
    web_channel.WebChannel.__code__.co_freevars,
    (cell.cell_contents for cell in web_channel.WebChannel.__closure__),
))["cls"]


def _fake_channel():
    channel = SimpleNamespace(
        sse_streams={},
        _sse_streams_lock=threading.RLock(),
        request_to_session={},
        request_to_agent={},
        SSE_REPLAY_MAX_EVENTS=5000,
        SSE_REPLAY_MAX_BYTES=4 * 1024 * 1024,
        SSE_POST_DONE_TAIL_SECONDS=60,
    )
    channel._drop_sse_request = lambda rid: WebChannel._drop_sse_request(channel, rid)
    channel._publish_sse_event = lambda rid, event: WebChannel._publish_sse_event(
        channel, rid, event
    )
    return channel


def _events(chunks):
    out = []
    for chunk in chunks:
        for line in chunk.decode("utf-8").splitlines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


def test_events_after_cancel_still_reach_the_client():
    channel = _fake_channel()
    request_id = "req-1"
    channel.sse_streams[request_id] = web_channel.SSEStreamState()
    channel._publish_sse_event(
        request_id, {"type": "cancelled", "content": "Cancelled"}
    )

    def late_producer():
        time.sleep(4)
        channel._publish_sse_event(request_id, {
            "type": "tool_end", "tool_call_id": "t1", "status": "success"
        })
        channel._publish_sse_event(
            request_id, {"type": "done", "content": "partial answer"}
        )
        channel._publish_sse_event(request_id, {"type": "stream_end"})

    threading.Thread(target=late_producer, daemon=True).start()
    events = _events(WebChannel.stream_response(channel, request_id))

    assert [event["type"] for event in events] == [
        "cancelled", "tool_end", "done", "stream_end"
    ]
    assert request_id in channel.sse_streams


def test_unfinished_run_does_not_hold_closed_client():
    channel = _fake_channel()
    request_id = "req-2"
    channel.sse_streams[request_id] = web_channel.SSEStreamState()
    channel._publish_sse_event(
        request_id, {"type": "cancelled", "content": "Cancelled"}
    )

    generator = WebChannel.stream_response(channel, request_id)
    event = _events([next(generator)])[0]
    assert event["type"] == "cancelled"
    assert event["seq"] == 1
    generator.close()
