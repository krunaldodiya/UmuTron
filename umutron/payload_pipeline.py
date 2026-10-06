"""Payload classification, executable ranking, and staging pipeline for game installations."""
from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import re
import shutil
import struct

from .sources.base import is_multipart_link, normalize_title


class PayloadKind(str, Enum):
    PORTABLE_LOOSE = 'portable_loose'
    INSTALLER_LOOSE = 'installer_loose'
    PORTABLE_ARCHIVE = 'portable_archive'
    INSTALLER_ARCHIVE = 'installer_archive'
    ARCHIVE = 'archive'
    UNKNOWN = 'unknown'


class InstallerType(str, Enum):
    INNO = 'inno'
    NSIS = 'nsis'
    MSI = 'msi'
    INSTALLSHIELD = 'installshield'
    UNKNOWN = 'unknown'


@dataclass
class PayloadInfo:
    kind: PayloadKind
    container: Path | None = None
    installer_exe: Path | None = None
    installer_type: InstallerType = InstallerType.UNKNOWN
    crack_dir: Path | None = None
    root_dir: Path | None = None


ARCHIVE_EXTENSIONS = ('.zip', '.rar', '.7z', '.iso', '.tar', '.gz', '.bz2', '.xz')

KNOWN_AUXILIARY_NAMES = {
    'unins000.exe', 'unins001.exe', 'uninstall.exe', 'uninstaller.exe',
    'unitycrashhandler.exe', 'unitycrashhandler32.exe', 'unitycrashhandler64.exe',
    'crashreport.exe', 'crashreporter.exe', 'crashhandler.exe', 'crashsender.exe',
    'dxsetup.exe', 'vcredist_x86.exe', 'vcredist_x64.exe', 'vc_redist.x86.exe', 'vc_redist.x64.exe',
    'easyanticheat.exe', 'easyanticheat_setup.exe', 'battleye.exe', 'beservice.exe',
    'setup.exe', 'install.exe', 'installer.exe', 'autorun.exe',
    'directx-setup.exe', 'websetup.exe',
}

DISFAVORED_FOLDER_NAMES = {
    '_redist', '_commonredist', 'commonredist', 'redist', 'directx',
    'vcredist', 'dotnet', 'support', 'prerequisites', 'installer',
}


def is_pe_executable(file_path: Path) -> bool:
    """Return True if the file has a valid Windows PE header."""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(2)
            if header != b'MZ':
                return False
            f.seek(60)
            e_lfanew_bytes = f.read(4)
            if len(e_lfanew_bytes) < 4:
                return False
            e_lfanew = struct.unpack('<I', e_lfanew_bytes)[0]
            f.seek(e_lfanew)
            pe_signature = f.read(4)
            return pe_signature == b'PE\x00\x00'
    except (OSError, struct.error):
        return False


def is_64bit_pe(file_path: Path) -> bool:
    """Return True if the PE file is compiled for AMD64/x86_64."""
    try:
        with open(file_path, 'rb') as f:
            f.seek(60)
            e_lfanew = struct.unpack('<I', f.read(4))[0]
            f.seek(e_lfanew + 4)
            machine = struct.unpack('<H', f.read(2))[0]
            return machine == 0x8664  # IMAGE_FILE_MACHINE_AMD64
    except (OSError, struct.error):
        return False


def detect_installer_engine(exe_path: Path) -> InstallerType:
    """Inspect executable strings and headers to classify the installer engine."""
    if not exe_path.is_file():
        return InstallerType.UNKNOWN
    if exe_path.suffix.lower() == '.msi':
        return InstallerType.MSI
    try:
        data = exe_path.read_bytes()[:2 * 1024 * 1024]
        if b'Inno Setup' in data or b'InnoSetup' in data:
            return InstallerType.INNO
        if b'Nullsoft' in data or b'NSIS' in data:
            return InstallerType.NSIS
        if b'InstallShield' in data:
            return InstallerType.INSTALLSHIELD
    except OSError:
        pass
    return InstallerType.UNKNOWN


def find_setup_executable(directory: Path) -> Path | None:
    """Look for an installer executable in a directory."""
    if not directory.is_dir():
        return None
    for pattern in ('setup.exe', 'install.exe', 'installer.exe'):
        matches = list(directory.glob(pattern))
        if matches and matches[0].is_file():
            return matches[0]
    for pattern in ('setup.exe', 'install.exe', 'installer.exe'):
        matches = list(directory.rglob(pattern))
        if matches and matches[0].is_file():
            return matches[0]
    return None


