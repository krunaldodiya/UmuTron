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
from gi.repository import Adw, Gio, Gtk


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
    def payload(family,page):
        versions=range(7,3,-1) if page==1 else range(3,0,-1)
        return [dict(tag_name=(family+('11-' if family=='GE-Proton' else '-10.0-')+str(i)),assets=[dict(name=(family+('11-' if family=='GE-Proton' else '-10.0-')+str(i))+'.tar.gz',size=archive.stat().st_size,digest='sha256:'+hashlib.sha256(archive.read_bytes()).hexdigest(),browser_download_url='https://github.com/'+REPOS[family]+'/releases/download/'+(family+('11-' if family=='GE-Proton' else '-10.0-')+str(i))+'/'+(family+('11-' if family=='GE-Proton' else '-10.0-')+str(i))+'.tar.gz')]) for i in versions]
    for family in REPOS:
        (manager.root/f'releases-{family}-1.json').write_text(json.dumps(payload(family,1)))
    umu=manager.umu_tools/'UMU-Latest';umu.mkdir(parents=True);(umu/'proton').write_text('inert');(umu/'version').write_text('1774856027 UMU-Proton-10.0-4\n')
    umu_release=next(r for r in manager.cached('UMU-Proton') if r['version']=='UMU-Proton-10.0-4')
    managed_umu=manager.target(umu_release);managed_umu.mkdir()
    (managed_umu/'proton').write_text('inert');(managed_umu/'version').write_bytes((umu/'version').read_bytes())
    (managed_umu/'umutron-release.json').write_text(json.dumps(umu_release))
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
    def download(url,path,limit,cancel,progress):
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
    assert len(panel.items['GE-Proton'])==4 and panel.loading, 'Cached rows must precede background results'
    assert window.get_sensitive() and settings.get_sensitive() and not window.busy
    focused=next(c for c in panel.controls if c['release'] and c['release']['version']==tag)
    focused['primary'].grab_focus()
    gate.set();wait(lambda:not panel.loading)
    refreshed=next(c for c in panel.controls if c['release'] and c['release']['version']==tag)
    assert settings.get_focus() is refreshed['primary'], 'Background catalog must retain the active row control'
    assert len(panel.items['GE-Proton'])==4
    assert library.path.read_bytes()==saved_before, 'Opening/loading the manager must preserve saved Valve/custom selections'
    assert 'Proton 11.0-2' in panel.default.get_text()
    catalog=next(c for c in panel.controls if c['release'] and c['release']['version']=='GE-Proton11-6')
    assert catalog['value']=='release:GE-Proton:GE-Proton11-6'
    assert manager.status(catalog['release'])['state']=='Available'
    preserved=next(c for c in panel.controls if not c['release'] and c['value']==str(local))
    assert 'unverified' in preserved['status'].get_text()
    local_umu=next(c for c in panel.controls if not c['release'] and c['value']==str(umu))
    assert 'UMU-managed' in local_umu['status'].get_text() and not local_umu['primary'].get_visible()
    downloaded_umu=next(c for c in panel.controls if c['release'] and c['value']==release_selector(umu_release))
    assert 'UmuTron download' in downloaded_umu['heading'].get_text()
    assert 'UMU-managed copy' in local_umu['heading'].get_text()
    assert downloaded_umu['heading'].get_text()!=local_umu['heading'].get_text()
    assert downloaded_umu['primary'].get_label()=='Uninstall' and downloaded_umu['primary'].get_visible()
    assert manager.status(umu_release)['state']=='Installed'
    manager.has_more=lambda family,page:page==1
    panel.more['GE-Proton']=True
    panel.scrolls['GE-Proton'].emit('edge-reached',Gtk.PositionType.BOTTOM)
    wait(lambda:panel.pages['GE-Proton']==2)
    assert len(panel.items['GE-Proton'])==7 and any('page=2' in u for u in calls)
    first=next(c for c in panel.controls if c['release'] and c['release']['version']==tag)
    first['primary'].emit('clicked');wait(lambda:not manager.busy());panel.update_controls()
    assert first['primary'].get_label()=='Uninstall'
    first['default'].emit('clicked')
    assert library.data['settings']['default_proton']==release_selector(first['release'])
    first=next(c for c in panel.controls if c['release'] and c['release']['version']==tag)
    assert first['default'].get_label()=='Default' and not first['default'].get_sensitive()
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
    panel.set_default(release_selector(first['release']))
    panel.set_default(str(umu))
    panel.stack.set_visible_child_name('UMU-Proton');settle();capture(settings,args.output/'proton-umu.png')
    local_umu=next(c for c in panel.controls if not c['release'] and c['value']==str(umu))
    assert local_umu['default'].get_label()=='Default'
    assert managed_umu.is_dir() and umu.is_dir(), 'Presentation must not merge or remove separate installations'
    manager.transport=lambda _:(_ for _ in ()).throw(OSError('Fixture offline'))
    panel.load('UMU-Proton',1);wait(lambda:not panel.loading)
    assert 'cached' in panel.statuses['UMU-Proton'].get_text().lower() and panel.retry['UMU-Proton'].get_visible()
    assert len(panel.items['UMU-Proton'])==4
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
print('PASS: exactly GE/UMU tabs; saved Valve/custom selectors preserved; distinct same-version copy labels and ownership; cached/background catalog; scroll pagination; install/default/uninstall state; referenced removal blocked; offline retention; visible Setup selector; stale async cancellation; no live data or execution')
