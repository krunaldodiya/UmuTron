"""Accepted installer confirmation integrated with actual Setup chronology."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import test_setup_save as setup_fixtures
from game_library.app import Window
from game_library.library import Library
from game_library.setup_history import groups


class SetupSaveHistoryTests(unittest.TestCase):
    def setUp(self):
        self.f=setup_fixtures.SetupSaveTests();self.f.setUp();self.addCleanup(self.f.doCleanups)

    def test_successful_save_stamps_once_without_inventing_play_history(self):
        f=self.f
        with patch('game_library.setup_history.time.time',return_value=100):editor=f.save(f.draft())
        editor.error.assert_not_called();saved=Library(f.library.root).games()[0]
        self.assertEqual(saved['setup_completed_at'],100)
        self.assertEqual(saved['installer_attempt']['session_id'],saved['installation']['session_id'])
        self.assertEqual([g['id'] for g in groups(f.library)[0]],[saved['id']])
        with patch('game_library.setup_history.time.time',return_value=200):
            f.save(saved).error.assert_not_called()
            saved['launch']['proton']='GE-Latest';f.save(saved).error.assert_not_called()
        saved=f.library.games()[0];saved['title']='Metadata edit';f.library.save(saved)
        self.assertEqual(f.library.games()[0]['setup_completed_at'],100)
        self.assertFalse((f.library.root/'play-history').exists())
        f.launcher.start.assert_not_called()

    def test_explicit_confirmation_uses_same_chronology_and_noop_keeps_date(self):
        f=self.f
        with patch('game_library.setup_history.time.time',return_value=100):saved=f.service.confirm(f.draft())
        self.assertEqual(saved['setup_completed_at'],100)
        with patch('game_library.setup_history.time.time',return_value=200):saved=f.service.confirm(saved)
        self.assertEqual(saved['setup_completed_at'],100)
        self.assertEqual(Library(f.library.root).games()[0],saved)

    def test_cancel_invalid_and_unsuccessful_save_never_stamp(self):
        f=self.f;before=f.library.path.read_bytes();Window.cancel_editor(f.editor(f.draft()))
        self.assertEqual(f.library.path.read_bytes(),before)
        candidate=f.draft();candidate['executable']=str(f.installer)
        replacement=f.root/'next-installer.exe';replacement.write_text('Inert next installer')
        candidate['installation']['installer']=str(replacement)
        f.save(candidate).error.assert_called_once();self.assertEqual(f.library.path.read_bytes(),before)
        f.record.update(state='Stopped',code=0);f.write_record()
        f.save(f.draft()).error.assert_not_called();self.assertNotIn('setup_completed_at',f.library.games()[0])
        # Merely seeing Finished still does not stamp; explicit Save does.
        f.record.update(state='Finished',code=0);f.write_record()
        self.assertNotIn('setup_completed_at',Library(f.library.root).games()[0])
        with patch('game_library.setup_history.time.time',return_value=300):f.save(f.library.games()[0]).error.assert_not_called()
        self.assertEqual(f.library.games()[0]['setup_completed_at'],300)

    def test_previously_confirmed_hotfix_record_stays_undated_on_noop(self):
        f=self.f;saved=f.service.validated_executable(f.draft());f.library.save(saved)
        self.assertNotIn('setup_completed_at',saved)
        with patch('game_library.setup_history.time.time',return_value=400):f.save(saved).error.assert_not_called()
        known,legacy=groups(Library(f.library.root))
        self.assertEqual(known,[]);self.assertEqual([g['id'] for g in legacy],[saved['id']])
        self.assertNotIn('setup_completed_at',legacy[0])

    def test_failed_combined_save_keeps_date_binding_and_confirmation_unwritten(self):
        f=self.f;before=f.library.path.read_bytes();candidate=f.draft();original=deepcopy(candidate)
        with patch('game_library.setup_history.time.time',return_value=100),patch.object(f.library,'_write',side_effect=OSError('fixture write failure')):
            editor=f.save(candidate)
        editor.error.assert_called_once();self.assertIsNotNone(editor.editor)
        self.assertEqual(f.library.path.read_bytes(),before);self.assertEqual(candidate,original)
        self.assertNotIn('setup_completed_at',f.library.games()[0]);self.assertNotIn('installer_attempt',f.library.games()[0])

    def test_backup_preserves_completed_attempt_and_setup_date_together(self):
        f=self.f
        with patch('game_library.setup_history.time.time',return_value=100):f.save(f.draft()).error.assert_not_called()
        saved=f.library.games()[0];archive=f.root/'combined.zip';f.library.export_zip(archive)
        restored=Library(f.root/'restored');restored.import_zip(archive)
        self.assertEqual(restored.games()[0],saved)
        self.assertEqual(restored.games()[0]['setup_completed_at'],100)
        self.assertEqual(restored.games()[0]['installer_attempt']['executable'],str(f.installer.resolve()))


if __name__=='__main__':unittest.main()
