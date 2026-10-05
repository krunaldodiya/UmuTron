"""Fail-closed removal of a verified, dedicated game payload, never a prefix.

Folder confirmation is separate from executable confirmation. Receipts and retry
journals stay machine-local and are never imported as deletion authority.
"""
from contextlib import contextmanager, ExitStack
import ctypes
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID, uuid4

from .library import atomic_write
from .launcher import defaults
from .prefix_guard import acquire as prefix_lock, ensure_idle

MAX_FILES=50000
PAYLOAD_EXTENSIONS={'.exe','.dll','.pak','.dat','.bin','.vpk','.mpq','.bsa','.ba2','.wad','.pck','.ucas','.utoc','.uasset','.umap','.bundle','.assets','.resS'.lower(),'.resource','.manifest','.acb','.awb','.bnk','.wem','.ogg','.wav','.mp3','.mp4','.bik','.bk2','.dds','.ktx','.ttf','.otf','.png','.jpg','.jpeg','.webm','.so','.jar','.loc','.rcc'}
DATA_NAMES={'save','saves','savegame','savegames','saved','userdata','user_data','profiles','screenshots','mods','pfx','drive_c','dosdevices'}
ROOT_NAMES={'games','game','steamapps','common','bin','binaries','x64','x86','win64','win32','program files','program files (x86)','users','downloads','documents','desktop'}


def fingerprint(game):return sha256(json.dumps(game,sort_keys=True).encode()).hexdigest()


def mount_points():
    result=set()
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        field=line.split()[4]
        result.add(re.sub(r'\\([0-7]{3})',lambda match:chr(int(match[1],8)),field))
    return result


@contextmanager
def directory(path):
    """Open every component without following links; keep the final inode pinned."""
    path=Path(path)
    if not path.is_absolute() or '..' in path.parts:raise ValueError('Use an absolute folder without parent traversal.')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        try:
            for part in path.parts[1:]:
                new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=new
        except OSError as error:
            raise ValueError('A folder is unavailable or uses a symbolic link.') from error
        yield fd
    finally:os.close(fd)


def identity(info):return {'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid}


def canonical(value):
    try:return Path(value).expanduser().resolve(strict=False)
    except (OSError,RuntimeError):raise ValueError('Cannot resolve another library path safely.') from None


def move_exclusive(source,destination,source_fd,destination_fd):
    """Linux atomic capture: never replace a destination another writer created."""
    rename=ctypes.CDLL(None,use_errno=True).renameat2
    rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    rename.restype=ctypes.c_int
    if rename(source_fd,os.fsencode(source),destination_fd,os.fsencode(destination),1):
        error=ctypes.get_errno();raise OSError(error,os.strerror(error))
    os.fsync(source_fd);os.fsync(destination_fd)


def matches(info,value):
    if identity(info)!={k:value[k] for k in ('device','inode','uid')}:return False
    if info.st_mode&0o022:return False
    if value['kind']=='directory':return stat.S_ISDIR(info.st_mode)
    return stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_size==value['size'] and info.st_mtime_ns==value['modified']


def private_dir(path):
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    with directory(path) as fd:
        info=os.fstat(fd)
        if info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('Unsafe local receipt directory permissions.')


def read_private(path):
    with directory(path.parent) as parent:
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>8*1024*1024:
                raise ValueError('Invalid local uninstall record.')
            with os.fdopen(os.dup(fd),'r') as stream:return json.load(stream)
        finally:os.close(fd)


def root_idle(root,prefix):
    """Read-only checks; denied inspection is uncertainty, never permission to kill."""
    ensure_idle(prefix)
    root=Path(root)
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name)==os.getpid():continue
        try:
            if process.stat().st_uid!=os.getuid():continue
            links=[process/'cwd',process/'exe']
            links.extend((process/'fd').iterdir())
            for link in links:
                try:
                    target=Path(os.readlink(link))
                    if target.is_absolute() and target.is_relative_to(root):raise RuntimeError('A live process uses this game folder. Close it before uninstalling.')
                except FileNotFoundError:pass
            with (process/'maps').open() as stream:
                data=stream.read(2*1024*1024+1)
            if len(data)>2*1024*1024:raise RuntimeError('Cannot verify that all game files are idle.')
            for line in data.splitlines():
                parts=line.split(maxsplit=5)
                if len(parts)==6 and parts[5].startswith('/') and Path(parts[5]).is_relative_to(root):
                    raise RuntimeError('A live process has game files loaded. Close it before uninstalling.')
        except (FileNotFoundError,ProcessLookupError):continue
        except (PermissionError,OSError):raise RuntimeError('Cannot verify that game files are idle. Uninstall is blocked.') from None


