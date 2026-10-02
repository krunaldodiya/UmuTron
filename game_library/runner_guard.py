"""Shared runner-use leases and exclusive managed-removal protection."""
import fcntl
import hashlib
import os
from pathlib import Path
import stat


def acquire(runner, exclusive=False):
    """Caller retains the fd through every owned descendant's lifetime."""
    runner = Path(runner).expanduser()
    if not runner.is_absolute():
        raise ValueError('A runner lease requires an absolute path.')
    base = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/tmp/game-library-launcher-{os.getuid()}')
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = base.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise RuntimeError('Runner lock directory is not private and user-owned.')
    locks = base / 'game-library-runner-locks'
    locks.mkdir(mode=0o700, exist_ok=True)
    info = locks.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError('Unsafe runner lock directory.')
    key = hashlib.sha256(os.fsencode(runner.resolve())).hexdigest()
    fd = os.open(locks / (key + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise RuntimeError('Unsafe runner lock file.')
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('This Proton runner is in use or being removed. Finish the operation first.') from None
        return fd
    except BaseException:
        os.close(fd)
        raise


def ensure_idle(runner, proc=Path('/proc')):
    """Reject observable external use; external launchers do not honor leases."""
    target = Path(runner).resolve()
    conflicts, uncertain = [], []
    for directory in proc.iterdir():
        if not directory.name.isdigit() or int(directory.name) == os.getpid():
            continue
        try:
            if directory.stat().st_uid != os.getuid():
                continue
            with (directory / 'environ').open('rb') as stream:
                raw = stream.read(262145)
            if len(raw) > 262144:
                uncertain.append(directory.name)
                continue
            env = dict(item.split(b'=', 1) for item in raw.split(b'\0') if b'=' in item)
            value = env.get(b'PROTONPATH')
            if value and Path(os.fsdecode(value)).is_absolute() and Path(os.fsdecode(value)).resolve() == target:
                conflicts.append(directory.name)
                continue
            for name in ('exe', 'cwd'):
                try:
                    if (directory / name).resolve(strict=True).is_relative_to(target):
                        conflicts.append(directory.name)
                        break
                except FileNotFoundError:
                    pass
        except (FileNotFoundError, ProcessLookupError):
            pass
        except (OSError, ValueError):
            uncertain.append(directory.name)
    if conflicts:
        raise RuntimeError('Processes still use this Proton runner. Close them before uninstalling.')
    if uncertain:
        raise RuntimeError('Cannot verify that this Proton runner is idle; same-user process inspection was denied.')
