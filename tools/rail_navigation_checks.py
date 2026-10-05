"""Long Home rail regression: both axes, reversals and stale native callbacks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4

parser=argparse.ArgumentParser()
parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--size',default='900x600')
parser.add_argument('--mode',choices=('desktop','fullscreen'),default='desktop')
parser.add_argument('--probe',action='store_true')
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
if os.environ.get('GDK_BACKEND')!='broadway':raise SystemExit('Use an isolated native Broadway fixture only.')
sys.path[:0]=[str(args.source),str(args.source/'tools')]
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library.play_history import record
from catalog_fixtures import FixtureCatalog
from navigation_fixture import key,frame,ready,after_frames,visible_in
from fullscreen_preview import settle,capture
from gi.repository import Adw,Gdk,Gio,Gtk

checks=[]
def check(value,name):
    checks.append({'check':name,'passed':bool(value)})
    if not value and not args.probe:raise AssertionError(name)

def horizontal(tile,scroll):
    valid,bounds=tile.compute_bounds(scroll)
    return valid and bounds.get_x()>=-1 and bounds.get_x()+bounds.get_width()<=scroll.get_width()+1

def bounds(tile,scroll):
    valid,rect=tile.compute_bounds(scroll)
    return [rect.get_x(),rect.get_y(),rect.get_width(),rect.get_height()] if valid else None

with tempfile.TemporaryDirectory(prefix='umutron-long-rail-') as tmp:
    os.environ['XDG_CACHE_HOME']=tmp;library=prepare_demo(True);sample=library.games()[0]
    for index in range(21):
        game=library.new_game();game.update(title=f'Recent fixture {index:02}',executable=sample['executable'],artwork=sample['artwork'],setup_completed_at=1000+index);library.save(game)
    for index,game in enumerate(library.games()):record(library.root,game['id'],str(uuid4()),2000+index)
    before=library.games();app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name='';controller.return_value.error='';w=Window(app,library,demo=True,catalog_provider=FixtureCatalog())
    app.window=w;w.navigation_window=lambda:w;w.proton_manager.releases=lambda *a,**k:[]
    w.theme.set_selected(2);w.set_tv_mode(args.mode=='fullscreen');w.unfullscreen();w.set_visible(False);w.unrealize()
    width,height=map(int,args.size.split('x'));w.set_size_request(width,height);w.set_default_size(width,height)
    for child in w.layout:
        if isinstance(child,Adw.Banner):child.set_title('NATIVE TEST RENDER · 24-game recent rail · Play disabled')
    w.show_home();w.present();frame(w)
    # The isolated renderer can defer the window's responsive tick. Use the
    # same resize hook as capture(), then require actual cover allocation before
    # driving input so a later screenshot cannot change the tested geometry.
    w.console_size=None;w.resize_console(w,None)
    ready(w,lambda:all(t.console_cover.get_width()==w.console_dimensions()[0] for _,t in w.tv_tiles),'Responsive rail cover allocation')
    settings=Gtk.Settings.get_default();old_animations=settings.get_property('gtk-enable-animations');settings.set_property('gtk-enable-animations',True)
    scroll_requests=[];scroll_into_view=w.scroll_tv_card_into_view
    def traced_scroll(tile,animate=False):
        scroll_requests.append({'tile_index':next((i for i,(_,t) in enumerate(w.tv_tiles) if t is tile),None),'focused':w.focused_control(w) is tile,'animate':animate,'generation':w.catalog_generation})
        return scroll_into_view(tile,animate)
    w.scroll_tv_card_into_view=traced_scroll
    def send(action):
        if args.mode=='fullscreen':w.controller_action(action)
        else:key(w,{'left':Gdk.KEY_Left,'right':Gdk.KEY_Right,'up':Gdk.KEY_Up,'down':Gdk.KEY_Down}[action])
    def finished(tile):
        return w.focused_control(w) is tile and not getattr(w,'rail_animation',None) and horizontal(tile,w.tv_scroll) and visible_in(tile,w.tv_page)
    def settle_animation(description):
        ready(w,lambda:not getattr(w,'rail_animation',None),description+' animation complete')
        after_frames(w,lambda:True,description+' native frame callbacks')
    def assert_tile(tile,description):
        settle_animation(description)
        check(w.focused_control(w) is tile,description+' intended focus')
        check(horizontal(tile,w.tv_scroll),description+' horizontal visibility')
        check(visible_in(tile,w.tv_page),description+' vertical visibility')
        if not args.probe:check(finished(tile),description+' final focused card visible on both axes')
    try:
        check((w.get_width(),w.get_height())==(width,height),'Exact native viewport '+args.size+' '+args.mode)
        check(len(w.tv_tiles)==24,'All 24 recently played games present')
        check(all(t.console_cover.get_width()==w.console_dimensions()[0] for _,t in w.tv_tiles),'Responsive cover widths match the native viewport')
        w.tv_tiles[0][1].grab_focus();settle_animation('First recent card')
        for index in range(1,11):
            send('right');assert_tile(w.tv_tiles[index][1],f'Right step {index}')
        check(w.tv_scroll.get_hadjustment().get_value()>0,'Long-rail traversal advances horizontal scroll')
        if args.probe:
            capture(w,args.output/'offscreen-regression.png')
        else:
            w.tv_tiles[20][1].grab_focus();assert_tile(w.tv_tiles[20][1],'Direct focus beyond viewport')
            capture(w,args.output/'long-rail-focused.png',remap=False)
            for action in ('right','left','right','left','left','right'):send(action)
            assert_tile(w.tv_tiles[20][1],'Rapid horizontal A-B-A reversal')
            # Leave the rail while its animation is pending. The callback must
            # not scroll after focus has moved into the vertical ready grid.
            send('left');send('down');grid=w.focused_control(w)
            check(grid in [t for _,t in w.home_setup_tiles],'Down moves from rail into ready grid')
            ready(w,lambda:visible_in(grid,w.tv_page),'Ready grid vertical reveal')
            adjustment=w.tv_scroll.get_hadjustment();position=adjustment.get_value()
            settle_animation('Leave rail')
            check(w.focused_control(w) is grid and visible_in(grid,w.tv_page),'Grid focus remains visible after old rail callback')
            check(adjustment.get_value()==position,'Canceled rail callback cannot change horizontal scroll')
            send('up');recent=w.focused_control(w)
            check(recent in [t for _,t in w.tv_tiles],'Up returns from ready grid to recent rail')
            assert_tile(recent,'Vertical return to horizontal rail')
            # A new Home generation creates a different scroll widget. A queued
            # animation from the old Home cannot repaint the replacement.
            send('right');old_scroll=w.tv_scroll;w.show_library();frame(w);w.show_home();frame(w)
            check(w.tv_scroll is not old_scroll,'Route change replaces the old rail')
            # Queue the initial allocation callback for one card, then move
            # focus before its frame. The old card must not steal the reveal.
            w.tv_tiles[20][1].grab_focus();w.finish_tv_library_focus()
            w.tv_tiles[12][1].grab_focus();assert_tile(w.tv_tiles[12][1],'Return after route generation changed')
            selected=w.tv_selected_id;w.focused_control(w).activate();ready(w,lambda:w.route=='detail','Open recent detail')
            w.return_from_detail();frame(w)
            restored=next(t for gid,t in w.tv_tiles if gid==selected);assert_tile(restored,'Back to long recent rail')
            # Reduced motion must keep the same ownership/visibility behavior.
            settings.set_property('gtk-enable-animations',False)
            w.tv_tiles[23][1].grab_focus();assert_tile(w.tv_tiles[23][1],'Animations disabled')
            send('right');assert_tile(w.tv_tiles[0][1],'Wrap to first recent card')
            capture(w,args.output/'long-rail-return.png',remap=False)
        check(library.games()==before,'Navigation preserves game records and dates')
    finally:
        settings.set_property('gtk-enable-animations',old_animations)
        report={'source':str(args.source),'app_sha256':hashlib.sha256((args.source/'game_library/app.py').read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'size':[w.get_width(),w.get_height()],'mode':args.mode,'checks':checks,'scroll_requests':scroll_requests,'last_focus_bounds':bounds(w.focused_control(w),w.tv_scroll) if w.focused_control(w) and hasattr(w,'tv_scroll') else None,'capture':'Synthetic native GTK test render; Play disabled','input':'In-process GTK key/controller actions; no physical input acceptance'}
        (args.output/'checks.json').write_text(json.dumps(report,indent=2)+'\n')
        w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True);w.controller.close();w.destroy();settle()
print(str(sum(x['passed'] for x in checks))+'/'+str(len(checks))+' long-rail assertions passed',flush=True)
assert all(x['passed'] for x in checks)