def has_installer_payloads(directory: Path) -> bool:
    """Return True if compressed setup payload files exist (.bin, .doi, .cab)."""
    if not directory.is_dir():
        return False
    for ext in ('*.bin', '*.doi', '*.cab', '*.iss'):
        matches = list(directory.glob(ext)) + list(directory.rglob(ext))
        if matches:
            return True
    return False


def find_crack_directory(directory: Path) -> Path | None:
    """Detect optional scene crack directories to copy over the installed game."""
    if not directory.is_dir():
        return None
    for name in ('CODEX', 'RUNE', 'FLT', 'SKIDROW', 'Crack', 'PLAZA'):
        target = directory / name
        if target.is_dir():
            return target
        matches = list(directory.rglob(name))
        if matches and matches[0].is_dir():
            return matches[0]
    return None

def get_silent_installer_arguments(installer_type: InstallerType, target_dir: Path) -> list[str]:
    """Return standard unattended silent CLI arguments for the detected installer framework."""
    target_str = str(target_dir)
    if installer_type == InstallerType.INNO:
        return ['/VERYSILENT', '/SP-', '/NORESTART', '/SUPPRESSMSGBOXES', f'/DIR={target_str}']
    elif installer_type == InstallerType.NSIS:
        return ['/S', f'/D={target_str}']
    elif installer_type == InstallerType.MSI:
        return ['/qn', f'TARGETDIR={target_str}']
    elif installer_type == InstallerType.INSTALLSHIELD:
        return ['/s', f'/v"/qn INSTALLDIR=\\"{target_str}\\""']
    else:
        return ['/VERYSILENT', '/SP-', '/NORESTART', '/SUPPRESSMSGBOXES', f'/DIR={target_str}']


def run_native_innoextract(setup_exe: Path, target_dir: Path) -> bool:
    """If innoextract is available on the system, unpack Inno Setup payloads natively."""
    from .download_service import ensure_innoextract_binary
    inno_bin = ensure_innoextract_binary()
    if not inno_bin or not setup_exe.is_file():
        return False
    import subprocess
    target_dir.mkdir(parents=True, exist_ok=True)
    cmd = [inno_bin, '--silent', '--extract', '--output-dir', str(target_dir), str(setup_exe)]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0
    except Exception:
        return False


def extract_archive(archive_path: Path, output_dir: Path) -> bool:
    """Extract an archive (.zip, .rar, .7z, .iso, .tar) to output_dir using 7zz or Python fallback."""
    archive_path = Path(archive_path)
    output_dir = Path(output_dir)
    if not archive_path.is_file():
        return False
    output_dir.mkdir(parents=True, exist_ok=True)

    from .download_service import ensure_7z_binary
    bin_7z = ensure_7z_binary()
    if bin_7z:
        import subprocess
        cmd = [bin_7z, 'x', '-y', f'-o{output_dir}', str(archive_path)]
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0:
                return True
        except Exception:
            pass

    suffix = archive_path.suffix.lower()
    if suffix == '.zip':
        import zipfile
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(output_dir)
            return True
        except Exception:
            return False
    elif suffix in ('.tar', '.gz', '.bz2', '.xz'):
        import tarfile
        try:
            with tarfile.open(archive_path, 'r:*') as tf:
                tf.extractall(output_dir)
            return True
        except Exception:
            return False

    return False
COMMON_GAME_DIRECTORIES = {
    'bin', 'bin64', 'bin_x64', 'win64', 'x64', 'binaries',
    'engine', 'content', 'data', 'game', 'gamedata', 'plugins',
}


def unwrap_single_root_directory(directory: Path) -> Path:
    """If directory contains only one container subdirectory and no other files, unwrap that folder."""
    if not directory.is_dir():
        return directory
    entries = [p for p in directory.iterdir() if p.name != '__pycache__' and not p.name.startswith('.')]
    if len(entries) == 1 and entries[0].is_dir() and entries[0].name.lower() not in COMMON_GAME_DIRECTORIES:
        child_entries = [p for p in entries[0].iterdir() if p.name != '__pycache__' and not p.name.startswith('.')]
        if any(p.is_file() or p.name.lower() in COMMON_GAME_DIRECTORIES for p in child_entries):
            return entries[0]
        return unwrap_single_root_directory(entries[0])
    return directory

