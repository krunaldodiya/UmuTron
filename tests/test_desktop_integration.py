"""Desktop identity contract, without GTK startup or writes to a real home."""
import ast
import configparser
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
APP_ID = 'io.github.game_library_launcher'


class DesktopIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.writes = {}
        # Capture installer outputs in memory; never touch a desktop/session/cache.
        with patch('game_library.library.atomic_write', side_effect=lambda p, data: self.writes.__setitem__(Path(p), data)), \
             patch('shutil.which', return_value=None), patch('pathlib.Path.unlink'):
            runpy.run_path(str(ROOT / 'tools/install.py'))
        self.entries = {}
        for path, data in self.writes.items():
            if path.suffix == '.desktop':
                parser = configparser.ConfigParser(interpolation=None)
                parser.read_string(data.decode())
                self.entries[path.name] = parser

    def test_window_id_resolves_to_one_visible_desktop_entry(self):
        self.assertIn(APP_ID + '.desktop', self.entries)
        entry = self.entries[APP_ID + '.desktop']['Desktop Entry']
        self.assertEqual(entry['Name'], 'UmuTron')
        self.assertEqual(entry['Icon'], 'game-library-launcher')
        self.assertEqual(entry['StartupWMClass'], APP_ID)
        visible = [name for name, parser in self.entries.items()
                   if not parser['Desktop Entry'].getboolean('NoDisplay', fallback=False)
                   and not parser['Desktop Entry'].getboolean('Hidden', fallback=False)]
        self.assertEqual(visible, [APP_ID + '.desktop'])

    def test_legacy_id_remains_launchable_without_competing_window_match(self):
        legacy = self.entries['game-library-launcher.desktop']['Desktop Entry']
        canonical = self.entries[APP_ID + '.desktop']['Desktop Entry']
        self.assertTrue(legacy.getboolean('NoDisplay'))
        self.assertFalse(legacy.getboolean('Hidden', fallback=False))
        self.assertNotIn('StartupWMClass', legacy)
        self.assertEqual(legacy['Exec'], canonical['Exec'])
        self.assertEqual(legacy['Icon'], canonical['Icon'])
        self.assertEqual(self.entries['game-library-launcher.desktop']['Desktop Action Demo']['Exec'],
                         canonical['Exec'] + ' --demo')

    def test_gtk_and_x11_program_identity_share_the_preserved_app_id(self):
        # Execute the actual initializer against inert stubs, never a native window.
        tree = ast.parse((ROOT / 'game_library/app.py').read_text())
        application = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Application')
        method = next(node for node in application.body if isinstance(node, ast.FunctionDef) and node.name == '__init__')
        stub_class = ast.ClassDef(name='Application', bases=[ast.Name(id='Base', ctx=ast.Load())],
                                  keywords=[], body=[method], decorator_list=[])
        from types import SimpleNamespace
        calls = []
        class Base:
            command_line = activate_window = None
            def __init__(self, **kwargs):
                calls.append(('application', kwargs['application_id']))
            def add_main_option(self, *args):
                pass
            def connect(self, *args):
                pass
        scope = {'Base': Base, 'APP_ID': APP_ID, 'APP_NAME': 'UmuTron', 'ICON_NAME': 'game-library-launcher',
                 'GLib': SimpleNamespace(set_prgname=lambda value: calls.append(('program', value)),
                                         set_application_name=lambda _: None, OptionFlags=SimpleNamespace(NONE=0),
                                         OptionArg=SimpleNamespace(NONE=0)),
                 'Gtk': SimpleNamespace(Window=SimpleNamespace(set_default_icon_name=lambda _: None)),
                 'Gio': SimpleNamespace(ApplicationFlags=SimpleNamespace(HANDLES_COMMAND_LINE=0))}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[stub_class], type_ignores=[])), '<initializer>', 'exec'), scope)
        for demo in (False, True):
            calls.clear()
            scope['Application'](demo=demo)
            identity = APP_ID + ('.demo' if demo else '')
            self.assertEqual(calls, [('program', identity), ('application', identity)])
