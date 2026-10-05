"""Native GTK Save/reopen fixture on isolated Broadway; no rendered-frame claim.

A browser client is optional for these widget/state assertions. With no client,
GTK allocation can remain zero: this verifies real native signals and persistence,
not layout, pixels, keyboard focus, or hardware-controller behavior.
"""
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock,patch

SOURCE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SOURCE),str(SOURCE/'tests'),str(SOURCE/'tools')]
if os.environ.get('GDK_BACKEND')!='broadway':raise SystemExit('An isolated Broadway display is required.')
from catalog_fixtures import FixtureCatalog
from game_library.app import Application,Window
from game_library.library import Library
from test_setup_save import SetupSaveTests
from gi.repository import Gio,Gtk


def widgets(parent):
    yield parent
    child=parent.get_first_child()
    while child:
        yield from widgets(child);child=child.get_next_sibling()


def make_window(library):
    app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name='';controller.return_value.error=''
        w=Window(app,library,demo=True,catalog_provider=FixtureCatalog())
    app.window=w;w.proton_manager.releases=lambda *_args,**_kwargs:[]
    w.launcher.start=Mock(side_effect=AssertionError('No execution in native fixture'))
    w.error=Mock();w.present()
    return app,w


def close(app,w):
    if w.editor:w.cancel_editor()
    w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True)
    w.destroy();app.quit()


if len(sys.argv)>1:
    assert len(sys.argv)==4 and sys.argv[1]=='--reopen'
    root=Path(sys.argv[2]);assert (root/'NATIVE-SETUP-SAVE-FIXTURE').read_text()=='Inert temporary native fixture only.\n'
    app,w=make_window(Library(root))
    try:
        game=w.library.games()[0];w.show_game(game)
        assert w.detail_primary.get_label()==sys.argv[3],w.detail_primary.get_label()
        assert not w.detail_primary.get_sensitive(),'Demo execution must remain disabled'
        w.launcher.start.assert_not_called()
        print('PASS: fresh-process native primary '+w.detail_primary.get_label())
    finally:close(app,w)
    raise SystemExit()

