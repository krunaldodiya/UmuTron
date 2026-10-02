"""Isolated native Proton Manager checks. No real downloads, games or libraries."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import threading
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fullscreen_preview import settle
from game_library.app import Application, Window
from game_library.demo import prepare_demo
from game_library.proton_manager import ProtonManager, REPOS
from game_library.runner_selection import release_selector
from gi.repository import Adw, Gdk, Gio, Gtk


def wait(predicate, timeout=5):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:
        settle(25)
    assert predicate(), 'Native Proton fixture timed out'


def widgets(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from widgets(child)
        child=child.get_next_sibling()


def assert_family(panel, family):
    assert panel.stack.get_visible_child_name()==family
    for name, button in panel.tab_buttons.items():
        expected=name==family
        assert button.get_active()==expected
        assert bool(button.get_state_flags() & Gtk.StateFlags.CHECKED)==expected
        assert button.has_css_class('suggested-action')==expected
        assert panel.rows[name].get_mapped()==expected


def key_on_tab(panel, family, key):
    button=panel.tab_buttons[family];button.grab_focus()
    controllers=button.observe_controllers()
    controller=next(controllers.get_item(i) for i in range(controllers.get_n_items()) if isinstance(controllers.get_item(i),Gtk.EventControllerKey))
    assert controller.emit('key-pressed',key,0,Gdk.ModifierType(0))
    settle(20)


def capture(widget,path):
    widget.set_visible(False);widget.present();settle(900)
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        paintable=Gtk.WidgetPaintable.new(widget);snapshot=Gtk.Snapshot()
        paintable.snapshot(snapshot,widget.get_width(),widget.get_height())
        node=snapshot.to_node()
        if node is not None:
            widget.get_renderer().render_texture(node,None).save_to_png(str(path));return
        settle(50)
    raise AssertionError('No acknowledged native fixture frame')


parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='umutron-proton-ui-') as temp:
    os.environ['XDG_CACHE_HOME']=temp
    library=prepare_demo(True)
    app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name='';controller.return_value.error=''
        window=Window(app,library,demo=True)
    app.window=window;window.present();window.theme.set_selected(2);settle()
    archive=Path(temp)/'source.tar.gz';tag='GE-Proton11-7'
    with tarfile.open(archive,'w:gz') as output:
        data=b'inert';item=tarfile.TarInfo(tag+'/proton');item.size=len(data);item.mode=0o755;output.addfile(item,io.BytesIO(data))
    manager=ProtonManager(library.root/'proton-manager',arch='x86_64',umu_root=Path(temp)/'umu/compatibilitytools');window.proton_manager=manager
    # Fresh setup inherits UMU-Latest; Settings never installs either family.
    fresh_before=library.path.read_bytes()
    with patch.object(manager,'install') as install, patch.object(manager,'downloader') as downloader:
        window.open_settings();settle()
        fresh_settings=next(w for w in Gtk.Window.get_toplevels() if w.get_title()=='Settings' and w.get_visible())
        fresh=window.proton_panel
        baseline=next(c for c in fresh.controls if c['baseline'])
        assert baseline['value']=='UMU-Latest' and baseline['default'].get_label()=='Default'
        assert 'Not installed' in baseline['status'].get_text() and 'first Play' in baseline['status'].get_text()
        assert not baseline['primary'].get_visible()
        baseline['primary'].emit('clicked');install.assert_not_called();downloader.assert_not_called()
        assert manager.installed()==[] and not fresh.items['GE-Proton']
        assert library.path.read_bytes()==fresh_before
        fresh_settings.close();settle()
    def payload(family,page):
        tags=[f'GE-Proton11-{i}' for i in (range(7,3,-1) if page==1 else range(3,0,-1))] if family=='GE-Proton' else [family+'-'+v for v in (('10.0-4','9.0-4e','9.0-4','9.0-3') if page==1 else ('9.0-2','9.0-1','9.0-0'))]
        return [dict(tag_name=version,assets=[dict(name=version+'.tar.gz',size=archive.stat().st_size,digest='sha256:'+hashlib.sha256(archive.read_bytes()).hexdigest(),browser_download_url='https://github.com/'+REPOS[family]+'/releases/download/'+version+'/'+version+'.tar.gz')]) for version in tags]
    for family in REPOS:
        (manager.root/f'releases-{family}-1.json').write_text(json.dumps(payload(family,1)))
    umu=manager.umu_tools/'UMU-Latest';umu.mkdir(parents=True);(umu/'proton').write_text('inert');(umu/'version').write_text('1774856027 UMU-Proton-10.0-4\n')
    umu_release=next(r for r in manager.cached('UMU-Proton') if r['version']=='UMU-Proton-10.0-4')
    managed_umu=manager.target(umu_release);managed_umu.mkdir()
    (managed_umu/'proton').write_text('inert');(managed_umu/'version').write_bytes((umu/'version').read_bytes())
    (managed_umu/'umutron-release.json').write_text(json.dumps(umu_release))
    older_release=next(r for r in manager.cached('UMU-Proton') if r['version']=='UMU-Proton-9.0-4e')
    older=manager.target(older_release);older.mkdir();(older/'proton').write_text('inert')
    (older/'version').write_text('1774856027 UMU-Proton-9.0-4e\n');(older/'umutron-release.json').write_text(json.dumps(older_release))
    local=manager.tools/'GE-Proton11-6';local.mkdir();(local/'proton').write_text('unreceipted fixture')
    valve=Path(temp)/'Valve-Proton';valve.mkdir();(valve/'proton').write_text('inert');(valve/'version').write_text('1774856027 Proton 11.0-2\n')
    custom=Path(temp)/'saved-custom-link';custom.symlink_to(valve,target_is_directory=True)
    library.set_default_proton(str(valve))
    custom_game=library.games()[-1];custom_game.setdefault('launch',{})['proton']=str(custom);library.save(custom_game)
    saved_before=library.path.read_bytes()
    gate=threading.Event();calls=[]
    def transport(url):
        calls.append(url)
        if not gate.wait(5):raise OSError('fixture worker timeout')
        family=next(f for f,r in REPOS.items() if r in url)
        return payload(family,int(url.rsplit('=',1)[1]))
    manager.transport=transport
    download_calls=[]
    def download(url,path,limit,cancel,progress):
        download_calls.append(url)
        Path(path).write_bytes(archive.read_bytes());progress(archive.stat().st_size)
    manager.downloader=download
    window.demo=False
    window.open_settings();settle()
    settings=next(w for w in Gtk.Window.get_toplevels() if w.get_title()=='Settings' and w.get_visible())
    settings.set_visible_page(window.proton_settings_page);panel=window.proton_panel
    assert panel.stack.get_pages().get_n_items()==2
    assert [panel.stack.get_pages().get_item(i).get_title() for i in range(2)]==['GE-Proton','UMU-Proton']
    assert panel.stack.get_visible_child_name()=='GE-Proton'
    assert not any(isinstance(w,Gtk.Button) and w.get_label() in ('Refresh','Load older versions','Refresh installed','Choose local Proton folder') for w in widgets(panel))
    panel.stack.set_visible_child_name('GE-Proton');settle()
    assert_family(panel,'GE-Proton')
    assert len(panel.items['GE-Proton'])==4 and panel.loading, 'Cached rows must precede background results'
    assert window.get_sensitive() and settings.get_sensitive() and not window.busy
    for i in range(30):
        family='UMU-Proton' if i%2==0 else 'GE-Proton'
        panel.tab_buttons[family].emit('clicked');settle(10);assert_family(panel,family)
    panel.tab_buttons['GE-Proton'].emit('clicked');settle(10);assert_family(panel,'GE-Proton')
    key_on_tab(panel,'GE-Proton',Gdk.KEY_Right);assert_family(panel,'UMU-Proton')
    key_on_tab(panel,'UMU-Proton',Gdk.KEY_Home);assert_family(panel,'GE-Proton')
    focused=next(c for c in panel.controls if c['release'] and c['release']['version']==tag)
    focused['primary'].grab_focus()
    gate.set();wait(lambda:not panel.loading)
    refreshed=next(c for c in panel.controls if c['release'] and c['release']['version']==tag)
    assert settings.get_focus() is refreshed['primary'], 'Background catalog must retain the active row control'
    assert_family(panel,'GE-Proton')
    assert len(panel.items['GE-Proton'])==4
    assert library.path.read_bytes()==saved_before, 'Opening/loading the manager must preserve saved Valve/custom selections'
    assert download_calls==[], 'Normal Settings catalog loading must not install runners'
    assert 'Proton 11.0-2' in panel.default.get_text()
    catalog=next(c for c in panel.controls if c['release'] and c['release']['version']=='GE-Proton11-6')
    assert catalog['value']=='release:GE-Proton:GE-Proton11-6'
    assert manager.status(catalog['release'])['state']=='Available'
    preserved=next(c for c in panel.controls if not c['release'] and c['value']==str(local))
    assert 'unverified' in preserved['status'].get_text()
    local_umu=next(c for c in panel.controls if c['baseline'])
    assert local_umu['value']=='UMU-Latest'
    assert 'Managed by UMU' in local_umu['status'].get_text() and not local_umu['primary'].get_visible()
    assert 'UMU-Proton-10.0-4' in local_umu['heading'].get_text()
    assert sum(c['baseline'] for c in panel.controls)==1
    assert not any(c['release'] and c['release']['version']==umu_release['version'] for c in panel.controls)
    assert not any(c['value']==str(managed_umu) for c in panel.controls)
    assert len([c for c in panel.controls if c['release'] and c['release']['family']=='UMU-Proton'])==3
    assert 'verified' not in local_umu['status'].get_text().lower()
    assert not any(isinstance(w,Gtk.Label) and 'copy' in w.get_text().lower() for w in widgets(panel))
    assert manager.status(umu_release)['state']=='Installed'
    # A receipt in a different installation never establishes the UMU baseline's identity.
    receipt=managed_umu/'umutron-release.json';valid_receipt=receipt.read_bytes()
    receipt.write_text(json.dumps(manager.cached('GE-Proton')[0]));panel.render()
    assert manager.status(umu_release)['state']=='Available'
    assert not any(c['release'] and c['release']['version']==umu_release['version'] for c in panel.controls)
    assert not next(c for c in panel.controls if c['baseline'])['primary'].get_visible()
    receipt.write_bytes(valid_receipt)
    # A saved exact selector for the suppressed version is not silently changed
    # to UMU-Latest, and its default is not falsely attributed to the baseline.
    saved_default=library.data['settings']['default_proton']
    panel.set_default(release_selector(umu_release));exact_before=library.path.read_bytes();panel.render()
    baseline=next(c for c in panel.controls if c['baseline'])
    assert baseline['default'].get_label()=='Set as default' and 'separate saved selection' in baseline['status'].get_text()
    assert library.path.read_bytes()==exact_before and download_calls==[]
    panel.set_default(saved_default)
    manager.has_more=lambda family,page:page==1
    panel.more['GE-Proton']=True
    panel.scrolls['GE-Proton'].emit('edge-reached',Gtk.PositionType.BOTTOM)
    wait(lambda:panel.pages['GE-Proton']==2)
    assert len(panel.items['GE-Proton'])==7 and any('page=2' in u for u in calls)
    panel.more['UMU-Proton']=True
    panel.tab_buttons['UMU-Proton'].emit('clicked')
    panel.scrolls['UMU-Proton'].emit('edge-reached',Gtk.PositionType.BOTTOM)
    wait(lambda:panel.pages['UMU-Proton']==2)
    assert len(panel.items['UMU-Proton'])==7;assert_family(panel,'UMU-Proton')
    older_control=next(c for c in panel.controls if c['value']==release_selector(older_release))
    assert older_control['primary'].get_label()=='Uninstall'
    with patch.object(panel,'remove') as remove:
        older_control['primary'].emit('clicked');remove.assert_called_once_with(str(older))
    install_umu=next(c for c in panel.controls if c['release'] and c['release']['version']=='UMU-Proton-9.0-3')
    install_umu['primary'].emit('clicked');wait(lambda:not manager.busy());panel.update_controls()
    assert install_umu['primary'].get_label()=='Uninstall'
    install_umu['default'].emit('clicked');umu_choice=library.data['settings']['default_proton']
    assert umu_choice=='release:UMU-Proton:UMU-Proton-9.0-3'
    manual_before=library.path.read_bytes()
    # Release completions from both families must not change the visible tab or
    # selected header, even when the previous page still has focusable controls.
    refresh_gate=threading.Event();old_transport=manager.transport
    def held(url):
        if not refresh_gate.wait(5):raise OSError('fixture refresh timeout')
        return old_transport(url)
    manager.transport=held
    panel.load('GE-Proton',1);panel.load('UMU-Proton',1)
    for family in ('GE-Proton','UMU-Proton')*8:
        panel.tab_buttons[family].emit('clicked');settle(5);assert_family(panel,family)
    refresh_gate.set();wait(lambda:not panel.loading);assert_family(panel,'UMU-Proton')
    assert library.path.read_bytes()==manual_before
    manager.transport=old_transport
    key_on_tab(panel,'UMU-Proton',Gdk.KEY_Left);assert_family(panel,'GE-Proton')
    first=next(c for c in panel.controls if c['release'] and c['release']['version']==tag)
    first['primary'].emit('clicked');wait(lambda:not manager.busy());panel.update_controls()
    assert first['primary'].get_label()=='Uninstall'
    first['default'].emit('clicked')
    assert library.data['settings']['default_proton']==release_selector(first['release'])
    first=next(c for c in panel.controls if c['release'] and c['release']['version']==tag)
    assert first['default'].get_label()=='Default' and not first['default'].get_sensitive()
    saved_manual=library.path.read_bytes();settings.close();settle();window.open_settings();settle()
    settings=next(w for w in Gtk.Window.get_toplevels() if w.get_title()=='Settings' and w.get_visible())
    settings.set_visible_page(window.proton_settings_page);panel=window.proton_panel
    wait(lambda:not panel.loading)
    assert_family(panel,'GE-Proton')
    assert library.path.read_bytes()==saved_manual, 'Reopen/background refresh must retain the chosen GE default'
    assert next(c for c in panel.controls if c['baseline'])['default'].get_label()=='Set as default'
    first=next(c for c in panel.controls if c['release'] and c['release']['version']==tag)
    capture(settings,args.output/'proton-ge.png')
    # Referenced removal is blocked before confirmation and leaves the runner intact.
    first['primary'].emit('clicked');settle()
    error=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_visible())
    assert 'App default' in error.get_body();error.emit('response','ok');error.close();settle(300)
    panel.set_default('UMU-Latest')
    first=next(c for c in panel.controls if c['release'] and c['release']['version']==tag)
    first['primary'].emit('clicked');settle()
    confirmation=next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_visible())
    assert confirmation.get_heading().startswith('Uninstall ')
    confirmation.emit('response','cancel');settle()
    assert manager.target(first['release']).is_dir(), 'Cancelling uninstall must keep files'
    # An explicit baseline action selects the mutable UMU alias, not a fixed archive.
    panel.set_default(release_selector(first['release']))
    next(c for c in panel.controls if c['baseline'])['default'].emit('clicked')
    assert library.data['settings']['default_proton']=='UMU-Latest'
    automatic_before=library.path.read_bytes()
    (umu/'version').write_text('1774856027 UMU-Proton-10.0-5\n');panel.render()
    assert 'UMU-Proton-10.0-5' in next(c for c in panel.controls if c['baseline'])['heading'].get_text()
    assert library.path.read_bytes()==automatic_before
    (umu/'version').write_text('1774856027 UMU-Proton-10.0-4\n');panel.render()
    panel.set_default(str(umu))
    panel.stack.set_visible_child_name('UMU-Proton');settle();capture(settings,args.output/'proton-umu.png')
    assert_family(panel,'UMU-Proton')
    key_on_tab(panel,'UMU-Proton',Gdk.KEY_Home);assert_family(panel,'GE-Proton')
    key_on_tab(panel,'GE-Proton',Gdk.KEY_End);assert_family(panel,'UMU-Proton')
    capture(settings,args.output/'proton-umu-keyboard.png');assert_family(panel,'UMU-Proton')
    adjustment=panel.scrolls['UMU-Proton'].get_vadjustment();adjustment.set_value(300);settle()
    capture(settings,args.output/'proton-umu-available.png');assert_family(panel,'UMU-Proton')
    adjustment.set_value(0)
    local_umu=next(c for c in panel.controls if c['baseline'])
    assert local_umu['default'].get_label()=='Default'
    assert managed_umu.is_dir() and umu.is_dir(), 'Presentation must not merge or remove separate installations'
    assert any(REPOS['UMU-Proton'] in url for url in calls)
    manager.transport=lambda _:(_ for _ in ()).throw(OSError('Fixture offline'))
    panel.stack.set_visible_child_name('GE-Proton');panel.load('GE-Proton',1);wait(lambda:not panel.loading)
    assert 'cached' in panel.statuses['GE-Proton'].get_text().lower() and panel.retry['GE-Proton'].get_visible()
    assert len(panel.items['GE-Proton'])==7
    panel.tab_buttons['UMU-Proton'].emit('clicked');panel.load('UMU-Proton',1);wait(lambda:not panel.loading)
    assert 'cached' in panel.statuses['UMU-Proton'].get_text().lower() and panel.retry['UMU-Proton'].get_visible()
    assert len(panel.items['UMU-Proton'])==7;assert_family(panel,'UMU-Proton')
    capture(settings,args.output/'proton-offline.png')
    settings.close();settle()
    # A previously saved custom/Valve path remains a usable Setup choice, even
    # though its former catalog tab no longer exists. Cancel preserves spelling.
    custom_before=library.path.read_bytes();window.show_game(custom_game);window.open_manage();settle()
    assert window.launch_fields['proton'].get_text()==str(custom)
    assert window.proton_choice.get_selected_item().get_string().startswith('Proton 11.0-2')
    window.cancel_editor();assert library.path.read_bytes()==custom_before
    assert (valve/'proton').read_text()=='inert' and custom.is_symlink()
    # A delayed Setup catalog response cannot change a new draft after Cancel.
    before=library.path.read_bytes();game=library.games()[0];window.show_game(game)
    entered=threading.Event();release=threading.Event()
    original_releases=manager.releases
    def delayed(family,*args,**kwargs):
        entered.set();release.wait(5);return manager.cached(family)
    manager.releases=delayed
    window.open_manage();settle();assert entered.wait(2)
    assert not window.proton_choice.is_ancestor(window.advanced) and not window.advanced.get_expanded()
    assert window.proton_choice.get_selected_item().get_string().startswith('Use default')
    assert 'Use default' in window.proton_choice.get_selected_item().get_string()
    old=window.proton_choice;window.cancel_editor()
    window.demo=True;window.open_manage();window.launch_fields['proton'].set_text('GE-Latest')
    release.set();settle(400)
    assert window.proton_choice is not old and window.launch_fields['proton'].get_text()=='GE-Latest'
    assert library.path.read_bytes()==before
    capture(window.editor,args.output/'proton-game-setup.png')
    window.cancel_editor();manager.releases=original_releases
    window.controller.close();window.destroy();window.pool.shutdown(wait=True)
print('PASS: rendered checked/accent headers match content through rapid clicks, keyboard, background refresh and reopen; UMU catalog/pagination/installed actions restored with baseline once; exact selectors and receipt boundaries preserved; no implicit downloads; GE/UMU defaults/install/guards/offline; stale Setup cancellation; no live data or execution')
