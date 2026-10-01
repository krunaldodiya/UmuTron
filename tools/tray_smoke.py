"""Exercise the real tray protocol on a private bus: dbus-run-session python3 tools/tray_smoke.py."""
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gi.repository import Gio,GLib
from game_library.tray import Tray


def pump(condition):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if condition():return
        time.sleep(.01)
    raise AssertionError('Tray protocol timed out')


conn=Gio.bus_get_sync(Gio.BusType.SESSION,None)
xml='''<node><interface name="org.kde.StatusNotifierWatcher"><method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method><property name="IsStatusNotifierHostRegistered" type="b" access="read"/><signal name="StatusNotifierHostUnregistered"/></interface></node>'''
registered=[];changes=[];actions=[]
def register(connection,sender,path,interface,method,parameters,invocation):registered.append(parameters.unpack()[0]);invocation.return_value(None)
obj=conn.register_object('/StatusNotifierWatcher',Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0],register,lambda *_:GLib.Variant('b',True),None)
owner=Gio.bus_own_name_on_connection(conn,'org.kde.StatusNotifierWatcher',Gio.BusNameOwnerFlags.NONE,None,None)
tray=Tray(lambda:actions.append('show'),lambda:actions.append('exit'),changes.append,lambda:actions.append('fullscreen'),lambda:actions.append('desktop'))
pump(lambda:tray.available);assert registered[-1]==conn.get_unique_name()
def call(path,interface,method,parameters):
    outcome=[]
    def done(c,result):outcome.append(c.call_finish(result))
    conn.call(conn.get_unique_name(),path,interface,method,parameters,None,Gio.DBusCallFlags.NONE,2000,None,done)
    pump(lambda:bool(outcome));return outcome[0]
layout=call('/Menu','com.canonical.dbusmenu','GetLayout',GLib.Variant('(iias)',(0,-1,[]))).unpack()
assert [node[1]['label'] for node in layout[1][2]]==['Show Launcher','Switch to Fullscreen','Switch to Desktop','Exit']
call('/StatusNotifierItem','org.kde.StatusNotifierItem','Activate',GLib.Variant('(ii)',(0,0)))
for item in (1,3,4,2):call('/Menu','com.canonical.dbusmenu','Event',GLib.Variant('(isvu)',(item,'clicked',GLib.Variant('i',0),0)))
assert actions==['show','show','fullscreen','desktop','exit']
conn.emit_signal(None,'/StatusNotifierWatcher','org.kde.StatusNotifierWatcher','StatusNotifierHostUnregistered',None)
pump(lambda:not tray.available);assert changes[-1] is False
Gio.bus_unown_name(owner);tray.close();conn.unregister_object(obj)
print('PASS: tray registration, host detection/loss, icon activation, Show Launcher/Exit DBus menu')
