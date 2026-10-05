"""Local recent-play records written only after an observed game-process milestone."""
import json
from pathlib import Path
from uuid import UUID
from .library import atomic_write


def record(root,game_id,session_id,observed_at):
    UUID(game_id);UUID(session_id)
    if type(observed_at) not in (int,float) or observed_at<=0:raise ValueError('Invalid play timestamp.')
    folder=Path(root)/'play-history';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    atomic_write(folder/(game_id+'.json'),json.dumps({'game_id':game_id,'session_id':session_id,'observed_at':observed_at}).encode())


def recent(library):
    result=[]
    for game in library.games():
        path=library.root/'play-history'/(game['id']+'.json')
        try:
            if path.stat().st_size>4096:continue
            value=json.loads(path.read_text());UUID(value['session_id'])
            if value['game_id']==game['id'] and type(value['observed_at']) in (int,float) and value['observed_at']>0:
                result.append((value['observed_at'],game))
        except (OSError,ValueError,KeyError,TypeError):pass
    return [game for _,game in sorted(result,key=lambda pair:pair[0],reverse=True)]


def revision(root):
    """Atomic record replacement changes the directory; no polling file contents."""
    try:
        info=(Path(root)/'play-history').stat()
        return info.st_dev,info.st_ino,info.st_mtime_ns
    except OSError:return None


class PlayMilestone:
    """Two continuous seconds of selected-executable evidence, never log text alone."""
    def __init__(self):self.first=None;self.token=None;self.recorded=False
    def observe(self,operation,evidence,stopping,now):
        if self.recorded:return False
        if operation!='play' or not evidence or stopping:self.first=None;self.token=None;return False
        if evidence!=self.token:self.first=None;self.token=evidence
        if self.first is None:self.first=now
        if now-self.first<2:return False
        self.recorded=True;return True
