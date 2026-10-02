"""Behavioral native fullscreen regression checks, using an isolated Broadway fixture."""
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fullscreen_preview import settle, capture
from game_library.app import Application, Window
from game_library.demo import prepare_demo
from game_library import metadata
from game_library.fullscreen import set_art
from gi.repository import Adw, Gdk, Gio, Gtk


def widgets(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from widgets(child)
        child = child.get_next_sibling()


def click(widget, text):
    next(w for w in widgets(widget) if isinstance(w, Gtk.Button) and w.get_label() == text).emit('clicked')


with tempfile.TemporaryDirectory(prefix='umutron-console-checks-') as temp:
    os.environ['XDG_CACHE_HOME'] = temp
    library = prepare_demo(True)
    app = Application(demo=True)
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name = ''
        controller.return_value.error = ''
        w = Window(app, library, demo=True)
    app.window = w
    w.present()
    settle()
    # A metadata response arriving after Cancel cannot write into a later page.
    original = library.games()[0]
    w.show_game(original)
    before = library.path.read_bytes()
    w.open_metadata()
    w.find_metadata()
    search = next(d for d in Gtk.Window.get_toplevels() if d.get_title() == 'Find game metadata')
    release = Event()
    entered = Event()
    def delayed_fetch(_):
        entered.set()
        if not release.wait(5):
            raise RuntimeError('Fixture did not release metadata worker')
        return {'title': 'Discard this stale result'}, {}, []
    with patch.object(metadata, 'search', return_value=[{'id': 1, 'name': 'Delayed fixture'}]), patch.object(metadata, 'fetch_game', delayed_fetch):
        click(search, 'Search')
        settle()
        click(search, 'Select')
        assert entered.wait(2)
        w.cancel_editor()
        release.set()
        settle()
        assert not w.busy and w.editor is None
        assert library.path.read_bytes() == before and w.game['title'] == original['title']
    # Prefix and setup remain available only in desktop Manage Game.
    w.open_manage()
    assert w.prefix_panel and w.stage_stack.get_child_by_name('prefix') is w.prefix_panel
    assert not w.advanced.get_expanded()
    w.cancel_editor()
    w.show_library()
    w.set_tv_mode(True)
    w.unfullscreen()
    w.navigation_window = lambda: w
    w.set_visible(False)
    w.unrealize()
    w.set_default_size(1024, 600)
    w.present()
    settle()
    assert len({(tile.get_width(), tile.get_height()) for _, tile in w.tv_tiles}) == 1, [(t.get_width(),t.get_height(),t.console_cover.get_size_request(),t.console_title.get_size_request()) for _,t in w.tv_tiles]
    saved = library.path.read_bytes()
    selection = w.tv_games[-1]
    w.select_tv_game(selection)
    w.focus_tv_card(False)
    assert w.tv_eyebrow.get_text() == 'IN YOUR COLLECTION' and w.backdrop.get_paintable() is not None
    w.show_game(selection)
    detail_widgets = list(widgets(w.body))
    assert not any(isinstance(item, Gtk.Label) and item.get_text() == 'YOUR NEXT ADVENTURE' for item in detail_widgets)
    assert not any(item.has_css_class('tv-detail-logo') for item in detail_widgets)
    assert len([item for item in detail_widgets if isinstance(item, Gtk.Picture)]) == 1, 'Keep only the left cover inside details'
    assert w.cover.get_parent() is w.play_buttons[selection['id']].get_parent()
    assert w.backdrop.get_paintable() is not None and selection['artwork']['logo'], 'Keep backdrop and stored artwork'
    summary = w.cover.get_parent().get_parent().get_last_child()
    title = summary.get_first_child()
    assert isinstance(title, Gtk.Label) and title.has_css_class('tv-title') and title.get_text() == selection['title'], 'Title directly starts the summary'
    w.go_back()  # Exercise queued detail focus before the next main-loop iteration.
    settle()
    assert w.tv_selected_id == selection['id'] and w.game is None
    assert w.focused_control(w) is next(t for gid, t in w.tv_tiles if gid == selection['id'])
    w.controller_action('play')
    assert not w.launcher.active()
    w.tv_games_tab.grab_focus()
    w.on_key(w.keyboard_controller, Gdk.KEY_Right, 0, Gdk.ModifierType(0))
    assert w.focused_control(w) is w.tv_library_tab and w.tv_section == 'games'
    w.controller_action('select')
    settle()
    assert w.tv_section == 'library'
    capture(w,Path(temp)/'grid-ready.png')
    w.select_tv_game(w.tv_games[0]);w.focus_tv_card(False);settle()
    assert w.focused_control(w) is w.tv_tiles[0][1],w.focused_control(w)
    previous=w.tv_selected_id
    w.on_key(w.keyboard_controller,Gdk.KEY_Right,0,Gdk.ModifierType(0));settle()
    assert w.tv_selected_id!=previous, [(t.get_width(),t.get_height(),t.compute_bounds(w)[1].get_x(),t.compute_bounds(w)[1].get_y()) for _,t in w.tv_tiles]
    # Corrupt art clears the previous hero and has a same-size cover fallback.
    corrupted = library.new_game()
    bad = library.art_dir / ('0' * 64 + '.png')
    bad.write_bytes(b'not an image')
    corrupted.update(title='Missing artwork', artwork={'hero': bad.name, 'portrait': bad.name})
    library.save(corrupted)
    w.set_tv_section('games')
    w.select_tv_game(corrupted)
    assert w.backdrop.get_paintable() is None
    assert w.tv_play.get_label() == 'Setup' and not w.tv_play.get_sensitive()
    assert w.tv_open.get_sensitive() and 'desktop' in w.tv_launch_status.get_text()
    assert not set_art(w.backdrop, bad)
    settle()
    assert len({(t.get_width(), t.get_height()) for _, t in w.tv_tiles}) == 1
    # Actual launch/stop state is reflected without adding an execution path.
    class LaunchFixture:
        record = {}
        stops = []
        def current(self): return self.record
        def active(self): return bool(self.record)
        def snapshot(self, _): return {'logs': []}
        def stop(self, game_id): self.stops.append(game_id)
    launch = LaunchFixture()
    w.launcher = launch
    w.demo = False
    w.show_game(selection)
    launch.record = {'game_id': selection['id'], 'title': selection['title'], 'state': 'Running', 'supervisor_pid': 1, 'operation': 'play'}
    w.refresh_launch_state()
    play = w.play_buttons[selection['id']]
    assert play.get_label() == 'Stop' and play.has_css_class('destructive-action')
    play.emit('clicked')
    prompt = next(d for d in Gtk.Window.get_toplevels() if isinstance(d, Adw.MessageDialog) and d.get_visible())
    prompt.emit('response', 'cancel')
    assert launch.stops == [] and launch.active()
    w.show_game(original)
    if original['id'] != selection['id']:
        assert not w.play_buttons[original['id']].get_sensitive()
    launch.record = {'game_id': original['id'], 'title': original['title'], 'state': 'Downloading runtime', 'supervisor_pid': 1}
    w.refresh_launch_state()
    assert w.runtime_progress.get_visible() and 'Waiting' in w.runtime_label.get_text()
    launch.record = {}
    w.refresh_launch_state()
    assert not w.runtime_progress.get_visible()
    w.demo = True
    # Primary action stays within the first small-window viewport.
    play = w.play_buttons[original['id']]
    settle()
    valid, bounds = play.compute_bounds(w)
    assert valid and bounds.get_y() + bounds.get_height() <= w.get_height(), (bounds.get_y(), bounds.get_height(), w.get_height())
    capture(w, Path(temp) / 'small-detail.png')
    w.detail_scroll.get_child().get_child().append(Gtk.Label(label='Long fixture information\n'*100));settle()
    scroll=w.detail_scroll.get_vadjustment();initial=scroll.get_value();expected=min(scroll.get_upper()-scroll.get_page_size(),initial+.8*scroll.get_page_size())
    w.controller_action('pagedown');settle();down=scroll.get_value();expected_up=max(0,down-.8*scroll.get_page_size())
    w.controller_action('pageup');settle();up=scroll.get_value()
    print('scroll bounds',initial,down,up,scroll.get_page_size(),scroll.get_upper(),flush=True)
    assert abs(down-expected)<1 and abs(up-expected_up)<1
    w.controller_action('play');settle()
    assert w.detail_scroll.get_child().get_scroll_to_focus()

    assert not any(isinstance(item, (Gtk.Entry, Gtk.DropDown)) for item in widgets(w.body))
    assert not any(isinstance(item, Gtk.Button) and item.get_tooltip_text() in ('Edit Metadata', 'Manage Game') for item in widgets(w.body))
    for game in list(library.games()):
        library.delete(game['id'])
    w.show_library()
    assert w.backdrop.get_paintable() is None and not w.tv_tiles
    assert any(isinstance(item, Adw.StatusPage) for item in widgets(w.body))
    w.controller.close()
    w.destroy()
    w.pool.shutdown(wait=True)
print('PASS: equal artwork slots, concise detail summary with preserved left cover/backdrop, responsive primary action, missing/corrupt/empty states, keyboard selection, rapid Back focus, late metadata cancellation, Prefix/setup preservation, Play/Stop and one-game guard')
