"""Native browse controls with synthetic data; no desktop input or live service."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
from unittest.mock import Mock, patch

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--probe', action='store_true')
parser.add_argument('--quick', action='store_true')
parser.add_argument('--selection-only', action='store_true')
args = parser.parse_args()
if os.environ.get('GDK_BACKEND') != 'broadway':
    raise SystemExit('Use only the owned isolated GTK fixture.')
args.output.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(args.source), str(args.source / 'tools')]
from game_library.app import Application, Window
from game_library.demo import prepare_demo
from catalog_fixtures import FixtureCatalog
from navigation_fixture import after_frames, frame, key, ready, visible_in
from fullscreen_preview import capture
from gi.repository import Adw, Gdk, Gio, Gtk


class LocalCatalog(FixtureCatalog):
    def __init__(self):
        super().__init__()
        self.release = Event()
        self.release.set()
        self.entered = Event()

    def browse(self, query='', genre=None, page=1):
        self.entered.set()
        if not self.release.wait(8):
            raise ValueError('Fixture release was not supplied')
        self.calls.append((query, genre, page))
        items = [self.detail(i) for i in range(1, 73)]
        items = [item for item in items if query.casefold() in item['name'].casefold()
                 and (genre is None or any(g['id'] == genre for g in item['genres']))]
        total = len(items)
        return {'items': items[(page - 1) * 24:page * 24], 'page': page,
                'has_next': page * 24 < total, 'total_items': total,
                'total_pages': max(1, (total + 23) // 24)}

    def detail(self, game_id):
        data = super().detail(game_id)
        data['images'] = {}
        return data


checks = []
captures = []
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition, name):
    checks.append({'check': name, 'passed': bool(condition)})
    if not condition and not args.probe:
        raise AssertionError(name)


def focus_is(control):
    return window.focused_control(window) is control


def popup_frames(control):
    popup = control.get_popover()
    seen = [0]
    def tick(*_):
        seen[0] += 1
        return True
    callback = popup.add_tick_callback(tick)
    def allocated():
        popup.queue_draw()
        return seen[0] >= 3 and popup.get_height() >= 100 and all(row.get_height() >= 20 for row in control.rows)
    try:
        ready(window, allocated, 'Popup has its own allocated native frames')
    finally:
        popup.remove_tick_callback(callback)


with tempfile.TemporaryDirectory(prefix='umutron-browse-controls-') as temporary:
    os.environ['XDG_CACHE_HOME'] = temporary
    library = prepare_demo(True)
    for index in range(55):
        game = library.new_game()
        game.update(title=f'Browse fixture {index:02}', genres='Adventure' if index % 2 else 'Puzzle')
        library.save(game)
    original = deepcopy(library.games())
    app = Application(demo=True)
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    provider = LocalCatalog()
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name = ''
        controller.return_value.error = ''
        window = Window(app, library, demo=True, catalog_provider=provider)
    app.window = window
    window.navigation_window = lambda: window
    window.launcher.start = Mock(side_effect=AssertionError('Execution is disabled'))
    window.catalog.image_transport = Mock(side_effect=AssertionError('No image requests in controls fixture'))
    window.proton_manager.releases = lambda *a, **kw: []
    for child in window.layout:
        if isinstance(child, Adw.Banner):
            child.set_title('NATIVE TEST RENDER · browse controls · fictional games · Play disabled')
    try:
        for size in (((1120, 800),) if args.quick else ((1120, 800), (900, 600))):
            for fullscreen in ((False,) if args.quick else (False, True)):
                window.set_tv_mode(fullscreen)
                window.unfullscreen()
                window.set_visible(False)
                window.unrealize()
                window.set_size_request(*size)
                window.set_default_size(*size)
                window.present()
                for route in (('library',) if args.quick else ('library', 'store')):
                    prefix = f'{route} {"fullscreen" if fullscreen else "desktop"} {size}'
                    print('CASE ' + prefix, flush=True)
                    window.routes[route].update(query='', genre=None, page=1, scroll=0, focus=None)
                    if route == 'library':
                        window.routes[route]['sort'] = 0
                        window.show_library()
                    else:
                        library_state = {key: window.routes['library'][key] for key in ('query', 'genre', 'sort', 'page')}
                        window.show_store()
                    frame(window)
                    ready(window, lambda: not window.catalog_futures and bool(window.collection_tiles), prefix + ' loaded')
                    check(window.controller_enabled(), prefix + ' focused app receives controller dispatch')
                    if not args.probe:
                        window.navigation_window = lambda: None
                        check(not window.controller_enabled(), prefix + ' inactive app rejects controller dispatch')
                        window.navigation_window = lambda: object()
                        check(window.controller_enabled() == fullscreen, prefix + ' desktop modal retains its own native input')
                        window.navigation_window = lambda: window
                        window.busy = True
                        check(not window.controller_enabled(), prefix + ' busy app rejects controller dispatch')
                        window.busy = False
                    menu_controls = all(isinstance(getattr(window, name, None), Gtk.MenuButton)
                                        for name in ('collection_genre',))
                    check(menu_controls, prefix + ' Filter is an owned native button')
                    window.collection_search.grab_focus()
                    window.controller_action('down')
                    check(focus_is(window.collection_search_button), prefix + ' input Down reaches Search')
                    if args.probe:
                        continue
                    controls = [window.collection_search, window.collection_search_button,
                                window.collection_genre]
                    if args.selection_only:
                        genre = controls[2]
                        expected_genre = genre.get_model().get_string(1).casefold() if route == 'library' else window.catalog_genres[0]['id']
                        window.routes[route]['page'] = 2
                        genre.grab_focus()
                        genre.popup()
                        popup_frames(genre)
                        genre.rows[1].emit('clicked')
                        ready(window, lambda: not window.catalog_futures, prefix + ' selected genre data completed')
                        after_frames(window, lambda: focus_is(genre), prefix + ' Filter selection returns to opener')
                        check(window.routes[route]['genre'] == expected_genre and window.routes[route]['page'] == 1, prefix + ' Filter selection updates route and resets page')
                        check(bool(window.collection_tiles), prefix + ' matching filtered results shown')
                        if route == 'store':
                            check(all(any(g['id'] == expected_genre for g in tile.catalog_item['genres']) for tile in window.collection_tiles.values()), prefix + ' Store filter sent before pagination')
                        else:
                            check(all(expected_genre in g['genres'].casefold() for g in window.tv_games), prefix + ' Library filter applies to full set')
                        genre.popup()
                        popup_frames(genre)
                        filename = f'{route}-{"fullscreen" if fullscreen else "desktop"}-{size[0]}x{size[1]}-selected-popup-native-test.png'
                        capture(genre.get_popover(), args.output / filename, remap=False)
                        captures.append({'file': filename, 'sha256': sha(args.output / filename)})
                        genre.rows[0].emit('clicked')
                        ready(window, lambda: not window.catalog_futures, prefix + ' clearing genre completed')
                        after_frames(window, lambda: focus_is(genre), prefix + ' cleared Filter retains focus')
                        check(window.routes[route]['genre'] is None, prefix + ' clear filter restores all genres')
                        if route == 'store':
                            genre.popup()
                            popup_frames(genre)
                            stale_row = genre.rows[1]
                            window.store_genres_loaded([{'id': 100 + i, 'name': f'Long fixture genre {i:02}'} for i in range(30)])
                            popup_frames(genre)
                            state_before = window.routes['store']['genre']
                            stale_row.emit('clicked')
                            check(window.routes['store']['genre'] == state_before, prefix + ' stale removed row cannot select a different genre')
                            genre.rows[-1].grab_focus()
                            after_frames(window, lambda: visible_in(genre.rows[-1], genre.scroll), prefix + ' long menu scroll reveals focused row')
                            check(genre.get_popover().get_height() <= size[1] and visible_in(genre.rows[-1], genre.scroll), prefix + ' long menu remains bounded and reachable')
                            key(window, Gdk.KEY_Escape)
                        check(library.games() == original, prefix + ' selection checks preserve saved library')
                        continue
                    first = next(iter(window.collection_tiles.values()))
                    header = (window.tv_library_tab if route == 'library' else window.tv_games_tab) if fullscreen else (window.library_nav if route == 'library' else window.store_nav)
                    for direction, order in (('down', controls[1:] + [first]),
                                             ('up', list(reversed(controls)) + [header])):
                        if direction == 'down':
                            controls[0].grab_focus()
                        for expected in order:
                            window.controller_action(direction)
                            check(focus_is(expected), prefix + ' controller ' + direction + ' ordered stop ' + type(expected).__name__)
                            if expected is not header:
                                ready(window, lambda: visible_in(expected, window.collection_scroll), prefix + ' focus visible')
                    controls[0].set_text('native caret')
                    controls[0].set_position(4)
                    controls[0].grab_focus()
                    for value in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Home, Gdk.KEY_End, Gdk.KEY_BackSpace):
                        check(not key(window, value) and controls[0].get_position() == 4,
                              prefix + ' native editing retained ' + str(value))
                    check(not key(window, Gdk.KEY_Tab), prefix + ' input Tab remains native')
                    window.child_focus(Gtk.DirectionType.TAB_FORWARD)
                    check(focus_is(controls[1]), prefix + ' GTK Tab reaches Search')
                    if fullscreen:
                        key(window, Gdk.KEY_Tab)
                    else:
                        check(not key(window, Gdk.KEY_Tab), prefix + ' desktop Tab remains GTK-owned')
                        window.child_focus(Gtk.DirectionType.TAB_FORWARD)
                    check(focus_is(controls[2]), prefix + ' Tab reaches Filter')
                    controls[0].set_text('')
                    for control in controls[2:]:
                        before = deepcopy(window.routes[route])
                        control.grab_focus()
                        # Emit the native toggle's clicked signal, not raw or host input.
                        control.get_first_child().emit('clicked')
                        ready(window, lambda: control.get_popover().get_visible(), prefix + ' click opens menu')
                        check(window.controller_popover(window) is control.get_popover(), prefix + ' menu has navigation ownership')
                        window.controller_action('down')
                        focused = window.focused_control(window)
                        check(focused in control.rows, prefix + ' menu navigation stays inside')
                        for action in ('pageup', 'pagedown', 'desktop', 'play'):
                            window.controller_action(action)
                            check(focus_is(focused), prefix + ' open menu contains ' + action)
                        check(key(window, Gdk.KEY_Escape), prefix + ' Escape handled in menu')
                        after_frames(window, lambda: not control.get_popover().get_visible() and focus_is(control), prefix + ' cancel returns to opener')
                        check(window.routes[route] == before, prefix + ' cancel preserves state')
                    check(not hasattr(window, 'collection_sort'), prefix + ' Sort is absent from both browse routes')
                    if route == 'store':
                        genre = controls[2]
                        genre.popup()
                        ready(window, lambda: genre.get_popover().get_visible(), prefix + ' genre open during update')
                        window.store_genres_loaded([*window.catalog_genres, {'id': 99, 'name': 'New fixture genre'}])
                        after_frames(window, lambda: window.focused_control(window) in genre.rows, prefix + ' taxonomy refresh retains menu focus')
                        key(window, Gdk.KEY_Escape)
                        check(library_state == {key: window.routes['library'][key] for key in library_state}, prefix + ' Store preserves independent Library state')
                    controls[0].set_text('no matching fixture 987654')
                    controls[0].emit('activate')
                    window.mark_browse_input()
                    controls[1].grab_focus()
                    ready(window, lambda: not window.catalog_futures and not window.collection_tiles, prefix + ' empty result')
                    controls[1].grab_focus()
                    for expected in controls[2:]:
                        window.controller_action('right')
                        check(focus_is(expected), prefix + ' empty result retains toolbar stops')
                    window.controller_action('down')
                    check(focus_is(controls[-1]), prefix + ' empty result has no invisible card target')
                    controls[0].set_text('')
                    controls[0].emit('activate')
                    ready(window, lambda: not window.catalog_futures and bool(window.collection_tiles), prefix + ' clear restores data')
                    # Deliberately open before the card restoration's next tick.
                    if route == 'library':
                        window.render_collection()
                    controls[2].grab_focus()
                    controls[2].popup()
                    ready(window, lambda: controls[2].get_popover().get_visible(), prefix + ' capture menu open')
                    after_frames(window, lambda: window.focused_control(window) in controls[2].rows, prefix + ' menu defeats queued card focus restoration')
                    check(window.focused_control(window) in controls[2].rows, prefix + ' menu owns focus after queued frames')
                    check(controls[2].get_popover().get_width() >= 320 and
                          not controls[2].rows[0].get_child().get_layout().is_ellipsized(), prefix + ' menu labels have readable allocated width')
                    filename = f'{route}-{"fullscreen" if fullscreen else "desktop"}-{size[0]}x{size[1]}-toolbar-native-test.png'
                    capture(window, args.output / filename, remap=False)
                    captures.append({'file': filename, 'sha256': sha(args.output / filename)})
                    filename = filename.replace('-toolbar-', '-popup-')
                    popup_frames(controls[2])
                    capture(controls[2].get_popover(), args.output / filename, remap=False)
                    captures.append({'file': filename, 'sha256': sha(args.output / filename)})
                    key(window, Gdk.KEY_Escape)
                    if route == 'store':
                        provider.release.clear()
                        provider.entered.clear()
                        controls[0].set_text('Nebula')
                        controls[0].emit('activate')
                        ready(window, provider.entered.is_set, prefix + ' held response entered')
                        controls[1].grab_focus()
                        window.controller_action('right')
                        check(focus_is(controls[2]), prefix + ' loading Filter remains reachable')
                        controls[0].set_text('Crimson')
                        controls[0].emit('activate')
                        controls[2].popup()
                        ready(window, lambda: controls[2].get_popover().get_visible(), prefix + ' menu opens while result held')
                        provider.release.set()
                        ready(window, lambda: not window.catalog_futures, prefix + ' stale and current responses finish')
                        after_frames(window, lambda: window.focused_control(window) in controls[2].rows, prefix + ' completion retains open menu focus')
                        check(window.routes['store']['query'] == 'Crimson' and all('Crimson' in tile.catalog_item['name'] for tile in window.collection_tiles.values()), prefix + ' stale query cannot repaint current results')
                        key(window, Gdk.KEY_Escape)
                    check(library.games() == original, prefix + ' saved library unchanged')
        check(not window.launcher.start.called, 'No execution requested')
    finally:
        provider.release.set()
        window.exiting = True
        window.catalog_cancel()
        window.catalog_pool.shutdown(wait=True, cancel_futures=True)
        window.pool.shutdown(wait=True)
        window.controller.close()
        window.destroy()
        result = {'label': 'Synthetic native GTK fixture; no physical input or live desktop; Play disabled',
                  'source': str(args.source), 'source_sha256': {str(p.relative_to(args.source)): sha(p) for p in (args.source / 'game_library').glob('*.py')},
                  'fixture_sha256': sha(Path(__file__)), 'checks': checks, 'captures': captures,
                  'saved_games_unchanged': library.games() == original}
        (args.output / 'checks.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'passed': sum(c['passed'] for c in checks), 'total': len(checks)}))
