"""Setup presentation after removal of the per-game Prefix/stage tabs."""
from pathlib import Path
import tempfile
import unittest
from game_library.setup_state import setup_state


class SetupStateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.exe=self.root/'game.exe';self.exe.write_text('inert')

    def test_metadata_only_can_install_without_claiming_ready(self):
        state=setup_state({'executable':''})
        self.assertFalse(state['ready']);self.assertFalse(state['reinstall'])

    def test_existing_preinstalled_executable_uses_reinstall(self):
        state=setup_state({'executable':str(self.exe)})
        self.assertTrue(state['ready']);self.assertTrue(state['reinstall'])
        self.assertFalse(state['needs_confirmation'])

    def test_missing_configured_executable_does_not_become_first_install(self):
        self.exe.unlink();state=setup_state({'executable':str(self.exe)})
        self.assertFalse(state['ready']);self.assertTrue(state['reinstall'])
        self.assertIn('reconnect',state['description'])

    def test_installer_attempt_requires_confirmation(self):
        game={'executable':str(self.exe),'installation':{'mode':'installer','session_id':'saved'}}
        state=setup_state(game);self.assertFalse(state['ready']);self.assertTrue(state['needs_confirmation'])
        game['installation']['confirmed']=True
        self.assertTrue(setup_state(game)['ready'])
        game['installation'].pop('session_id')
        self.assertFalse(setup_state(game)['ready'])

    def test_setup_binary_and_missing_workdir_are_not_ready(self):
        game={'executable':str(self.exe),'installation':{'mode':'installer','session_id':'saved','confirmed':True,'installer':str(self.exe)}}
        self.assertFalse(setup_state(game)['ready'])
        game['installation']['installer']=str(self.root/'setup.exe');game['working_dir']=str(self.root/'missing')
        self.assertFalse(setup_state(game)['ready'])
        game['working_dir']=str(self.root)
        self.assertTrue(setup_state(game)['ready'])

    def test_partial_attempt_remains_secondary_and_readonly(self):
        game={'executable':'','installation':{'mode':'installer','session_id':'saved','prefix':str(self.root)}}
        before=repr(game);state=setup_state(game)
        self.assertTrue(state['reinstall']);self.assertTrue(state['needs_confirmation'])
        self.assertFalse(state['ready']);self.assertEqual(repr(game),before)

    def test_legacy_unstarted_installer_can_explicitly_accept_existing_files(self):
        state=setup_state({'executable':str(self.exe),'installation':{'mode':'installer','installer':str(self.root/'setup.exe')}})
        self.assertFalse(state['ready']);self.assertTrue(state['needs_confirmation'])
        self.assertTrue(state['reinstall'])
