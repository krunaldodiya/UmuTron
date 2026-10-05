"""Inert Storage controller/lifetime regressions; never touches host drives/input."""
import argparse
import gc
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import weakref
from threading import Event
from unittest.mock import patch

p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
assert os.environ.get('GDK_BACKEND')=='broadway'
sys.path[:0]=[str(args.source),str(args.source/'tools')]
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library.storage import Volume
from game_library.storage_access import StorageAccess,PrivateStateStore,DemoStorage
from game_library.storage_ui import StoragePage
from game_library.dialogs import style_surface
from catalog_fixtures import FixtureCatalog
from fullscreen_preview import settle
from storage_integration_checks import capture
from gi.repository import Adw,Gio,Gtk

args.output.mkdir(parents=True,exist_ok=False);checks=[];observations={}
Gtk.Settings.get_default().set_property('gtk-enable-animations',False)
def check(value,name,**details):
 checks.append({'check':name,'passed':bool(value),**details});print(('PASS ' if value else 'FAIL ')+name,flush=True)
def wait(predicate):
 until=time.monotonic()+6
 while time.monotonic()<until:
  settle(30)
  if predicate():return
 raise AssertionError('Async fixture did not settle')
def collect():
 for _ in range(3):gc.collect();settle(80)
def widgets(widget):
 yield widget;child=widget.get_first_child()
 while child:yield from widgets(child);child=child.get_next_sibling()
def retain(refs):return sum(ref() is not None for ref in refs)