class GameUninstall:
    def __init__(self,library,idle_check=root_idle,runtime_root=None):
        self.library=library;self.idle_check=idle_check
        self.folder=library.root/'installation-roots'
        self.runtime_root=Path(runtime_root or os.environ.get('XDG_RUNTIME_DIR',f'/tmp/umutron-{os.getuid()}'))/'game-root-locks'

    def _paths(self,game_id):
        UUID(game_id)
        return self.folder/(game_id+'.json'),self.folder/(game_id+'-uninstall.json')

    def has_recovery(self,game):return self._paths(game['id'])[1].is_file()

    def root_hint(self,game):
        try:
            value=read_private(self._paths(game['id'])[0])
            return value['root']['path'] if value.get('game_id')==game['id'] else None
        except (OSError,ValueError,KeyError,TypeError):return None

    def _current(self,game):
        current=next((g for g in self.library.games() if g['id']==game['id']),None)
        if current!=game:raise ValueError('Game setup changed. Save and review the current game first.')
        # Read fresh persisted bytes too: a second app/import must not be overwritten.
        disk=json.loads(self.library.path.read_text())
        if disk!=self.library.data:raise ValueError('The library changed in another operation. Reload before uninstalling.')

    def _validate_root(self,game,root,original=None):
        original=Path(original or root);root=Path(root)
        if not root.is_absolute() or root!=Path(os.path.normpath(root)) or '..' in root.parts:
            raise ValueError('Select one absolute game installation folder.')
        protected=[Path('/'),Path.home(),self.library.root,Path('/usr'),Path('/etc'),Path('/var'),Path('/tmp'),Path('/opt'),Path('/boot'),Path('/dev'),Path('/proc'),Path('/sys'),Path('/run'),Path('/mnt'),Path('/media')]
        if original.name.casefold() in ROOT_NAMES or any(original==p or original in p.parents for p in protected):
            raise ValueError('Select the dedicated game folder, not a shared container or binary subfolder.')
        mounts={Path(p) for p in mount_points()}
        if original in mounts or any(p==root or p.is_relative_to(root) for p in mounts):raise ValueError('A volume root or nested mount cannot be uninstalled.')
        exe=Path(game['executable'])
        if not exe.is_absolute() or not exe.is_relative_to(original) or exe==original:
            raise ValueError('The selected executable must be inside this game installation folder.')
        for entry in self.library.games():
            context=defaults(entry,self.library.root)
            for key in ('prefix','proton'):
                value=context[key]
                path=Path(value).expanduser()
                if path.is_absolute():path=canonical(path)
                if path.is_absolute() and (original==path or path.is_relative_to(original) or (key=='proton' and original.is_relative_to(path))):
                    raise ValueError('Game files must be separate from prefixes and Proton runtimes.')
            if entry['id']!=game['id']:
                for value in (entry.get('executable'),entry.get('working_dir')):
                    if value and Path(value).expanduser().is_absolute() and canonical(value).is_relative_to(original):
                        raise ValueError('Another library game uses this installation folder.')
                receipt,_=self._paths(entry['id'])
                if receipt.exists():
                    other=canonical(read_private(receipt)['root']['path'])
                    if other.is_relative_to(original) or original.is_relative_to(other):raise ValueError('Game installation folders overlap.')

    def _inventory(self,fd):
        entries={};device=os.fstat(fd).st_dev
        def walk(current,prefix=''):
            for name in sorted(os.listdir(current)):
                if len(entries)>=MAX_FILES:raise ValueError('Folder exceeds the bounded uninstall inventory.')
                info=os.stat(name,dir_fd=current,follow_symlinks=False);rel=prefix+name
                if info.st_uid!=os.getuid() or info.st_mode&0o022 or info.st_dev!=device:
                    raise ValueError('Mixed ownership, writable shared files or nested volumes are not eligible.')
                if name.casefold() in DATA_NAMES:raise ValueError('Saves, personal data or a prefix are inside this folder. Uninstall is blocked.')
                if stat.S_ISDIR(info.st_mode):
                    child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current)
                    try:
                        if identity(os.fstat(child))!=identity(info):raise ValueError('Directory changed during inspection.')
                        entries[rel]={'kind':'directory',**identity(info)};walk(child,rel+'/')
                    finally:os.close(child)
                elif stat.S_ISREG(info.st_mode) and info.st_nlink==1:
                    if Path(name).suffix.lower() not in PAYLOAD_EXTENSIONS:raise ValueError('Unclassified files are present. Automatic uninstall is unavailable for this folder.')
                    entries[rel]={'kind':'file',**identity(info),'size':info.st_size,'modified':info.st_mtime_ns}
                else:raise ValueError('Links or special files are not eligible for automatic uninstall.')
        walk(fd);return entries

    def inspect(self,game,root):
        self._current(game);root=Path(root);self._validate_root(game,root)
        with directory(root) as fd:
            info=os.fstat(fd)
            if info.st_uid!=os.getuid() or info.st_mode&0o022:raise ValueError('The installation folder must be private to its owner.')
            entries=self._inventory(fd)
            relative=str(Path(game['executable']).relative_to(root))
            if relative not in entries or entries[relative]['kind']!='file':raise ValueError('The game executable is not a regular owned file.')
            return {'version':1,'game_id':game['id'],'game_digest':fingerprint(game),'root':{'path':str(root),**identity(info)},'entries':entries}

    def confirm(self,game,inspection):
        fresh=self.inspect(game,inspection['root']['path'])
        if fresh!=inspection:raise ValueError('Folder contents changed. Review the installation folder again.')
        private_dir(self.folder)
        with directory(self.folder.parent) as parent:os.fsync(parent)
        receipt,journal=self._paths(game['id'])
        if journal.exists():raise ValueError('An uninstall is incomplete. Recover it before confirming another folder.')
        atomic_write(receipt,json.dumps({**fresh,'receipt_id':str(uuid4())}).encode());receipt.chmod(0o600)
        with directory(receipt.parent) as parent:os.fsync(parent)

    def plan(self,game):
        self._current(game);receipt_path,journal_path=self._paths(game['id'])
        try:receipt=read_private(receipt_path)
        except (OSError,ValueError):raise ValueError('Verify the existing installation folder in Setup before uninstalling.') from None
        if receipt.get('version')!=1 or receipt.get('game_id')!=game['id'] or receipt.get('game_digest')!=fingerprint(game):
            raise ValueError('Saved folder verification no longer matches this game. Review it in Setup.')
        UUID(receipt['receipt_id']);original=Path(receipt['root']['path']);journal=None;root=original
        if journal_path.exists():
            journal=read_private(journal_path);UUID(journal['operation_id'])
            root=original.parent/('UmuTron-uninstall-'+journal['operation_id'])
            if journal.get('receipt_id')!=receipt['receipt_id'] or journal.get('stage') not in ('planned','deleting','payload-empty','files-removed'):
                raise ValueError('Invalid uninstall recovery journal.')
            if journal['stage']=='planned' and original.exists():root=original
            elif original.exists():raise ValueError('The original game location was recreated. Recovery needs review.')
        self._validate_root(game,root,original)
        if root.exists():
            with directory(root) as fd:
                if identity(os.fstat(fd))!={k:receipt['root'][k] for k in ('device','inode','uid')}:raise ValueError('Installation folder identity changed.')
                current=self._inventory(fd)
            if journal:
                if any(receipt['entries'].get(k)!=v for k,v in current.items()):raise ValueError('Uninstall recovery contains new or changed files.')
            elif current!=receipt['entries']:raise ValueError('Installation contents changed. Verify the folder again in Setup.')
        elif not journal or journal['stage'] not in ('payload-empty','files-removed'):raise ValueError('Installation folder is missing; its absence is not proof of uninstall.')
        if journal:
            staging=original.parent/('UmuTron-uninstall-stage-'+journal['operation_id'])
            if staging.exists():
                with directory(staging) as fd:self._validate_staging(fd,receipt['entries'],journal)
            elif journal.get('staging') and journal['stage'] not in ('payload-empty','files-removed'):
                raise ValueError('Private uninstall staging is missing; recovery needs review.')
        return {'game':game,'receipt':receipt,'journal':journal,'root':str(root),'original':str(original)}

    @contextmanager
    def _locks(self,plan):
        private_dir(self.runtime_root)
        key=sha256(json.dumps(plan['receipt']['root'],sort_keys=True).encode()).hexdigest()
        with ExitStack() as stack:
            for path in (self.library.root/'launch.lock',self.runtime_root/(key+'.lock')):
                fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);stack.callback(os.close,fd)
                info=os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1:raise ValueError('Unsafe operation lock.')
                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:raise RuntimeError('A game, installer or maintenance operation is active.') from None
            prefix=defaults(plan['game'],self.library.root)['prefix']
            # Existing prefix lock is retained across verification and deletion.
            fd=prefix_lock(prefix,check_processes=False);stack.callback(os.close,fd)
            self.idle_check(plan['root'],prefix);yield

    def _validate_staging(self,fd,expected,journal):
        info=os.fstat(fd)
        if info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('Unsafe private uninstall staging.')
        if journal.get('staging') and identity(info)!=journal['staging']:raise ValueError('Private uninstall staging identity changed.')
        names=os.listdir(fd)
        if names and not journal.get('staging'):raise ValueError('Unrecognized private uninstall staging contents.')
        mapping={sha256(rel.encode()).hexdigest():value for rel,value in expected.items()}
        for name in names:
            value=mapping.get(name)
            if value is None or not matches(os.stat(name,dir_fd=fd,follow_symlinks=False),value):
                raise ValueError('An unexpected captured file was preserved in private uninstall staging. Manual review is required.')
            if value['kind']=='directory':
                child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                try:
                    if os.listdir(child):raise ValueError('Unexpected files in a captured directory were preserved.')
                finally:os.close(child)
        return mapping

    def _clear_staging(self,fd,expected,journal):
        mapping=self._validate_staging(fd,expected,journal)
        for name in os.listdir(fd):
            if mapping[name]['kind']=='directory':os.rmdir(name,dir_fd=fd)
            else:os.unlink(name,dir_fd=fd)
        os.fsync(fd)

    def _delete_tree(self,fd,expected,staging,journal,prefix=''):
        for name in sorted(os.listdir(fd)):
            rel=prefix+name;value=expected.get(rel)
            if value is None:raise ValueError('New file detected during uninstall.')
            info=os.stat(name,dir_fd=fd,follow_symlinks=False)
            if not matches(info,value):raise ValueError('File identity changed during uninstall.')
            if value['kind']=='directory':
                child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                try:
                    if not matches(os.fstat(child),value):raise ValueError('Directory was replaced during uninstall.')
                    self._delete_tree(child,expected,staging,journal,rel+'/')
                finally:os.close(child)
            # Capture first, verify what actually moved, then unlink inside the
            # operation-owned 0700 directory. Writers at the original pathname
            # cannot substitute an unapproved object between verification/unlink.
            captured=sha256(rel.encode()).hexdigest()
            move_exclusive(name,captured,fd,staging)
            self._clear_staging(staging,expected,journal)

    def execute(self,plan):
        with self._locks(plan):
            fresh=self.plan(plan['game'])
            if fresh!=plan:raise ValueError('The uninstall plan changed. Review it again.')
            receipt_path,journal_path=self._paths(plan['game']['id']);original=Path(plan['original']);root=Path(plan['root'])
            journal=plan['journal'] or {'operation_id':str(uuid4()),'receipt_id':plan['receipt']['receipt_id'],'stage':'planned'}
            destination=original.parent/('UmuTron-uninstall-'+journal['operation_id'])
            staging=original.parent/('UmuTron-uninstall-stage-'+journal['operation_id'])
            def save():
                atomic_write(journal_path,json.dumps(journal).encode());journal_path.chmod(0o600)
                with directory(journal_path.parent) as parent:os.fsync(parent)
            with directory(journal_path.parent.parent) as parent:os.fsync(parent)
            save()
            if root==original:
                with directory(original.parent) as parent:
                    with directory(original) as opened:
                        if identity(os.fstat(opened))!={k:plan['receipt']['root'][k] for k in ('device','inode','uid')}:raise ValueError('Installation folder changed.')
                        move_exclusive(original.name,destination.name,parent,parent)
                root=destination
            if journal['stage'] in ('planned','deleting'):
                with directory(root) as fd:
                    if identity(os.fstat(fd))!={k:plan['receipt']['root'][k] for k in ('device','inode','uid')}:raise ValueError('Recovery folder changed.')
                    if not staging.exists():
                        staging.mkdir(mode=0o700)
                        with directory(staging.parent) as parent:os.fsync(parent)
                    with directory(staging) as stage:
                        self._validate_staging(stage,plan['receipt']['entries'],journal)
                        journal.update(stage='deleting',staging=identity(os.fstat(stage)));save()
                        self._clear_staging(stage,plan['receipt']['entries'],journal)
                        self._delete_tree(fd,plan['receipt']['entries'],stage,journal)
                        if os.listdir(fd) or os.listdir(stage):raise ValueError('Files remain. The library entry was kept.')
                        os.fsync(fd);os.fsync(stage)
                        # Durable empty-payload proof precedes the last rmdir, so
                        # retry survives a failed write after the folder is gone.
                        journal['stage']='payload-empty';save()
            if journal['stage']=='payload-empty':
                for folder,expected in ((root,{k:plan['receipt']['root'][k] for k in ('device','inode','uid')}),(staging,journal.get('staging'))):
                    if not folder.exists():continue
                    with directory(folder) as fd:
                        if identity(os.fstat(fd))!=expected or os.listdir(fd):raise ValueError('A recovery folder changed. It was preserved.')
                    with directory(folder.parent) as parent:
                        os.rmdir(folder.name,dir_fd=parent);os.fsync(parent)
                journal['stage']='files-removed';save()
            if original.exists() or root.exists() or staging.exists():raise ValueError('Files remain. The library entry was kept.')
            self._current(plan['game']);self.library.delete(plan['game']['id'])
            with directory(self.library.path.parent) as parent:os.fsync(parent)
            journal_path.unlink();receipt_path.unlink()
            with directory(journal_path.parent) as parent:os.fsync(parent)
