"""Exact catalog tracking; shared Steam relations are inert navigation only."""
import gc
import os
from pathlib import Path
import socket
import sys
import tempfile
import weakref
from threading import Event
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
assert os.environ.get('GDK_BACKEND')=='broadway'
def guard(event,args):
    if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn'):raise RuntimeError('Execution disabled')
    if event in ('socket.connect','socket.bind') and getattr(args[0],'family',None)!=socket.AF_UNIX:raise RuntimeError('Network disabled')
sys.addaudithook(guard)
from fullscreen_preview import settle
from navigation_fixture import ready,frame
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library.catalog import item_game,validate_item,members,related_members
from gi.repository import Gio,Gtk


class Provider:
    def genres(self):return []
    def browse(self,*_):
        return {'page':1,'has_next':False,'items':[{'id':i,'name':'Same catalog title','steam_app_id':None,'game_type':kind,'platforms':[{'id':6,'name':'PC (Microsoft Windows)'}]} for i,kind in ((334647,'Bundle'),(334254,'Expanded Game'))]}
    def detail(self,game_id):
        relation={'bundles':[],'parent_game':None,'expanded_games':[],'version_parent':None}
        if game_id==334647:relation['bundle_contents']={'items':[{'id':334254,'name':'Reported component'}],'complete':False}
        else:relation['expanded_from']={'items':[],'complete':True}
        return {**next(i for i in self.browse()['items'] if i['id']==game_id),'steam_app_id':3240220,'relationships':relation}


checks=[]
def widgets(widget):
    yield widget;child=widget.get_first_child()
    while child:yield from widgets(child);child=child.get_next_sibling()
def check(condition,name):
    assert condition,name
    checks.append(name);print('PASS '+name,flush=True)

