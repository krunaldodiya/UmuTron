from types import SimpleNamespace
import unittest
from unittest.mock import patch

from umutron.app import Window


class LauncherPickerTests(unittest.TestCase):
    def test_launcher_picker_defaults_to_game_launchers_with_all_files_override(self):
        filters = []

        class Filter:
            def __init__(self):
                self.name = ''
                self.mimes = []
                self.patterns = []
            def set_name(self, name): self.name = name
            def add_mime_type(self, value): self.mimes.append(value)
            def add_pattern(self, value): self.patterns.append(value)

        class Dialog:
            def set_current_folder(self, folder): self.folder = folder
            def add_filter(self, value): filters.append(value)
            def connect(self, *_): pass
            def show(self): pass

        dialog = Dialog()
        gtk = SimpleNamespace(
            FileChooserAction=SimpleNamespace(SAVE='save', SELECT_FOLDER='folder', OPEN='open'),
            FileChooserNative=SimpleNamespace(new=lambda *_: dialog),
            FileFilter=Filter,
            ResponseType=SimpleNamespace(ACCEPT='accept'),
        )
        gio = SimpleNamespace(File=SimpleNamespace(new_for_path=lambda path: path))
        window = SimpleNamespace(editor=None, storage_service=None)
        with patch('umutron.app.Gtk', gtk), patch('umutron.app.Gio', gio):
            Window.choose_file(window, 'Choose launcher', lambda _: None, parent=object(), launcher=True)

        self.assertEqual([item.name for item in filters], ['Game launchers', 'All files'])
        self.assertIn('*.exe', filters[0].patterns)
        self.assertIn('application/x-executable', filters[0].mimes)
        self.assertEqual(filters[1].patterns, ['*'])


if __name__ == '__main__':
    unittest.main()
