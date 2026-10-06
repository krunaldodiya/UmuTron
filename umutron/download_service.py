"""Native download boundary and source-discovery compatibility exports."""
import json
import os
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler

from .sources import (
    DownloadRelease, DownloadSource, DownloadSourceCache, SourceProviderRegistry,
    build_search_queries, normalize_title, search_game_release, search_game_releases,
    source_cache, source_registry,
)

from .sources.model import parse_size_bytes
from .payload_pipeline import (
    InstallerType, PayloadInfo, PayloadKind, classify_payload,
    extract_archive, get_silent_installer_arguments, is_pe_executable,
    rank_game_executables, run_native_innoextract, stage_portable_game,
)


class InstallUnavailable(RuntimeError):
    pass


class UnavailableInstallService:
    reason = 'Automatic game downloads are not configured yet.'

    def availability(self, game_id, metadata_identity):
        return {'available': False, 'reason': self.reason}

    def start(self, request):
        raise InstallUnavailable(self.reason)

    def snapshot(self, job_id):
        raise InstallUnavailable('No download job exists.')

    def cancel(self, job_id):
        raise InstallUnavailable('No download job exists.')

    def resume(self, job_id):
        raise InstallUnavailable('No download job exists.')



def format_size(bytes_val):
    if bytes_val is None or bytes_val <= 0: return '0 B'
    val = float(bytes_val)
    for u in ('B', 'KB', 'MB', 'GB', 'TB'):
        if val < 1024 or u == 'TB':
            return f'{val:.1f} {u}' if u != 'B' else f'{int(val)} B'
        val /= 1024


def estimate_space_requirements(installer_bytes):
    installed_bytes = int(installer_bytes * 3.33)
    total_required = installer_bytes + installed_bytes
    return installer_bytes, installed_bytes, total_required
PUBLIC_TRACKERS = [
    'udp://tracker.opentrackr.org:1337/announce',
    'udp://open.tracker.cl:1337/announce',
    'udp://opentracker.i2p.rocks:6969/announce',
    'udp://tracker.torrent.eu.org:451/announce',
    'udp://open.demonii.com:1337/announce',
    'udp://tracker.openbittorrent.com:80/announce',
    'udp://exodus.desync.com:6969/announce',
    'http://tracker.openbittorrent.com:80/announce',
    'udp://tracker.dler.org:6969/announce',
]


def enrich_magnet_uri(magnet):
    if not magnet or not magnet.startswith('magnet:'): return magnet
    if '&tr=' in magnet: return magnet
    from urllib.parse import quote
    tr_params = '&'.join([f'tr={quote(t)}' for t in PUBLIC_TRACKERS])
    return f'{magnet}&{tr_params}'



def ensure_downloader_binary():
    import shutil
    system_bin = shutil.which('aria2c')
    if system_bin and os.access(system_bin, os.X_OK):
        return system_bin
    tools_dir = Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share')) / 'umutron' / 'tools'
    local_bin = tools_dir / 'aria2c'
    if local_bin.is_file() and os.access(local_bin, os.X_OK):
        return str(local_bin)
    import zipfile
    tools_dir.mkdir(parents=True, exist_ok=True)
    zip_path = tools_dir / 'aria2.zip'
    url = 'https://github.com/abcfy2/aria2-static-build/releases/download/1.37.0/aria2-x86_64-linux-musl_static.zip'
    req = Request(url, headers={'User-Agent': 'UmuTron'})
    with build_opener(ProxyHandler({})).open(req, timeout=30) as resp:
        zip_path.write_bytes(resp.read())
    with zipfile.ZipFile(zip_path) as z:
        z.extract('aria2c', path=tools_dir)
    zip_path.unlink(missing_ok=True)
    local_bin.chmod(0o755)
    return str(local_bin)

