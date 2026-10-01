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


def settle(milliseconds=180):
    ready=[False];GLib.timeout_add(milliseconds,lambda:(ready.__setitem__(0,True),False)[-1]);pump_until(lambda:ready[0])


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
    w=Window(app,library,demo=True);app.window=w;w.controller.close();w.present();settle(1000)
    def screenshot(name,target=None):
        target=target or w;target.set_visible(False);target.present();settle(800)
        captured=[]
        def ready_frame():
            if not target.get_mapped() or not target.get_renderer():return False
            paintable=Gtk.WidgetPaintable.new(target);snapshot=Gtk.Snapshot();paintable.snapshot(snapshot,target.get_width(),target.get_height())
            node=snapshot.to_node()
            if node is None:return False
            captured.append(node);return True
        pump_until(ready_frame)
        texture=target.get_renderer().render_texture(captured[0],None)
        texture.save_to_png(str(Path(__file__).resolve().parents[1]/'docs/screenshots'/name))
    w.theme.set_selected(1);screenshot('library-light.png');w.theme.set_selected(2);screenshot('library-dark.png')
    game=library.games()[0];before=library.path.read_bytes();art={p.name:p.read_bytes() for p in library.art_dir.iterdir()}
    w.show_game(game);screenshot('details-dark.png')
    assert not any(isinstance(i,(Gtk.Entry,Gtk.DropDown)) for i in widgets(w.body)), 'Detail must be readonly'
    assert next(b for b in buttons(w) if b.get_tooltip_text()=='Edit Metadata')
    assert next(b for b in buttons(w) if b.get_tooltip_text()=='Manage Game')
    assert any(b.get_label()=='Play' for b in buttons(w))
    assert not w.tv_mode and w.editor is None,(w.tv_mode,w.editor_kind)
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
    assert w.play_buttons[saved['id']].get_label()=='Setup'
    w.demo=False;click(w,'Setup');assert w.editor.get_title()=='Manage Game';w.cancel_editor();w.demo=True
    # Manual fallback remains optional, and cancellation creates no entry.
    count=len(library.games());w.add_game();settle()
    add=next(d for d in Gtk.Window.get_toplevels() if d.get_title()=='Find game metadata')
    click(add,'Enter details manually');assert w.editor.get_title()=='Edit Metadata';w.cancel_editor();assert len(library.games())==count
    metadata.search=original_search;metadata.fetch_game=original_fetch
    # Launch choices occur afterwards in Manage Game, without executing anything.
    for mode,index in (('installed',0),('installer',1)):
        draft=library.new_game();draft.update(title='New '+mode,description='Metadata saved before launch setup');library.save(draft);w.show_game(draft);w.open_manage();settle()
        w.already_installed.set_active(mode=='installed')
        assert w.editor.get_title()=='Manage Game' and not w.advanced.get_expanded()
        assert w.stage_stack.get_visible_child_name()==('game' if mode=='installed' else 'install')
        assert w.game_tab.get_sensitive()==(mode=='installed')
        assert w.install_tab.get_sensitive()==(mode=='installer')
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
    assert w.stage_stack.get_visible_child_name()=='game' and w.confirm_executable_button.get_visible()
    assert w.game_tab.get_sensitive() and not w.install_tab.get_sensitive()
    w.return_to_installation();assert w.stage_stack.get_visible_child_name()=='install'
    assert w.install_tab.get_sensitive() and not w.game_tab.get_sensitive()
    w.cancel_editor();w.open_manage();assert w.stage_stack.get_visible_child_name()=='game'
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
    fake=FakeLaunch();real=w.launcher;w.launcher=fake;w.show_game(game)
    partial=Path(temp)/'runtime.tar.gz.parts';partial.write_bytes(b'x'*1048576)
    fake.record={'game_id':game['id'],'title':game['title'],'state':'Downloading runtime','logs':['Downloading runtime.tar.gz...',f'Writing: {partial}']}
    w.refresh_launch_state();assert w.runtime_progress.get_visible() and '1.0 MiB downloaded' in w.runtime_label.get_text()
    partial.write_bytes(b'x'*2097152);w.refresh_launch_state();assert '2.0 MiB downloaded' in w.runtime_label.get_text()
    assert not hasattr(w,'launch_status')
    screenshot('runtime-download-dark.png')
    fake.record={'game_id':game['id'],'title':game['title'],'state':'Running','operation':'installer','supervisor_pid':123}
    w.show_library();w.refresh_launch_state();assert not w.runtime_progress.get_visible();assert w.play_buttons[game['id']].get_label()=='Stop installer'
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
    for leftover in list(Gtk.Window.get_toplevels()):
        if leftover is not w:leftover.destroy()
    w.present();settle()
    # Inject fixture navigation independently of user focus/hardware during smoke.
    w.controller.close()
    def navigate(action):
        actual=w.navigation_window;w.navigation_window=lambda:w
        try:w.controller_action(action)
        finally:w.navigation_window=actual
    # Console-style fullscreen mode and controller navigation.
    # Many metadata-only fixtures force horizontal overflow; no real library used.
    for number in range(10):
        entry=library.new_game();entry['title']='TV fixture '+str(number);library.save(entry)
    w.show_library();snapshot=library.path.read_bytes();w.set_tv_mode(True);settle()
    assert w.tv_mode and w.has_css_class('tv-mode')
    assert not w.get_decorated() and not w.header.get_visible() and w.tv_controls.get_visible()
    assert library.path.read_bytes()==snapshot
    selected=dict(w.tv_selected_game());long_selected=dict(selected);long_selected['description']='Long home description. '*100;w.select_tv_game(long_selected)
    assert len(w.tv_description.get_text())<=300 and w.tv_description.get_text().endswith('...')
    assert not any(b.get_label()=='Game Info' for b in buttons(w.body));w.select_tv_game(selected)
    screenshot('fullscreen-library-dark.png')
    assert all(not control.get_visible() for control in (w.theme,w.settings_button,w.log_button,w.exit_button,w.mode_button))
    assert not hasattr(w,'tv_home') and w.tv_clock.get_text()
    for control in (w.tv_games_tab,w.tv_library_tab,w.tv_menu):
        control.grab_focus();settle(350);assert w.focused_control(w) is control and control.has_css_class('control-focused') and w.tv_section=='games'
    screenshot('fullscreen-header-focus-dark.png')
    assert not w.tv_clock.get_focusable()
    # Installed grid excludes metadata-only and unconfirmed installer entries.
    w.set_tv_section('library');settle()
    assert all(g['executable'] and (g.get('installation',{}).get('mode')!='installer' or g['installation'].get('confirmed')) for g in w.tv_games)
    assert all(g['title']!='Metadata only' for g in w.tv_games)
    sizes={(tile.get_width(),tile.get_height()) for _,tile in w.tv_tiles}
    assert max(height for _,height in sizes)-min(height for _,height in sizes)<=1,sizes
    assert max(width for width,_ in sizes)-min(width for width,_ in sizes)<=1,sizes
    assert next(iter(sizes))[1]<300,'Grid cards must not stretch to screen bottom'
    screenshot('fullscreen-installed-grid-dark.png')
    for _ in range(8):
        navigate('next');settle();assert isinstance(w.focused_control(w),(Gtk.Button,Gtk.MenuButton))
    navigate('back');settle();assert w.tv_section=='games'
    for _ in range(5):navigate('back');settle();assert w.tv_mode
    w.tv_games_tab.grab_focus();navigate('right');settle();assert w.focused_control(w) is w.tv_library_tab
    navigate('right');settle();assert w.focused_control(w) is w.tv_menu
    navigate('left');settle();assert w.focused_control(w) is w.tv_library_tab
    navigate('select');pump_until(lambda:w.tv_section=='library');settle();assert w.focused_control(w) is w.tv_library_tab
    navigate('down');settle();assert w.focused_control(w) in [tile for _,tile in w.tv_tiles]
    library_game=next(g for g in w.tv_games if g['artwork'].get('hero'));w.select_tv_game(library_game)
    assert w.backdrop.get_file().get_path()==str(library.art_dir/library_game['artwork']['hero']) and w.backdrop.get_opacity()>0
    for section in ('library','games'):
        w.set_tv_section(section);settle()
        selected=w.tv_games[-1];w.select_tv_game(selected);w.focus_tv_card();settle()
        w.show_game(selected);settle();navigate('back');settle()
        assert w.tv_selected_id==selected['id']
        assert w.focused_control(w) is next(tile for gid,tile in w.tv_tiles if gid==selected['id'])
    w.set_tv_section('games');settle()
    rail_y=w.tv_scroll.get_allocation().y
    for selected in w.tv_games:
        w.select_tv_game(selected);settle();assert w.tv_scroll.get_allocation().y==rail_y,'Hero height must remain stable across artwork/text changes'
    w.select_tv_game(w.tv_games[0]);settle()
    # Emulate smaller display allocations without changing monitor settings.
    w.unfullscreen();pump_until(lambda:not w.is_fullscreen());w.set_visible(False);w.unrealize();w.set_default_size(1280,720);w.present();settle(800)
    assert w.get_width()<=1280 and w.get_height()<=720,(w.get_width(),w.get_height())
    screenshot('fullscreen-library-720p-dark.png')
    w.select_tv_game(w.tv_games[-1]);w.focus_tv_card();settle()
    assert w.tv_selected_id==w.tv_games[-1]['id']
    w.set_visible(False);w.unrealize();w.set_default_size(1024,600);w.present();settle(800)
    assert w.get_width()<=1024 and w.get_height()<=600,(w.get_width(),w.get_height())
    w.focus_tv_card();settle()
    assert w.tv_scroll.get_hadjustment().get_value()>0
    selected=w.tv_selected_game();w.show_game(selected);settle();navigate('back');settle()
    assert w.tv_selected_id==selected['id'] and w.tv_scroll.get_hadjustment().get_value()>0
    assert w.focused_control(w) is next(tile for gid,tile in w.tv_tiles if gid==selected['id'])
    assert w.tv_menu.get_mapped()
    w.set_tv_section('library');settle();assert w.get_height()<=600
    assert len({tile.get_height() for _,tile in w.tv_tiles})==1
    screenshot('fullscreen-installed-grid-small-dark.png')
    w.set_tv_section('games');settle()
    w.show_game(w.tv_games[0]);settle();assert w.get_height()<=600 and w.tv_menu.get_mapped()
    assert w.play_buttons[w.game['id']].get_mapped()
    w.show_library();settle()
    w.fullscreen();settle()
    # Mode changes preserve the active record and disable other game launches.
    real=w.launcher;w.launcher=fake;w.demo=False
    fake.record={'game_id':w.tv_selected_id,'title':'Fixture active','state':'Running','operation':'play','supervisor_pid':123}
    w.refresh_launch_state();w.focus_tv_card();settle();assert w.tv_play.get_label()=='Stop' and w.tv_play.get_sensitive()
    navigate('right');settle();assert not w.tv_play.get_sensitive()
    assert fake.active();w.launcher=real;w.demo=True;w.refresh_launch_state()
    w.focus_tv_card();settle()
    initial=w.tv_selected_id
    navigate('right');settle();assert w.tv_selected_id!=initial
    navigate('select');pump_until(lambda:w.game is not None);settle();assert not w.launcher.active()
    screenshot('fullscreen-details-dark.png')
    assert not w.settings_button.get_visible() and not w.log_button.get_visible() and not w.exit_button.get_visible()
    w.demo=False
    long_game=dict(next(candidate for candidate in library.games() if candidate.get('executable') and (candidate.get('installation',{}).get('mode')!='installer' or candidate['installation'].get('confirmed'))));long_game['description']='Long description sentence. '*100
    w.show_game(long_game);settle();assert not any(isinstance(widget,Gtk.Label) and widget.get_text()==long_game['description'] for widget in widgets(w.body))
    w.show_game_info(long_game);settle();info=next(window for window in Gtk.Window.get_toplevels() if window.get_title()=='Game Info' and window.get_visible())
    assert any(isinstance(widget,Gtk.Label) and widget.get_text()==long_game['description'] for widget in widgets(info));info.close();settle();screenshot('fullscreen-details-dark.png')
    play=w.play_buttons[w.game['id']];assert play.get_parent() is w.cover.get_parent();assert abs(play.compute_bounds(play.get_parent())[1].get_width()-w.cover.compute_bounds(w.cover.get_parent())[1].get_width())<=1,(play.get_allocation().width,w.cover.get_allocation().width)
    navigate('play');settle();assert not w.launcher.active()
    assert play.get_sensitive()
    play.grab_focus();settle(350);assert w.focused_control(w) is play and play.has_css_class('control-focused');w.demo=True
    # Text never enters the fullscreen keyboard/controller focus path.
    assert all(not widget.get_selectable() and not widget.get_focusable() for widget in widgets(w.body) if isinstance(widget,Gtk.Label))
    for _ in range(12):
        navigate('next');settle();assert isinstance(w.focused_control(w),(Gtk.Button,Gtk.MenuButton))
    # Shoulder buttons scroll readonly details without opening configuration.
    w.detail_scroll.get_child().get_child().append(Gtk.Label(label='Long fixture information\n'*100));settle()
    navigate('pagedown');settle();assert w.detail_scroll.get_vadjustment().get_value()>0
    navigate('pageup');settle();assert w.detail_scroll.get_vadjustment().get_value()==0
    assert not any(b.get_tooltip_text() in ('Edit Metadata','Manage Game') and b.get_mapped() for b in buttons(w))
    w.open_manage();assert w.editor is None
    w.add_game();assert not any(d.get_title()=='Find game metadata' for d in Gtk.Window.get_toplevels())
    navigate('back');settle();assert w.game is None
    w.tv_menu.popup();settle();assert {b.get_label() for b in buttons(w.tv_menu.get_popover())}=={'Exit fullscreen','Exit'};next(b for b in buttons(w.tv_menu.get_popover()) if b.get_label()=='Exit fullscreen').grab_focus();navigate('select');pump_until(lambda:not w.tv_mode);settle();assert not w.tv_mode and w.header.get_visible()
    assert library.path.read_bytes()==snapshot
    # Default mode affects next launch, not the current window or game data.
    w.open_settings();settle();settings=next(d for d in Gtk.Window.get_toplevels() if d.get_title()=='Settings')
    w.default_mode_choice.set_selected(1);assert not w.tv_mode
    assert library.data['settings']['default_display_mode']=='fullscreen';settings.destroy()
    other=Window(app,library,demo=True);other.present();settle();assert other.tv_mode
    other.controller.close();other.destroy();other.pool.shutdown(wait=True)
    library.set_default_display_mode('desktop');w.present();settle()
    w.controller.close()
    w.show_library();w.filter.set_text('Nebula');w.render_cards();assert len(list(w.flow))==1
    settle();selected=next(g for g in library.games() if 'Nebula' in g['title'])
    w.show_game(selected);settle();w.go_back();settle()
    assert w.filter.get_text()=='Nebula'
    assert w.focused_control(w) is w.desktop_tiles[selected['id']]
    for window in list(Gtk.Window.get_toplevels()):window.destroy()
    w.pool.shutdown(wait=True)
    print('PASS: readonly details, modal Save/Cancel, metadata-first Add Game and later launch choices, collapsed advanced settings, metadata switching/default public search, tray hide/reopen/fallback/Exit cancel, operation controls, ZIP, Proton Manager, fullscreen Games/installed Library grid, control-only navigation, controller scroll and default mode')
