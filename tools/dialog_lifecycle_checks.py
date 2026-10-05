"""Inert native lifetime regressions: no live desktop, app data or execution."""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import weakref
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if os.environ.get('GDK_BACKEND') != 'broadway':
    raise SystemExit('Use only the owned isolated renderer.')
sys.path[:0] = [str(args.source), str(args.source / 'tools')]
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk
from game_library.dialogs import modal_window, dialog_body, message_dialog, style_surface
from fullscreen_preview import settle

args.output.mkdir(parents=True, exist_ok=False)
checks = []
observations = {}
source_hash = hashlib.sha256((args.source / 'game_library/dialogs.py').read_bytes()).hexdigest()

def check(value, name, **details):
    checks.append({'check': name, 'passed': bool(value), **details})
    print(('PASS ' if value else 'FAIL ') + name, flush=True)

def collect():
    for _ in range(3):
        gc.collect()
        settle(50)

def remaining(refs):
    return sum(ref() is not None for ref in refs)

def discard(parent, styled):
    refs = {'messages': [], 'popovers': []}
    for index in range(10):
        if styled:
            child = message_dialog(parent, 'Disposable fixture ' + str(index))
        else:
            child = Adw.MessageDialog.new(parent, 'Baseline fixture', '')
            child.add_response('ok', 'OK')
        child.present()
        settle(20)
        child.destroy()
        refs['messages'].append(weakref.ref(child))
        del child
    for _ in range(3):
        popup = Gtk.Popover()
        if styled:
            style_surface(popup)
        refs['popovers'].append(weakref.ref(popup))
        del popup
    collect()
    return {name: remaining(values) for name, values in refs.items()}

Adw.init()
manager = Adw.StyleManager.get_default()
root = Gtk.Window(default_width=900, default_height=600)
root.present()
settle(100)
connections = []
original_connect = manager.connect

def track_connect(name, *args):
    identifier = original_connect(name, *args)
    if name == 'notify::dark':
        connections.append(identifier)
    return identifier