with tempfile.TemporaryDirectory(prefix='umu-storage-regression-') as tmp:
 root=Path(tmp);volumes=[]
 for name in ('a','b','c'):
  path=root/name;path.mkdir();volumes.append(Volume(name,'boot:'+name,str(path),'Fixture partition '+name.upper(),1000,2000,device=path.stat().st_dev))
 volumes.append(Volume('external','boot:e','/fixture/external','Unsupported fixture',1000,2000,support_reason='External partition unsupported'))
 service=StorageAccess(PrivateStateStore(root/'registry.sqlite3'),lambda:list(volumes));identity=service.register(volumes[0],'install')
 library=prepare_demo(True);before=library.path.read_bytes();app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
 with patch('game_library.app.Controller') as controller:
  controller.return_value.name=controller.return_value.error='';w=Window(app,library,demo=True,catalog_provider=FixtureCatalog(),storage_service=service)
 app.window=w;w.proton_manager.releases=lambda *a,**k:[];w.present();settle(100);w.set_tv_mode(True);w.unfullscreen()
 try:
  w.open_settings('storage');wait(lambda:not w.storage_settings_page.pending);settings=w.settings_dialog;page=w.storage_settings_page
  menu=page.rows[identity]['menu'];popup=menu.get_popover();menu.popup();settle(100)
  with patch.object(w,'navigation_window',return_value=settings):
   check(w.controller_popover(settings) is popup,'Owned modal drive menu is recognized')
   first=next(c for c in widgets(popup) if isinstance(c,Gtk.Button));first.grab_focus()
   w.controller_action('next');settle(30)
   check(bool(w.focused_control(settings) and w.focused_control(settings).is_ancestor(popup)),'Controller traversal stays inside drive menu')
   w.controller_action('back');settle(100)
   check(settings.get_visible() and page.active and not popup.get_mapped(),'Back closes only the drive menu')
   check(w.focused_control(settings) is menu,'Back restores focus to Drive options')
  if w.settings_dialog:w.settings_dialog.close()
  w.open_settings('storage');wait(lambda:not w.storage_settings_page.pending);page=w.storage_settings_page;page.open_picker('install');picker=page.picker;wait(lambda current=picker:not current.pending)
  a,b,c,disabled=[control for _,control in picker.options]
  check(not a.is_sensitive() and b.is_sensitive() and c.is_sensitive() and not disabled.is_sensitive(),'Only unregistered supported partitions are eligible')
  cancel=next(control for control in widgets(picker) if isinstance(control,Gtk.Button) and control.get_label()=='Cancel');cancel.grab_focus()
  seen=[]
  with patch.object(w,'navigation_window',return_value=picker):
   for _ in range(12):
    w.controller_action('next');settle(15);seen.append(w.focused_control(picker))
   check(b in seen and c in seen,'Controller traversal reaches both eligible partition choices')
   check(a not in seen and disabled not in seen,'Controller traversal skips unavailable partition choices')
   b.grab_focus();w.controller_action('select');settle(50)
   check(b.get_active() and picker.selected is volumes[1] and picker.confirm.is_sensitive(),'Select toggles eligible partition and enables Add drive')
   w.controller_action('next');settle(30)
   check(w.focused_control(picker) is c,'Next reaches the next eligible partition')
   w.controller_action('select');settle(50)
   check(c.get_active() and not b.get_active() and picker.selected is volumes[2],'Select changes the single selected partition')
   # Restore B via actual controller dispatch; no direct set_active shortcut.
   b.grab_focus();w.controller_action('select');settle(40)
   capture(picker,args.output/'partition-controller-focus.png',picker.get_width(),picker.get_height())
   if picker.confirm.is_sensitive():
    picker.confirm.grab_focus();w.controller_action('select');wait(lambda current=picker,owner=page:not current.active and not owner.pending)
   check(any(row['volume_id']=='b' for row in service.snapshot()['registrations']),'Controller Add commits exactly the selected partition')
  check(library.path.read_bytes()==before,'Drive registration leaves game metadata unchanged')
  if picker.active:picker.close()
  w.settings_dialog.close();settle(80)
  # Direct weak-reference comparison matching the independent review, plus
  # real Settings cycles to catch a stale Window.storage_settings_page owner.
  retained={}
  for variant in ('control','storage'):
   parents=[];pages=[]
   for index in range(3):
    parent=style_surface(Adw.PreferencesWindow(title=variant+' fixture'),w)
    if variant=='storage':
     instance=StoragePage(DemoStorage(),parent);parent.add(instance);wait(lambda current=instance:not current.pending);pages.append(weakref.ref(instance))
    parent.present();settle(40);parents.append(weakref.ref(parent));parent.close();settle(80)
    if variant=='storage':check(not instance.active,'Closed page cancels work',cycle=index);del instance
    del parent;collect()
   retained[variant]={'parents':retain(parents),'pages':retain(pages)}
  check(retained['control']=={'parents':0,'pages':0},'No-page native control releases all parents')
  check(retained['storage']=={'parents':0,'pages':0},'Three closed Storage pages and parents are released')
  observations['direct_lifetime']=retained
  del settings,page,menu,popup,first,picker,a,b,c,disabled,cancel,seen
  parents=[];pages=[]
  for index in range(3):
   w.set_tv_mode(index%2==0);w.unfullscreen();w.open_settings('storage' if w.tv_mode else None);wait(lambda:not w.storage_settings_page.pending)
   parent=w.settings_dialog;instance=w.storage_settings_page;parents.append(weakref.ref(parent));pages.append(weakref.ref(instance))
   parent.close();settle(100)
   check(w.settings_dialog is None and getattr(w,'storage_settings_page',None) is None,'Closed real Settings clears both owner references',cycle=index)
   del parent,instance;collect()
  observations['settings_lifetime']={'parents':retain(parents),'pages':retain(pages)}
  def owner_kinds(ref):
   obj=ref()
   if obj is None:return []
   return [{'kind':type(v).__name__,'keys':[str(k) for k,x in v.items() if x is obj]} if isinstance(v,dict) else {'kind':type(v).__name__} for v in gc.get_referrers(obj)]
  observations['settings_referrers']=[owner_kinds(ref) for ref in parents]
  print(json.dumps(observations['settings_referrers']),flush=True)
  check(retain(parents)==0 and retain(pages)==0,'Repeated real Settings releases pages and windows')
  # Closing with outstanding discovery cannot re-populate, save or keep a page.
  w.set_tv_mode(True);w.unfullscreen();w.open_settings('storage');wait(lambda:not w.storage_settings_page.pending)
  parent=w.settings_dialog;instance=w.storage_settings_page;release=Event();started=Event();original=service.choices
  def held():started.set();release.wait(4);return original()
  with patch.object(service,'choices',new=held):
   instance.open_picker('install');child=instance.picker;wait(started.is_set);refs=[weakref.ref(parent),weakref.ref(instance),weakref.ref(child)];parent.close();release.set();settle(200)
   check(not instance.active and not child.active and not child.options,'Parent close rejects late picker discovery')
  del parent,instance,child;collect()
  check(retain(refs)==0,'Closed parent, page and held picker release after worker finishes')
  check(library.path.read_bytes()==before,'All navigation and lifecycle checks preserve saved metadata')
 finally:
  for target in list(Gtk.Window.get_toplevels()):
   if target is not w:target.destroy()
  w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True,cancel_futures=True);w.controller.close();w.destroy();settle(100)
args.output.joinpath('results.json').write_text(json.dumps({'checks':checks,'observations':observations,'scope':'Synthetic native GTK method/signal and weak-reference fixtures; no physical input or host drives'},indent=2)+'\n')
raise SystemExit(0 if all(c['passed'] for c in checks) else 1)
