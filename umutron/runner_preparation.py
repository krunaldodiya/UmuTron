"""Resolve exact downloaded runners before any game/installer process starts."""
import os
from pathlib import Path
from .runner_selection import AUTOMATIC, parse_release
from .runner_guard import acquire
from .proton_manager import ProtonManager


def prepare_runner(request, cancel, progress, manager=None):
    value = request['env']['PROTONPATH']
    if cancel.is_set():
        raise InterruptedError('Proton preparation cancelled.')
    # Existing automatic policies remain UMU-owned; they are never rewritten on save.
    if value in AUTOMATIC:
        return None
    manager = manager or ProtonManager(Path(request['record']).parent / 'proton-manager')
    release = None
    if parse_release(value):
        progress(state='Resolving selected release')
        release = manager.resolve(value)
        value = str(manager.target(release))
    lease = acquire(value)
    try:
        if release:
            value = manager.ensure(release, cancel, progress)
        if cancel.is_set():
            raise InterruptedError('Proton preparation cancelled.')
        path = Path(value).expanduser()
        if not path.is_absolute() or not (path / 'proton').is_file():
            raise ValueError('Selected Proton runner is unavailable. Choose another version in Setup.')
        request['env']['PROTONPATH'] = str(path)
        return lease
    except BaseException:
        os.close(lease)
        raise
