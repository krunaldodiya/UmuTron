"""Bounded local diagnostics; never follow links or touch game/prefix data."""
import fcntl
import os
from pathlib import Path
import time
from uuid import UUID

MAX_FILE=8*1024*1024
MAX_TOTAL=100*1024*1024
MAX_AGE=14*24*60*60


def log_files(root):
    folder=Path(root)/'diagnostics'
    if not folder.is_dir() or folder.is_symlink():return []
    files=[]
    for game in folder.iterdir():
        try:UUID(game.name)
        except ValueError:continue
        if game.is_symlink() or not game.is_dir():continue
        files.extend(p for p in game.iterdir() if p.suffix=='.log' and not p.is_symlink() and p.is_file())
    return files


def cleanup(root,clear=False,now=None):
    """Caller holds launch.lock; no runner may be writing while logs are cleaned."""
    now=time.time() if now is None else now
    kept=[];removed=0
    for p in log_files(root):
        stat=p.stat()
        if clear or now-stat.st_mtime>MAX_AGE:
            p.unlink();removed+=1;continue
        if stat.st_size>MAX_FILE:
            with p.open('rb') as stream:
                stream.seek(-MAX_FILE,os.SEEK_END);tail=stream.read(MAX_FILE)
            with p.open('wb') as stream:stream.write(tail)
            os.utime(p,(stat.st_atime,stat.st_mtime))
        kept.append((stat.st_mtime,p,p.stat().st_size))
    total=sum(size for _,_,size in kept)
    for _,p,size in sorted(kept):
        if total<=MAX_TOTAL:break
        p.unlink();total-=size;removed+=1
    return removed


def clear_all(root):
    with (Path(root)/'launch.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Finish the active game or installer before clearing diagnostic logs.') from None
        return cleanup(root,clear=True)
