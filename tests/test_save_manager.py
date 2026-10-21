import tempfile
import unittest
from pathlib import Path
from umutron.save_manager import export_saves, find_game_save_folders, import_saves


class SaveManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.prefix = self.root / 'compatdata' / 'My Game'
        self.drive_c = self.prefix / 'drive_c'
        self.save_dir = self.drive_c / 'users' / 'steamuser' / 'Documents' / 'My Games' / 'My Game'
        self.save_dir.mkdir(parents=True)
        (self.save_dir / '1.sav').write_bytes(b'SAVEDATA1')
        (self.save_dir / 'profile.bin').write_bytes(b'PROFILE')
        self.game = {
            'title': 'My Game',
            'id': 'test-uuid',
            'launch': {'prefix': str(self.prefix)},
            'installation': {'mode': 'linked', 'prefix': str(self.prefix)},
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_find_game_save_folders(self):
        folders = find_game_save_folders(self.game)
        self.assertEqual(len(folders), 1)
        rel, path = folders[0]
        self.assertEqual(path, self.save_dir)

    def test_export_and_import_saves(self):
        zip_path = self.root / 'backups' / 'save.zip'
        count = export_saves(self.game, zip_path)
        self.assertEqual(count, 2)
        self.assertTrue(zip_path.is_file())

        # Wipe save directory to test restore
        (self.save_dir / '1.sav').unlink()
        (self.save_dir / 'profile.bin').unlink()
        self.assertFalse((self.save_dir / '1.sav').exists())

        restored_count = import_saves(self.game, zip_path)
        self.assertEqual(restored_count, 2)
        self.assertEqual((self.save_dir / '1.sav').read_bytes(), b'SAVEDATA1')
        self.assertEqual((self.save_dir / 'profile.bin').read_bytes(), b'PROFILE')


if __name__ == '__main__':
    unittest.main()
