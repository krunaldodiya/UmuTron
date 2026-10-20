"""Native isolated UI acceptance; no real games, installer executions or provider credentials."""
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
from threading import Event
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
try:
    from headless import ensure_headless
    ensure_headless()
except ImportError:
    pass
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
    class FixtureStorage:
        def snapshot(self):
            return {'registrations':[{'id':'fixture-drive','roles':['install'],'root':temp,
                                      'status':'ready','label':'Fixture game drive','default':True}]}
    original_storage=w.storage_service
    w.storage_service=FixtureStorage()
    proton=Path(temp)/'Proton';proton.mkdir();(proton/'proton').write_text('inert')
    w.proton_manager.installed=lambda:[str(proton)]
    w.show_game(uninstalled_game);settle()
    assert w.detail_primary.get_label()=='Add Installed Game'
    w.detail_gear.emit('clicked');settings=next(window for window in Gtk.Window.get_toplevels() if isinstance(window,Gtk.Window) and window.get_title().startswith('Game Settings'))
    w.detail_gear.emit('clicked');settle()
    assert len([win for win in Gtk.Window.get_toplevels() if isinstance(win,Gtk.Window) and win.get_title().startswith('Game Settings')])==1
    uninstalled_actions={button.get_label() for button in buttons(settings)}
    assert 'Restore game backup…' in uninstalled_actions and 'Back up game files…' not in uninstalled_actions
    click(settings,'Restore game backup…');settle()
    restore_dlg=next(window for window in Gtk.Window.get_toplevels() if isinstance(window,Gtk.Window) and window.get_title()=='Restore Game Backup')
    assert restore_dlg.get_transient_for() is settings
    assert {'Browse…','Cancel','Restore game'} <= {button.get_label() for button in buttons(restore_dlg)}
    click(restore_dlg,'Cancel');pump_until(lambda:not restore_dlg.get_visible())
    settings.close();pump_until(lambda:not settings.get_visible())
    w.open_add_installed_game()
    add_dialog=next(window for window in Gtk.Window.get_toplevels()
                    if isinstance(window,Gtk.Window) and window.get_title()=='Add Installed Game')
    assert len([widget for widget in widgets(add_dialog) if isinstance(widget,Gtk.DropDown)])==1
    assert {'Choose game folder…','Choose launcher executable…','Add game'} <= {button.get_label() for button in buttons(add_dialog)}
    screenshot('add-installed-game-dark.png',add_dialog)
    add_dialog.close();pump_until(lambda:not add_dialog.get_visible())
    w.storage_service=original_storage
    managed_game=deepcopy(game);managed_game['installation']={'mode':'linked','root':temp}
    w.show_game(managed_game);settle()
    w.detail_gear.emit('clicked');settings=next(window for window in Gtk.Window.get_toplevels() if isinstance(window,Gtk.Window) and window.get_title().startswith('Game Settings'))
    managed_actions={button.get_label() for button in buttons(settings)}
    assert {'Back up game files…','Move install folder…','Remove installed game…','Uninstall game files…','Browse…'} <= managed_actions
    assert 'Restore game backup…' not in managed_actions
    click(settings,'Back up game files…');settle()
    backup=next(window for window in Gtk.Window.get_toplevels() if isinstance(window,Gtk.Window) and window.get_title()=='Back Up Game')
    assert backup.get_transient_for() is settings
    assert {'Cancel','Back up game'} <= {button.get_label() for button in buttons(backup)}
    click(backup,'Cancel');pump_until(lambda:not backup.get_visible())
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
    w.launcher=real;w.show_game(game)
    w.proton_manager.releases=lambda *args,**kwargs:[{'family':'GE-Proton','version':'GE-Proton11-fixture','name':'GE-Proton11-fixture.tar.gz','architecture':'x86_64','source':'Official upstream fixture','url':'https://github.com/GloriousEggroll/proton-ge-custom/releases/download/GE-Proton11-fixture/GE-Proton11-fixture.tar.gz','size':1,'digest':'sha256:'+'0'*64,'checksum_url':''}]
    w.open_settings();settle();settings=next(d for d in Gtk.Window.get_toplevels() if d.get_title()=='Settings')
    assert not any('backup' in (button.get_label() or '').lower() or 'export' in (button.get_label() or '').lower() for button in buttons(settings))
    settings.set_visible_page(w.proton_settings_page);w.proton_panel.stack.set_visible_child_name('GE-Proton');w.proton_panel.load('GE-Proton',1)
    pump_until(lambda:any(button.get_label()=='Install' for button in buttons(settings)));screenshot('proton-manager-dark.png',settings);settings.destroy()
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
    w.show_game(uninstalled_game);settle()
    assert w.detail_primary.get_label()=='Add Installed Game'
    assert not any(isinstance(i,(Gtk.Entry,Gtk.DropDown)) for i in widgets(w.body))
    w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True)
    w.pool.shutdown(wait=True);w.destroy()
print('PASS: native managed-game, runtime, settings, tray, and navigation fixtures')
