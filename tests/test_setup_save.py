"""Explicit Save after an installer: inert files and journal, never execution."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from game_library.app import Window
from game_library.download_service import detail_actions
from game_library.installations import Installations
from game_library.library import Library
from game_library.setup_state import setup_state


class SetupSaveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.library=Library(self.root/'library')
        self.runner=self.root/'umu-run';self.runner.write_text('Inert fixture; never execute.');self.runner.chmod(0o700)
        self.proton=self.root/'proton-version';self.proton.mkdir();(self.proton/'proton').write_text('Inert')
        self.installer=self.root/'installers/setup.exe';self.installer.parent.mkdir();self.installer.write_text('Inert installer')
        self.exe=self.root/'game/game.exe';self.exe.parent.mkdir();self.exe.write_text('Inert playable file')
        self.game=self.library.new_game();self.game.update(title='Completed installer fixture',launch={'runner':str(self.runner)},installation={'mode':'installer','installer':str(self.installer),'prefix':str(self.root/'prefix'),'proton':str(self.proton),'session_id':str(uuid4()),'confirmed':False})
        self.library.save(self.game)
        self.record={'operation':'installer','game_id':self.game['id'],'session_id':self.game['installation']['session_id'],'state':'Finished','code':0,'proton':str(self.proton)}
        self.record_path=self.library.root/'installation-sessions'/(self.game['id']+'.json');self.record_path.parent.mkdir();self.write_record()
        self.launcher=Mock();self.launcher.active.return_value=False;self.launcher.current.return_value={};self.launcher.start.side_effect=AssertionError('Execution forbidden in this fixture')
        self.service=Installations(self.library,self.launcher)

    def write_record(self):self.record_path.write_text(json.dumps(self.record))

    def draft(self):return dict(deepcopy(self.game),executable=str(self.exe),working_dir=str(self.exe.parent))

    def editor(self,candidate):
        return SimpleNamespace(collect=lambda:deepcopy(candidate),original=deepcopy(self.game),editor_kind='manage',launcher=self.launcher,
                               installations=self.service,library=self.library,editor=Mock(),close_installer=Mock(),show_game=Mock(),
                               show_library=Mock(),notify=Mock(),error=Mock())

    def save(self,candidate):
        editor=self.editor(candidate);Window.save_editor(editor);return editor

    def test_save_confirms_completed_installer_and_survives_reopen(self):
        before=self.record_path.read_bytes();editor=self.save(self.draft())
        editor.error.assert_not_called();self.assertIsNone(editor.editor)
        saved=Library(self.library.root).games()[0]
        self.assertTrue(saved['installation']['confirmed']);self.assertTrue(setup_state(saved)['ready'])
        self.assertEqual(detail_actions(saved,True,False)['primary'],'Play')
        self.assertEqual(saved['launch']['prefix'],self.game['installation']['prefix']);self.assertEqual(saved['launch']['proton'],str(self.proton))
        self.assertEqual(self.record_path.read_bytes(),before);self.launcher.start.assert_not_called()
        # Opening Setup and resaving the same executable repairs the existing false flag too.
        saved['installation']['confirmed']=False;self.library.save(saved);self.game=deepcopy(saved)
        editor=self.save(saved);editor.error.assert_not_called()
        self.assertTrue(Library(self.library.root).games()[0]['installation']['confirmed'])

    def test_cancel_does_not_save_or_confirm_the_draft(self):
        before=self.library.path.read_bytes();editor=self.editor(self.draft());Window.cancel_editor(editor)
        self.assertEqual(self.library.path.read_bytes(),before);self.assertFalse(self.library.games()[0]['installation']['confirmed']);editor.error.assert_not_called()

    def test_active_operation_blocks_save_and_keeps_editor(self):
        self.launcher.active.return_value=True;before=self.library.path.read_bytes();editor=self.save(self.draft())
        editor.error.assert_called_once();self.assertIsNotNone(editor.editor);self.assertEqual(self.library.path.read_bytes(),before)

    def test_invalid_file_or_working_directory_never_confirms(self):
        cases=({'executable':str(self.root/'missing.exe')},{'executable':str(self.installer)},
               {'executable':'relative.exe'},{'working_dir':str(self.root/'missing-directory')})
        for changed in cases:
            with self.subTest(changed=changed):
                before=self.library.path.read_bytes();candidate=self.draft();candidate.update(changed);editor=self.save(candidate)
                editor.error.assert_called_once();self.assertIsNotNone(editor.editor);self.assertEqual(self.library.path.read_bytes(),before)

    def test_non_success_or_unmatched_session_stays_unconfirmed(self):
        cases=({'state':'Error','code':1},{'state':'Stopped','code':0},{'state':'Preparing','code':None},
               {'state':'Finished','code':7},{'state':'Finished','code':None},{'operation':'play'},
               {'session_id':str(uuid4())},{'game_id':str(uuid4())})
        original=deepcopy(self.record)
        for change in cases:
            with self.subTest(change=change):
                self.record={**original,**change};self.write_record();editor=self.save(self.draft());editor.error.assert_not_called()
                saved=Library(self.library.root).games()[0];self.assertFalse(saved['installation']['confirmed'])
                self.assertEqual(detail_actions(saved,True,False)['primary'],'Install')

    def test_missing_session_or_no_executable_is_only_a_draft(self):
        for missing in ('session','executable'):
            with self.subTest(missing=missing):
                candidate=self.draft()
                if missing=='session':candidate['installation'].pop('session_id')
                else:candidate['executable']=''
                editor=self.save(candidate);editor.error.assert_not_called()
                self.assertFalse(self.library.games()[0]['installation']['confirmed'])

    def test_failed_persistence_keeps_disk_memory_and_editor(self):
        before=self.library.path.read_bytes();memory=self.library.games();candidate=self.draft();original=deepcopy(candidate)
        with patch.object(self.library,'_write',side_effect=OSError('fixture write failure')):editor=self.save(candidate)
        editor.error.assert_called_once();self.assertIsNotNone(editor.editor)
        self.assertEqual(self.library.path.read_bytes(),before);self.assertEqual(self.library.games(),memory);self.assertEqual(candidate,original)

    def test_changed_confirmed_executable_requires_validation(self):
        confirmed=self.draft();confirmed['installation']['confirmed']=True;self.library.save(confirmed);self.game=deepcopy(confirmed)
        candidate=deepcopy(confirmed);candidate['executable']=str(self.root/'missing.exe')
        before=self.library.path.read_bytes();editor=self.save(candidate);editor.error.assert_called_once()
        self.assertEqual(self.library.path.read_bytes(),before)

    def test_confirmed_unavailable_setup_and_preinstalled_behavior_are_preserved(self):
        for mode in ('installer','installed'):
            candidate=self.draft();candidate['installation'].update(mode=mode,confirmed=True);candidate['executable']=str(self.root/'unmounted/game.exe');candidate['working_dir']=''
            self.library.save(candidate);self.game=deepcopy(candidate)
            editor=self.save(candidate);editor.error.assert_not_called()
            self.assertEqual(self.library.games()[0],candidate)

    def test_changed_installer_draft_cannot_confirm_completed_installer_or_alias(self):
        replacement=self.root/'replacement.exe';replacement.write_text('Inert replacement installer')
        alias=self.root/'aliases/alias.exe';alias.parent.mkdir(exist_ok=True);alias.symlink_to(self.installer)
        hardlink=self.root/'aliases/hardlink.exe';hardlink.hardlink_to(self.installer)
        for executable in (self.installer,alias,hardlink):
            with self.subTest(executable=executable.name):
                candidate=self.draft();candidate['executable']=str(executable);candidate['installation']['installer']=str(replacement)
                before=self.library.path.read_bytes();editor=self.save(candidate)
                editor.error.assert_called_once();self.assertIsNotNone(editor.editor)
                self.assertEqual(self.library.path.read_bytes(),before)
                self.assertFalse(self.library.games()[0]['installation']['confirmed'])

    def test_changed_draft_keeps_attempt_identity_across_save_reopen_and_backup(self):
        replacement=self.root/'replacement.exe';replacement.write_text('Inert replacement installer')
        candidate=self.draft();candidate['executable']='';candidate['installation']['installer']=str(replacement)
        editor=self.save(candidate);editor.error.assert_not_called()
        saved=Library(self.library.root).games()[0]
        self.assertEqual(saved['installer_attempt']['executable'],str(self.installer.resolve()))
        self.assertEqual(saved['installation']['installer'],str(replacement))
        candidate=deepcopy(saved);candidate['executable']=str(self.installer)
        before=self.library.path.read_bytes();editor=self.save(candidate);editor.error.assert_called_once();self.assertEqual(self.library.path.read_bytes(),before)
        candidate['executable']=str(self.exe);editor=self.save(candidate);editor.error.assert_not_called()
        saved=Library(self.library.root).games()[0];self.assertTrue(saved['installation']['confirmed'])
        self.assertEqual(saved['installer_attempt']['executable'],str(self.installer.resolve()))
        archive=self.root/'backup.zip';self.library.export_zip(archive)
        restored=Library(self.root/'restored');restored.import_zip(archive)
        self.assertEqual(restored.games()[0]['installer_attempt']['executable'],str(self.installer.resolve()))

    def test_explicit_confirmation_also_rejects_completed_installer_after_draft_change(self):
        replacement=self.root/'replacement.exe';replacement.write_text('Inert replacement installer')
        candidate=self.draft();candidate['executable']=str(self.installer);candidate['installation']['installer']=str(replacement)
        before=self.library.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'setup installer'):self.service.confirm(candidate)
        self.assertEqual(self.library.path.read_bytes(),before)

    def test_new_attempt_binds_resolved_installer_and_replaces_old_binding(self):
        replacement=self.root/'replacement.exe';replacement.write_text('Inert replacement installer')
        alias=self.root/'selected-installer.exe';alias.symlink_to(replacement)
        candidate=self.draft();candidate['installer_attempt']={'session_id':candidate['installation']['session_id'],'executable':str(self.installer)}
        candidate['installation']['installer']=str(alias);session=str(uuid4())
        def fake_start(game,operation,before_start):
            self.assertEqual(operation,'installer');self.assertEqual(game['executable'],str(alias))
            before_start({'session_id':session},{})
        self.launcher.start.side_effect=fake_start
        saved=self.service.start(candidate)
        self.assertEqual(saved['installation']['session_id'],session)
        self.assertEqual(saved['installer_attempt']['session_id'],session)
        self.assertEqual(saved['installer_attempt']['executable'],str(replacement.resolve()))
        self.assertFalse(saved['installation']['confirmed'])
        alias.unlink();alias.symlink_to(self.installer)
        # Retargeting the selected spelling cannot erase the attempted executable.
        saved['installation']['confirmed']=True;saved['executable']=str(replacement)
        self.assertFalse(setup_state(saved)['ready'])

    def test_play_rejects_bound_installer_and_alias_before_any_launch(self):
        from game_library.launcher import Launcher
        replacement=self.root/'replacement.exe';replacement.write_text('Inert replacement installer')
        alias=self.root/'aliases/alias.exe';alias.parent.mkdir(exist_ok=True);alias.symlink_to(self.installer)
        hardlink=self.root/'aliases/hardlink.exe';hardlink.hardlink_to(self.installer)
        for executable in (self.installer,alias,hardlink):
            candidate=self.draft();candidate['executable']=str(executable)
            candidate['installation'].update(installer=str(replacement),confirmed=True)
            candidate['installer_attempt']={'session_id':candidate['installation']['session_id'],'executable':str(self.installer.resolve())}
            self.assertFalse(setup_state(candidate)['ready'])
            with patch('game_library.launcher.subprocess.Popen') as spawn:
                with self.assertRaisesRegex(ValueError,'cannot run setup'):Launcher(self.library.root).start(candidate)
                spawn.assert_not_called()

    def test_attempt_metadata_is_validated_and_old_session_does_not_bind_new_session(self):
        good={'session_id':self.game['installation']['session_id'],'executable':str(self.installer)}
        cases=(None,{},dict(good,unexpected=True),dict(good,session_id='invalid'),dict(good,executable='relative.exe'),dict(good,executable='bad\x00path'))
        for attempt in cases:
            candidate=self.draft();candidate['installer_attempt']=attempt;before=self.library.path.read_bytes()
            with self.subTest(attempt=attempt),self.assertRaises(ValueError):self.library.save(candidate)
            self.assertEqual(self.library.path.read_bytes(),before)
        # Older app versions preserve unknown top-level fields on a new attempt.
        candidate=self.draft();candidate['installer_attempt']={'session_id':str(uuid4()),'executable':str(self.exe)}
        self.library.save(candidate);editor=self.save(candidate);editor.error.assert_not_called()
        saved=self.library.games()[0]
        self.assertEqual(saved['installer_attempt'],good);self.assertTrue(setup_state(saved)['ready'])

    def test_saved_attempt_wins_over_changed_draft_metadata(self):
        saved=self.draft();saved['installer_attempt']={'session_id':saved['installation']['session_id'],'executable':str(self.installer)}
        self.library.save(saved)
        candidate=deepcopy(saved);candidate['executable']=str(self.installer)
        candidate['installation']['installer']=str(self.exe);candidate['installer_attempt']['executable']=str(self.exe)
        before=self.library.path.read_bytes();editor=self.save(candidate);editor.error.assert_called_once()
        self.assertEqual(self.library.path.read_bytes(),before)


if __name__=='__main__':unittest.main()
