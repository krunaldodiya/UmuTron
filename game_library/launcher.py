"""Explicit UMU launches. Data never becomes a shell command; no global process control."""
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import fcntl
import json
import signal
import sys
from uuid import UUID

FIELDS={'runner','proton','prefix','arguments'}
ACTIVE={'Preparing','Downloading runtime','Running','Stopping'}
MARKER='.metadata-manager-prefix'


def validate_settings(settings):
    if not isinstance(settings,dict) or set(settings)-FIELDS: raise ValueError('Invalid direct launch settings.')
    for key in ('runner','proton','prefix'):
        value=settings.get(key,'')
        if not isinstance(value,str) or len(value)>4096 or '\x00' in value: raise ValueError('Invalid launch '+key+'.')
    args=settings.get('arguments',[])
    if not isinstance(args,list) or len(args)>128 or any(not isinstance(a,str) or len(a)>8192 or '\x00' in a or '\n' in a or '\r' in a for a in args):
        raise ValueError('Direct arguments must be a list of at most 128 single-line strings.')


def discover(home=None):
    home=Path(home or Path.home())
    roots=[home/'.local/share/Steam/compatibilitytools.d',home/'.steam/steam/compatibilitytools.d',home/'.local/share/umu/compatibilitytools',home/'.local/share/Steam/steamapps/common']
    protons={str(p.resolve()) for root in roots if root.is_dir() for p in root.iterdir() if p.is_dir() and (p/'proton').is_file()}
    return {'runner':shutil.which('umu-run') or '', 'protons':sorted(protons,key=lambda p:('GE-Proton' not in Path(p).name,Path(p).name),reverse=False)}


def defaults(game,root):
    settings=game.get('launch',{}); validate_settings(settings)
    found=discover()
    try:arguments=list(settings['arguments']) if 'arguments' in settings else shlex.split(game.get('arguments',''))
    except ValueError:raise ValueError('Legacy launch arguments have unmatched quotes. Set the Direct Play argument list explicitly.') from None
    return {'runner':settings.get('runner') or found['runner'],
            'proton':settings.get('proton') or (found['protons'][0] if found['protons'] else 'UMU-Latest'),
            'prefix':settings.get('prefix') or str(Path(root)/'prefixes'/game['id']),
            'arguments':arguments}


def build_command(game,root,inherited=None):
    settings=defaults(game,root)
    runner=Path(settings['runner']).expanduser()
    if not runner.is_absolute() or not runner.is_file() or not os.access(runner,os.X_OK): raise ValueError('Install umu-run or choose its executable path in Direct Play.')
    exe=Path(game['executable']).expanduser()
    if not game['executable'] or not exe.is_absolute() or not exe.is_file(): raise ValueError('Choose an existing game executable.')
    cwd=Path(game['working_dir']).expanduser() if game['working_dir'] else exe.parent
    if not cwd.is_absolute() or not cwd.is_dir(): raise ValueError('The working directory does not exist.')
    proton=settings['proton']
    if proton not in ('UMU-Latest','GE-Latest'):
        tool=Path(proton).expanduser()
        if not tool.is_absolute() or not tool.is_dir() or not (tool/'proton').is_file(): raise ValueError('Choose a Proton folder containing the proton launcher, or UMU-Latest / GE-Latest.')
        proton=str(tool)
    prefix=Path(settings['prefix']).expanduser()
    if not prefix.is_absolute() or prefix==exe.parent or prefix.is_relative_to(exe.parent): raise ValueError('Use a dedicated prefix outside the game folder.')
    if prefix.exists():
        if not prefix.is_dir() or prefix.is_symlink(): raise ValueError('The prefix must be a dedicated directory, not a file or symbolic link.')
        if any(prefix.iterdir()) and not (prefix/MARKER).is_file(): raise ValueError('This folder already contains data. Choose a new empty prefix; existing game prefixes are preserved.')
    if any(parent.is_symlink() for parent in prefix.parents): raise ValueError('Choose a prefix without symbolic-link parents.')
    env={k:v for k,v in (inherited if inherited is not None else os.environ).items() if k in {'HOME','USER','LOGNAME','PATH','LANG','DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','XAUTHORITY','XDG_RUNTIME_DIR','XDG_SESSION_TYPE','XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_DIRS','PULSE_SERVER','PIPEWIRE_REMOTE','DRI_PRIME','__NV_PRIME_RENDER_OFFLOAD','__GLX_VENDOR_LIBRARY_NAME'} or k.startswith('LC_')}
    env.update(WINEPREFIX=str(prefix),PROTONPATH=proton,UMU_LOG='debug',PYTHONUNBUFFERED='1')
    # GAMEID/STORE are deliberately unset; catalog IDs are not gamefix IDs.
    return [str(runner),str(exe),*settings['arguments']],str(cwd),env


