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
mode=[False]
def switch(value):actions.append('fullscreen' if value else 'desktop');mode[0]=value
def register(connection,sender,path,interface,method,parameters,invocation):registered.append(parameters.unpack()[0]);invocation.return_value(None)
obj=conn.register_object('/StatusNotifierWatcher',Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0],register,lambda *_:GLib.Variant('b',True),None)
owner=Gio.bus_own_name_on_connection(conn,'org.kde.StatusNotifierWatcher',Gio.BusNameOwnerFlags.NONE,None,None)
tray=Tray(lambda:actions.append('show'),lambda:actions.append('exit'),changes.append,lambda:switch(True),lambda:switch(False),lambda:actions.append('settings'),mode=lambda:mode[0])
updates=[]
subscription=conn.signal_subscribe(None,'com.canonical.dbusmenu','LayoutUpdated','/Menu',None,Gio.DBusSignalFlags.NONE,lambda *args:updates.append(args[-1].unpack()))
pump(lambda:tray.available);assert registered[-1]==conn.get_unique_name()
def call(path,interface,method,parameters):
    outcome=[]
    def done(c,result):outcome.append(c.call_finish(result))
    conn.call(conn.get_unique_name(),path,interface,method,parameters,None,Gio.DBusCallFlags.NONE,2000,None,done)
    pump(lambda:bool(outcome));return outcome[0]
properties=call('/StatusNotifierItem','org.freedesktop.DBus.Properties','GetAll',GLib.Variant('(s)',('org.kde.StatusNotifierItem',))).unpack()[0]
assert properties['Id']=='game-library-launcher'
assert properties['Title']=='UmuTron' and properties['IconName']=='game-library-launcher'
assert properties['ToolTip']==('game-library-launcher',[],'UmuTron','Show UmuTron or Exit')
layout=call('/Menu','com.canonical.dbusmenu','GetLayout',GLib.Variant('(iias)',(0,-1,[]))).unpack()
assert [node[1]['label'] for node in layout[1][2]]==['Show UmuTron','Switch to fullscreen','Settings','Exit']
call('/StatusNotifierItem','org.kde.StatusNotifierItem','Activate',GLib.Variant('(ii)',(0,0)))
for item in (1,3,4,6,2):call('/Menu','com.canonical.dbusmenu','Event',GLib.Variant('(isvu)',(item,'clicked',GLib.Variant('i',0),0)))
assert actions==['show','show','fullscreen','desktop','settings','exit']
for current in (True,False,True,False):
    mode[0]=current;tray.sync_mode()
    layout=call('/Menu','com.canonical.dbusmenu','GetLayout',GLib.Variant('(iias)',(0,-1,[]))).unpack()
    assert [node[0] for node in layout[1][2]]==[1,4 if current else 3,6,2]
    before=list(actions)
    stale=3 if current else 4
    call('/Menu','com.canonical.dbusmenu','Event',GLib.Variant('(isvu)',(stale,'clicked',GLib.Variant('i',0),0)))
    assert actions==before,'A stale hidden mode action must not execute'
pump(lambda:len(updates)>=6)
assert all(update[1]==0 for update in updates)
conn.emit_signal(None,'/StatusNotifierWatcher','org.kde.StatusNotifierWatcher','StatusNotifierHostUnregistered',None)
pump(lambda:not tray.available);assert changes[-1] is False
Gio.bus_unown_name(owner);tray.close();conn.signal_unsubscribe(subscription);conn.unregister_object(obj)
print('PASS: tray protocol, opposite-mode-only menu, repeated updates/revisions, stale-action rejection, Show/Settings/Exit, host loss')
