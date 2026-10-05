"""Native single-screen Setup regression checks using only isolated fixtures."""
import argparse
from copy import deepcopy
from uuid import uuid4
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullscreen_preview import settle
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from gi.repository import Adw,Gdk,Gio,Gtk


def widgets(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from widgets(child)
        child=child.get_next_sibling()


def capture(widget,path,remap=True):
    if remap:widget.set_visible(False);widget.present()
    settle(800)
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        paintable=Gtk.WidgetPaintable.new(widget);snapshot=Gtk.Snapshot()
        paintable.snapshot(snapshot,widget.get_width(),widget.get_height());node=snapshot.to_node()
        if node is not None:
            widget.get_native().get_renderer().render_texture(node,None).save_to_png(str(path));return
        settle(50)
    raise AssertionError('Native fixture did not render')


def message(heading):
    return next(d for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_visible() and d.get_heading()==heading)


def respond(dialog,response):
    title=dialog.get_response_label(response)
    control=next(v for v in widgets(dialog) if isinstance(v,Gtk.Button) and v.get_label()==title)
    control.emit('clicked');settle(300)


def escape(dialog):
    controllers=dialog.observe_controllers()
    controller=next(controllers.get_item(i) for i in range(controllers.get_n_items()) if isinstance(controllers.get_item(i),Gtk.EventControllerKey))
    assert controller.emit('key-pressed',Gdk.KEY_Escape,0,Gdk.ModifierType(0))
    settle()


parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='umutron-setup-ui-') as temp:
    os.environ['XDG_CACHE_HOME']=temp
    library=prepare_demo(True)
    app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller'):
        w=Window(app,library,demo=True)
    app.window=w;w.proton_manager.releases=lambda *args,**kwargs:[];w.present();w.theme.set_selected(2);settle()
    game=library.new_game();game.update(title='Installer fixture',description='Metadata saved before setup');library.save(game);w.show_game(game);w.open_manage();settle()
    names=[widget.get_label() for widget in widgets(w.editor) if isinstance(widget,Gtk.Button)]
    assert 'Prefix' not in names and '1 · Install' not in names and '2 · Game setup' not in names, 'Setup must be a single screen without stage or Prefix tabs'
    assert not hasattr(w,'prefix_panel') and not hasattr(w,'stage_stack')
    assert w.install_action.get_label()=='Install game…' and isinstance(w.manage_more,Gtk.MenuButton)
    assert w.install_action.is_ancestor(w.manage_more.get_popover())
    assert not w.advanced.get_expanded() and w.installer_dialog is None
    assert 'Installer executable' not in [v.get_text() for v in widgets(w.editor) if isinstance(v,Gtk.Label)]
    baseline=library.path.read_bytes();w.launch_args.get_buffer().set_text('--fixture-argument')
    game_files=Path(temp)/'game-files';game_files.mkdir();exe=game_files/'game.exe';exe.write_text('inert');setup=Path(temp)/'setup.exe';setup.write_text('inert')
    capture(w.editor,args.output/'setup-unconfigured.png')
    w.manage_more.popup();settle();capture(w.manage_more.get_popover(),args.output/'install-menu.png',False);w.manage_more.popdown()
    with patch.object(w.installations,'start') as start_install,patch.object(w.launcher,'stop') as stop:
        # Opening, closing and reopening never install or leak a discarded picker.
        for i in range(3):
            w.manage_more.popup();settle();assert w.install_action.get_mapped()
            w.install_action.emit('clicked');settle();modal=w.installer_dialog
            assert modal.get_modal() and modal.get_transient_for() is w.editor
            w.open_installer();assert w.installer_dialog is modal
            w.installer_entry.set_text(str(setup));assert w.collect()['installation']['installer']==str(setup)
            assert not w.install_button.get_sensitive(), 'Demo remains unable to execute'
            if i==0:capture(modal,args.output/'installer-modal.png')
            escape(modal);assert w.installer_dialog is None
            assert w.focused_control(w.editor) is w.manage_more
            assert library.path.read_bytes()==baseline
            assert w.collect()['launch']['arguments']==['--fixture-argument']
        start_install.assert_not_called();stop.assert_not_called()
        w.open_installer()
        with patch.object(w,'choose_file') as picker:
            w.pick_installer();late_pick=picker.call_args.args[1]
        w.close_installer();w.open_installer();late_pick(Path(temp)/'stale-choice.exe')
        assert w.installer_entry.get_text()==str(setup)
        w.close_installer()
        # A configured preinstalled game uses the same menu, with a distinct label.
        w.fields['executable'].set_text(str(exe));w.fields['working_dir'].set_text(str(exe.parent));settle()
        assert w.install_action.get_label()=='Reinstall…'
        w.manage_more.popup();settle();capture(w.editor,args.output/'setup-preinstalled.png',False);capture(w.manage_more.get_popover(),args.output/'reinstall-menu.png',False);w.manage_more.popdown()
        w.open_installer();w.installer_entry.set_text(str(setup));w.demo=False;w.refresh_launch_state()
        assert w.install_button.get_sensitive()
        w.install_button.emit('clicked');settle();confirmation=message('Reinstall this game?')
        assert confirmation.get_transient_for() is w.installer_dialog and confirmation.get_default_response()=='cancel'
        assert confirmation.get_response_label('confirm')=='Reinstall'
        capture(confirmation,args.output/'reinstall-confirmation.png')
        respond(confirmation,'cancel');settle();start_install.assert_not_called()
        assert library.path.read_bytes()==baseline
        # Neither changed settings nor a newly active operation can use an old confirmation.
        w.run_installer();pending=message('Reinstall this game?')
        w.fields['working_dir'].set_text(str(Path(temp)/'changed-directory'))
        respond(pending,'confirm');error=message('Could not complete this action')
        assert 'changed after confirmation' in error.get_body();respond(error,'ok');start_install.assert_not_called()
        w.fields['working_dir'].set_text(str(exe.parent))
        w.run_installer();pending=message('Reinstall this game?')
        with patch.object(w.launcher,'active',return_value=True):respond(pending,'confirm')
        error=message('Could not complete this action');assert 'active operation' in error.get_body();respond(error,'ok');start_install.assert_not_called()
        # A stale confirmation cannot execute after its owning Setup is cancelled.
        w.run_installer();stale=message('Reinstall this game?');w.cancel_editor();settle()
        stale.emit('response','confirm');start_install.assert_not_called();stale.destroy()
        assert w.installer_dialog is None and w.editor is None
        assert library.path.read_bytes()==baseline
    # Persist a preinstalled fixture, including a custom runner and saved paths.
    game=deepcopy(game);game['executable']=str(exe);game['working_dir']=str(exe.parent)
    game['launch']={'proton':'GE-Latest','arguments':['saved argument']};library.save(game);w.show_game(game);w.open_manage()
    saved=library.path.read_bytes();assert w.install_action.get_label()=='Reinstall…'
    w.fields['executable'].set_text('');w.open_installer();assert w.installer_dialog.get_title()=='Reinstall game';w.close_installer();w.fields['executable'].set_text(str(exe))
    exe.unlink();w.update_install_stage();assert w.install_action.get_label()=='Reinstall…'
    assert 'unavailable' in w.setup_status.get_text();exe.write_text('inert')
    # Busy controls and modal close cannot launch or stop the in-flight operation.
    own={'game_id':game['id'],'session_id':str(uuid4()),'operation':'installer','state':'Running','supervisor_pid':123}
    with patch.object(w.launcher,'active',return_value=True),patch.object(w.launcher,'current',return_value=own),patch.object(w.installations,'status',return_value={'phase':'Running','logs':['fixture progress']}),patch.object(w.installations,'start') as no_start,patch.object(w.launcher,'stop') as no_stop:
        w.refresh_launch_state();assert w.install_action.get_label()=='Installation progress…'
        w.open_installer();assert w.install_status.get_text()=='Running'
        assert not w.install_button.get_sensitive() and not w.installer_entry.get_sensitive()
        assert not w.editor_save.get_sensitive() and not w.executable_panel.get_sensitive()
        assert not w.proton_section.get_sensitive() and not w.advanced.get_sensitive()
        assert w.install_cancel.get_visible() and w.install_cancel.get_sensitive() and not w.install_button.get_visible()
        capture(w.installer_dialog,args.output/'installer-running.png')
        valid,bounds=w.install_cancel.compute_bounds(w.installer_dialog)
        assert valid and 0<=bounds.get_y() and bounds.get_y()+bounds.get_height()<=w.installer_dialog.get_height(), 'Active installer cancellation must remain visible without scrolling'
        w.close_installer();w.open_installer();assert w.install_status.get_text()=='Running'
        w.run_installer();error=message('Could not complete this action');respond(error,'ok');settle()
        no_start.assert_not_called();no_stop.assert_not_called()
        own['game_id']='another-game';w.refresh_launch_state();assert not w.install_cancel.get_visible()
        w.close_installer()
    w.refresh_launch_state();assert w.editor_save.get_sensitive()
    assert library.path.read_bytes()==saved
    # Explicit final confirmation passes the same launch settings to the existing
    # installation service. Real inert execution is covered by ui_smoke.py.
    w.open_installer();w.installer_entry.set_text(str(setup));calls=[]
    def accepted(candidate):
        calls.append(deepcopy(candidate));result=deepcopy(candidate)
        result['installation'].update(mode='installer',confirmed=False,session_id=str(uuid4()),prefix=str(Path(temp)/'prefix'),proton='GE-Latest')
        library.save(result);return result
    with patch.object(w.installations,'start',side_effect=accepted):
        w.run_installer();confirmation=message('Reinstall this game?');assert not calls
        respond(confirmation,'confirm');settle();assert len(calls)==1,[(d.get_heading(),d.get_body()) for d in Gtk.Window.get_toplevels() if isinstance(d,Adw.MessageDialog) and d.get_visible()]
        assert calls[0]['launch']['proton']==game['launch']['proton'] and calls[0]['launch']['arguments']==game['launch']['arguments']
        assert calls[0]['installation']['installer']==str(setup)
    w.close_installer();w.cancel_editor();w.open_manage();assert w.confirm_executable_button.get_visible()
    assert w.install_action.get_label()=='Reinstall…';w.open_installer();assert w.installer_entry.get_text()==str(setup)
    w.close_installer();w.editor.set_default_size(480,540);settle();capture(w.editor,args.output/'setup-small.png')
    w.cancel_editor()
    # Legacy installer drafts with no attempt can still choose preinstalled files
    # explicitly, using the real validation service without executing anything.
    legacy=library.new_game();legacy.update(title='Legacy unstarted setup',executable=str(exe),working_dir=str(exe.parent),installation={'mode':'installer','installer':str(setup)})
    runner=Path(temp)/'inert-runner';runner.write_text('#!/bin/sh\nexit 0\n');runner.chmod(0o700)
    legacy['launch']={'runner':str(runner),'proton':'UMU-Latest'};library.save(legacy);w.show_game(legacy);w.open_manage();settle()
    assert w.confirm_executable_button.get_visible() and w.confirm_executable_button.get_label()=='Use existing game executable'
    with patch.object(w.installations,'start') as no_start,patch.object(w.launcher,'start') as no_launch:
        w.confirm_executable_button.emit('clicked');settle();no_start.assert_not_called();no_launch.assert_not_called()
    accepted=next(g for g in library.games() if g['id']==legacy['id'])
    assert accepted['installation']['mode']=='installed' and accepted['installation']['installer']==str(setup),(accepted['installation'],w.log_lines[-3:])
    assert accepted['executable']==str(exe) and not (library.root/'prefixes'/legacy['id']).exists()
    assert w.editor is None
    w.destroy();w.pool.shutdown(wait=True)
print('PASS: single-screen Setup; consistent More Install/Reinstall; preinstalled/missing files; repeated modal open/close/Escape; preserved drafts and defaults; stale picker/confirmation cancelled; active operation disabled actions/progress; explicit final confirmation only; no live execution')
