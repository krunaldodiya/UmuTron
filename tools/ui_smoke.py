"""Exercise native UI against an isolated demo library; never uses real Steam."""
import os
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('GSK_RENDERER','cairo')
from game_library.app import Application,Window
from game_library.demo import prepare_demo
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
    def screenshot(name,target=None):
        settle()
        target=target or w
        paintable=Gtk.WidgetPaintable.new(target); snapshot=Gtk.Snapshot()
        paintable.snapshot(snapshot,target.get_width(),target.get_height())
        texture=target.get_renderer().render_texture(snapshot.to_node(),None)
        texture.save_to_png(str(Path(__file__).resolve().parents[1]/'docs/screenshots'/name))
    w.theme.set_selected(1); screenshot('library-light.png')
    w.theme.set_selected(2); screenshot('library-dark.png')
    game=library.games()[0]; w.show_game(game)
    w.fields['title'].set_text('Nebula Drift — reviewed')
    assert w.dirty()
    w.save_game()
    assert library.games()[0]['title']=='Nebula Drift — reviewed'
    screenshot('details-dark.png')
    assert w.cover.get_height()<220, 'Detail header cover must stay compact'
    w.set_default_size(920,640); w.detail_tabs.set_visible_child_name('files'); settle()
    adjustment=w.detail_tabs.get_visible_child().get_vadjustment()
    assert adjustment.get_page_size()>100, 'Detail form must have usable viewport height'
    assert adjustment.get_upper()>adjustment.get_page_size(), 'Long details must be scrollable'
    adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size()); settle()
    assert adjustment.get_value()>0, 'Detail scrollbar must reach lower fields'
    w.set_default_size(1120,800); w.detail_tabs.set_visible_child_name('overview'); settle()
    assert not any(b.get_label() in ('Sync','Save & Sync') for b in buttons(w))
    assert any(b.get_label()=='Play' for b in buttons(w))
    assert len(w.progress_labels)==3
    assert w.progress_labels[1].get_text().startswith('✓')
    assert w.detail_tabs.get_child_by_name('play') is not None
    w.detail_tabs.set_visible_child_name('play');settle();screenshot('direct-play-dark.png')
    assert not w.play_buttons[w.game['id']].get_sensitive(), 'Demo Play must be disabled'
    w.fields['title'].set_text('Saved new title');w.save_game()
    w.launch_fields['proton'].set_text('GE-Latest');w.launch_args.get_buffer().set_text('one argument\n--flag');w.save_game()
    assert library.games()[0]['launch']['arguments']==['one argument','--flag']
    assert not w.launcher.active()
    # Exercise native Play/Stop/navigation with an inert injected launch service.
    class FakeLaunch:
        def __init__(self):self.record={}
        def active(self):return bool(self.record)
        def current(self):return self.record
        def snapshot(self,game_id):return {'state':'Running' if self.record.get('game_id')==game_id else 'Not started','logs':['inert fixture'],'code':None}
    fake=FakeLaunch();real=w.launcher;w.launcher=fake
    fake.record={'game_id':w.game['id'],'title':w.game['title'],'state':'Running'}
    w.refresh_launch_state();assert w.play_buttons[w.game['id']].get_label()=='Stop'
    w.show_library();w.refresh_launch_state()
    assert w.play_buttons[fake.record['game_id']].get_label()=='Stop'
    assert all(not b.get_sensitive() for game_id,b in w.play_buttons.items() if game_id!=fake.record['game_id'])
    w.launcher=real;w.show_game(library.games()[0])
    archive=Path(temp)/'backup.zip'; library.export_zip(archive)
    assert library.preview_import(archive)['conflicts']==3
    library.import_zip(archive,'replace')
    assert all(g['sync'] is None for g in library.games())
    assert library.games()[0]['launch']['arguments']==['one argument','--flag']
    w.show_library(); w.filter.set_text('Nebula'); w.render_cards()
    assert len(list(w.flow))==1
    w.show_game(library.games()[0]); w.delete_game()
    dialog=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog))
    dialog.emit('response','confirm'); settle()
    assert len(library.games())==2
    library.data['settings'].pop('default_proton',None)
    w.proton_manager.releases=lambda *args,**kwargs:[{'family':'GE-Proton','version':'GE-Proton11-fixture','name':'GE-Proton11-fixture.tar.gz','architecture':'x86_64','source':'Official upstream fixture','url':'https://github.com/GloriousEggroll/proton-ge-custom/releases/download/test/GE-Proton11-fixture.tar.gz','size':1,'digest':'sha256:'+'0'*64,'checksum_url':''}]
    w.open_settings(); settle()
    settings=next(d for d in Gtk.Window.get_toplevels() if d.get_title()=='Settings')
    assert any(b.get_label()=='Export ZIP' for b in buttons(settings))
    assert not any(b.get_label()=='Export backup' for b in buttons(w))
    assert settings.get_visible_page().get_title()=='General'
    settings.set_visible_page(w.proton_settings_page);settle()
    assert any(b.get_label()=='Refresh' for b in buttons(settings))
    next(b for b in buttons(settings) if b.get_label()=='Refresh').emit('clicked')
    pump_until(lambda:any(b.get_label()=='Install' for b in buttons(settings)));settle()
    screenshot('proton-manager-dark.png',settings)
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
    print('PASS: native themes, local save, direct Play settings, strict active-game navigation, Proton Manager, ZIP restore and filtering')
