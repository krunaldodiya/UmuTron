"""Automatic headless virtual display wrapper for UI tests and smoke checks."""
import os
import shutil
import sys


def ensure_headless() -> None:
    """Rerun inside xvfb-run if launched on an interactive desktop, avoiding window popups."""
    if os.environ.get('UMUTRON_HEADLESS') == '1':
        return
    if os.environ.get('UMUTRON_VISIBLE') == '1':
        return
    if os.environ.get('GDK_BACKEND') == 'broadway':
        return
    if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
        return
    xvfb = shutil.which('xvfb-run')
    if xvfb:
        env = dict(os.environ)
        env['UMUTRON_HEADLESS'] = '1'
        env.pop('WAYLAND_DISPLAY', None)
        env.setdefault('GSK_RENDERER', 'cairo')
        env.setdefault('GSETTINGS_BACKEND', 'memory')
        os.execvpe(xvfb, [xvfb, '-a', sys.executable, *sys.argv], env)
