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
        self.mode=False;self.tray.mode=lambda:self.mode;self.tray.last_mode=False;self.tray.revision=1;self.tray.connection=None
        for action in ('show', 'exit_app', 'fullscreen', 'desktop', 'settings', 'activity', 'appearance'):
            setattr(self.tray, action, lambda action=action: self.actions.append(action))
        def switch(value):self.actions.append('fullscreen' if value else 'desktop');self.mode=value
        self.tray.fullscreen=lambda:switch(True);self.tray.desktop=lambda:switch(False)

    def call(self, method, parameters):
        invocation = Invocation()
        self.tray.method(None, None, '/Menu', 'com.canonical.dbusmenu', method, parameters, invocation)
        return invocation.value.unpack()

    def test_visible_menu_contains_only_retained_actions(self):
        _, layout = self.call('GetLayout', GLib.Variant('(iias)', (0, -1, [])))
        self.assertEqual([node[0] for node in layout[2]], [1, 3, 6, 2])
        self.assertEqual([node[1]['label'] for node in layout[2]],
                         ['Show UmuTron', 'Switch to fullscreen', 'Settings', 'Exit'])
        self.assertTrue(all(node[1]['enabled'] and node[1]['visible'] for node in layout[2]))

    def test_removed_items_are_absent_from_group_properties(self):
        groups, = self.call('GetGroupProperties', GLib.Variant('(aias)', (list(range(8)), [])))
        self.assertEqual([item for item, _ in groups], [0, 1, 2, 3, 6])

    def test_retained_actions_dispatch_and_removed_items_do_nothing(self):
        for item in (1, 3, 4, 5, 6, 7, 2):
            self.tray.event(item, 'clicked')
        self.assertEqual(self.actions, ['show', 'fullscreen', 'desktop', 'settings', 'exit_app'])

    def test_opposite_mode_only_with_revision_and_stale_click_rejection(self):
        before,_=self.call('GetLayout',GLib.Variant('(iias)',(0,-1,[])))
        self.mode=True
        changed,layout=self.call('GetLayout',GLib.Variant('(iias)',(0,-1,[])))
        self.assertGreater(changed,before);self.assertEqual([n[0] for n in layout[2]],[1,4,6,2])
        self.tray.event(3,'clicked');self.assertFalse(self.actions)
        self.tray.event(4,'clicked');self.tray.event(4,'clicked')
        self.assertEqual(self.actions,['desktop'])
        visible,=self.call('GetProperty',GLib.Variant('(is)',(4,'visible')))
        self.assertFalse(visible)

    def test_query_refresh_catches_mode_change_before_notification(self):
        self.mode=True
        changed,=self.call('AboutToShow',GLib.Variant('(i)',(0,)))
        self.assertTrue(changed)
        changed,=self.call('AboutToShow',GLib.Variant('(i)',(0,)))
        self.assertFalse(changed)
        self.mode=False
        updates,errors=self.call('AboutToShowGroup',GLib.Variant('(ai)',([0],)))
        self.assertEqual(updates,[0]);self.assertEqual(errors,[])


if __name__ == '__main__':
    unittest.main()