fixture=SetupSaveTests();fixture.setUp();app,w=make_window(fixture.library)
try:
    marker=fixture.library.root/'NATIVE-SETUP-SAVE-FIXTURE';marker.write_text('Inert temporary native fixture only.\n')
    before_journal=fixture.record_path.read_bytes()
    w.show_game(fixture.game);assert w.detail_primary.get_label()=='Setup'
    w.open_manage();assert w.editor is not None
    # The installer has already completed in the inert journal. Reopening and
    # closing its native progress dialog must not itself confirm anything.
    w.open_installer();assert w.installer_dialog is not None
    w.close_installer();assert not fixture.library.games()[0]['installation']['confirmed']
    w.fields['executable'].set_text(str(fixture.exe));w.fields['working_dir'].set_text(str(fixture.exe.parent))
    assert w.editor_save.get_sensitive();w.editor_save.emit('clicked')
    w.error.assert_not_called();assert w.editor is None
    saved=Library(fixture.library.root).games()[0]
    assert saved['installation']['confirmed'] and w.detail_primary.get_label()=='Play'
    assert saved['launch']['prefix']==fixture.game['installation']['prefix'] and saved['launch']['proton']==str(fixture.proton)
    assert fixture.record_path.read_bytes()==before_journal
    w.open_manage();assert w.fields['executable'].get_text()==str(fixture.exe)
    w.cancel_editor();assert w.detail_primary.get_label()=='Play'
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--reopen',str(fixture.library.root),'Play'],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    print(result.stdout.strip(),flush=True)

    # Old persisted false flag: resaving the unchanged valid path is explicit validation.
    saved['installation']['confirmed']=False;fixture.library.save(saved);w.show_game(saved);w.open_manage();w.editor_save.emit('clicked')
    w.error.assert_not_called();assert w.detail_primary.get_label()=='Play'

    # P2 regression: changing an unstarted installer draft must not hide the
    # installer that actually completed. Exercise the real modal entry and Save.
    replacement=fixture.root/'replacement.exe';replacement.write_text('Inert replacement installer')
    alias=fixture.root/'aliases/alias.exe';alias.parent.mkdir();alias.symlink_to(fixture.installer)
    hardlink=fixture.root/'aliases/hardlink.exe';hardlink.hardlink_to(fixture.installer)
    fixture.library.save(fixture.game);w.show_game(fixture.game)
    for executable in (fixture.installer,alias,hardlink):
        w.open_manage();w.open_installer();w.installer_entry.set_text(str(replacement));w.close_installer()
        w.fields['executable'].set_text(str(executable));w.fields['working_dir'].set_text(str(executable.parent))
        before=fixture.library.path.read_bytes();w.error.reset_mock();w.editor_save.emit('clicked')
        w.error.assert_called_once();assert w.editor is not None and fixture.library.path.read_bytes()==before
        w.cancel_editor();assert w.detail_primary.get_label()=='Setup'
    w.open_manage();w.open_installer();w.installer_entry.set_text(str(replacement));w.close_installer()
    w.error.reset_mock();w.editor_save.emit('clicked');w.error.assert_not_called()
    saved=Library(fixture.library.root).games()[0]
    assert saved['installation']['installer']==str(replacement)
    assert saved['installer_attempt']['executable']==str(fixture.installer.resolve())
    w.open_manage();w.fields['executable'].set_text(str(alias));before=fixture.library.path.read_bytes()
    w.editor_save.emit('clicked');w.error.assert_called_once();assert fixture.library.path.read_bytes()==before
    w.fields['executable'].set_text(str(fixture.exe));w.fields['working_dir'].set_text(str(fixture.exe.parent))
    w.error.reset_mock();w.editor_save.emit('clicked');w.error.assert_not_called()
    assert w.detail_primary.get_label()=='Play'
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--reopen',str(fixture.library.root),'Play'],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    print('PASS: changed unstarted installer draft; completed installer, symlink and hardlink rejected; saved draft/reopen retains binding; actual game becomes Play and survives fresh process.',flush=True)

    # Cancel is a real native button signal and never writes the draft.
    fixture.library.save(fixture.game);w.show_game(fixture.game);w.open_manage();w.fields['executable'].set_text(str(fixture.exe))
    before=fixture.library.path.read_bytes()
    next(c for c in widgets(w.editor) if isinstance(c,Gtk.Button) and c.get_label()=='Cancel').emit('clicked')
    assert fixture.library.path.read_bytes()==before and w.detail_primary.get_label()=='Setup'

    # Invalid candidates stay in the editor, with the saved record unchanged.
    for value in (str(fixture.installer),str(fixture.root/'missing.exe')):
        w.open_manage();w.fields['executable'].set_text(value);before=fixture.library.path.read_bytes();w.error.reset_mock()
        w.editor_save.emit('clicked');w.error.assert_called_once()
        assert w.editor is not None and fixture.library.path.read_bytes()==before
        w.cancel_editor();assert w.detail_primary.get_label()=='Setup'

    # Save remains guarded even if an operation starts while this editor is open.
    w.open_manage();w.fields['executable'].set_text(str(fixture.exe));before=fixture.library.path.read_bytes();w.error.reset_mock()
    with patch.object(w.launcher,'active',return_value=True):
        w.update_install_stage();assert not w.editor_save.get_sensitive()
        w.editor_save.emit('clicked');w.error.assert_called_once()
    assert fixture.library.path.read_bytes()==before;w.cancel_editor()

    # An ended but canceled installer does not acquire completion from Save.
    fixture.record.update(state='Stopped',code=0);fixture.write_record();w.error.reset_mock()
    w.open_manage();w.fields['executable'].set_text(str(fixture.exe));w.fields['working_dir'].set_text(str(fixture.exe.parent));w.editor_save.emit('clicked')
    w.error.assert_not_called();assert w.detail_primary.get_label()=='Setup'
    assert not Library(fixture.library.root).games()[0]['installation']['confirmed']
    w.launcher.start.assert_not_called()
    print('PASS: native Save/Cancel signals, completed installer popup close, validated Setup→Play, editor reopen and fresh process, unchanged-path repair, invalid/missing files, active guard and canceled-session exclusion; no execution.',flush=True)
    print('LIMIT: native widgets had no browser-rendered frame; pixels, layout and focus were not evaluated.',flush=True)
finally:
    close(app,w);fixture.doCleanups()
