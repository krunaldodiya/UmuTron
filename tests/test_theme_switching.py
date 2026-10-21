import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk

from umutron.app import Application, Window
from umutron.library import Library


class ThemeSwitchingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / 'library.json').write_text('{"version": 1, "games": [], "settings": {}}')
        self.library = Library(self.root)
        self.app = Application(demo=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dynamic_theme_switching(self):
        window = Window(self.app, self.library, demo=True)
        try:
            # Default theme
            self.assertEqual(window.theme_engine.active_theme_id, 'steamos-dark')
            self.assertTrue(Adw.StyleManager.get_default().get_dark())

            # Switch to OLED Midnight
            window.theme_engine.apply_theme('oled-midnight')
            self.assertEqual(window.theme_engine.active_theme_id, 'oled-midnight')
            self.assertTrue(Adw.StyleManager.get_default().get_dark())

            # Switch to Nord Frost
            window.theme_engine.apply_theme('nord-frost')
            self.assertEqual(window.theme_engine.active_theme_id, 'nord-frost')
            self.assertTrue(Adw.StyleManager.get_default().get_dark())

            # Switch to Clean Slate Light
            window.theme_engine.apply_theme('clean-slate-light')
            self.assertEqual(window.theme_engine.active_theme_id, 'clean-slate-light')
            self.assertFalse(Adw.StyleManager.get_default().get_dark())

            # Revert to SteamOS Dark
            window.theme_engine.apply_theme('steamos-dark')
            self.assertEqual(window.theme_engine.active_theme_id, 'steamos-dark')
            self.assertTrue(Adw.StyleManager.get_default().get_dark())
        finally:
            window.pool.shutdown(wait=False)
            window.destroy()

    def test_window_starts_with_persisted_theme_identifier(self):
        self.library.set_theme('steamos-dark')
        window = Window(self.app, self.library, demo=True)
        try:
            self.assertEqual(window.theme_engine.active_theme_id, 'steamos-dark')
        finally:
            window.pool.shutdown(wait=False)
            window.destroy()


if __name__ == '__main__':
    unittest.main()