def ensure_7z_binary():
    import shutil, io, tarfile
    for name in ('7zz', '7z', '7za'):
        system_bin = shutil.which(name)
        if system_bin and os.access(system_bin, os.X_OK):
            return system_bin
    tools_dir = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'umutron' / 'tools'
    local_bin = tools_dir / '7zz'
    if local_bin.is_file() and os.access(local_bin, os.X_OK):
        return str(local_bin)
    tools_dir.mkdir(parents=True, exist_ok=True)
    url = 'https://www.7-zip.org/a/7z2603-linux-x64.tar.xz'
    try:
        req = Request(url, headers={'User-Agent': 'UmuTron'})
        with build_opener(ProxyHandler({})).open(req, timeout=30) as resp:
            data = resp.read()
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:xz') as tar:
            member = tar.extractfile('7zz')
            if member:
                local_bin.write_bytes(member.read())
                local_bin.chmod(0o755)
                return str(local_bin)
    except Exception:
        pass
    return None


def ensure_innoextract_binary():
    import shutil, io, tarfile
    system_bin = shutil.which('innoextract')
    if system_bin and os.access(system_bin, os.X_OK):
        return system_bin
    tools_dir = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'umutron' / 'tools'
    local_bin = tools_dir / 'innoextract'
    if local_bin.is_file() and os.access(local_bin, os.X_OK):
        return str(local_bin)
    tools_dir.mkdir(parents=True, exist_ok=True)
    url = 'https://constexpr.org/innoextract/files/innoextract-1.9-linux.tar.xz'
    try:
        req = Request(url, headers={'User-Agent': 'UmuTron'})
        with build_opener(ProxyHandler({})).open(req, timeout=30) as resp:
            data = resp.read()
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:xz') as tar:
            for m in tar.getmembers():
                if m.name.endswith('innoextract') and m.isfile():
                    member = tar.extractfile(m)
                    if member:
                        local_bin.write_bytes(member.read())
                        local_bin.chmod(0o755)
                        return str(local_bin)
    except Exception:
        pass
    return None


