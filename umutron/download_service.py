"""Native download boundary and FitGirl catalog lookup."""
import json
import os
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler

DEFAULT_API_KEY = 'mysupersecretkey'


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

def parse_size_bytes(size_str):
    if not size_str or not isinstance(size_str, str): return 0
    s = re.sub(r'\(.*?\)', '', size_str).strip()
    parts = s.split('/')
    last_unit_match = re.search(r'(gb|mb|tb|kb)', s, re.I)
    default_unit = last_unit_match.group(1).upper() if last_unit_match else 'GB'
    max_bytes = 0
    for part in parts:
        m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(gb|mb|tb|kb)?', part, re.I)
        if m:
            val = float(m.group(1))
            unit = (m.group(2) or default_unit).upper()
            mult = {'TB': 1024**4, 'GB': 1024**3, 'MB': 1024**2, 'KB': 1024}.get(unit, 1024**3)
            max_bytes = max(max_bytes, int(val * mult))
    return max_bytes


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
        job.update({
            'status': status,
            'completed_bytes': completed,
            'total_bytes': total,
            'percent': pct,
            'speed_bps': speed,
            'speed_text': speed_text,
            'eta_text': eta_str,
            'files': [f.get('path') for f in data.get('files', []) if f.get('path')]
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
        for cand in p.rglob('*.exe'):
            if cand.is_file(): return cand
        return None


download_manager = TorrentDownloadManager()
class DownloadRelease:
    def __init__(self, provider_id, provider_name, title, file_size, magnet, uris=None, install_strategy='installer', upload_date=None, raw=None):
        self.provider_id = provider_id
        self.provider_name = provider_name
        self.title = title
        self.file_size = file_size
        self.size_bytes = parse_size_bytes(file_size)
        self.magnet = magnet
        self.uris = uris or ([magnet] if magnet else [])
        self.install_strategy = install_strategy
        self.upload_date = upload_date
        self.raw = raw or {}

    def __getitem__(self, key):
        if hasattr(self, key):
            val = getattr(self, key)
            if val is not None: return val
        return self.raw.get(key)

    def get(self, key, default=None):
        if hasattr(self, key):
            val = getattr(self, key)
            if val is not None: return val
        return self.raw.get(key, default)

    def to_dict(self):
        d = dict(self.raw)
        d.update({
            'provider_id': self.provider_id,
            'provider_name': self.provider_name,
            'title': self.title,
            'file_size': self.file_size,
            'size_bytes': self.size_bytes,
            'magnet': self.magnet,
            'uris': self.uris,
            'install_strategy': self.install_strategy,
            'upload_date': self.upload_date,
        })
        return d

    @classmethod
    def from_dict(cls, data):
        if not data or not isinstance(data, dict): return None
        return cls(
            provider_id=data.get('provider_id', 'unknown'),
            provider_name=data.get('provider_name', 'Unknown'),
            title=data.get('title', ''),
            file_size=data.get('file_size', 'Unknown size'),
            magnet=data.get('magnet', ''),
            uris=data.get('uris', []),
            install_strategy=data.get('install_strategy', 'installer'),
            upload_date=data.get('upload_date'),
            raw=data
        )

def normalize_title(title):
    if not title or not isinstance(title, str):
        return ''
    n = unicodedata.normalize('NFKD', title)
    n = ''.join(c for c in n if not unicodedata.combining(c))
    n = n.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    n = n.replace('–', '-').replace('—', '-')
    return n.strip()


def build_search_queries(title):
    norm = normalize_title(title)
    if not norm:
        return []
    queries = [norm]
    if "'" in norm:
        queries.append(norm.replace("'", '’'))
    if ':' in norm:
        queries.append(norm.replace(':', ''))
        queries.append(norm.replace(':', ' - '))
    for sep in (':', ' - '):
        if sep in norm:
            base = norm.split(sep)[0].strip()
            if len(base) > 2 and base not in queries:
                queries.append(base)
    roman_map = [
        (r'\bVIII\b', '8'), (r'\bVII\b', '7'), (r'\bVI\b', '6'),
        (r'\bIV\b', '4'), (r'\bV\b', '5'), (r'\bIII\b', '3'), (r'\bII\b', '2')
    ]
    roman_variant = norm
    for r_pat, arabic in roman_map:
        roman_variant = re.sub(r_pat, arabic, roman_variant)
    if roman_variant != norm and roman_variant not in queries:
        queries.append(roman_variant)
    return queries

class BaseSourceProvider:
    id = ''
    name = ''
    priority = 100
    install_strategy = 'installer'

    def filter_candidates(self, items):
        return [it for it in items if 'patch from' not in it.get('title', '').lower()]

    def search(self, base_url, title, api_key=None, transport=None):
        if not base_url or not title:
            return []
        key = api_key or os.environ.get('UMUTRON_API_KEY') or os.environ.get('INTERNAL_API_KEY') or DEFAULT_API_KEY
        queries = build_search_queries(title)
        seen_queries = set()

        for query in queries:
            q_clean = query.strip()
            if not q_clean or q_clean in seen_queries:
                continue
            seen_queries.add(q_clean)

            params = urlencode({'link_type': 'magnet', 'source_name': self.id, 'q': q_clean, 'limit': 10})
            endpoint = f"{base_url.rstrip('/')}/api/downloads?{params}"

            try:
                if transport is not None:
                    data = transport(endpoint)
                else:
                    req = Request(endpoint, headers={'x-api-key': key, 'Accept': 'application/json',
                                                      'User-Agent': f'UmuTron/provider-{self.id}'})
                    with build_opener(ProxyHandler({})).open(req, timeout=15) as resp:
                        data = json.loads(resp.read().decode('utf-8'))

                items = data.get('data', [])
                if items:
                    candidates = self.filter_candidates(items)
                    results = []
                    for item in candidates:
                        uris = item.get('uris', [])
                        magnet = next((u for u in uris if u.startswith('magnet:')), None)
                        if magnet:
                            rel = DownloadRelease(
                                provider_id=self.id,
                                provider_name=self.name,
                                title=item.get('title', title),
                                file_size=item.get('file_size') or 'Unknown size',
                                magnet=magnet,
                                uris=uris,
                                install_strategy=self.install_strategy,
                                upload_date=item.get('upload_date'),
                                raw=item
                            )
                            results.append(rel)
                    if results:
                        return results
            except Exception:
                continue

        return []


class FitGirlProvider(BaseSourceProvider):
    id = 'fitgirl'
    name = 'FitGirl'
    priority = 10
    install_strategy = 'installer'


class DODIProvider(BaseSourceProvider):
    id = 'dodi'
    name = 'DODI'
    priority = 20
    install_strategy = 'installer'

    def filter_candidates(self, items):
        return [it for it in items if 'patch' not in it.get('title', '').lower()]


class ByXatabProvider(BaseSourceProvider):
    id = 'byxatab'
    name = 'ByXatab'
    priority = 30
    install_strategy = 'installer'

    def filter_candidates(self, items):
        full = [it for it in items if 'патч' not in it.get('title', '').lower() and 'patch' not in it.get('title', '').lower()]
        return full if full else items


class AnkerGamesProvider(BaseSourceProvider):
    id = 'ankergames'
    name = 'AnkerGames'
    priority = 40
    install_strategy = 'portable'


class SourceProviderRegistry:
    def __init__(self):
        self._providers = {}
        for p in (FitGirlProvider(), DODIProvider(), ByXatabProvider(), AnkerGamesProvider()):
            self.register(p)

    def register(self, provider):
        self._providers[provider.id] = provider

    def get(self, provider_id):
        return self._providers.get(provider_id)

    def providers(self):
        return sorted(self._providers.values(), key=lambda p: p.priority)

    def search_all(self, base_url, title, api_key=None, transport=None):
        for provider in self.providers():
            results = provider.search(base_url, title, api_key=api_key, transport=transport)
            if results:
                return results
        return []

source_registry = SourceProviderRegistry()


class DownloadSourceCache:
    def __init__(self, cache_file=None):
        if cache_file is None:
            root = Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share')) / 'umutron'
            cache_file = root / 'source-releases-cache.json'
        self.path = Path(cache_file)
        self.legacy_path = self.path.parent / 'fitgirl-cache.json'
        self.data = {}
        self._load()

    def _load(self):
        if self.path.is_file():
            try: self.data = json.loads(self.path.read_text())
            except Exception: pass
        elif self.legacy_path.is_file():
            try:
                legacy = json.loads(self.legacy_path.read_text())
                for k, v in legacy.items():
                    if v and isinstance(v, dict):
                        v.setdefault('provider_id', 'fitgirl')
                        v.setdefault('provider_name', 'FitGirl')
                        v.setdefault('install_strategy', 'installer')
                    self.data[k] = v
            except Exception: pass

    def get(self, title):
        if not title: return None
        val = self.data.get(title.strip().lower())
        if val is None: return None
        if val is False: return False
        return DownloadRelease.from_dict(val)

    def set(self, title, release):
        if not title: return
        key = title.strip().lower()
        self.data[key] = release.to_dict() if isinstance(release, DownloadRelease) else (release if isinstance(release, dict) else False)
        try:
            from .library import atomic_write
            atomic_write(self.path, json.dumps(self.data, indent=2).encode())
        except Exception:
            pass

source_cache = DownloadSourceCache()
fitgirl_cache = source_cache


def search_game_release(base_url, title, api_key=None, transport=None, provider_id=None):
    cached = source_cache.get(title)
    if cached is not None:
        return cached if isinstance(cached, DownloadRelease) else None

    if provider_id:
        prov = source_registry.get(provider_id)
        results = prov.search(base_url, title, api_key=api_key, transport=transport) if prov else []
    else:
        results = source_registry.search_all(base_url, title, api_key=api_key, transport=transport)

    if results:
        best = results[0]
        source_cache.set(title, best)
        return best

    source_cache.set(title, False)
    return None


def search_fitgirl_repack(base_url, title, api_key=None, transport=None):
    prov = source_registry.get('fitgirl')
    if not prov: return []
    results = prov.search(base_url, title, api_key=api_key, transport=transport)
    if results:
        source_cache.set(title, results[0])
    else:
        source_cache.set(title, False)
    return results

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
