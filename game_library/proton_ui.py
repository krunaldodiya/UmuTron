"""GE/UMU Proton browsing and ordinary per-game runner selection."""
from pathlib import Path
from gi.repository import Adw, GLib, Gtk
from .proton_manager import BUSY, REPOS, runner_label
from .runner_selection import DOWNLOAD_FAMILIES, INHERIT, parse_release, release_selector


def text(value, css=None):
    widget = Gtk.Label(label=value, xalign=0, wrap=True)
    if css:
        widget.add_css_class(css)
    return widget


def box(vertical=True, spacing=10):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=spacing)


def action(title, callback):
    control = Gtk.Button(label=title, valign=Gtk.Align.CENTER)
    control.connect('clicked', lambda _: callback())
    return control


def choice_label(value):
    if value == INHERIT:
        return 'Use default'
    parsed = parse_release(value)
    return parsed[1] if parsed else runner_label(value)


def family_of(path):
    name = (Path(path).name + ' ' + runner_label(path)).lower()
    if 'ge-proton' in name or 'proton-ge' in name:
        return 'GE-Proton'
    if 'umu-proton' in name:
        return 'UMU-Proton'
    return 'Proton'


def cached_all(manager, family):
    items = {}
    for page in range(1, 101):
        if not (manager.root / f'releases-{family}-{page}.json').exists():
            break
        for release in manager.cached(family, page):
            items[release_selector(release)] = release
    return list(items.values())


