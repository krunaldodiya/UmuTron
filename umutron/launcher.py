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
import time
from uuid import UUID
from .runner_selection import effective_selector, global_selector, parse_release
from .installer_identity import is_installer_executable

FIELDS={'runner','proton','prefix','arguments','dll_overrides'}
ACTIVE={'Preparing','Downloading runtime','Running','Stopping'}
MARKER='.metadata-manager-prefix'


def preparation_progress(record):
    """Report observed UMU output and bytes, never invent a total or percentage."""
    logs=record.get('logs',[])
    stage=next((line for line in reversed(logs) if any(word in line.lower() for word in ('downloading','extracting','verifying','restoring','setting up','updating steamrt'))),record.get('state','Preparing'))
    transferred=record.get('downloaded_bytes')
    for line in reversed(logs):
        match=re.search(r"Writing: (.+\.parts)$",line)
        if not match:continue
        path=Path(match.group(1).strip("'\""))
        try:
            if path.is_absolute() and not path.is_symlink() and path.is_file():transferred=path.stat().st_size
        except OSError:pass
        break
    return {'stage':record.get('preparation_stage') or stage,'bytes':transferred}


def validate_settings(settings):
    if not isinstance(settings,dict) or set(settings)-FIELDS: raise ValueError('Invalid direct launch settings.')
    for key in ('runner','proton','prefix'):
        value=settings.get(key,'')
        if not isinstance(value,str) or len(value)>4096 or '\x00' in value: raise ValueError('Invalid launch '+key+'.')
    overrides=settings.get('dll_overrides','')
    if not isinstance(overrides,str) or len(overrides)>1024 or (overrides and not re.fullmatch(r'[A-Za-z0-9_.-]+=(?:n,b|b,n|n|b|d)(?:;[A-Za-z0-9_.-]+=(?:n,b|b,n|n|b|d))*',overrides)):
        raise ValueError('DLL overrides must use entries such as winmm=n,b, separated by semicolons. Allowed orders: n,b / b,n / n / b / d.')
    args=settings.get('arguments',[])
    if not isinstance(args,list) or len(args)>128 or any(not isinstance(a,str) or len(a)>8192 or '\x00' in a or '\n' in a or '\r' in a for a in args):
        raise ValueError('Direct arguments must be a list of at most 128 single-line strings.')


def discover(home=None):
    home=Path(home or Path.home())
    roots=[home/'.local/share/Steam/compatibilitytools.d',home/'.steam/steam/compatibilitytools.d',home/'.local/share/umu/compatibilitytools',home/'.local/share/Steam/steamapps/common']
    protons={str(p.resolve()) for root in roots if root.is_dir() for p in root.iterdir() if p.is_dir() and (p/'proton').is_file()}
    return {'runner':shutil.which('umu-run') or '', 'protons':sorted(protons,key=lambda p:('GE-Proton' not in Path(p).name,Path(p).name),reverse=False)}

def gamemode_binary():
    return shutil.which('gamemoderun')

def is_gamemode_enabled(root):
    try:
        path=Path(root)/'library.json'
        if path.is_file():
            data=json.loads(path.read_text())
            return bool(data.get('settings',{}).get('gamemode',False))
    except Exception:pass
    return False

def detected_dll_overrides(exe_path):
    if not exe_path:return ''
    try:
        folder=Path(exe_path).parent
        if not folder.is_dir():return ''
        overrides=[]
        names={f.name.lower() for f in folder.iterdir() if f.is_file()}
        if 'dbghelp.dll' in names:overrides.append('dbghelp=n,b')
        if 'winmm.dll' in names:overrides.append('winmm=n,b')
        if any(c in names for c in ('codex64.dll','codex.dll')):
            overrides.extend(['lsteamclient=d','steamclient64=n,b','steamclient=n,b'])
        return ';'.join(dict.fromkeys(overrides))
    except Exception:return ''


def defaults(game,root):
    settings=game.get('launch',{}); validate_settings(settings)
    installed=game.get('installation',{})
    found=discover()
    try:arguments=list(settings['arguments']) if 'arguments' in settings else shlex.split(game.get('arguments',''))
    except ValueError:raise ValueError('Legacy launch arguments have unmatched quotes. Set the Direct Play argument list explicitly.') from None
    overrides=settings.get('dll_overrides')
    if overrides is None or overrides=='':overrides=detected_dll_overrides(game.get('executable'))
    return {'runner':settings.get('runner') or found['runner'],
            'proton':effective_selector(game,global_selector(root)),
            'prefix':settings.get('prefix') or installed.get('prefix') or str(Path(root)/'prefixes'/game['id']),
            'arguments':arguments,'dll_overrides':overrides}

