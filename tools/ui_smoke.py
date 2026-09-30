"""Exercise native UI against an isolated demo library; never uses real Steam."""
import os
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('GSK_RENDERER','cairo')
from steam_library.app import Application,Window
from steam_library.demo import prepare_demo
from gi.repository import Adw,Gio,GLib,Gtk


def pump_until(condition,timeout=5):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)
        if condition(): return
        time.sleep(.01)
    raise AssertionError('Native UI condition timed out')


def settle():
    ready=[False]
    GLib.timeout_add(180,lambda:(ready.__setitem__(0,True),False)[-1])
    pump_until(lambda:ready[0])


def buttons(widget):
    if isinstance(widget,Gtk.Button): yield widget
    child=widget.get_first_child()
    while child:
        yield from buttons(child); child=child.get_next_sibling()


def click_window(title,button_text):
    target=next(w for w in Gtk.Window.get_toplevels() if w.get_title()==title)
    match=next(b for b in buttons(target) if b.get_label()==button_text)
    match.emit('clicked')


with tempfile.TemporaryDirectory() as temp:
    os.environ['XDG_CACHE_HOME']=temp
    library=prepare_demo(seed=True)
    app=Application(demo=True); app.set_flags(Gio.ApplicationFlags.NON_UNIQUE); app.register(None)
    w=Window(app,library,demo=True); w.present(); settle()
    def screenshot(name):
        settle()
        paintable=Gtk.WidgetPaintable.new(w); snapshot=Gtk.Snapshot()
        paintable.snapshot(snapshot,w.get_width(),w.get_height())
        texture=w.get_renderer().render_texture(snapshot.to_node(),None)
        texture.save_to_png(str(Path(__file__).resolve().parents[1]/'docs/screenshots'/name))
    w.theme.set_selected(1); screenshot('library-light.png')
    w.theme.set_selected(2); screenshot('library-dark.png')
    game=library.games()[0]; w.show_game(game)
    w.fields['title'].set_text('Nebula Drift — reviewed')
    assert w.dirty()
    w.save_game(False)
    assert library.games()[0]['title']=='Nebula Drift — reviewed'
    assert library.status(library.games()[0])=='Not synced'
    assert not (library.root/'steam/userdata/123/config/shortcuts.vdf').exists()
    screenshot('details-dark.png')
    assert w.cover.get_height()<220, 'Detail header cover must stay compact'
    w.set_default_size(920,640); w.detail_tabs.set_visible_child_name('steam'); settle()
    adjustment=w.detail_tabs.get_visible_child().get_vadjustment()
    assert adjustment.get_page_size()>100, 'Detail form must have usable viewport height'
    assert adjustment.get_upper()>adjustment.get_page_size(), 'Long details must be scrollable'
    adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size()); settle()
    assert adjustment.get_value()>0, 'Detail scrollbar must reach lower fields'
    w.set_default_size(1120,800); w.detail_tabs.set_visible_child_name('overview'); settle()
    w.save_game(True)
    click_window('Choose Steam account','Steam account 123')
    pump_until(lambda:not w.busy)
    assert not (library.root/'steam/userdata/123/config/shortcuts.vdf').exists()
    click_window('Review Steam changes','Confirm sync to Steam')
    pump_until(lambda:not w.busy)
    assert library.status(library.games()[0])=='Synced'
    w.engine.undo(w.engine.latest_backup())
    assert not (library.root/'steam/userdata/123/config/shortcuts.vdf').exists()
    archive=Path(temp)/'backup.zip'; library.export_zip(archive)
    assert library.preview_import(archive)['conflicts']==3
    library.import_zip(archive,'replace')
    assert all(g['sync'] is None for g in library.games())
    w.show_library(); w.filter.set_text('Nebula'); w.render_cards()
    assert len(list(w.flow))==1
    w.show_game(library.games()[0]); w.delete_game()
    dialog=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog))
    dialog.emit('response','confirm'); settle()
    assert len(library.games())==2
    w.open_settings(); settle()
    settings=next(d for d in Gtk.Window.get_toplevels() if d.get_title()=='Settings')
    assert any(b.get_label()=='Export ZIP' for b in buttons(settings))
    assert not any(b.get_label()=='Export backup' for b in buttons(w))
    settings.close()
    original_choose=w.choose_file
    def no_picker(*args,**kwargs): raise AssertionError('Add Game must start with metadata search, not file selection')
    w.choose_file=no_picker; w.add_game(); settle()
    assert any(d.get_title()=='Find game metadata' for d in Gtk.Window.get_toplevels())
    click_window('Find game metadata','Cancel')
    assert w.game is None
    w.choose_file=original_choose
    for window in list(Gtk.Window.get_toplevels()): window.destroy()
    w.pool.shutdown(wait=True)
    print('PASS: native themes, library, editing, local save, explicit sync preview, fixture sync, undo, ZIP restore and filtering')