class ProtonPanel(Gtk.Box):
    def __init__(self, window, dialog):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.window, self.dialog, self.manager = window, dialog, window.proton_manager
        self.alive = True
        self.items = {family: {} for family in REPOS}
        self.pages = {family: 1 for family in REPOS}
        self.loading = set()
        self.retry_pages = {family: 1 for family in REPOS}
        self.more = {family: False for family in REPOS}
        self.messages = {family: 'Loading official releases…' for family in REPOS}
        self.controls = []
        self.default = text('', 'heading')
        self.append(self.default)
        self.append(text('Used by every game unless its Setup selects another version. Missing downloadable versions are verified before Play or installation.', 'dim-label'))
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.NONE, vhomogeneous=False)
        switcher = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.CENTER)
        self.append(switcher)
        self.append(self.stack)
        self.rows, self.statuses, self.retry, self.scrolls = {}, {}, {}, {}
        for family in DOWNLOAD_FAMILIES:
            page = box()
            page.append(text('Official ' + family + ' releases · ' + self.manager.arch, 'title-3'))
            status = text('', 'dim-label')
            page.append(status)
            self.statuses[family] = status
            retry = action('Retry connection', lambda f=family: self.load(f, self.retry_pages[f]))
            retry.set_halign(Gtk.Align.START)
            retry.set_visible(False)
            page.append(retry)
            self.retry[family] = retry
            rows = box()
            scroll = Gtk.ScrolledWindow(min_content_height=320, max_content_height=440, propagate_natural_height=True)
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll.set_child(rows)
            page.append(scroll)
            self.rows[family], self.scrolls[family] = rows, scroll
            scroll.connect('edge-reached', lambda _, edge, f=family: self.next_page(f) if edge == Gtk.PositionType.BOTTOM else None)
            self.stack.add_titled(page, family, family)
            if family in REPOS:
                for release in cached_all(self.manager, family):
                    self.items[family][release_selector(release)] = release
        self.stack.set_visible_child_name('GE-Proton')
        self.stack.connect('notify::visible-child-name', lambda *_: self.maybe_load_visible())
        dialog.connect('unrealize', lambda *_: setattr(self, 'alive', False))
        self.render()
        dialog.connect('map', self.mapped)

    def mapped(self, *_):
        if getattr(self, 'started', False):
            return
        self.started = True
        GLib.timeout_add(250, self.update)
        if not self.window.demo:
            for family in REPOS:
                self.load(family, 1)
        else:
            for family in REPOS:
                self.messages[family] = 'Demo catalog · downloads disabled'
            self.render()

    def maybe_load_visible(self):
        family = self.stack.get_visible_child_name()
        if family in REPOS and not self.window.demo and not self.items[family] and family not in self.loading:
            self.load(family, 1)

    def next_page(self, family):
        if family in REPOS and self.more[family] and family not in self.loading:
            self.load(family, self.pages[family] + 1)

    def load(self, family, page):
        if family in self.loading or not self.alive:
            return
        self.loading.add(family)
        self.retry_pages[family] = page
        self.retry[family].set_visible(False)
        self.messages[family] = 'Updating catalog…' if self.items[family] else 'Loading official releases…'
        self.statuses[family].set_text(self.messages[family])
        future = self.window.pool.submit(self.manager.releases, family, page, True)
        def finish():
            if not self.alive:
                return False
            self.loading.discard(family)
            try:
                releases = future.result()
                self.pages[family] = page
                self.more[family] = self.manager.has_more(family, page)
                fresh = {release_selector(release): release for release in releases}
                if page == 1:
                    self.items[family] = {**fresh, **{k: v for k, v in self.items[family].items() if k not in fresh}}
                else:
                    self.items[family].update(fresh)
                self.messages[family] = ('Scroll for older versions' if self.more[family] else 'All available versions loaded') if self.items[family] else 'No verified releases for this architecture.'
            except Exception as error:
                self.messages[family] = ('Showing cached versions. ' if self.items[family] else '') + 'Could not update catalog: ' + str(error)[:180]
                self.retry[family].set_visible(True)
            self.render()
            return False
        future.add_done_callback(lambda _: GLib.idle_add(finish))

    def error(self, error):
        dialog = Adw.MessageDialog.new(self.dialog, 'Could not complete this action', str(error)[:2000])
        dialog.add_response('ok', 'OK')
        dialog.present()

    def set_default(self, value):
        try:
            self.window.library.set_default_proton(value)
            self.render()
        except Exception as error:
            self.error(error)

    def remove(self, path):
        try:
            refs = self.manager.references(path)
            if refs:
                raise ValueError('Choose another Proton version for: ' + ', '.join(refs) + '. Then retry uninstalling.')
        except Exception as error:
            self.error(error)
            return
        dialog = Adw.MessageDialog.new(self.dialog, 'Uninstall ' + Path(path).name + '?', 'Remove this UmuTron-managed runner. Game files, prefixes and saves are kept. It can be downloaded again later.')
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('remove', 'Uninstall')
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        dialog.set_response_appearance('remove', Adw.ResponseAppearance.DESTRUCTIVE)
        def response(_, value):
            if value == 'remove':
                self.window.async_job('Uninstalling Proton…', lambda: self.manager.uninstall(path), lambda _: self.render() if self.alive else None)
        dialog.connect('response', response)
        dialog.present()

    def render(self):
        selected = self.window.library.data['settings'].get('default_proton') or 'UMU-Latest'
        self.default.set_text('App default · ' + choice_label(selected))
        focused = self.dialog.get_focus()
        focus_key = next(((c['value'], key) for c in self.controls for key in ('default', 'primary', 'cancel') if c[key] is focused), None)
        scroll_values = {family: scroll.get_vadjustment().get_value() for family, scroll in self.scrolls.items()}
        self.controls.clear()
        installed = self.manager.installed()
        for family in DOWNLOAD_FAMILIES:
            rows = self.rows[family]
            while child := rows.get_first_child():
                rows.remove(child)
            covered = set()
            releases = self.items.get(family, {})
            pending = []
            for value, release in releases.items():
                status = self.manager.status(release)
                path = status.get('path', '')
                if path:
                    covered.add(str(Path(path).resolve()))
                if status['state']=='Installed':
                    self.add_row(rows, release['version'], value, selected, release)
                else:
                    pending.append((value,release))
            local = [path for path in installed if family_of(path) == family and str(Path(path).resolve()) not in covered]
            self.statuses[family].set_text(self.messages[family])
            for path in local:
                self.add_row(rows, runner_label(path).removesuffix(' — installed'), path, selected)
            for value, release in pending:
                self.add_row(rows, release['version'], value, selected, release)
        self.update_controls()
        if focus_key:
            match = next((c for c in self.controls if c['value'] == focus_key[0]), None)
            if match and match[focus_key[1]].get_sensitive():
                match[focus_key[1]].grab_focus()
        for family, value in scroll_values.items():
            self.scrolls[family].get_vadjustment().set_value(value)

    def add_row(self, rows, title, value, selected, release=None):
        card = box()
        card.add_css_class('card')
        for edge in ('top', 'bottom', 'start', 'end'):
            getattr(card, 'set_margin_' + edge)(2)
        inner = box()
        for edge in ('top', 'bottom', 'start', 'end'):
            getattr(inner, 'set_margin_' + edge)(12)
        card.append(inner)
        if release:
            origin = 'UmuTron download'
        elif Path(value).absolute().parent == self.manager.umu_tools.absolute():
            origin = 'UMU-managed copy'
        else:
            origin = 'Local copy'
        heading = text(title + ' · ' + origin, 'heading')
        inner.append(heading)
        status = text('', 'dim-label')
        inner.append(status)
        row = box(False)
        inner.append(row)
        default = action('Set as default', lambda: self.set_default(value))
        row.append(default)
        primary = action('Install', lambda: None)
        row.append(primary)
        cancel = action('Cancel', lambda: self.manager.cancel(release))
        row.append(cancel)
        control = dict(card=card, heading=heading, status=status, default=default, primary=primary, cancel=cancel, value=value, release=release)
        primary.connect('clicked', lambda _: self.primary(control))
        self.controls.append(control)
        rows.append(card)

    def primary(self, control):
        release = control['release']
        path = self.manager.status(release).get('path') if release else control['value']
        try:
            if path and self.manager.managed(path):
                self.remove(path)
            elif release and not path:
                self.manager.install(release)
                self.update_controls()
        except Exception as error:
            self.error(error)

    def update_controls(self):
        selected = self.window.library.data['settings'].get('default_proton') or 'UMU-Latest'
        for control in self.controls:
            release, value = control['release'], control['value']
            status = self.manager.status(release) if release else {'state': 'Installed', 'path': value, 'error': ''}
            phase, path = status['state'], status.get('path', '')
            active = phase in BUSY
            same = selected == value or bool(release and selected == release_selector(release))
            if path and Path(selected).is_absolute():
                same = same or Path(selected).resolve() == Path(path).resolve()
            control['default'].set_label('Default' if same else 'Set as default')
            control['default'].set_sensitive(not same and not active)
            managed = bool(path and self.manager.managed(path))
            detail = phase + (' · Default' if same else '')
            if active and phase == 'Downloading':
                detail += f" · {int(status.get('progress', 0) * 100)}%"
            if path and not release:
                detail += ' · ' + self.manager.local_origin(path)
            if status.get('error'):
                detail += ' · ' + status['error']
            control['status'].set_text(detail)
            control['primary'].set_label('Uninstall' if managed else 'Retry' if phase in ('Failed', 'Cancelled') else 'Install')
            control['primary'].set_visible(managed or bool(release and not path))
            control['primary'].set_sensitive(not active and not self.window.demo)
            control['cancel'].set_visible(active)

    def update(self):
        if not self.alive or not self.dialog.get_visible():
            return False
        self.update_controls()
        return True


