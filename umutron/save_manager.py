"""Lightweight save game export and import for UmuTron games."""
from pathlib import Path
import re
import shutil
import zipfile


def find_game_save_folders(game) -> list[tuple[str, Path]]:
    """Locate directories containing player saves for this game."""
    results = []
    prefix_str = game.get('launch', {}).get('prefix') or game.get('installation', {}).get('prefix')
    if prefix_str:
        drive_c = Path(prefix_str).expanduser().resolve() / 'drive_c'
        if drive_c.is_dir():
            title = game.get('title', '')
            safe_title = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", title).strip()
            candidates = [
                drive_c / 'users' / 'steamuser' / 'Saved Games' / safe_title,
                drive_c / 'users' / 'steamuser' / 'Documents' / 'My Games' / safe_title,
                drive_c / 'users' / 'steamuser' / 'Documents' / safe_title,
                drive_c / 'users' / 'steamuser' / 'AppData' / 'Local' / safe_title,
                drive_c / 'users' / 'steamuser' / 'AppData' / 'Roaming' / safe_title,
                drive_c / 'users' / 'Public' / 'Documents' / safe_title,
            ]
            app_id = game.get('metadata_app_id')
            if app_id:
                candidates.extend([
                    drive_c / 'users' / 'steamuser' / 'AppData' / 'Roaming' / str(app_id),
                    drive_c / 'users' / 'steamuser' / 'AppData' / 'Local' / str(app_id),
                    drive_c / 'users' / 'Public' / 'Documents' / 'Steam' / 'CODEX' / str(app_id),
                    drive_c / 'users' / 'Public' / 'Documents' / 'Steam' / 'RUNE' / str(app_id),
                    drive_c / 'users' / 'Public' / 'Documents' / 'uPlay' / 'CODEX' / 'Saves' / safe_title,
                ])
            for c in candidates:
                if c.is_dir() and any(c.iterdir()):
                    try:
                        rel = c.relative_to(drive_c)
                        results.append((str(rel), c))
                    except ValueError:
                        pass

    root_str = game.get('installation', {}).get('root')
    if root_str:
        root_dir = Path(root_str).expanduser().resolve()
        for sub in ('bin/SAVES', 'bin/Savegame', 'SAVES', 'Savegame'):
            p = root_dir / sub
            if p.is_dir() and any(p.iterdir()):
                results.append((sub, p))
    return results


def export_saves(game, target_zip_path: Path) -> int:
    """Create a lightweight zip containing detected save files."""
    folders = find_game_save_folders(game)
    if not folders:
        raise ValueError("No save files were found for this game yet. Launch the game to create a save.")
    target_zip_path = Path(target_zip_path)
    target_zip_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(target_zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for rel_prefix, folder in folders:
            for file_path in folder.rglob('*'):
                if file_path.is_file():
                    arcname = f"{rel_prefix}/{file_path.relative_to(folder)}"
                    zf.write(file_path, arcname)
                    count += 1
    return count


def import_saves(game, source_zip_path: Path) -> int:
    """Extract a save game zip back into the game's prefix or folder."""
    prefix_str = game.get('launch', {}).get('prefix') or game.get('installation', {}).get('prefix')
    if not prefix_str:
        raise ValueError("This game does not have an active prefix.")
    drive_c = Path(prefix_str).expanduser().resolve() / 'drive_c'
    root_str = game.get('installation', {}).get('root')
    root_dir = Path(root_str).expanduser().resolve() if root_str else None

    count = 0
    with zipfile.ZipFile(source_zip_path, 'r') as zf:
        for member in zf.namelist():
            if '..' in member or member.startswith('/') or member.endswith('/'):
                continue
            if member.startswith('bin/SAVES') or member.startswith('bin/Savegame') or member.startswith('SAVES') or member.startswith('Savegame'):
                dest = (root_dir / member) if root_dir else (drive_c / member)
            else:
                dest = drive_c / member
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(dest, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            count += 1
    return count
