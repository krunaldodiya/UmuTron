"""Native Storage flows, injected inert volumes, owned isolated Broadway only."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if os.environ.get('GDK_BACKEND')!='broadway':raise SystemExit('Use the isolated Broadway fixture.')
from fullscreen_preview import settle
from catalog_fixtures import FixtureCatalog
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library.storage import Volume,SizePlan
from game_library.storage_access import StorageAccess,PrivateStateStore
from game_library.storage_ui import InstallDriveDialog,VolumePicker
from game_library.storage_topology import LIMITED
import game_library.storage_ui as storage_ui
from gi.repository import Adw,Gio,Gtk


def widgets(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from widgets(child);child=child.get_next_sibling()


def wait(predicate):
    deadline=time.monotonic()+6
    while time.monotonic()<deadline:
        settle(30)
        if predicate():return
    raise AssertionError('Native async state did not settle')


def response(heading,key):
    d=next(w for w in Gtk.Window.get_toplevels() if isinstance(w,Adw.MessageDialog) and w.get_visible() and w.get_heading()==heading)
    text=d.get_response_label(key)
    next(c for c in widgets(d) if isinstance(c,Gtk.Button) and c.get_label()==text).emit('clicked');settle(150)


def capture(window,path,width,height):
    window.set_title('NATIVE TEST RENDER · inert volumes · '+window.get_title())
    window.present();settle(600)
    assert (window.get_width(),window.get_height())==(width,height),(window.get_width(),window.get_height())
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        window.queue_draw();settle(100)
        paintable=Gtk.WidgetPaintable.new(window);snap=Gtk.Snapshot();paintable.snapshot(snap,width,height);node=snap.to_node()
        if node is not None:
            window.get_renderer().render_texture(node,None).save_to_png(str(path));return
    raise AssertionError(('No fixture frame',window.get_visible(),window.get_mapped(),window.get_width(),window.get_height()))


class SizedPicker(VolumePicker):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.set_size_request(760,760);self.set_default_size(760,760)


def sized_preferences(width,height):
    original=Adw.PreferencesWindow
    class SizedSettings(original):
        def __init__(self,**kwargs):
            kwargs.update(default_width=width,default_height=height)
            super().__init__(**kwargs);self.set_size_request(width,height)
    return SizedSettings


def settings(window,width=760,height=800):
    with patch('game_library.app.Adw.PreferencesWindow',sized_preferences(width,height)):window.open_settings()
    window.settings_dialog.set_visible_page(window.storage_settings_page)
    notice=window.storage_settings_page.notice;notice.set_text('NATIVE TEST RENDER · inert volumes · no transfers');notice.set_visible(True);notice.add_css_class('warning')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    events=[];storage_ui.VolumePicker=SizedPicker
    with tempfile.TemporaryDirectory(prefix='storage-native-') as tmp:
        root=Path(tmp);os.environ['XDG_CACHE_HOME']=str(root/'cache');library=prepare_demo(seed=False)
        game=library.new_game();game.update(title='Storage flow fixture',description='Metadata first. Existing files stay where they are.');library.save(game)
        a=root/'Internal SSD';b=root/'Second partition';a.mkdir();b.mkdir()
        gib=1024**3
        volumes=[Volume('partition-a','boot:a',str(a),'Internal SSD · Partition 1',320*gib,512*gib,device=a.stat().st_dev),
                 Volume('partition-b','boot:b',str(b),'Internal SSD · Partition 2',600*gib,1024*gib,device=b.stat().st_dev),
                 Volume('external','boot:e','/fixture/USB','USB backup',600*gib,1024*gib,support_reason='External, removable and hot-plug drives are not supported.'),
                 Volume('unknown','boot:u','/fixture/NVMe','Unverified attachment',600*gib,1024*gib,support_reason='Internal attachment could not be verified. This partition is unavailable.'),
                 Volume('limited','boot:n','/fixture/Games','PCIe NVMe · limited verification',600*gib,1024*gib,managed_reason=LIMITED)]
        service=StorageAccess(PrivateStateStore(root/'storage.sqlite3'),lambda:list(volumes))
        app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
        with patch('game_library.app.Controller'):
            window=Window(app,library,demo=True,catalog_provider=FixtureCatalog(),storage_service=service)
        app.window=window;window.proton_manager.releases=lambda *a,**k:[];window.present();window.theme.set_selected(2);window.show_game(game)
        errors=[];window.error=lambda error:errors.append(str(error))
        # Empty production registry must not gate manual Setup or its installer.
        assert not service.snapshot()['registrations']
        with patch.object(service,'snapshot',side_effect=AssertionError('Manual flow consulted Storage')), patch.object(service,'discover',side_effect=AssertionError('Manual flow discovered drives')):
            window.open_manage();assert window.editor is not None
            external=root/'Unregistered external game';external.mkdir();exe=external/'game.exe';exe.write_text('Inert fixture; never execute')
            window.fields['executable'].set_text(str(exe));window.fields['working_dir'].set_text(str(external))
            window.save_editor();assert window.editor is None
            assert library.games()[0]['executable']==str(exe) and library.games()[0]['working_dir']==str(external)
            window.open_manage();window.open_installer();assert window.installer_dialog is not None
            assert not any(isinstance(c,Gtk.Label) and 'Registered drive' in c.get_text() for c in widgets(window.installer_dialog))
            window.close_installer();window.cancel_editor()
        assert not service.snapshot()['registrations'];events.append('Zero registrations: native Setup opens/saves external existing path; manual installer opens without drive prompt')
        before=library.path.read_bytes()
        settings(window)
        page=window.storage_settings_page;wait(lambda:not page.pending)
        capture(window.settings_dialog,args.output/'storage-empty.png',760,800)
        page.open_picker('install');picker=page.picker;wait(lambda:not picker.pending)
        assert [c.get_sensitive() for _,c in picker.options]==[True,True,False,False,True]
        assert not any(isinstance(c,(Gtk.Entry,Gtk.FileChooserWidget)) for c in widgets(picker))
        capture(picker,args.output/'storage-partitions.png',760,760)
        picker.options[4][1].set_active(True);picker.commit();wait(lambda:not picker.active and not page.pending)
        restricted=service.snapshot()['registrations'][0]
        assert restricted['roles']==['install'] and restricted['managed_reason']==LIMITED
        assert library.path.read_bytes()==before
        capture(window.settings_dialog,args.output/'storage-nvme-registration.png',760,800)
        service.remove(restricted['id']);page.refresh();wait(lambda:not page.pending)
        page.open_picker('cache');picker=page.picker;wait(lambda:not picker.pending)
        assert not picker.options[4][1].get_sensitive()
        capture(picker,args.output/'storage-nvme-cache-blocked.png',760,760)
        picker.close();settle()
        events.append('Limited PCIe NVMe registers metadata only; cache remains disabled; no game metadata or drive writes')
        page.open_picker('install');picker=page.picker;wait(lambda:not picker.pending)
        picker.options[0][1].set_active(True);picker.close();settle();picker.commit();assert not service.snapshot()['registrations']
        page.open_picker('install');picker=page.picker;wait(lambda:not picker.pending)
        picker.options[0][1].set_active(True);picker.commit();wait(lambda:not picker.active and not page.pending)
        identity=service.snapshot()['registrations'][0]['id'];assert len(page.rows)==1
        page.open_picker('install');picker=page.picker;wait(lambda:not picker.pending)
        assert not picker.options[0][1].get_sensitive() and picker.options[1][1].get_sensitive()
        capture(picker,args.output/'storage-duplicate-disabled.png',760,760);picker.close();settle()
        page.change(lambda:service.add_role(identity,'cache'));wait(lambda:not page.pending)
        assert len(page.rows)==1 and set(next(iter(page.rows.values()))['data']['roles'])=={'install','cache'}
        capture(window.settings_dialog,args.output/'storage-shared-roles.png',760,800)
        window.settings_dialog.close();settle();assert not page.active and window.settings_dialog is None
        assert library.path.read_bytes()==before;events.append('Partition registration and shared roles do not change game metadata')
        # Held discovery callback cannot revive a closed picker or register anything.
        settings(window);page=window.storage_settings_page;wait(lambda:not page.pending)
        release=Event();started=Event();original=service.choices
        def held():started.set();release.wait(4);return original()
        with patch.object(service,'choices',held):
            page.open_picker('install');picker=page.picker;wait(started.is_set);window.settings_dialog.close();release.set();settle(250)
            assert not picker.active and not picker.options
        events.append('Closed picker ignores delayed discovery')
        second=service.register(volumes[1],'install');volumes[0]=replace(volumes[0],read_only=True)
        selected=[];dialog=InstallDriveDialog(window,service,SizePlan(100,200),lambda *v:selected.append(v));dialog.present();settle()
        assert not dialog.confirm.get_sensitive() and dialog.install_id is None
        dialog.options[1][1].set_active(True);assert not dialog.confirm.get_sensitive() # Required cache is offline too.
        dialog.close();assert not selected
        events.append('Inactive managed target chooser has no offline-default fallback; no transfer or reservation starts')
        volumes[0]=replace(volumes[0],read_only=False)
        settings(window,600,600);page=window.storage_settings_page;wait(lambda:not page.pending)
        capture(window.settings_dialog,args.output/'storage-small.png',600,600)
        page.request_remove(page.rows[second]['data']);response('Remove this storage registration?','cancel')
        assert len(service.snapshot()['registrations'])==2
        window.settings_dialog.close();settle()
        # The same registered partition follows a mount-path change, then goes
        # offline without resolving its old directory on the parent filesystem.
        old_root=volumes[1].root
        volumes[1]=replace(volumes[1],root=str(root/'Remounted partition'),mount_id='boot:new-b')
        settings(window);page=window.storage_settings_page;wait(lambda:not page.pending)
        assert page.rows[second]['data']['root']!=old_root
        assert page.rows[second]['data']['id']==second
        del volumes[1];page.refresh();wait(lambda:not page.pending)
        assert page.rows[second]['data']['status']=='offline' and page.rows[second]['data']['free'] is None
        capture(window.settings_dialog,args.output/'storage-offline-remount.png',760,800)
        window.settings_dialog.close();settle()
        events.append('Mount changes retain partition registration; offline state never uses stale path')
        window.set_tv_mode(True);window.unfullscreen();window.open_tv_options();settle()
        options=window.tv_options_dialog
        # An unconnected Broadway renderer may not acknowledge a resize after
        # mapping. Request fixture dimensions before the first present, as in
        # the desktop cases; keep the exact allocated-size assertion below.
        with patch('game_library.app.Adw.PreferencesWindow',sized_preferences(760,800)):
            next(c for c in widgets(options) if isinstance(c,Gtk.Button) and c.get_label()=='Storage').emit('clicked')
        wait(lambda:window.settings_dialog is not None and not window.storage_settings_page.pending)
        fullscreen_settings=window.settings_dialog;page=window.storage_settings_page
        assert window.tv_mode and fullscreen_settings.has_css_class('umu-tv')
        assert fullscreen_settings.has_css_class('umu-dark') and page.rows
        capture(fullscreen_settings,args.output/'storage-fullscreen.png',760,800)
        page.open_picker('install');picker=page.picker;wait(lambda:not picker.pending)
        assert picker.has_css_class('umu-tv') and picker.has_css_class('umu-dark')
        picker.close();settle();assert not picker.active
        with patch.object(window,'navigation_window',return_value=fullscreen_settings):window.controller_action('back')
        settle();assert window.settings_dialog is None and not page.active
        events.append('Fullscreen Storage uses same records/palette; native Back cancels and closes')
        window.exiting=True;window.catalog_cancel();window.catalog_pool.shutdown(wait=False,cancel_futures=True);window.pool.shutdown(wait=True);window.controller.close();window.destroy();settle()
        assert not errors,errors
        assert not (a/'EmuGames').exists() and not (a/'UmuTronCache').exists()
    (args.output/'checks.json').write_text(json.dumps({'passed':events,'real_registrations':0,'payload_writes':0,'capture':'Synthetic native GTK test renders'},indent=2)+'\n')
    print('PASS: '+str(len(events))+' native Storage flow groups; inert fixtures only')


if __name__=='__main__':main()