with tempfile.TemporaryDirectory(prefix='umutron-membership-ui-') as temp:
    os.environ['XDG_CACHE_HOME']=temp;library=prepare_demo(True)
    local=library.games()[0];local.update(title='Same catalog title',metadata_source={'provider':'steam','id':3240220},metadata_app_id=3240220);library.save(local)
    provider=Provider();app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name=controller.return_value.error='';w=Window(app,library,demo=True,catalog_provider=provider)
    app.window=w;w.launcher.start=Mock(side_effect=AssertionError('No execution'));w.installations.start=Mock(side_effect=AssertionError('No installer'))
    w.proton_manager.releases=lambda *a,**k:[];w.present();settle(150);w.show_store()
    ready(w,lambda:len(w.collection_tiles)==2 and all(t.catalog_item['steam_app_id'] for t in w.collection_tiles.values()),'Related lookup completes')
    before=library.path.read_bytes()
    check(all(t.collection_badge.get_text()=='Related saved entry' for t in w.collection_tiles.values()),'Shared Steam marks related, never In library')
    check([t.catalog_context.get_text() for t in w.collection_tiles.values()]==['Bundle · PC','Expanded game · PC'],'Distinct entity/platform labels survive lookup')
    # Refresh the same provider IDs without replacing focusable tile objects.
    tile=w.collection_tiles[334647];tile.grab_focus();frame(w)
    page=w.catalog.browse();page['items'][0]['platforms'].append({'id':3,'name':'Linux'})
    w.render_store(page,refresh=True);settle(50)
    check(w.collection_tiles[334647] is tile and w.focused_control(w) is tile,'Same-ID refresh preserves card and focus')
    check(tile.catalog_context.get_text()=='Bundle · PC +1','Same-ID refresh updates classification')
    for fullscreen in (False,True):
        w.set_tv_mode(fullscreen);w.unfullscreen();w.open_catalog_item(validate_item(provider.detail(334647)))
        ready(w,lambda:w.detail_primary.get_sensitive() and w.detail_related is not None,'Related detail loaded')
        check(not w.saved_detail() and w.detail_primary.get_label()=='Add to library','Related Store record remains explicit Add in '+str(fullscreen))
        check(w.detail_entity.get_text()=='Bundle · PC (Microsoft Windows)','Detail exposes full classification')
        w.detail_related.emit('clicked');settle(100)
        check(w.saved_detail() and w.game==local and w.detail_item is None,'Explicit related navigation keeps legacy UUID and metadata')
        check(w.detail_primary.get_label()=='Play' and library.path.read_bytes()==before,'Related navigation neither rewrites nor launches')
        w.return_from_detail();ready(w,lambda:w.route=='store' and len(w.collection_tiles)==2,'Related Back returns to Store')
    w.open_catalog_item(validate_item(provider.detail(334647)));ready(w,lambda:w.detail_related is not None and w.detail_primary.get_sensitive(),'Bundle relation detail')
    w.show_game_info(w.game);settle(80)
    info=next(c for c in Gtk.Window.get_toplevels() if c.get_visible() and c.get_title()=='Game Info')
    labels=[c.get_text() for c in widgets(info) if isinstance(c,Gtk.Label)]
    check('Included catalog entries' in labels and 'Partial list reported by IGDB.' in labels,'Game Info preserves reported relation direction and partial state')
    reference=next(c for c in widgets(info) if getattr(c,'catalog_reference_id',None)==334254);reference.grab_focus()
    with patch.object(w,'navigation_window',return_value=info):w.controller_action('select')
    ready(w,lambda:w.detail_item and w.detail_item['id']==334254 and not w.catalog_futures,'Explicit reference selection')
    check(not info.get_visible() and not w.saved_detail() and library.path.read_bytes()==before,'Reference selection opens exact component without adding or merging')
    w.show_game_info(w.game);settle(80);component_info=next(c for c in Gtk.Window.get_toplevels() if c.get_visible() and c.get_title()=='Game Info')
    check(any(isinstance(c,Gtk.Label) and c.get_text()=='No originals reported by IGDB.' for c in widgets(component_info)),'Complete empty inverse list does not invent an original')
    with patch.object(w,'navigation_window',return_value=component_info):w.controller_action('back')
    check(not component_info.get_visible(),'Game Info Back cancels without navigation')
    w.show_library();reference.emit('clicked');settle(60)
    check(w.route=='library' and library.path.read_bytes()==before,'Closed modal reference cannot revive a catalog route')
    info_ref=weakref.ref(info);component_ref=weakref.ref(component_info);del info,component_info
    for _ in range(3):gc.collect();settle(60)
    check(info_ref() is None and component_ref() is None,'Closed relationship dialogs release even with an old reference button retained')
    # A repeated click and concurrent exact-ID Add must reuse that exact record,
    # never a Steam-related record. Hold artwork completion to force the race.
    item=validate_item({'id':999,'name':'Concurrent completion','steam_app_id':999,'images':{'portrait':'https://images.igdb.com/igdb/image/upload/t_cover_big/held.jpg'}})
    w.show_shared_detail(item_game(item,preview=True),item)
    started=Event();release=Event();artpath=library.art_dir/next(iter(local['artwork'].values()))
    def held_image(_):started.set();assert release.wait(5);return artpath
    with patch.object(w.catalog,'image',held_image):
        w.detail_action();w.detail_action();ready(w,started.is_set,'Add artwork held')
        incoming=library.new_game();incoming.update(title='Existing exact setup',metadata_source={'provider':'igdb','id':999},metadata_app_id=999,working_dir='/inert/preserve');library.save(incoming)
        after=library.path.read_bytes();release.set();ready(w,lambda:w.saved_detail() and w.game['id']==incoming['id'],'Concurrent exact Add completes')
    check(w.game==incoming and library.path.read_bytes()==after,'Repeated/concurrent Add preserves exact local Setup')
    # Add a component with the same external link; the bundle remains unsaved.
    w.open_catalog_item(validate_item(provider.detail(334254)));ready(w,lambda:w.detail_primary.get_sensitive() and w.detail_related is not None,'Component loaded')
    w.detail_action();w.detail_action();ready(w,w.saved_detail,'Explicit component Add')
    check(w.game['id']!=local['id'] and w.game['metadata_source']=={'provider':'igdb','id':334254},'Component Add creates its own tracked UUID')
    check(not members(library,provider.detail(334647)) and len(related_members(library,provider.detail(334647)))==2,'Adding component never marks bundle In library')
    check(next(g for g in library.games() if g['id']==local['id'])==local,'Legacy settings preserved after explicit component Add')
    w.open_catalog_item(validate_item(provider.detail(334647)));ready(w,lambda:w.detail_related is not None and w.detail_related.get_label()=='Open Library','Multiple related entries')
    w.detail_related.emit('clicked');settle(100);check(w.route=='library','Multiple related entries open Library for explicit selection')
    # A held detail response cannot replace a route after Back/navigation.
    started=Event();release=Event()
    def held_detail(identity):started.set();assert release.wait(5);return validate_item(provider.detail(identity))
    with patch.object(w.catalog,'detail',held_detail):
        w.open_catalog_item(validate_item(provider.detail(334647)));ready(w,started.is_set,'Detail held')
        after=library.path.read_bytes();w.show_library();release.set();settle(150)
    check(w.route=='library' and library.path.read_bytes()==after,'Stale detail completion cannot revive old page or write metadata')
    # Leaving an Add before its artwork completes also cancels the save callback.
    item=validate_item({'id':1001,'name':'Canceled Add','images':{'portrait':'https://images.igdb.com/igdb/image/upload/t_cover_big/canceled.jpg'}})
    started=Event();release=Event()
    with patch.object(w.catalog,'image',held_image):
        w.show_shared_detail(item_game(item,preview=True),item);w.detail_action();ready(w,started.is_set,'Cancelable Add held')
        w.show_library();release.set();settle(150)
    check(not members(library,item) and library.path.read_bytes()==after,'Navigation cancels pending Add without library writes')
    check(not w.launcher.start.called and not w.installations.start.called,'No game or installer dispatch')
    w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True);w.destroy();app.quit()
print(f'PASS: {len(checks)} exact entity/related-entry/async navigation assertions; inert native fixture only.')
