"""GTK4-compatible StatusNotifierItem and mode-switching DBusMenu, using Gio only."""
from pathlib import Path
from gi.repository import Gio, GLib
from . import APP_NAME, ICON_NAME


def _load_icon_pixmaps():
    candidates = [
        Path(__file__).resolve().parents[1] / 'assets/umutron.svg',
        Path.home() / '.local/share/icons/hicolor/scalable/apps/umutron.svg',
        Path.home() / '.local/share/icons/hicolor/scalable/apps/game-library-launcher.svg',
    ]
    svg_path = next((p for p in candidates if p.is_file()), None)
    if not svg_path:
        return []
    try:
        import gi
        gi.require_version('GdkPixbuf', '2.0')
        from gi.repository import GdkPixbuf
        pixmaps = []
        for s in (16, 22, 24, 32, 48):
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(svg_path), s, s, True)
            w, h = pb.get_width(), pb.get_height()
            pixels = pb.get_pixels()
            stride = pb.get_rowstride()
            n_ch = pb.get_n_channels()
            has_a = pb.get_has_alpha()
            argb = bytearray(w * h * 4)
            dst = 0
            for y in range(h):
                row_start = y * stride
                for x in range(w):
                    off = row_start + x * n_ch
                    argb[dst] = pixels[off + 3] if has_a else 255
                    argb[dst + 1] = pixels[off]
                    argb[dst + 2] = pixels[off + 1]
                    argb[dst + 3] = pixels[off + 2]
                    dst += 4
            pixmaps.append((w, h, bytes(argb)))
        return pixmaps
    except Exception:
        return []


_ICON_PIXMAPS = None


def get_icon_pixmaps():
    global _ICON_PIXMAPS
    if _ICON_PIXMAPS is None:
        _ICON_PIXMAPS = _load_icon_pixmaps()
    return _ICON_PIXMAPS
ITEM_XML='''<node><interface name="org.kde.StatusNotifierItem">
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
<property name="IconName" type="s" access="read"/><property name="IconPixmap" type="a(iiay)" access="read"/>
<property name="IconThemePath" type="s" access="read"/><property name="AttentionIconName" type="s" access="read"/>
<property name="AttentionIconPixmap" type="a(iiay)" access="read"/><property name="OverlayIconName" type="s" access="read"/>
<property name="OverlayIconPixmap" type="a(iiay)" access="read"/><property name="Menu" type="o" access="read"/>
<property name="ItemIsMenu" type="b" access="read"/><property name="WindowId" type="u" access="read"/>
<property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
<signal name="NewStatus"><arg type="s"/></signal><signal name="NewIcon"/>
</interface></node>'''
MENU_XML='''<node><interface name="com.canonical.dbusmenu">
<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/><arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
<method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/></method>
<method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/></method>
<method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
<method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
<method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/></method>
<property name="Version" type="u" access="read"/><property name="TextDirection" type="s" access="read"/><property name="Status" type="s" access="read"/><property name="IconThemePath" type="as" access="read"/>
<signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
</interface></node>'''


def close_action(tray_available):return 'hide' if tray_available else 'minimize'


