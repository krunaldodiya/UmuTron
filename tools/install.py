#!/usr/bin/python3
"""Install the desktop app for the current user; no root or Steam writes."""
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from steam_library.library import atomic_write

source=Path(__file__).resolve().parents[1]
target=Path.home()/'.local/opt/steam-library-metadata-manager'
for item in (source/'steam_library').glob('*.py'):
    atomic_write(target/'steam_library'/item.name,item.read_bytes())
atomic_write(target/'run.py',(source/'run.py').read_bytes())
icon=Path.home()/'.local/share/icons/hicolor/scalable/apps/steam-library-metadata-manager.svg'
atomic_write(icon,(source/'assets/steam-library-metadata-manager.svg').read_bytes())
# Desktop Exec escaping follows the desktop-entry specification (not shell quoting).
def quoted(path):
    text=str(path).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
    return '"'+text+'"'
launch='/usr/bin/python3 '+quoted(target/'run.py')
entry=f'''[Desktop Entry]
Type=Application
Name=Steam Library Metadata Manager
Comment=Organize non-Steam game details and artwork; sync manually
Exec={launch}
Icon=steam-library-metadata-manager
Terminal=false
Categories=Game;
StartupNotify=true
Actions=Demo;

[Desktop Action Demo]
Name=Open isolated demo
Exec={launch} --demo
'''
desktop=Path.home()/'.local/share/applications/steam-library-metadata-manager.desktop'
atomic_write(desktop,entry.encode())
if shutil.which('desktop-file-validate'):
    subprocess.run(['desktop-file-validate',str(desktop)],check=True)
if shutil.which('update-desktop-database'):
    subprocess.run(['update-desktop-database',str(desktop.parent)],check=True)
print('Installed user application and menu entry. No Steam files changed.')
