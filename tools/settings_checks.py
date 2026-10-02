"""Check Settings access to Activity/Appearance on an isolated native display."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fullscreen_preview import settle
from game_library.app import Application, Window
from game_library.demo import prepare_demo
from gi.repository import Adw, Gio, Gtk


def widgets(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from widgets(child)
        child = child.get_next_sibling()


with tempfile.TemporaryDirectory(prefix='umutron-settings-check-') as temp:
    os.environ['XDG_CACHE_HOME'] = temp
    library = prepare_demo(True)
    app = Application(demo=True)
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name = ''
        controller.return_value.error = ''
        window = Window(app, library, demo=True)
    app.window = window
    window.present()
    settle()
    window.log_revealer.set_reveal_child(False)
    for _ in range(2):
        window.open_settings()
        settle()
        dialog = next(w for w in Gtk.Window.get_toplevels()
                      if w.get_title() == 'Settings' and w.get_visible())
        appearance = next(w for w in widgets(dialog)
                          if isinstance(w, Adw.PreferencesGroup) and w.get_title() == 'Appearance')
        choice = next(w for w in widgets(appearance) if isinstance(w, Gtk.DropDown))
        choice.set_selected(2)
        assert library.data['settings']['theme'] == 'dark'
        activity = next((w for w in widgets(dialog)
                         if isinstance(w, Gtk.Button) and w.get_label() == 'Activity'), None)
        assert activity is not None, 'Settings must expose Activity'
        activity.emit('clicked')
        settle()
        assert not dialog.get_visible(), 'Activity closes Settings before revealing the viewer'
        assert window.log_revealer.get_reveal_child(), 'Activity is open, including on repeated entry'
        assert not window.launcher.active()
    window.controller.close()
    window.destroy()
    window.pool.shutdown(wait=True)
print('PASS: Settings Appearance changes theme; Activity opens the existing viewer on first and repeated entry')
