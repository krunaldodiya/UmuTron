"""Read-only, bounded prefix evidence. Never execute Wine or traverse drive mappings."""
import os
import re
import stat
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .launcher import MARKER, defaults

MAX_PE = 32 * 1024 * 1024
MAX_REG = 32 * 1024 * 1024


@dataclass(frozen=True)
class Requirement:
    key: str
    title: str
    architecture: str
    minimum: tuple
    dlls: tuple
    url: str = ''


# Deliberately describes core CRT coverage, not every optional MFC/OpenMP component.
RECIPES = {
    'vc14-' + arch: Requirement('vc14-' + arch, 'Microsoft VC++ v14 core (2015 and later)', arch,
                               (14, 0, 24212, 0), ('vcruntime140.dll', 'msvcp140.dll', 'concrt140.dll'),
                               f'https://aka.ms/vc14/vc_redist.{arch}.exe')
    for arch in ('x86', 'x64')
}
# A newer explicit core minimum can be selected without guessing a game's toolset.
RECIPES.update({
    'vc14-modern-' + arch: Requirement('vc14-modern-' + arch, 'Microsoft VC++ v14 core (minimum 14.44)', arch,
        (14, 44, 35211, 0), ('vcruntime140.dll', 'msvcp140.dll', 'concrt140.dll') +
        (('vcruntime140_1.dll',) if arch == 'x64' else ()), f'https://aka.ms/vc14/vc_redist.{arch}.exe')
    for arch in ('x86', 'x64')
})
LEGACY = [Requirement(f'vc{major}-{arch}', f'Microsoft VC++ {year} core', arch, (major, 0, 0, 0),
                      (f'msvcr{major}0.dll', f'msvcp{major}0.dll'))
          for major, year in ((10, 2010), (11, 2012), (12, 2013)) for arch in ('x86', 'x64')]


def version_text(value):
    return '.'.join(map(str, value)) if value else 'Unknown'