try:
    # A recording Mock would itself retain every callback and native weak-ref
    # wrapper in its call history. Observe only integer handler IDs instead.
    with patch.object(manager, 'connect', new=track_connect):
        # Direct regression for the independent review's 10 + 3 retained objects.
        baseline = discard(root, False)
        candidate = discard(root, True)
        observations['released_objects'] = {'baseline': baseline, 'candidate': candidate}
        check(baseline == {'messages': 0, 'popovers': 0}, 'Native baseline releases ten dialogs and three discarded popovers', counts=baseline)
        check(candidate == baseline, 'Styled dialogs and discarded popovers release just like baseline', counts=candidate)

        live = modal_window(root, 'Live theme fixture')
        content = dialog_body(live)
        control = Gtk.MenuButton(label='Fixture menu')
        content.append(control)
        # Weak observation; GTK container references should keep the same Python
        # receiver valid while mapped, despite releasing temporary local aliases.
        live.present()
        settle(100)
        for scheme, dark in ((Adw.ColorScheme.FORCE_DARK, True), (Adw.ColorScheme.FORCE_LIGHT, False)):
            manager.set_color_scheme(scheme)
            settle(50)
            check(live.has_css_class('umu-dark') == dark, 'Mapped modal follows the effective theme', dark=dark)
        for _ in range(3):
            live.set_visible(False)
            manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            live.present()
            settle(50)
            check(live.has_css_class('umu-dark'), 'Hidden modal reopens with current dark palette')
            manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            settle(50)
            check(not live.has_css_class('umu-dark'), 'Reopened modal keeps its live theme subscription')

        # Popup native ownership, repeated opening and reparenting must survive
        # removing the global listener's strong reference to the receiver.
        popup = style_surface(Gtk.Popover())
        popup.set_child(Gtk.Button(label='Menu fixture action'))
        control.set_popover(popup)
        popup_ref = popup.weak_ref()
        del popup
        collect()
        check(popup_ref() is not None, 'Attached popup survives through its GTK parent')
        for _ in range(3):
            control.popup()
            settle(60)
            manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            settle(40)
            check(control.get_popover().has_css_class('umu-dark'), 'Mapped popup follows dark theme')
            manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            settle(40)
            check(not control.get_popover().has_css_class('umu-dark'), 'Mapped popup follows light theme')
            control.popdown()
            settle(60)
        popup = control.get_popover()
        control.set_popover(None)
        tv_parent = Gtk.Window(default_width=600, default_height=400)
        tv_parent.tv_mode = True
        tv_control = Gtk.MenuButton(label='Fullscreen fixture menu')
        tv_parent.set_child(tv_control)
        tv_parent.present()
        tv_control.set_popover(popup)
        del popup
        tv_control.popup()
        settle(100)
        check(tv_control.get_popover().has_css_class('umu-tv') and tv_control.get_popover().has_css_class('umu-dark'),
              'Reparented popup inherits fullscreen owner even under a light theme')
        tv_control.popdown()
        settle(100)
        popup = tv_control.get_popover()
        tv_control.set_popover(None)
        control.set_popover(popup)
        del popup
        control.popup()
        settle(100)
        check(not control.get_popover().has_css_class('umu-tv') and not control.get_popover().has_css_class('umu-dark'),
              'Popup returns to desktop density and effective light palette')
        control.popdown()
        settle(100)
        control.set_popover(None)
        collect()
        check(popup_ref() is None, 'Previously mapped and reparented popup releases after detachment')
        tv_parent.destroy()
        del tv_control, tv_parent
        live_ref = weakref.ref(live)
        live.destroy()
        del content, control, live
        collect()
        check(live_ref() is None, 'Closed modal releases after live theme and reopen cycles')

        settings = style_surface(Adw.PreferencesWindow(title='Settings fixture'), root)
        settings.present()
        manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        settle(80)
        check(settings.has_css_class('umu-dark'), 'Live PreferencesWindow receives theme changes')
        settings_ref = weakref.ref(settings)
        settings.destroy()
        del settings
        collect()
        check(settings_ref() is None, 'Destroyed PreferencesWindow releases its theme listener and receiver')

        # Match the reviewer's baseline distinction: a destroyed GTK parent may
        # legitimately remain referenced until its explicit Python owner lets go.
        for styled in (False, True):
            if styled:
                parent = modal_window(root, 'Nested parent fixture')
                dialog_body(parent)
            else:
                parent = Gtk.Window(title='Native parent fixture', transient_for=root, modal=True)
            parent.present()
            settle(50)
            if styled:
                child = message_dialog(parent, 'Nested prompt fixture', responses=(('cancel', 'Cancel'), ('confirm', 'Confirm')),
                                       default='cancel', close='cancel')
            else:
                child = Adw.MessageDialog.new(parent, 'Native nested fixture', '')
                child.set_destroy_with_parent(True)
                child.add_response('cancel', 'Cancel')
                child.add_response('confirm', 'Confirm')
                child.set_default_response('cancel')
                child.set_close_response('cancel')
            responses = []
            child.connect('response', lambda _, response: responses.append(response))
            child.present()
            settle(50)
            parent_ref = weakref.ref(parent)
            parent.destroy()
            del parent
            collect()
            native_gone = not child.get_mapped() and not child.get_realized() and child not in list(Gtk.Window.get_toplevels())
            check(parent_ref() is None, 'Destroyed parent releases after external references are dropped', styled=styled)
            check(native_gone, 'Nested prompt loses mapped/native lifetime with its released parent', styled=styled)
            check('confirm' not in responses, 'Parent destruction never activates the affirmative response', styled=styled)
            child_ref = weakref.ref(child)
            child.destroy()
            del child
            collect()
            check(child_ref() is None and parent_ref() is None, 'Explicit nested cleanup leaves no parent or child retained', styled=styled)

        # No dead global callbacks should accumulate as weak receivers vanish.
        collect()
        connected = [identifier for identifier in connections if manager.handler_is_connected(identifier)]
        check(bool(connections) and not connected, 'Observed live theme subscriptions are all disconnected after disposal', remaining_handlers=len(connected), created_handlers=len(connections))
        check(hashlib.sha256((args.source / 'game_library/dialogs.py').read_bytes()).hexdigest() == source_hash,
              'Runtime source unchanged throughout lifecycle fixture')
finally:
    for window in list(Gtk.Window.get_toplevels()):
        window.destroy()
    (args.output / 'results.json').write_text(json.dumps({'checks': checks, 'observations': observations,
        'dialogs_sha256': source_hash, 'scope': 'Inert GTK weak-reference, signal and native-window lifetime checks; no app services, live desktop or physical input.'}, indent=2) + '\n')
print(json.dumps({'passed': sum(check['passed'] for check in checks), 'total': len(checks)}), flush=True)
assert all(check['passed'] for check in checks), 'See lifecycle results.json'
