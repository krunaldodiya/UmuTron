"""Native mode/ownership/install actions; no download, game or installer runs."""
import argparse
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullscreen_preview import settle,capture
from catalog_fixtures import FixtureCatalog
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library.catalog import item_game
from gi.repository import Gio,Gtk


def menu_labels(window):
    menu=window.detail_gear.get_popover().get_child();labels=[];child=menu.get_first_child()
    while child:
        if isinstance(child,Gtk.Button):labels.append(child.get_label())
        child=child.get_next_sibling()
    return labels


parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='umutron-detail-actions-') as temp:
    os.environ['XDG_CACHE_HOME']=temp;library=prepare_demo(True);installed=library.games()[0]
    uninstalled=library.new_game();uninstalled.update(title='Nebula Drift · awaiting install',artwork=deepcopy(installed['artwork']),description='Fictional saved game. Automatic downloads are unavailable in this fixture.');library.save(uninstalled)
    provider=FixtureCatalog();app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name='';controller.return_value.error=''
        w=Window(app,library,demo=True,catalog_provider=provider)
    app.window=w;w.present();settle(600);w.theme.set_selected(2)
    w.catalog.image_transport=lambda *_:(_ for _ in ()).throw(OSError('fixture no network'))
    before=library.path.read_bytes()
    for fullscreen in (False,True):
        w.set_tv_mode(fullscreen);w.unfullscreen();settle(300)
        w.show_shared_detail(item_game(provider.detail(1),preview=True),provider.detail(1));settle()
        assert not w.saved_detail() and w.detail_primary.get_label()=='Link a game'
        w.show_game(uninstalled);settle();w.demo=False;w.refresh_launch_state()
        assert w.detail_primary.get_label()=='Link a game' and w.detail_primary.get_sensitive()
        assert menu_labels(w)==['Remove from library','Add Installed Game…','Restore game backup…','Game Info','Search links']
        if fullscreen:
            w.set_visible(False);w.unrealize();w.set_default_size(1920,1080);w.set_size_request(1920,1080);w.present();settle(700)
            capture(w,args.output/'detail-primary-add-1920.png')
        else:
            capture(w,args.output/'detail-primary-add-desktop.png')
        assert library.path.read_bytes()==before and w.game['id']==uninstalled['id']
        w.demo=True
        w.show_game(installed);settle()
        assert w.detail_primary.get_label()=='Play'
        assert 'Relink Installed Game…' in menu_labels(w)
        assert 'Remove from library' in menu_labels(w) and 'Uninstall…' in menu_labels(w)
        incomplete=deepcopy(installed);incomplete['installation']={'mode':'installer','confirmed':False}
        library.save(incomplete);w.show_game(incomplete);settle()
        assert w.detail_primary.get_label()=='Link a game' and 'Uninstall…' not in menu_labels(w)
        library.save(installed)
    class Launch:
        record={'game_id':installed['id'],'state':'Running','operation':'play','title':'Fixture'}
        def current(self):return self.record
        def active(self):return bool(self.record)
        def snapshot(self,_):return {'logs':[]}
    real=w.launcher;w.launcher=Launch();w.demo=False;w.show_game(installed);w.refresh_launch_state()
    assert w.detail_primary.get_label()=='Stop' and w.detail_primary.get_sensitive()
    w.show_game(uninstalled);w.refresh_launch_state();assert not w.detail_primary.get_sensitive()
    w.launcher=real;w.demo=True;assert library.path.read_bytes()==before
    w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True);w.destroy();app.quit()
print('PASS: game detail exposes Add Installed Game, relinking, per-game backup restore, and Play/Stop guards without automatic installation.')
