import json

import tarfile
import shutil
import tempfile
import unittest
from pathlib import Path

from umutron.game_assets import BackupCancelled, backup_game, link_game, move_game_installation, regenerate_manifest, relink_installed_game, restore_game, set_game_launch_options, set_game_proton, unlink_game
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

    def test_move_game_installation_succeeds_when_game_manifest_already_exists_on_target_drive(self):
        from umutron.game_assets import regenerate_manifest
        external_drive = self.root / 'external_drive_source'
        external_drive.mkdir()
        ext_root = external_drive / 'CustomGames' / 'MyExtGame2'
        ext_root.mkdir(parents=True)
        exe = ext_root / 'game.exe'
        exe.write_text('bin')
        managed_base = self.drive / 'UmuLibrary' / 'umuapps'
        prefix = managed_base / 'compatdata' / 'MyExtGame2'
        prefix.mkdir(parents=True)
        game = {
            'id': 'test-uuid-move-same-drive',
            'title': 'MyExtGame2',
            'metadata_app_id': 54321,
            'executable': str(exe),
            'working_dir': str(ext_root),
            'launch': {'prefix': str(prefix), 'proton': str(self.proton)},
            'installation': {'root': str(ext_root), 'prefix': str(prefix)},
        }
        updated = regenerate_manifest(game)
        self.assertTrue(Path(updated['installation']['manifest']).is_file())
        moved = move_game_installation(updated, drive_root=self.drive)
        self.assertEqual(moved['root'], str(managed_base / 'common' / 'MyExtGame2'))
        self.assertTrue(Path(moved['executable']).is_file())
        self.assertTrue(Path(moved['manifest']).is_file())
        self.assertFalse(ext_root.exists())

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

    def test_regenerate_manifest_external_game(self):
        from umutron.game_assets import regenerate_manifest
        external_drive = self.root / 'external_drive'
        external_drive.mkdir()
        external_game_root = external_drive / 'CustomGames' / 'MyExtGame'
        external_game_root.mkdir(parents=True)
        exe = external_game_root / 'game.exe'
        exe.write_text('bin')
        managed_base = self.drive / 'UmuLibrary' / 'umuapps'
        prefix = managed_base / 'compatdata' / 'MyExtGame'
        prefix.mkdir(parents=True)
        game = {
            'id': 'test-uuid-1234',
            'title': 'MyExtGame',
            'metadata_app_id': 12345,
            'executable': str(exe),
            'working_dir': str(external_game_root),
            'launch': {'prefix': str(prefix), 'proton': str(self.proton)},
            'installation': {'root': str(external_game_root), 'prefix': str(prefix)},
        }
        updated = regenerate_manifest(game)
        manifest_path = Path(updated['installation']['manifest'])
        self.assertTrue(manifest_path.is_file())
        self.assertEqual(manifest_path.name, 'appmanifest_12345.json')
        self.assertEqual(manifest_path.parent, managed_base)


    def test_relink_external_game_updates_root_launcher_and_manifest_without_moving_files(self):
        old_root = self.root / 'old-game'
        old_root.mkdir()
        old_launcher = old_root / 'old.exe'
        old_launcher.write_text('old')
        new_root = self.root / 'new-game'
        (new_root / 'bin').mkdir(parents=True)
        new_launcher = new_root / 'bin' / 'correct.exe'
        new_launcher.write_text('new')
        prefix = self.drive / 'UmuLibrary' / 'umuapps' / 'compatdata' / 'External Game'
        prefix.mkdir(parents=True)
        game = {
            'id': 'test-uuid-relink', 'title': 'External Game', 'metadata_app_id': 77778,
            'executable': str(old_launcher), 'working_dir': str(old_root),
            'launch': {'prefix': str(prefix), 'proton': str(self.proton)},
            'installation': {'mode': 'installed', 'root': str(old_root), 'prefix': str(prefix)},
        }
        linked = regenerate_manifest(game)
        updated = relink_installed_game(linked, root=new_root, launcher=new_launcher, games=[linked])
        self.assertEqual(updated['installation']['root'], str(new_root.resolve()))
        self.assertEqual(updated['executable'], str(new_launcher.resolve()))
        self.assertEqual(updated['working_dir'], str(new_launcher.parent.resolve()))
        self.assertTrue(old_launcher.is_file())
        self.assertTrue(new_launcher.is_file())
        manifest = json.loads(Path(updated['installation']['manifest']).read_text())
        self.assertEqual(manifest['launcher_relative_path'], 'bin/correct.exe')

    def test_relink_managed_game_to_external_folder_keeps_former_folder_and_detaches_record(self):
        linked = self._linked_game()
        former_root = Path(linked['installation']['root'])
        new_root = self.root / 'correct-external-game'
        new_root.mkdir()
        new_launcher = new_root / 'correct.exe'
        new_launcher.write_text('new')
        updated = relink_installed_game(linked, root=new_root, launcher=new_launcher, games=[linked])
        self.assertEqual(updated['installation']['mode'], 'installed')
        self.assertNotIn('link_mode', updated['installation'])
        self.assertEqual(updated['installation']['root'], str(new_root.resolve()))
        self.assertTrue(former_root.is_dir())
        manifest = json.loads(Path(updated['installation']['manifest']).read_text())
        self.assertEqual(manifest['launcher_relative_path'], 'correct.exe')

    def test_relink_external_game_rejects_another_library_game_folder(self):
        root = self.root / 'first-game'
        root.mkdir()
        launcher = root / 'first.exe'
        launcher.write_text('first')
        other_root = self.root / 'other-game'
        other_root.mkdir()
        other_launcher = other_root / 'other.exe'
        other_launcher.write_text('other')
        game = {
            'id': 'test-uuid-relink-first', 'title': 'First Game', 'metadata_app_id': None,
            'executable': str(launcher), 'working_dir': str(root),
            'launch': {'prefix': str(self.root / 'prefix'), 'proton': str(self.proton)},
            'installation': {'mode': 'installed', 'root': str(root), 'prefix': str(self.root / 'prefix')},
        }
        other = {**game, 'id': 'test-uuid-relink-second', 'executable': str(other_launcher),
                 'working_dir': str(other_root), 'installation': {'mode': 'installed', 'root': str(other_root)}}
        with self.assertRaisesRegex(ValueError, 'Another library game'):
            relink_installed_game(game, root=other_root, launcher=other_launcher, games=[game, other])

    def test_external_game_proton_selection_updates_manifest_and_survives_regeneration(self):
        cachyos = self.root / 'proton-cachyos'
        cachyos.mkdir()
        (cachyos / 'proton').write_text('#!/bin/sh\n')
        external_drive = self.root / 'external-proton-drive'
        external_root = external_drive / 'Games' / 'External Game'
        external_root.mkdir(parents=True)
        executable = external_root / 'game.exe'
        executable.write_text('bin')
        base = self.drive / 'UmuLibrary' / 'umuapps'
        prefix = base / 'compatdata' / 'External Game'
        prefix.mkdir(parents=True)
        game = {
            'id': 'test-uuid-external-proton', 'title': 'External Game', 'metadata_app_id': 77777,
            'executable': str(executable), 'working_dir': str(external_root),
            'launch': {'prefix': str(prefix), 'proton': str(self.proton)},
            'installation': {'mode': 'installed', 'root': str(external_root), 'prefix': str(prefix)},
        }
        generated = regenerate_manifest(game)
        updated = {**generated, 'launch': {**generated['launch'], 'proton': str(cachyos)},
                   'installation': {**generated['installation'], 'proton': str(cachyos)}}
        self.assertEqual(set_game_proton(updated, cachyos), str(cachyos.resolve()))
        manifest = Path(updated['installation']['manifest'])
        self.assertEqual(json.loads(manifest.read_text())['proton'], str(cachyos.resolve()))
        regenerated = regenerate_manifest(updated)
        self.assertEqual(regenerated['installation']['proton'], str(cachyos))
        self.assertEqual(json.loads(manifest.read_text())['proton'], str(cachyos))
        updated['launch']['proton'] = 'UMU-Latest'
        updated['installation']['proton'] = 'UMU-Latest'
        self.assertEqual(set_game_proton(updated, 'UMU-Latest'), 'UMU-Latest')
        self.assertEqual(json.loads(manifest.read_text())['proton'], 'UMU-Latest')

    def test_unlink_external_game_removes_manifest(self):
        from umutron.game_assets import regenerate_manifest
        external_drive = self.root / 'external_drive_unlink'
        external_drive.mkdir()
        ext_root = external_drive / 'CustomGames' / 'MyExtUnlink'
        ext_root.mkdir(parents=True)
        exe = ext_root / 'game.exe'
        exe.write_text('bin')
        managed_base = self.drive / 'UmuLibrary' / 'umuapps'
        prefix = managed_base / 'compatdata' / 'MyExtUnlink'
        prefix.mkdir(parents=True)
        game = {
            'id': 'test-uuid-unlink-external',
            'title': 'MyExtUnlink',
            'metadata_app_id': 99999,
            'executable': str(exe),
            'working_dir': str(ext_root),
            'launch': {'prefix': str(prefix), 'proton': str(self.proton)},
            'installation': {'root': str(ext_root), 'prefix': str(prefix)},
        }
        updated = regenerate_manifest(game)
        manifest = Path(updated['installation']['manifest'])
        self.assertTrue(manifest.is_file())
        unlink_game(updated)
        self.assertFalse(manifest.exists())

if __name__ == '__main__':
    unittest.main()
