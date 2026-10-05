"""Synthetic UDisks/mount metadata only; never mount or inspect a real drive."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

from game_library.storage import StorageError, StorageModel, StateStore, SizePlan, Volume
from game_library.storage_observer import BLOCK, FILESYSTEM, LinuxVolumes, mount_rows
from game_library.storage_topology import LIMITED

BOOT='12345678-1234-5678-9012-123456789012'


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.mounts='41 1 8:2 / /fixture/drive rw,nosuid - ext4 /dev/fixture rw\n'
        self.objects={'/block':{BLOCK:{'Id':'physical-id-part2','IdUUID':'filesystem-uuid','DeviceNumber':os.makedev(8,2),'IdLabel':'Games'},
                                FILESYSTEM:{'MountPoints':[b'/fixture/drive\0']}}}
        self.info={'free':1000,'total':2000,'readonly':False,'inode':8,'managed_reason':''}
        self.observer=LinuxVolumes(lambda:deepcopy(self.objects),lambda:self.mounts,lambda *_:dict(self.info),BOOT,99,topology=lambda *_:'')

    def test_correlates_stable_device_and_current_mount_without_path_identity(self):
        original=self.observer()[0]
        self.assertEqual(original.root,'/fixture/drive');self.assertEqual(original.device,os.makedev(8,2))
        self.assertIn(BOOT,original.mount_id);self.assertIn(':99:41:',original.mount_id)
        self.mounts=self.mounts.replace('41 ','42 ',1).replace('/fixture/drive','/fixture/new')
        self.objects['/block'][FILESYSTEM]['MountPoints']=[b'/fixture/new\0']
        changed=self.observer()[0]
        self.assertEqual(changed.volume_id,original.volume_id);self.assertNotEqual(changed.stamp,original.stamp)
        self.objects['/block'][BLOCK]['IdUUID']='reformatted'
        self.assertNotEqual(self.observer()[0].volume_id,original.volume_id)

    def test_no_stable_identity_or_device_match_has_no_path_fallback(self):
        for key,value in (('Id',''),('IdUUID',''),('DeviceNumber',os.makedev(8,3))):
            with self.subTest(key=key):
                before=deepcopy(self.objects);self.objects['/block'][BLOCK][key]=value
                self.assertEqual(self.observer(),[]);self.objects=before

    def test_duplicate_identity_and_bind_mount_rejected(self):
        self.objects['/clone']=deepcopy(self.objects['/block'])
        values=self.observer()
        with self.assertRaisesRegex(StorageError,'ambiguous'):StorageModel.resolve(values[0].volume_id,values)
        self.objects.pop('/clone');self.mounts+='42 1 8:2 / /fixture/alias rw - ext4 /dev/fixture rw\n'
        self.assertIn('multiple',self.observer()[0].reason)

    def test_readonly_and_partial_mount(self):
        self.info['readonly']=True;self.assertIn('read-only',self.observer()[0].reason)
        self.info['readonly']=False;self.objects['/block'][BLOCK]['ReadOnly']=True
        self.assertIn('read-only',self.observer()[0].reason)
        self.objects['/block'][BLOCK]['ReadOnly']=False;self.mounts=self.mounts.replace('8:2 / ','8:2 /nested ')
        self.assertIn('partial',self.observer()[0].reason)

    def test_ntfs_manual_registration_is_not_managed_write_authority(self):
        self.mounts=self.mounts.replace('ext4','ntfs3');self.info['managed_reason']='Root permissions do not support managed writes.'
        volume=self.observer()[0];self.assertFalse(volume.reason)
        with self.assertRaisesRegex(StorageError,'managed writes'):StorageModel.resolve(volume.volume_id,[volume],managed=True)

    def test_mount_change_during_discovery_rejects_entire_snapshot(self):
        calls=iter([self.mounts,self.mounts.replace('41 ','42 ',1)])
        self.observer.mounts=lambda:next(calls)
        with self.assertRaisesRegex(StorageError,'changed during'):self.observer()

    def test_inaccessible_root_omitted_and_invalid_mount_text_rejected(self):
        self.observer.inspect=lambda *_:(_ for _ in ()).throw(OSError('offline'))
        self.assertEqual(self.observer(),[])
        with self.assertRaises(StorageError):mount_rows('malformed')
        self.assertEqual(mount_rows(self.mounts.replace('/fixture/drive','/fixture/My\\040Drive'))[0]['root'],'/fixture/My Drive')

    def test_limited_fuseblk_metadata_registration_cannot_admit_cache_or_archives(self):
        self.observer.topology=lambda *_:('',LIMITED)
        self.mounts=self.mounts.replace('ext4','fuseblk')
        volume=self.observer()[0]
        self.assertFalse(volume.reason);self.assertEqual(volume.managed_reason,LIMITED)
        with tempfile.TemporaryDirectory() as folder:
            cache=Volume('cache','cache-mount','/fixture/cache','Cache',1000,2000)
            model=StorageModel(StateStore(Path(folder)/'state.sqlite3'),lambda:[*self.observer(),cache])
            install=model.register(volume,'install')
            self.assertEqual(model.snapshot()['registrations'][0]['managed_reason'],LIMITED)
            with self.assertRaisesRegex(StorageError,'PCIe attachment'):model.add_role(install,'cache')
            model.register(cache,'cache')
            with self.assertRaisesRegex(StorageError,'PCIe attachment'):model.quote(install,SizePlan(10,10))
            with self.assertRaisesRegex(StorageError,'PCIe attachment'):model.reserve('12345678-1234-5678-9012-123456789012',1,install,SizePlan(10,10))
        self.info['managed_reason']='Root permissions do not support managed writes.'
        self.assertIn('Root permissions',self.observer()[0].managed_reason)
        self.assertIn('PCIe attachment',self.observer()[0].managed_reason)

    def test_limited_topology_cannot_override_mount_or_identity_rejections(self):
        self.observer.topology=lambda *_:('',LIMITED)
        self.info['readonly']=True;self.assertIn('read-only',self.observer()[0].reason)
        self.info['readonly']=False;self.mounts=self.mounts.replace('8:2 / ','8:2 /nested ')
        self.assertIn('partial',self.observer()[0].reason)


if __name__=='__main__':unittest.main()
