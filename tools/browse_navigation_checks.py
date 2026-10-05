"""Bidirectional browse focus with shared native fixtures and synthetic games."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
from unittest.mock import patch
from uuid import uuid4

parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
parser.add_argument('--output',type=Path,required=True);parser.add_argument('--probe',action='store_true')
parser.add_argument('--route',choices=('home','library','store'))
modes=parser.add_mutually_exclusive_group();modes.add_argument('--desktop-only',action='store_true');modes.add_argument('--fullscreen-only',action='store_true')
parser.add_argument('--async-only',action='store_true')
parser.add_argument('--size')
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
if os.environ.get('GDK_BACKEND')!='broadway':raise SystemExit('Use the isolated native fixture.')
sys.path.insert(0,str(args.source));sys.path.insert(0,str(args.source/'tools'))
from navigation_fixture import key,frame,ready,visible_in,after_frames
from fullscreen_preview import settle,capture
from catalog_fixtures import FixtureCatalog
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library.play_history import record
from gi.repository import Adw,Gdk,Gio,Gtk


class LocalCatalog(FixtureCatalog):
    def detail(self,game_id):
        item=super().detail(game_id);item['images']={};return item


def widgets(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from widgets(child);child=child.get_next_sibling()


checks=[]
def check(condition,name):
    checks.append({'check':name,'passed':bool(condition)})
    if not args.probe and not condition:
        widget=w.get_focus();ancestry=[]
        while widget:
            ancestry.append({'type':type(widget).__name__,'css_name':widget.get_css_name(),'label':widget.get_label() if isinstance(widget,Gtk.Button) else None})
            widget=widget.get_parent()
        print('FOCUS FAILURE',name,ancestry,'named controls',[key for key in ('tv_menu','tv_home_tab','tv_library_tab','tv_games_tab','collection_search_button') if getattr(w,key,None) is w.focused_control(w)],flush=True)
        raise AssertionError(name)


with tempfile.TemporaryDirectory(prefix='umutron-browse-navigation-') as temporary:
    os.environ['XDG_CACHE_HOME']=temporary;library=prepare_demo(True);samples=library.games()
    for index in range(53):
        game=library.new_game();game.update(title=f'Ready fixture {index:02}',executable=samples[0]['executable'],artwork=samples[0]['artwork'])
        if index<18:game['setup_completed_at']=10000+index
        library.save(game)
    legacy=library.new_game();legacy.update(title='Undated Library only fixture',executable=samples[0]['executable']);library.save(legacy)
    for index,game in enumerate(samples):record(library.root,game['id'],str(uuid4()),100+index)
    before=library.games();app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name='';controller.return_value.error=''
        w=Window(app,library,demo=True,catalog_provider=LocalCatalog())
    app.window=w;w.navigation_window=lambda:w;w.proton_manager.releases=lambda *a,**k:[]
    w.theme.set_selected(2);w.present()
    for child in w.layout:
        if isinstance(child,Adw.Banner):child.set_title('NATIVE TEST RENDER · final Home/navigation fixture · Play disabled')
    def send(action,controller=False):
        if controller:w.controller_action(action)
        else:key(w,{'up':Gdk.KEY_Up,'down':Gdk.KEY_Down,'left':Gdk.KEY_Left,'right':Gdk.KEY_Right}[action])
    try:
        sizes=[(1120,800)] if args.probe or args.route else [(1120,800),(900,600),(1920,1080)]
        if args.size:sizes=[tuple(map(int,args.size.split('x')))]
        if args.async_only:
            sizes=[];w.set_tv_mode(args.fullscreen_only);frame(w)
        for width,height in sizes:
            for tv in ((False,) if args.desktop_only else (True,) if args.fullscreen_only else (False,True)):
                w.set_tv_mode(tv);w.unfullscreen();w.set_visible(False);w.unrealize()
                w.set_size_request(width,height);w.set_default_size(width,height);w.present()
                for route,show in (('home',w.show_home),('library',w.show_library),('store',w.show_store)):
                    if args.route and args.route!=route:continue
                    if os.environ.get('UMUTRON_TEST_IO_GUARD')=='1':
                        pressure={line.split()[0]:float(line.split()[1].split('=')[1]) for line in Path('/proc/pressure/io').read_text().splitlines()}
                        if pressure.get('full',0)>10 or pressure.get('some',0)>20:
                            print('RESOURCE PAUSE before route',route,pressure,flush=True)
                            raise SystemExit('Paused for I/O pressure; incomplete matrix')
                    prefix=f'{route} {width}x{height} '+('fullscreen' if tv else 'desktop')
                    show();frame(w)
                    check((w.get_width(),w.get_height())==(width,height),prefix+' exact native viewport')
                    if route=='store':ready(w,lambda:len(w.tv_tiles)==24,prefix+' loaded cards')
                    if route!='home':
                        # Immediate cached cards can be mapped before the next
                        # responsive tick reallocates their compact cover size.
                        # Assert the current viewport's geometry before testing
                        # whether its bottom row needs scrolling.
                        compact=(height<700,width<1000)
                        cover_height=(120 if compact[1] else 144) if compact[0] else 204
                        ready(w,lambda:all(getattr(t,'collection_compact',None)==compact and t.console_cover.get_height()==cover_height for _,t in w.tv_tiles),prefix+' current responsive card allocation')
                    header=[w.tv_home_tab,w.tv_library_tab,w.tv_games_tab,w.tv_menu] if tv else [w.home_nav,w.library_nav,w.store_nav]
                    active=header[('home','library','store').index(route)]
                    scroll=w.tv_page if route=='home' else w.collection_scroll
                    tiles=w.home_setup_tiles if route=='home' else w.tv_tiles
                    if route=='home':
                        labels=[x.get_text() for x in widgets(w.body) if isinstance(x,Gtk.Label)]
                        check('Existing setups' not in labels and 'Recently ready to play' in labels,prefix+' final Home headings')
                        check(legacy['id'] not in [gid for gid,_ in tiles],prefix+' undated title excluded from Home ready rail')
                        check(any(g['id']==legacy['id'] and 'setup_completed_at' not in g for g in library.games()),prefix+' legacy record retained without invented date')
                    else:
                        active.grab_focus();send('down',tv);settle(80)
                        focus=w.get_focus();search=w.collection_search
                        check(focus is search or (focus and focus.is_ancestor(search)),prefix+' route Down reaches search input')
                        if not args.probe:
                            if tv:
                                active.grab_focus();key(w,Gdk.KEY_Down)
                                check(w.focused_control(w) is search,prefix+' fullscreen keyboard also reaches search')
                            search.set_text('fixture caret');search.set_position(4)
                            for value in (Gdk.KEY_Left,Gdk.KEY_Right):
                                check(not key(w,value) and search.get_position()==4,prefix+' native caret key is not intercepted '+str(value))
                            check(key(w,Gdk.KEY_Escape) and w.focused_control(w) is active,prefix+' Escape returns from search to current route')
                            active.grab_focus();send('down',tv)
                            if tv:
                                # The previous route's selection need not occur
                                # on this collection page. Down must still work.
                                w.tv_selected_id='off-page-selection'
                                for expected in (w.collection_search_button,w.collection_genre):
                                    w.controller_action('down');check(w.focused_control(w) is expected,prefix+' controller traverses browse toolbar')
                                w.controller_action('down');check(w.focused_control(w) in [t for _,t in tiles],prefix+' controller exits toolbar into cards')
                            else:
                                # Tab stays with GTK; navigate through the native chain.
                                check(not key(w,Gdk.KEY_Tab),prefix+' search Tab remains native')
                                w.child_focus(Gtk.DirectionType.TAB_FORWARD)
                                check(w.focused_control(w) is w.collection_search_button,prefix+' native Tab reaches Search button')
                            search.set_text('')
                    # Deep-card focus is only fixture setup. Return to the top
                    # uses the same input actions the product receives.
                    bottom=tiles[-1][1];bottom.grab_focus()
                    ready(w,lambda:visible_in(bottom,scroll),prefix+' bottom card visibility')
                    check(scroll.get_vadjustment().get_value()>0,prefix+' lower content requires scrolling')
                    if args.probe:
                        active.grab_focus();settle(200)
                        check(scroll.get_vadjustment().get_value()<=1,prefix+' top route focus reveals top content')
                        continue
                    seen=[]
                    for step in range(100):
                        focused=w.focused_control(w)
                        if focused in header:break
                        send('up',tv)
                        next_focus=w.focused_control(w)
                        if next_focus is focused and route!='home' and next_focus is w.collection_search:
                            key(w,Gdk.KEY_Escape);next_focus=w.focused_control(w)
                        if next_focus is focused and not tv:
                            native=w.get_focus()
                            while native and not isinstance(native,Gtk.DropDown):native=native.get_parent()
                            if native:
                                check(not key(w,Gdk.KEY_Tab,Gdk.ModifierType.SHIFT_MASK),prefix+' native filter Tab is not intercepted')
                                w.child_focus(Gtk.DirectionType.TAB_BACKWARD);next_focus=w.focused_control(w)
                        check(next_focus is not focused,prefix+f' Up makes progress {step}')
                        if next_focus.is_ancestor(scroll):
                            ready(w,lambda:visible_in(next_focus,scroll),prefix+' upward focused card visibility')
                            check(visible_in(next_focus,scroll),prefix+f' Up keeps focused control visible {step}')
                        seen.append(next_focus)
                    check(w.focused_control(w) in header,prefix+' upward traversal reaches route controls')
                    after_frames(w,lambda:scroll.get_vadjustment().get_value()<=1,prefix+' header reveals top content')
                    check(scroll.get_vadjustment().get_value()<=1,prefix+' header scroll is at top')
                    # Opposing changes before the next layout frame must keep
                    # only the last focus destination, including A-B-A cycles.
                    middle=tiles[len(tiles)//2][1];middle.grab_focus()
                    send('down',tv);send('up',tv);send('down',tv);send('up',tv)
                    target=w.focused_control(w)
                    if target.is_ancestor(scroll):after_frames(w,lambda:visible_in(target,scroll),prefix+' rapid direction reversal')
                    check(w.focused_control(w) is target,prefix+' rapid reversal retains last focus')
                    for repeat in range(2):
                        selected=w.tv_selected_id
                        target.activate();ready(w,lambda:w.route=='detail',prefix+' opens selected detail')
                        w.return_from_detail()
                        def restored():
                            current=next((t for gid,t in (w.home_setup_tiles if route=='home' else w.tv_tiles) if gid==selected),None)
                            viewport=w.tv_page if route=='home' else w.collection_scroll
                            return current is not None and w.focused_control(w) is current and visible_in(current,viewport)
                        ready(w,restored,prefix+' Back restores visible focus')
                        check(restored(),prefix+f' Back {repeat+1} restores visible focus')
                        target=w.focused_control(w)
                    scroll=w.tv_page if route=='home' else w.collection_scroll
                    active.grab_focus();ready(w,lambda:scroll.get_vadjustment().get_value()<=1,prefix+' top after Back')
                    if route!='home':
                        w.restore_collection();active.grab_focus();key(w,Gdk.KEY_Left);key(w,Gdk.KEY_Right)
                        after_frames(w,lambda:w.focused_control(w) is active and scroll.get_vadjustment().get_value()<=1,prefix+' stale restore canceled')
                        check(w.focused_control(w) is active,prefix+' queued restore cannot steal route focus')
                        w.tv_tiles[0][1].grab_focus();key(w,Gdk.KEY_Page_Down)
                        ready(w,lambda:w.routes[route]['page']==2 and bool(w.tv_tiles),prefix+' next page')
                        frame(w);key(w,Gdk.KEY_Page_Up);ready(w,lambda:w.routes[route]['page']==1 and bool(w.tv_tiles),prefix+' previous page');frame(w)
                        check(w.routes[route]['page']==1,prefix+' page round trip')
                        if route=='library':check(any(g['id']==legacy['id'] for g in library.games()),prefix+' Library retains undated title')
                        w.collection_search.grab_focus();w.collection_search.set_text('fixture')
                        if tv:w.controller_action('select')
                        else:
                            check(not key(w,Gdk.KEY_Return),prefix+' native search Enter is not intercepted')
                            w.collection_search.emit('activate')
                        ready(w,lambda:w.routes[route]['query']=='fixture' and bool(w.tv_tiles),prefix+' search submission')
                        check(w.routes[route]['query']=='fixture',prefix+' native/controller search submission preserves query')
                        w.collection_search.set_text('');w.collection_search.emit('activate')
                        ready(w,lambda:w.routes[route]['query']=='' and bool(w.tv_tiles),prefix+' search reset')
                        frame(w);w.focus_browse_route()
                        after_frames(w,lambda:w.collection_scroll.get_vadjustment().get_value()<=1,prefix+' top after query reset')
                    if (width,height) in ((1120,800),(900,600)):
                        capture(w,args.output/(route+('-fullscreen-' if tv else '-desktop-')+str(height)+'.png'))
                    print('PASS ROUTE',prefix,flush=True)
        if not args.probe and not args.route:
            # A same-route completion must retain a search draft and its focus.
            entered=Event();release=Event();browse=w.catalog.provider.browse
            def delayed(*arguments,**keywords):
                entered.set()
                if not release.wait(5):raise AssertionError('Fixture release timed out')
                return browse(*arguments,**keywords)
            with patch.object(w.catalog.provider,'browse',side_effect=delayed):
                try:
                    w.show_store();ready(w,entered.is_set,'pending same-route Store request')
                    w.focus_browse_route();key(w,Gdk.KEY_Down)
                    search=w.collection_search;search.set_text('unfinished search draft')
                    check(not key(w,Gdk.KEY_Right),'Draft search keeps native caret during a pending request')
                    release.set();ready(w,lambda:bool(w.tv_tiles),'pending Store request completes')
                    after_frames(w,lambda:w.focused_control(w) is search and search.get_text()=='unfinished search draft' and w.collection_scroll.get_vadjustment().get_value()<=1,'late Store response retains search focus')
                    check(w.focused_control(w) is search,'Late Store result cannot reclaim focus or scroll from search')
                finally:release.set()
        check(library.games()==before,'All navigation preserves game records and timestamps')
    finally:
        w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True);w.controller.close();w.destroy();settle()
        result={'source':str(args.source),'source_sha256':{name:hashlib.sha256((args.source/'game_library'/name).read_bytes()).hexdigest() for name in ('app.py','catalog_ui.py')},'fixture_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'checks':checks,'real_game_or_installer_runs':0,'capture':'Synthetic native test render; shared existing GTK fixture helpers','input':'In-process key-controller signals and controller methods; no hardware input acceptance'}
        (args.output/'checks.json').write_text(json.dumps(result,indent=2)+'\n')
for row in checks:
    if not row['passed']:print('FAIL: '+row['check'])
print(str(sum(c['passed'] for c in checks))+'/'+str(len(checks))+' browse assertions pass')
assert all(row['passed'] for row in checks)
