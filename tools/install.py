#!/usr/bin/python3
"""Install the desktop app for the current user; no root or game execution."""
from pathlib import Path
import json
import os
import shlex
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
api_dir=source.parent/'UmuTron-FastAPI'

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
if (api_dir/'docker-compose.yml').is_file():
    # Keep the installed launcher pointed at the local-only FastAPI stack when
    # this install is made from the workspace containing both projects.
    wrapper=target/'run-local-api.sh'
    script=f'''#!/bin/sh
set -eu
API_DIR="${{UMUTRON_API_DIR:-}}"
if [ -z "$API_DIR" ]; then API_DIR={shlex.quote(str(api_dir))}; fi
export UMUTRON_API_DIR="$API_DIR"
export APP_BASE_URL="${{APP_BASE_URL:-http://127.0.0.1:8000}}"
export UMUTRON_ALLOW_LOOPBACK_HTTP=1
if [ -z "${{INTERNAL_API_KEY:-}}" ] && [ -f "$API_DIR/.env" ]; then
    INTERNAL_API_KEY="$(awk -F= '$1 == "INTERNAL_API_KEY" {{ sub(/^[^=]*=/, ""); sub(/\\r$/, ""); print; exit }}' "$API_DIR/.env")"
    export INTERNAL_API_KEY
fi
if [ -n "${{INTERNAL_API_KEY:-}}" ]; then
    export UMUTRON_API_KEY="${{UMUTRON_API_KEY:-$INTERNAL_API_KEY}}"
fi
exec /usr/bin/python3 "$HOME/.local/opt/umutron/run.py" "$@"
'''
    atomic_write(wrapper,script.encode())
    try: wrapper.chmod(0o755)
    except OSError: pass
    config_dir=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'umutron'
    atomic_write(config_dir/'server.json',(json.dumps({'repo_dir':str(api_dir)})+'\n').encode())
    launch=quoted(wrapper)
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
