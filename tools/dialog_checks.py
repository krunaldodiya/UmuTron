"""Synthetic native dialog checks; no live desktop, provider or execution."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if os.environ.get('GDK_BACKEND') != 'broadway':
    raise SystemExit('Use the isolated Broadway renderer, never the live desktop.')
source = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(source))
from game_library.app import Application, Window
from game_library.demo import prepare_demo
from catalog_fixtures import FixtureCatalog
from fullscreen_preview import settle
from gi.repository import Adw, Gdk, Gio, Gtk

args.output.mkdir(parents=True, exist_ok=False)
checks = []
images = []
def hashes():
    return {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source / 'game_library').glob('*.py')}
initial_hashes = hashes()

def check(condition, name):
    checks.append({'check': name, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(name)

def widgets(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from widgets(child)
        child = child.get_next_sibling()

def visible_message():
    return next(w for w in Gtk.Window.get_toplevels() if isinstance(w, Adw.MessageDialog) and w.get_visible())

def respond(dialog, response):
    caption = dialog.get_response_label(response)
    next(w for w in widgets(dialog) if isinstance(w, Gtk.Button) and w.get_label() == caption).emit('clicked')
    settle(100)

def escape(dialog):
    controllers = dialog.observe_controllers()
    handled = False
    for i in range(controllers.get_n_items()):
        controller = controllers.get_item(i)
        if isinstance(controller, Gtk.EventControllerKey):
            handled = controller.emit('key-pressed', Gdk.KEY_Escape, 0, Gdk.ModifierType(0))
            if handled:
                break
    check(handled, 'Native modal Escape handler consumes Escape')
    settle(100)

def capture(widget, name):
    print('CAPTURE', name, flush=True)
    # Snapshot this fixture widget tree only. No desktop capture or raw input.
    widget.queue_draw()
    settle(400)
    for attempt in range(40):
        paintable = Gtk.WidgetPaintable.new(widget)
        snap = Gtk.Snapshot()
        paintable.snapshot(snap, widget.get_width(), widget.get_height())
        node = snap.to_node()
        if node is not None:
            native = widget.get_native()
            native.get_renderer().render_texture(node, None).save_to_png(str(args.output / name))
            images.append({'path': name, 'width': widget.get_width(), 'height': widget.get_height(),
                           'label': 'Synthetic native GTK test render; fictional data; execution disabled'})
            return
        settle(50)
    raise AssertionError('No frame for ' + name)

def footer_visible(dialog):
    footer = next(v for v in widgets(dialog) if v.has_css_class('umu-footer'))
    valid, bounds = footer.compute_bounds(dialog)
    check(valid and bounds.get_y() >= 0 and bounds.get_y() + bounds.get_height() <= dialog.get_height() + 1,
          'Modal footer fully visible without scrolling')
    for control in widgets(footer):
        if isinstance(control, Gtk.Button) and control.get_visible():
            valid, bounds = control.compute_bounds(dialog)
            check(valid and bounds.get_x() >= 0 and bounds.get_x() + bounds.get_width() <= dialog.get_width() + 1,
                  'Visible modal action fits within window')

class LocalCatalog(FixtureCatalog):
    def detail(self, game_id):
        result = super().detail(game_id)
        result['images'] = {}
        return result

with tempfile.TemporaryDirectory(prefix='umutron-dialog-fixture-') as temp:
    os.environ['XDG_CACHE_HOME'] = temp
    library = prepare_demo(True)
    app = Application(demo=True)
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    with patch('game_library.app.Controller'):
        window = Window(app, library, demo=True, catalog_provider=LocalCatalog())
    app.window = window
    window.proton_manager.releases = lambda *a, **k: []
    window.catalog.image_transport = Mock(side_effect=AssertionError('No image transport in dialog fixture'))
    window.present()
    settle(300)
    game = library.games()[0]
    original_games = deepcopy(library.games())
    try:
        with patch.object(window.launcher, 'start', side_effect=AssertionError('Execution forbidden')), \
             patch.object(window.installations, 'start', side_effect=AssertionError('Installer forbidden')):
            for mode, theme, tv in (('desktop-dark', 2, False), ('desktop-light', 1, False), ('fullscreen', 1, True)):
                window.set_tv_mode(False)
                window.theme.set_selected(theme)
                window.set_tv_mode(tv)
                window.unfullscreen()  # Synthetic fixed-size layout, no host display change.
                window.show_game(game)
                settle(200)
                callback = Mock()
                window.confirm('Play Nebula Drift?', '', 'Play', callback)
                dialog = visible_message()
                check(dialog.has_css_class('umu-surface'), mode + ' shared confirmation surface')
                check(dialog.has_css_class('umu-dark') == (tv or theme == 2), mode + ' correct palette')
                check(dialog.has_css_class('umu-tv') == tv, mode + ' mode follows transient owner')
                check(dialog.get_body() == '', 'Title-only prompt has no fabricated subtitle')
                check(dialog.get_default_response() == dialog.get_close_response() == 'cancel', 'Confirmation defaults and closes to Cancel')
                check(dialog.get_response_appearance('confirm') == Adw.ResponseAppearance.SUGGESTED, 'Primary response retains suggested semantics')
                capture(dialog, mode + '-play-native-fixture.png')
                respond(dialog, 'cancel')
                callback.assert_not_called()
                window.confirm('Remove Nebula Drift from library?', 'Only its library entry is removed. Game files, saves, prefixes and Proton are kept.', 'Remove from library', callback, True)
                dialog = visible_message()
                check(dialog.get_response_appearance('confirm') == Adw.ResponseAppearance.DESTRUCTIVE, 'Removal retains destructive semantics')
                capture(dialog, mode + '-remove-native-fixture.png')
                dialog.close()
                settle(150)
                callback.assert_not_called()
                window.show_game_info(game)
                info = next(w for w in Gtk.Window.get_toplevels() if w.get_visible() and w.get_title() == 'Game Info')
                check(info.get_modal() and info.get_transient_for() is window, 'Game Info remains owned modal')
                capture(info, mode + '-info-native-fixture.png')
                footer_visible(info)
                description = next(v for v in widgets(info.info_scroll) if isinstance(v, Gtk.Label))
                valid, bounds = description.compute_bounds(info.info_scroll)
                check(valid and bounds.get_y() < 2 and description.get_height() < info.info_scroll.get_height(),
                      'Short Game Info copy begins at the top of its scroll viewport')
                escape(info)
                check(not info.get_visible(), 'Escape dismisses information dialog')
                window.detail_gear.popup()
                capture(window.detail_gear.get_popover(), mode + '-gear-native-fixture.png')
                check(window.detail_gear.get_popover().has_css_class('umu-dark') == (tv or theme == 2), 'Popover inherits effective palette')
                window.detail_gear.popdown()
                if tv:
                    window.open_tv_options()
                    capture(window.tv_options_dialog, mode + '-options-native-fixture.png')
                    window.tv_options_dialog.close()
                    settle(100)
                else:
                    before = library.path.read_bytes()
                    window.open_manage()
                    window.editor.set_default_size(660, 520)
                    capture(window.editor, mode + '-setup-native-fixture.png')
                    footer_visible(window.editor)
                    window.launch_args.get_buffer().set_text('discarded draft argument')
                    window.open_installer()
                    window.installer_entry.set_text('/fictional/discarded-setup.exe')
                    capture(window.installer_dialog, mode + '-installer-native-fixture.png')
                    footer_visible(window.installer_dialog)
                    check(window.installer_dialog.get_transient_for() is window.editor, 'Installer preserves nested transient ownership')
                    escape(window.installer_dialog)
                    check(window.installer_dialog is None and window.focused_control(window.editor) is window.manage_more, 'Installer Escape restores More focus')
                    escape(window.editor)
                    check(window.editor is None and library.path.read_bytes() == before, 'Setup Escape discards draft without saving')
            # Theme changes must update already open surfaces, not only new ones.
            window.set_tv_mode(False)
            window.theme.set_selected(2)
            window.confirm('Continue?', 'A harmless fixture response.', 'Continue', callback)
            dialog = visible_message()
            window.theme.set_selected(1)
            settle(100)
            check(not dialog.has_css_class('umu-dark'), 'An open dialog follows theme changes')
            respond(dialog, 'confirm')
            check(callback.call_count == 1, 'Explicit response invokes callback once')
            # Import keeps all three choices, with cancel as the safe default.
            with patch.object(window, 'choose_file', side_effect=lambda _, callback: callback(Path('/fixture.zip'))), \
                 patch.object(window, 'async_job', side_effect=lambda _, work, done: done(work())), \
                 patch.object(library, 'preview_import', return_value={'new': 2, 'conflicts': 2, 'titles': ['Nebula Drift', 'Crimson Circuit']}), \
                 patch.object(library, 'import_zip') as import_zip:
                window.import_backup()
                dialog = visible_message()
                check(dialog.get_default_response() == 'cancel' and dialog.get_response_appearance('replace') == Adw.ResponseAppearance.DESTRUCTIVE,
                      'Three-choice conflict prompt retains safe default and destructive replacement')
                capture(dialog, 'desktop-light-import-native-fixture.png')
                respond(dialog, 'cancel')
                import_zip.assert_not_called()
                for response in ('keep', 'replace'):
                    window.import_backup()
                    respond(visible_message(), response)
                    check(import_zip.call_args.args == (Path('/fixture.zip'), response), 'Import passes the selected conflict policy unchanged')
            window.error(ValueError('A long fixture failure message. ' * 30))
            error = visible_message()
            check(error.get_default_response() == error.get_close_response() == 'ok', 'Error acknowledges with OK')
            capture(error, 'desktop-light-error-native-fixture.png')
            respond(error, 'ok')
            window.open_settings()
            settings = next(w for w in Gtk.Window.get_toplevels() if w.get_visible() and w.get_title() == 'Settings')
            capture(settings, 'desktop-light-settings-native-fixture.png')
            window.proton_panel.error(ValueError('Fixture runner is unavailable.'))
            error = visible_message()
            check(error.get_transient_for() is settings and error.get_destroy_with_parent(), 'Proton error belongs to Settings and closes with it')
            capture(error, 'desktop-light-proton-error-native-fixture.png')
            respond(error, 'ok')
            settings.close()
            # Messages must remain usable within a short desktop window.
            print('COMPACT parent resize', flush=True)
            window.set_visible(False)
            window.unrealize()
            window.set_default_size(900, 600)
            window.present()
            settle(300)
            for tv in (False, True):
                window.set_tv_mode(tv)
                window.unfullscreen()
                # GTK binds adjustment animation policy when the scroll area maps.
                # Disable it before construction for deterministic method checks;
                # Broadway without a browser does not acknowledge animation frames.
                settings = Gtk.Settings.get_default()
                animations = settings.get_property('gtk-enable-animations')
                settings.set_property('gtk-enable-animations', False)
                window.error(ValueError('A bounded long fixture failure. ' * 100))
                error = visible_message()
                capture(error, ('compact-fullscreen' if tv else 'compact-desktop') + '-long-error-native-fixture.png')
                check(error.get_height() <= window.get_height(), 'Long message is bounded by compact parent height')
                scroll = error.info_scroll
                text = next(v for v in widgets(scroll) if isinstance(v, Gtk.Label))
                check(text.get_text() == ('A bounded long fixture failure. ' * 100)[:2000], 'Long message preserves all bounded error text')
                viewport = scroll.get_child()
                valid, bounds = text.compute_bounds(viewport)
                check(valid and bounds.get_width() <= viewport.get_width() + 1,
                      'Wrapped message fits the visible viewport horizontally')
                adjustment = scroll.get_vadjustment()
                check(adjustment.get_upper() > adjustment.get_page_size(), 'Long message can scroll to remaining content')
                scroll.grab_focus()
                check(scroll.emit('scroll-child', Gtk.ScrollType.PAGE_DOWN, False), 'Native scrolling action is handled')
                settle(100)
                check(adjustment.get_value() > 0, 'Native scroll action reaches later message text')
                if tv:
                    adjustment.set_value(0)
                    with patch.object(window, 'navigation_window', return_value=error):
                        window.controller_action('pagedown')
                    check(adjustment.get_value() > 0, 'Existing fullscreen controller paging reaches long message text')
                acknowledge = next(v for v in widgets(error) if isinstance(v, Gtk.Button) and v.get_label() == 'OK')
                valid, bounds = acknowledge.compute_bounds(error)
                check(valid and bounds.get_y() >= 0 and bounds.get_y() + bounds.get_height() <= error.get_height() + 1,
                      'Long error keeps acknowledgment reachable')
                respond(error, 'ok')
                settings.set_property('gtk-enable-animations', animations)
            window.set_tv_mode(False)
            for route in ('library', 'store'):
                getattr(window, 'show_' + route)()
                settle(200)
                window.collection_genre.popup()
                capture(window.collection_genre.get_popover(), route + '-filter-native-fixture.png')
                window.collection_genre.popdown()
                check(window.collection_search.grab_focus(), route + ' Search remains focusable')
                check(window.collection_genre.grab_focus(), route + ' Filter remains focusable')
                check(not hasattr(window, 'collection_sort'), route + ' has no Sort control')
            check(library.games() == original_games, 'Dialog navigation and cancellation preserve every saved game')
            check(hashes() == initial_hashes, 'Runtime source is unchanged throughout fixture')
    finally:
        for dialog in list(Gtk.Window.get_toplevels()):
            if dialog is not window:
                dialog.destroy()
        window.exiting = True
        window.catalog_cancel()
        window.catalog_pool.shutdown(wait=True, cancel_futures=True)
        window.controller.close()
        window.destroy()
        window.pool.shutdown(wait=True, cancel_futures=True)
        (args.output / 'results.json').write_text(json.dumps({'checks': checks, 'images': images, 'runtime_source': initial_hashes,
            'scope': 'Synthetic GTK method/signal fixture; no live desktop, physical input, game or installer execution.'}, indent=2) + '\n')
print(f'{len(checks)} native dialog assertions passed; {len(images)} synthetic previews.')
