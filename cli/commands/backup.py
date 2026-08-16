"""Portable local backup and restore commands for CowAgent user data."""

import json
import os
import shutil
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional, Set

import click

from cli.utils import get_project_root


BACKUP_FORMAT = "cowagent-backup"
BACKUP_VERSION = 1
_SKIP_DIRS = {".git", "__pycache__", "tmp"}
_SKIP_FILES = {".DS_Store"}


def _data_root() -> Path:
    configured = os.environ.get("COW_DATA_DIR")
    return Path(configured).expanduser().resolve() if configured else Path(get_project_root()).resolve()


def _read_config(data_root: Path) -> dict:
    path = data_root / "config.json"
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _workspace_from_config(config: dict) -> Path:
    return Path(config.get("agent_workspace") or "~/cow").expanduser().resolve()


def _legacy_user_data_path(data_root: Path, config: dict) -> Path:
    appdata_dir = config.get("appdata_dir") or ""
    return (data_root / appdata_dir / "user_datas.pkl").resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([str(path.resolve()), str(root.resolve())]) == str(root.resolve())
    except (OSError, ValueError):
        return False


def _iter_workspace_files(workspace: Path, excluded: Set[Path]):
    if not workspace.is_dir():
        return
    for current, dirnames, filenames in os.walk(str(workspace), followlinks=False):
        current_path = Path(current)
        dirnames[:] = [
            name for name in dirnames
            if name not in _SKIP_DIRS and not (current_path / name).is_symlink()
        ]
        for name in filenames:
            path = current_path / name
            if name in _SKIP_FILES or name.endswith((".pyc", ".pyo")):
                continue
            if path.is_symlink() or path.resolve() in excluded:
                continue
            if path.is_file():
                yield path


def create_backup_archive(
    output: Path,
    data_root: Path,
    workspace: Path,
    excluded_paths: Optional[Iterable[Path]] = None,
) -> dict:
    """Create a portable archive containing config and the agent workspace."""
    output = Path(output).expanduser().resolve()
    data_root = Path(data_root).expanduser().resolve()
    workspace = Path(workspace).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    excluded = {Path(path).expanduser().resolve() for path in (excluded_paths or [])}
    excluded.add(output)

    config_path = data_root / "config.json"
    config = _read_config(data_root)
    legacy_path = _legacy_user_data_path(data_root, config)
    workspace_files = list(_iter_workspace_files(workspace, excluded))
    total_bytes = sum(path.stat().st_size for path in workspace_files)

    manifest = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "workspace_source": str(workspace),
        "contents": {
            "config": config_path.is_file(),
            "legacy_user_data": legacy_path.is_file(),
            "workspace_files": len(workspace_files),
            "workspace_bytes": total_bytes,
        },
    }

    temp_dir = Path(tempfile.mkdtemp(prefix="cowagent-backup-"))
    temp_archive = temp_dir / "backup.zip"
    try:
        with zipfile.ZipFile(
            str(temp_archive), "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
        ) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
            if config_path.is_file():
                archive.write(str(config_path), "data/config.json")
            if legacy_path.is_file():
                archive.write(str(legacy_path), "data/user_datas.pkl")
            for path in workspace_files:
                relative = path.relative_to(workspace).as_posix()
                archive.write(str(path), "workspace/" + relative)
        os.replace(str(temp_archive), str(output))
        try:
            os.chmod(str(output), stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)

    manifest["archive"] = str(output)
    return manifest


def _validate_archive(archive: zipfile.ZipFile) -> dict:
    names = {info.filename for info in archive.infolist()}
    if "manifest.json" not in names:
        raise ValueError("archive is missing manifest.json")
    try:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("archive manifest is invalid") from exc
    if manifest.get("format") != BACKUP_FORMAT or manifest.get("version") != BACKUP_VERSION:
        raise ValueError("unsupported CowAgent backup format or version")

    for info in archive.infolist():
        name = info.filename
        path = PurePosixPath(name)
        if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError(f"unsafe archive path: {name!r}")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise ValueError(f"symbolic links are not allowed in backups: {name!r}")
        if name != "manifest.json" and not name.startswith(("data/", "workspace/")):
            raise ValueError(f"unexpected archive entry: {name!r}")
    return manifest


def _extract_validated(archive: zipfile.ZipFile, destination: Path) -> None:
    for info in archive.infolist():
        target = destination.joinpath(*PurePosixPath(info.filename).parts)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info, "r") as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)


def _atomic_copy(source: Path, destination: Path, private: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=destination.name + ".", dir=str(destination.parent))
    os.close(fd)
    try:
        shutil.copy2(str(source), temp_name)
        os.replace(temp_name, str(destination))
        if private:
            try:
                os.chmod(str(destination), stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)