def build_game_selector(window, content, dialog):
    manager = window.proton_manager
    backing = window.launch_fields['proton']
    row = box()
    row.append(text('Proton version', 'heading'))
    select = Gtk.DropDown(hexpand=True, enable_search=True)
    window.proton_choice = select
    row.append(select)
    status = text('Missing versions download and verify when you choose Play or Launch Installer.', 'dim-label')
    row.append(status)
    content.append(row)
    releases = {release_selector(r): r for f in REPOS for r in cached_all(manager, f)}
    values, synchronizing = [], [False]
    editor_game = window.game
    def live():
        return window.editor is dialog and window.game is editor_game
    def rebuild():
        if not live():
            return
        current = backing.get_text()
        # Legacy blank keeps an installer pin until Use default is explicitly chosen.
        effective = current or editor_game.get('installation', {}).get('proton') or INHERIT
        released_paths = {str(Path(p).resolve()) for value in releases if (p := manager.installed_release(value))}
        local = [p for p in manager.installed() if str(Path(p).resolve()) not in released_paths]
        choices = [INHERIT, *local, *releases]
        if effective not in choices:
            choices.insert(1, effective)
        choices = list(dict.fromkeys(choices))
        synchronizing[0] = True
        values[:] = choices
        labels = ['Use default · ' + choice_label(window.library.data['settings'].get('default_proton') or 'UMU-Latest') if v == INHERIT else choice_label(v) + (' · downloads when needed' if v in releases and not manager.installed_release(v) else '') for v in choices]
        select.set_model(Gtk.StringList.new(labels))
        select.set_selected(choices.index(effective))
        synchronizing[0] = False
    def changed(widget, _):
        if live() and not synchronizing[0] and widget.get_selected() < len(values):
            backing.set_text(values[widget.get_selected()])
    select.connect('notify::selected', changed)
    backing.connect('changed', lambda *_: rebuild())
    rebuild()
    if window.demo:
        return
    def work():
        found, failed = [], False
        for family in REPOS:
            try:
                found.extend(manager.releases(family, refresh=True))
            except Exception:
                failed = True
        return found, failed
    future = window.pool.submit(work)
    def finish():
        if not live():
            return False
        found, failed = future.result()
        fresh = {release_selector(r): r for r in found}
        ordered = {**fresh, **{k: v for k, v in releases.items() if k not in fresh}}
        releases.clear();releases.update(ordered)
        rebuild()
        if failed:
            status.set_text('Showing saved choices. Catalog update unavailable; retry from Proton Manager. Missing verified versions download when you launch.')
        return False
    future.add_done_callback(lambda _: GLib.idle_add(finish))