def read_bounded(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('Not a bounded regular file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError('File grew beyond inspection limit')
        return data
    finally:
        os.close(fd)


def pe_evidence(path, roots=()):
    """Origin is file metadata evidence, not Authenticode authentication."""
    path = Path(path)
    result = {'path': str(path), 'origin': 'Unknown', 'architecture': 'Unknown', 'version': None}
    try:
        resolved = path.resolve(strict=True)
        if roots and not any(resolved.is_relative_to(Path(root).resolve()) for root in roots):
            return {**result, 'detail': 'External link; contents not inspected'}
        data = read_bounded(resolved, MAX_PE)
        if data[:2] != b'MZ':
            return {**result, 'detail': 'Not a PE image'}
        pe = struct.unpack_from('<I', data, 60)[0]
        if data[pe:pe + 4] != b'PE\0\0':
            return {**result, 'detail': 'Invalid PE header'}
        machine = struct.unpack_from('<H', data, pe + 4)[0]
        result['architecture'] = {0x14c: 'x86', 0x8664: 'x64', 0xaa64: 'arm64'}.get(machine, 'Unknown')
        builtin = b'Wine builtin DLL' in data[:4096] or b'Wine placeholder DLL' in data[:4096]
        # Limit version evidence to the PE resource section; do not scan arbitrary payloads.
        count = struct.unpack_from('<H', data, pe + 6)[0]
        size = struct.unpack_from('<H', data, pe + 20)[0]
        resources = b''
        for index in range(min(count, 96)):
            section = pe + 24 + size + index * 40
            if data[section:section + 8].rstrip(b'\0') == b'.rsrc':
                length, offset = struct.unpack_from('<II', data, section + 16)
                if offset + length <= len(data):
                    resources = data[offset:offset + length]
        marker = resources.find(b'\xbd\x04\xef\xfe\x00\x00\x01\x00')
        if marker >= 0:
            ms, ls = struct.unpack_from('<II', resources, marker + 8)
            result['version'] = (ms >> 16, ms & 65535, ls >> 16, ls & 65535)
        strings = resources.decode('utf-16le', errors='ignore')
        wine = builtin or 'Wine project' in strings or 'Wine Project' in strings
        runner_component = 'DXVK' if 'DXVK' in strings else 'VKD3D' if 'vkd3d' in strings.casefold() else ''
        result['origin'] = 'Wine/Proton builtin' if wine else ('Runner '+runner_component if runner_component else 'Microsoft native' if 'Microsoft Corporation' in strings else 'Unknown')
        result['detail'] = ('Wine image marker / resource metadata' if wine else
                            'Microsoft file metadata; signature not authenticated' if result['origin'] == 'Microsoft native' else
                            'Publisher could not be established')
        result['resolved'] = str(resolved)
        return result
    except FileNotFoundError:
        return {**result, 'origin': 'Missing', 'detail': 'Broken link' if path.is_symlink() else 'No file'}
    except (OSError, ValueError, struct.error, RuntimeError) as error:
        return {**result, 'detail': str(error)}


def directory_usage(root, cancel=None, limit=200000, seconds=20):
    """Allocated bytes, including link inodes; dedupe hardlinks; exclude mappings/mounts."""
    cancel = cancel or threading.Event()
    result = {'allocated': 0, 'apparent': 0, 'files': 0, 'links': 0, 'broken_links': 0, 'skipped': 0, 'complete': True}
    start = time.monotonic()
    seen = set()
    try:
        root_stat = root.stat()
        device = root_stat.st_dev
        seen.add((root_stat.st_dev, root_stat.st_ino))
        result['allocated'] = root_stat.st_blocks * 512
        result['apparent'] = root_stat.st_size
        def error(_):
            result['complete'] = False
            result['skipped'] += 1
        for folder, dirs, files, fd in os.fwalk(root, follow_symlinks=False, onerror=error):
            if cancel.is_set():
                raise InterruptedError('Inspection cancelled')
            for name in [*dirs, *files]:
                if result['files'] >= limit or time.monotonic() - start > seconds:
                    result['complete'] = False
                    return result
                try:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if name in dirs and (info.st_dev != device or (Path(folder) == root and name == 'dosdevices')):
                        dirs.remove(name)
                        result['skipped'] += 1
                    if info.st_dev != device:
                        continue
                    inode = (info.st_dev, info.st_ino)
                    if inode in seen:
                        continue
                    seen.add(inode)
                    result['files'] += 1
                    result['allocated'] += info.st_blocks * 512
                    result['apparent'] += info.st_size
                    if stat.S_ISLNK(info.st_mode):
                        result['links'] += 1
                        try:
                            os.stat(name, dir_fd=fd)
                        except FileNotFoundError:
                            result['broken_links'] += 1
                        except OSError:
                            error(None)
                except OSError:
                    error(None)
        return result
    except InterruptedError:
        raise
    except OSError:
        result['complete'] = False
        return result


def registry(prefix):
    try:
        path = prefix / 'system.reg'
        if path.is_symlink():
            raise ValueError('Linked registry is not inspected')
        text = read_bounded(path, MAX_REG).decode('utf-8', errors='replace')
        sections = {}
        for part in re.split(r'^\[', text, flags=re.M)[1:]:
            key, _, body = part.partition(']')
            sections[key.replace('\\\\', '\\').casefold()] = body
        architecture = 'x64' if '#arch=win64' in text else 'x86' if '#arch=win32' in text else 'Unknown'
        return sections, architecture, True
    except (OSError, ValueError):
        return {}, 'Unknown', False


def runtime_row(requirement, prefix, architecture, sections, registry_ok, runner):
    folder = 'syswow64' if architecture == 'x64' and requirement.architecture == 'x86' else 'system32'
    files = [pe_evidence(prefix / 'drive_c/windows' / folder / dll, (prefix, runner)) for dll in requirement.dlls]
    if requirement.key.startswith('vc14'):
        keys = [body for key, body in sections.items() if key.endswith('visualstudio\\14.0\\vc\\runtimes\\' + requirement.architecture)]
        registration = any(re.search(r'"Installed"=dword:0*1\b', body, re.I) for body in keys)
    else:
        registration = any('uninstall\\' in key and 'Microsoft Visual C++' in body and
                           requirement.title.split()[2] in body and requirement.architecture in body.casefold()
                           for key, body in sections.items())
    native = [f for f in files if f['origin'] == 'Microsoft native' and f['architecture'] == requirement.architecture]
    versions = [f['version'] for f in native if f['version']]
    verified = len(native) == len(files) and len(versions) == len(files) and min(versions) >= requirement.minimum
    if architecture == 'Unknown' or not registry_ok:
        status = 'Unknown'
    elif verified and registration:
        status = 'Installed'
    elif native:
        status = 'Partial'
    elif any(f['origin'] == 'Unknown' for f in files):
        status = 'Unknown'
    elif registration:
        status = 'Unknown'  # Wine seeds registry claims, even without native files.
    else:
        status = 'Missing'
    return {'key': requirement.key, 'title': requirement.title, 'architecture': requirement.architecture,
            'minimum': version_text(requirement.minimum), 'version': version_text(min(versions) if versions else None),
            'status': status, 'registration': registration, 'files': files,
            'detail': 'Native core files + registry corroborated' if status == 'Installed' else
                      'Registry claim alone does not establish a Microsoft installation' if registration else
                      'Core file evidence only; optional components and game requirements are unknown'}


def context(game, root, default_proton=''):
    from .runner_selection import effective_selector, global_selector, parse_release
    settings = defaults(game, root)
    settings['proton'] = effective_selector(game, default_proton or global_selector(root))
    if parse_release(settings['proton']):
        from .proton_manager import ProtonManager
        manager = ProtonManager(Path(root) / 'proton-manager', create=False)
        settings['proton'] = manager.installed_release(settings['proton']) or settings['proton']
    return settings


def runner_version(runner):
    try:
        text = read_bounded(Path(runner) / 'version', 4096).decode('utf-8', errors='replace').strip()
        first = text.splitlines()[0] if text else ''
        return re.sub(r'^\d+\s+', '', first)[:200] or 'Unknown'
    except (OSError, ValueError):
        return 'Unknown (folder: ' + Path(runner).name + ')'


def inspect_prefix(game, root, default_proton='', cancel=None):
    settings = context(game, root, default_proton)
    configured = Path(settings['prefix']).expanduser()
    prefix = configured.resolve()
    runner = Path(settings['proton']).expanduser()
    runner = runner.resolve() if runner.is_absolute() else Path('/__unresolved_runner__')
    result = {'name': prefix.name, 'path': str(prefix), 'configured_path': str(configured),
              'runner': settings['runner'], 'proton': settings['proton'], 'resolved_proton': str(runner),
              'runner_version': runner_version(runner), 'state': 'Not created', 'architecture': 'Unknown',
              'requirements': 'Unknown — no curated game-specific requirements are recorded. Inventory does not prove game readiness.',
              'runtimes': [], 'builtins': [], 'local': [], 'usage': None, 'settings': settings}
    if not prefix.exists():
        return result
    if not prefix.is_dir():
        result['state'] = 'Invalid path (not a directory)'
        return result
    sections, architecture, registry_ok = registry(prefix)
    result['architecture'] = architecture
    result['state'] = 'Created' if registry_ok and (prefix / 'drive_c/windows').is_dir() else 'Partial / not initialized'
    if configured.is_symlink() or any(p.is_symlink() for p in configured.parents):
        result['state'] += ' · linked path (inspection only)'
    if not (prefix / MARKER).is_file():
        result['state'] += ' · not app-owned (inspection only)'
    result['usage'] = directory_usage(prefix, cancel)
    for requirement in [*RECIPES.values(), *LEGACY]:
        if architecture == 'x86' and requirement.architecture == 'x64':
            continue
        row = runtime_row(requirement, prefix, architecture, sections, registry_ok, runner)
        result['runtimes'].append(row)
        result['builtins'].extend(f for f in row['files'] if f['origin'] == 'Wine/Proton builtin')
    # Observation only: .NET registration is often synthetic; do not accept it as a native install.
    net_claim = any('net framework setup\\ndp' in key for key in sections)
    result['dotnet'] = '.NET: Unknown — ' + ('registry claims present; ' if net_claim else '') + 'native .NET version/coverage not verified; no installation recipe.'
    result['directx'] = 'Unknown — legacy DirectX helper coverage is game-specific; no installation recipe. DXVK/VKD3D belong to the selected runner.'
    for folder in ('system32', 'syswow64'):
        if architecture == 'x86' and folder == 'syswow64':
            continue
        for dll in ('mscoree.dll', 'd3d9.dll', 'd3d11.dll', 'd3d12.dll', 'dxgi.dll', 'd3dx9_43.dll', 'xinput1_3.dll'):
            item = pe_evidence(prefix / 'drive_c/windows' / folder / dll, (prefix, runner))
            if item['origin'] != 'Missing':
                result['builtins'].append({**item, 'component': 'Runner / compatibility component; not an installer package'})
    executable = Path(game.get('executable', '')).expanduser()
    if game.get('executable') and executable.is_absolute():
        result['game_architecture'] = pe_evidence(executable, (executable.parent,))['architecture']
        for dll in sorted({dll for req in [*RECIPES.values(), *LEGACY] for dll in req.dlls}):
            item = pe_evidence(executable.parent / dll, (executable.parent,))
            if item['origin'] != 'Missing':
                result['local'].append(item)
    result['framework_files'] = []
    for architecture, folder in (('x86', 'Framework'), ('x64', 'Framework64')):
        if architecture == 'x64' and result['architecture'] == 'x86':continue
        for dll in ('clr.dll', 'mscorlib.dll'):
            item = pe_evidence(prefix / 'drive_c/windows/Microsoft.NET' / folder / 'v4.0.30319' / dll, (prefix, runner))
            if item['origin'] != 'Missing':result['framework_files'].append(item)
    result['local_scope'] = 'Only known core DLLs beside the selected executable are inspected. Subfolders, loaded dependencies and exact game requirements are unknown.'
    return result


def inventory_text(info):
    lines = [f"Name: {info['name']}", f"Resolved path: {info['path']}", f"Creation state: {info['state']}",
             f"Prefix architecture: {info['architecture']}", f"UMU launcher: {info['runner'] or 'Not configured'}",
             f"Proton: {info['proton']}", f"Resolved runner: {info['resolved_proton']}",
             f"Runner version: {info['runner_version']}",
             f"Game executable architecture: {info.get('game_architecture', 'Unknown')}", '', 'GAME REQUIREMENTS', info['requirements']]
    usage = info['usage']
    if usage:
        lines.insert(4, f"Disk usage: {'at least ' if not usage['complete'] else ''}{usage['allocated'] / 1048576:.1f} MiB allocated; {usage['apparent'] / 1048576:.1f} MiB apparent")
        lines.insert(5, f"{usage['links']} symlinks; {usage['broken_links']} broken links; {usage['skipped']} skipped mappings/mounts/errors. Links not followed; hardlinks counted once; sparse allocation respected.")
    else:
        lines.insert(4, 'Disk usage: unavailable / no prefix created')
    lines += ['', 'PREFIX-WIDE NATIVE RUNTIME PACKAGES']
    for row in info['runtimes']:
        lines += [f"{row['title']} · {row['architecture']} · {row['status']}",
                  f"  Core minimum {row['minimum']}; native file version {row['version']}. {row['detail']}"]
        lines += [f"  {Path(f['path']).name}: {f['origin']} · {f['architecture']} · {version_text(f['version'])}" for f in row['files']]
    lines += [info.get('dotnet', '.NET: Unknown'), info.get('directx', 'DirectX: Unknown'), '',
              'WINE / PROTON AND RUNNER COMPONENTS (READ-ONLY)']
    lines += [f"{f['path']}: {f['origin']} · {f['architecture']} · {version_text(f['version'])}" for f in info['builtins']]
    lines += ['', '.NET FRAMEWORK 4 FILE EVIDENCE (COVERAGE UNKNOWN)']
    lines += [f"{f['path']}: {f['origin']} · {f['architecture']} · {version_text(f['version'])}" for f in info.get('framework_files', [])]
    lines += ['', 'GAME-LOCAL FILES (NOT PREFIX PACKAGES)', info.get('local_scope', 'Unknown')]
    lines += [f"{f['path']}: {f['origin']} · {f['architecture']} · {version_text(f['version'])}" for f in info['local']]
    return '\n'.join(lines)
