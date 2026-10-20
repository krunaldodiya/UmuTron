#!/usr/bin/python3
"""Install the desktop app for the current user; no root or game execution."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from game_library.library import atomic_write
from game_library import APP_ID, APP_NAME, ICON_NAME

API_ORIGIN='https://umutron-fastapi.vercel.app'
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
svg_data=(source/'assets/umutron.svg').read_bytes()
for name in (ICON_NAME,'umutron',APP_ID):
    p=Path.home()/f'.local/share/icons/hicolor/scalable/apps/{name}.svg'
    atomic_write(p,svg_data)
    try: p.chmod(0o644)
    except OSError: pass
try:
    import gi
    gi.require_version('GdkPixbuf','2.0')
    from gi.repository import GdkPixbuf
    svg_file=source/'assets/umutron.svg'
    for size in (16,22,24,32,48,64,128,256,512):
        pb=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(svg_file),size,size,True)
        out_dir=Path.home()/f'.local/share/icons/hicolor/{size}x{size}/apps'
        out_dir.mkdir(parents=True,exist_ok=True)
        for name in (ICON_NAME,'umutron',APP_ID):
            out_file=out_dir/f'{name}.png'
            pb.savev(str(out_file),'png',[],[])
            try: out_file.chmod(0o644)
            except OSError: pass
except Exception:
    pass
index_theme=Path.home()/'.local/share/icons/hicolor/index.theme'
if not index_theme.is_file() and Path('/usr/share/icons/hicolor/index.theme').is_file():
    try: atomic_write(index_theme,Path('/usr/share/icons/hicolor/index.theme').read_bytes())
    except OSError: pass
if shutil.which('gtk-update-icon-cache'):
    try: subprocess.run(['gtk-update-icon-cache','-f','-t',str(Path.home()/'.local/share/icons/hicolor')],check=False)
    except Exception: pass
if shutil.which('kbuildsycoca6'):
    try: subprocess.run(['kbuildsycoca6'],check=False)
    except Exception: pass
elif shutil.which('kbuildsycoca5'):
    try: subprocess.run(['kbuildsycoca5'],check=False)
    except Exception: pass
# Desktop Exec escaping follows the desktop-entry specification (not shell quoting).
def quoted(path):
    text=str(path).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
    return '"'+text+'"'
launch='/usr/bin/python3 '+quoted(target/'run.py')
for obsolete in (target/'run-local-api.sh', Path.home()/'.config'/'umutron'/'server.json'):
    try:
        obsolete.unlink()
    except FileNotFoundError:
        pass
config_dir=Path.home()/'.config'/'umutron'
atomic_write(config_dir/'catalog.json',(json.dumps({'APP_BASE_URL':API_ORIGIN})+'\n').encode())
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
desktop=applications/(APP_ID+'.desktop')
atomic_write(desktop,entry.encode())
try: desktop.chmod(0o644)
except OSError: pass
compatibility=applications/'game-library-launcher.desktop'
compatibility_entry=entry.replace('StartupWMClass='+APP_ID+'\n','NoDisplay=true\n')
atomic_write(compatibility,compatibility_entry.encode())
try: compatibility.chmod(0o644)
except OSError: pass
if shutil.which('desktop-file-validate'):
    for path in (desktop,compatibility):
        subprocess.run(['desktop-file-validate',str(path)],check=True)
if shutil.which('update-desktop-database'):
    subprocess.run(['update-desktop-database',str(desktop.parent)],check=True)
if shutil.which('kbuildsycoca6'):
    try: subprocess.run(['kbuildsycoca6'],check=False)
    except Exception: pass
elif shutil.which('kbuildsycoca5'):
    try: subprocess.run(['kbuildsycoca5'],check=False)
    except Exception: pass
print('Installed '+APP_NAME+' and its menu entry. Existing libraries and games were preserved.')
