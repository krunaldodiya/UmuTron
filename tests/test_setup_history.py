from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from game_library.library import Library, validate_game
from game_library.setup_history import groups

class SetupHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.lib=Library(self.root/'library')
        self.exe=self.root/'game.exe';self.exe.write_text('inert fixture')
        self.game=self.lib.new_game();self.game['title']='A game';self.lib.save(self.game)
    def ready(self,at=100):
        game=deepcopy(self.game);game['executable']=str(self.exe)
        with patch('game_library.setup_history.time.time',return_value=at):return self.lib.save_setup(game)
    def test_metadata_add_and_cancelled_drafts_do_not_create_history(self):
        self.assertEqual(groups(self.lib),([],[]))
        draft=deepcopy(self.game);draft['executable']=str(self.exe)
        self.assertEqual(groups(Library(self.lib.root)),([],[]))
    def test_successful_setup_persists_and_noop_or_metadata_edit_keeps_timestamp(self):
        saved=self.ready();self.assertEqual(saved['setup_completed_at'],100)
        with patch('game_library.setup_history.time.time',return_value=200):
            same=self.lib.save_setup(saved);self.assertEqual(same['setup_completed_at'],100)
        saved['title']='Edited';self.lib.save(saved)
        self.assertEqual(Library(self.lib.root).games()[0]['setup_completed_at'],100)
    def test_setup_changes_stamp_but_launch_preferences_do_not(self):
        saved=self.ready();saved['launch']={'proton':'GE-Latest'}
        with patch('game_library.setup_history.time.time',return_value=200):
            self.assertEqual(self.lib.save_setup(saved)['setup_completed_at'],100)
        other=self.root/'other.exe';other.write_text('inert')
        saved['executable']=str(other)
        with patch('game_library.setup_history.time.time',return_value=300):
            self.assertEqual(self.lib.save_setup(saved)['setup_completed_at'],300)
    def test_missing_path_and_unconfirmed_installer_do_not_stamp(self):
        game=deepcopy(self.game);game['executable']=str(self.root/'missing.exe')
        self.assertNotIn('setup_completed_at',self.lib.save_setup(game))
        game['executable']=str(self.exe);game['installation']={'mode':'installer','session_id':str(uuid4()),'confirmed':False}
        self.assertNotIn('setup_completed_at',self.lib.save_setup(game))
        game['installation']['confirmed']=True
        with patch('game_library.setup_history.time.time',return_value=400):
            self.assertEqual(self.lib.save_setup(game)['setup_completed_at'],400)
    def test_legacy_noop_never_invents_date_and_groups_are_deterministic(self):
        legacy=deepcopy(self.game);legacy['executable']=str(self.exe);self.lib.save(legacy)
        self.assertNotIn('setup_completed_at',self.lib.save_setup(legacy))
        for title,at in [('Z',300),('B',200),('A',300)]:
            game=self.lib.new_game();game.update(title=title,executable=str(self.exe))
            with patch('game_library.setup_history.time.time',return_value=at):self.lib.save_setup(game)
        known,unknown=groups(self.lib)
        self.assertEqual([g['title'] for g in known],['A','Z','B'])
        self.assertEqual([g['id'] for g in unknown],[legacy['id']])
        self.exe.unlink();self.assertEqual([g['id'] for g in groups(self.lib)[0]],[g['id'] for g in known])
    def test_failed_persistence_does_not_mutate_original_or_library(self):
        game=deepcopy(self.game);game['executable']=str(self.exe);before=self.lib.path.read_bytes()
        with patch.object(self.lib,'_write',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):self.lib.save_setup(game)
        self.assertNotIn('setup_completed_at',game);self.assertEqual(self.lib.path.read_bytes(),before)
        self.assertEqual(groups(self.lib),([],[]))
    def test_backup_roundtrip_preserves_actual_timestamp(self):
        self.ready();archive=self.root/'backup.zip';self.lib.export_zip(archive)
        restored=Library(self.root/'restored');restored.import_zip(archive)
        self.assertEqual(restored.games()[0]['setup_completed_at'],100)
    def test_timestamp_validation_rejects_invalid_values(self):
        for value in (True,0,-1,1.5,'100',None,253402300800):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_game({**self.game,'setup_completed_at':value})
