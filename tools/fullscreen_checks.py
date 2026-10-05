"""Native route, async cancellation, focus and launch-state fixture regression checks."""
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
from unittest.mock import patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullscreen_preview import settle,capture
from catalog_fixtures import FixtureCatalog
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library.play_history import record
from gi.repository import Adw,Gio,Gtk


def widgets(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from widgets(child);child=child.get_next_sibling()


with tempfile.TemporaryDirectory(prefix='umutron-route-checks-') as temp:
    os.environ['XDG_CACHE_HOME']=temp
    library=prepare_demo(True);provider=FixtureCatalog();app=Application(demo=True)
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name='';controller.return_value.error=''
        w=Window(app,library,demo=True,catalog_provider=provider)
    app.window=w;w.present();settle()
    w.catalog.image_transport=lambda *_:(_ for _ in ()).throw(OSError('fixture missing artwork'))
    original=library.games()[0];selection=library.games()[-1];before=library.path.read_bytes()
    # Back cancels late catalog details; neither callback nor canceled Add saves.
    w.show_store();settle();entered=Event();release=Event();detail=provider.detail
    def delayed(identity):
        entered.set()
        if not release.wait(5):raise RuntimeError('Fixture release timed out')
        return detail(identity)
    with patch.object(provider,'detail',side_effect=delayed):
        w.open_catalog_item(detail(1));assert entered.wait(2)
        assert not w.detail_primary.get_sensitive()
        w.return_from_detail();release.set();settle(800)
        assert w.route=='store' and library.path.read_bytes()==before
    # A late browse cannot repaint Library, and genre-model replacement keeps selection.
    entered.clear();release.clear();browse=provider.browse
    def delayed_browse(*args):
        entered.set()
        if not release.wait(5):raise RuntimeError('Fixture release timed out')
        return browse(*args)
    with patch.object(provider,'browse',side_effect=delayed_browse):
        w.load_store();assert entered.wait(2);w.show_library();release.set();settle(800)
        assert w.route=='library' and len(w.collection_tiles)==3
    w.show_store();settle(800);w.collection_genre.set_selected(1);settle(800)
    assert w.routes['store']['genre']==provider.genres()[0]['id'] and w.collection_genre.get_selected()==1
    # Leaving while Add fetches artwork cancels the pending membership write.
    w.open_catalog_item(detail(27));settle(800);entered.clear();release.clear()
    def delayed_art(_):
        entered.set()
        if not release.wait(5):raise OSError('Fixture timeout')
        raise OSError('Fixture unavailable art')
    with patch.object(w.catalog,'image',side_effect=delayed_art):
        w.detail_action();w.detail_action();assert entered.wait(2)
        w.return_from_detail();release.set();settle(800)
        assert w.route=='store' and library.path.read_bytes()==before
    # Existing Setup remains separate; modal cancellation preserves library bytes.
    w.show_game(original);w.open_manage();assert w.proton_choice and not hasattr(w,'prefix_panel')
    w.cancel_editor();assert library.path.read_bytes()==before
    w.remove_detail();prompt=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_visible())
    assert prompt.get_default_response()=='cancel';next(b for b in widgets(prompt) if isinstance(b,Gtk.Button) and b.get_label()==prompt.get_response_label('cancel')).emit('clicked');settle()
    assert library.path.read_bytes()==before
    for index,game in enumerate(library.games()):record(library.root,game['id'],str(uuid4()),100+index)
    w.show_home();w.set_tv_mode(True);w.unfullscreen();w.set_visible(False);w.unrealize();w.set_default_size(1024,600);w.present();settle()
    w.navigation_window=lambda:w
    w.select_tv_game(selection);w.focus_tv_card(False);settle()
    assert w.tv_eyebrow.get_text()=='RECENTLY PLAYED'
    w.show_game(selection);w.go_back();settle()
    assert w.route=='home' and w.home_selected_id==selection['id']
    w.show_library();settle();w.collection_tiles[original['id']].grab_focus();w.show_home();settle()
    assert w.home_selected_id==selection['id']
    w.tv_home_tab.grab_focus();w.controller_action('right');assert w.focused_control(w) is w.tv_library_tab
    w.controller_action('right');assert w.focused_control(w) is w.tv_games_tab
    # Missing artwork must clear the previous game's scene.
    missing=library.new_game();missing['title']='Missing artwork';library.save(missing);w.show_game(missing);settle()
    assert w.backdrop.get_paintable() is None and w.detail_backdrop.get_paintable() is None
    assert not any(isinstance(item,(Gtk.Entry,Gtk.DropDown)) for item in widgets(w.body))
    class LaunchFixture:
        record={};stops=[]
        def current(self):return self.record
        def active(self):return bool(self.record)
        def snapshot(self,_):return {'logs':[]}
        def stop(self,identity):self.stops.append(identity)
    launch=LaunchFixture();w.launcher=launch;w.demo=False;w.show_game(selection)
    launch.record={'game_id':selection['id'],'title':selection['title'],'state':'Running','supervisor_pid':1,'operation':'play'}
    w.refresh_launch_state();assert w.detail_primary.get_label()=='Stop'
    w.detail_primary.emit('clicked');prompt=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_visible());next(b for b in widgets(prompt) if isinstance(b,Gtk.Button) and b.get_label()==prompt.get_response_label('cancel')).emit('clicked')
    assert not launch.stops
    w.show_game(original);assert not w.detail_primary.get_sensitive()
    launch.record={};w.refresh_launch_state();w.demo=True;settle()
    valid,bounds=w.detail_primary.compute_bounds(w)
    assert valid and bounds.get_y()+bounds.get_height()<=w.get_height(),(bounds.get_y(),bounds.get_height(),w.get_height())
    capture(w,Path(temp)/'small-detail.png')
    # Long detail scrolling supports existing controller page actions.
    content=w.detail_scroll.get_child().get_child();content.append(Gtk.Label(label='Long fixture information\n'*100));settle()
    adjustment=w.detail_scroll.get_vadjustment();w.controller_action('pagedown');settle();assert adjustment.get_value()>0
    w.controller_action('pageup');settle();assert adjustment.get_value()==0
    w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True);w.controller.close();w.destroy();app.quit()
print('PASS: stale detail/browse callbacks, genre state, cancel preservation, separate Setup, recent Home focus, keyboard/controller navigation, missing art, small detail action, scrolling and Play/Stop guard')
