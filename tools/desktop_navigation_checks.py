"""In-process key-controller/native-widget regression; no raw desktop input."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4

parser=argparse.ArgumentParser();parser.add_argument('--probe',action='store_true');parser.add_argument('--home-only',action='store_true');parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
if os.environ.get('GDK_BACKEND')!='broadway':raise SystemExit('Use an owned isolated Broadway display.')
sys.path.insert(0,str(args.source));sys.path.insert(0,str(args.source/'tools'))
from fullscreen_preview import settle,capture
from catalog_fixtures import FixtureCatalog
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library.play_history import record
from gi.repository import Adw,Gdk,Gio,Gtk


class LocalCatalog(FixtureCatalog):
    def detail(self,game_id):
        item=super().detail(game_id);item['images']={};return item


checks=[]
def check(condition,name):checks.append({'check':name,'passed':bool(condition)})
from navigation_fixture import key,frame,ready,visible_in


with tempfile.TemporaryDirectory(prefix='umutron-desktop-arrows-') as temporary:
    os.environ['XDG_CACHE_HOME']=temporary;library=prepare_demo(True);samples=library.games()
    for i in range(51):
        game=library.new_game();game.update(title=f'Fixture game {i:02}',executable=samples[0]['executable'],artwork=samples[0]['artwork'],setup_completed_at=10000+i);library.save(game)
    for i,game in enumerate(samples):record(library.root,game['id'],str(uuid4()),100+i)
    app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name='';controller.return_value.error=''
        w=Window(app,library,demo=True,catalog_provider=LocalCatalog())
    app.window=w;w.proton_manager.releases=lambda *a,**k:[];w.navigation_window=lambda:w
    w.set_size_request(1120,800);w.set_default_size(1120,800);w.present();settle(400)
    for child in w.layout:
        if isinstance(child,Adw.Banner):child.set_title('NATIVE TEST RENDER · keyboard fixture · Play disabled')
    w.theme.set_selected(2);before=library.path.read_bytes()
    try:
        for route,show in (('home',w.show_home),('library',w.show_library),('store',w.show_store)):
            if args.home_only and route!='home':continue
            show();settle(500);frame(w)
            w.home_nav.grab_focus();handled=key(w,Gdk.KEY_Right)
            check(handled and w.focused_control(w) is w.library_nav,route+': header Right reaches Library')
            key(w,Gdk.KEY_Right);check(w.focused_control(w) is w.store_nav,route+': header Right reaches Store')
            key(w,Gdk.KEY_Left);check(w.focused_control(w) is w.library_nav,route+': header Left returns')
            key(w,Gdk.KEY_Down)
            check(w.focused_control(w) is w.collection_search if route!='home' else w.focused_control(w) in [t for _,t in w.tv_tiles],route+': header Down enters search or Home cards')
            first=w.tv_tiles[0][1];first.grab_focus();frame(w)
            handled=key(w,Gdk.KEY_Right);settle(80)
            check(handled and w.focused_control(w) is w.tv_tiles[1][1],route+': card Right advances')
            key(w,Gdk.KEY_Left);check(w.focused_control(w) is first,route+': card Left returns')
            handled=key(w,Gdk.KEY_Down);settle(150)
            expected=w.home_setup_tiles if route=='home' else w.tv_tiles
            check(handled and w.focused_control(w) in [t for _,t in expected] and w.focused_control(w) is not first,route+': card Down reaches next row/section')
            chosen=w.focused_control(w)
            check(not key(w,Gdk.KEY_Tab),route+': Tab remains native')
            check(not key(w,Gdk.KEY_Left,Gdk.ModifierType.CONTROL_MASK) and w.focused_control(w) is chosen,route+': modified arrows remain native')
            if args.probe:continue
            if route=='home':
                check(w.tv_page.get_vadjustment().get_value()>0,'Home: setup focus scrolls into view')
                chosen_id=w.tv_selected_id
                for repeat in range(3):
                    w.show_game(w.tv_selected_game());settle();w.return_from_detail()
                    def home_restored():
                        tile=next((t for gid,t in w.home_setup_tiles if gid==chosen_id),None)
                        return w.route=='home' and w.home_focus_section=='setup' and tile is not None and w.focused_control(w) is tile and visible_in(tile,w.tv_page)
                    ready(w,home_restored,'Home exact setup card after Back')
                    check(home_restored(),f'Home: Back {repeat+1} restores exact setup card and visibility')
            else:
                # Exercise nonzero scrolling before returning from detail.
                key(w,Gdk.KEY_Down);key(w,Gdk.KEY_Down);chosen=w.focused_control(w)
                ready(w,lambda:visible_in(chosen,w.collection_scroll),route+' focused card scroll')
                identity=next(i for i,t in w.tv_tiles if t is chosen)
                for repeat in range(3):
                    saved_scroll=w.collection_scroll.get_vadjustment().get_value()
                    chosen=w.collection_tiles[identity];chosen.activate()
                    ready(w,lambda:w.route=='detail',route+' detail activation')
                    check(w.route=='detail',route+': native card activation opens detail')
                    w.return_from_detail()
                    def restored():
                        tile=w.collection_tiles.get(identity)
                        return (w.route==route and w.routes[route]['focus']==identity and tile is not None
                                and w.focused_control(w) is tile and visible_in(tile,w.collection_scroll)
                                and abs(w.collection_scroll.get_vadjustment().get_value()-saved_scroll)<1)
                    ready(w,restored,route+' exact card and saved scroll after Back')
                    check(restored(),f'{route}: Back {repeat+1} restores exact card and scroll')
                # Switch away and return through the real header callbacks.
                w.home_nav.emit('clicked');ready(w,lambda:w.route=='home' and bool(w.home_setup_tiles),'route switch to Home')
                (w.library_nav if route=='library' else w.store_nav).emit('clicked')
                ready(w,restored,route+' route return focus/scroll')
                check(restored(),route+': route switch restores exact card and scroll')
                w.collection_search.grab_focus();w.collection_search.set_text('fixture caret text');settle(50)
                page=w.routes[route]['page'];focus=w.get_focus()
                for value in (Gdk.KEY_Left,Gdk.KEY_Right,Gdk.KEY_Up,Gdk.KEY_Down,Gdk.KEY_Page_Up,Gdk.KEY_Page_Down):
                    check(not key(w,value) and w.get_focus() is focus and w.routes[route]['page']==page,route+': input key '+str(value)+' not intercepted')
                w.collection_search.set_text('');w.collection_genre.grab_focus();settle(50)
                check(key(w,Gdk.KEY_Down) and w.focused_control(w) in w.collection_tiles.values(),route+': closed Filter moves to cards')
                w.tv_tiles[0][1].grab_focus();key(w,Gdk.KEY_Page_Down);settle(450);frame(w)
                check(w.routes[route]['page']==2,route+': PageDown advances page')
                key(w,Gdk.KEY_Page_Up);settle(450);frame(w)
                check(w.routes[route]['page']==1,route+': PageUp returns')
            capture(w,args.output/(route+'-desktop-test.png'))

        if not args.probe and not args.home_only:
            w.show_library();frame(w);w.tv_tiles[0][1].grab_focus()
            modal=Adw.Window(transient_for=w,modal=True,title='Inert modal');modal.set_content(Gtk.Entry());modal.present();settle()
            page=w.routes['library']['page'];focus=w.focused_control(w)
            for value in (Gdk.KEY_Right,Gdk.KEY_Page_Down,Gdk.KEY_F11):
                check(not key(w,value) and w.routes['library']['page']==page and w.focused_control(w) is focus,'Modal prevents background key '+str(value))
            modal.destroy();settle()
            pop=Gtk.Popover();pop.set_parent(w.library_nav);pop.set_child(Gtk.Button(label='Inert popup action'));pop.popup();settle()
            check(not key(w,Gdk.KEY_Right) and not key(w,Gdk.KEY_Page_Down),'Popover keeps arrows/pagination inside native surface')
            pop.popdown();pop.unparent();settle()
            w.show_game(samples[0]);settle();w.open_manage();settle()
            w.fields['executable'].grab_focus()
            check(not key(w,Gdk.KEY_Right),'Setup editor receives its native keys');w.cancel_editor();settle()

            # Repeated desktop/fullscreen changes retain existing controller behavior.
            for _ in range(2):
                w.show_library();key(w,Gdk.KEY_F11);settle();check(w.tv_mode,'F11 enters fullscreen layout')
                w.tv_library_tab.grab_focus();key(w,Gdk.KEY_Right);check(w.focused_control(w) is w.tv_games_tab,'Fullscreen header arrows unchanged')
                w.set_tv_mode(False);settle();w.home_nav.grab_focus();key(w,Gdk.KEY_Right)
                check(not w.tv_mode and w.focused_control(w) is w.library_nav,'Desktop arrows work after mode return')
            w.set_size_request(900,650);w.set_default_size(900,650);w.show_library();frame(w)
            w.tv_tiles[0][1].grab_focus();key(w,Gdk.KEY_Right)
            check(w.focused_control(w) is w.tv_tiles[1][1],'Resized desktop grid retains horizontal navigation')
            check(library.path.read_bytes()==before,'No game metadata changed')
    finally:
        w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True);w.controller.close();w.destroy();settle()
record={'source':str(args.source),'app_sha256':hashlib.sha256((args.source/'game_library/app.py').read_bytes()).hexdigest(),'checks':checks,'capture':'Isolated native test render, not live desktop','input':'In-process Gtk.EventControllerKey signal and native widget focus/activation, no hardware keyboard/controller exercised','real_games_or_installers':0}
(args.output/'checks.json').write_text(json.dumps(record,indent=2)+'\n')
for c in checks:
    if not c['passed']:print('FAIL: '+c['check'])
print(f'{sum(c["passed"] for c in checks)}/{len(checks)} native assertions passed')
assert all(c['passed'] for c in checks)
