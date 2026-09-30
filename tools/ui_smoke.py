"""Native isolated UI acceptance; no real games, installer executions or provider credentials."""
import os
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('GSK_RENDERER','cairo')
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library import metadata
from gi.repository import Adw,Gio,GLib,Gtk


def pump_until(condition,timeout=5):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if condition():return
        time.sleep(.01)
    raise AssertionError('Native UI condition timed out')


def settle():
    ready=[False];GLib.timeout_add(180,lambda:(ready.__setitem__(0,True),False)[-1]);pump_until(lambda:ready[0])


def widgets(widget):
    yield widget
    child=widget.get_first_child()
    while child:yield from widgets(child);child=child.get_next_sibling()


def buttons(widget):return [i for i in widgets(widget) if isinstance(i,Gtk.Button)]


def click(target,text):next(b for b in buttons(target) if b.get_label()==text).emit('clicked')


with tempfile.TemporaryDirectory() as temp:
    os.environ['XDG_CACHE_HOME']=temp
    library=prepare_demo(seed=True)
    app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    w=Window(app,library,demo=True);app.window=w;w.present();settle()
    def screenshot(name,target=None):
        settle();target=target or w
        paintable=Gtk.WidgetPaintable.new(target);snapshot=Gtk.Snapshot();paintable.snapshot(snapshot,target.get_width(),target.get_height())
        texture=target.get_renderer().render_texture(snapshot.to_node(),None)
        texture.save_to_png(str(Path(__file__).resolve().parents[1]/'docs/screenshots'/name))
    w.theme.set_selected(1);screenshot('library-light.png');w.theme.set_selected(2);screenshot('library-dark.png')
    game=library.games()[0];before=library.path.read_bytes();art={p.name:p.read_bytes() for p in library.art_dir.iterdir()}
    w.show_game(game);screenshot('details-dark.png')
    assert not any(isinstance(i,(Gtk.Entry,Gtk.DropDown)) for i in widgets(w.body)), 'Detail must be readonly'
    assert next(b for b in buttons(w) if b.get_tooltip_text()=='Edit Metadata')
    assert next(b for b in buttons(w) if b.get_tooltip_text()=='Manage Game')
    assert any(b.get_label()=='Play' for b in buttons(w))
    w.open_metadata();w.fields['title'].set_text('Cancel this title');w.cancel_editor()
    assert library.path.read_bytes()==before
    assert {p.name:p.read_bytes() for p in library.art_dir.iterdir()}==art
    w.open_metadata();w.fields['title'].set_text('Nebula reviewed');w.save_editor();assert library.games()[0]['title']=='Nebula reviewed'
    w.open_manage();assert not w.advanced.get_expanded();w.advanced.set_expanded(True);settle()
    w.launch_fields['proton'].set_text('GE-Latest');w.launch_args.get_buffer().set_text('one argument\n--flag')
    screenshot('manage-game-dark.png',w.editor)
    viewport=w.editor.get_child().get_first_child();adjustment=viewport.get_vadjustment();assert adjustment.get_page_size()>100 and adjustment.get_upper()>adjustment.get_page_size()
    adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());settle();assert adjustment.get_value()>0
    screenshot('advanced-bottom-dark.png',w.editor);w.save_editor()
    assert library.games()[0]['launch']['arguments']==['one argument','--flag']
    w.open_manage();w.reset_launch_defaults();w.cancel_editor();assert library.games()[0]['launch']['proton']=='GE-Latest'
    # Metadata switching defaults to public catalogue, entirely fixture-backed.
    original_search=metadata.search;original_fetch=metadata.fetch_game
    metadata.search=lambda query:[{'id':620,'name':'Catalogue fixture'}]
    metadata.fetch_game=lambda game_id:({'title':'Catalogue fixture','description':'Public fixture description','metadata_app_id':620},{},[])
    w.open_metadata();w.find_metadata();settle()
    dialog=next(d for d in Gtk.Window.get_toplevels() if d.get_title()=='Find game metadata')
    assert w.metadata_provider.get_selected()==0
    w.metadata_provider.set_selected(1)
    entry=next(i for i in widgets(dialog) if isinstance(i,Gtk.Entry));entry.set_text('Fixture');click(dialog,'Search');pump_until(lambda:not w.busy);settle()
    error=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_heading()=='Could not complete this action')
    assert 'Providers' in error.get_body();error.emit('response','ok');w.metadata_provider.set_selected(0);click(dialog,'Search')
    pump_until(lambda:any(b.get_label()=='Select' for b in buttons(dialog)));click(dialog,'Select');pump_until(lambda:not w.busy)
    assert w.fields['title'].get_text()=='Catalogue fixture';w.cancel_editor();assert library.games()[0]['title']=='Nebula reviewed'
    # Metadata-first Add Game saves artwork and opens details without configuration.
    image=(library.art_dir/game['artwork']['portrait']).read_bytes()
    metadata.fetch_game=lambda game_id:({'title':'Metadata only','description':'Fetched once','metadata_app_id':620},{'portrait':image,'hero':image,'logo':image},[])
    before_add=len(library.games());w.add_game();settle()
    add=next(d for d in Gtk.Window.get_toplevels() if d.get_title()=='Find game metadata')
    assert w.editor is None and w.metadata_provider.get_selected()==0
    assert not any(b.get_label() in ('Already installed','Install from installer') for b in buttons(add))
    screenshot('add-game-dark.png',add)
    click(add,'Search');pump_until(lambda:any(b.get_label()=='Select' for b in buttons(add)))
    click(add,'Select');pump_until(lambda:len(library.games())==before_add+1)
    saved=w.game;assert saved['title']=='Metadata only' and saved['description']=='Fetched once'
    assert saved['executable']=='' and saved['launch']=={} and saved['installation']=={}
    assert set(saved['artwork'])=={'portrait','hero','logo'} and w.editor is None
    assert not any(isinstance(i,Gtk.Entry) for i in widgets(w.body))
    assert w.play_buttons[saved['id']].get_label()=='Set up to play'
    w.demo=False;click(w,'Set up to play');assert w.editor.get_title()=='Manage Game';w.cancel_editor();w.demo=True
    # Manual fallback remains optional, and cancellation creates no entry.
    count=len(library.games());w.add_game();settle()
    add=next(d for d in Gtk.Window.get_toplevels() if d.get_title()=='Find game metadata')
    click(add,'Enter details manually');assert w.editor.get_title()=='Edit Metadata';w.cancel_editor();assert len(library.games())==count
    metadata.search=original_search;metadata.fetch_game=original_fetch
    # Launch choices occur afterwards in Manage Game, without executing anything.
    for mode,index in (('installed',0),('installer',1)):
        draft=library.new_game();draft.update(title='New '+mode,description='Metadata saved before launch setup');library.save(draft);w.show_game(draft);w.open_manage();settle()
        assert w.install_mode.get_model().get_n_items()==2
        w.install_mode.set_selected(index)
        assert w.editor.get_title()=='Manage Game' and not w.advanced.get_expanded()
        assert w.executable_panel.get_visible()==(mode=='installed')
        assert w.installer_panel.get_visible()==(mode=='installer')
        w.fields['executable'].set_text(game['executable']);w.installer_entry.set_text(str(Path(temp)/'setup.exe'))
        if mode=='installer':
            screenshot('installer-dark.png',w.editor);assert not w.install_button.get_sensitive()
        w.save_editor();assert not w.launcher.active()
        assert next(g for g in library.games() if g['title']=='New '+mode)['installation']['mode']==mode
    # Run only our inert fixture installer through the real UI confirmation.
    fixture_dir=Path(temp)/'installer-fixture';fixture_dir.mkdir();setup=fixture_dir/'setup.exe';setup.write_text('inert')
    runner=fixture_dir/'runner';runner.write_text('#!/usr/bin/python3\nimport os\nfrom pathlib import Path\np=Path(os.environ["WINEPREFIX"])/"drive_c/Game"\np.mkdir(parents=True,exist_ok=True)\n(p/"game.exe").write_text("inert installed game")\nprint("fixture install complete",flush=True)\n');runner.chmod(0o700)
    proton=fixture_dir/'Proton';proton.mkdir();(proton/'proton').write_text('inert')
    w.open_manage();w.installer_entry.set_text(str(setup));w.fields['executable'].set_text('');w.fields['working_dir'].set_text('')
    w.launch_fields['runner'].set_text(str(runner));w.launch_fields['proton'].set_text(str(proton));w.demo=False
    w.run_installer();confirmation=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_heading()=='Run this installer?');confirmation.emit('response','confirm')
    pump_until(lambda:not w.launcher.active() and w.installations.status(w.game)['phase']=='Select installed executable')
    prefix=Path(w.game['installation']['prefix']);assert (prefix/'drive_c/Game/game.exe').exists()
    w.cancel_editor();w.open_manage();assert w.install_status.get_text()=='Select installed executable'
    assert w.executable_panel.get_visible() and w.confirm_executable_button.get_visible()
    settle();screenshot('installer-select-executable-dark.png',w.editor)
    w.fields['executable'].set_text(str(prefix/'drive_c/Game/game.exe'));w.confirm_installed()
    saved=next(g for g in library.games() if g['title']=='New installer');assert saved['installation']['confirmed'];assert saved['launch']['prefix']==str(prefix)
    assert not w.launcher.active();w.demo=True
    # Active operation controls and navigation use an inert injected service.
    class FakeLaunch:
        def __init__(self):self.record={}
        def active(self):return bool(self.record)
        def current(self):return self.record
        def snapshot(self,game_id):return {'state':'Running' if self.record.get('game_id')==game_id else 'Not started','logs':['fixture'],'code':None}
    fake=FakeLaunch();real=w.launcher;w.launcher=fake
    fake.record={'game_id':game['id'],'title':game['title'],'state':'Running','operation':'installer','supervisor_pid':123}
    w.show_library();w.refresh_launch_state();assert w.play_buttons[game['id']].get_label()=='Stop installer'
    assert all(not b.get_sensitive() for gid,b in w.play_buttons.items() if gid!=game['id'])
    # close hides, activation shows same window, unavailable tray minimizes safely.
    class FakeTray:
        available=True
        def close(self):self.closed=True
    app.tray=FakeTray();w.close_requested();assert not w.get_visible();app.activate_window();assert app.window is w and w.get_visible()
    app.tray.available=False;calls=[];original_minimize=w.minimize;w.minimize=lambda:calls.append('minimize');w.close_requested();assert calls==['minimize'];w.minimize=original_minimize
    w.explicit_exit();dialog=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_heading()=='Exit Launcher?')
    assert 'CONTINUE' in dialog.get_body();dialog.emit('response','cancel');assert not w.exiting
    quit_original=app.quit;exit_calls=[];app.quit=lambda:exit_calls.append('exit');w.explicit_exit()
    dialog=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_heading()=='Exit Launcher?');dialog.emit('response','confirm')
    assert exit_calls==['exit'] and fake.active();app.quit=quit_original;w.exiting=False;w.pool=__import__('concurrent.futures',fromlist=['ThreadPoolExecutor']).ThreadPoolExecutor(max_workers=2)
    w.launcher=real;w.show_game(library.games()[0])
    archive=Path(temp)/'backup.zip';library.export_zip(archive);library.import_zip(archive,'replace')
    assert library.games()[0]['launch']['arguments']==['one argument','--flag']
    w.proton_manager.releases=lambda *args,**kwargs:[{'family':'GE-Proton','version':'GE-Proton11-fixture','name':'GE-Proton11-fixture.tar.gz','architecture':'x86_64','source':'Official upstream fixture','url':'https://github.com/GloriousEggroll/proton-ge-custom/releases/download/test/GE-Proton11-fixture.tar.gz','size':1,'digest':'sha256:'+'0'*64,'checksum_url':''}]
    w.open_settings();settle();settings=next(d for d in Gtk.Window.get_toplevels() if d.get_title()=='Settings')
    assert any(b.get_label()=='Export ZIP' for b in buttons(settings));settings.set_visible_page(w.proton_settings_page);click(settings,'Refresh')
    pump_until(lambda:any(b.get_label()=='Install' for b in buttons(settings)));screenshot('proton-manager-dark.png',settings);settings.destroy()
    w.show_library();w.filter.set_text('Nebula');w.render_cards();assert len(list(w.flow))==1
    for window in list(Gtk.Window.get_toplevels()):window.destroy()
    w.pool.shutdown(wait=True)
    print('PASS: readonly details, modal Save/Cancel, metadata-first Add Game and later launch choices, collapsed advanced settings, metadata switching/default public search, tray hide/reopen/fallback/Exit cancel, operation controls, ZIP and Proton Manager')
