"""Native hide/restore and synthetic mode acknowledgments on private bus/Broadway."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

if os.environ.get('GDK_BACKEND')!='broadway':raise SystemExit('Use an owned isolated Broadway display and private bus.')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullscreen_preview import settle
from catalog_fixtures import FixtureCatalog
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library.tray import Tray
from gi.repository import Gdk,Gio,GLib,Gtk

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
checks=[]
def check(value,name):checks.append({'check':name,'passed':bool(value)})
class Invocation:
    def return_value(self,value):self.value=value
def layout(tray):
    reply=Invocation();tray.method(None,None,'/Menu','com.canonical.dbusmenu','GetLayout',GLib.Variant('(iias)',(0,-1,[])),reply)
    return [node[0] for node in reply.value.unpack()[1][2]]
def widgets(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from widgets(child);child=child.get_next_sibling()

with tempfile.TemporaryDirectory(prefix='umutron-tray-mode-') as temp:
    os.environ['XDG_CACHE_HOME']=temp;library=prepare_demo()
    app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name='';controller.return_value.error=''
        w=Window(app,library,demo=True,catalog_provider=FixtureCatalog())
    app.window=w;actions=[];observed=[False]
    # Broadway without a browser client does not acknowledge fullscreen.
    # Inject only the getter and emit normal GObject notifications in this
    # isolated fixture; do not manipulate a live display or backend protocol.
    mode_patch=patch.object(w,'is_fullscreen',lambda:observed[0]);mode_patch.start()
    def acknowledge(value):observed[0]=value;w.notify('fullscreened');settle(80)
    def show():actions.append('show');w.present()
    def switch(value):actions.append(value);show();w.set_tv_mode(value)
    tray=Tray(show,lambda:actions.append('exit'),lambda _:None,lambda:switch(True),lambda:switch(False),lambda:None,mode=w.is_fullscreen)
    app.tray=tray;handler=w.connect('notify::fullscreened',tray.sync_mode)
    w.present();settle(400)
    def check_mode(name):
        check(layout(tray)==[1,4 if w.is_fullscreen() else 3,6,2],name)
        check(tray.last_mode==w.is_fullscreen(),name+' injected acknowledged state')
    try:
        check(not w.is_fullscreen(),'Initial desktop state');check_mode('Initial tray')
        for _ in range(3):
            tray.event(3,'clicked');settle(100)
            check(layout(tray)==[1,3,6,2],'Request alone does not claim fullscreen acknowledgment')
            acknowledge(True)
            check(w.tv_mode and w.is_fullscreen(),'Tray request enters acknowledged fullscreen');check_mode('Fullscreen tray')
            before=list(actions);tray.event(3,'clicked');check(actions==before,'Stale fullscreen action ignored')
            tray.available=True;w.close_requested();settle(100)
            check(not w.get_visible(),'Close hides to tray');check_mode('Hidden fullscreen tray')
            tray.event(1,'clicked');settle(250);check(w.get_visible() and w.is_fullscreen(),'Show restores hidden fullscreen');check_mode('Restored tray')
            tray.event(4,'clicked');settle(100);acknowledge(False)
            check(not w.tv_mode and not w.is_fullscreen(),'Tray request enters acknowledged desktop');check_mode('Desktop tray')
        w.keyboard_controller.emit('key-pressed',Gdk.KEY_F11,0,Gdk.ModifierType(0));settle(100);acknowledge(True)
        check(w.is_fullscreen(),'F11 changes acknowledged mode');check_mode('F11 tray')
        w.open_tv_options();settle(100)
        next(x for x in widgets(w.tv_options_dialog) if isinstance(x,Gtk.Button) and x.get_label()=='Exit fullscreen').emit('clicked');settle(100);acknowledge(False)
        check(not w.is_fullscreen(),'Fullscreen options exits acknowledged mode');check_mode('Options tray')
        # Simulated compositor acknowledgments exercise the registered native
        # GObject notification and mode getter, independent of layout intent.
        w.fullscreen();settle(100);acknowledge(True);check(w.is_fullscreen() and not w.tv_mode,'External-style fullscreen differs from layout flag');check_mode('Native fullscreen notification')
        tray.event(4,'clicked');settle(100);acknowledge(False)
        check(not w.is_fullscreen(),'Tray desktop reapplies request despite matching layout flag')
        w.set_tv_mode(True);settle(100);acknowledge(True);w.unfullscreen();settle(100);acknowledge(False)
        check(not w.is_fullscreen() and w.tv_mode,'External-style exit differs from layout flag');check_mode('Native desktop notification')
        tray.event(3,'clicked');settle(100);acknowledge(True);check(w.is_fullscreen(),'Tray fullscreen reapplies request despite matching layout flag')
        check_mode('Reapplied fullscreen tray')
        tray.event(2,'clicked');check(actions[-1]=='exit','Exit callback retained')
        check(not (library.root/'launch-session.json').exists(),'No game/installer session created')
    finally:
        w.disconnect(handler);tray.close();mode_patch.stop();w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True);w.controller.close();w.destroy();settle()
(args.output/'checks.json').write_text(json.dumps({'checks':checks,'environment':'Owned Broadway native windows/private bus; fullscreen getter and GObject notifications injected because this backend has no fullscreen acknowledgment. Real hide/restore and callbacks; no live tray/compositor or raw input'},indent=2)+'\n')
for item in checks:
    if not item['passed']:print('FAIL: '+item['check'])
print(f'{sum(item["passed"] for item in checks)}/{len(checks)} native tray checks passed')
assert all(item['passed'] for item in checks)
