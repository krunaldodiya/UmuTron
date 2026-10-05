"""Persisted registration tracks partitions, never a stale mount path."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

from game_library.storage import StorageError
from game_library.storage_access import PrivateStateStore,StorageAccess
from game_library.storage_observer import BLOCK,FILESYSTEM,LinuxVolumes

class PartitionReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.root.chmod(0o700)
        self.paths=['/run/media/fixture/Games','/mnt/Second'];self.present=[True,True]
        self.uuids=['fixture-filesystem-a','fixture-filesystem-b']
        self.observer=LinuxVolumes(self.objects,self.mounts,lambda *_:{'free':1000,'total':2000,'readonly':False,'inode':2,'managed_reason':''},'12345678-1234-5678-9012-123456789012',9,topology=lambda *_:'')
        self.service=StorageAccess(PrivateStateStore(self.root/'registry.sqlite3'),self.observer)

    def objects(self):
        return {f'/block/{i}':{BLOCK:{'Id':f'same-physical-disk-part{i+1}','IdUUID':self.uuids[i],'DeviceNumber':os.makedev(8,i+1),'IdLabel':f'Partition {i+1}'},FILESYSTEM:{'MountPoints':[(self.paths[i]+'\0').encode()]}} for i in range(2) if self.present[i]}

    def mounts(self):
        return ''.join(f'{20+i} 1 8:{i+1} / {self.paths[i]} rw - ext4 /dev/fixture{i} rw\n' for i in range(2) if self.present[i])

    def test_two_partitions_one_disk_register_once_each_and_follow_new_mount(self):
        volumes=self.observer();ids=[self.service.register(volume,'install') for volume in volumes]
        old=deepcopy(self.service.snapshot());self.paths[0]='/mnt/Games'
        reopened=StorageAccess(PrivateStateStore(self.root/'registry.sqlite3'),self.observer)
        current=reopened.snapshot()
        self.assertEqual([r['id'] for r in current['registrations']],ids)
        self.assertEqual(current['default_install'],ids[0]);self.assertEqual(current['registrations'][0]['root'],'/mnt/Games')
        self.assertEqual(current['registrations'][0]['volume_id'],old['registrations'][0]['volume_id'])
        with self.assertRaisesRegex(StorageError,'already registered'):reopened.register(self.observer()[0],'install')
        self.assertEqual(len(reopened.snapshot()['registrations']),2)

    def test_offline_does_not_follow_other_partition_mounted_at_old_path(self):
        identity=self.service.register(self.observer()[0],'install');self.present[0]=False;self.paths[1]=self.paths[0]
        row=self.service.snapshot()['registrations'][0]
        self.assertEqual(row['id'],identity);self.assertEqual(row['status'],'offline')
        self.assertIsNone(row['free']);self.assertIsNone(row['total'])
        self.assertEqual(self.service.snapshot()['default_install'],identity)
        self.present[0]=True;self.paths[0]='/mnt/Games'
        self.assertEqual(self.service.snapshot()['registrations'][0]['root'],'/mnt/Games')

    def test_reformatted_partition_is_a_new_identity_and_stale_selection_rejects(self):
        original=self.observer()[0];self.service.register(original,'install');self.uuids[0]='replacement-filesystem'
        self.assertEqual(self.service.snapshot()['registrations'][0]['status'],'offline')
        with self.assertRaises(StorageError):self.service.register(original,'install')
        replacement=self.observer()[0];self.assertNotEqual(replacement.volume_id,original.volume_id)
        self.service.register(replacement,'install');self.assertEqual(len(self.service.snapshot()['registrations']),2)
