"""Local Docker FastAPI server lifecycle and non-secret desktop configuration.

The desktop owns this server: it is always addressed over numeric loopback HTTP,
its ``.env`` is the single source of truth for container environment values, and
Docker Compose is the only deployment mechanism. No remote catalog is used.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

DEFAULT_API_URL = 'http://127.0.0.1:8000'
DEFAULT_REPO = 'krunaldodiya/UmuTron-FastAPI'
DEFAULT_REPO_URL = f'https://github.com/{DEFAULT_REPO}.git'
DEFAULT_REPO_SSH = f'git@github.com:{DEFAULT_REPO}.git'
MAX_ENV_BYTES = 256 * 1024
MAX_CONFIG_BYTES = 16 * 1024

Progress = Callable[[str], None]


class ServerError(RuntimeError):
    """A sanitized, user-showable server lifecycle failure."""


@dataclass(frozen=True)
class ServerEnvironment:
    internal_api_key: str = ''
    twitch_client_id: str = ''
    twitch_client_secret: str = ''
    live_catalog: bool = False


@dataclass(frozen=True)
class ServerStatus:
    healthy: bool
    api_url: str
    repo_dir: Path | None
    repo_installed: bool
    docker_available: bool


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Server health checks do not follow redirects.')


def _safe_read(path: Path, limit: int) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except FileNotFoundError:
        raise
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise OSError('Configuration is not a regular file.')
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise OSError('Configuration file is too large.')
    return raw


def _atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=str(path.parent))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if key.startswith('export '):
            key = key[7:].strip()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        values[key] = value
    return values


def _update_env(text: str, updates: Mapping[str, str]) -> str:
    seen: set[str] = set()
    result: list[str] = []
    for raw in text.splitlines():
        match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=', raw)
        if match and match.group(1) in updates:
            key = match.group(1)
            if key in seen:
                continue
            seen.add(key)
            result.append(f'{key}={updates[key]}')
            continue
        result.append(raw)
    for key, value in updates.items():
        if key not in seen:
            result.append(f'{key}={value}')
    return '\n'.join(result).rstrip() + '\n'


def _remote_failure(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    detail = lines[-1] if lines else 'unknown error'
    return detail[:300]


class ServerManager:
    """Read/write the checkout environment and run its Compose stack."""

    def __init__(
        self,
        *,
        config_dir: Path | None = None,
        clone_dir: Path | None = None,
        repo_dir: Path | None = None,
        api_url: str | None = None,
        runner: Callable[..., subprocess.CompletedProcess] | None = None,
        health_transport: Callable[[str, float], bool] | None = None,
        environ: Mapping[str, str] | None = None,
    ):
        self.environ = dict(os.environ if environ is None else environ)
        config_home = Path(self.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
        self.config_dir = Path(config_dir) if config_dir is not None else config_home / 'umutron'
        self.config_path = self.config_dir / 'server.json'
        self.catalog_path = self.config_dir / 'catalog.json'
        data_home = Path(self.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
        self.clone_dir = Path(clone_dir) if clone_dir is not None else data_home / 'umutron' / 'UmuTron-FastAPI'
        self._repo_override = Path(repo_dir).expanduser() if repo_dir is not None else None
        self.api_url = (api_url or self.environ.get('UMUTRON_API_URL') or DEFAULT_API_URL).rstrip('/')
        parsed = urlparse(self.api_url)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', '::1') or parsed.path not in ('', '/'):
            raise ValueError('The local server URL must be numeric loopback HTTP.')
        self.runner = runner or subprocess.run
        self.health_transport = health_transport
        self._docker_available: bool | None = None

    # ------------------------------------------------------------------ files
    def _read_config(self) -> dict[str, str]:
        try:
            raw = _safe_read(self.config_path, MAX_CONFIG_BYTES)
            value = json.loads(raw)
        except (OSError, ValueError):
            return {}
        if not isinstance(value, dict):
            return {}
        result = {}
        for key in ('repo_dir', 'api_url'):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                result[key] = item.strip()
        return result

    def _write_config(self, **updates: str) -> None:
        current = self._read_config()
        current.update({key: str(value) for key, value in updates.items() if str(value).strip()})
        _atomic_write(self.config_path, json.dumps(current, indent=2).encode() + b'\n')

    def _command_env(self) -> dict[str, str]:
        env = dict(self.environ)
        env.update({
            'GIT_TERMINAL_PROMPT': '0',
            'GIT_SSH_COMMAND': 'ssh -o BatchMode=yes -o ConnectTimeout=10',
            'GH_PROMPT_DISABLED': '1',
            'DOCKER_CLI_HINTS': 'false',
            'COMPOSE_ANSI': 'never',
        })
        return env

    @staticmethod
    def is_repo(path: Path | None) -> bool:
        return bool(path and (path / 'docker-compose.yml').is_file() and (path / 'app').is_dir())

    def find_repo(self) -> Path | None:
        candidates: list[Path] = []
        if self._repo_override is not None:
            candidates.append(self._repo_override)
        configured = self.environ.get('UMUTRON_API_DIR')
        if configured:
            candidates.append(Path(configured).expanduser())
        saved = self._read_config().get('repo_dir')
        if saved:
            candidates.append(Path(saved).expanduser())
        source_parent = Path(__file__).resolve().parents[2]
        candidates.append(source_parent / 'UmuTron-FastAPI')
        candidates.append(Path.home() / '.local/opt/UmuTron-FastAPI')
        candidates.append(self.clone_dir)
        seen: set[Path] = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            if self.is_repo(resolved):
                return resolved
        return None

    def repo_path(self) -> Path:
        return self.find_repo() or self._repo_override or (
            Path(self.environ['UMUTRON_API_DIR']).expanduser()
            if self.environ.get('UMUTRON_API_DIR') else self.clone_dir
        )

    def env_path(self, repo: Path | None = None) -> Path:
        return (repo or self.repo_path()) / '.env'

    def read_environment(self, repo: Path | None = None) -> ServerEnvironment:
        target = repo or self.find_repo()
        if target is None:
            return ServerEnvironment()
        try:
            text = _safe_read(target / '.env', MAX_ENV_BYTES).decode('utf-8', 'replace')
        except OSError:
            return ServerEnvironment()
        values = _parse_env(text)
        return ServerEnvironment(
            internal_api_key=values.get('INTERNAL_API_KEY', '').strip(),
            twitch_client_id=values.get('TWITCH_CLIENT_ID', '').strip(),
            twitch_client_secret=values.get('TWITCH_CLIENT_SECRET', '').strip(),
            live_catalog=(
                values.get('CATALOG_MODE', 'mock').strip().lower() == 'igdb'
                and values.get('ENABLE_LIVE_IGDB', '0').strip() == '1'
            ),
        )

    @staticmethod
    def generate_key() -> str:
        return secrets.token_hex(32)

    @staticmethod
    def _validate_twitch(settings: ServerEnvironment) -> None:
        client_id = settings.twitch_client_id.strip()
        secret = settings.twitch_client_secret.strip()
        if client_id and not re.fullmatch(r'[A-Za-z0-9]{1,200}', client_id):
            raise ServerError('Twitch Client ID must contain letters and digits only.')
        if secret and not re.fullmatch(r'[A-Za-z0-9]{1,500}', secret):
            raise ServerError('Twitch Client Secret must contain letters and digits only.')
        if settings.live_catalog and not (client_id and secret):
            raise ServerError('Live IGDB requires both a Twitch Client ID and Client Secret.')

    def save_environment(self, repo: Path, settings: ServerEnvironment) -> ServerEnvironment:
        """Persist credentials and catalog mode; the result is read back from disk."""
        if not self.is_repo(repo):
            raise ServerError('The UmuTron FastAPI checkout is not installed yet.')
        settings = replace(
            settings,
            internal_api_key=settings.internal_api_key.strip() or self.generate_key(),
            twitch_client_id=settings.twitch_client_id.strip(),
            twitch_client_secret=settings.twitch_client_secret.strip(),
        )
        if not re.fullmatch(r'[^\s]{16,256}', settings.internal_api_key):
            raise ServerError('The internal API key must be 16–256 non-whitespace characters.')
        self._validate_twitch(settings)
        try:
            text = _safe_read(repo / '.env', MAX_ENV_BYTES).decode('utf-8', 'replace')
        except OSError:
            try:
                text = _safe_read(repo / '.env.example', MAX_ENV_BYTES).decode('utf-8', 'replace')
            except OSError:
                text = ''
        updates = {
            'APP_BASE_URL': self.api_url,
            'INTERNAL_API_KEY': settings.internal_api_key,
            'TWITCH_CLIENT_ID': settings.twitch_client_id,
            'TWITCH_CLIENT_SECRET': settings.twitch_client_secret,
            'CATALOG_MODE': 'igdb' if settings.live_catalog else 'mock',
            'ENABLE_LIVE_IGDB': '1' if settings.live_catalog else '0',
        }
        _atomic_write(repo / '.env', _update_env(text, updates).encode())
        os.environ['INTERNAL_API_KEY'] = settings.internal_api_key
        os.environ['UMUTRON_API_KEY'] = settings.internal_api_key
        self.environ['INTERNAL_API_KEY'] = settings.internal_api_key
        self.environ['UMUTRON_API_KEY'] = settings.internal_api_key
        return self.read_environment(repo)

    def write_catalog_config(self) -> Path:
        self.config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        _atomic_write(self.catalog_path, json.dumps({'APP_BASE_URL': self.api_url}).encode() + b'\n')
        return self.catalog_path

    def activate_local(self) -> None:
        """Force the desktop process to the local backend only."""
        os.environ['APP_BASE_URL'] = self.api_url
        os.environ['UMUTRON_ALLOW_LOOPBACK_HTTP'] = '1'
        self.environ['APP_BASE_URL'] = self.api_url
        self.environ['UMUTRON_ALLOW_LOOPBACK_HTTP'] = '1'
        env = self.read_environment()
        if env.internal_api_key:
            os.environ.setdefault('INTERNAL_API_KEY', env.internal_api_key)
            os.environ.setdefault('UMUTRON_API_KEY', env.internal_api_key)
            self.environ.setdefault('INTERNAL_API_KEY', env.internal_api_key)
            self.environ.setdefault('UMUTRON_API_KEY', env.internal_api_key)
        self.write_catalog_config()

    # ----------------------------------------------------------------- health
    def health(self, timeout: float = 1.5) -> bool:
        if self.health_transport is not None:
            try:
                return bool(self.health_transport(self.api_url, timeout))
            except Exception:
                return False
        request = Request(
            self.api_url + '/health',
            headers={'Accept': 'application/json', 'User-Agent': 'UmuTron/server-check'},
        )
        try:
            with build_opener(ProxyHandler({}), _NoRedirects).open(request, timeout=timeout) as response:
                body = response.read(64 * 1024 + 1)
                status = getattr(response, 'status', 200)
        except (OSError, ValueError, HTTPError, URLError):
            return False
        if status != 200 or len(body) > 64 * 1024:
            return False
        try:
            data = json.loads(body)
        except ValueError:
            return False
        return isinstance(data, dict) and data.get('status') == 'ok'

    def docker_available(self, *, force: bool = False) -> bool:
        if self._docker_available is not None and not force:
            return self._docker_available
        docker = shutil.which('docker')
        if not docker:
            self._docker_available = False
            return False
        try:
            result = self.runner(
                [docker, 'compose', 'version'],
                capture_output=True,
                text=True,
                timeout=12,
                env=self._command_env(),
            )
            self._docker_available = result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            self._docker_available = False
        return self._docker_available

    def status(self) -> ServerStatus:
        repo = self.find_repo()
        return ServerStatus(
            healthy=self.health(),
            api_url=self.api_url,
            repo_dir=repo,
            repo_installed=repo is not None,
            docker_available=self.docker_available(),
        )

    # ---------------------------------------------------------------- install
    def clone(self, progress: Progress | None = None) -> Path:
        target = self.clone_dir
        if self.is_repo(target):
            self._write_config(repo_dir=str(target))
            return target
        if target.exists() and any(target.iterdir()):
            raise ServerError(f'The server directory already exists but is not a valid checkout: {target}')
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        partial = target.with_name(target.name + f'.partial-{os.getpid()}')
        if partial.exists():
            shutil.rmtree(partial, ignore_errors=True)
        commands: list[list[str]] = []
        gh = shutil.which('gh')
        if gh:
            commands.append([gh, 'repo', 'clone', DEFAULT_REPO, str(partial), '--', '--depth=1'])
        git = shutil.which('git')
        if git:
            commands.append([git, 'clone', '--depth=1', DEFAULT_REPO_SSH, str(partial)])
            commands.append([git, 'clone', '--depth=1', DEFAULT_REPO_URL, str(partial)])
        if not commands:
            raise ServerError('Neither GitHub CLI nor Git is installed, so the server cannot be cloned.')
        if progress:
            progress('Cloning the UmuTron FastAPI server from GitHub…')
        failures: list[str] = []
        for command in commands:
            if partial.exists():
                shutil.rmtree(partial, ignore_errors=True)
            try:
                result = self.runner(
                    command,
                    cwd=target.parent,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=self._command_env(),
                )
            except (OSError, subprocess.SubprocessError) as error:
                failures.append(str(error))
                continue
            if result.returncode == 0 and self.is_repo(partial):
                partial.rename(target)
                self._write_config(repo_dir=str(target))
                return target
            output = (getattr(result, 'stderr', '') or getattr(result, 'stdout', '') or '')
            failures.append(_remote_failure(output))
        shutil.rmtree(partial, ignore_errors=True)
        detail = failures[-1] if failures else 'No clone method succeeded.'
        raise ServerError(
            'Could not clone the private server repository. Sign in with GitHub CLI '
            f'(gh auth login) or set UMUTRON_API_DIR to an existing checkout. ({detail})'
        )

    def install(self, progress: Progress | None = None) -> Path:
        repo = self.find_repo()
        if repo is None:
            repo = self.clone(progress)
        else:
            self._write_config(repo_dir=str(repo))
        return repo

    # --------------------------------------------------------------- lifecycle
    def _run(self, command: list[str], repo: Path, timeout: int) -> None:
        try:
            result = self.runner(
                command,
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._command_env(),
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ServerError(f'Docker Compose could not run: {error}') from None
        if result.returncode != 0:
            output = (getattr(result, 'stderr', '') or getattr(result, 'stdout', '') or '')
            raise ServerError(f'Docker Compose failed: {_remote_failure(output)}')

    def start(self, repo: Path, *, build: bool = True, recreate_api: bool = False,
              progress: Progress | None = None) -> None:
        if not self.docker_available(force=True):
            raise ServerError('Docker is not installed or the Docker daemon is not available.')
        if not self.is_repo(repo):
            raise ServerError('The UmuTron FastAPI checkout is missing.')
        command = ['docker', 'compose', 'up', '-d']
        if build:
            command.append('--build')
        if recreate_api:
            command.extend(['--force-recreate', 'api'])
        if progress:
            progress('Building and starting the local Docker server…' if build
                     else 'Restarting the local Docker server…')
        self._run(command, repo, 1800)

    def stop(self, repo: Path, *, progress: Progress | None = None) -> None:
        if not self.docker_available(force=True):
            raise ServerError('Docker is not installed or the Docker daemon is not available.')
        if progress:
            progress('Stopping the local Docker server…')
        self._run(['docker', 'compose', 'stop'], repo, 120)

    def wait_healthy(self, *, timeout: float = 90, progress: Progress | None = None) -> None:
        if progress:
            progress('Waiting for the local server to become healthy…')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.health(timeout=1.0):
                return
            time.sleep(0.5)
        raise ServerError(f'The local server did not become healthy at {self.api_url}.')

    def install_and_start(self, settings: ServerEnvironment | None = None,
                          *, progress: Progress | None = None) -> tuple[Path, ServerEnvironment]:
        repo = self.install(progress)
        current = self.read_environment(repo)
        if settings is None:
            settings = current
        if not settings.internal_api_key:
            settings = replace(settings, internal_api_key=current.internal_api_key or self.generate_key())
        saved = self.save_environment(repo, settings)
        self.start(repo, build=True, progress=progress)
        self.wait_healthy(progress=progress)
        self.activate_local()
        return repo, saved

    def apply_environment(self, repo: Path, settings: ServerEnvironment,
                          *, progress: Progress | None = None) -> ServerEnvironment:
        saved = self.save_environment(repo, settings)
        if self.health():
            self.start(repo, build=False, recreate_api=True, progress=progress)
            self.wait_healthy(progress=progress)
        self.activate_local()
        return saved
