"""Native first-card readiness with held provider/genre/artwork fixtures."""
import argparse
import faulthandler
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

faulthandler.enable()

parser=argparse.ArgumentParser()
parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--mode',choices=('desktop','fullscreen'),default='desktop')
parser.add_argument('--probe',action='store_true')
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
if os.environ.get('GDK_BACKEND')!='broadway':raise SystemExit('Use an isolated Broadway fixture.')
sys.path[:0]=[str(args.source),str(args.source/'tools')]
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from fullscreen_preview import settle,capture
from navigation_fixture import ready,frame,after_frames,visible_in
from gi.repository import Adw,Gio,GLib


class ControlledCatalog:
    def __init__(self):
        self.lock=threading.Lock();self.active=0;self.calls=[];self.images=[]
        self.running={'metadata':0,'image':0};self.peak=dict(self.running)
        self.variant=0;self.suffix='';self.art_tag='';self.offline=False;self.query_gates={};self.query_entered={};self.total=None;self.reset()
    def reset(self):
        self.page_gate=threading.Event();self.genre_gate=threading.Event();self.art_gate=threading.Event()
        self.page_entered=threading.Event();self.genre_entered=threading.Event()
        self.art_entered=threading.Event()
        self.art_completed=0
    def release(self):
        for event in (self.page_gate,self.genre_gate,self.art_gate):event.set()
    def held(self,kind,gate,entered=None):
        group='image' if kind=='image' else 'metadata'
        with self.lock:
            self.active+=1;self.calls.append({'kind':kind,'at':time.monotonic()})
            self.running[group]+=1;self.peak[group]=max(self.peak[group],self.running[group])
        try:
            if entered:entered.set()
            if not gate.wait(30):raise RuntimeError('Fixture gate timed out: '+kind)
            if self.offline:raise OSError('Fixture offline')
        finally:
            with self.lock:self.active-=1;self.running[group]-=1
    def genres(self):
        self.held('genres',self.genre_gate,self.genre_entered)
        return [{'id':5,'name':'Adventure'},{'id':12,'name':'Exploration'}]
    def item(self,identity,art_tag=None):
        tag=self.art_tag if art_tag is None else art_tag
        return {'id':identity,'name':f'Orbit {identity:02}'+self.suffix,'description':'A fictional performance fixture.',
                'genres':[{'id':5,'name':'Adventure'}],
                'images':{'portrait':f'https://images.igdb.com/igdb/image/upload/t_cover_big/performance{tag}{identity%3}.jpg'}}
    def browse(self,query='',genre=None,page=1):
        gate=self.query_gates.get(query,self.page_gate)
        entered=self.query_entered.setdefault(query,threading.Event())
        self.page_entered.set();self.held('page',gate,entered)
        offset={'old':200,'new':300}.get(query,self.variant*100)
        data={'items':[self.item(i+offset) for i in range(1,25)],'page':page,'has_next':False}
        if self.total is not None:data.update(total_items=self.total*24,total_pages=self.total,has_next=page<self.total)
        return data
    def detail(self,identity):return self.item(identity)
    def image(self,url,limit):
        self.held('image',self.art_gate,self.art_entered)
        with self.lock:self.art_completed+=1
        return self.images[int(url[-5])]


checks=[];measurements=[];active_measurement=None
def check(condition,name):
    checks.append({'check':name,'passed':bool(condition)})
    print(('PASS ' if condition else 'FAIL ')+name,flush=True)
    if not condition and not args.probe:raise AssertionError(name)

