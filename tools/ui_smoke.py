"""Native isolated UI acceptance; no real games, installer executions or provider credentials."""
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
from threading import Event
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('GSK_RENDERER','broadway' if os.environ.get('GDK_BACKEND')=='broadway' else 'cairo')
os.environ.setdefault('GSETTINGS_BACKEND','memory')
from copy import deepcopy
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from catalog_fixtures import FixtureCatalog
from game_library.play_history import record
from game_library.catalog_work import CatalogWork
from game_library.sources.registry import DownloadSource
from game_library.sources.model import DownloadRelease
from game_library.download_service import source_registry
from uuid import uuid4
from gi.repository import Adw,Gdk,Gio,GLib,Gtk


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
    source_lookup=patch('game_library.catalog_ui.search_game_releases',return_value=[])
    source_lookup_mock=source_lookup.start()
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name = ''
        controller.return_value.error = ''
        w=Window(app,library,demo=True,catalog_provider=FixtureCatalog())
    w.proton_manager.releases=lambda *args,**kwargs:[];app.window=w;w.controller.close();w.present();settle(1000)
    def screenshot(name,target=None):
        target=target or w;focus=target.get_focus();target.set_visible(False);target.present();settle(800)
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
        # Remapping the fixture can drop native activation while retaining its
        # logical focus. Restore that focus through GTK after capture so later
        # navigation checks do not inherit the screenshot helper's side effect.
        if target is w and w.tv_mode and focus and focus.get_root() is target and focus.is_sensitive():
            target.set_focus(None);focus.grab_focus()
            pump_until(lambda:target.get_focus() is focus)
    w.theme.set_selected(1);screenshot('library-light.png');w.theme.set_selected(2);screenshot('library-dark.png')
    game=library.games()[0]
    uninstalled_game=deepcopy(game);uninstalled_game['executable']='';uninstalled_game['working_directory']=''
    before=library.path.read_bytes();art={p.name:p.read_bytes() for p in library.art_dir.iterdir()}
    w.show_game(uninstalled_game);screenshot('details-dark.png')
    assert not any(isinstance(i,(Gtk.Entry,Gtk.DropDown)) for i in widgets(w.body)), 'Detail must be readonly'
    assert w.detail_gear.get_visible()
    assert not any(b.get_tooltip_text()=='Edit Metadata' for b in buttons(w))
    assert library.path.read_bytes()==before and {p.name:p.read_bytes() for p in library.art_dir.iterdir()}==art
    pump_until(lambda:w.detail_refresh.get_sensitive())
    calls_before_installed=source_lookup_mock.call_count
    executable=Path(temp)/'installed-fixture.exe';executable.write_bytes(b'inert fixture')
    installed=deepcopy(game);installed['executable']=str(executable)
    w.show_game(installed)
    assert not w.detail_size.get_visible() and not w.detail_source_row.get_visible()
    assert source_lookup_mock.call_count==calls_before_installed
    source_registry.replace_sources([
        DownloadSource('source-a','Source A'),DownloadSource('source-b','Source B'),
        DownloadSource('source-c','Source C'),DownloadSource('source-d','Source D'),
        DownloadSource('source-e','Source E')])
    library.data.setdefault('settings',{})['disabled_sources']=['source-c']
    source_registry.apply_disabled_sources(['source-c'])
    source_a=DownloadRelease('source-a','Source A','Game installer','42 GB','magnet:?xt=urn:btih:fixture-a')
    source_b=DownloadRelease('source-b','Source B','Game edition','68 GB','magnet:?xt=urn:btih:fixture-b')
    source_c=DownloadRelease('source-c','Source C','Game repack','55 GB','magnet:?xt=urn:btih:fixture-c')
    availability_started=Event();availability_continue=Event()
    def blocked_lookup(*_args,**_kwargs):
        availability_started.set()
        availability_continue.wait(2)
        return []
    source_lookup_mock.side_effect=blocked_lookup
    w.demo=False
    w.show_game(uninstalled_game)
    pump_until(availability_started.is_set)
    assert w.detail_availability_checking and not w.detail_primary.get_sensitive()
    w.install_detail()
    assert not any(window.get_title()=='Install '+uninstalled_game['title']
                   for window in Gtk.Window.get_toplevels())
    availability_continue.set()
    pump_until(lambda:not w.detail_availability_checking)
    assert w.detail_primary.get_sensitive(), f'Install did not re-enable after an empty result: demo={w.demo}, tv={w.tv_mode}, checking={w.detail_availability_checking}, active={w.launcher.active()}, label={w.detail_primary.get_label()}'
    failed_lookup=Event()
    def failing_lookup(*_args,**_kwargs):
        failed_lookup.set()
        raise RuntimeError('fixture source API failure')
    source_lookup_mock.side_effect=failing_lookup
    w.load_detail_sources(force_refresh=False)
    pump_until(failed_lookup.is_set)
    pump_until(lambda:not w.detail_availability_checking)
    assert w.detail_primary.get_sensitive()
    assert 'lookup failed' in (w.detail_primary.get_tooltip_text() or '').lower()
    source_lookup_mock.side_effect=None
    source_lookup_mock.return_value=[source_a,source_b,source_c]
    w.set_detail_releases([source_a,source_b,source_c])
    assert w.detail_size.get_label()=='Source A · Download: 42 GB  ▾'
    assert w.detail_refresh.get_tooltip_text()=='Refresh source results'
    refresh_calls=source_lookup_mock.call_count
    w.detail_refresh.emit('clicked')
    assert not w.detail_refresh.get_sensitive(), 'Refresh click did not start a source query'
    pump_until(lambda:source_lookup_mock.call_count>refresh_calls)
    pump_until(lambda:w.detail_refresh.get_sensitive())
    assert source_lookup_mock.call_args.kwargs.get('force_refresh') is True
    assert [release.provider_id for release in w.detail_all_releases]==['source-a','source-b','source-c']
    assert [release.provider_id for release in w.detail_releases]==['source-a','source-b']
    screenshot('detail-source-button-dark.png')
    w.detail_size.emit('clicked')
    source_dialog=next(window for window in Gtk.Window.get_toplevels()
                       if isinstance(window,Gtk.Window) and window.get_title()=='Select Download Source')
    notebooks=[widget for widget in widgets(source_dialog) if isinstance(widget,Gtk.Notebook)]
    assert len(notebooks)==1
    notebook=notebooks[0]
    tabs=[notebook.get_tab_label_text(notebook.get_nth_page(index))
          for index in range(notebook.get_n_pages())]
    assert tabs==['Source A','Source B']
    page_titles=[[widget.get_title() for widget in widgets(notebook.get_nth_page(index))
                  if isinstance(widget,Adw.ActionRow)] for index in range(notebook.get_n_pages())]
    assert page_titles==[['Game installer'],['Game edition']]
    checks=[widget for widget in widgets(source_dialog) if isinstance(widget,Gtk.CheckButton)]
    assert len(checks)==2 and checks[0].get_active() and not checks[1].get_active()
    assert source_dialog.source_key_controller.emit('key-pressed',Gdk.KEY_Right,0,Gdk.ModifierType(0))
    assert notebook.get_current_page()==1, 'Desktop arrow navigation did not change source tab'
    assert source_dialog.source_key_controller.emit('key-pressed',Gdk.KEY_Left,0,Gdk.ModifierType(0))
    assert notebook.get_current_page()==0
    assert source_dialog.get_focus() is notebook, 'Desktop arrow navigation must retain visible notebook focus'
    screenshot('source-selection-dark.png',source_dialog)
    checks[1].set_active(True)
    click(source_dialog,'Use Source')
    pump_until(lambda:not source_dialog.get_visible())
    assert w.detail_release.provider_id=='source-b'
    source_registry.set_enabled('source-c',True)
    class FixtureStorage:
        def snapshot(self):
            return {'registrations':[{'id':'fixture-drive','roles':['install'],'path':temp,'label':'Fixture'}],
                    'default_install':'fixture-drive'}
    original_storage=w.storage_service
    w.storage_service=FixtureStorage()
    w.install_detail()
    install_title='Install '+w.game['title']
    install_dialog=next(window for window in Gtk.Window.get_toplevels()
                        if isinstance(window,Gtk.Window) and window.get_title()==install_title)
    groups=[widget for widget in widgets(install_dialog) if isinstance(widget,Adw.PreferencesGroup)]
    assert any(group.get_title()=='Matched Source: Source B' for group in groups)
    install_dialog.close();pump_until(lambda:not install_dialog.get_visible())
    w.storage_service=original_storage
    w.open_manage();assert not w.advanced.get_expanded();w.advanced.set_expanded(True);settle()
    assert w.launch_args.is_ancestor(w.executable_panel) and not w.launch_args.is_ancestor(w.advanced)

    w.launch_fields['dll_overrides'].set_text('winmm=n,b');w.launch_fields['proton'].set_text('GE-Latest');w.launch_args.get_buffer().set_text('one argument\n--flag')
    screenshot('manage-game-dark.png',w.editor)
    viewport=w.editor.get_child().get_first_child();adjustment=viewport.get_vadjustment();assert adjustment.get_page_size()>100 and adjustment.get_upper()>adjustment.get_page_size()
    adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());settle();assert adjustment.get_value()>0
    screenshot('advanced-bottom-dark.png',w.editor);w.save_editor()
    assert library.games()[0]['launch']['arguments']==['one argument','--flag']
    assert library.games()[0]['launch']['dll_overrides']=='winmm=n,b'
    w.open_manage();w.launch_fields['dll_overrides'].set_text('dinput8=n');w.cancel_editor();assert library.games()[0]['launch']['dll_overrides']=='winmm=n,b'
    w.open_manage();w.reset_launch_defaults();assert w.launch_fields['dll_overrides'].get_text()=='';assert w.collect()['launch']['arguments']==['one argument','--flag'];w.cancel_editor();assert library.games()[0]['launch']['proton']=='GE-Latest'
    # Store preview is separate from explicit addition; back never saves a draft.
    image=(library.art_dir/game['artwork']['portrait']).read_bytes()
    w.catalog.image_transport=lambda *_:image
    before_add=len(library.games());w.add_game();pump_until(lambda:len(w.collection_tiles)==24)
    w.open_catalog_item(w.catalog.provider.detail(1));pump_until(lambda:w.detail_primary.get_sensitive())
    assert len(library.games())==before_add and not w.saved_detail()
    w.return_from_detail();assert len(library.games())==before_add
    w.open_catalog_item(w.catalog.provider.detail(1));pump_until(lambda:w.detail_primary.get_sensitive())
    w.detail_action();pump_until(lambda:w.saved_detail());saved=w.game
    assert len(library.games())==before_add+1 and saved['executable']=='' and saved['installation']=={}
    assert w.detail_primary.get_label()=='Install'
    w.demo=False;w.refresh_launch_state();assert w.detail_primary.get_sensitive()
    w.detail_action();assert w.editor.get_title()=='Manage Game';w.cancel_editor();w.demo=True
    # Launch choices occur afterwards in Manage Game, without executing anything.
    for mode in ('installed','installer'):
        draft=library.new_game();draft.update(title='New '+mode,description='Metadata saved before launch setup');library.save(draft);w.show_game(draft);w.open_manage();settle()
        assert w.editor.get_title()=='Manage Game' and not w.advanced.get_expanded()
        assert not hasattr(w,'stage_stack') and not hasattr(w,'prefix_panel')
        assert w.install_action.get_label()=='Install game…'
        if mode=='installed':
            w.fields['executable'].set_text(game['executable'])
            assert w.install_action.get_label()=='Reinstall…'
        else:
            w.open_installer();w.installer_entry.set_text(str(Path(temp)/'setup.exe'))
            screenshot('installer-dark.png',w.installer_dialog);assert not w.install_button.get_sensitive()
            w.close_installer()
        w.save_editor();assert not w.launcher.active()
        config=next(g for g in library.games() if g['title']=='New '+mode)['installation']
        assert config==({} if mode=='installed' else {'installer':str(Path(temp)/'setup.exe')}), 'Save preserves installer selection without changing installation mode or executing'
    # Run only our inert fixture installer through the real UI confirmation.
    fixture_dir=Path(temp)/'installer-fixture';fixture_dir.mkdir();setup=fixture_dir/'setup.exe';setup.write_text('inert')
    runner=fixture_dir/'runner';runner.write_text('#!/usr/bin/python3\nimport os\nfrom pathlib import Path\np=Path(os.environ["WINEPREFIX"])/"drive_c/Game"\np.mkdir(parents=True,exist_ok=True)\n(p/"game.exe").write_text("inert installed game")\nprint("fixture install complete",flush=True)\n');runner.chmod(0o700)
    proton=fixture_dir/'Proton';proton.mkdir();(proton/'proton').write_text('inert')
    w.open_manage();w.fields['executable'].set_text('');w.fields['working_dir'].set_text('');w.open_installer();w.installer_entry.set_text(str(setup))
    w.launch_fields['runner'].set_text(str(runner));w.launch_fields['proton'].set_text(str(proton));w.demo=False
    w.run_installer();confirmation=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_heading()=='Run this installer?');confirmation.emit('response','confirm')
    pump_until(lambda:not w.launcher.active() and w.installations.status(w.game)['phase']=='Select installed executable')
    prefix=Path(w.game['installation']['prefix']);assert (prefix/'drive_c/Game/game.exe').exists()
    w.cancel_editor();w.open_manage();assert w.confirm_executable_button.get_visible()
    assert not hasattr(w,'stage_stack') and w.install_action.get_label()=='Reinstall…'
    w.open_installer();assert w.install_status.get_text()=='Select installed executable'
    assert w.installer_entry.get_text()==str(setup)
    w.close_installer();w.cancel_editor();w.open_manage();assert w.confirm_executable_button.get_visible()
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
    w.demo=False
    with patch('game_library.app.build_command',return_value=[]):w.play_game(game)
    settle()
    confirmation=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_heading()=='Play '+game['title']+'?')
    assert confirmation.get_body()=='' and confirmation.get_response_label('confirm')=='Play' and confirmation.get_response_label('cancel')=='Cancel'
    screenshot('play-confirmation-dark.png',confirmation)
    confirmation.emit('response','cancel');settle();assert not fake.active();w.demo=True
    partial=Path(temp)/'runtime.tar.gz.parts';partial.write_bytes(b'x'*1048576)
    fake.record={'game_id':game['id'],'title':game['title'],'state':'Downloading runtime','logs':['Downloading runtime.tar.gz...',f'Writing: {partial}']}
    w.refresh_launch_state();assert w.runtime_progress.get_visible() and '1.0 MiB downloaded' in w.runtime_label.get_text()
    partial.write_bytes(b'x'*2097152);w.refresh_launch_state();assert '2.0 MiB downloaded' in w.runtime_label.get_text()
    assert not hasattr(w,'launch_status')
    screenshot('runtime-download-dark.png')
    fake.record={'game_id':game['id'],'title':game['title'],'state':'Running','operation':'installer','supervisor_pid':123}
    w.show_game(game);w.refresh_launch_state();assert not w.runtime_progress.get_visible();assert w.play_buttons[game['id']].get_label()=='Stop installer'
    assert all(not b.get_sensitive() for gid,b in w.play_buttons.items() if gid!=game['id'])
    # close hides, activation shows same window, unavailable tray minimizes safely.
    class FakeTray:
        available=True
        def close(self):self.closed=True
    app.tray=FakeTray();w.close_requested();assert not w.get_visible();app.activate_window();assert app.window is w and w.get_visible()
    app.tray.available=False;calls=[];original_minimize=w.minimize;w.minimize=lambda:calls.append('minimize');w.close_requested();assert calls==['minimize'];w.minimize=original_minimize
    w.explicit_exit();dialog=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_heading()=='Exit UmuTron?')
    assert 'CONTINUE' in dialog.get_body();dialog.emit('response','cancel');assert not w.exiting
    quit_original=app.quit;exit_calls=[];app.quit=lambda:exit_calls.append('exit');w.explicit_exit()
    dialog=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_heading()=='Exit UmuTron?');dialog.emit('response','confirm')
    assert exit_calls==['exit'] and fake.active();app.quit=quit_original;w.exiting=False;w.pool=__import__('concurrent.futures',fromlist=['ThreadPoolExecutor']).ThreadPoolExecutor(max_workers=2);w.catalog_pool=CatalogWork()
    w.launcher=real;w.show_game(installed)
    archive=Path(temp)/'backup.zip';library.export_zip(archive);library.import_zip(archive,'replace')
    assert library.games()[0]['launch']['arguments']==['one argument','--flag']
    w.proton_manager.releases=lambda *args,**kwargs:[{'family':'GE-Proton','version':'GE-Proton11-fixture','name':'GE-Proton11-fixture.tar.gz','architecture':'x86_64','source':'Official upstream fixture','url':'https://github.com/GloriousEggroll/proton-ge-custom/releases/download/GE-Proton11-fixture/GE-Proton11-fixture.tar.gz','size':1,'digest':'sha256:'+'0'*64,'checksum_url':''}]
    source_load=patch.object(source_registry,'load_sources',return_value=source_registry.providers())
    source_load.start()
    w.open_settings();settle();settings=next(d for d in Gtk.Window.get_toplevels() if d.get_title()=='Settings')
    pump_until(lambda:len(w.sources_settings_page._rows)==5)
    assert [row.get_title() for row in w.sources_settings_page._rows]==[
        'Source A','Source B','Source C','Source D','Source E']
    assert any(b.get_label()=='Export ZIP' for b in buttons(settings));settings.set_visible_page(w.proton_settings_page);w.proton_panel.stack.set_visible_child_name('GE-Proton');w.proton_panel.load('GE-Proton',1)
    pump_until(lambda:any(b.get_label()=='Install' for b in buttons(settings)));screenshot('proton-manager-dark.png',settings);settings.destroy();source_load.stop()
    for leftover in list(Gtk.Window.get_toplevels()):
        if leftover is not w:leftover.destroy()
    w.present();settle()
    # Inject fixture navigation independently of user focus/hardware during smoke.
    w.controller.close()
    def navigate(action):
        actual=w.navigation_window;w.navigation_window=lambda:w
        try:w.controller_action(action)
        finally:w.navigation_window=actual
    # Home uses fixture play-history evidence; Library remains the full collection.
    for index,entry in enumerate(library.games()[:3]):record(library.root,entry['id'],str(uuid4()),100+index)
    w.show_home();w.set_tv_mode(True);settle(500)
    assert w.route=='home' and len(w.tv_games)==3 and w.backdrop.get_paintable() is not None
    screenshot('fullscreen-library-dark.png')
    selected=w.tv_games[0];w.show_game(selected);settle();assert w.detail_origin=='home'
    screenshot('fullscreen-details-dark.png');w.return_from_detail();settle();assert w.route=='home'
    w.show_library();settle();assert len(w.collection_tiles)==len(library.games())
    screenshot('fullscreen-installed-grid-dark.png')
    chosen=next(iter(w.collection_tiles));w.collection_tiles[chosen].grab_focus();settle();navigate('right');settle()
    assert w.routes['library']['focus']!=chosen
    for _ in range(4):navigate('back');assert w.tv_mode and w.route=='library'
    w.tv_home_tab.grab_focus();navigate('right');settle();assert w.focused_control(w) is w.tv_library_tab
    navigate('right');settle();assert w.focused_control(w) is w.tv_games_tab
    w.show_game(uninstalled_game);pump_until(lambda:w.detail_refresh.get_sensitive())
    w.detail_size.emit('clicked')
    source_dialog=next(window for window in Gtk.Window.get_toplevels()
                       if isinstance(window,Gtk.Window) and window.get_title()=='Select Download Source')
    notebook=source_dialog.source_notebook
    assert source_dialog.get_focus() is notebook
    actual_navigation=w.navigation_window
    w.navigation_window=lambda:source_dialog
    try:
        w.controller_action('right')
        assert notebook.get_current_page()==1, 'Fullscreen controller navigation did not change source tab'
        w.controller_action('select')
        assert source_dialog.get_focus() is source_dialog.source_option_pages[1][0]
        w.controller_action('down')
        assert source_dialog.get_focus() is source_dialog.source_footer_controls[1]
    finally:
        w.navigation_window=actual_navigation
        source_dialog.close()
    pump_until(lambda:not source_dialog.get_visible())
    w.show_game(installed);settle()
    assert not any(isinstance(i,(Gtk.Entry,Gtk.DropDown)) for i in widgets(w.body))
    w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True)
    source_lookup.stop()
    w.pool.shutdown(wait=True);w.destroy()
print('PASS: native Store/shared detail, Setup cancellation/save/installer continuity, runtime and one-game guards, backup, Proton, tray/Exit and navigation fixtures')
