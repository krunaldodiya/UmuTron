"""Isolated native fixture: 205+ games, paged Store and shared detail navigation."""
import argparse
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullscreen_preview import settle,capture
from navigation_fixture import frame,ready
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library.play_history import recent,record
from gi.repository import Gio,Gdk


from catalog_fixtures import FixtureCatalog


parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='umutron-catalog-ui-') as temp:
    os.environ['XDG_CACHE_HOME']=temp
    library=prepare_demo(True);seed=library.games()
    for i in range(205):
        game=deepcopy(seed[i%3]);game['id']=str(uuid4());game['title']=f'Library game {i+1:03}';library.save(game)
    assert recent(library)==[]
    provider=FixtureCatalog()
    app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller'):
        w=Window(app,library,demo=True,catalog_provider=provider)
    w.controller.name=''
    def art(url,limit):
        index=int(url.split('fixture')[1].split('.')[0]);kind='portrait' if 'cover_big' in url else 'hero'
        return (library.art_dir/seed[index]['artwork'][kind]).read_bytes()
    w.catalog.image_transport=art;w.proton_manager.releases=lambda *a,**k:[]
    app.window=w;w.show_library();w.present();w.theme.set_selected(2);settle(800)
    assert len(w.collection_tiles)==48
    for _ in range(3):assert w.on_key(None,Gdk.KEY_Page_Down,0,0)
    settle();assert w.routes['library']['page']==4
    target=next(g for g in w.tv_games if g['title']=='Library game 175')
    w.collection_tiles[target['id']].grab_focus();settle();w.show_game(target);settle()
    assert w.saved_detail() and w.route=='detail'
    w.return_from_detail();settle();assert w.routes['library']['page']==4
    assert w.routes['library']['focus']==target['id']
    capture(w,args.output/'library-page-4-desktop.png')
    w.show_store();settle(1800);assert len(w.collection_tiles)==24
    capture(w,args.output/'store-desktop.png')
    w.collection_page(1);settle(1200);assert w.routes['store']['page']==2
    w.open_catalog_item(provider.detail(25));settle(1500)
    assert not w.saved_detail();capture(w,args.output/'store-detail-before-add.png')
    count=len(library.games());w.detail_action();w.detail_action();settle(800)
    assert w.saved_detail() and len(library.games())==count+1
    assert recent(library)==[]
    saved=deepcopy(w.game);w.return_from_detail();settle()
    assert w.route=='store' and w.routes['store']['page']==2
    w.open_catalog_item(provider.detail(25));settle()
    assert w.game==saved;capture(w,args.output/'shared-detail-saved.png')
    w.show_home();settle();assert not w.tv_games
    capture(w,args.output/'home-empty-desktop.png')
    record(library.root,saved['id'],str(uuid4()),100)
    w.show_home();settle();assert [g['id'] for g in w.tv_games]==[saved['id']]
    capture(w,args.output/'home-desktop.png')
    w.set_tv_mode(True);w.unfullscreen();w.set_visible(False);w.unrealize();w.set_size_request(1920,1080);w.set_default_size(1920,1080);w.present();frame(w)
    ready(w,lambda:(w.get_width(),w.get_height())==(1920,1080),'Catalog fullscreen fixture allocation');capture(w,args.output/'home-played-fullscreen.png')
    w.show_library();settle();w.navigation_window=lambda:w
    w.controller_action('pageup');settle();assert w.routes['library']['page']==3
    w.controller_action('pagedown');settle();assert w.routes['library']['page']==4
    capture(w,args.output/'library-fullscreen.png')
    w.show_game(saved);settle();capture(w,args.output/'shared-detail-fullscreen.png')
    w.go_back();settle();assert w.route=='library'
    w.show_store();settle(1000);provider.offline=True;w.load_store();settle(1000)
    assert 'Offline' in w.collection_status.get_text();capture(w,args.output/'store-offline-fullscreen.png')
    w.set_tv_mode(False);w.set_visible(False);w.unrealize();w.set_size_request(780,640);w.set_default_size(780,640);w.present();frame(w)
    ready(w,lambda:(w.get_width(),w.get_height())==(780,640),'Catalog compact fixture allocation');capture(w,args.output/'store-small.png')
    w.show_game(saved);settle();capture(w,args.output/'detail-small.png')
    w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.destroy();app.quit()
    print('Catalog native checks passed: 208+ entries, page navigation, shared details, add membership, recent history and offline cache.')