def build_command(game,root,inherited=None,allow_prepare=False,gamemode=None):
    settings=defaults(game,root)
    runner=Path(settings['runner']).expanduser()
    if not runner.is_absolute() or not runner.is_file() or not os.access(runner,os.X_OK): raise ValueError('Install umu-run or choose its executable path in Direct Play.')
    exe=Path(game['executable']).expanduser()
    if not game['executable'] or not exe.is_absolute() or not exe.is_file(): raise ValueError('Choose an existing game executable.')
    cwd=Path(game['working_dir']).expanduser() if game['working_dir'] else exe.parent
    if not cwd.is_absolute() or not cwd.is_dir(): raise ValueError('The working directory does not exist.')
    proton=settings['proton']
    if parse_release(proton):
        from .proton_manager import ProtonManager
        installed=ProtonManager(Path(root)/'proton-manager').installed_release(proton)
        if installed:proton=installed
        elif not allow_prepare:raise ValueError('This Proton version is not installed yet. Play or Launch Installer will download and verify it first.')
    if proton not in ('UMU-Latest','GE-Latest') and not parse_release(proton):
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
    env.update(PROTON_LOG='-all,err+all,warn+seh',PROTON_LOG_DIR=str(Path(root)/'diagnostics'/game['id']))
    if settings['dll_overrides']:env['WINEDLLOVERRIDES']=settings['dll_overrides']
    if game.get('metadata_app_id'):env['GAMEID']=str(game['metadata_app_id'])
    if gamemode is None:gamemode=is_gamemode_enabled(root)
    cmd=[str(runner),str(exe),*settings['arguments']]
    if gamemode and gamemode_binary():cmd=[gamemode_binary(),*cmd]
    return cmd,str(cwd),env


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


def running_game_evidence(supervisor_pid,supervisor_start,executable):
    """Bounded read-only evidence: the selected executable is an owned descendant.

    UMU and Wine wrapper argv can contain the game path as a later argument;
    only argv[0] counts. Wine drive letters differ from host paths, so compare
    the executable filename, within the verified supervisor ancestry only.
    """
    if type(supervisor_pid) is not int or not supervisor_start or pid_identity(supervisor_pid)!=supervisor_start:return False
    filename=str(executable).replace('\\','/').rsplit('/',1)[-1].casefold()
    if not filename:return False
    table={}
    for index,directory in enumerate(Path('/proc').iterdir()):
        if index>=8192:break
        if not directory.name.isdigit():continue
        try:
            raw=(directory/'stat').read_text();fields=raw[raw.rfind(')')+2:].split()
            table[int(directory.name)]=(int(fields[1]),fields[19],fields[0])
        except (OSError,IndexError,ValueError):continue
    owned={supervisor_pid}
    for _ in range(100):
        children={pid for pid,(parent,_,state) in table.items() if parent in owned and state!='Z'}
        if children<=owned:break
        owned|=children
    for pid in owned-{supervisor_pid}:
        try:
            with (Path('/proc')/str(pid)/'cmdline').open('rb') as stream:arg=stream.read(8192).split(b'\x00',1)[0].decode('utf-8',errors='replace').strip()
            if arg.replace('\\','/').rsplit('/',1)[-1].casefold()==filename and pid_identity(pid)==table[pid][1]:return True
        except OSError:continue
    return False


