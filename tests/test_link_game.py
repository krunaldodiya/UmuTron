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

    def test_link_game_with_steam_save_migration(self):
        window = Window(self.app, self.library, demo=True)
        try:
            window.game = None
            window.detail_item = {
                'id': 75235,
                'title': 'Ghost of Tsushima',
                'images': {},
            }
            runner_dir = self.root / 'fake-proton'
            runner_dir.mkdir(exist_ok=True)
            (runner_dir / 'proton').write_text('#!/bin/sh\n')
            window.proton_manager.installed = MagicMock(return_value=[str(runner_dir)])

            game_folder = self.root / 'SteamLibrary' / 'steamapps' / 'common' / 'Ghost of Tsushima'
            game_folder.mkdir(parents=True, exist_ok=True)
            exe = game_folder / 'GhostOfTsushima.exe'
            exe.write_text('fake binary')
            (game_folder / 'steam_appid.txt').write_text('2215430\n')

            steam_docs = self.root / 'SteamLibrary' / 'steamapps' / 'compatdata' / '2215430' / 'pfx' / 'drive_c' / 'users' / 'steamuser' / 'Documents'
            steam_docs.mkdir(parents=True)
            (steam_docs / 'save.dat').write_text('save data')

            window.open_add_installed_game()
            from gi.repository import Gtk
            def widgets(w):
                yield w
                c = w.get_first_child()
                while c:
                    yield from widgets(c)
                    c = c.get_next_sibling()
            all_entries = [w for w in widgets(window.add_installed_dialog) if isinstance(w, Gtk.Entry)]
            all_entries[0].set_text(str(game_folder))
            all_entries[1].set_text(str(exe))
            buttons = [w for w in widgets(window.add_installed_dialog) if isinstance(w, Gtk.Button) and w.get_label() == 'Link a game']
            buttons[0].emit('clicked')

            self.assertIsNotNone(window.game)
            prefix = Path(window.game['launch']['prefix'])
            our_save = prefix / 'drive_c' / 'users' / 'steamuser' / 'Documents' / 'save.dat'
            self.assertTrue(our_save.is_file())
            self.assertEqual(our_save.read_text(), 'save data')
        finally:
            window.pool.shutdown(wait=False)
            window.destroy()

    def test_linked_game_location_can_be_corrected_from_game_settings(self):
        window = Window(self.app, self.library, demo=True)
        try:
            old_root = self.root / 'old-game'
            old_root.mkdir()
            old_launcher = old_root / 'old.exe'
            old_launcher.write_text('old')
            new_root = self.root / 'correct-game'
            new_root.mkdir()
            new_launcher = new_root / 'correct.exe'
            new_launcher.write_text('new')
            prefix = self.root / 'prefix'
            prefix.mkdir()
            game = self.library.new_game()
            game.update(title='Correctable Game', executable=str(old_launcher), working_dir=str(old_root),
                        launch={'prefix': str(prefix), 'proton': 'UMU-Latest'},
                        installation={'mode': 'installed', 'root': str(old_root), 'prefix': str(prefix), 'confirmed': True})
            self.library.save(game)
            window.show_game(game)
            window.open_game_settings()
            from gi.repository import Gtk
            def widgets(widget):
                yield widget
                child = widget.get_first_child()
                while child:
                    yield from widgets(child)
                    child = child.get_next_sibling()
            settings = window.game_settings_dialog
            entries = [widget for widget in widgets(settings) if isinstance(widget, Gtk.Entry)]
            next(entry for entry in entries if entry.get_text() == str(old_root)).set_text(str(new_root))
            next(entry for entry in entries if entry.get_text() == str(old_launcher)).set_text(str(new_launcher))
            next(widget for widget in widgets(settings) if isinstance(widget, Gtk.Button) and widget.get_label() == 'Save linked location').emit('clicked')
            self.assertEqual(window.game['installation']['root'], str(new_root.resolve()))
            self.assertEqual(window.game['executable'], str(new_launcher.resolve()))
            saved = next(item for item in self.library.games() if item['id'] == game['id'])
            self.assertEqual(saved['working_dir'], str(new_root.resolve()))
        finally:
            window.pool.shutdown(wait=False)
            window.destroy()


if __name__ == '__main__':
    unittest.main()
