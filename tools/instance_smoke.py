"""Single-instance integration on private D-Bus and isolated app data only."""
import os
from pathlib import Path
import subprocess
import tempfile
import time

with tempfile.TemporaryDirectory() as temp:
    env=dict(os.environ,XDG_DATA_HOME=temp+'/data',XDG_CONFIG_HOME=temp+'/config',XDG_CACHE_HOME=temp+'/cache',GSK_RENDERER='cairo')
    script=Path(__file__).resolve().parents[1]/'run.py'
    first=subprocess.Popen(['/usr/bin/python3',str(script)],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    try:
        deadline=time.monotonic()+5
        while not (Path(temp)/'data/game-library-launcher/proton-manager').exists() and time.monotonic()<deadline:
            assert first.poll() is None;time.sleep(.05)
        time.sleep(.4)
        second=subprocess.run(['/usr/bin/python3',str(script),'--fullscreen'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=5)
        assert second.returncode==0,second.stdout.decode()
        assert first.poll() is None,'Existing application must stay alive'
        assert not (Path(temp)/'data/game-library-launcher/launch-session.json').exists(),'Activation never launches a game'
    finally:
        first.terminate()
        try:output=first.communicate(timeout=5)[0]
        except subprocess.TimeoutExpired:first.kill();output=first.communicate()[0]
    print('PASS: second launch activates existing instance and exits; no game or installer started')
