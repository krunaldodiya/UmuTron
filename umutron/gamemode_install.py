"""System package installation for Feral GameMode."""
import shutil
import subprocess


def install_command():
    """Resolve the host package manager command to install gamemode."""
    if shutil.which('pacman'):
        return ['pkexec', 'pacman', '-S', '--noconfirm', '--needed', 'gamemode', 'lib32-gamemode']
    if shutil.which('apt-get'):
        return ['pkexec', 'apt-get', 'install', '-y', 'gamemode']
    if shutil.which('dnf'):
        return ['pkexec', 'dnf', 'install', '-y', 'gamemode']
    if shutil.which('zypper'):
        return ['pkexec', 'zypper', 'install', '-y', 'gamemode']
    return None


def install_system_gamemode():
    """Install feral gamemode using pkexec and the host package manager."""
    if not shutil.which('pkexec'):
        raise RuntimeError("PolicyKit (pkexec) is not available to install packages.")

    cmd = install_command()
    if not cmd:
        raise RuntimeError("No supported package manager found (pacman, apt, dnf, zypper).")

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        if cmd[1] == 'pacman' and 'lib32-gamemode' in cmd:
            fallback = ['pkexec', 'pacman', '-S', '--noconfirm', '--needed', 'gamemode']
            res = subprocess.run(fallback, capture_output=True, text=True)
        if res.returncode != 0:
            err = (res.stderr or res.stdout or "Installation was cancelled or failed.").strip()
            raise RuntimeError(f"GameMode installation failed: {err}")

    if not shutil.which('gamemoderun'):
        raise RuntimeError("Installation completed, but gamemoderun was not found in PATH.")
    return True
