#!/usr/bin/python3
"""Install the desktop app for the current user; no root or game execution."""
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from game_library.library import atomic_write

source=Path(__file__).resolve().parents[1]
target=Path.home()/'.local/opt/game-library-launcher'
for item in (source/'game_library').glob('*.py'):
    atomic_write(target/'game_library'/item.name,item.read_bytes())
atomic_write(target/'run.py',(source/'run.py').read_bytes())
icon=Path.home()/'.local/share/icons/hicolor/scalable/apps/game-library-launcher.svg'
atomic_write(icon,(source/'assets/steam-library-metadata-manager.svg').read_bytes())
# Desktop Exec escaping follows the desktop-entry specification (not shell quoting).
def quoted(path):
    text=str(path).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
    return '"'+text+'"'
launch='/usr/bin/python3 '+quoted(target/'run.py')
entry=f'''[Desktop Entry]
Type=Application
Name=Game Library Launcher
Comment=Organize and play installed games with UMU and Proton
Exec={launch}
Icon=game-library-launcher
Terminal=false
Categories=Game;
StartupNotify=true
Actions=Demo;

[Desktop Action Demo]
Name=Open isolated demo
Exec={launch} --demo
'''
desktop=Path.home()/'.local/share/applications/game-library-launcher.desktop'
atomic_write(desktop,entry.encode())
if shutil.which('desktop-file-validate'):
    subprocess.run(['desktop-file-validate',str(desktop)],check=True)
if shutil.which('update-desktop-database'):
    subprocess.run(['update-desktop-database',str(desktop.parent)],check=True)
legacy=Path.home()/'.local/share/applications/steam-library-metadata-manager.desktop'
if legacy.is_file() and 'Steam Library Metadata Manager' in legacy.read_text():legacy.unlink()
print('Installed user application and menu entry. Existing libraries and games were preserved.')
