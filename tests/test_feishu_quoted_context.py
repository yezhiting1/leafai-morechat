import json
from types import SimpleNamespace

from channel.feishu.feishu_message import FeishuMessage


def _event(parent_id="om_parent", text="What does this mean?"):
    return {
        "app_id": "cli_bot",
        "sender": {"sender_id": {"open_id": "ou_user"}},
        "message": {
            "message_id": "om_child",
            "parent_id": parent_id,
            "chat_id": "oc_chat",
            "message_type": "text",
            "content": json.dumps({"text": text}),
        },
    }


def _response(body, status_code=200):
    return SimpleNamespace(status_code=status_code, json=lambda: body)


def test_text_reply_fetches_parent_without_replacing_user_message(monkeypatch):
    response = _response(
        {
            "code": 0,
            "data": {
                "items": [
                    {
                        "msg_type": "text",
                        "body": {"content": json.dumps({"text": "Original answer"})},
                    }
                ]
            },
        }
    )
    monkeypatch.setattr(
        "channel.feishu.feishu_message.requests.get", lambda **kwargs: response
    )

    message = FeishuMessage(_event(), access_token="tenant-token")

    assert message.content == "What does this mean?"
    assert message.quoted_content == "Original answer"
    assert message.content_with_quote() == (
        "[Quoted message]\nOriginal answer\n[/Quoted message]\n\n"
        "What does this mean?"
    )


def test_post_reply_extracts_title_and_text(monkeypatch):
    post = {
        "title": "Release note",
        "content": [
            [
                {"tag": "text", "text": "Fixed the scheduler."},
                {"tag": "a", "text": "Details", "href": "https://example.com"},
            ]
        ],
    }
    response = _response(
        {
            "code": 0,
            "data": {
                "items": [
                    {"msg_type": "post", "body": {"content": json.dumps(post)}}
                ]
            },
        }
    )
    monkeypatch.setattr(
        "channel.feishu.feishu_message.requests.get", lambda **kwargs: response
    )

    message = FeishuMessage(_event(), access_token="tenant-token")

    assert message.quoted_content == (
        "Release note\nFixed the scheduler.\nDetails (https://example.com)"
    )


def test_quote_fetch_failure_keeps_current_message_usable(monkeypatch):
    def fail(**kwargs):
        raise TimeoutError("network timeout")

    monkeypatch.setattr("channel.feishu.feishu_message.requests.get", fail)

    message = FeishuMessage(_event(), access_token="tenant-token")

    assert message.quoted_content == ""
    assert message.content_with_quote() == "What does this mean?"


def test_message_without_parent_does_not_fetch(monkeypatch):
    def unexpected(**kwargs):
        raise AssertionError("quote API should not be called")

    monkeypatch.setattr("channel.feishu.feishu_message.requests.get", unexpected)

    message = FeishuMessage(_event(parent_id=""), access_token="tenant-token")

    assert message.quoted_content == ""
    assert message.content_with_quote() == "What does this mean?"
