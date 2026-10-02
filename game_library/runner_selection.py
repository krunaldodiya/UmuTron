"""Stable runner choices, separate from discovery, installation and execution."""
import re

INHERIT = 'default'
AUTOMATIC = {'UMU-Latest': 'UMU-Proton', 'GE-Latest': 'GE-Proton'}
DOWNLOAD_FAMILIES = ('GE-Proton', 'UMU-Proton')


def parse_release(value):
    if not value.startswith('release:'):
        return None
    parts = value.split(':')
    if len(parts) != 3 or parts[1] not in DOWNLOAD_FAMILIES:
        raise ValueError('Unknown Proton release selection.')
    family, tag = parts[1:]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', tag) or not tag.startswith(family):
        raise ValueError('Invalid Proton release version.')
    return family, tag


def release_selector(release):
    value = 'release:' + release['family'] + ':' + release['version']
    parse_release(value)
    return value


def effective_selector(game, global_default='UMU-Latest'):
    """Read legacy pins without mutation; only explicit Use default opts out."""
    if global_default == INHERIT:
        raise ValueError('The global Proton default must identify a runner.')
    fallback = global_default or 'UMU-Latest'
    selected = game.get('launch', {}).get('proton', '')
    if selected == INHERIT:
        return fallback
    return selected or game.get('installation', {}).get('proton') or fallback


def global_selector(root):
    """Read the saved global policy without modifying a legacy library."""
    import json
    from pathlib import Path
    path = Path(root) / 'library.json'
    if not path.exists():
        return 'UMU-Latest'
    if path.stat().st_size > 20 * 1024**2:
        raise ValueError('Library is too large.')
    return json.loads(path.read_text()).get('settings', {}).get('default_proton') or 'UMU-Latest'
