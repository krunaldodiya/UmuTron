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
target=Path.home()/'.local/opt/game-library-launcher'
for item in (source/'game_library').glob('*.py'):
    atomic_write(target/'game_library'/item.name,item.read_bytes())
atomic_write(target/'run.py',(source/'run.py').read_bytes())
icon=Path.home()/'.local/share/icons/hicolor/scalable/apps/game-library-launcher.svg'
atomic_write(icon,(source/'assets/umutron.svg').read_bytes())
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
