"""Tests for portable CowAgent backup archives."""

import json
import zipfile
from pathlib import Path

import pytest

from cli.commands.backup import create_backup_archive, restore_backup_archive


def _write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_backup_restore_round_trip(tmp_path):
    source_data = tmp_path / "source-data"
    source_workspace = tmp_path / "source-workspace"
    _write_json(source_data / "config.json", {
        "agent_workspace": str(source_workspace),
        "open_ai_api_key": "secret-value",
    })
    (source_workspace / "memory").mkdir(parents=True)
    (source_workspace / "scheduler").mkdir()
    (source_workspace / "knowledge").mkdir()
    (source_workspace / "USER.md").write_text("# User\n", encoding="utf-8")
    (source_workspace / "MEMORY.md").write_text("remember this\n", encoding="utf-8")
    (source_workspace / "memory" / "2026-07-17.md").write_text("daily\n", encoding="utf-8")
    (source_workspace / "scheduler" / "tasks.json").write_text("{}\n", encoding="utf-8")
    (source_workspace / "knowledge" / "index.md").write_text("# Index\n", encoding="utf-8")
    (source_workspace / "tmp").mkdir()
    (source_workspace / "tmp" / "scratch.txt").write_text("skip", encoding="utf-8")

    archive = tmp_path / "cow-backup.zip"
    summary = create_backup_archive(archive, source_data, source_workspace)
    assert summary["contents"]["workspace_files"] == 5
    assert archive.exists()

    target_data = tmp_path / "target-data"
    target_workspace = tmp_path / "target-workspace"
    result = restore_backup_archive(archive, target_data, target_workspace)

    restored_config = json.loads((target_data / "config.json").read_text(encoding="utf-8"))
    assert restored_config["agent_workspace"] == str(target_workspace.resolve())
    assert restored_config["open_ai_api_key"] == "secret-value"
    assert (target_workspace / "MEMORY.md").read_text(encoding="utf-8") == "remember this\n"
    assert (target_workspace / "scheduler" / "tasks.json").exists()
    assert (target_workspace / "knowledge" / "index.md").exists()
    assert not (target_workspace / "tmp" / "scratch.txt").exists()
    assert result["workspace_files"] == 5


def test_restore_merges_without_deleting_unrelated_files(tmp_path):
    source_data = tmp_path / "source-data"
    source_workspace = tmp_path / "source-workspace"
    _write_json(source_data / "config.json", {"agent_workspace": str(source_workspace)})
    source_workspace.mkdir()
    (source_workspace / "MEMORY.md").write_text("new\n", encoding="utf-8")
    archive = tmp_path / "cow-backup.zip"
    create_backup_archive(archive, source_data, source_workspace)

    target_workspace = tmp_path / "target-workspace"
    target_workspace.mkdir()
    (target_workspace / "MEMORY.md").write_text("old\n", encoding="utf-8")
    (target_workspace / "keep.txt").write_text("keep\n", encoding="utf-8")

    restore_backup_archive(archive, tmp_path / "target-data", target_workspace)
    assert (target_workspace / "MEMORY.md").read_text(encoding="utf-8") == "new\n"
    assert (target_workspace / "keep.txt").read_text(encoding="utf-8") == "keep\n"


def test_restore_rejects_path_traversal(tmp_path):
    archive = tmp_path / "malicious.zip"
    manifest = {"format": "cowagent-backup", "version": 1}
    with zipfile.ZipFile(str(archive), "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        output.writestr("workspace/../../escape.txt", "nope")

    with pytest.raises(ValueError, match="unsafe archive path"):
        restore_backup_archive(archive, tmp_path / "data", tmp_path / "workspace")


def test_fresh_restore_ignores_archive_controlled_destinations(tmp_path, monkeypatch):
    source_data = tmp_path / "source-data"
    source_workspace = tmp_path / "source-workspace"
    outside_appdata = tmp_path / "outside-appdata"
    archive_workspace = tmp_path / "archive-controlled-workspace"
    _write_json(source_data / "config.json", {
        "agent_workspace": str(archive_workspace),
        "appdata_dir": str(outside_appdata),
    })
    source_workspace.mkdir()
    (source_workspace / "MEMORY.md").write_text("portable\n", encoding="utf-8")
    outside_appdata.mkdir()
    (outside_appdata / "user_datas.pkl").write_bytes(b"legacy")
    archive = tmp_path / "cow-backup.zip"
    create_backup_archive(archive, source_data, source_workspace)

    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(fake_home))
    target_data = tmp_path / "target-data"
    result = restore_backup_archive(archive, target_data)

    assert result["workspace"] == str((fake_home / "cow").resolve())
    assert (fake_home / "cow" / "MEMORY.md").exists()
    assert not archive_workspace.exists()
    assert (target_data / "user_datas.pkl").read_bytes() == b"legacy"
    restored_config = json.loads((target_data / "config.json").read_text(encoding="utf-8"))
    assert restored_config["appdata_dir"] == ""
