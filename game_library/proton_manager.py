"""Official GE/UMU releases, staged checksum-verified runner installation."""
import fcntl
import hashlib
import json
from itertools import islice
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import tarfile
import tempfile
import threading
import time
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .library import atomic_write
from .runner_selection import AUTOMATIC, effective_selector, parse_release, release_selector
from . import runner_guard

REPOS={'GE-Proton':'GloriousEggroll/proton-ge-custom','UMU-Proton':'Open-Wine-Components/umu-proton'}
HOSTS={'api.github.com','github.com','objects.githubusercontent.com','release-assets.githubusercontent.com'}
MAX_DOWNLOAD=2*1024**3
MAX_EXPANDED=8*1024**3


def trusted(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,443):raise ValueError('Unexpected upstream download address.')
    return url


class Redirects(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        trusted(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)


def fetch(url):
    with build_opener(Redirects).open(Request(trusted(url),headers={'User-Agent':'GameLibraryLauncher/0.2','Accept':'application/vnd.github+json'}),timeout=25) as response:
        data=response.read(4*1024*1024+1)
    if len(data)>4*1024*1024:raise ValueError('Release response is too large.')
    return json.loads(data)


def validate_release(release, arch):
    family = release.get('family')
    repo = REPOS.get(family)
    if not repo:
        raise ValueError('Runner source is not an official supported release.')
    tag = release.get('version', '')
    parse_release('release:' + family + ':' + tag)
    name = release.get('name', '')
    architecture = release.get('architecture')
    if architecture != arch or arch not in ('x86_64', 'aarch64'):
        raise ValueError('Runner architecture does not match this host.')
    allowed = {tag + '.tar.gz', tag + '-' + arch + '.tar.gz'}
    if name not in allowed or (arch == 'aarch64' and name == tag + '.tar.gz'):
        raise ValueError('Invalid runner release archive name.')
    base = 'https://github.com/' + repo + '/releases/download/' + tag + '/'
    if release.get('url') != base + name:
        raise ValueError('Runner URL does not identify this exact official release.')
    checksum = release.get('checksum_url', '')
    if checksum and checksum != base + name.removesuffix('.tar.gz') + '.sha512sum':
        raise ValueError('Unexpected checksum source.')
    digest = release.get('digest', '')
    if digest and not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
        raise ValueError('Invalid published checksum.')
    if not checksum and not digest:
        raise ValueError('No published checksum available.')
    size = release.get('size', 0)
    if type(size) is not int or not 0 < size <= MAX_DOWNLOAD:
        raise ValueError('Invalid runner archive size.')
    return release


def release_items(payload, family, arch):
    results = []
    if not isinstance(payload, list):
        raise ValueError('Invalid upstream release response.')
    for release in payload:
        if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
            continue
        tag = release.get('tag_name', '')
        assets = release.get('assets', [])
        for asset in assets:
            name = asset.get('name', '')
            if not name.endswith('.tar.gz'):
                continue
            architecture = 'aarch64' if 'aarch64' in name or 'arm64' in name else 'x86_64'
            checks = next((a for a in assets if a.get('name') == name.removesuffix('.tar.gz') + '.sha512sum'), None)
            item = {'family': family, 'version': tag, 'architecture': architecture, 'name': name,
                    'url': asset.get('browser_download_url', ''), 'size': asset.get('size', 0),
                    'digest': asset.get('digest') or '', 'checksum_url': checks.get('browser_download_url', '') if checks else '',
                    'source': 'https://github.com/' + REPOS[family]}
            try:
                validate_release(item, arch)
            except (ValueError, TypeError):
                continue
            results.append(item)
    return results


def download(url,destination,limit,cancel,progress):
    with build_opener(Redirects).open(Request(trusted(url),headers={'User-Agent':'GameLibraryLauncher/0.2'}),timeout=25) as response,Path(destination).open('xb') as output:
        size=0
        while chunk:=response.read(1024*1024):
            if cancel.is_set():raise InterruptedError('Installation cancelled.')
            size+=len(chunk)
            if size>limit:raise ValueError('Download exceeds expected size.')
            output.write(chunk);progress(size)
        output.flush();os.fsync(output.fileno())
    return size


def extract(archive,destination,cancel):
    destination=Path(destination)
    with tarfile.open(archive,'r:gz') as tar:
        members=[];total=0;roots=set();seen=set()
        for item in tar:
            if cancel.is_set():raise InterruptedError('Installation cancelled.')
            path=PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or '\\' in item.name or not path.parts:raise ValueError('Unsafe archive path.')
            if not (item.isdir() or item.isfile() or item.issym() or item.islnk()):raise ValueError('Unsupported archive entry.')
            key=str(path)
            if key in seen and not item.isdir():raise ValueError('Duplicate archive entry.')
            seen.add(key);roots.add(path.parts[0]);total+=item.size
            if total>MAX_EXPANDED or len(members)>=150000:raise ValueError('Runner archive exceeds safe limits.')
            members.append(item)
        if len(roots)!=1:raise ValueError('Runner archive must have one top-level folder.')
        if shutil.disk_usage(destination).free<total+128*1024**2:raise ValueError('Not enough free space to extract this runner.')
        # Extract files before links; never write a file through an archive-created symlink.
        for item in members:
            if item.issym() or item.islnk():continue
            target=destination/item.name
            if item.isdir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(item) as source,target.open('xb') as out:
                    while chunk:=source.read(1024*1024):
                        if cancel.is_set():raise InterruptedError('Installation cancelled.')
                        out.write(chunk)
                target.chmod(item.mode&0o777)
        for item in members:
            if not (item.issym() or item.islnk()):continue
            if cancel.is_set():raise InterruptedError('Installation cancelled.')
            target=destination/item.name;target.parent.mkdir(parents=True,exist_ok=True)
            link=(target.parent/item.linkname) if item.issym() else (destination/item.linkname)
            if PurePosixPath(item.linkname).is_absolute() or not link.resolve().is_relative_to(destination.resolve()):raise ValueError('Archive link escapes the installation.')
            if item.issym():target.symlink_to(item.linkname)
            else:
                if not link.is_file() or link.is_symlink():raise ValueError('Invalid archive hard link.')
                os.link(link,target)
        root=destination/next(iter(roots))
        if not (root/'proton').is_file() or not (root/'proton').resolve().is_relative_to(root.resolve()):raise ValueError('Archive has no usable proton launcher.')
        # Verify all link chains after creation as well.
        for item in members:
            if item.issym() and not (destination/item.name).resolve().is_relative_to(root.resolve()):raise ValueError('Archive link chain escapes the runner.')
        return root


def runner_label(value):
    """Presentation only: never replace a saved automatic selector with a path."""
    if value == 'UMU-Latest':return 'UMU-Proton — automatic latest'
    if value == 'GE-Latest':return 'GE-Proton — automatic latest'
    from .prefix_inventory import runner_version
    path=Path(value).expanduser()
    installed=path.is_dir() and (path/'proton').is_file()
    version=runner_version(path)
    name=path.name if version.startswith('Unknown') else version
    return name + (' — installed' if installed else ' — unavailable')


def runner_choices(paths,selected):
    """Dedupe real installations while retaining the exact stored selection value."""
    installed={str(Path(path).expanduser().resolve()):str(Path(path).expanduser().resolve()) for path in paths}
    if selected and selected not in ('UMU-Latest','GE-Latest'):
        canonical=str(Path(selected).expanduser().resolve())
        # Keep a saved symlink/custom spelling attached to its existing canonical item.
        installed[canonical]=selected
    values=['UMU-Latest','GE-Latest',*[installed[path] for path in sorted(installed)]]
    labels=[runner_label(value) for value in values]
    labels=[text+' · '+value if labels.count(text)>1 else text for text,value in zip(labels,values)]
    return values,labels


BUSY = {'Waiting', 'Downloading', 'Verifying', 'Installing'}


class ProtonManager:
    def __init__(self, root, transport=fetch, downloader=download, arch=None, create=True, umu_root=None):
        self.root = Path(root).absolute()
        self.tools = self.root / 'runners'
        self.umu_tools = Path(umu_root) if umu_root is not None else Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'umu/compatibilitytools'
        if create:
            self.tools.mkdir(parents=True, exist_ok=True)
        self.transport, self.downloader = transport, downloader
        self.arch = arch or platform.machine()
        self.lock, self.jobs = threading.Lock(), {}

    def installed(self):
        # Bounded direct UMU discovery, never a recursive/client-library scan.
        paths = {str(p) for p in self.tools.iterdir() if not p.is_symlink() and p.is_dir() and (p / 'proton').is_file() and not p.name.startswith('.')} if self.tools.is_dir() else set()
        try:
            for path in islice(self.umu_tools.iterdir(), 256):
                if path.name.startswith(('UMU-', 'GE-')) and path.is_dir() and (path / 'proton').is_file():
                    paths.add(str(path.absolute()))
        except OSError:
            pass
        try:
            data = self._library_data()
            values = [data.get('settings', {}).get('default_proton', '')]
            for game in data.get('games', []):
                values.extend(game.get(key, {}).get('proton', '') for key in ('launch', 'installation'))
            paths.update(v for v in values if isinstance(v, str) and Path(v).is_absolute() and (Path(v) / 'proton').is_file())
        except (OSError, ValueError):
            pass
        return sorted(paths)

    def _library_data(self):
        path = self.root.parent / 'library.json'
        if not path.exists():
            return {}
        if path.stat().st_size > 32 * 1024**2:
            raise ValueError('Library is too large to verify runner references.')
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError('Cannot verify runner references.')
        return data

    def cached(self, family, page=1):
        self._page(family, page)
        try:
            path = self.root / f'releases-{family}-{page}.json'
            if path.stat().st_size > 4 * 1024**2:
                return []
            return release_items(json.loads(path.read_text()), family, self.arch)
        except (OSError, ValueError, TypeError):
            return []

    def _page(self, family, page):
        if family not in REPOS or type(page) is not int or not 1 <= page <= 100:
            raise ValueError('Invalid release page.')
        if self.arch not in ('x86_64', 'aarch64'):
            raise ValueError('Runner downloads currently support x86_64 and aarch64 hosts only.')

    def has_more(self, family, page):
        try:
            return page < 100 and len(json.loads((self.root / f'releases-{family}-{page}.json').read_text())) == 20
        except (OSError, ValueError, TypeError):
            return False

    def releases(self, family, page=1, refresh=False):
        self._page(family, page)
        cache = self.root / f'releases-{family}-{page}.json'
        if cache.is_file() and not refresh and time.time() - cache.stat().st_mtime < 3600:
            return self.cached(family, page)
        data = self.transport(f'https://api.github.com/repos/{REPOS[family]}/releases?per_page=20&page={page}')
        items = release_items(data, family, self.arch)
        atomic_write(cache, json.dumps(data).encode())
        return items

    def resolve(self, selector):
        selection = parse_release(selector)
        if selection:
            family, tag = selection
            for path in sorted(self.root.glob('releases-' + family + '-*.json')):
                try:
                    page = int(path.stem.rsplit('-', 1)[1])
                    found = next((r for r in self.cached(family, page) if r['version'] == tag), None)
                    if found:
                        return found
                except ValueError:
                    continue
            payload = self.transport(f'https://api.github.com/repos/{REPOS[family]}/releases/tags/{tag}')
            items = release_items([payload], family, self.arch)
            found = next((r for r in items if r['version'] == tag), None)
            if found:
                return found
            raise ValueError('This exact release has no verified archive for this computer.')
        raise ValueError('Select an exact downloadable Proton release.')

    def target(self, release):
        validate_release(release, self.arch)
        return self.tools / release['name'].removesuffix('.tar.gz')

    def installed_release(self, selector):
        """Local-only resolution; receipt proves which exact archive was installed."""
        parsed = parse_release(selector)
        if not parsed:
            return None
        if not self.tools.is_dir():
            return None
        for path in self.tools.iterdir():
            if path.is_symlink() or not path.is_dir():
                continue
            receipt = path / 'umutron-release.json'
            try:
                if receipt.is_symlink() or receipt.stat().st_size > 16384:
                    continue
                release = json.loads(receipt.read_text())
                if release_selector(release) == selector and self.target(release) == path and (path / 'proton').is_file():
                    return str(path)
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return None

    def status(self, release):
        target = self.target(release)
        with self.lock:
            job = self.jobs.get(release['name'])
            if job and job['state'] in BUSY:
                return dict(job)
        verified = self.installed_release(release_selector(release))
        if verified:
            return {'state': 'Installed', 'path': verified, 'progress': 1, 'error': ''}
        with self.lock:
            if job and job['state'] in {'Failed', 'Cancelled'}:
                return dict(job)
        collision = target.exists() or target.is_symlink()
        return {'state': 'Available', 'path': '', 'progress': 0,
                'error': 'An existing installation occupies this destination. It is preserved; this release cannot be downloaded into the same folder.' if collision else ''}

    def local_origin(self, path):
        path = Path(path).absolute()
        if path.parent == self.umu_tools.absolute():
            return 'UMU-managed folder · not removable here'
        if self.managed(path):
            receipt=path/'umutron-release.json'
            try:
                if not receipt.is_symlink() and receipt.stat().st_size<=16384:
                    release=json.loads(receipt.read_text())
                    if self.installed_release(release_selector(release))==str(path):
                        return 'Verified managed installation'
            except (OSError,ValueError,KeyError,TypeError):
                pass
            return 'Local installation · release identity unverified'
        return 'Custom folder · not removable here'

    def cancel(self, release):
        with self.lock:
            job = self.jobs.get(release['name'])
            if job and job['state'] in BUSY:
                job['cancel'].set()

    def install(self, release, active_runner=None):
        target = self.target(release)
        with self.lock:
            job = self.jobs.get(release['name'])
            if job and job['state'] in BUSY:
                return  # Same request attaches to the existing installation.
            if target.exists() or target.is_symlink():
                raise ValueError('That runner is already installed; it will not be overwritten.')
            job = {'state': 'Waiting', 'progress': 0, 'error': '', 'path': '', 'cancel': threading.Event()}
            self.jobs[release['name']] = job
        threading.Thread(target=self._install, args=(release, job), daemon=True).start()

    def _install(self, release, job):
        try:
            path = self.ensure(release, job['cancel'], lambda **kw: self._update(job, **kw))
            self._update(job, state='Installed', progress=1, path=path)
        except Exception as error:
            self._update(job, state='Cancelled' if isinstance(error, InterruptedError) else 'Failed', error=str(error)[:1000])

    def ensure(self, release, cancel, progress=lambda **kw: None):
        """Verified atomic install. Same-target waiters reuse completion across processes."""
        target = self.target(release)
        self._safe_tools()
        lease = runner_guard.acquire(target)
        fd = None
        try:
            fd = os.open(self.root / 'runner-install.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            while True:
                if cancel.is_set():
                    raise InterruptedError('Proton installation cancelled.')
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    progress(state='Waiting')
                    time.sleep(.05)
            existing = self.installed_release(release_selector(release))
            if existing:
                return existing
            if target.exists() or target.is_symlink():
                raise ValueError('Runner folder already exists without a matching verified receipt; it was preserved.')
            # Under the install lock only: no concurrent installer can own these stages.
            stages = self.root / 'staging'
            if stages.is_symlink():
                raise ValueError('Unsafe Proton staging folder.')
            stages.mkdir(exist_ok=True)
            for stale in (*stages.glob('install-*'), *self.tools.glob('.install-*')):
                if stale.is_dir() and not stale.is_symlink():
                    shutil.rmtree(stale)
            if shutil.disk_usage(self.tools).free < release['size'] * 5 + 128 * 1024**2:
                raise ValueError('Not enough free space for download and extraction.')
            with tempfile.TemporaryDirectory(prefix='install-', dir=stages) as temp:
                folder = Path(temp)
                archive = folder / release['name']
                progress(state='Downloading', progress=0)
                self.downloader(release['url'], archive, release['size'], cancel,
                                lambda n: progress(state='Downloading', progress=min(1, n / release['size']), downloaded_bytes=n, total_bytes=release['size']))
                if archive.stat().st_size != release['size']:
                    raise ValueError('Incomplete runner download. Retry to download the archive again.')
                progress(state='Verifying')
                digest = release.get('digest', '')
                if digest:
                    with archive.open('rb') as stream:
                        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
                    if actual != digest.split(':', 1)[1]:
                        raise ValueError('Runner checksum verification failed.')
                if release.get('checksum_url'):
                    checksum = folder / 'checksum.txt'
                    self.downloader(release['checksum_url'], checksum, 16384, cancel, lambda _: None)
                    expected = None
                    for line in checksum.read_text().splitlines():
                        parts = line.split()
                        if len(parts) == 2 and parts[-1].lstrip('*') == release['name'] and re.fullmatch(r'[a-fA-F0-9]{128}', parts[0]):
                            expected = parts[0].lower()
                    if expected is None:
                        raise ValueError('Published checksum does not identify this runner archive.')
                    with archive.open('rb') as stream:
                        actual = hashlib.file_digest(stream, 'sha512').hexdigest()
                    if actual != expected:
                        raise ValueError('Published runner checksum verification failed.')
                if cancel.is_set():
                    raise InterruptedError('Proton installation cancelled.')
                progress(state='Installing')
                stage = folder / 'unpacked'
                stage.mkdir()
                runner = extract(archive, stage, cancel)
                receipt = runner / 'umutron-release.json'
                if receipt.exists() or receipt.is_symlink():
                    raise ValueError('Archive contains a reserved receipt path.')
                atomic_write(receipt, json.dumps(release).encode())
                if target.exists() or target.is_symlink():
                    raise ValueError('Runner appeared during installation; it was preserved.')
                if cancel.is_set():
                    raise InterruptedError('Proton installation cancelled.')
                runner.rename(target)
                return str(target)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(lease)

    def _safe_tools(self):
        for path in (self.tools, *self.tools.parents):
            if path.is_symlink():
                raise ValueError('Managed runner folders must not use symbolic links.')
        if self.tools.stat().st_uid != os.getuid():
            raise ValueError('Managed runners must be owned by this user.')

    def managed(self, path):
        target = Path(path).absolute()
        return target.parent == self.tools and not target.is_symlink() and target.is_dir() and (target / 'proton').is_file() and not target.name.startswith('.')

    def references(self, path):
        target = Path(path).resolve()
        data = self._library_data()
        def matches(value):
            if not value or value in AUTOMATIC or value == 'default':
                return False
            if parse_release(value):
                actual = self.installed_release(value)
                return bool(actual and Path(actual).resolve() == target)
            return Path(value).expanduser().is_absolute() and Path(value).expanduser().resolve() == target
        refs = []
        if matches(data.get('settings', {}).get('default_proton', '')):
            refs.append('App default')
        for game in data.get('games', []):
            # A deliberate per-game override supersedes a historical installer
            # pin; an empty legacy override still references that exact pin.
            if matches(effective_selector(game, data.get('settings', {}).get('default_proton') or 'UMU-Latest')):
                refs.append(game.get('title') or 'Untitled game')
        return refs

    def uninstall(self, path):
        """Only direct managed children; never prefixes, saves or custom folders."""
        self._safe_tools()
        if not self.managed(path):
            raise ValueError('Only runners installed in UmuTron’s managed folder can be uninstalled here.')
        target = Path(path).absolute()
        launch_fd = os.open(self.root.parent / 'launch.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        lease = None
        try:
            try:
                fcntl.flock(launch_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Finish the active game, installer or prefix operation before uninstalling.') from None
            lease = runner_guard.acquire(target, exclusive=True)
            references = self.references(target)
            if references:
                raise ValueError('Choose another Proton version for: ' + ', '.join(references) + '. Then retry uninstalling.')
            runner_guard.ensure_idle(target)
            if not self.managed(target):
                raise ValueError('Runner location changed; nothing was removed.')
            shutil.rmtree(target)
            with self.lock:
                self.jobs.pop(target.name + '.tar.gz', None)
        finally:
            if lease is not None:
                os.close(lease)
            os.close(launch_fd)

    def _update(self, job, **changes):
        with self.lock:
            job.update(changes)

    def busy(self):
        with self.lock:
            return any(j['state'] in BUSY for j in self.jobs.values())
