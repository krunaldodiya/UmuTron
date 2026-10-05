"""Private production registry. No game-file, Setup or execution authority."""
import os
from pathlib import Path
import sqlite3
import stat

from .storage import StateStore, StorageError, StorageModel
from .storage_observer import LinuxVolumes


class PrivateStateStore(StateStore):
    def connect(self):
        path=Path(self.path)
        for part in [*reversed(path.parent.parents),path.parent]:
            if part.is_symlink():raise StorageError('Storage registry ancestry must not use symbolic links.')
        parent=path.parent.stat()
        if parent.st_uid!=os.getuid() or parent.st_mode&0o077:
            raise StorageError('The local Storage registry folder must be private to its owner.')
        for extra in (path,Path(str(path)+'-journal'),Path(str(path)+'-wal'),Path(str(path)+'-shm')):
            if not os.path.lexists(extra):continue
            info=extra.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_nlink!=1:
                raise StorageError('The local Storage registry has unsafe ownership or links. Existing files were preserved.')
        if not os.path.lexists(path):
            try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            except FileExistsError:return self.connect()
            else:
                os.fsync(fd);os.close(fd)
                directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:os.fsync(directory)
                finally:os.close(directory)
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        connection=None
        try:
            before=os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or before.st_mode&0o077 or before.st_nlink!=1:
                raise StorageError('Storage registry changed or has unsafe ownership.')
            if before.st_size>8*1024*1024:raise StorageError('Storage registry is too large. Preserve it for recovery.')
            connection=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=2)
            after=path.lstat()
            if (before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino):raise StorageError('Storage registry changed while opening.')
            return connection
        except BaseException:
            if connection is not None:connection.close()
            raise
        finally:os.close(fd)


class StorageAccess(StorageModel):
    reason=''


def configured_storage(root):
    return StorageAccess(PrivateStateStore(Path(root)/'storage.sqlite3'),LinuxVolumes())


class DemoStorage:
    """Explicit --demo only: no observer or persistent registry."""
    enabled=False
    reason='Demo only. Real storage registrations are unchanged.'
    def snapshot(self):return {'registrations':[],'default_install':None,'active_jobs':0}
    def choices(self):return {'volumes':[],'registered':set()}
