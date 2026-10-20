"""Steam-like managed game layout, linking, and per-game backups."""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile
from typing import Any

from .library import atomic_write

_LAYOUT = "UmuLibrary/umuapps"
_MANIFEST_PREFIX = "appmanifest_"
_MAX_MANIFEST = 256 * 1024


def _safe_folder(title: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", title).strip().rstrip(".")
    value = re.sub(r"\s+", " ", value)
    if not value or value in {".", ".."}:
        raise ValueError("Game title cannot be used as a managed library folder.")
    return value[:120]


def manifest_key(game: dict[str, Any]) -> str:
    app_id = game.get("metadata_app_id")
    return str(app_id) if isinstance(app_id, int) and app_id > 0 else str(game["id"])


def layout_root(drive_root: str | Path) -> Path:
    root = Path(drive_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Selected library drive is unavailable.")
    return root.joinpath(*_LAYOUT.split("/"))


def _managed_paths(drive_root: str | Path, game: dict[str, Any]) -> tuple[Path, Path, Path, Path]:
    base = layout_root(drive_root)
    folder = _safe_folder(str(game.get("title") or ""))
    content = base / "common" / folder
    prefix = base / "compatdata" / folder
    manifest = base / f"{_MANIFEST_PREFIX}{manifest_key(game)}.json"
    return base, content, prefix, manifest


def _validate_source(root: str | Path, executable: str | Path) -> tuple[Path, Path, Path]:
    source = Path(root).expanduser().resolve(strict=True)
    launcher = Path(executable).expanduser().resolve(strict=True)
    if not source.is_dir():
        raise ValueError("Choose the installed game's root directory.")
    if not launcher.is_file():
        raise ValueError("Choose an existing main game launcher executable.")
    try:
        relative = launcher.relative_to(source)
    except ValueError as error:
        raise ValueError("The launcher executable must be inside the selected game root.") from error
    return source, launcher, relative


def _validate_proton(proton: str | Path) -> str:
    path = Path(proton).expanduser().resolve(strict=True)
    if not path.is_dir() or not (path / "proton").is_file():
        raise ValueError("Choose an installed Proton compatibility layer.")
    return str(path)


def _manifest(game: dict[str, Any], content: Path, prefix: Path, executable_relative: Path, proton: str) -> dict[str, Any]:
    return {
        "format": 1,
        "game_id": game["id"],
        "title": game["title"],
        "steam_app_id": game.get("metadata_app_id"),
        "content_directory": (Path("common") / content.name).as_posix(),
        "launcher_relative_path": executable_relative.as_posix(),
        "compatdata_directory": (Path("compatdata") / prefix.name).as_posix(),
        "proton": proton,
    }


def _write_manifest(path: Path, data: dict[str, Any]) -> None:
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))


def link_game(
    game: dict[str, Any], *, drive_root: str | Path, source_root: str | Path,
    launcher: str | Path, proton: str | Path, move: bool,
) -> dict[str, Any]:
    """Copy or move a user-installed game into the selected managed library."""
    if type(move) is not bool:
        raise ValueError("Choose whether to copy or move the installed game.")
    source, _launcher, executable_relative = _validate_source(source_root, launcher)
    proton_path = _validate_proton(proton)
    base, destination, prefix, manifest_path = _managed_paths(drive_root, game)
    if destination.exists() or manifest_path.exists() or (prefix.exists() and not prefix.is_dir()):
        raise ValueError("This game already has managed content on the selected drive.")
    if destination == source or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("The managed library must be separate from the selected game root.")
    base.mkdir(parents=True, exist_ok=True)
    (base / "common").mkdir(exist_ok=True)
    (base / "compatdata").mkdir(exist_ok=True)
    staging = destination.with_name("." + destination.name + ".linking-" + str(os.getpid()))
    if staging.exists():
        raise RuntimeError("A previous game linking operation is still present. Review the managed library folder.")
    try:
        if move:
            shutil.move(str(source), str(staging))
        else:
            shutil.copytree(source, staging, symlinks=True)
        staging.rename(destination)
        prefix.mkdir(mode=0o700, exist_ok=True)
        manifest = _manifest(game, destination, prefix, executable_relative, proton_path)
        _write_manifest(manifest_path, manifest)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "root": str(destination),
        "executable": str(destination / executable_relative),
        "working_dir": str((destination / executable_relative).parent),
        "prefix": str(prefix),
        "proton": proton_path,
        "manifest": str(manifest_path),
        "mode": "move" if move else "copy",
    }

def unlink_game(game: dict[str, Any]) -> None:
    """Remove the managed manifest after its content is uninstalled; keep compatdata."""
    installation = game.get("installation", {})
    root = Path(installation.get("root", "")).expanduser().resolve()
    manifest = Path(installation.get("manifest", "")).expanduser().resolve(strict=True)
    base = manifest.parent
    if root.parent != base / "common" or manifest.name != f"{_MANIFEST_PREFIX}{manifest_key(game)}.json":
        raise ValueError("Only a matching managed game manifest can be removed.")
    manifest.unlink()


def _linked_paths(game: dict[str, Any]) -> tuple[Path, Path, Path]:
    installation = game.get("installation", {})
    root = Path(installation.get("root", "")).expanduser().resolve(strict=True)
    prefix = Path(installation.get("prefix", game.get("launch", {}).get("prefix", ""))).expanduser().resolve(strict=True)
    manifest = Path(installation.get("manifest", ""))
    if not root.is_dir() or not prefix.is_dir() or not manifest.is_file():
        raise ValueError("This game's managed files or manifest are unavailable.")
    base = manifest.parent.resolve(strict=True)
    if root.parent != base / "common" or prefix.parent != base / "compatdata" or not manifest.name.startswith(_MANIFEST_PREFIX):
        raise ValueError("Only games linked into an UmuLibrary can be backed up.")
    return root, prefix, manifest


