"""Native GTK behavior only, no browser allocation/pixel or hardware-input claim."""
import os
from pathlib import Path
import sys
from unittest.mock import Mock,patch
from uuid import uuid4

SOURCE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SOURCE),str(SOURCE/'tests'),str(SOURCE/'tools')]
if os.environ.get('GDK_BACKEND')!='broadway':raise SystemExit('Use an isolated Broadway fixture only.')
from catalog_fixtures import FixtureCatalog
from fullscreen_preview import settle
from game_library.app import Application,Window
from game_library.library import Library
from game_library.play_history import record
from test_setup_save import SetupSaveTests
from gi.repository import Gio,Gtk


def children(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from children(child);child=child.get_next_sibling()


fixture=SetupSaveTests();fixture.setUp();lib=fixture.library
app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
with patch('game_library.app.Controller') as controller:
    controller.return_value.name='';controller.return_value.error=''
    w=Window(app,lib,demo=True,catalog_provider=FixtureCatalog())
app.window=w;w.navigation_window=lambda:w
w.launcher.start=Mock(side_effect=AssertionError('No execution in this fixture'))
w.proton_manager.releases=lambda *_a,**_k:[];w.error=Mock();w.present()
try:
    w.show_game(fixture.game);w.open_manage()
    w.fields['executable'].set_text(str(fixture.exe));w.fields['working_dir'].set_text(str(fixture.exe.parent))
    with patch('game_library.setup_history.time.time',return_value=100):w.editor_save.emit('clicked')
    w.error.assert_not_called();saved=lib.games()[0]
    assert saved['setup_completed_at']==100 and saved['installation']['confirmed']
    assert saved['installer_attempt']['executable']==str(fixture.installer.resolve())
    assert w.detail_primary.get_label()=='Play'
    w.open_manage()
    with patch('game_library.setup_history.time.time',return_value=200):w.editor_save.emit('clicked')
    assert lib.games()[0]['setup_completed_at']==100
    legacy=lib.new_game();legacy.update(title='Existing undated setup',executable=str(fixture.exe));lib.save(legacy)
    metadata=lib.new_game();metadata['title']='Metadata only';lib.save(metadata)
    gone=lib.new_game();gone.update(title='Disconnected setup',executable=str(fixture.exe))
    with patch('game_library.setup_history.time.time',return_value=300):gone=lib.save_setup(gone)
    gone['executable']=str(fixture.root/'unmounted/game.exe');lib.save(gone)
    before=lib.path.read_bytes();w.set_tv_mode(True);w.show_home();w.refresh_launch_state()
    assert not w.tv_games
    assert [g['id'] for g in w.home_setup_games]==[gone['id'],saved['id']]
    assert metadata['id'] not in [g['id'] for g in w.home_setup_games]
    assert 'Files unavailable' in w.home_setup_tiles[0][1].get_tooltip_text()
    assert any(g['id']==legacy['id'] and 'setup_completed_at' not in g for g in lib.games())
    tile=next(t for gid,t in w.home_setup_tiles if gid==saved['id'])
    w.select_home_tile(saved,tile);w.refresh_launch_state();assert w.tv_play.get_label()=='Play' and not w.tv_launch_status.get_text()
    w.show_game(saved);w.return_from_detail();assert w.route=='home' and w.home_focus_section=='setup' and w.tv_selected_id==saved['id']
    assert not hasattr(w,'tv_search') and not hasattr(w,'search_library')
    assert not any(isinstance(c,Gtk.SearchEntry) for c in children(w.tv_controls))
    # Synthetic observed-play records stay separate from setup chronology.
    record(lib.root,saved['id'],str(uuid4()),400);w.refresh_launch_state();settle(30)
    assert [g['id'] for g in w.tv_games]==[saved['id']]
    record(lib.root,legacy['id'],str(uuid4()),500)
    w.navigation_window=lambda:None;w.refresh_launch_state();assert len(w.tv_games)==1
    w.navigation_window=lambda:w;w.refresh_launch_state();assert [g['id'] for g in w.tv_games]==[legacy['id'],saved['id']]
    assert w.tv_selected_id==saved['id'] and w.home_focus_section=='setup'
    rail=w.tv_rail;w.refresh_launch_state();assert w.tv_rail is rail
    # Route filters remain independent after global Search removal.
    w.show_library();w.collection_search.set_text(saved['title']);w.collection_search.emit('activate');settle(30)
    assert w.routes['library']['query']==saved['title'] and len(w.collection_tiles)==1
    w.show_store();settle(150);w.collection_search.set_text('Fixture game 010');w.collection_search.emit('activate');settle(150)
    assert w.routes['store']['query']=='Fixture game 010'
    w.show_library();assert w.collection_search.get_text()==saved['title']
    w.show_store(restore=True);assert w.collection_search.get_text()=='Fixture game 010'
    w.library=Library(lib.root);w.show_home()
    assert [g['id'] for g in w.tv_games]==[legacy['id'],saved['id']]
    assert lib.path.read_bytes()==before
    # The alignment composition is unchanged; these are widget properties,
    # not measured action-row geometry or rendered screenshots.
    w.show_game(saved)
    info=next(c for c in children(w.body) if isinstance(c,Gtk.Button) and c.get_label()=='Game Info')
    assert all(c.get_valign()==Gtk.Align.CENTER for c in (w.detail_primary,w.detail_gear,info))
    for mode in (False,True):
        w.set_tv_mode(mode);w.show_game(saved)
        w.launcher.start.assert_not_called()
    print('PASS: native confirmed Save stamps once; hotfix identity retained; ready/undated/unavailable Home groups; metadata exclusion; Back restores section/selection; async observed-play refresh/modal deferral; removed global Search and scoped route filters; reload and centered action properties. No execution.',flush=True)
    print('LIMIT: no current rendered frame or viewport geometry; no keyboard hardware or gamepad input claim.',flush=True)
finally:
    if w.editor:w.cancel_editor()
    w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True);w.destroy();app.quit();fixture.doCleanups()
