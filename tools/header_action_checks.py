"""Isolated native layout/search checks. Only inert fixtures; no launch actions."""
import argparse
# Explicit fixture minima prevent the default 1024x768 Broadway monitor from
# clamping a requested test viewport. Native size/bounds assertions stay intact.
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullscreen_preview import settle,capture
from catalog_fixtures import FixtureCatalog
from game_library.app import Application,Window
from game_library.catalog import item_game
from game_library.demo import prepare_demo
from gi.repository import Adw,Gio,Gtk


def descendants(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from descendants(child)
        child=child.get_next_sibling()


def bounds(widget,window):
    ok,rect=widget.compute_bounds(window)
    assert ok and rect.get_width()>0 and rect.get_height()>0,'Unallocated native control'
    return [rect.get_x(),rect.get_y(),rect.get_width(),rect.get_height()]


def aligned(window):
    info=next(c for c in descendants(window.body) if isinstance(c,Gtk.Button) and c.get_label()=='Game Info')
    controls=[window.detail_primary,info]
    if window.detail_gear.get_visible():controls.insert(1,window.detail_gear)
    boxes=[bounds(c,window) for c in controls]
    centers=[r[1]+r[3]/2 for r in boxes]
    assert max(centers)-min(centers)<=1,(window.detail_primary.get_label(),boxes)
    assert all(a[0]+a[2]<=b[0] for a,b in zip(boxes,boxes[1:])),boxes
    assert all(r[0]>=0 and r[0]+r[2]<=window.get_width() for r in boxes),boxes
    return boxes


parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--baseline',action='store_true')
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='umutron-header-action-') as temp:
    os.environ['XDG_CACHE_HOME']=temp;library=prepare_demo(True);seed=deepcopy(library.games()[0]);provider=FixtureCatalog()
    app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name='';controller.return_value.error=''
        w=Window(app,library,demo=True,catalog_provider=provider)
    app.window=w;w.present();w.theme.set_selected(2);settle(400)
    w.catalog.image_transport=lambda *_:(_ for _ in ()).throw(OSError('Offline fixture'))
    for child in w.layout:
        if isinstance(child,Adw.Banner):child.set_title('NATIVE TEST RENDER · synthetic games · Play disabled')
    real_launcher=w.launcher;results=[]
    class Active:
        def current(self):return {'game_id':seed['id'],'state':'Running','operation':'play','title':'Fixture'}
        def active(self):return True
        def snapshot(self,_):return {'logs':[]}
    try:
        sizes=((True,1920,1080),(True,1280,720),(True,1024,600),(False,1120,800),(False,640,540))
        for tv,width,height in sizes:
            w.set_tv_mode(tv);w.unfullscreen();settle(150);w.set_visible(False);w.unrealize();w.set_default_size(width,height);w.set_size_request(width,height);w.present();settle(500)
            for variant in ('short','long-missing'):
                game=deepcopy(seed)
                if variant=='short':game.update(title='Orbit',description='A short adventure.',genres='Adventure',developers='',publishers='')
                else:game.update(title='A Very Long Game Title With An Extended Definitive Edition Name',artwork={},description=('Explore a distant world with your companions. '*9),genres='Adventure · Role-playing · Exploration',developers='The Long Name Studio',publishers='The Long Name Studio · Another Publisher')
                for state in ('Play','Setup','Add','Stop'):
                    w.launcher=real_launcher;w.demo=True;configured=deepcopy(game)
                    if state=='Setup':configured['executable']='';configured['working_directory']=''
                    library.save(configured)
                    if state=='Add':
                        item=provider.detail(1);preview=item_game(item,preview=True)
                        preview.update({k:configured[k] for k in ('title','description','genres','developers','publishers','artwork')})
                        w.show_shared_detail(preview,item)
                    else:
                        if state=='Stop':w.launcher=Active()
                        w.show_game(configured)
                    w.refresh_launch_state();settle(150)
                    path=args.output/f'{"fullscreen" if tv else "desktop"}-{width}-{variant}-{state.lower()}.png'
                    capture(w,path)
                    # Compact windows intentionally scroll; expose the action row as a user can.
                    adjustment=w.detail_scroll.get_vadjustment()
                    if adjustment.get_upper()>adjustment.get_page_size():
                        adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());settle(100);capture(w,path)
                    assert (w.get_width(),w.get_height())==(width,height)
                    expected=('Open desktop Setup' if tv else 'Setup') if state=='Setup' else ('Add to library' if state=='Add' else state)
                    assert w.detail_primary.get_label()==expected,(expected,w.detail_primary.get_label())
                    assert w.detail_size.get_label()=='Installation size · Unknown'
                    assert w.detail_size.get_visible() and w.detail_primary.get_label()!='Install'
                    boxes=aligned(w)
                    viewport=bounds(w.detail_scroll,w)
                    assert all(r[1]>=viewport[1] and r[1]+r[3]<=viewport[1]+viewport[3] for r in boxes),(boxes,viewport)
                    results.append({'mode':'fullscreen' if tv else 'desktop','size':[width,height],'variant':variant,'state':state,'bounds':boxes})
                    if args.baseline:raise AssertionError('Baseline unexpectedly aligned')
                    # Focus stays on an actionable control across an actual responsive resize.
                    if state=='Setup':
                        w.detail_gear.grab_focus();w.detail_responsive(w.detail_row,None)
                        assert w.focused_control(w) is w.detail_gear
        w.launcher=real_launcher;w.demo=True;library.save(seed)
        w.set_tv_mode(True);w.unfullscreen();w.show_home();settle(300)
        assert not hasattr(w,'tv_search') and not hasattr(w,'search_library')
        assert all(not isinstance(c,Gtk.SearchEntry) for c in descendants(w.tv_controls))
        w.navigation_window=lambda:w
        w.tv_games_tab.grab_focus();w.controller_action('right');assert w.focused_control(w) is w.tv_menu
        w.controller_action('left');assert w.focused_control(w) is w.tv_games_tab
        w.tv_menu.grab_focus();w.controller_action('right');assert w.focused_control(w) is w.tv_menu
        w.show_library();settle();w.collection_search.set_text(seed['title']);w.collection_search.emit('activate');settle()
        assert w.routes['library']['query']==seed['title'] and len(w.collection_tiles)==1
        w.show_store();settle(600);w.collection_search.set_text('Fixture game 010');w.collection_search.emit('activate');settle(600)
        assert w.routes['store']['query']=='Fixture game 010'
        w.show_home();settle();assert {g['id'] for g in w.home_setup_games}=={g['id'] for g in library.games() if g.get('setup_completed_at')}
        w.show_library();settle();assert w.collection_search.get_text()==seed['title'] and len(w.collection_tiles)==1
        w.show_store(restore=True);settle(600);assert w.collection_search.get_text()=='Fixture game 010'
        capture(w,args.output/'scoped-store-search.png')
        w.show_home();capture(w,args.output/'home-header.png')
        (args.output/'geometry.json').write_text(json.dumps(results,indent=2)+'\n')
    finally:
        w.launcher=real_launcher;w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True);w.destroy();app.quit()
print('PASS: 40 native action-row geometries, Add/Setup/Play/Stop, title/art variants, five viewports, header focus and independent route search state.')
