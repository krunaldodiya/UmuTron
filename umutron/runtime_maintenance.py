"""Install-only curated Microsoft runtime recipes. No shell, verbs, repair or removal."""
import hashlib
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .launcher import MARKER, build_command
from .prefix_inventory import (
    RECIPES,
    inspect_prefix,
    pe_evidence,
    version_text,
)

DOCS = 'https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist'
MAX_INSTALLER = 100 * 1024 * 1024
HOSTS = {'aka.ms', 'download.microsoft.com', 'download.visualstudio.microsoft.com'}


def install_plan(game, root, key):
    if key not in RECIPES:
        raise ValueError('Unsupported runtime recipe.')
    requirement = RECIPES[key]
    info = inspect_prefix(game, root)
    settings = info['settings']
    prefix = Path(settings['prefix']).expanduser()
    if info['state'] != 'Created' or prefix.is_symlink() or any(p.is_symlink() for p in prefix.parents):
        raise ValueError('Runtime maintenance needs an initialized, app-owned, unlinked prefix. Inspection never creates one.')
    if not (prefix / MARKER).is_file() or (prefix / MARKER).is_symlink():
        raise ValueError('This prefix is not app-owned.')
    tool = Path(settings['proton']).expanduser()
    if not tool.is_absolute() or not (tool / 'proton').is_file():
        raise ValueError('Choose a concrete installed Proton folder first; automatic latest aliases cannot pin maintenance.')
    tool = tool.resolve()
    # Resolve aliases for the immutable confirmation context, not at execution time.
    if not (tool / 'proton').is_file():
        raise ValueError('Selected Proton build is missing.')
    if info['architecture'] not in ('x86', 'x64'):
        raise ValueError('Prefix architecture is unknown.')
    if requirement.architecture == 'x64' and info['architecture'] != 'x64':
        raise ValueError('An x64 package cannot be installed in an x86 prefix.')
    row = next(row for row in info['runtimes'] if row['key'] == key)
    if row['status'] == 'Installed':
        raise ValueError('The selected core requirement is already positively satisfied; installation is disabled.')
    # Never risk downgrading unverified native files or repairing a newer package.
    for item in row['files']:
        if item['origin'] == 'Unknown' or (item['origin'] == 'Microsoft native' and not item['version']):
            raise ValueError('Native file identity/version is uncertain. This recipe cannot safely replace it.')
    pinned = deepcopy(game)
    pinned['launch'] = {**settings, 'prefix': str(prefix.resolve()), 'proton': str(tool), 'arguments': [], 'dll_overrides': ''}
    # Validate UMU and prefix through the same launch contract, with an inert existing file as placeholder.
    probe = deepcopy(pinned)
    probe.update(executable=str(Path(__file__).resolve()), working_dir=str(Path(__file__).parent.resolve()))
    build_command(probe, root)
    def identity(path):
        value = Path(path).stat()
        return f'{value.st_dev}:{value.st_ino}:{value.st_mtime_ns}:{value.st_size}'
    prefix_id = prefix.stat()
    return {'game': pinned, 'recipe': key, 'info': info, 'requirement': requirement,
            'context': (str(prefix.resolve()), str(tool), str(Path(settings['runner']).resolve()), key,
                        f'{prefix_id.st_dev}:{prefix_id.st_ino}', identity(tool / 'proton'), identity(settings['runner'])),
            'existing_versions': [f['version'] for f in row['files'] if f['origin'] == 'Microsoft native' and f['version']]}


