"""Cross-library advisory locks and fail-closed same-user prefix process checks."""
import fcntl
import hashlib
import os
import stat
from pathlib import Path


def process_conflicts(prefix, proc=Path('/proc')):
    target = Path(prefix).resolve()
    conflicts = []
    uncertain = []
    for directory in proc.iterdir():
        if not directory.name.isdigit() or int(directory.name) == os.getpid():
            continue
        try:
            if directory.stat().st_uid != os.getuid():
                continue
            with (directory / 'environ').open('rb') as stream:
                entries = stream.read(262145)
            if len(entries) > 262144:
                uncertain.append(directory.name)
                continue
            env = dict(item.split(b'=', 1) for item in entries.split(b'\0') if b'=' in item)
            paths = [env.get(b'WINEPREFIX'), env.get(b'STEAM_COMPAT_DATA_PATH')]
            if any(value and (Path(os.fsdecode(value)).resolve() == target or
                              (Path(os.fsdecode(value)) / 'pfx').resolve() == target) for value in paths):
                conflicts.append(directory.name)
                continue
            # Catch Wine helpers whose environment no longer contains the prefix.
            for link in (directory / 'cwd',):
                try:
                    if link.resolve(strict=True).is_relative_to(target):
                        conflicts.append(directory.name)
                except FileNotFoundError:
                    pass
        except (FileNotFoundError, ProcessLookupError):
            pass
        except (PermissionError, OSError, ValueError):
            uncertain.append(directory.name)
    return conflicts, uncertain


def ensure_idle(prefix):
    conflicts, uncertain = process_conflicts(prefix)
    if conflicts:
        raise RuntimeError('Processes still use this prefix (PIDs ' + ', '.join(conflicts[:12]) + '). Close them before maintenance or launch.')
    if uncertain:
        raise RuntimeError('Cannot verify that this prefix is idle. Same-user process inspection was denied; maintenance/launch is blocked.')


def acquire(prefix, check_processes=True):
    """Hold the inode lock in the independent supervisor until all descendants exit.

    The lock covers this app across libraries. External launchers do not honor it;
    process checks reject observable existing use, not OS-wide future starts.
    """
    base = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/tmp/game-library-launcher-{os.getuid()}')
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = base.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise RuntimeError('Prefix lock directory is not private and user-owned.')
    locks = base / 'game-library-prefix-locks'
    locks.mkdir(mode=0o700, exist_ok=True)
    info = locks.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError('Unsafe prefix lock directory.')
    key = hashlib.sha256(os.fsencode(Path(prefix).resolve())).hexdigest()
    fd = os.open(locks / (key + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise RuntimeError('Unsafe prefix lock file.')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another operation owns this prefix, possibly in another library.') from None
        if check_processes:
            ensure_idle(prefix)
        return fd
    except BaseException:
        os.close(fd)
        raise
