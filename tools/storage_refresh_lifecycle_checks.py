"""Replaced Storage groups must release callbacks; inert native fixtures only."""
import argparse
import gc
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import weakref

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
assert os.environ.get('GDK_BACKEND')=='broadway'
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).parent)]
from game_library.storage import Volume
from game_library.storage_access import StorageAccess,PrivateStateStore
from game_library.storage_ui import StoragePage
from game_library.dialogs import style_surface
from fullscreen_preview import settle
from gi.repository import Adw,Gtk

args.output.mkdir(parents=True,exist_ok=False);checks=[];observations={}
Gtk.Settings.get_default().set_property('gtk-enable-animations',False)
def check(value,name,**details):
 checks.append({'check':name,'passed':bool(value),**details});print(('PASS ' if value else 'FAIL ')+name,flush=True)
def wait(view):
 end=time.monotonic()+6
 while time.monotonic()<end:
  settle(30)
  if not view.pending:return
 raise AssertionError('Storage worker did not settle')
def collect():
 for _ in range(3):gc.collect();settle(70)
def retained(refs):return sum(ref() is not None for ref in refs)
def widgets(widget):
 yield widget;child=widget.get_first_child()
 while child:yield from widgets(child);child=child.get_next_sibling()

Adw.init();root=Gtk.Window(default_width=900,default_height=700);root.present();settle(80)
try:
 with tempfile.TemporaryDirectory(prefix='storage-refresh-regression-') as tmp:
  folder=Path(tmp);volume=folder/'fixture-partition';volume.mkdir()
  service=StorageAccess(PrivateStateStore(folder/'registry.sqlite3'),lambda:[Volume('fixture-volume','boot:fixture',str(volume),'Fixture SSD partition',1024**3,2*1024**3,device=volume.stat().st_dev)])
  identity=service.register(service.discover()[0],'install')
  for scenario in ('no_refresh','populated_refresh','role_change_refresh'):
   pages=[];parents=[]
   for cycle in range(3):
    parent=style_surface(Adw.PreferencesWindow(title='Inert Storage refresh fixture'),root);view=StoragePage(service,parent);parent.add(view);parent.present();wait(view)
    check(len(view.rows)==1,scenario+' starts populated',cycle=cycle)
    if scenario=='populated_refresh':
     for _ in range(3):view.refresh();wait(view)
    if scenario=='role_change_refresh':
     view.change(lambda:service.add_role(identity,'cache'));wait(view)
     check(set(view.rows[identity]['data']['roles'])=={'install','cache'},'Role change renders current roles',cycle=cycle)
     view.change(lambda:service.remove_role(identity,'cache'));wait(view)
    pages.append(weakref.ref(view));parents.append(weakref.ref(parent));parent.close();settle(60)
    check(not view.active,scenario+' close deactivates page',cycle=cycle)
    del view,parent;collect()
   counts={'pages':retained(pages),'parents':retained(parents)};observations[scenario]=counts
   check(counts=={'pages':0,'parents':0},scenario+' releases all three pages and parents',**counts)
  # A removed menu may still be held by a queued event. Its old callback must
  # be disconnected, rather than acting on a new live set of Storage rows.
  parent=style_surface(Adw.PreferencesWindow(title='Inert stale menu fixture'),root);view=StoragePage(service,parent);parent.add(view);parent.present();wait(view)
  old_menu=view.rows[identity]['menu'];old_menu.popup();settle(50)
  old_action=next(c for c in widgets(old_menu.get_popover()) if isinstance(c,Gtk.Button) and c.get_label()=='Also use for download cache')
  view.refresh();wait(view)
  check(getattr(old_action,'storage_action_handler',None) is None,'Replaced menu action handler is disconnected')
  before=service.snapshot()['registrations'];old_action.emit('clicked');wait(view);settle(50)
  check(service.snapshot()['registrations']==before,'Stale replaced menu cannot change registry roles')
  parent.close();del old_action,old_menu,view,parent;collect()
  check(not (volume/'UmuTronCache').exists() and not (volume/'EmuGames').exists(),'Refresh and role changes never create payload directories')
finally:
 for window in list(Gtk.Window.get_toplevels()):
  if window is not root:window.destroy()
 root.destroy();collect()
(args.output/'results.json').write_text(json.dumps({'checks':checks,'observations':observations,'scope':'Temporary SQLite registry and native weak references; no real partitions, payloads, provider calls or physical input'},indent=2)+'\n')
raise SystemExit(0 if all(c['passed'] for c in checks) else 1)