def confirmation_text(plan):
    req = plan['requirement']
    return (f"{req.title} · {req.architecture}\nCore minimum: {version_text(req.minimum)}\n"
            f"Prefix: {plan['context'][0]}\nProton: {plan['context'][1]}\nUMU: {plan['context'][2]}\n"
            f"Download: {req.url}\n\n"
            'Game-specific requirements are unknown. Install this only if the game vendor requires this family and architecture. '
            'This downloads the current official v14 package, which may upgrade or replace shared native/Wine components in this prefix and affect other games using it. '
            'It does not establish support for a newer game-specific minimum or optional MFC/OpenMP libraries.\n\n'
            'The Microsoft installer will display its license agreement; review and accept there, or cancel. '
            'No license is accepted by this app. The app provides no removal, repair, reset or uninstall actions. '
            'This restriction does not control Windows installer dialogs or tools outside the app.\n\n'
            'Close all programs using this prefix and do not start it from other tools until maintenance completes. '
            'App launches are locked, but external launchers do not honor the app lock. Cancellation can leave partial changes; files are kept.')


def trusted(url):
    value = urlparse(url)
    if value.scheme != 'https' or value.hostname not in HOSTS or value.username or value.password or value.port not in (None, 443):
        raise ValueError('Runtime download redirected outside the trusted Microsoft hosts.')
    return url


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        trusted(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_installer(requirement, destination, cancelled, progress):
    digest = hashlib.sha256()
    with build_opener(Redirects).open(Request(trusted(requirement.url), headers={'User-Agent': 'GameLibraryLauncher'}), timeout=20) as response:
        trusted(response.geturl())
        total = 0
        with destination.open('xb') as output:
            while chunk := response.read(256 * 1024):
                if cancelled():
                    raise InterruptedError('Download cancelled; no runtime installer started.')
                total += len(chunk)
                if total > MAX_INSTALLER:
                    raise ValueError('Runtime installer exceeds the download limit.')
                output.write(chunk)
                digest.update(chunk)
                progress(total)
            output.flush()
            os.fsync(output.fileno())
    evidence = pe_evidence(destination)
    if evidence['origin'] != 'Microsoft native' or not evidence['version'] or evidence['version'] < requirement.minimum:
        raise ValueError('Downloaded installer has unexpected publisher/version metadata; execution blocked.')
    return digest.hexdigest(), evidence['version']


def prepare(request, cancelled, progress):
    """Called in the independent supervisor while both locks are held."""
    from .prefix_guard import ensure_idle
    root = Path(request['record']).parent
    plan = install_plan(request['runtime_game'], root, request['recipe'])
    if list(plan['context']) != request['runtime_context']:
        raise RuntimeError('Prefix or runner changed after confirmation; review again.')
    if cancelled():
        raise InterruptedError('Maintenance cancelled before download.')
    ensure_idle(plan['context'][0])
    temp = tempfile.TemporaryDirectory(prefix='game-library-runtime-')
    try:
        destination = Path(temp.name) / ('vc_redist.' + plan['requirement'].architecture + '.exe')
        digest, version = download_installer(plan['requirement'], destination, cancelled, progress)
        if plan['existing_versions'] and max(plan['existing_versions']) > version:
            raise RuntimeError('Downloaded package is older than existing native files; downgrade blocked.')
        if cancelled():
            raise InterruptedError('Maintenance cancelled before execution.')
        current = install_plan(request['runtime_game'], root, request['recipe'])
        if current['existing_versions'] and max(current['existing_versions']) > version:
            raise RuntimeError('Native files changed during download; downgrade blocked.')
        if current['context'] != plan['context']:
            raise RuntimeError('Prefix or runner changed during download; execution blocked.')
        ensure_idle(plan['context'][0])
        launch = deepcopy(plan['game'])
        launch.update(executable=str(destination), working_dir=str(destination.parent))
        launch['launch']['arguments'] = ['/install', '/norestart']  # Interactive EULA; never /quiet or /passive.
        argv, cwd, env = build_command(launch, root)
        env['PROTONFIXES_DISABLE'] = '1'
        return temp, argv, cwd, env, digest
    except BaseException:
        temp.cleanup()
        raise


def verify(request):
    info = inspect_prefix(request['runtime_game'], Path(request['record']).parent)
    row = next(row for row in info['runtimes'] if row['key'] == request['recipe'])
    return row['status'] == 'Installed', f"Post-install evidence: {row['status']}; native core version {row['version']}. {row['detail']}"
