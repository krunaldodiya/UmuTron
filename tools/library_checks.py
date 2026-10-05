"""Isolated native Library filters and shared pagination, with no network."""
import argparse
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fullscreen_preview import settle, capture
from navigation_fixture import frame, ready, after_frames, visible_in
from catalog_fixtures import FixtureCatalog
from game_library.app import Application, Window
from game_library.demo import prepare_demo
from gi.repository import Adw, Gio, Gtk


def numbered(window):
    result = []; child = window.collection_numbers.get_first_child()
    while child:
        if isinstance(child, Gtk.Button): result.append(child)
        child = child.get_next_sibling()
    return result


parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='umutron-local-browse-') as temp:
    os.environ['XDG_CACHE_HOME'] = temp
    library = prepare_demo(True); seed = library.games()
    for i in range(217):
        game = deepcopy(seed[i % 3]); game.update(id=str(uuid4()), title=f'Voyage {i:03}',
                                                genres='Role-playing (RPG)' if i < 97 else 'Action, Adventure')
        library.save(game)
    provider = FixtureCatalog(); app = Application(demo=True)
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE); app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name = ''; controller.return_value.error = ''
        w = Window(app, library, demo=True, catalog_provider=provider)
    app.window = w; w.proton_manager.releases = lambda *a, **k: []
    w.catalog.image_transport = lambda *_: (_ for _ in ()).throw(OSError('no network in fixture'))
    w.present(); w.theme.set_selected(2); settle(600); w.navigation_window = lambda: w
    w.show_store(); settle(700)
    w.routes['store'].update(query='Remote query', genre=5, page=2)
    w.load_store(); settle(700); store_state = deepcopy(w.routes['store'])
    assert not w.last_page.get_visible() and [b.get_label() for b in numbered(w)] == ['2']
    w.show_library(); settle()
    before = library.path.read_bytes()
    with patch.object(w.catalog, 'genres') as genres, patch.object(w.catalog, 'browse') as browse, \
            patch.object(w.catalog, 'detail') as detail, patch.object(w.catalog, 'image') as image:
        # Search waits for explicit submission, like Store; typing keeps focus.
        w.collection_search.grab_focus(); w.collection_search.set_text('Voyage'); settle()
        assert w.routes['library']['query'] == ''
        w.collection_search.emit('activate'); settle()
        assert w.routes['library']['query'] == 'Voyage' and len(w.collection_tiles) == 48
        model = w.collection_genre.get_model()
        genre_index = next(i for i in range(model.get_n_items()) if model.get_string(i) == 'Role-playing (RPG)')
        w.collection_genre.set_selected(genre_index); settle()
        assert w.routes['library']['genre'] == 'role-playing (rpg)'
        assert w.collection_total_pages == 3 and '97 games' in w.collection_status.get_text()
        assert all(g['genres'] == 'Role-playing (RPG)' for g in w.tv_games)
        numbered(w)[1].emit('clicked'); frame(w); assert w.routes['library']['page'] == 2
        target = w.tv_games[15]; tile = w.collection_tiles[target['id']];tile.grab_focus()
        after_frames(w,lambda:visible_in(tile,w.collection_scroll),'Focused Library card is actually visible before opening detail')
        scroll = w.collection_scroll.get_vadjustment().get_value()
        assert scroll>0
        w.show_game(target); settle(); assert w.routes['library']['scroll']==scroll, ('capture',w.routes['library']['scroll'],scroll)
        w.return_from_detail(); frame(w)
        assert w.routes['library']['page'] == 2 and w.routes['library']['focus'] == target['id']
        adjustment=w.collection_scroll.get_vadjustment()
        ready(w,lambda:adjustment.get_page_size()>0 and abs(adjustment.get_value()-scroll)<2 and visible_in(w.collection_tiles[target['id']],w.collection_scroll),'Back restores actual Library scroll and visible focused card')
        assert abs(adjustment.get_value() - scroll) < 2, (scroll,adjustment.get_value(),adjustment.get_upper(),adjustment.get_page_size(),w.routes['library'])
        assert w.routes['store'] == store_state and library.path.read_bytes() == before
        # Last page has one result; removal must clamp and preserve both filters.
        w.last_page.emit('clicked'); settle(); assert len(w.collection_tiles) == 1
        w.show_game(w.tv_games[0]); w.remove_detail()
        prompt = next(d for d in Gtk.Window.get_toplevels() if isinstance(d, Adw.MessageDialog) and d.get_visible())
        prompt.emit('response', 'confirm'); prompt.close(); settle()
        assert w.routes['library']['page'] == 2 and w.collection_total_pages == 2
        assert len(w.collection_tiles) == 48 and w.routes['library']['genre'] == 'role-playing (rpg)'
        w.collection_search.set_text('No such title'); w.collection_search_button.emit('clicked'); settle()
        assert not w.collection_tiles and w.routes['library']['page'] == 1
        assert not w.first_page.is_sensitive() and not w.next_page.is_sensitive() and not w.last_page.is_sensitive()
        w.collection_search.set_text('Voyage'); w.collection_search.emit('activate'); settle()
        w.collection_genre.set_selected(0); settle()
        assert w.collection_total_pages == 5 and '216 games' in w.collection_status.get_text()
        settle(5000)  # let the removal toast expire before visual inspection
        w.set_tv_mode(True); assert w.tv_mode; w.unfullscreen(); settle(500)
        for width, height in ((1920, 1080), (1024, 600), (800, 640)):
            w.set_visible(False); w.unrealize(); w.set_size_request(width,height);w.set_default_size(width, height); w.present(); frame(w)
            assert (w.get_width(), w.get_height()) == (width, height), (width,height,w.get_width(),w.get_height())
            first=next(iter(w.collection_tiles.values()));first.grab_focus()
            after_frames(w,lambda:visible_in(first,w.collection_scroll),'Responsive Library focus is fully revealed')
            capture(w, args.output / f'library-{width}.png',remap=False)
            for control in (w.collection_search, w.collection_search_button, w.collection_genre,
                            w.first_page, w.last_page):
                ok, rect = control.compute_bounds(w)
                assert ok and rect.get_x() >= 0 and rect.get_x() + rect.get_width() <= width, (width, control)
            if height<700:
                _,title_rect=next(iter(w.collection_tiles.values())).console_title.compute_bounds(w)
                _,scroll_rect=w.collection_scroll.compute_bounds(w)
                assert title_rect.get_y()+title_rect.get_height()<=scroll_rect.get_y()+scroll_rect.get_height(), (width,'first title clipped')
        w.controller_action('pagedown'); settle(); assert w.routes['library']['page'] == 2
        w.controller_action('pageup'); settle(); assert w.routes['library']['page'] == 1
        assert w.tv_games[0]['title'] == 'Voyage 000'  # deterministic default order
        w.show_home(); settle(); assert not w.tv_games  # no fabricated play history
        w.show_library(); settle(); assert w.routes['library']['query'] == 'Voyage'
        for mock in (genres, browse, detail, image): mock.assert_not_called()
    # Store supports counted pages, a legacy unknown-total fallback, and the cap.
    w.set_tv_mode(False); w.show_store(restore=True); settle()
    w.set_visible(False); w.unrealize(); w.set_size_request(780,640);w.set_default_size(780,640);w.present();frame(w)
    capture(w,args.output/'store-desktop-780.png')
    assert w.routes['store']['query'] == 'Remote query' and w.routes['store']['genre'] == 5
    raw_browse = provider.browse
    def fixture_art(url,limit):
        index=int(url.split('fixture')[1].split('.')[0])
        return (library.art_dir/seed[index]['artwork']['portrait']).read_bytes()
    w.catalog.image_transport=fixture_art
    def counted(query='', genre=None, page=1):
        return {**raw_browse(query, genre, page), 'total_items': 72, 'total_pages': 3}
    with patch.object(provider, 'browse', side_effect=counted):
        w.load_store(); settle(700)
        assert w.last_page.get_visible() and w.last_page.is_sensitive()
        w.last_page.emit('clicked'); settle(700); assert w.routes['store']['page'] == 3
        assert not w.next_page.is_sensitive() and not w.last_page.is_sensitive()
        w.first_page.emit('clicked'); settle(700); assert w.routes['store']['page'] == 1
        w.set_tv_mode(True); w.unfullscreen(); w.set_visible(False); w.unrealize()
        w.set_size_request(1920,1080);w.set_default_size(1920, 1080); w.present(); frame(w)
        capture(w, args.output / 'store-numbered-1920.png')
    w.render_store({'items': [], 'page': 1000, 'has_next': False, 'cached': False,
                    'total_items': 24025, 'total_pages': 1002})
    assert not w.last_page.is_sensitive() and not w.next_page.is_sensitive()
    assert 'of 1002' in w.collection_page_label.get_text() and 'limited' in w.collection_page_label.get_text()
    w.render_store({'items': [], 'page': 2, 'has_next': True, 'cached': False})
    assert not w.last_page.get_visible() and [b.get_label() for b in numbered(w)] == ['2']
    assert w.first_page.is_sensitive() and w.next_page.is_sensitive()
    w.exiting = True; w.catalog_cancel(); w.catalog_pool.shutdown(wait=True, cancel_futures=True)
    w.pool.shutdown(wait=True); w.destroy(); app.quit()
print('PASS: local 220-entry filtering, independent state, bounded grid/pager, back/focus/scroll, removal clamp, offline provider isolation, responsive native layouts and Store totals/fallback.')
