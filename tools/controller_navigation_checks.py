"""Read-only candidate controller checks on inert GTK widgets, no app services."""
import ast
import hashlib
import json
import os
import time
from pathlib import Path

if os.environ.get('GDK_BACKEND')!='broadway':raise SystemExit('Use an isolated Broadway fixture only.')

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

root = Path(__file__).resolve().parents[1]
source = root / 'game_library/app.py'
contents = source.read_bytes()
tree = ast.parse(contents)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Window')
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ('focused_control', 'move_control_focus', 'controller_action', 'controller_popover', 'mark_browse_input')]
namespace = {'Gtk': Gtk}
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), 'exec'), namespace)

class Probe(Gtk.Window):
    focused_control = namespace['focused_control']
    move_control_focus = namespace['move_control_focus']
    controller_action = namespace['controller_action']
    controller_popover = namespace['controller_popover']
    mark_browse_input = namespace['mark_browse_input']

def settle():
    until = time.monotonic() + .35
    while time.monotonic() < until:
        while GLib.MainContext.default().iteration(False):
            pass
        time.sleep(.005)

checks = []
def check(condition, message):
    checks.append({'check': message, 'passed': bool(condition)})

window = Probe()
row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
play = Gtk.Button(label='Play')
gear = Gtk.MenuButton(icon_name='emblem-system-symbolic')
info = Gtk.Button(label='Game Info')
popover = Gtk.Popover()
menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
items = [Gtk.Button(label=name) for name in ('First', 'Disabled', 'Hidden', 'Second', 'Third')]
for item in items:
    menu.append(item)
items[1].set_sensitive(False)
items[2].set_visible(False)
popover.set_child(menu)
gear.set_popover(popover)
for control in (play, gear, info):
    row.append(control)
window.set_child(row)
window.detail_primary = play
window.detail_gear = gear
window.controller_enabled = lambda: True
target = [window]
window.navigation_window = lambda: target[0]
window.route = 'detail'
window.game = {'id': 'inert-fixture'}
window.tv_home_tab, window.tv_library_tab, window.tv_games_tab, window.tv_menu = [Gtk.Button() for _ in range(4)]
window.editor = None
window.tv_mode = True
window.routes = {}
window.return_from_detail = lambda: callbacks.append('route')
window.open_tv_options = lambda: callbacks.append('options')
window.update_focus_outline = lambda: None
callbacks = []
def menu_action(index):
    callbacks.append(index)
    gear.popdown()
for index, item in enumerate(items):
    item.connect('clicked', lambda button, index=index: menu_action(index))
play.connect('clicked', lambda *_: callbacks.append('play'))
window.present()
settle()
native_size = [window.get_width(), window.get_height()]

try:
    play.grab_focus()
    window.controller_action('right')
    check(window.focused_control(window) is gear, 'Right reaches gear')
    window.controller_action('right')
    check(window.focused_control(window) is info, 'Right reaches info from gear')
    window.controller_action('left')
    check(window.focused_control(window) is gear, 'Left returns to gear')
    window.controller_action('select')
    settle()
    check(window.controller_popover(window) is popover and window.focused_control(window) is items[0], 'Select opens menu and focuses first')
    for action, expected in [('down', 3), ('down', 4), ('down', 0), ('up', 4), ('previous', 3), ('next', 4)]:
        window.controller_action(action)
        check(window.focused_control(window) is items[expected], f'{action} reaches item {expected} within popup')
    for action in ('left', 'right', 'play', 'desktop', 'pageup', 'pagedown'):
        window.controller_action(action)
        check(window.focused_control(window) is items[4] and not callbacks, f'{action} does not escape popup')
    window.controller_action('select')
    settle()
    check(callbacks == [4] and not popover.get_visible(), 'Select invokes selected action exactly once')
    callbacks.clear()

    gear.grab_focus()
    window.controller_action('select')
    settle()
    window.controller_action('back')
    settle()
    check(not popover.get_visible() and window.focused_control(window) is gear and not callbacks and window.route == 'detail', 'Back closes menu, restores gear, retains detail')

    gear.set_sensitive(False)
    play.grab_focus()
    window.controller_action('right')
    check(window.focused_control(window) is info, 'Disabled gear skipped')
    gear.set_sensitive(True)
    gear.set_visible(False)
    settle()
    play.grab_focus()
    window.controller_action('right')
    check(window.focused_control(window) is info, 'Hidden gear skipped')
    gear.set_visible(True)
    settle()

    gear.popup()
    settle()
    # Select must not activate a background control if focus is unexpectedly outside.
    play.grab_focus()
    window.controller_action('select')
    settle()
    check(not callbacks and window.focused_control(window) is items[0], 'Select outside open popup restores menu focus without activating Play')
    gear.popdown()
    settle()

    modal = Gtk.Window(transient_for=window, modal=True)
    modal_row = Gtk.Box()
    modal_a, modal_b = Gtk.Button(label='A'), Gtk.Button(label='B')
    modal_row.append(modal_a)
    modal_row.append(modal_b)
    modal.set_child(modal_row)
    modal.present()
    settle()
    target[0] = modal
    check(window.controller_popover(modal) is None, 'Different modal never uses detail popup')
    modal_a.grab_focus()
    window.controller_action('next')
    check(window.focused_control(modal) is modal_b, 'Separate modal keeps its own navigation')
    window.controller_action('back')
    settle()
    check(not modal.get_visible() and not callbacks, 'Back closes separate modal without route return')
    modal.destroy()
    target[0] = window

    gear.popup()
    settle()
    row.set_visible(False)
    settle()
    check(not gear.get_mapped(), 'Hidden parent unmaps gear')
    check(window.controller_popover(window) is None, 'Unmapped attached gear cannot intercept')
    row.set_visible(True)
    gear.popdown()
    settle()
    row.remove(gear)
    # Retain the old gear exactly as a route rebuild can after detaching it.
    check(gear.get_root() is None and window.controller_popover(window) is None, 'Detached old gear cannot intercept')

    check(source.read_bytes() == contents, 'Candidate bytes unchanged during probe')
finally:
    window.destroy()
    settle()

print(json.dumps({'app_sha256': hashlib.sha256(contents).hexdigest(), 'methods': {m.name: hashlib.sha256(ast.unparse(m).encode()).hexdigest() for m in methods}, 'native_window': native_size, 'checks': checks}, indent=2))
assert all(check['passed'] for check in checks), 'See failed native assertions'
