"""Manual Setup/installer flows work with no storage registration or observer."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from game_library.app import Window
from game_library.installations import Installations
from game_library.library import Library


class UnusedStorage:
    def __getattr__(self,name):raise AssertionError('Manual flow consulted Storage: '+name)


class ManualStorageIndependenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.library=Library(self.root/'library');self.game=self.library.new_game();self.game['title']='Manual game';self.library.save(self.game)
        self.external=self.root/'unregistered-external';self.external.mkdir();self.setup=self.external/'setup.exe';self.setup.write_text('Inert installer')
        self.exe=self.external/'game.exe';self.exe.write_text('Inert game')
        self.launcher=Mock();self.launcher.active.return_value=False
        self.owner=SimpleNamespace(storage_service=UnusedStorage(),editor_kind='manage',editor=Mock(),installer_dialog=Mock(),
            demo=False,busy=False,launcher=self.launcher,original=deepcopy(self.game),game=deepcopy(self.game),
            library=self.library,installations=Installations(self.library,self.launcher),error=Mock(),notify=Mock(),
            close_installer=Mock(),show_game=Mock(),refresh_launch_state=Mock(),installer_entry=Mock(),confirm=Mock())

    def test_save_existing_external_executable_needs_no_registration(self):
        game={**self.game,'executable':str(self.exe),'working_dir':str(self.external)}
        self.owner.collect=lambda:deepcopy(game);Window.save_editor(self.owner)
        self.owner.error.assert_not_called();self.assertIsNone(self.owner.editor)
        self.assertEqual(self.library.games()[0]['executable'],str(self.exe));self.launcher.start.assert_not_called()
        self.assertFalse((self.library.root/'storage.sqlite3').exists())

    def test_manual_installer_confirmation_reaches_existing_service_without_drive_choice(self):
        self.owner.collect=lambda:deepcopy(self.game);self.owner.installer_entry.get_text.return_value=str(self.setup)
        self.owner.installations=Mock();self.owner.installations.start.return_value=deepcopy(self.game)
        Window.run_installer(self.owner);self.owner.error.assert_not_called();self.owner.installations.start.assert_not_called()
        self.owner.confirm.call_args.args[3]()
        self.owner.installations.start.assert_called_once();self.owner.error.assert_not_called()
        self.assertEqual(self.owner.installations.start.call_args.args[0]['installation']['installer'],str(self.setup))
        self.assertFalse((self.library.root/'storage.sqlite3').exists())

    def test_manual_confirmation_still_rejects_changed_or_closed_editor(self):
        self.owner.collect=lambda:deepcopy(self.game);self.owner.installer_entry.get_text.return_value=str(self.setup)
        self.owner.installations=Mock();Window.run_installer(self.owner)
        self.owner.installer_entry.get_text.return_value=str(self.exe);self.owner.confirm.call_args.args[3]()
        self.owner.installations.start.assert_not_called();self.owner.error.assert_called_once()
        self.owner.error.reset_mock();Window.run_installer(self.owner);self.owner.editor=None
        self.owner.confirm.call_args.args[3]();self.owner.installations.start.assert_not_called()