def restore_backup_archive(
    archive_path: Path,
    data_root: Path,
    workspace: Optional[Path] = None,
) -> dict:
    """Merge a validated backup into the selected data root and workspace."""
    archive_path = Path(archive_path).expanduser().resolve()
    data_root = Path(data_root).expanduser().resolve()
    current_config = _read_config(data_root)

    temp_dir = Path(tempfile.mkdtemp(prefix="cowagent-restore-"))
    try:
        with zipfile.ZipFile(str(archive_path), "r") as archive:
            manifest = _validate_archive(archive)
            _extract_validated(archive, temp_dir)

        archived_config_path = temp_dir / "data" / "config.json"
        archived_config = {}
        if archived_config_path.is_file():
            with archived_config_path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            if not isinstance(value, dict):
                raise ValueError("archived config.json must contain an object")
            archived_config = value

        if workspace is not None:
            target_workspace = Path(workspace).expanduser().resolve()
        elif current_config.get("agent_workspace"):
            target_workspace = _workspace_from_config(current_config)
        else:
            # Do not trust an archive-controlled absolute destination on a
            # fresh machine. Portable restores default to the standard local
            # workspace unless the operator supplies --workspace.
            target_workspace = Path("~/cow").expanduser().resolve()

        restored_config = dict(archived_config)
        if restored_config:
            restored_config["agent_workspace"] = str(target_workspace)
            appdata_dir = restored_config.get("appdata_dir") or ""
            if appdata_dir:
                archived_appdata = (data_root / appdata_dir).resolve()
                if not _is_within(archived_appdata, data_root):
                    # Keep legacy user data under the selected data root
                    # instead of writing to an archive-controlled path.
                    restored_config["appdata_dir"] = ""
            config_temp = temp_dir / "restored-config.json"
            with config_temp.open("w", encoding="utf-8") as handle:
                json.dump(restored_config, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            _atomic_copy(config_temp, data_root / "config.json", private=True)

        workspace_root = temp_dir / "workspace"
        restored_files = 0
        if workspace_root.is_dir():
            for source in _iter_workspace_files(workspace_root, set()):
                relative = source.relative_to(workspace_root)
                destination = target_workspace / relative
                if not _is_within(destination, target_workspace):
                    raise ValueError(f"unsafe workspace destination: {relative}")
                _atomic_copy(source, destination)
                restored_files += 1

        legacy_source = temp_dir / "data" / "user_datas.pkl"
        if legacy_source.is_file():
            effective_config = restored_config or current_config
            legacy_destination = _legacy_user_data_path(data_root, effective_config)
            _atomic_copy(legacy_source, legacy_destination, private=True)

        return {
            "manifest": manifest,
            "workspace": str(target_workspace),
            "workspace_files": restored_files,
            "config_restored": bool(restored_config),
            "legacy_user_data_restored": legacy_source.is_file(),
        }
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)


@click.command("backup")
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Output .zip path (default: ./cow-backup-<timestamp>.zip).",
)
def backup_command(output: Optional[Path]):
    """Back up config, persona, memory, skills, knowledge, and schedules."""
    data_root = _data_root()
    config = _read_config(data_root)
    workspace = _workspace_from_config(config)
    if output is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = Path.cwd() / f"cow-backup-{stamp}.zip"
    result = create_backup_archive(output, data_root, workspace)
    click.echo(click.style("✓ Backup created", fg="green"))
    click.echo(f"  Archive: {result['archive']}")
    click.echo(f"  Workspace files: {result['contents']['workspace_files']}")
    click.echo("  Keep this archive private: it may contain API keys and personal data.")


@click.command("restore")
@click.argument("archive", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--workspace",
    type=click.Path(file_okay=False, path_type=Path),
    help="Restore workspace files to this directory.",
)
@click.option("--yes", is_flag=True, help="Confirm overwriting matching files.")
def restore_command(archive: Path, workspace: Optional[Path], yes: bool):
    """Restore a backup without deleting unrelated destination files."""
    from cli.commands.process import _read_pid

    pid = _read_pid()
    if pid:
        raise click.ClickException(
            f"CowAgent is running (PID: {pid}). Run 'cow stop' before restoring."
        )
    if not yes:
        click.confirm(
            "Restore this archive and overwrite matching config/workspace files?",
            abort=True,
        )

    data_root = _data_root()
    current_config = _read_config(data_root)
    current_workspace = _workspace_from_config(current_config)
    has_current_data = (data_root / "config.json").is_file() or current_workspace.is_dir()
    if has_current_data:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        rollback = archive.resolve().parent / f"cow-pre-restore-{stamp}.zip"
        create_backup_archive(
            rollback,
            data_root,
            current_workspace,
            excluded_paths={archive.resolve()},
        )
        click.echo(f"Rollback backup: {rollback}")

    result = restore_backup_archive(archive, data_root, workspace)
    click.echo(click.style("✓ Backup restored", fg="green"))
    click.echo(f"  Workspace: {result['workspace']}")
    click.echo(f"  Restored files: {result['workspace_files']}")
