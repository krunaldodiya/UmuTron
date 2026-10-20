import tarfile
import tempfile
import unittest
from pathlib import Path

from umutron.game_assets import backup_game, link_game, restore_game
from umutron.library import Library


class ManagedGameAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.library = Library(self.root / 'state')
        self.game = self.library.new_game()
        self.game.update(title='Fixture Game', metadata_app_id=292030)
        self.source = self.root / 'outside' / 'Fixture Game'
        (self.source / 'bin').mkdir(parents=True)
        self.launcher = self.source / 'bin' / 'Fixture.exe'
        self.launcher.write_bytes(b'MZ fixture')
        self.proton = self.root / 'GE-Proton'
        self.proton.mkdir()
        (self.proton / 'proton').write_text('#!/bin/sh\n')
        self.drive = self.root / 'drive'
        self.drive.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def _linked_game(self):
        linked = link_game(self.game, drive_root=self.drive, source_root=self.source,
                           launcher=self.launcher, proton=self.proton, move=False)
        return {**self.game, 'executable': linked['executable'], 'working_dir': linked['working_dir'],
                'launch': {'prefix': linked['prefix'], 'proton': linked['proton']},
                'installation': {'mode': 'linked', 'root': linked['root'], 'prefix': linked['prefix'],
                                 'proton': linked['proton'], 'manifest': linked['manifest'],
                                 'link_mode': linked['mode'], 'confirmed': True}}

    def test_copy_link_creates_common_compatdata_and_json_manifest(self):
        linked = self._linked_game()
        base = self.drive / 'UmuLibrary' / 'umuapps'
        self.assertTrue(self.launcher.is_file())
        self.assertTrue(Path(linked['executable']).is_file())
        self.assertTrue(Path(linked['installation']['prefix']).is_dir())
        manifest = Path(linked['installation']['manifest'])
        self.assertEqual(manifest.name, 'appmanifest_292030.json')
        self.assertIn('"launcher_relative_path": "bin/Fixture.exe"', manifest.read_text())
        self.assertTrue((base / 'common' / 'Fixture Game').is_dir())

    def test_move_link_removes_original_after_confirmed_operation(self):
        linked = link_game(self.game, drive_root=self.drive, source_root=self.source,
                           launcher=self.launcher, proton=self.proton, move=True)
        self.assertFalse(self.source.exists())
        self.assertTrue(Path(linked['executable']).is_file())

    def test_backup_has_manifest_and_content_archive_then_restores(self):
        linked_game = self._linked_game()
        backup = self.root / 'Fixture Game.tar.gz'
        backup_game(linked_game, backup)
        with tarfile.open(backup, 'r:*') as archive:
            names = archive.getnames()
        self.assertIn('Fixture Game/appmanifest_292030.json', names)
        self.assertIn('Fixture Game/content.tar.gz', names)
        restored_drive = self.root / 'restored-drive'
        restored_drive.mkdir()
        restored = restore_game(self.game, archive=backup, drive_root=restored_drive)
        self.assertNotIn('Fixture Game/compatdata.tar.gz', names)
        self.assertTrue(Path(restored['prefix']).is_dir())


if __name__ == '__main__':
    unittest.main()
