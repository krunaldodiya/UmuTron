import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from umutron.app import Application, Window
from umutron.library import Library


class LinkGameTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / 'library.json').write_text('{"version": 1, "games": [], "settings": {}}')
        self.library = Library(self.root)
        self.app = Application(demo=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_link_game_when_win_game_is_none(self):
        window = Window(self.app, self.library, demo=True)
        try:
            window.game = None
            window.detail_item = {
                'id': 75235,
                'title': 'Ghost of Tsushima',
                'images': {},
            }
            # Mock proton manager to provide a runner
            runner_dir = self.root / 'fake-proton'
            runner_dir.mkdir()
            (runner_dir / 'proton').write_text('#!/bin/sh\n')
            window.proton_manager.installed = MagicMock(return_value=[str(runner_dir)])

            # Create mock installed game directory and executable
            game_folder = self.root / 'SteamLibrary' / 'steamapps' / 'common' / 'Ghost of Tsushima'
            game_folder.mkdir(parents=True)
            exe = game_folder / 'GhostOfTsushima.exe'
            exe.write_text('fake binary')

            window.open_add_installed_game()
            self.assertIsNotNone(window.add_installed_dialog)

            # Find entries
            from gi.repository import Gtk
            def widgets(widget):
                yield widget
                child = widget.get_first_child()
                while child:
                    yield from widgets(child)
                    child = child.get_next_sibling()
            all_entries = [w for w in widgets(window.add_installed_dialog) if isinstance(w, Gtk.Entry)]
            self.assertEqual(len(all_entries), 2)
            all_entries[0].set_text(str(game_folder))
            all_entries[1].set_text(str(exe))

            # Find 'Link a game' button in footer
            buttons = [w for w in widgets(window.add_installed_dialog) if isinstance(w, Gtk.Button) and w.get_label() == 'Link a game']
            self.assertEqual(len(buttons), 1)

            # Click button
            buttons[0].emit('clicked')

            # Verify game was linked and created
            self.assertIsNotNone(window.game)
            self.assertEqual(window.game['title'], 'Ghost of Tsushima')
            self.assertEqual(window.game['executable'], str(exe))
            self.assertTrue(Path(window.game['launch']['prefix']).is_dir())
        finally:
            window.pool.shutdown(wait=False)
            window.destroy()


if __name__ == '__main__':
    unittest.main()