with tempfile.TemporaryDirectory(prefix='umutron-store-performance-') as tmp:
    os.environ['XDG_CACHE_HOME']=tmp;library=prepare_demo(True);before=library.games()
    provider=ControlledCatalog();provider.images=[(library.art_dir/g['artwork']['portrait']).read_bytes() for g in before]
    app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    def create_window():
        with patch('game_library.app.Controller') as controller:
            controller.return_value.name='';controller.return_value.error=''
            window=Window(app,library,demo=True,catalog_provider=provider)
        app.window=window;window.navigation_window=lambda:window;window.catalog.image_transport=provider.image
        window.proton_manager.releases=lambda *a,**k:[];window.theme.set_selected(2)
        render=window.render_store
        def observed(data,*args,**kwargs):
            result=render(data,*args,**kwargs)
            if active_measurement is not None and active_measurement['first_model_ms'] is None and len(window.collection_tiles)==24:
                active_measurement['first_model_ms']=round((time.monotonic()-active_measurement['started'])*1000,2)
            return result
        window.render_store=observed
        window.set_tv_mode(args.mode=='fullscreen');window.unfullscreen();window.set_visible(False);window.unrealize()
        window.set_size_request(1120,800);window.set_default_size(1120,800)
        for child in window.layout:
            if isinstance(child,Adw.Banner):child.set_title('NATIVE TEST RENDER · held provider/artwork · Play disabled')
        window.show_home();window.present();frame(window)
        return window
    def close_window(window):
        provider.release();window.exiting=True;window.catalog_cancel()
        window.catalog_pool.shutdown(wait=True,cancel_futures=True);window.pool.shutdown(wait=True)
        window.controller.close();window.destroy();settle()
    w=create_window()
    def usable():
        tiles=list(w.collection_tiles.values())
        return len(tiles)==24 and tiles[0].get_mapped() and tiles[0].get_width()>0 and tiles[0].is_sensitive()
    def drained():return not w.catalog_futures and provider.active==0 and not getattr(w.catalog,'flights',{})
    def begin(name):
        global active_measurement
        provider.reset();started=time.monotonic();active_measurement={'started':started,'first_model_ms':None};w.show_store()
        if name=='cold':
            def release_page():provider.page_gate.set();return False
            GLib.timeout_add(120,release_page)
        if args.probe:
            ready(w,lambda:provider.genre_entered.is_set() or provider.page_entered.is_set(),name+' provider entered')
            after_frames(w,lambda:True,name+' existing native frames',frames=3)
        else:ready(w,usable,name+' first usable native cards')
        usable_before=usable()
        measurements.append({'phase':name,'first_model_ms':active_measurement['first_model_ms'],'first_usable_ms':round((time.monotonic()-started)*1000,2) if usable_before else None,
                             'usable_while_genres_held':usable_before and not provider.genre_gate.is_set(),
                             'usable_while_page_held':usable_before and not provider.page_gate.is_set(),
                             'art_completed_at_first_cards':provider.art_completed})
        check(usable_before,name+' cards usable before genres complete')
        if name=='cold':check(provider.art_completed==0,'Cold cards do not wait for artwork')
        else:
            check(usable_before and not provider.page_gate.is_set(),name+' validated cards visible before network refresh')
            check('refreshing' in w.collection_status.get_text().lower(),name+' saved results are refreshing, not declared offline')
        capture(w,args.output/(name+'-first-cards.png'),remap=False)
        active_measurement=None
        return started
    try:
        begin('cold')
        if not args.probe:
            selected=next(iter(w.collection_tiles));w.collection_tiles[selected].activate()
            ready(w,lambda:w.route=='detail','Cold card opens before artwork and genres finish')
            check(w.detail_item['id']==selected and provider.art_completed==0 and not provider.genre_gate.is_set(),'First usable card opens shared detail while artwork and genres are held')
            provider.release();ready(w,drained,'Cold detail work finished')
            w.return_from_detail();ready(w,usable,'Cold detail Back restores Store');ready(w,drained,'Cold Store refresh finished')
        provider.release();ready(w,drained,'Cold page, genre and progressive artwork finished')
        check(len(w.collection_tiles)==24,'Cold request finishes with 24 cards')
        if not args.probe:check(all(t.catalog_image_url for t in w.collection_tiles.values()),'Artwork fills existing card slots progressively')
        begin('warm')
        search=w.collection_search;search.set_text('Unsubmitted draft');search.grab_focus();w.mark_browse_input()
        provider.suffix=' refreshed';provider.release();ready(w,drained,'Warm background refresh finished')
        check(w.collection_search is search and search.get_text()=='Unsubmitted draft','Warm refresh retains native search object and draft')
        check(w.focused_control(w) is search,'Warm refresh cannot reclaim newer search focus')
        close_window(w);w=create_window();begin('reopen');provider.release();ready(w,drained,'Reopened background refresh finished')
        if not args.probe:
            # Cache paint happens first. Move deeper into cards while the fresh
            # page is held; metadata changes must retain the actual native tile.
            provider.reset();w.show_store();ready(w,usable,'Cached cards for focus preservation')
            tile=w.collection_tiles[17];tile.grab_focus();w.mark_browse_input()
            ready(w,lambda:visible_in(tile,w.collection_scroll),'Selected cached card visible')
            provider.suffix=' updated again';provider.page_gate.set()
            ready(w,lambda:not w.routes['store']['result'].get('cached'), 'Fresh page applied independently of genres')
            after_frames(w,lambda:True,'Fresh card native layout')
            check(w.collection_tiles[17] is tile and w.focused_control(w) is tile,'Same identities retain focused native card')
            check(visible_in(tile,w.collection_scroll),'Refreshed focused card remains fully visible')
            provider.release();ready(w,drained,'Focus-preserving refresh complete')
            # A changed result set must not reclaim the search field, and old
            # artwork completions must not paint a replacement card.
            provider.reset();w.show_store();ready(w,usable,'Cached cards before changed results')
            search=w.collection_search;search.set_text('Keep this draft');search.grab_focus();w.mark_browse_input()
            provider.variant=1;provider.page_gate.set()
            ready(w,lambda:101 in w.collection_tiles,'Changed fresh identities arrive')
            after_frames(w,lambda:True,'Changed results native layout')
            check(w.focused_control(w) is search and search.get_text()=='Keep this draft','Replacement results preserve newer search focus and draft')
            provider.release();ready(w,drained,'Replacement artwork complete')
            provider.reset();w.show_store();ready(w,usable,'Cached cards before selected identity disappears')
            w.collection_tiles[117].grab_focus();w.mark_browse_input();provider.variant=2;provider.page_gate.set()
            ready(w,lambda:201 in w.collection_tiles and w.focused_control(w) is w.collection_tiles[201],'Removed selected identity falls back to first current card')
            ready(w,lambda:visible_in(w.collection_tiles[201],w.collection_scroll),'Replacement first card fully visible')
            check(w.routes['store']['focus']==201,'Removed selected card falls back to current page identity')
            provider.release();ready(w,drained,'Removed selection refresh finished')
            provider.reset();w.show_store();ready(w,usable,'Cached cards while genres refresh')
            w.collection_genre.set_selected(1)
            ready(w,lambda:w.routes['store']['genre']==5,'Genre choice committed while old genre refresh held')
            provider.release();ready(w,drained,'Genre choice refresh finished')
            check(w.routes['store']['genre']==5 and w.collection_genre.get_selected()==1,'Late genre refresh preserves newer selected filter')
            w.store_genres_loaded([{'id':12,'name':'Exploration'}])
            check(w.routes['store']['genre']==5 and w.catalog_genres[w.collection_genre.get_selected()-1]['id']==5,'Missing selected taxonomy entry retains active filter identity')
            w.collection_genre.set_selected(0);ready(w,drained,'All genres restored')
            provider.total=8;w.catalog.browse();provider.reset();w.show_store();ready(w,usable,'Known cached pager before refresh')
            page_button=next(c for c in w.collection_numbers if getattr(c,'catalog_page_number',None)==2)
            page_button.grab_focus();w.mark_browse_input();provider.total=9;provider.page_gate.set()
            ready(w,lambda:w.collection_total_pages==9,'Changed known totals arrive')
            check(getattr(w.focused_control(w),'catalog_page_number',None)==2,'Refresh retains focused page number when still available')
            provider.release();ready(w,drained,'Known pager refresh complete')
            provider.reset();w.show_store();ready(w,usable,'Known cached pager before unknown total')
            last_number=next(c for c in w.collection_numbers if getattr(c,'catalog_page_number',None)==3)
            last_number.grab_focus();w.mark_browse_input();provider.total=None;provider.page_gate.set()
            ready(w,lambda:w.collection_total_pages is None,'Unknown total replaces known total')
            check(w.focused_control(w) is w.collection_search,'Removed page number yields focus to search')
            provider.release();ready(w,drained,'Unknown total refresh complete')
            # Same-generation refresh reuses card widgets. Late artwork from
            # the cached render must not paint those widgets with an old URL.
            provider.art_tag='held';w.catalog.browse()
            provider.reset();w.show_store();ready(w,usable,'Cached page with uncached held artwork')
            ready(w,provider.art_entered.is_set,'Old artwork transport entered')
            old_gate=provider.art_gate
            old_paths={hashlib.sha256(item['images']['portrait'].encode()).hexdigest()+'.jpg' for item in w.routes['store']['result']['items']}
            import game_library.catalog_ui as catalog_ui
            painted=[];update_cover=catalog_ui.update_cover
            def tracked(frame,path):painted.append(Path(path).name);return update_cover(frame,path)
            with patch.object(catalog_ui,'update_cover',side_effect=tracked):
                provider.art_tag='fresh';provider.page_gate.set();provider.genre_gate.set()
                ready(w,lambda:not w.routes['store']['result'].get('cached'),'Fresh URLs replace held cached URLs')
                provider.art_gate=threading.Event();provider.art_gate.set();old_gate.set()
                ready(w,drained,'Old and new artwork transports finish')
            check(not old_paths.intersection(painted),'Superseded same-page artwork never paints reused card widgets')
            check(all('fresh' in t.catalog_image_url for t in w.collection_tiles.values()),'Only current artwork URLs populate refreshed cards')
            # Older query completion may populate its own cache, but cannot
            # repaint a newer query or reclaim its search draft/focus.
            old_query=threading.Event();new_query=threading.Event()
            provider.query_gates={'old':old_query,'new':new_query};provider.release()
            w.collection_search.set_text('old');w.mark_browse_input();w.collection_search.emit('activate')
            ready(w,lambda:provider.query_entered.get('old',threading.Event()).is_set(),'Old query begins')
            w.collection_search.set_text('new');w.mark_browse_input();w.collection_search.emit('activate')
            ready(w,lambda:provider.query_entered.get('new',threading.Event()).is_set(),'New query begins independently')
            new_query.set();ready(w,lambda:301 in w.collection_tiles,'New query cards arrive')
            search=w.collection_search;search.set_text('Newer unsent draft');search.grab_focus();w.mark_browse_input()
            old_query.set();ready(w,drained,'Old query finally completes');after_frames(w,lambda:True,'Stale query callbacks settle')
            check(w.routes['store']['query']=='new' and 301 in w.collection_tiles and 201 not in w.collection_tiles,'Older query completion cannot replace current cards')
            check(w.focused_control(w) is search and search.get_text()=='Newer unsent draft','Older query cannot reclaim search draft or focus')
            check(w.catalog.cached_browse('old')['items'][0]['id']==201 and w.catalog.cached_browse('new')['items'][0]['id']==301,'Concurrent query snapshots retain their exact keys')
            provider.query_gates={}
            provider.offline=True;provider.reset();w.show_store();ready(w,usable,'Offline cache immediately usable')
            check('refreshing' in w.collection_status.get_text().lower(),'Offline is not inferred before refresh fails')
            provider.release();ready(w,drained,'Offline refresh fallback')
            check('Offline' in w.collection_status.get_text() and len(w.collection_tiles)==24,'Failed refresh retains validated cards and reports offline')
            provider.offline=False;provider.release()
            selected=next(iter(w.collection_tiles));w.collection_tiles[selected].activate();ready(w,lambda:w.route=='detail','Cached card opens shared detail')
            check(w.detail_item['id']==selected,'Refreshed card opens its current metadata identity')
            w.return_from_detail();ready(w,usable,'Detail Back returns to cached Store cards')
            provider.release();ready(w,drained,'Final Store refresh complete')
            capture(w,args.output/'store-final.png',remap=False)
        check(library.games()==before,'Browsing and refresh preserve all saved game records')
        if not args.probe:check(provider.peak['metadata']<=3 and provider.peak['image']<=2,'Provider concurrency stays inside separate metadata and image bounds')
    finally:
        for gate in provider.query_gates.values():gate.set()
        provider.release();close_window(w)
        report={'source':str(args.source),'mode':args.mode,'size':[1120,800],'checks':checks,'measurements':measurements,
                'fixture_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'source_sha256':{str(p.relative_to(args.source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.source/'game_library').glob('*.py')},
                'provider_calls':provider.calls,'peak_provider_concurrency':provider.peak,'capture':'Synthetic native GTK test render; Play disabled',
                'timing_note':'Controlled gates; cold page released after 120 ms. No live API latency claim. Warm/reopen readiness asserted before releasing network refresh.'}
        (args.output/'checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'{sum(c["passed"] for c in checks)}/{len(checks)} native Store performance assertions pass',flush=True)
if not args.probe:assert all(c['passed'] for c in checks)
