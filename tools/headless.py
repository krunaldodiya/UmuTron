"""Automatic headless virtual display wrapper for UI tests and smoke checks."""
import os
import shutil
import sys


def ensure_headless() -> None:
    """Rerun inside xvfb-run whenever a native display could be reachable."""
    if os.environ.get('UMUTRON_HEADLESS') == '1':
        return
    if os.environ.get('UMUTRON_VISIBLE') == '1':
        return
    if os.environ.get('GDK_BACKEND') == 'broadway':
        return
    xvfb = shutil.which('xvfb-run')
    if xvfb:
        env = dict(os.environ)
        env['UMUTRON_HEADLESS'] = '1'
        env.pop('WAYLAND_DISPLAY', None)
        env['GDK_BACKEND'] = 'x11'
        env.setdefault('GSK_RENDERER', 'cairo')
        env.setdefault('GSETTINGS_BACKEND', 'memory')
        os.execvpe(xvfb, [xvfb, '-a', sys.executable, *sys.argv], env)
