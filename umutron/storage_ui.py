"""Native Storage registration and drive choice; no filesystem payload writes."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from gi.repository import Adw, GLib, Gtk

from .storage import StorageError
from .dialogs import style_surface, message_dialog


def size_text(value):
    if value is None: return 'Unknown'
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'):
        if value < 1024 or unit == 'PiB':
            return f'{value:.0f} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024


def caption(text, style='dim-label'):
    label = Gtk.Label(label=text, xalign=0, wrap=True)
    label.add_css_class(style)
    return label


def action(label, callback, primary=False):
    control = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
    if primary: control.add_css_class('suggested-action')
    control.storage_action_handler=control.connect('clicked', lambda *_: callback())
    return control


def disconnect_actions(widget):
    """Release only Storage-owned callbacks before native children disappear."""
    handler=getattr(widget,'storage_action_handler',None)
    if handler is not None:
        if widget.handler_is_connected(handler):widget.disconnect(handler)
        widget.storage_action_handler=None
    child=widget.get_first_child()
    while child:
        disconnect_actions(child);child=child.get_next_sibling()


class AsyncView:
    def init_async(self):
        self.active=True;self.pending=False;self.cancelled=Event()
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='umutron-storage')

    def query(self,work,done):
        if not self.active or self.pending:return
        self.pending=True;future=self.executor.submit(work)
        def completed():
            if not self.active:return False
            self.pending=False
            try:done(future.result())
            except Exception as error:self.show_error(error)
            return False
        future.add_done_callback(lambda _:GLib.idle_add(completed))

    def dispose_async(self):
        if not self.active:return
        self.active=False;self.cancelled.set();self.executor.shutdown(wait=False,cancel_futures=True)


class VolumePicker(AsyncView,Adw.Window):
    """Explicit metadata registration; the selected mount is revalidated."""
    def __init__(self,parent,service,role,saved):
        super().__init__(title='Choose cache drive' if role=='cache' else 'Add install drive',
                         transient_for=parent,modal=True,default_width=580,default_height=480)
        style_surface(self,parent)
        self.init_async();self.service=service;self.role=role;self.saved=saved
        self.selected=None;self.options=[]
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);header=Adw.HeaderBar();box.append(header)
        header.pack_start(action('Cancel',self.close))
        self.confirm=action('Add drive',self.commit,True);self.confirm.set_sensitive(False);header.pack_end(self.confirm)
        scroll=Gtk.ScrolledWindow(vexpand=True);box.append(scroll)
        self.content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16,margin_top=20,margin_bottom=24,margin_start=24,margin_end=24);scroll.set_child(self.content)
        self.content.append(caption('Choose a mounted partition.', 'heading'))
        self.content.append(caption('Registration keeps existing game locations unchanged. No partition, folder or game file is created.'))
        if role=='cache':self.content.append(caption('Cache is for future archive downloads. Manual Setup and local installers do not require it.'))
        self.error=caption('Checking connected drives…');self.content.append(self.error)
        self.listing=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE);self.listing.add_css_class('boxed-list');self.content.append(self.listing)
        self.content.append(action('Refresh drives',self.refresh))
        self.set_content(box);self.connect('close-request',self.closed);self.connect('unrealize',self.closed);self.refresh()

    def refresh(self):
        if self.pending:return
        self.selected=None;self.confirm.set_sensitive(False)
        self.query(self.service.choices,self.populate)

    def populate(self,state):
        volumes=state['volumes'];registered=state['registered']
        while self.listing.get_first_child():self.listing.remove(self.listing.get_first_child())
        self.options=[];self.error.set_text('' if volumes else 'No mounted internal partitions found. Mount a supported internal partition, then refresh.');self.error.set_visible(not volumes)
        for volume in volumes:
            reason='Already registered — change roles on its Storage card.' if volume.volume_id in registered else volume.reason or (volume.managed_reason if self.role=='cache' else '')
            if sum(v.volume_id==volume.volume_id for v in volumes)!=1:reason='Drive identity is ambiguous.'
            row=Adw.ActionRow(title=volume.label,subtitle=volume.root+'\n'+(reason or size_text(volume.free_bytes)+' available of '+size_text(volume.total_bytes)+' · '+(volume.managed_reason or 'Writable')))
            row.set_use_markup(False);row.set_subtitle_lines(4)
            control=Gtk.CheckButton(valign=Gtk.Align.CENTER)
            if self.options:control.set_group(self.options[0][1])
            control.set_sensitive(not reason);control.storage_action_handler=control.connect('toggled',self.choose,volume)
            row.add_prefix(Gtk.Image.new_from_icon_name('drive-harddisk-symbolic'));row.add_suffix(control)
            row.set_activatable_widget(control);self.listing.append(row);self.options.append((volume,control))

    def choose(self,control,volume):
        if self.active and not self.pending and control.get_active():self.selected=volume;self.confirm.set_sensitive(True)

    def show_error(self,error):
        self.error.set_text(str(error));self.error.set_visible(True);self.error.add_css_class('error')
        self.confirm.set_sensitive(self.selected is not None)

    def commit(self):
        if not self.active or self.pending or self.selected is None:return
        selected=self.selected;self.confirm.set_sensitive(False)
        def completed(_):self.saved();self.close()
        self.query(lambda:self.service.register(selected,self.role,cancelled=self.cancelled.is_set),completed)

    def closed(self,*_):
        self.dispose_async();self.saved=None;disconnect_actions(self);return False


class StoragePage(AsyncView,Adw.PreferencesPage):
    def __init__(self,service,parent,changed=None):
        super().__init__(title='Storage',icon_name='drive-harddisk-symbolic')
        self.init_async();self.service=service;self.parent=parent;self.changed=changed
        self.picker=None;self.removal_dialog=None;self.rows={};self.groups=[];self.state=None
        intro=Adw.PreferencesGroup(title='Your game drives',description='Automatic downloads and installs are not available yet. Manual Setup and Windows installers keep their own paths.')
        self.add(intro);self.notice=caption(service.reason);self.notice.set_visible(bool(service.reason));self.notice.set_margin_bottom(12);intro.add(self.notice)
        self.error=caption('Checking storage…');intro.add(self.error)
        self.refresh_control=action('Refresh drives',self.refresh);self.refresh_control.set_sensitive(service.enabled);self.refresh_control.set_margin_top(12);self.refresh_control.set_margin_bottom(6);intro.add(self.refresh_control)
        self.parent_handlers=[parent.connect('close-request',self.closed),parent.connect('unrealize',self.closed)];self.refresh()

    def closed(self,*_):
        self.dispose_async()
        disconnect_actions(self)
        parent=self.parent;self.parent=None
        if parent:
            for handler in self.parent_handlers:
                if parent.handler_is_connected(handler):parent.disconnect(handler)
        self.parent_handlers=[];self.changed=None
        picker=self.picker;self.picker=None
        removal=self.removal_dialog;self.removal_dialog=None
        if picker:picker.close()
        if removal:removal.close()
        return False

    def show_error(self,error):
        if self.active:self.error.set_text(str(error));self.error.set_visible(True)

    def change(self,operation):self.query(operation,lambda _:self.refresh())

    def open_picker(self,role):
        if not self.active or self.pending or not self.service.enabled:return
        if self.picker and self.picker.active:self.picker.present();return
        self.picker=VolumePicker(self.parent,self.service,role,self.refresh);self.picker.present()

    def request_remove(self,row):
        if not self.active:return
        dialog=message_dialog(self.parent,'Remove this storage registration?',
            row['label']+'\n\nOnly the registration is removed. Game files, saves and existing folders stay on the drive. Manual Setup and Play are unaffected.',
            responses=(('cancel','Keep drive'),('remove','Remove registration')),default='cancel',close='cancel',destructive='remove')
        pending=True
        def responded(_dialog,response):
            nonlocal pending
            if not pending:return
            pending=False
            if self.active and response=='remove':self.change(lambda:self.service.remove(row['id']))
        dialog.connect('response',responded);self.removal_dialog=dialog;dialog.present()

    def drive_card(self,row,group):
        card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,margin_top=10,margin_bottom=12,margin_start=14,margin_end=14)
        heading=Gtk.Box(spacing=12);icon=Gtk.Image.new_from_icon_name('drive-harddisk-symbolic');icon.set_pixel_size(28);heading.append(icon)
        names=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,hexpand=True)
        names.append(caption(row['label'],'heading'));roles=('Default install drive' if row['default'] else 'Install drive') if 'install' in row['roles'] else ''
        if 'cache' in row['roles']:roles+=(' · ' if roles else '')+'Download cache'
        names.append(caption(roles));heading.append(names)
        menu=Gtk.MenuButton(icon_name='view-more-symbolic',valign=Gtk.Align.CENTER,tooltip_text='Drive options')
        popover=style_surface(Gtk.Popover());popover.browse_owner=menu;choices=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,margin_top=6,margin_bottom=6,margin_start=6,margin_end=6)
        def apply(callback):popover.popdown();callback()
        if 'install' in row['roles'] and not row['default']:choices.append(action('Make default',lambda:apply(lambda:self.change(lambda:self.service.set_default(row['id'])))))
        if 'install' not in row['roles']:
            choices.append(action('Use for installations',lambda:apply(lambda:self.change(lambda:self.service.add_role(row['id'],'install')))))
        if 'cache' in row['roles'] and len(row['roles'])>1:
            cache=action('Remove cache role',lambda:apply(lambda:self.change(lambda:self.service.remove_role(row['id'],'cache'))))
            cache.set_sensitive(not row['busy']);choices.append(cache)
        elif not any('cache' in r['roles'] for r in self.state['registrations']):
            cache=action('Also use for download cache',lambda:apply(lambda:self.change(lambda:self.service.add_role(row['id'],'cache'))))
            cache.set_sensitive(row['status']=='ready' and not row.get('managed_reason'));choices.append(cache)
        remove=action('Remove registration',lambda:apply(lambda:self.request_remove(row)));remove.set_sensitive(not row['busy'])
        choices.append(remove);popover.set_child(choices);menu.set_popover(popover);heading.append(menu);card.append(heading)
        path=caption(row['root']);path.set_selectable(True);card.append(path)
        if row['status']=='ready':
            card.append(Gtk.ProgressBar(fraction=1-row['free']/row['total'] if row['total'] else 0))
            card.append(caption(f"{size_text(row['free'])} available of {size_text(row['total'])}"))
            if 'install' in row['roles']:card.append(caption('Connected · '+('Managed writes unavailable' if row.get('managed_reason') else 'Writable for managed installation')))
        else:card.append(caption(('Offline · last known location\n' if row['status']=='offline' else '')+row['reason'],'warning'))
        if 'cache' in row['roles']:card.append(caption('Cache: '+row['paths']['cache']))
        if row.get('managed_reason'):card.append(caption('Managed cache/archive use unavailable: '+row['managed_reason']))
        if row['busy']:card.append(caption('A job has reserved space on this drive.'))
        frame=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,margin_bottom=8);frame.add_css_class('card');frame.append(card);group.add(frame)
        self.rows[row['id']]={'data':row,'card':frame,'remove':remove,'menu':menu}

    def refresh(self):
        if not self.active or self.pending:return
        self.query(self.service.snapshot,self.render)

    def render(self,state):
        self.state=state;self.error.set_visible(False)
        for group in self.groups:self.remove_group(group)
        self.groups=[];self.rows={}
        group=Adw.PreferencesGroup(title='Registered partitions',description='Choose a partition once. Its install and cache roles share the same capacity.');self.add(group);self.groups.append(group)
        for row in state['registrations']:self.drive_card(row,group)
        if not state['registrations']:
            group.add(Adw.ActionRow(title='Add your first installation drive',subtitle='Only verified internal partitions are available. Their mounted root paths cannot be edited.'))
        control=action('Add drive…',lambda:self.open_picker('install'));control.set_sensitive(self.service.enabled);group.add(control)
        note=Adw.PreferencesGroup(description='Registration never moves game files or verifies them for uninstall.')
        self.add(note);self.groups.append(note)
        if self.changed:self.changed(state)

    def remove_group(self,group):
        disconnect_actions(group)
        Adw.PreferencesPage.remove(self,group)


class InstallDriveDialog(Adw.Window):
    """Choose a fixture target and review BOTH budgets; never starts/reserves jobs."""
    def __init__(self, parent, service, plan, selected):
        super().__init__(title='Choose install drive', transient_for=parent, modal=True,
                         default_width=620, default_height=620)
        self.service = service; self.plan = plan; self.selected_callback = selected
        self.active = True; self.install_id = None; self.options = []; self.last_quote = None
        self.parent = parent; self.parent_close_id = parent.connect('close-request', self.parent_closed)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); header = Adw.HeaderBar(); box.append(header)
        header.pack_start(action('Cancel', self.close))
        self.confirm = action('Use this drive', self.commit, True); self.confirm.set_sensitive(False); header.pack_end(self.confirm)
        scroll = Gtk.ScrolledWindow(vexpand=True); box.append(scroll)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=20,
                          margin_bottom=24, margin_start=24, margin_end=24); scroll.set_child(content)
        content.append(caption('Room for the download and the game', 'title-2'))
        content.append(caption(f'Archive: {size_text(plan.archive_bytes)} · Expanded: {size_text(plan.expanded_bytes)}'))
        content.append(caption(f'Cache: {size_text(plan.archive_bytes)} archive + {size_text(plan.cache_extra)} temporary files\n'
                               f'Install: {size_text(plan.expanded_bytes)} expanded + {size_text(plan.install_margin)} margin + {size_text(plan.install_extra)} temporary files'))
        self.error = caption('', 'warning'); content.append(self.error)
        listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE); listing.add_css_class('boxed-list'); content.append(listing)
        self.budgets = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12); content.append(self.budgets)
        content.append(caption('Isolated preview: this selects a target only. It cannot start a download or write game files.'))
        try:
            state = service.snapshot()
            for entry in state['registrations']:
                if 'install' not in entry['roles']: continue
                row = Adw.ActionRow(title=entry['label'] + (' · Default' if entry['default'] else ''),
                                    subtitle=entry['path'] + '\n' + (size_text(entry['free']) + ' available' if entry['status'] == 'ready' else entry['reason']))
                row.set_use_markup(False); row.set_subtitle_lines(3)
                control = Gtk.CheckButton(valign=Gtk.Align.CENTER)
                if self.options: control.set_group(self.options[0][1])
                control.set_sensitive(entry['status'] == 'ready')
                control.connect('toggled', lambda c, i=entry['id']: self.choose(i) if c.get_active() else None)
                row.add_suffix(control); row.set_activatable_widget(control); listing.append(row)
                self.options.append((entry, control))
            # Default is a selection hint, never an automatic fallback to another volume.
            default = next((c for row, c in self.options if row['default'] and c.get_sensitive()), None)
            if default: default.set_active(True)
            if not self.options: self.error.set_text('Add install storage in Settings first.')
        except StorageError as error: self.error.set_text(str(error))
        self.set_content(box); self.connect('close-request', self.closed)

    def parent_closed(self, *_):
        self.active = False; self.close()
        return False

    def closed(self, *_):
        self.active = False
        if self.parent_close_id:
            self.parent.disconnect(self.parent_close_id); self.parent_close_id = None
        return False

    def choose(self, install_id):
        if not self.active: return
        self.install_id = install_id; self.confirm.set_sensitive(False); self.last_quote = None
        while self.budgets.get_first_child(): self.budgets.remove(self.budgets.get_first_child())
        try:
            quote = self.service.quote(install_id, self.plan); self.last_quote = quote
            for volume in quote.volumes:
                roles = 'Cache + installation · shared filesystem' if len(volume.roles) == 2 else 'Download cache' if volume.roles[0] == 'cache' else 'Installation'
                self.budgets.append(caption(roles + ' — ' + volume.label, 'heading'))
                detail = f'{size_text(volume.required)} needed · {size_text(volume.free)} currently available\n{size_text(volume.other)} reserved by other jobs'
                if volume.floor: detail += f' · {size_text(volume.floor)} extra minimum free space'
                self.budgets.append(caption(detail))
            self.error.remove_css_class('warning'); self.error.remove_css_class('success')
            self.error.add_css_class('success' if quote.fits is True else 'warning')
            self.error.set_text('Inspect the archive and expanded size before downloading.' if quote.fits is None else
                                'There is not enough space on both selected drives.' if not quote.fits else 'Both storage budgets fit at this check. Space will be checked again before starting.')
            self.confirm.set_sensitive(quote.fits is True)
        except StorageError as error:
            self.error.remove_css_class('success'); self.error.add_css_class('warning'); self.error.set_text(str(error))

    def commit(self):
        if not self.active or not self.install_id: return
        self.choose(self.install_id)  # Refresh stale free-space observations before selection.
        if self.last_quote is None or self.last_quote.fits is not True: return
        self.active = False; self.selected_callback(self.install_id, self.last_quote); self.close()
