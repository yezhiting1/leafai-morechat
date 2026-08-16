"""What survives of a sub agent's run once the stream is gone.

The report a sub agent wrote is the point of having spawned it, so a reloaded
page has to show it. Neither the file nor the readable conclusion is in the
stored conversation: the file was written a level down, and the conclusion is
deliberately kept out of the model's context. Both are rebuilt from the one
thing that is stored — the spawn call's result.
"""

import json

from channel.web import web_channel


def _subagent_step(results, is_error=False):
    return {
        "type": "tool",
        "name": "subagent",
        "arguments": {"goal": "research it"},
        "result": json.dumps({"results": results}),
        "is_error": is_error,
    }


def test_a_file_written_by_a_sub_agent_is_found_in_history(tmp_path, monkeypatch):
    report = tmp_path / "report.md"
    report.write_text("# Findings\n", encoding="utf-8")
    monkeypatch.setattr(
        "agent.protocol.artifact.get_workspace_root", lambda: str(tmp_path)
    )

    artifacts = web_channel._artifacts_from_steps([
        _subagent_step([{
            "task_index": 0,
            "subagent_type": "general-purpose",
            "status": "completed",
            "summary": "wrote it up",
            "files": [str(report)],
        }])
    ])

    assert [a["file_name"] for a in artifacts] == ["report.md"]


def test_write_steps_still_produce_their_cards(tmp_path, monkeypatch):
    note = tmp_path / "note.md"
    note.write_text("hi", encoding="utf-8")
    monkeypatch.setattr(
        "agent.protocol.artifact.get_workspace_root", lambda: str(tmp_path)
    )

    artifacts = web_channel._artifacts_from_steps([
        {"type": "tool", "name": "write", "arguments": {"path": str(note)}, "is_error": False}
    ])

    assert [a["file_name"] for a in artifacts] == ["note.md"]


def test_a_failed_spawn_contributes_no_files(tmp_path):
    artifacts = web_channel._artifacts_from_steps([
        _subagent_step([{"task_index": 0, "files": [str(tmp_path / "x.md")]}], is_error=True)
    ])

    assert artifacts == []


def test_a_step_whose_result_is_not_the_expected_shape_is_skipped():
    steps = [
        {"type": "tool", "name": "subagent", "result": "not json at all"},
        {"type": "tool", "name": "subagent", "result": json.dumps({"results": "wrong type"})},
        {"type": "tool", "name": "subagent"},
    ]

    assert web_channel._artifacts_from_steps(steps) == []
    web_channel._add_subagent_displays(steps)
    assert all("display" not in step for step in steps)


def test_a_reloaded_page_shows_the_report_rather_than_the_json():
    steps = [_subagent_step([{
        "task_index": 0,
        "subagent_type": "explore",
        "status": "completed",
        "summary": "Genspark raised $645M.",
        "duration_seconds": 125.88,
    }])]

    web_channel._add_subagent_displays(steps)

    assert steps[0]["display"].startswith("### explore · 2m 6s")
    assert "Genspark raised $645M." in steps[0]["display"]
    # The stored result stays as the model saw it.
    assert json.loads(steps[0]["result"])["results"][0]["summary"] == "Genspark raised $645M."


def test_a_session_recorded_before_files_were_listed_still_loads():
    """The stored result is whatever the tool returned at the time, so older
    sessions have no `files` key. They must read as "wrote nothing", not fail."""
    steps = [_subagent_step([{
        "task_index": 0,
        "subagent_type": "general-purpose",
        "status": "completed",
        "summary": "old news",
        "duration_seconds": 12.0,
    }])]

    assert web_channel._artifacts_from_steps(steps) == []
    web_channel._add_subagent_displays(steps)
    assert "old news" in steps[0]["display"]


def test_other_tools_are_left_alone():
    steps = [{"type": "tool", "name": "web_search", "result": json.dumps({"results": [1, 2]})}]

    web_channel._add_subagent_displays(steps)

    assert "display" not in steps[0]