class Launcher:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.record=self.root/'launch-session.json';self.processes=[];self.evidence_cache={}

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
            if record['state'] in ('Preparing','Downloading runtime'):
                key=(record.get('supervisor_pid'),record.get('supervisor_start'),record['game_id'])
                cached=self.evidence_cache.get('result')
                if not cached or cached[0]!=key or time.monotonic()-cached[1]>.5:
                    running=False;request_path=self.root/'launch-request.json'
                    if request_path.is_file() and request_path.stat().st_size<=500000:
                        request=json.loads(request_path.read_text())
                        target_exe=request.get('executable') or (request['argv'][2] if len(request.get('argv',[]))>2 and Path(request['argv'][0]).name=='gamemoderun' else request['argv'][1] if len(request.get('argv',[]))>1 else '')
                        if request.get('game_id')==record['game_id'] and target_exe:
                            running=running_game_evidence(key[0],key[1],target_exe)
                    cached=(key,time.monotonic(),running);self.evidence_cache['result']=cached
                if cached[2]:record['state']='Running'
            return record
        except (OSError,ValueError,KeyError,TypeError):return {}

    def snapshot(self,game_id):
        state=self.current()
        if state.get('game_id')!=game_id:return {'state':'Not started','logs':[],'code':None}
        if state['state'] in ACTIVE and not self.active():
            state['state']='Error';state['logs']=[*state.get('logs',[])[-199:],'Launch supervisor ended unexpectedly. Review before retrying.']
        return state

    def start(self,game,operation='play',before_start=None,runtime_recipe=None,runtime_context=None):
        from .library import atomic_write
        if operation not in ('play','installer','runtime'):raise ValueError('Unknown operation.')
        runtime_plan=None
        if operation=='runtime':
            from .runtime_maintenance import install_plan
            runtime_plan=install_plan(game,self.root,runtime_recipe)
            if runtime_context is None or tuple(runtime_context)!=runtime_plan['context']:raise ValueError('Runtime confirmation context changed; review again.')
            game=runtime_plan['game']
        if operation=='play' and game.get('installation',{}).get('mode')=='installer' and not game['installation'].get('confirmed'):raise ValueError('Confirm the installed game executable in Manage Game before playing.')
        if operation=='play' and is_installer_executable(game):raise ValueError('Play cannot run setup. Confirm the installed game executable.')
        if runtime_plan:
            from copy import deepcopy
            probe=deepcopy(game);probe.update(executable=str(Path(__file__).resolve()),working_dir=str(Path(__file__).parent.resolve()))
            argv,cwd,env=build_command(probe,self.root)
        else:argv,cwd,env=build_command(game,self.root,allow_prepare=True)
        prefix_fd=None
        fd=os.open(self.root/'launch.lock',os.O_CREAT|os.O_RDWR,0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('A game is already active. Stop or finish it before launching another.') from None
            from .prefix_guard import acquire
            prefix_fd=acquire(env['WINEPREFIX'],check_processes=operation=='runtime')
            from .diagnostics import cleanup
            cleanup(self.root)
            session=str(__import__('uuid').uuid4())
            request={'operation':operation,'session_id':session,'game_id':game['id'],'title':game['title'],'executable':str(game.get('executable','')),'argv':argv,'cwd':cwd,'env':env,'record':str(self.record)}
            if runtime_plan:
                request.update(recipe=runtime_recipe,runtime_game=game,runtime_context=list(runtime_plan['context']))
            atomic_write(self.root/'launch-request.json',json.dumps(request).encode())
            state={'operation':operation,'session_id':session,'game_id':game['id'],'title':game['title'],'state':'Preparing','logs':['Preparing UMU. First use may download Proton and runtime assets.'],'code':None}
            if before_start:before_start(state,env)
            atomic_write(self.record,json.dumps(state).encode())
            if operation=='installer':atomic_write(self.root/'installation-sessions'/ (game['id']+'.json'),json.dumps(state).encode())
            supervisor=Path(__file__).with_name('launch_supervisor.py')
            process=subprocess.Popen([sys.executable,str(supervisor),str(self.root/'launch-request.json')],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,pass_fds=(fd,prefix_fd))
            self.processes=[p for p in self.processes if p.poll() is None]+[process]
        except Exception as error:
            if not isinstance(error,RuntimeError):
                failure={'operation':operation,'session_id':locals().get('session',''),'game_id':game['id'],'title':game['title'],'state':'Error','logs':[str(error)[:2000]],'code':None}
                atomic_write(self.record,json.dumps(failure).encode())
                if operation=='installer':atomic_write(self.root/'installation-sessions'/(game['id']+'.json'),json.dumps(failure).encode())
            raise
        finally:
            if prefix_fd is not None:os.close(prefix_fd)
            os.close(fd)

    def stop(self,game_id):
        state=self.current()
        if not self.active() or state.get('game_id')!=game_id:raise RuntimeError('This game has no owned active launch.')
        pid=state.get('supervisor_pid');identity=state.get('supervisor_start')
        if type(pid) is not int and state.get('state')=='Preparing' and state.get('session_id'):
            from .library import atomic_write
            atomic_write(self.root/'cancel-request.json',json.dumps({'session_id':state['session_id'],'game_id':game_id}).encode());return
        if type(pid) is not int or not identity or pid_identity(pid)!=identity:raise RuntimeError('The launch supervisor no longer exists. Review the operation status before retrying.')
        os.kill(pid,signal.SIGTERM)