def classify_payload(target_path: Path) -> PayloadInfo:
    """Inspect a downloaded file or directory and determine its payload structure."""
    target_path = Path(target_path)
    if not target_path.exists():
        return PayloadInfo(kind=PayloadKind.UNKNOWN)

    # 1. Single file archive/container
    if target_path.is_file():
        suffix = target_path.suffix.lower()
        if suffix in ARCHIVE_EXTENSIONS:
            return PayloadInfo(kind=PayloadKind.ARCHIVE, container=target_path)
        if suffix == '.exe':
            engine = detect_installer_engine(target_path)
            return PayloadInfo(
                kind=PayloadKind.INSTALLER_LOOSE,
                installer_exe=target_path,
                installer_type=engine,
            )
        return PayloadInfo(kind=PayloadKind.UNKNOWN)

    # 2. Directory inspection
    if target_path.is_dir():
        effective_dir = unwrap_single_root_directory(target_path)
        setup_exe = find_setup_executable(effective_dir)
        has_setup_data = has_installer_payloads(effective_dir)

        # Check if directory contains a single archive container
        archive_candidates = [
            f for f in effective_dir.iterdir()
            if f.is_file() and f.suffix.lower() in ARCHIVE_EXTENSIONS
            and not is_multipart_link(f.name)
        ]
        if len(archive_candidates) == 1 and not setup_exe:
            return PayloadInfo(
                kind=PayloadKind.ARCHIVE,
                container=archive_candidates[0],
                root_dir=effective_dir,
            )

        crack_dir = find_crack_directory(effective_dir)

        if setup_exe or has_setup_data:
            engine = detect_installer_engine(setup_exe) if setup_exe else InstallerType.UNKNOWN
            return PayloadInfo(
                kind=PayloadKind.INSTALLER_LOOSE,
                installer_exe=setup_exe,
                installer_type=engine,
                crack_dir=crack_dir,
                root_dir=effective_dir,
            )

        # Look for loose Windows executables
        exe_files = [f for f in effective_dir.rglob('*.exe') if f.is_file()]
        if exe_files:
            return PayloadInfo(
                kind=PayloadKind.PORTABLE_LOOSE,
                crack_dir=crack_dir,
                root_dir=effective_dir,
            )

    return PayloadInfo(kind=PayloadKind.UNKNOWN, root_dir=target_path)


def rank_game_executables(folder: Path, title: str = '') -> list[Path]:
    """Score and rank all candidate game executables in a folder, best match first."""
    folder = Path(folder)
    if not folder.is_dir():
        return []

    candidates: list[tuple[int, Path]] = []
    clean_title = normalize_title(title).lower()
    title_tokens = set(re.findall(r'[a-z0-9]+', clean_title))

    all_exes = [p for p in folder.rglob('*.exe') if p.is_file()]
    for exe in all_exes:
        name_lower = exe.name.lower()
        if name_lower in KNOWN_AUXILIARY_NAMES:
            continue
        if any(part.lower() in DISFAVORED_FOLDER_NAMES for part in exe.parts):
            continue

        score = 0
        stem_lower = exe.stem.lower()
        exe_tokens = set(re.findall(r'[a-z0-9]+', stem_lower))

        # Title token match
        overlap = title_tokens & exe_tokens
        score += len(overlap) * 30
        if clean_title and clean_title.replace(' ', '') in stem_lower.replace(' ', ''):
            score += 50
        elif stem_lower and stem_lower in clean_title:
            score += 40

        # Location scoring
        rel_parts = exe.relative_to(folder).parts
        if len(rel_parts) == 1:
            score += 25
        elif any(part.lower() in ('bin', 'bin64', 'bin_x64', 'win64', 'x64') for part in rel_parts):
            score += 35

        # File size scoring (main game executables are typically substantial)
        try:
            size_mb = exe.stat().st_size / (1024 * 1024)
            if size_mb < 0.5:
                score -= 20  # tiny launcher or stub
            else:
                score += min(int(size_mb), 40)
        except OSError:
            pass

        # 64-bit architecture preference
        if is_64bit_pe(exe):
            score += 15

        candidates.append((score, exe))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [exe for _, exe in candidates]


def stage_portable_game(source_dir: Path, target_dir: Path) -> Path:
    """Move or copy loose portable game files into the target destination directory and clean up staging."""
    source_dir = Path(source_dir)
    target_dir = Path(target_dir)

    effective_source = unwrap_single_root_directory(source_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    if effective_source.resolve() == target_dir.resolve():
        return target_dir

    if target_dir.exists():
        for item in effective_source.iterdir():
            dest_item = target_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest_item, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest_item)
        if source_dir.resolve() != target_dir.resolve():
            shutil.rmtree(source_dir, ignore_errors=True)
    else:
        try:
            os.rename(str(effective_source), str(target_dir))
            if source_dir.resolve() != target_dir.resolve():
                shutil.rmtree(source_dir, ignore_errors=True)
        except OSError:
            shutil.copytree(effective_source, target_dir, dirs_exist_ok=True)
            if source_dir.resolve() != target_dir.resolve():
                shutil.rmtree(source_dir, ignore_errors=True)

    return target_dir
