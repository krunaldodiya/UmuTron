"""Responsive read-only inventory with a separate, explicit maintenance action."""
import threading
from copy import deepcopy

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk

from .prefix_inventory import (
    RECIPES,
    context,
    inspect_prefix,
    inventory_text,
    version_text,
)
from .runtime_maintenance import confirmation_text, install_plan


class PrefixPanel(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.window = window
        self.editor = window.editor
        self.info = None
        self.cancel_scan = threading.Event()
        self.scanning = False
        self.planning = False
        self.was_active = False
        self.signature = None
        self.status = Gtk.Label(label='Inspecting prefix…', wrap=True, xalign=0)
        self.append(self.status)
        self.refresh = Gtk.Button(label='Refresh inventory')
        self.refresh.connect('clicked', lambda *_: self.scan())
        self.append(self.refresh)
        self.inventory = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.inventory.update_property([Gtk.AccessibleProperty.LABEL], ['Read-only prefix inventory'])
        scroll = Gtk.ScrolledWindow(min_content_height=300, vexpand=True)
        scroll.set_child(self.inventory)
        self.append(scroll)
        title = Gtk.Label(label='Manual runtime maintenance', xalign=0)
        title.add_css_class('heading')
        self.append(title)
        self.append(Gtk.Label(label='Inventory is read-only. No game-specific prerequisites are inferred. '
                              'Only the VC++ v14 core recipe is supported for installation; .NET, legacy VC++, '
                              'DirectX, DXVK and VKD3D have no manual actions. No removal controls are provided by this app.',
                              wrap=True, xalign=0))
        self.keys = list(RECIPES)
        self.choice = Gtk.DropDown.new_from_strings([f'{RECIPES[key].title} · {RECIPES[key].architecture} · core ≥ {version_text(RECIPES[key].minimum)}' for key in self.keys])
        self.choice.update_property([Gtk.AccessibleProperty.LABEL], ['Curated runtime recipe and architecture'])
        self.choice.connect('notify::selected', lambda *_: self.update_controls())
        self.append(self.choice)
        self.reason = Gtk.Label(wrap=True, xalign=0)
        self.append(self.reason)
        self.install = Gtk.Button(label='Install missing runtime…')
        self.install.connect('clicked', lambda *_: self.prepare_install())
        self.append(self.install)
        self.cancel = Gtk.Button(label='Cancel runtime installation')
        self.cancel.connect('clicked', lambda *_: window.confirm('Cancel runtime installation?',
                            'Only this operation’s owned processes are stopped. Partial runtime changes and files are kept.',
                            'Cancel installation', lambda: window.stop_game(window.game['id']), True))
        self.append(self.cancel)
        self.operation = Gtk.Label(wrap=True, xalign=0, selectable=True)
        self.append(self.operation)
        self.scan()

    def current_game(self):
        game = deepcopy(self.window.collect())
        game['launch'] = context(game, self.window.library.root, self.window.library.data['settings'].get('default_proton', ''))
        return game

    def alive(self):
        return self.window.editor is self.editor

    def scan(self):
        if self.scanning or not self.alive():
            return
        try:
            game = self.current_game()
        except Exception as error:
            self.status.set_text(str(error))
            return
        self.cancel_scan = threading.Event()
        self.scanning = True
        self.info = None
        self.signature = game
        self.status.set_text('Inspecting prefix in the background…')
        self.update_controls()
        future = self.window.pool.submit(inspect_prefix, game, self.window.library.root, '', self.cancel_scan)
        def finish():
            self.scanning = False
            if not self.alive():
                return False
            try:
                self.info = future.result()
                self.inventory.get_buffer().set_text(inventory_text(self.info))
                self.status.set_text('Read-only snapshot of current draft launch settings. Refresh after external changes.')
            except Exception as error:
                self.status.set_text('Inspection incomplete: ' + str(error))
            self.update_controls()
            return False
        future.add_done_callback(lambda _: GLib.idle_add(finish))

    def update_controls(self):
        if not self.alive():
            return
        active = self.window.launcher.active()
        current = self.window.launcher.current()
        own = active and current.get('operation') == 'runtime' and current.get('game_id') == self.window.game['id']
        reason = 'Choose a curated architecture only when the game vendor requires it; exact game minimum is unknown.'
        enabled = bool(self.info) and not (active or self.scanning or self.planning or self.window.demo)
        if self.window.demo:
            reason = 'Runtime execution is disabled in the demo.'
        elif active:
            reason = 'Finish the active game, installer or runtime operation first.'
        elif self.scanning or self.planning:
            reason = 'Checking prefix evidence…'
        elif self.info:
            try:
                if self.current_game() != self.signature:
                    enabled = False
                    reason = 'Draft launch settings changed. Refresh inventory before maintenance.'
                elif self.info['state'] != 'Created':
                    enabled = False
                    reason = 'An initialized, app-owned prefix is required. Inspection does not create one.'
                else:
                    row = next((r for r in self.info['runtimes'] if r['key'] == self.keys[self.choice.get_selected()]), None)
                    if row is None:
                        enabled = False
                        reason = 'This architecture is not supported by the prefix.'
                    elif row['status'] == 'Installed':
                        enabled = False
                        reason = 'Installed: this architecture and core minimum are positively satisfied. Exact game requirements remain unknown.'
                    else:
                        reason = row['status'] + ' for the selected core requirement. Review evidence and confirmation before installing.'
            except Exception as error:
                enabled = False
                reason = str(error)
        self.reason.set_text(reason)
        self.install.set_sensitive(enabled)
        self.choice.set_sensitive(not (active or self.planning))
        self.refresh.set_sensitive(not (self.scanning or self.planning))
        self.cancel.set_visible(own)
        self.cancel.set_sensitive(own and current.get('state') != 'Stopping')

    def prepare_install(self):
        if not self.install.get_sensitive() or self.window.demo:
            return
        game = self.current_game()
        key = self.keys[self.choice.get_selected()]
        self.planning = True
        self.update_controls()
        future = self.window.pool.submit(install_plan, game, self.window.library.root, key)
        def ready():
            self.planning = False
            if not self.alive():
                return False
            try:
                plan = future.result()
                if self.current_game() != game:
                    raise ValueError('Draft settings changed. Refresh and review again.')
                def start():
                    if not self.alive() or self.current_game() != game:
                        self.window.error(ValueError('Settings changed after confirmation. Review again.'))
                        return
                    self.window.async_job('Preparing explicitly approved runtime maintenance…',
                        lambda: self.window.launcher.start(plan['game'], operation='runtime', runtime_recipe=key,
                                                          runtime_context=plan['context']),
                        lambda _: self.window.refresh_launch_state())
                self.window.confirm('Install this runtime?', confirmation_text(plan), 'Download and open installer', start)
            except Exception as error:
                self.window.error(error)
            self.update_controls()
            return False
        future.add_done_callback(lambda _: GLib.idle_add(ready))

    def poll(self, active, current):
        if not self.alive():
            return
        runtime = current.get('operation') == 'runtime' and current.get('game_id') == self.window.game['id']
        if runtime:
            self.operation.set_text(current.get('state', '') + '\n' + '\n'.join(current.get('logs', [])[-8:]))
        if self.was_active and not active:
            self.scan()
        self.was_active = active
        self.update_controls()
