"""Read-only presentation of a game's existing setup; never infer a reinstall."""
from pathlib import Path
from .installer_identity import is_installer_executable


def setup_state(game):
    config=game.get('installation',{})
    executable=game.get('executable','')
    path=Path(executable)
    present=bool(executable and path.is_absolute() and path.is_file())
    installer=config.get('mode')=='installer'
    confirmed=not installer or bool(config.get('confirmed') and config.get('session_id'))
    distinct=not present or not is_installer_executable(game)
    working=game.get('working_dir','')
    working_ok=not working or (Path(working).is_absolute() and Path(working).is_dir())
    ready=present and confirmed and distinct and working_ok
    # Keep Reinstall secondary even when a configured drive is disconnected.
    existing=bool(executable or config.get('session_id') or config.get('confirmed'))
    if ready:
        description='Game executable connected.'
    elif executable and not present:
        description='Game executable unavailable. Check its location or reconnect the drive.'
    elif present and not distinct:
        description='Choose the game executable, not the setup installer.'
    elif present and not working_ok:
        description='The working directory is unavailable. Check its location.'
    elif installer and config.get('session_id') and not confirmed:
        description='Installation needs confirmation. Select the installed game executable below.'
    else:
        description='Connect an existing game executable, or choose More → Install game…'
    return {'ready':ready,'reinstall':existing,'description':description,
            'needs_confirmation':bool(installer and not confirmed)}