def clean_log(line):
    line=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',line)
    if re.search(r'\b[A-Za-z_][A-Za-z0-9_]*=',line) and 'DEBUG' in line: return ''
    line=re.sub(r'(?i)(token|password|secret|authorization)(\s*[:=]\s*)\S+',r'\1\2[redacted]',line)
    line=re.sub(r'(https?://[^\s?]+)\?\S+',r'\1?[redacted]',line)
    return line.strip()[:2000]


def pid_identity(pid):
    try:
        text=Path(f'/proc/{pid}/stat').read_text();fields=text[text.rfind(')')+2:].split()
        return fields[19]
    except (OSError,IndexError):return None


class Launcher:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.record=self.root/'launch-session.json';self.processes=[]

    def active(self):
        fd=os.open(self.root/'launch.lock',os.O_CREAT|os.O_RDWR,0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return True
            for process in self.processes:
                try:process.wait(timeout=.05)
                except subprocess.TimeoutExpired:pass
            return False
        finally:os.close(fd)

    def current(self):
        if not self.record.exists():return {}
        try:
            if self.record.stat().st_size>500000:return {}
            record=json.loads(self.record.read_text()); UUID(record['game_id'])
            if record['state'] not in ACTIVE|{'Finished','Error','Stopped'}:return {}
            return record
        except (OSError,ValueError,KeyError,TypeError):return {}

    def snapshot(self,game_id):
        state=self.current()
        if state.get('game_id')!=game_id:return {'state':'Not started','logs':[],'code':None}
        if state['state'] in ACTIVE and not self.active():
            state['state']='Error';state['logs']=[*state.get('logs',[])[-199:],'Launch supervisor ended unexpectedly. Review before retrying.']
        return state

    def start(self,game):
        from .library import atomic_write
        argv,cwd,env=build_command(game,self.root)
        fd=os.open(self.root/'launch.lock',os.O_CREAT|os.O_RDWR,0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('A game is already active. Stop or finish it before launching another.') from None
            request={'game_id':game['id'],'title':game['title'],'argv':argv,'cwd':cwd,'env':env,'record':str(self.record)}
            atomic_write(self.root/'launch-request.json',json.dumps(request).encode())
            state={'game_id':game['id'],'title':game['title'],'state':'Preparing','logs':['Preparing UMU. First use may download Proton and runtime assets.'],'code':None}
            atomic_write(self.record,json.dumps(state).encode())
            supervisor=Path(__file__).with_name('launch_supervisor.py')
            process=subprocess.Popen([sys.executable,str(supervisor),str(self.root/'launch-request.json')],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,pass_fds=(fd,))
            self.processes=[p for p in self.processes if p.poll() is None]+[process]
        except Exception as error:
            if not isinstance(error,RuntimeError):
                atomic_write(self.record,json.dumps({'game_id':game['id'],'title':game['title'],'state':'Error','logs':[str(error)[:2000]],'code':None}).encode())
            raise
        finally:os.close(fd)

    def stop(self,game_id):
        state=self.current()
        if not self.active() or state.get('game_id')!=game_id:raise RuntimeError('This game has no owned active launch.')
        pid=state.get('supervisor_pid');identity=state.get('supervisor_start')
        if type(pid) is not int or not identity or pid_identity(pid)!=identity:raise RuntimeError('The launch supervisor is still preparing or no longer exists. Try again shortly.')
        os.kill(pid,signal.SIGTERM)