class Tray:
    def __init__(self,show,exit_app,changed,fullscreen=None,desktop=None,settings=None,mode=None):
        self.fullscreen=fullscreen;self.desktop=desktop;self.settings=settings
        self.mode=mode or (lambda:False);self.last_mode=bool(self.mode());self.revision=1
        self.show=show;self.exit_app=exit_app;self.changed=changed;self.available=False;self.connection=None;self.registrations=[];self.owner=None;self.signals=[]
        try:
            self.connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
            for path,xml in (('/StatusNotifierItem',ITEM_XML),('/Menu',MENU_XML)):
                info=Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0]
                self.registrations.append(self.connection.register_object(path,info,self.method,self.property,None))
            for event in ('StatusNotifierHostRegistered','StatusNotifierHostUnregistered'):
                self.signals.append(self.connection.signal_subscribe('org.kde.StatusNotifierWatcher','org.kde.StatusNotifierWatcher',event,'/StatusNotifierWatcher',None,Gio.DBusSignalFlags.NONE,self.host_signal))
            self.watch=Gio.bus_watch_name_on_connection(self.connection,'org.kde.StatusNotifierWatcher',Gio.BusNameWatcherFlags.NONE,self.appeared,self.vanished)
        except GLib.Error:self.changed(False)

    def appeared(self,connection,name,owner):
        self.owner=owner
        def done(conn,result):
            try:conn.call_finish(result)
            except GLib.Error:self.available=False;self.changed(False);return
            def host_done(bus,response):
                try:available=bool(bus.call_finish(response).unpack()[0]) and self.owner==owner
                except GLib.Error:available=False
                self.available=available;self.changed(available)
            conn.call(name,'/StatusNotifierWatcher','org.freedesktop.DBus.Properties','Get',GLib.Variant('(ss)',('org.kde.StatusNotifierWatcher','IsStatusNotifierHostRegistered')),GLib.VariantType.new('(v)'),Gio.DBusCallFlags.NONE,3000,None,host_done)
        connection.call(name,'/StatusNotifierWatcher','org.kde.StatusNotifierWatcher','RegisterStatusNotifierItem',GLib.Variant('(s)',(connection.get_unique_name(),)),None,Gio.DBusCallFlags.NONE,3000,None,done)

    def host_signal(self,connection,sender,path,interface,event,parameters):
        if event=='StatusNotifierHostUnregistered':self.available=False;self.changed(False)
        elif self.owner:self.appeared(connection,'org.kde.StatusNotifierWatcher',self.owner)

    def vanished(self,*_):
        self.owner=None;self.available=False;self.changed(False)

    def sync_mode(self,*_):
        current=bool(self.mode())
        if current==self.last_mode:return False
        self.last_mode=current;self.revision=(self.revision+1)&0xffffffff
        if self.connection:
            self.connection.emit_signal(None,'/Menu','com.canonical.dbusmenu','LayoutUpdated',GLib.Variant('(ui)',(self.revision,0)))
        return True

    def items(self):return (1,4 if self.last_mode else 3,6,2)

    def properties(self,item):
        if item==0:return {'children-display':GLib.Variant('s','submenu')}
        return {'label':GLib.Variant('s',{1:'Show '+APP_NAME,2:'Exit',3:'Switch to fullscreen',4:'Switch to desktop',6:'Settings'}.get(item,'')),'enabled':GLib.Variant('b',item in self.items()),'visible':GLib.Variant('b',item in self.items())}

    def property(self,connection,sender,path,interface,name):
        if interface=='com.canonical.dbusmenu':
            return {'Version':GLib.Variant('u',3),'TextDirection':GLib.Variant('s','ltr'),'Status':GLib.Variant('s','normal'),'IconThemePath':GLib.Variant('as',[])}.get(name)
        pixmaps = get_icon_pixmaps()
        theme_path = str(Path.home() / '.local/share/icons/hicolor')
        values={'Category':('s','ApplicationStatus'),'Id':('s','game-library-launcher'),'Title':('s',APP_NAME),'Status':('s','Active'),
                'IconName':('s',ICON_NAME),'IconThemePath':('s',theme_path),'AttentionIconName':('s',''),'OverlayIconName':('s',''),
                'IconPixmap':('a(iiay)',pixmaps),'AttentionIconPixmap':('a(iiay)',[]),'OverlayIconPixmap':('a(iiay)',[]),
                'Menu':('o','/Menu'),'ItemIsMenu':('b',False),'WindowId':('u',0),'ToolTip':('(sa(iiay)ss)',(ICON_NAME,pixmaps,APP_NAME,'Show '+APP_NAME+' or Exit'))}
        return GLib.Variant(*values[name]) if name in values else None

    def event(self,item,event):
        self.sync_mode()
        if event=='clicked' and item in self.items():
            if item==1:self.show()
            elif item==2:self.exit_app()
            elif item==3 and self.fullscreen:self.fullscreen()
            elif item==4 and self.desktop:self.desktop()
            elif item==6 and self.settings:self.settings()
            self.sync_mode()

    def method(self,connection,sender,path,interface,method,parameters,invocation):
        args=parameters.unpack()
        changed=self.sync_mode()
        if interface=='org.kde.StatusNotifierItem':
            if method in ('Activate','SecondaryActivate','ContextMenu'):self.show()
            invocation.return_value(None);return
        if method=='GetLayout':
            item,depth,_=args
            children=[GLib.Variant('(ia{sv}av)',(i,self.properties(i),[])) for i in self.items()] if item==0 and depth!=0 else []
            result=GLib.Variant('(u(ia{sv}av))',(self.revision,(item,self.properties(item),children)))
        elif method=='GetGroupProperties':result=GLib.Variant('(a(ia{sv}))',([(i,self.properties(i)) for i in args[0] if i in (0,*self.items())],))
        elif method=='GetProperty':result=GLib.Variant('(v)',(self.properties(args[0]).get(args[1],GLib.Variant('s','')),))
        elif method=='Event':self.event(args[0],args[1]);result=None
        elif method=='EventGroup':
            for item,event,_,_ in args[0]:self.event(item,event)
            result=GLib.Variant('(ai)',([],))
        elif method=='AboutToShow':result=GLib.Variant('(b)',(changed,))
        elif method=='AboutToShowGroup':result=GLib.Variant('(aiai)',([0] if changed and 0 in args[0] else [],[]))
        else:invocation.return_dbus_error('com.canonical.dbusmenu.UnknownMethod','Unknown method');return
        invocation.return_value(result)

    def close(self):
        if hasattr(self,'watch'):Gio.bus_unwatch_name(self.watch)
        if self.connection:
            for subscription in self.signals:self.connection.signal_unsubscribe(subscription)
            for registration in self.registrations:self.connection.unregister_object(registration)
