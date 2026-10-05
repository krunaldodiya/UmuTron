"""Read-only identity checks for an installer attempt, separate from its next draft."""
from pathlib import Path
from uuid import UUID


def validate_installer_attempt(value):
    if not isinstance(value,dict) or set(value)!={'session_id','executable'}:
        raise ValueError('Invalid installer attempt.')
    for key in ('session_id','executable'):
        item=value[key]
        if not isinstance(item,str) or not item or len(item)>4096 or '\x00' in item:
            raise ValueError('Invalid installer attempt '+key+'.')
    UUID(value['session_id'])
    if not Path(value['executable']).is_absolute():raise ValueError('Invalid installer attempt executable.')


def matching_installer_attempt(game):
    attempt=game.get('installer_attempt',{})
    return attempt if attempt.get('session_id')==game.get('installation',{}).get('session_id') else {}


def is_installer_executable(game):
    config=game.get('installation',{})
    if config.get('mode')!='installer' or not game.get('executable'):return False
    executable=Path(game['executable'])
    for value in (config.get('installer'),matching_installer_attempt(game).get('executable')):
        if not value:continue
        installer=Path(value)
        if executable.resolve()==installer.resolve():return True
        try:
            if executable.samefile(installer):return True
        except OSError:pass
    return False
