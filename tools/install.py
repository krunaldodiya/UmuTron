#!/usr/bin/python3
"""Install the desktop app for the current user; no root or game execution."""
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from game_library.library import atomic_write
from game_library import APP_ID, APP_NAME, ICON_NAME

source=Path(__file__).resolve().parents[1]
target=Path.home()/'.local/opt/umutron'
legacy_target=Path.home()/'.local/opt/game-library-launcher'
source_pkg=source/'umutron' if (source/'umutron').is_dir() else source/'game_library'

def install_package(destination):
    for item in source_pkg.iterdir():
        if item.is_file() and item.suffix == '.py':
            atomic_write(destination/item.name,item.read_bytes())
        elif item.is_dir() and item.name != '__pycache__':
            shutil.copytree(item,destination/item.name,dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__','*.pyc'))

install_package(target/'umutron')
install_package(target/'game_library')
atomic_write(target/'run.py',(source/'run.py').read_bytes())
if not legacy_target.exists():
    try: legacy_target.symlink_to('umutron', target_is_directory=True)
    except OSError: pass
if legacy_target.is_dir() and not legacy_target.is_symlink():
    install_package(legacy_target/'game_library')
    atomic_write(legacy_target/'run.py',(source/'run.py').read_bytes())
icon=Path.home()/'.local/share/icons/hicolor/scalable/apps/game-library-launcher.svg'
atomic_write(icon,(source/'assets/umutron.svg').read_bytes())
umutron_icon=Path.home()/'.local/share/icons/hicolor/scalable/apps/umutron.svg'
atomic_write(umutron_icon,(source/'assets/umutron.svg').read_bytes())
# Desktop Exec escaping follows the desktop-entry specification (not shell quoting).
def quoted(path):
    text=str(path).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
    return '"'+text+'"'
launch='/usr/bin/python3 '+quoted(target/'run.py')
entry=f'''[Desktop Entry]
Type=Application
Name={APP_NAME}
Comment=Organize and play installed games with UMU and Proton
Exec={launch}
Icon={ICON_NAME}
Terminal=false
Categories=Game;
Keywords=UmuTron;UMU;Proton;Games;
StartupNotify=true
StartupWMClass={APP_ID}
Actions=Demo;

[Desktop Action Demo]
Name=Open isolated demo
Exec={launch} --demo
'''
applications=Path.home()/'.local/share/applications'
# GNOME matches the GTK/Wayland application ID to this exact desktop filename.
desktop=applications/(APP_ID+'.desktop')
atomic_write(desktop,entry.encode())
# Keep existing launch references usable, without a second menu item or WM_CLASS claim.
compatibility=applications/'game-library-launcher.desktop'
compatibility_entry=entry.replace('StartupWMClass='+APP_ID+'\n','NoDisplay=true\n')
atomic_write(compatibility,compatibility_entry.encode())
if shutil.which('desktop-file-validate'):
    for path in (desktop,compatibility):
        subprocess.run(['desktop-file-validate',str(path)],check=True)
if shutil.which('update-desktop-database'):
    subprocess.run(['update-desktop-database',str(desktop.parent)],check=True)
print('Installed '+APP_NAME+' and its menu entry. Existing libraries and games were preserved.')
