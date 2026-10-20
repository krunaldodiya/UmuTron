"""Steam-like managed game layout, linking, and per-game backups."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
from typing import Any

from .library import atomic_write

_LAYOUT = "UmuLibrary/umuapps"
_MANIFEST_PREFIX = "appmanifest_"
_MAX_MANIFEST = 256 * 1024

class BackupCancelled(Exception):
    """A user cancelled a backup before its archive was finalized."""


def _check_cancelled(cancelled) -> None:
    if cancelled and cancelled():
        raise BackupCancelled("Backup cancelled.")


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
        "launch_options": list(game.get("launch", {}).get("arguments", [])),
    }


def _write_manifest(path: Path, data: dict[str, Any]) -> None:
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))

def _digest(path: Path, cancelled=None) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        while chunk:=stream.read(1024*1024):
            _check_cancelled(cancelled)
            digest.update(chunk)
    return digest.hexdigest()


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

def move_game_installation(game: dict[str, Any], *, drive_root: str | Path) -> dict[str, Any]:
    """Move an existing installed or linked game into the selected managed library drive."""
    installation = game.get("installation", {})
    source_root = Path(installation.get("root", "")).expanduser().resolve(strict=True)
    executable = Path(game.get("executable", "")).expanduser().resolve(strict=True)
    proton = game.get("launch", {}).get("proton", "")
    old_manifest_path = installation.get("manifest")
    result = link_game(game, drive_root=drive_root, source_root=source_root,
                       launcher=executable, proton=proton, move=True)
    if old_manifest_path:
        old_manifest = Path(old_manifest_path).expanduser().resolve()
        if old_manifest.is_file() and old_manifest != Path(result["manifest"]):
            try:old_manifest.unlink()
            except OSError:pass
    return result

def unlink_game(game: dict[str, Any]) -> None:
    """Remove the managed manifest after its content is uninstalled; keep compatdata."""
    installation = game.get("installation", {})
    manifest_path_str = installation.get("manifest")
    if not manifest_path_str:
        return
    try:
        manifest = Path(manifest_path_str).expanduser().resolve(strict=True)
    except OSError:
        return
    base = manifest.parent
    root = Path(installation.get("root", "")).expanduser().resolve()
    if root.parent == base / "common" and manifest.name == f"{_MANIFEST_PREFIX}{manifest_key(game)}.json":
        manifest.unlink()
def set_game_proton(game: dict[str, Any], proton: str | Path) -> str:
    """Persist an installed Proton choice in the managed manifest."""
    _root, _prefix, manifest = _linked_paths(game)
    selected = _validate_proton(proton)
    try:data=json.loads(manifest.read_bytes())
    except (UnicodeDecodeError,json.JSONDecodeError) as error:raise ValueError("Managed game manifest is invalid.") from error
    data["proton"]=selected
    _write_manifest(manifest,data)
    return selected

def set_game_launch_options(game: dict[str, Any], arguments: list[str]) -> list[str]:
    """Persist direct launch arguments in the managed manifest."""
    if not isinstance(arguments,list) or any(not isinstance(value,str) or '\x00' in value or '\n' in value or '\r' in value for value in arguments):
        raise ValueError("Launch options must be direct single-line arguments.")
    _root, _prefix, manifest = _linked_paths(game)
    try:data=json.loads(manifest.read_bytes())
    except (UnicodeDecodeError,json.JSONDecodeError) as error:raise ValueError("Managed game manifest is invalid.") from error
    data["launch_options"]=list(arguments)
    _write_manifest(manifest,data)
    return arguments


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


def _fast_size(path: Path) -> int:
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    total += _fast_size(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    total += entry.stat().st_size
    except OSError:
        pass
    return total


def _game_archive_paths(game: dict[str, Any]) -> tuple[Path, Path, dict[str, Any], str]:
    installation = game.get("installation", {})
    root = Path(installation.get("root", "")).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("This game's installation folder is unavailable.")
    executable = Path(game.get("executable", "")).expanduser().resolve(strict=True)
    try:executable_rel = executable.relative_to(root)
    except ValueError:raise ValueError("The launcher executable must be inside the game installation folder.")
    proton = game.get("launch", {}).get("proton", "")
    prefix_str = installation.get("prefix", game.get("launch", {}).get("prefix", ""))
    prefix = Path(prefix_str).expanduser() if prefix_str else root.parent / "compatdata" / _safe_folder(game["title"])
    manifest_name = f"{_MANIFEST_PREFIX}{manifest_key(game)}.json"
    manifest_path = Path(installation.get("manifest", "")) if installation.get("manifest") else None
    if manifest_path and manifest_path.is_file():
        try:manifest_data = json.loads(manifest_path.read_bytes())
        except (UnicodeDecodeError, json.JSONDecodeError):manifest_data = _manifest(game, root, prefix, executable_rel, proton)
    else:manifest_data = _manifest(game, root, prefix, executable_rel, proton)
    return root, prefix, manifest_data, manifest_name


def _archive_component(source: Path, destination: Path, directory: str, progress=None, cancelled=None) -> str:
    _check_cancelled(cancelled)
    total = _fast_size(source)
    done = 0
    hasher = hashlib.sha256()
    safe_name = _safe_folder(source.name)
    tar_bin = shutil.which("tar")
    if tar_bin:
        if source.parent.name == directory:
            base = str(source.parent.parent)
            rel = f"{directory}/{source.name}"
            cmd = [tar_bin, "-cf", "-", "-C", base, rel]
        else:
            base = str(source.parent)
            cmd = [tar_bin, "-cf", "-", "-C", base, "--transform", f"s,^{re.escape(source.name)},{directory}/{safe_name},", source.name]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        try:
            with destination.open("wb", buffering=0) as out:
                while True:
                    if cancelled and cancelled():
                        if proc.poll() is None:
                            proc.terminate()
                            try:proc.wait(timeout=1)
                            except subprocess.TimeoutExpired:(proc.kill(),proc.wait())
                        raise BackupCancelled("Backup cancelled.")
                    chunk = proc.stdout.read(4 * 1024 * 1024)
                    if not chunk:break
                    out.write(chunk);hasher.update(chunk);done += len(chunk)
                    if progress:progress(min(done, total), total)
            ret = proc.wait()
            if ret > 1:
                err = proc.stderr.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"tar command failed: {err}")
        finally:
            if proc.stdout:proc.stdout.close()
            if proc.stderr:proc.stderr.close()
            if proc.poll() is None:(proc.kill(),proc.wait())
    else:
        class _HashingWriter:
            def __init__(self, target, h):self.target = target;self.hasher = h
            def write(self, b):self.target.write(b);self.hasher.update(b);return len(b)
        files = [p for p in source.rglob("*") if p.is_file()]
        with destination.open("wb", buffering=0) as raw_out:
            writer = _HashingWriter(raw_out, hasher)
            with tarfile.open(fileobj=writer, mode="w", format=tarfile.PAX_FORMAT) as tar:
                tar.add(source, arcname=f"{directory}/{safe_name}", recursive=False)
                for path in files:
                    _check_cancelled(cancelled)
                    tar.add(path, arcname=(Path(directory)/safe_name/path.relative_to(source)).as_posix(), recursive=False)
                    done += path.stat().st_size
                    if progress:progress(min(done, total), total)
    _check_cancelled(cancelled)
    if progress:progress(total, total)
    return hasher.hexdigest()


def backup_game(game: dict[str, Any], destination: str | Path, *, replace: bool = False, progress=None, cancelled=None) -> Path:
    """Write one portable game directory with a manifest and uncompressed content tar."""
    _check_cancelled(cancelled)
    root, _prefix, manifest_data, manifest_name = _game_archive_paths(game)
    parent = Path(destination).expanduser().resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("Choose an existing backup directory.")
    package_name = _safe_folder(game["title"])
    final = parent / package_name
    if final.exists() and not replace:
        raise ValueError("A backup folder with this game name already exists there.")
    with tempfile.TemporaryDirectory(prefix=".umutron-backup-", dir=parent) as staging:
        package = Path(staging) / package_name
        package.mkdir()
        digest = _archive_component(root, package / "content.tar", "common", progress, cancelled)
        _check_cancelled(cancelled)
        manifest_data["content_archive"]={"name":"content.tar","sha256":digest}
        _write_manifest(package / manifest_name,manifest_data)
        if final.exists():
            shutil.rmtree(final)
        package.rename(final)
    return final


def _backup_manifest(backup: str | Path) -> tuple[dict[str, Any], Path]:
    folder = Path(backup).expanduser().resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("Choose a game backup folder.")
    manifests = list(folder.glob(_MANIFEST_PREFIX + "*.json"))
    if len(manifests) != 1 or manifests[0].stat().st_size > _MAX_MANIFEST:
        raise ValueError("Backup has no valid game manifest.")
    try:value=json.loads(manifests[0].read_bytes())
    except (UnicodeDecodeError,json.JSONDecodeError) as error:raise ValueError("Backup game manifest is invalid.") from error
    required={"format","game_id","title","steam_app_id","content_directory","launcher_relative_path","compatdata_directory","proton"}
    if not isinstance(value,dict) or not required.issubset(value) or value.get("format")!=1:
        raise ValueError("Backup game manifest is unsupported.")
    if not isinstance(value["title"],str) or not isinstance(value["launcher_relative_path"],str) or not isinstance(value["proton"],str):
        raise ValueError("Backup game manifest is invalid.")
    if "launch_options" in value and (not isinstance(value["launch_options"],list) or any(not isinstance(option,str) or '\x00' in option or '\n' in option or '\r' in option for option in value["launch_options"])):
        raise ValueError("Backup launch options are invalid.")
    return value, folder


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
    """Restore one game backup directory into common/ and compatdata/."""
    manifest, folder = _backup_manifest(archive)
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
        content_archive = folder / "content.tar"
        if not content_archive.is_file():
            raise ValueError("Backup does not contain content.tar.")
        expected=manifest.get("content_archive",{})
        if expected and (expected.get("name")!="content.tar" or expected.get("sha256")!=_digest(content_archive)):
            raise ValueError("Backup content checksum does not match its manifest.")
        staging.mkdir(parents=True, exist_ok=True)
        with tarfile.open(content_archive, "r:") as tar:
            members = _safe_members(tar, ("common/",))
        tar_bin = shutil.which("tar")
        if tar_bin:
            res = subprocess.run([tar_bin, "-xf", str(content_archive), "-C", str(staging)], capture_output=True)
            if res.returncode != 0:
                raise RuntimeError(f"tar extraction failed: {res.stderr.decode('utf-8', errors='replace')}")
        else:
            with tarfile.open(content_archive, "r:") as tar:
                tar.extractall(staging, members=members, filter="data")
        staged_content = staging / backed_content.parts[0] / backed_content.parts[1]
        if not staged_content.is_dir():
            raise ValueError("Backup did not restore the expected game content.")
        (base / "common").mkdir(exist_ok=True)
        (base / "compatdata").mkdir(exist_ok=True)
        staged_content.rename(destination)
        prefix.mkdir(mode=0o700)
        restored_game={**game,"launch":{**game.get("launch",{}),"arguments":manifest.get("launch_options",[])}}
        restored = _manifest(restored_game, destination, prefix, Path(manifest["launcher_relative_path"]), _validate_proton(manifest["proton"]))
        _write_manifest(destination_manifest, restored)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    executable = destination / manifest["launcher_relative_path"]
    if not executable.is_file():
        raise ValueError("Backup launcher executable is missing after restore.")
    return {
        "root": str(destination), "executable": str(executable), "working_dir": str(executable.parent),
        "prefix": str(prefix), "proton": manifest["proton"], "manifest": str(destination_manifest),
        "arguments": manifest.get("launch_options", []), "mode": "restore",
    }
