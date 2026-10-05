"""Desktop presentation regressions on inert native GTK widgets only."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch
from uuid import uuid4

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--probe', action='store_true')
args = parser.parse_args()
if os.environ.get('GDK_BACKEND') != 'broadway':
    raise SystemExit('Use only the isolated native fixture.')
args.output.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(args.source), str(args.source / 'tools')]
from catalog_fixtures import FixtureCatalog
from fullscreen_preview import capture, settle
from navigation_fixture import after_frames, frame, key, ready, visible_in
from game_library.app import Application, Window
from game_library.demo import prepare_demo
from game_library.play_history import record
from gi.repository import Adw, Gdk, Gio, Pango

sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
runtime = {str(p.relative_to(args.source)): sha(p) for p in (args.source / 'game_library').glob('*.py')}
checks, images, geometry = [], [], []


def check(value, name):
    checks.append({'check': name, 'passed': bool(value)})
    if not value and not args.probe:
        raise AssertionError(name)


def bounds(control, parent):
    valid, rect = control.compute_bounds(parent)
    assert valid
    return [round(v, 2) for v in (rect.get_x(), rect.get_y(), rect.get_width(), rect.get_height())]


def picture(name):
    # Geometry can settle one frame before the cached paint node catches up.
    after_frames(w, lambda: True, 'Final evidence frame', frames=3)
    path = args.output / (name + '.png')
    capture(w, path, remap=False)
    images.append({'file': path.name, 'sha256': sha(path)})


class MissingCatalog(FixtureCatalog):
    def detail(self, identity):
        item = super().detail(identity)
        item['images'] = {}
        return item


with tempfile.TemporaryDirectory(prefix='umutron-parity-checks-') as temporary:
    os.environ['XDG_CACHE_HOME'] = temporary
    library = prepare_demo(True)
    regular = library.games()[0]
    long_game = deepcopy(regular)
    long_game.update(id=str(uuid4()), title='A very long adventure across the stars: the complete collection and its many distant worlds', artwork={}, description='A long fictional description. ' * 35)
    library.save(long_game)
    for index in range(22):
        game = deepcopy(long_game)
        game.update(id=str(uuid4()), title=f'Distant world {index:02} · a fictional adventure')
        library.save(game)
    record(library.root, regular['id'], str(uuid4()), 100)
    record(library.root, long_game['id'], str(uuid4()), 200)
    original_games = library.games()
    app = Application(demo=True)
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name = controller.return_value.error = ''
        w = Window(app, library, demo=True, catalog_provider=MissingCatalog())
    app.window = w
    w.navigation_window = lambda: w
    w.launcher.start = Mock(side_effect=AssertionError('No execution in native parity checks'))
    w.proton_manager.releases = lambda *a, **kw: []
    w.update_tv_clock = lambda: False
    w.tv_clock.set_text('8:42 PM')
    w.catalog.image_transport = Mock(side_effect=AssertionError('No network in native parity checks'))
    for child in w.layout:
        if isinstance(child, Adw.Banner):
            child.set_visible(False)
    try:
        for dark in (True, False):
            manager = Adw.StyleManager.get_default()
            manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK if dark else Adw.ColorScheme.FORCE_LIGHT)
            for width, height in ((1920, 1080), (900, 600)):
                prefix = ('dark' if dark else 'light') + f'-{width}'
                w.set_visible(False); w.unrealize()
                w.set_size_request(width, height); w.set_default_size(width, height); w.present()
                w.home_selected_id = long_game['id']; w.show_home(); frame(w)
                w.mark_browse_input(); w.focus_browse_route()
                after_frames(w, lambda: w.tv_page.get_vadjustment().get_value() <= 1, 'Home top')
                check((w.get_width(), w.get_height()) == (width, height), prefix + ' exact viewport')
                check(w.has_css_class('desktop-mode') and w.has_css_class('desktop-dark') == dark, prefix + ' reacts to system palette signal')
                font = w.tv_title.get_pango_context().get_font_description().get_size() / Pango.SCALE
                check(font == (36 if width < 1400 else 52), prefix + ' responsive Home font')
                check(w.tv_title.get_lines() == 2 and w.tv_title.get_ellipsize() == Pango.EllipsizeMode.END, prefix + ' long hero remains bounded')
                check(w.home_backdrop.get_paintable() is None, prefix + ' missing hero clears previous image')
                check(not w.tv_play.get_sensitive(), prefix + ' demo Home Play disabled')
                geometry.append({'case': prefix, 'font': font, 'home_title': bounds(w.tv_title, w), 'home_primary': bounds(w.tv_play, w)})
                picture(prefix + '-home-long-missing-native-test')

                w.show_game(long_game); frame(w)
                panel = w.detail_row.get_parent()
                panel_bounds = bounds(panel, w)
                check(panel_bounds[2] <= 1140 and abs(panel_bounds[0] * 2 + panel_bounds[2] - width) <= 2, prefix + ' detail panel bounded and centered')
                check(w.cover.get_width() == (180 if width >= 1400 else 160), prefix + ' balanced detail cover')
                check(bounds(w.detail_primary, w)[2] >= 144, prefix + ' primary has deliberate minimum width')
                check(w.detail_backdrop.get_paintable() is None, prefix + ' missing detail clears backdrop')
                check(w.detail_row.get_width() <= panel.get_width(), prefix + ' long description stays in panel')
                # Text can make detail taller; every action remains reachable by native focus scrolling.
                w.detail_gear.grab_focus(); frame(w)
                ready(w, lambda: visible_in(w.detail_gear, w.detail_scroll), 'Detail options visible')
                check(visible_in(w.detail_primary, w.detail_scroll), prefix + ' action row visible after scroll')
                geometry[-1]['detail_panel'] = panel_bounds
                picture(prefix + '-detail-long-missing-native-test')

                w.routes['library'].update(query='', genre=None, page=1, scroll=0, focus=None)
                w.show_library(); frame(w)
                ready(w, lambda: len(w.collection_tiles) == len(original_games), 'All saved fixtures on one local Library page')
                last = list(w.collection_tiles.values())[-1]
                w.mark_browse_input(); last.grab_focus(); w.reveal_browse_control(last)
                ready(w, lambda: visible_in(last, w.collection_scroll), 'Last card revealed')
                check(w.focused_control(w) is last, prefix + ' missing-art card focus persists')
                check(visible_in(last, w.collection_scroll), prefix + ' complete card and caption visible')
                check(last.get_tooltip_text().startswith('View '), prefix + ' full card title remains available')
                picture(prefix + '-library-focus-native-test')
                search = w.collection_search
                search.grab_focus(); search.set_text('no matching fictional game'); search.set_position(3)
                check(not key(w, Gdk.KEY_Left) and not key(w, Gdk.KEY_Right), prefix + ' search caret keys remain native')
                w.collection_search_button.emit('clicked'); frame(w)
                check(not w.collection_tiles and '0 games' in w.collection_status.get_text(), prefix + ' empty search is readable')
                check(search.get_text() == 'no matching fictional game', prefix + ' empty search retains query')
                if width == 900:picture(prefix + '-empty-search-native-test')
                search.set_text(''); w.collection_search_button.emit('clicked'); frame(w)
                check(len(w.collection_tiles) == len(original_games), prefix + ' clearing search restores saved cards')
                check(library.games() == original_games, prefix + ' metadata and configuration unchanged')

        # Switching fullscreen and back restores the selected desktop palette and scopes.
        w.theme.set_selected(1)
        w.set_tv_mode(True); w.unfullscreen(); frame(w)
        check(not w.has_css_class('desktop-mode') and w.has_css_class('tv-mode'), 'Fullscreen has no desktop presentation scope')
        w.set_tv_mode(False); frame(w)
        check(w.has_css_class('desktop-mode') and not w.has_css_class('desktop-dark'), 'Returning to desktop restores light appearance')
        w.launcher.start.assert_not_called(); w.catalog.image_transport.assert_not_called()
        check(library.games() == original_games, 'All fixture games unchanged')
    finally:
        w.exiting = True; w.catalog_cancel()
        w.catalog_pool.shutdown(wait=True, cancel_futures=True); w.pool.shutdown(wait=True)
        w.controller.close(); w.destroy(); settle()
        assert runtime == {str(p.relative_to(args.source)): sha(p) for p in (args.source / 'game_library').glob('*.py')}
        (args.output / 'checks.json').write_text(json.dumps({'label': 'Synthetic native GTK test renders; fictional data; Play disabled; not live desktop screenshots', 'source_sha256': runtime, 'fixture_sha256': sha(Path(__file__)), 'checks': checks, 'geometry': geometry, 'images': images, 'saved_games_unchanged': library.games() == original_games}, indent=2) + '\n')
print('PASS', sum(c['passed'] for c in checks), '/', len(checks), 'native desktop presentation checks', flush=True)
