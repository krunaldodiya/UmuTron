"""Exercise the real stage transition method with inert widgets; no native desktop use."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


class Widget:
    def __init__(self, active=False):
        self.active = active
    def get_active(self):
        return self.active
    def set_sensitive(self, value):
        self.sensitive = value
    def set_visible(self, value):
        self.visible = value
    def add_css_class(self, _):
        pass
    def remove_css_class(self, _):
        pass
    def set_text(self, value):
        self.text = value


class Stack:
    def __init__(self, visible):
        self.visible = visible
    def get_visible_child_name(self):
        return self.visible
    def set_visible_child_name(self, value):
        self.visible = value


class PrefixStageTests(unittest.TestCase):
    def test_prefix_survives_poll_while_both_original_stages_still_work(self):
        source = Path(__file__).resolve().parents[1] / 'game_library/app.py'
        tree = ast.parse(source.read_text())
        window = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Window')
        method = next(n for n in window.body if isinstance(n, ast.FunctionDef) and n.name == 'update_install_stage')
        scope = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), scope)
        w = SimpleNamespace(already_installed=Widget(True), game={}, launcher=SimpleNamespace(active=lambda: False),
                            install_retry_requested=False, install_tab=Widget(), game_tab=Widget(),
                            stage_stack=Stack('prefix'), executable_stage=Widget(),
                            confirm_executable_button=Widget(), retry_stage_button=Widget())
        update = lambda: scope['update_install_stage'](w)
        update()
        self.assertEqual(w.stage_stack.visible, 'prefix')
        self.assertTrue(w.game_tab.sensitive)
        self.assertFalse(w.install_tab.sensitive)
        w.stage_stack.visible = 'game'
        w.already_installed.active = False
        update()
        self.assertEqual(w.stage_stack.visible, 'install')
        w.game = {'installation': {'session_id': 'fixture'}}
        update()
        self.assertEqual(w.stage_stack.visible, 'game')
        self.assertTrue(w.confirm_executable_button.visible)
