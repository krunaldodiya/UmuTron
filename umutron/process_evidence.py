"""Conservative local evidence for recent-play history, separate from UI status.

argv[0] must resolve to the selected file through an absolute Unix path or an
explicit Wine drive mapping. A basename, wrapper argument or log is insufficient.
"""
import os
from pathlib import Path
import re
import stat


def _process(proc,pid):
    text=(proc/str(pid)/'stat').read_text();fields=text[text.rfind(')')+2:].split()
    return int(fields[1]),fields[19],fields[0]


def _file(arg,prefix):
    if arg.startswith('/'):return Path(arg).resolve(strict=True)
    match=re.fullmatch(r'([A-Za-z]):[\\/](.*)',arg)
    if not match:return None
    drive=Path(prefix)/'dosdevices'/(match[1].lower()+':')
    if not drive.is_symlink():return None
    parts=match[2].replace('\\','/').split('/')
    if any(part in ('.','..') for part in parts):return None
    return drive.resolve(strict=True).joinpath(*parts).resolve(strict=True)


def selected_game_evidence(supervisor_pid,supervisor_start,executable,prefix,proc=Path('/proc')):
    """Return one stable (PID,start-time,device,inode) token, or no evidence."""
    if type(supervisor_pid) is not int or not supervisor_start:return None
    try:
        if _process(proc,supervisor_pid)[1]!=supervisor_start:return None
        selected=Path(executable).resolve(strict=True);info=selected.stat()
        if not selected.is_absolute() or not stat.S_ISREG(info.st_mode):return None
        selected_identity=(info.st_dev,info.st_ino);table={}
        for index,entry in enumerate(proc.iterdir()):
            if index>=8192:return None
            if not entry.name.isdigit():continue
            try:table[int(entry.name)]=_process(proc,int(entry.name))
            except (OSError,IndexError,ValueError):continue
        owned={supervisor_pid}
        for _ in range(100):
            children={pid for pid,(parent,_,state) in table.items() if parent in owned and state!='Z'}
            if children<=owned:break
            owned|=children
        else:return None
        tokens=[]
        for pid in owned-{supervisor_pid}:
            try:
                with (proc/str(pid)/'cmdline').open('rb') as stream:raw=stream.read(8193)
                if b'\0' not in raw or len(raw)>8192:continue
                arg=os.fsdecode(raw.split(b'\0',1)[0]);path=_file(arg,prefix)
                if path is None:continue
                current=path.stat()
            except (OSError,RuntimeError,ValueError):
                # A helper may exit or name a path visible only inside Proton's
                # runtime. It is not evidence, but must not veto a verified game.
                continue
            if (current.st_dev,current.st_ino)!=selected_identity:continue
            # Recheck the whole chain, not just the leaf, to reject PID reuse.
            ancestor=pid
            for _ in range(100):
                if _process(proc,ancestor)!=table[ancestor]:return None
                if ancestor==supervisor_pid:break
                ancestor=table[ancestor][0]
            else:return None
            tokens.append((pid,table[pid][1],*selected_identity))
        return tokens[0] if len(tokens)==1 else None
    except (OSError,RuntimeError,KeyError,IndexError,ValueError):return None
