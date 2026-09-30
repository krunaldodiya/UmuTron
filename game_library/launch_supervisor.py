"""Linux subreaper: observe and stop only descendants of this explicit launch."""
from collections import deque
import ctypes
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from game_library.library import atomic_write
from game_library.launcher import MARKER, clean_log, pid_identity, running_game_evidence


def main(request_path):
    request=json.loads(Path(request_path).read_text())
    # Orphaned descendants are adopted here, not by the desktop application.
    if ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)!=0:raise RuntimeError('Unable to enable safe launch supervision.')
    state={'operation':request.get('operation','play'),'session_id':request.get('session_id',''),'game_id':request['game_id'],'title':request['title'],'state':'Preparing','logs':[],'code':None,'proton':request['env']['PROTONPATH'],'supervisor_pid':os.getpid(),'supervisor_start':pid_identity(os.getpid())}
    logs=deque(['Preparing UMU. First use may download Proton and runtime assets.'],maxlen=200)
    stopping=[False];signal.signal(signal.SIGTERM,lambda *_:stopping.__setitem__(0,True))
    owned={};sent=set();stop_at=None;last_save=0;last_evidence=0;pending=b'';code=None;pipe_open=True
    def save():
        state['logs']=list(logs);atomic_write(request['record'],json.dumps(state).encode())
        if request.get('operation')=='installer':atomic_write(Path(request['record']).parent/'installation-sessions'/(request['game_id']+'.json'),json.dumps(state).encode())
    def observe():
        # Parent IDs and start times prevent accidentally targeting reused PIDs.
        table={}
        for directory in Path('/proc').iterdir():
            if not directory.name.isdigit():continue
            try:
                text=(directory/'stat').read_text();fields=text[text.rfind(')')+2:].split()
                table[int(directory.name)]=(int(fields[1]),fields[19],fields[0])
            except (OSError,IndexError,ValueError):continue
        parents={os.getpid()}
        for _ in range(100):
            children={pid for pid,(ppid,_,_) in table.items() if ppid in parents}
            if children<=parents:break
            parents|=children
        for pid in parents-{os.getpid()}:
            if pid in table:owned[pid]=table[pid][1]
        return {pid for pid,identity in owned.items() if pid in table and table[pid][1]==identity and table[pid][2]!='Z'}
    def cancel_requested():
        path=Path(request['record']).parent/'cancel-request.json'
        try:
            if not request.get('session_id') or path.stat().st_size>4096:return False
            value=json.loads(path.read_text());return value.get('session_id')==request['session_id'] and value.get('game_id')==request['game_id']
        except (OSError,ValueError):return False
    try:
        if cancel_requested():state['state']='Stopped';logs.append('Operation cancelled before execution.');return
        prefix=Path(request['env']['WINEPREFIX']);prefix.mkdir(parents=True,exist_ok=True,mode=0o700)
        if prefix.is_symlink() or (any(prefix.iterdir()) and not (prefix/MARKER).is_file()):raise ValueError('Prefix changed before launch. Existing data was preserved.')
        if not (prefix/MARKER).exists():
            with (prefix/MARKER).open('x') as f:f.write('Dedicated UMU prefix for Game Library Launcher.\n')
        save()
        with subprocess.Popen(request['argv'],cwd=request['cwd'],env=request['env'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True) as process:
            owned[process.pid]=pid_identity(process.pid)
            os.set_blocking(process.stdout.fileno(),False)
            selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
            while True:
                if cancel_requested():stopping[0]=True
                live=observe()
                if state['proton'] in ('UMU-Latest','GE-Latest'):
                    for pid in live:
                        try:
                            with (Path('/proc')/str(pid)/'environ').open('rb') as stream:entries=stream.read(262144).split(b'\x00')
                            env=dict(e.split(b'=',1) for e in entries if b'=' in e)
                            tool=Path(os.fsdecode(env.get(b'PROTONPATH',b'')))
                            if env.get(b'WINEPREFIX')==os.fsencode(prefix) and tool.is_absolute() and (tool/'proton').is_file():state['proton']=str(tool.resolve());break
                        except OSError:continue
                if stopping[0]:
                    state['state']='Stopping'
                    if stop_at is None:stop_at=time.monotonic();logs.append('Stopping this launch’s owned processes…')
                    for pid in live:
                        force=time.monotonic()-stop_at>3
                        if pid not in sent or force:
                            if pid_identity(pid)==owned[pid]:
                                try:os.kill(pid,signal.SIGKILL if force else signal.SIGTERM)
                                except ProcessLookupError:pass
                            sent.add(pid)
                for key,_ in selector.select(.08):
                    chunk=os.read(key.fileobj.fileno(),262144)
                    if not chunk:selector.unregister(key.fileobj);pipe_open=False
                    else:
                        pending+=chunk
                        while b'\n' in pending or len(pending)>8192:
                            raw,_,pending=pending.partition(b'\n') if b'\n' in pending else (pending[:8192],b'',pending[8192:])
                            text=clean_log(raw.decode('utf-8',errors='replace'))
                            if text:
                                logs.append(text);lower=text.lower()
                                if not stopping[0]:
                                    if state['state']!='Running' and any(w in lower for w in ('download','restoring runtime','setting up unified','updating steamrt')):state['state']='Downloading runtime'
                                    if 'waitforexitandrun' in lower:state['state']='Running'
                if not stopping[0] and state['state']!='Running' and time.monotonic()-last_evidence>.5:
                    last_evidence=time.monotonic()
                    if running_game_evidence(os.getpid(),state['supervisor_start'],request['argv'][1]):state['state']='Running'
                code=process.poll()
                if code is not None:
                    while True:
                        try:
                            pid,_=os.waitpid(-1,os.WNOHANG)
                            if pid==0:break
                        except ChildProcessError:break
                    if live and not stopping[0]:state['state']='Running'
                    if not live:break
                if time.monotonic()-last_save>.2:save();last_save=time.monotonic()
                if not pipe_open:time.sleep(.08)
            selector.close()
        if pending:logs.append(clean_log(pending.decode('utf-8',errors='replace')))
        state['code']=code;state['state']='Stopped' if stopping[0] else ('Finished' if code==0 else 'Error')
        logs.append('Launch stopped.' if stopping[0] else f'UMU exited with code {code}.')
    except Exception as error:
        state['state']='Error';logs.append(clean_log(str(error)))
    finally:save()


if __name__=='__main__':main(sys.argv[1])
