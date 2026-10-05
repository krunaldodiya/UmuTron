"""Read-only Linux volume snapshots. No mount, format, privilege or payload calls."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from uuid import UUID

from .storage import StorageError, Volume
from .storage_topology import InternalPartitions

BLOCK='org.freedesktop.UDisks2.Block'
FILESYSTEM='org.freedesktop.UDisks2.Filesystem'
MAX_MOUNTS=4096


def read_objects():
    from gi.repository import Gio, GLib
    try:
        bus=Gio.bus_get_sync(Gio.BusType.SYSTEM,None)
        value=bus.call_sync('org.freedesktop.UDisks2','/org/freedesktop/UDisks2',
            'org.freedesktop.DBus.ObjectManager','GetManagedObjects',None,
            GLib.VariantType.new('(a{oa{sa{sv}}})'),Gio.DBusCallFlags.NO_AUTO_START,1500,None)
        if value.get_size()>4*1024*1024:raise StorageError('Drive discovery returned too much data.')
        return value.unpack()[0]
    except GLib.Error as error:
        raise StorageError('Drive discovery is unavailable. Connect a drive and check that UDisks2 is running.') from error


def read_mounts():
    with Path('/proc/self/mountinfo').open() as stream:value=stream.read(2*1024*1024+1)
    if len(value)>2*1024*1024:raise StorageError('The mounted-drive list is too large.')
    return value


def mount_rows(value):
    rows=[]
    decode=lambda text:re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),text)
    try:
        for line in value.splitlines():
            before,after=line.split(' - ',1);fields=before.split();tail=after.split()
            major,minor=map(int,fields[2].split(':'))
            rows.append({'id':int(fields[0]),'device':os.makedev(major,minor),'filesystem_root':decode(fields[3]),
                         'root':decode(fields[4]),'readonly':'ro' in fields[5].split(',') or 'ro' in tail[2].split(','),
                         'filesystem':tail[0]})
            if len(rows)>MAX_MOUNTS:raise ValueError()
    except (IndexError,ValueError,OverflowError):
        raise StorageError('The mounted-drive list could not be verified.') from None
    return rows


def mount_text(value):
    raw=bytes(value)
    if not raw or len(raw)>4096 or raw[-1]!=0 or b'\0' in raw[:-1]:raise ValueError('Invalid mount path')
    return raw[:-1].decode('utf-8')


@contextmanager
def opened_root(root):
    path=Path(root)
    if not path.is_absolute() or '..' in path.parts or str(path)!=root:raise StorageError('Choose a mounted filesystem root.')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            os.close(fd);fd=child
        yield fd
    finally:os.close(fd)


def inspect_root(root,device):
    with opened_root(root) as fd:
        info=os.fstat(fd);space=os.fstatvfs(fd)
        if info.st_dev!=device:raise StorageError('The mounted drive changed. Refresh and select it again.')
        private=info.st_uid==os.getuid() and not info.st_mode&0o022 and os.access(root,os.W_OK|os.X_OK)
        # Registration for existing files does not confer managed-write or
        # uninstall authority. Root-owned system filesystems may contain a
        # writable user game folder; check that actual folder separately.
        return {'free':max(0,space.f_bavail)*space.f_frsize,'total':space.f_blocks*space.f_frsize,
                'readonly':bool(space.f_flag&os.ST_RDONLY),'inode':info.st_ino,
                'managed_reason':'' if private else 'This drive root is not private and writable for managed cache or archive installation.'}


class LinuxVolumes:
    def __init__(self,objects=read_objects,mounts=read_mounts,inspect=inspect_root,boot=None,namespace=None,topology=None):
        self.objects=objects;self.mounts=mounts;self.inspect=inspect
        self.boot=boot;self.namespace=namespace;self.topology=topology or InternalPartitions().registration

    def __call__(self):
        before=self.mounts();mounts=mount_rows(before);objects=self.objects()
        if not isinstance(objects,dict) or len(objects)>2048:raise StorageError('Drive discovery returned an invalid inventory.')
        boot=self.boot or Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        try:UUID(boot)
        except (ValueError,TypeError):raise StorageError('The current boot identity is unavailable.') from None
        namespace=self.namespace if self.namespace is not None else Path('/proc/self/ns/mnt').stat().st_ino
        volumes=[]
        for interfaces in objects.values():
            if not isinstance(interfaces,dict) or BLOCK not in interfaces or FILESYSTEM not in interfaces:continue
            block=interfaces[BLOCK];filesystem=interfaces[FILESYSTEM]
            if block.get('HintIgnore'):continue
            device=block.get('DeviceNumber');block_id=block.get('Id');uuid=block.get('IdUUID')
            if type(device) is not int or device<0:continue
            roots=filesystem.get('MountPoints',[])
            if not isinstance(roots,(list,tuple)) or len(roots)>MAX_MOUNTS:raise StorageError('Invalid drive mount locations.')
            if not roots:continue
            if not all(isinstance(v,str) and v and len(v)<=4096 for v in (block_id,uuid)):
                # No unstable path/device-name fallback for persistent identity.
                continue
            stable='udisks:'+sha256(json.dumps([block_id,uuid],ensure_ascii=True).encode()).hexdigest()
            matching=[m for m in mounts if m['device']==device]
            for raw in roots:
                try:root=mount_text(raw)
                except (ValueError,TypeError,UnicodeError):continue
                candidates=[m for m in matching if m['root']==root]
                if len(candidates)!=1:continue
                mount=candidates[0]
                label=block.get('IdLabel') or block.get('HintName') or 'Local drive'
                label=' '.join(str(label).split())[:200] or 'Local drive'
                reason='This filesystem has multiple mounted locations. Choose a uniquely mounted drive.' if len(matching)!=1 or len(roots)!=1 else ''
                if mount['filesystem_root']!='/':reason='Subvolume or partial mounts are not supported for drive registration yet.'
                evidence=self.topology(interfaces,objects)
                topology_reason,managed_topology=evidence if isinstance(evidence,tuple) else (evidence,'')
                reason=reason or topology_reason
                try:info=self.inspect(root,device)
                except (OSError,StorageError):
                    # An inaccessible or concurrently unmounted root must not
                    # become a writable path on its parent filesystem.
                    continue
                volumes.append(Volume(stable,f'{boot}:{namespace}:{mount["id"]}:{device}:{info["inode"]}',root,label,
                    info['free'],info['total'],bool(block.get('ReadOnly')) or mount['readonly'] or info['readonly'],
                    reason,True,' '.join(filter(None,(managed_topology,info['managed_reason']))),device))
        if self.mounts()!=before:raise StorageError('Mounted drives changed during discovery. Refresh and try again.')
        return volumes