class TorrentDownloadManager:
    def __init__(self):
        self.port = 6812
        self.secret = 'umutron-rpc-secret'
        self.active_jobs = {}
        self._daemon_started = False

    def _ensure_daemon(self):
        if self._daemon_started: return True
        bin_path = ensure_downloader_binary()
        import subprocess, time
        cmd = [
            bin_path,
            '--enable-rpc',
            f'--rpc-listen-port={self.port}',
            '--rpc-listen-all=false',
            '--daemon=true',
            f'--rpc-secret={self.secret}',
            '--enable-dht=true',
            '--enable-dht6=true',
            '--dht-entry-point=router.bittorrent.com:6881',
            '--dht-entry-point6=dht.transmissionbt.com:6881',
            '--enable-peer-exchange=true',
            '--bt-enable-lpd=true',
            '--bt-max-peers=100',
            '--seed-time=0',
            '--follow-torrent=mem',
            f'--bt-tracker={",".join(PUBLIC_TRACKERS)}',
            '--max-connection-per-server=8',
            '--split=8',
            '--summary-interval=0'
        ]
        try:
            subprocess.run(cmd, check=True)
            self._daemon_started = True
            time.sleep(0.4)
            return True
        except Exception:
            return False

    def _rpc(self, method, params=None):
        self._ensure_daemon()
        payload = json.dumps({
            'jsonrpc': '2.0',
            'id': 'umutron',
            'method': method,
            'params': [f'token:{self.secret}'] + (params or [])
        }).encode()
        req = Request(f'http://127.0.0.1:{self.port}/jsonrpc', data=payload, headers={'Content-Type': 'application/json'})
        with build_opener(ProxyHandler({})).open(req, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def start_download(self, magnet_uri, download_dir, game_id, title=''):
        import time
        magnet_uri = enrich_magnet_uri(magnet_uri)
        Path(download_dir).mkdir(parents=True, exist_ok=True)
        res = self._rpc('aria2.addUri', [[magnet_uri], {'dir': str(download_dir)}])
        gid = res.get('result')
        if not gid:
            raise RuntimeError('Failed to start torrent download')
        job = {
            'gid': gid,
            'active_gid': gid,
            'game_id': game_id,
            'title': title,
            'dir': str(download_dir),
            'magnet': magnet_uri,
            'status': 'active',
            'started_at': time.time(),
        }
        self.active_jobs[game_id] = job
        return job

    def get_status(self, game_id):
        job = self.active_jobs.get(game_id)
        if not job:
            return None
        current_gid = job.get('active_gid', job['gid'])
        try:
            data = self._rpc('aria2.tellStatus', [current_gid]).get('result', {})
            followed = data.get('followedBy', [])
            if followed:
                job['active_gid'] = followed[0]
                current_gid = followed[0]
                data = self._rpc('aria2.tellStatus', [current_gid]).get('result', {})
        except Exception:
            return {**job, 'percent': 0.0, 'speed_text': '0 B/s', 'eta_text': ''}
        status = data.get('status', 'active')
        completed = int(data.get('completedLength', 0))
        total = int(data.get('totalLength', 0))
        speed = int(data.get('downloadSpeed', 0))
        pct = (completed / total * 100.0) if total > 0 else 0.0
        connections = data.get('connections', '0')
        speed_text = f"{format_size(speed)}/s" if total > 0 else f"Connecting ({connections} peers)..."
        eta = ((total - completed) // speed) if speed > 0 and total > completed else 0
        eta_str = f"{eta // 60}m {eta % 60}s" if eta >= 60 else f"{eta}s" if eta > 0 else ""
        files = [f.get('path') for f in data.get('files', []) if isinstance(f.get('path'), str) and f.get('path')]
        job.update({
            'status': status,
            'completed_bytes': completed,
            'total_bytes': total,
            'percent': pct,
            'speed_bps': speed,
            'speed_text': speed_text,
            'eta_text': eta_str,
            'files': files,
        })
        return job

    def pause(self, game_id):
        job = self.active_jobs.get(game_id)
        gid = job.get('active_gid', job.get('gid')) if job else None
        if gid:
            try: self._rpc('aria2.pause', [gid])
            except Exception: pass
            job['status'] = 'paused'
            return True
        return False

    def resume(self, game_id):
        job = self.active_jobs.get(game_id)
        gid = job.get('active_gid', job.get('gid')) if job else None
        if gid:
            try: self._rpc('aria2.unpause', [gid])
            except Exception: pass
            job['status'] = 'active'
            return True
        return False

    def cancel(self, game_id, cleanup=True):
        job = self.active_jobs.pop(game_id, None)
        if job:
            for g in {job.get('gid'), job.get('active_gid')}:
                if g:
                    try: self._rpc('aria2.remove', [g])
                    except Exception: pass
            if cleanup:
                import shutil
                folder = Path(job['dir'])
                if folder.is_dir() and '.umutron-downloads' in folder.parts:
                    shutil.rmtree(folder, ignore_errors=True)
            return True
        return False

    def find_setup_exe(self, download_dir):
        p = Path(download_dir)
        if not p.is_dir(): return None
        for cand in p.rglob('setup.exe'):
            if cand.is_file(): return cand
        return None

    def inspect_payload(self, download_dir):
        return classify_payload(Path(download_dir))

    def detect_main_executable(self, folder, title='', verified=False):
        ranked = rank_game_executables(Path(folder), title)
        return next((exe for exe in ranked if not verified or (not exe.is_symlink() and is_pe_executable(exe))), None)

    def stage_portable(self, source_dir, target_dir):
        return stage_portable_game(Path(source_dir), Path(target_dir))

    def get_silent_args(self, installer_type, target_dir):
        return get_silent_installer_arguments(installer_type, Path(target_dir))

    def run_innoextract(self, setup_exe, target_dir):
        return run_native_innoextract(Path(setup_exe), Path(target_dir))

    def extract_container(self, container_path, output_dir):
        return extract_archive(Path(container_path), Path(output_dir))


download_manager = TorrentDownloadManager()

def configured_game(game):
    """Keep configured/unmounted games playable for the normal launch checks."""
    return bool(game.get('executable')) and (game.get('installation', {}).get('mode') != 'installer'
                                            or bool(game['installation'].get('confirmed')))


def detail_actions(game, saved, fullscreen, payload_exists=False, recovery=False):
    configured = configured_game(game)
    return {'primary': 'Play' if configured else 'Install',
            'setup': saved and configured and not fullscreen, 'remove': saved,
            'uninstall': saved and configured and payload_exists,
            'resume_uninstall': saved and recovery}
