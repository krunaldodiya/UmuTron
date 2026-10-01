"""GTK4-compatible StatusNotifierItem and mode-switching DBusMenu, using Gio only."""
from gi.repository import Gio, GLib

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
</interface></node>'''


def close_action(tray_available):return 'hide' if tray_available else 'minimize'


class Tray:
    def __init__(self,show,exit_app,changed,fullscreen=None,desktop=None,activity=None,settings=None,appearance=None):
        self.fullscreen=fullscreen;self.desktop=desktop;self.activity=activity;self.settings=settings;self.appearance=appearance
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

    @staticmethod
    def properties(item):
        if item==0:return {'children-display':GLib.Variant('s','submenu')}
        return {'label':GLib.Variant('s',{1:'Show Launcher',2:'Exit',3:'Switch to Fullscreen',4:'Switch to Desktop',5:'Activity',6:'Settings',7:'Appearance'}.get(item,'')),'enabled':GLib.Variant('b',True),'visible':GLib.Variant('b',True)}

    def property(self,connection,sender,path,interface,name):
        if interface=='com.canonical.dbusmenu':
            return {'Version':GLib.Variant('u',3),'TextDirection':GLib.Variant('s','ltr'),'Status':GLib.Variant('s','normal'),'IconThemePath':GLib.Variant('as',[])}.get(name)
        values={'Category':('s','ApplicationStatus'),'Id':('s','game-library-launcher'),'Title':('s','Game Library Launcher'),'Status':('s','Active'),
                'IconName':('s','applications-games'),'IconThemePath':('s',''),'AttentionIconName':('s',''),'OverlayIconName':('s',''),
                'IconPixmap':('a(iiay)',[]),'AttentionIconPixmap':('a(iiay)',[]),'OverlayIconPixmap':('a(iiay)',[]),
                'Menu':('o','/Menu'),'ItemIsMenu':('b',False),'WindowId':('u',0),'ToolTip':('(sa(iiay)ss)',('applications-games',[],'Game Library Launcher','Show Launcher or Exit'))}
        return GLib.Variant(*values[name]) if name in values else None

    def event(self,item,event):
        if event=='clicked':
            if item==1:self.show()
            elif item==2:self.exit_app()
            elif item==3 and self.fullscreen:self.fullscreen()
            elif item==4 and self.desktop:self.desktop()
            elif item==5 and self.activity:self.activity()
            elif item==6 and self.settings:self.settings()
            elif item==7 and self.appearance:self.appearance()

    def method(self,connection,sender,path,interface,method,parameters,invocation):
        args=parameters.unpack()
        if interface=='org.kde.StatusNotifierItem':
            if method in ('Activate','SecondaryActivate','ContextMenu'):self.show()
            invocation.return_value(None);return
        if method=='GetLayout':
            item,depth,_=args
            children=[GLib.Variant('(ia{sv}av)',(i,self.properties(i),[])) for i in (1,3,4,5,6,7,2)] if item==0 and depth!=0 else []
            result=GLib.Variant('(u(ia{sv}av))',(1,(item,self.properties(item),children)))
        elif method=='GetGroupProperties':result=GLib.Variant('(a(ia{sv}))',([(i,self.properties(i)) for i in args[0] if i in (0,1,2,3,4,5,6,7)],))
        elif method=='GetProperty':result=GLib.Variant('(v)',(self.properties(args[0]).get(args[1],GLib.Variant('s','')),))
        elif method=='Event':self.event(args[0],args[1]);result=None
        elif method=='EventGroup':
            for item,event,_,_ in args[0]:self.event(item,event)
            result=GLib.Variant('(ai)',([],))
        elif method=='AboutToShow':result=GLib.Variant('(b)',(False,))
        elif method=='AboutToShowGroup':result=GLib.Variant('(aiai)',([],[]))
        else:invocation.return_dbus_error('com.canonical.dbusmenu.UnknownMethod','Unknown method');return
        invocation.return_value(result)

    def close(self):
        if hasattr(self,'watch'):Gio.bus_unwatch_name(self.watch)
        if self.connection:
            for subscription in self.signals:self.connection.signal_unsubscribe(subscription)
            for registration in self.registrations:self.connection.unregister_object(registration)
