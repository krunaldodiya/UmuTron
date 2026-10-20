import tarfile
import shutil
import tempfile
import unittest
from pathlib import Path

from umutron.game_assets import BackupCancelled, backup_game, link_game, move_game_installation, restore_game, set_game_launch_options, unlink_game
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

    def test_unlink_keeps_prefix_and_allows_a_fresh_add(self):
        linked_game = self._linked_game()
        linked_root = Path(linked_game['installation']['root'])
        linked_prefix = Path(linked_game['installation']['prefix'])
        linked_manifest = Path(linked_game['installation']['manifest'])
        shutil.rmtree(linked_root)
        unlink_game(linked_game)
        self.assertTrue(linked_prefix.is_dir())
        self.assertFalse(linked_manifest.exists())
        fresh = link_game(self.game, drive_root=self.drive, source_root=self.source,
                          launcher=self.launcher, proton=self.proton, move=False)
        self.assertTrue(Path(fresh['executable']).is_file())

    def test_backup_directory_has_manifest_and_content_archive_then_restores(self):
        linked_game = self._linked_game()
        backup_parent = self.root / 'backups'
        backup_parent.mkdir()
        backup = backup_game(linked_game, backup_parent)
        self.assertEqual(backup, backup_parent / 'Fixture Game')
        self.assertTrue((backup / 'appmanifest_292030.json').is_file())
        self.assertTrue((backup / 'content.tar').is_file())
        with tarfile.open(backup / 'content.tar', 'r:') as archive:
            self.assertIn('common/Fixture Game/bin/Fixture.exe', archive.getnames())
        restored_drive = self.root / 'restored-drive'
        restored_drive.mkdir()
        restored = restore_game(self.game, archive=backup, drive_root=restored_drive)
        self.assertTrue(Path(restored['prefix']).is_dir())


    def test_backup_cancellation_discards_staged_archive(self):
        linked_game = self._linked_game()
        backup_parent = self.root / 'backups'
        backup_parent.mkdir()
        with self.assertRaises(BackupCancelled):
            backup_game(linked_game, backup_parent, cancelled=lambda: True)
        self.assertEqual(list(backup_parent.iterdir()), [])

    def test_backup_and_restore_keep_launch_options(self):
        linked_game = self._linked_game()
        linked_game['launch']['arguments'] = ['--nolauncher', '--mod-path', '/mods with spaces']
        set_game_launch_options(linked_game, linked_game['launch']['arguments'])
        backup_parent = self.root / 'backups'
        backup_parent.mkdir()
        backup = backup_game(linked_game, backup_parent)
        restored_drive = self.root / 'restored-drive'
        restored_drive.mkdir()
        restored = restore_game(self.game, archive=backup, drive_root=restored_drive)
        self.assertEqual(restored['arguments'], linked_game['launch']['arguments'])

    def test_restore_rejects_backup_without_manifest(self):
        linked_game = self._linked_game()
        backup_parent = self.root / 'backups'
        backup_parent.mkdir()
        backup = backup_game(linked_game, backup_parent)
        (backup / 'appmanifest_292030.json').unlink()
        restored_drive = self.root / 'restored-drive'
        restored_drive.mkdir()
        with self.assertRaisesRegex(ValueError, 'no valid game manifest'):
            restore_game(self.game, archive=backup, drive_root=restored_drive)

    def test_backup_and_restore_external_installed_game_uses_managed_drive(self):
        external_game = {
            **self.game,
            'executable': str(self.launcher),
            'working_dir': str(self.launcher.parent),
            'launch': {'proton': str(self.proton), 'prefix': str(self.root / 'external_prefix')},
            'installation': {'mode': 'installed', 'root': str(self.source), 'confirmed': True},
        }
        backup_parent = self.root / 'backups'
        backup_parent.mkdir()
        backup = backup_game(external_game, backup_parent)
        self.assertTrue((backup / 'appmanifest_292030.json').is_file())
        self.assertTrue((backup / 'content.tar').is_file())
        restored_drive = self.root / 'internal-managed-drive'
        restored_drive.mkdir()
        restored = restore_game(external_game, archive=backup, drive_root=restored_drive)
        self.assertEqual(restored['root'], str(restored_drive / 'UmuLibrary' / 'umuapps' / 'common' / 'Fixture Game'))
        self.assertTrue(Path(restored['executable']).is_file())
        self.assertTrue(Path(restored['manifest']).is_file())
        self.assertNotEqual(Path(restored['root']), self.source)

    def test_move_game_installation_moves_files_and_updates_manifest(self):
        linked_game = self._linked_game()
        destination_drive = self.root / 'second-managed-drive'
        destination_drive.mkdir()
        moved = move_game_installation(linked_game, drive_root=destination_drive)
        self.assertEqual(moved['root'], str(destination_drive / 'UmuLibrary' / 'umuapps' / 'common' / 'Fixture Game'))
        self.assertTrue(Path(moved['executable']).is_file())
        self.assertTrue(Path(moved['manifest']).is_file())
        self.assertFalse(Path(linked_game['installation']['root']).exists())
        self.assertFalse(Path(linked_game['installation']['manifest']).exists())

    def test_restore_game_succeeds_when_prefix_and_manifest_already_exist(self):
        linked_game = self._linked_game()
        backup_parent = self.root / 'backups'
        backup_parent.mkdir()
        backup = backup_game(linked_game, backup_parent)
        shutil.rmtree(Path(linked_game['installation']['root']))
        self.assertFalse(Path(linked_game['installation']['root']).exists())
        self.assertTrue(Path(linked_game['installation']['prefix']).is_dir())
        self.assertTrue(Path(linked_game['installation']['manifest']).is_file())
        restored = restore_game(self.game, archive=backup, drive_root=self.drive)
        self.assertTrue(Path(restored['root']).is_dir())
        self.assertTrue(Path(restored['executable']).is_file())

    def test_unlink_game_keeps_actual_game_folder_on_disk(self):
        linked_game = self._linked_game()
        unlink_game(linked_game)
        self.assertTrue(Path(linked_game['installation']['root']).is_dir())
        self.assertTrue(Path(linked_game['executable']).is_file())
        self.assertFalse(Path(linked_game['installation']['manifest']).exists())

if __name__ == '__main__':
    unittest.main()