def _archive_component(source: Path, destination: Path, directory: str) -> None:
    with tarfile.open(destination, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        tar.add(source, arcname=directory + "/" + source.name, recursive=True)


def backup_game(game: dict[str, Any], destination: str | Path) -> None:
    """Write an outer game archive with a manifest and common/ game content."""
    root, prefix, manifest = _linked_paths(game)
    archive = Path(destination).expanduser()
    if archive.suffixes[-2:] != [".tar", ".gz"]:
        archive = archive.with_suffix(archive.suffix + ".tar.gz") if archive.suffix else archive.with_suffix(".tar.gz")
    archive.parent.mkdir(parents=True, exist_ok=True)
    package_name = _safe_folder(game["title"])
    with tempfile.TemporaryDirectory(prefix=".umutron-backup-", dir=archive.parent) as staging:
        package = Path(staging) / package_name
        package.mkdir()
        shutil.copy2(manifest, package / manifest.name)
        _archive_component(root, package / "content.tar.gz", "common")
        with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as tar:
            tar.add(package, arcname=package_name, recursive=True)


def _backup_manifest(archive: str | Path) -> tuple[dict[str, Any], str]:
    with tarfile.open(archive, "r:*") as tar:
        members = [member for member in tar.getmembers() if member.isfile() and member.name.rsplit("/", 1)[-1].startswith(_MANIFEST_PREFIX)]
        if len(members) != 1 or members[0].size > _MAX_MANIFEST:
            raise ValueError("Backup has no valid game manifest.")
        stream = tar.extractfile(members[0])
        if stream is None:
            raise ValueError("Backup has no readable game manifest.")
        try:
            value = json.loads(stream.read(_MAX_MANIFEST + 1))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Backup game manifest is invalid.") from error
    required = {"format", "game_id", "title", "steam_app_id", "content_directory", "launcher_relative_path", "compatdata_directory", "proton"}
    if not isinstance(value, dict) or set(value) != required or value.get("format") != 1:
        raise ValueError("Backup game manifest is unsupported.")
    if not isinstance(value["title"], str) or not isinstance(value["launcher_relative_path"], str) or not isinstance(value["proton"], str):
        raise ValueError("Backup game manifest is invalid.")
    return value, str(PurePosixPath(members[0].name).parent)


def _safe_members(tar: tarfile.TarFile, allowed: tuple[str, ...]) -> list[tarfile.TarInfo]:
    members = tar.getmembers()
    if len(members) > 200_000:
        raise ValueError("Backup has too many files.")
    for member in members:
        path = PurePosixPath(member.name)
        inside = any(member.name == prefix.rstrip("/") or member.name.startswith(prefix) for prefix in allowed)
        if not inside or path.is_absolute() or ".." in path.parts or member.isdev() or member.islnk():
            raise ValueError("Backup contains an unsafe entry.")
    return members


def restore_game(game: dict[str, Any], *, archive: str | Path, drive_root: str | Path) -> dict[str, Any]:
    """Restore one backed-up game into common/ and compatdata/ on a selected drive."""
    source = Path(archive).expanduser().resolve(strict=True)
    manifest, package = _backup_manifest(source)
    if manifest["game_id"] != game["id"]:
        raise ValueError("This backup belongs to another game library entry.")
    base, destination, prefix, destination_manifest = _managed_paths(drive_root, game)
    if destination.exists() or prefix.exists() or destination_manifest.exists():
        raise ValueError("This game already has managed files on the selected drive.")
    backed_content = PurePosixPath(manifest["content_directory"])
    if len(backed_content.parts) != 2 or backed_content.parts[0] != "common" or not backed_content.parts[1]:
        raise ValueError("Backup content path is invalid.")
    launcher_path = PurePosixPath(manifest["launcher_relative_path"])
    if launcher_path.is_absolute() or ".." in launcher_path.parts:
        raise ValueError("Backup launcher path is unsafe.")
    base.mkdir(parents=True, exist_ok=True)
    staging = base / (".restore-" + str(os.getpid()))
    if staging.exists():
        raise RuntimeError("A previous restore operation is still present. Review the managed library folder.")
    try:
        with tarfile.open(source, "r:*") as tar:
            members = _safe_members(tar, (package + "/",))
            required = {package + "/content.tar.gz"}
            if not required.issubset({member.name for member in members}):
                raise ValueError("Backup does not contain the game content archive.")
            tar.extractall(staging, members=members, filter="data")
        content_archive = staging / package / "content.tar.gz"
        with tarfile.open(content_archive, "r:*") as tar:
            tar.extractall(staging, members=_safe_members(tar, ("common/",)), filter="data")
        staged_content = staging / backed_content.parts[0] / backed_content.parts[1]
        if not staged_content.is_dir():
            raise ValueError("Backup did not restore the expected game content.")
        (base / "common").mkdir(exist_ok=True)
        (base / "compatdata").mkdir(exist_ok=True)
        staged_content.rename(destination)
        prefix.mkdir(mode=0o700)
        restored = _manifest(game, destination, prefix, Path(manifest["launcher_relative_path"]), _validate_proton(manifest["proton"]))
        _write_manifest(destination_manifest, restored)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    executable = destination / manifest["launcher_relative_path"]
    if not executable.is_file():
        raise ValueError("Backup launcher executable is missing after restore.")
    return {
        "root": str(destination), "executable": str(executable), "working_dir": str(executable.parent),
        "prefix": str(prefix), "proton": manifest["proton"], "manifest": str(destination_manifest), "mode": "restore",
    }
