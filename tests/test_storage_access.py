"""Private registry durability only. Manual game flows never consult it."""
from pathlib import Path
import tempfile
import unittest

from game_library.storage import StorageError,Volume
from game_library.storage_access import PrivateStateStore,StorageAccess


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.path=self.root/'storage.sqlite3';self.volume=Volume('partition','boot:mount','/fixture/drive','Internal SSD',100,200)
        self.service=StorageAccess(PrivateStateStore(self.path),lambda:[self.volume])

    def test_private_registry_survives_reopen_and_remove_only_changes_metadata(self):
        game=self.root/'existing.exe';game.write_text('Preserve game')
        identity=self.service.register(self.volume,'install');self.assertEqual(self.path.stat().st_mode&0o777,0o600)
        reopened=StorageAccess(PrivateStateStore(self.path),lambda:[self.volume]);self.assertEqual(reopened.snapshot()['registrations'][0]['id'],identity)
        reopened.remove(identity);self.assertEqual(game.read_text(),'Preserve game')

    def test_symlink_hardlink_or_shared_registry_preserved(self):
        original=self.root/'original';original.write_text('preserve');original.chmod(0o600)
        for link in ('symlink','hardlink','shared'):
            if link=='symlink':self.path.symlink_to(original)
            elif link=='hardlink':self.path.hardlink_to(original)
            else:self.path.write_text('preserve');self.path.chmod(0o666)
            with self.subTest(link=link),self.assertRaises(StorageError):self.service.snapshot()
            self.assertEqual(original.read_text(),'preserve');self.path.unlink()

    def test_shared_parent_and_corrupt_database_never_reset(self):
        self.root.chmod(0o755)
        with self.assertRaises(StorageError):self.service.snapshot()
        self.assertFalse(self.path.exists());self.root.chmod(0o700)
        self.path.write_text('preserve damaged registry');self.path.chmod(0o600)
        with self.assertRaises(StorageError):self.service.snapshot()
        self.assertEqual(self.path.read_text(),'preserve damaged registry')

    def test_canceled_registration_and_unsafe_sidecar_do_not_commit(self):
        with self.assertRaises(StorageError):self.service.register(self.volume,'install',cancelled=lambda:True)
        self.assertFalse(self.service.snapshot()['registrations'])
        sidecar=Path(str(self.path)+'-wal');sidecar.write_text('preserve');sidecar.chmod(0o666)
        with self.assertRaises(StorageError):self.service.snapshot()
        self.assertEqual(sidecar.read_text(),'preserve')
