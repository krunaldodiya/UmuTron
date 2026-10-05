import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from game_library.library import Library


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lib = Library(self.root / 'data')

    def test_metadata_only_entry_is_valid_and_can_configure_later(self):
        game=self.lib.new_game()
        game.update(title='Catalogue game',description='Fetched description',metadata_source={'provider':'steam','id':620})
        self.lib.save(game)
        saved=Library(self.root/'data').games()[0]
        self.assertEqual(saved['executable'],'')
        self.assertEqual(saved['launch'],{})
        self.assertEqual(saved['installation'],{})
        saved.update(executable='/games/launcher.lnk',working_dir='/games',installation={'mode':'shortcut'})
        self.lib.save(saved)
        self.assertEqual(self.lib.games()[0]['metadata_source'],game['metadata_source'])
        self.assertEqual(self.lib.games()[0]['id'],game['id'])
        archive=self.root/'backup.zip';self.lib.export_zip(archive)
        self.lib.import_zip(archive,'replace')
        self.assertEqual(self.lib.games()[0]['installation']['mode'],'shortcut')

    def test_default_display_mode_persists_and_backup_retains_it(self):
        before=self.lib.games()
        self.lib.set_default_display_mode('fullscreen')
        self.assertEqual(Library(self.root/'data').data['settings']['default_display_mode'],'fullscreen')
        self.assertEqual(self.lib.games(),before)
        archive=self.root/'mode.zip';self.lib.export_zip(archive)
        self.lib.set_default_display_mode('desktop');self.lib.import_zip(archive,'replace')
        self.assertEqual(self.lib.data['settings']['default_display_mode'],'fullscreen')
        with self.assertRaises(ValueError):self.lib.set_default_display_mode('unexpected')

    def test_save_reload_and_relink_preserve_identity(self):
        game = self.lib.new_game()
        game.update(title='A game', executable='/games/a.exe', metadata_app_id=620)
        self.lib.save(game)
        loaded = Library(self.root / 'data').games()[0]
        loaded['executable'] = '/other/a.exe'
        self.lib.save(loaded)
        self.assertEqual(self.lib.games()[0]['id'], game['id'])
        self.assertEqual(self.lib.status(loaded), 'Not synced')

    def test_sync_status_changes_only_after_explicit_record(self):
        game = self.lib.new_game(); game['title'] = 'Game'
        self.lib.save(game)
        self.lib.mark_synced(game['id'], '/fixture', 123)
        saved = self.lib.games()[0]
        self.assertEqual(self.lib.status(saved), 'Synced')
        saved['title'] = 'New title'; self.lib.save(saved)
        self.assertEqual(self.lib.status(self.lib.games()[0]), 'Changes pending')

    def test_zip_restore_retains_metadata_but_clears_machine_mapping(self):
        game = self.lib.new_game(); game['title'] = 'Game'; self.lib.save(game)
        self.lib.mark_synced(game['id'], '/fixture', 123)
        archive = self.root/'backup.zip'; self.lib.export_zip(archive)
        other = Library(self.root/'restored')
        preview = other.preview_import(archive)
        self.assertEqual(preview['new'], 1)
        other.import_zip(archive, 'keep')
        restored = other.games()[0]
        self.assertEqual(restored['title'], 'Game')
        self.assertEqual(other.status(restored), 'Not synced')
        self.assertIsNone(restored['sync'])

    def test_zip_path_traversal_rejected(self):
        archive = self.root/'bad.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('../escape', 'bad')
            z.writestr('library.json', json.dumps({'version':1,'games':[],'settings':{}}))
        with self.assertRaises(ValueError): self.lib.preview_import(archive)
        self.assertFalse((self.root/'escape').exists())

    def test_import_keep_or_replace_is_explicit(self):
        game = self.lib.new_game(); game['title'] = 'Original'; self.lib.save(game)
        archive = self.root/'backup.zip'; self.lib.export_zip(archive)
        game['title'] = 'Edited'; self.lib.save(game)
        self.assertEqual(self.lib.preview_import(archive)['conflicts'], 1)
        self.lib.import_zip(archive, 'keep')
        self.assertEqual(self.lib.games()[0]['title'], 'Edited')
        self.lib.import_zip(archive, 'replace')
        self.assertEqual(self.lib.games()[0]['title'], 'Original')

    def test_provider_credentials_excluded_from_export(self):
        from game_library.providers import Credentials
        credentials=Credentials(self.lib.root/'private')
        credentials.save({'steamgriddb_key':'test-secret-must-not-export'})
        archive=self.root/'backup.zip'; self.lib.export_zip(archive)
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(z.namelist(),['library.json'])
            self.assertNotIn(b'test-secret-must-not-export',z.read('library.json'))

    def test_zip_restores_appearance(self):
        self.lib.set_theme('light')
        archive=self.root/'backup.zip'; self.lib.export_zip(archive)
        other=Library(self.root/'restored'); other.import_zip(archive)
        self.assertEqual(other.data['settings']['theme'],'light')

    def test_image_backup_round_trip_and_corruption_rejected(self):
        import base64
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN1kAAAAASUVORK5CYII=')
        name=self.lib.add_image(png)
        game=self.lib.new_game(); game['title']='Art'; game['artwork']={'portrait':name}; self.lib.save(game)
        archive=self.root/'backup.zip'; self.lib.export_zip(archive)
        other=Library(self.root/'restored'); other.import_zip(archive)
        self.assertEqual((other.art_dir/name).read_bytes(),png)
        bad=self.root/'bad.zip'
        with zipfile.ZipFile(archive) as src,zipfile.ZipFile(bad,'w') as dst:
            for info in src.infolist():
                content=src.read(info)
                dst.writestr(info,content+b'corruption' if info.filename.startswith('artwork/') else content)
        with self.assertRaisesRegex(ValueError,'checksum'): other.preview_import(bad)

    def test_delete_removes_only_local_entry_not_game_files(self):
        executable=self.root/'game.exe'; executable.write_bytes(b'inert fixture')
        game=self.lib.new_game(); game.update(title='Delete me',executable=str(executable)); self.lib.save(game)
        self.lib.delete(game['id'])
        self.assertEqual(self.lib.games(),[])
        self.assertEqual(executable.read_bytes(),b'inert fixture')

    def test_first_run_copies_legacy_and_preserves_original_and_defaults(self):
        legacy=Library(self.root/'steam-library-metadata-manager')
        game=legacy.new_game();game.update(title='Legacy',executable='/inert/old.exe')
        legacy.save(game);legacy.set_default_proton('GE-Latest')
        original=legacy.path.read_bytes()
        with patch.dict('os.environ',{'XDG_DATA_HOME':str(self.root)}):
            current=Library()
        self.assertEqual(current.games()[0]['id'],game['id'])
        self.assertEqual(legacy.path.read_bytes(),original)
        current.set_default_proton('UMU-Latest')
        archive=self.root/'defaults.zip';current.export_zip(archive)
        restored=Library(self.root/'restored-defaults');restored.import_zip(archive)
        self.assertEqual(restored.data['settings']['default_proton'],'UMU-Latest')

    def test_uninstaller_field_is_preserved_and_defaults_empty(self):
        game = self.lib.new_game()
        self.assertEqual(game.get('uninstaller'), '')
        game.update(title='Test Game', uninstaller='/games/unins000.exe')
        self.lib.save(game)
        reloaded = Library(self.root/'data').games()[0]
        self.assertEqual(reloaded['uninstaller'], '/games/unins000.exe')


class DescriptionExcerptTests(unittest.TestCase):
    def test_bounded_display_preserves_short_and_long_sources(self):
        from game_library.library import description_excerpt
        self.assertEqual(description_excerpt('Short description.'),'Short description.')
        original='Long description. '*200
        excerpt=description_excerpt(original)
        self.assertLessEqual(len(excerpt),300)
        self.assertTrue(excerpt.endswith('...'))
        self.assertEqual(original,'Long description. '*200)
        self.assertEqual(description_excerpt('a\n b'),'a b')
