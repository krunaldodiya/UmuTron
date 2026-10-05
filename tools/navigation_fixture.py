"""Shared existing native key/frame/readiness helpers; no host input or capture."""
from fullscreen_preview import settle
from gi.repository import Gdk,GLib,Gtk

def key(window,value,state=Gdk.ModifierType(0)):
    return window.keyboard_controller.emit('key-pressed',value,0,state)
def frame(window):
    # Request a real fixture frame; Broadway without a browser may otherwise
    # retain a pending route tick despite nonzero measurement allocations.
    window.set_visible(False);window.present();settle(700)
    window.queue_draw();settle(300)
    paintable=Gtk.WidgetPaintable.new(window);snap=Gtk.Snapshot();paintable.snapshot(snap,window.get_width(),window.get_height())
    node=snap.to_node()
    if node is not None:window.get_renderer().render_texture(node,None)
    settle(350)


def ready(window,predicate,description):
    """Await the asserted GTK state; request frames without changing focus.

    Frame ticks, focus notifications and actual scroll adjustments supply
    readiness. The timeout is only a failure bound, never the success signal.
    """
    loop=GLib.MainLoop();outcome={'ready':False}
    def inspect(*_):
        if predicate():outcome['ready']=True;loop.quit()
        return True
    def request():
        window.queue_draw()
        paintable=Gtk.WidgetPaintable.new(window);snap=Gtk.Snapshot()
        paintable.snapshot(snap,window.get_width(),window.get_height());node=snap.to_node()
        if node is not None:window.get_renderer().render_texture(node,None)
        inspect();return True
    def timeout():loop.quit();return True
    tick=window.add_tick_callback(inspect);focus=window.connect('notify::focus-widget',inspect)
    redraw=GLib.timeout_add(25,request);deadline=GLib.timeout_add_seconds(8,timeout)
    try:
        request()
        if not outcome['ready']:loop.run()
    finally:
        window.remove_tick_callback(tick);window.disconnect(focus)
        GLib.source_remove(redraw);GLib.source_remove(deadline)
    if not outcome['ready']:
        control=window.focused_control(window);scroll=window.tv_page if window.route=='home' else getattr(window,'collection_scroll',None)
        bounds=control.compute_bounds(scroll)[1] if control and scroll else None
        print('READINESS',description,'route',window.route,'logical',window.tv_selected_id,'home_section',getattr(window,'home_focus_section',None),'focus',control,'bounds',([bounds.get_x(),bounds.get_y(),bounds.get_width(),bounds.get_height()] if bounds else None),'viewport',([scroll.get_width(),scroll.get_height(),scroll.get_vadjustment().get_value()] if scroll else None),'focused_home_ids',[gid for gid,t in getattr(window,'home_setup_tiles',[]) if t is control],flush=True)
    assert outcome['ready'],'Native readiness failed: '+description


def visible_in(control,scroll):
    valid,bounds=control.compute_bounds(scroll)
    return (control.get_mapped() and control.get_width()>0 and valid and bounds.get_y()>=-1
            and bounds.get_y()+bounds.get_height()<=scroll.get_height()+1)


def after_frames(window,predicate,description,frames=3):
    """Exercise queued native frame callbacks before asserting final state."""
    seen=0
    def tick(*_):
        nonlocal seen
        seen+=1;return True
    callback=window.add_tick_callback(tick)
    try:ready(window,lambda:seen>=frames and predicate(),description)
    finally:window.remove_tick_callback(callback)
