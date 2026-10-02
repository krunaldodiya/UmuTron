"""Tray menu contract without a desktop or session-bus registration."""
import unittest

from gi.repository import GLib

from game_library.tray import Tray


class Invocation:
    def return_value(self, value):
        self.value = value


class TrayMenuTests(unittest.TestCase):
    def setUp(self):
        self.actions = []
        self.tray = Tray.__new__(Tray)
        for action in ('show', 'exit_app', 'fullscreen', 'desktop', 'settings', 'activity', 'appearance'):
            setattr(self.tray, action, lambda action=action: self.actions.append(action))

    def call(self, method, parameters):
        invocation = Invocation()
        self.tray.method(None, None, '/Menu', 'com.canonical.dbusmenu', method, parameters, invocation)
        return invocation.value.unpack()

    def test_visible_menu_contains_only_retained_actions(self):
        _, layout = self.call('GetLayout', GLib.Variant('(iias)', (0, -1, [])))
        self.assertEqual([node[0] for node in layout[2]], [1, 3, 4, 6, 2])
        self.assertEqual([node[1]['label'] for node in layout[2]],
                         ['Show UmuTron', 'Switch to Fullscreen', 'Switch to Desktop', 'Settings', 'Exit'])
        self.assertTrue(all(node[1]['enabled'] and node[1]['visible'] for node in layout[2]))

    def test_removed_items_are_absent_from_group_properties(self):
        groups, = self.call('GetGroupProperties', GLib.Variant('(aias)', (list(range(8)), [])))
        self.assertEqual([item for item, _ in groups], [0, 1, 2, 3, 4, 6])

    def test_retained_actions_dispatch_and_removed_items_do_nothing(self):
        for item in (1, 3, 4, 5, 6, 7, 2):
            self.tray.event(item, 'clicked')
        self.assertEqual(self.actions, ['show', 'fullscreen', 'desktop', 'settings', 'exit_app'])


if __name__ == '__main__':
    unittest.main()
