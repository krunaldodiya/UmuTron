"""Settings page for API-configured download sources."""
from gi.repository import Adw, GLib, Gtk

from .download_service import source_registry


class SourcesPage(Adw.PreferencesPage):
    def __init__(self, library, window=None):
        super().__init__(title='Sources', icon_name='network-server-symbolic')
        self.library = library
        self.window = window
        self._rows = []
        self._request_generation = 0
        self.group = Adw.PreferencesGroup(
            title='Download sources',
            description='Sources are loaded from the configured UmuTron API. Disabled sources are still checked but hidden from the picker.',
        )
        self.add(self.group)
        self._set_status('Loading active sources…')
        self.load_sources()

    def _base_url(self):
        catalog = getattr(self.window, 'catalog', None)
        provider = getattr(catalog, 'provider', None)
        return getattr(provider, 'base', None)

    def _clear_group(self):
        for row in self._rows:
            self.group.remove(row)
        self._rows.clear()

    def _set_status(self, title, retry=False):
        self._clear_group()
        row = Adw.ActionRow(title=title)
        if retry:
            button = Gtk.Button(label='Refresh', valign=Gtk.Align.CENTER)
            button.connect('clicked', lambda *_: self.load_sources())
            row.add_suffix(button)
            row.set_activatable_widget(button)
        self.group.add(row)
        self._rows.append(row)

    def load_sources(self):
        self._request_generation += 1
        generation = self._request_generation
        pool = getattr(self.window, 'catalog_pool', None)
        if pool is None:
            self._set_status('Source API is not available.', retry=True)
            return
        self._set_status('Loading active sources…')
        try:
            future = pool.submit_source(lambda: source_registry.load_sources(self._base_url()))
        except (AttributeError, RuntimeError):
            self._set_status('Could not load active sources.', retry=True)
            return
        future.add_done_callback(
            lambda completed: GLib.idle_add(self._loaded, completed, generation))

    def _loaded(self, future, generation):
        if generation != self._request_generation or self.get_root() is None:
            return False
        try:
            sources = future.result()
        except Exception:
            self._set_status('Could not load active sources.', retry=True)
            return False
        self._clear_group()
        if not sources:
            self._set_status('No active sources are configured in the API.', retry=True)
            return False
        self.library.data.setdefault('settings', {})
        source_registry.apply_disabled_sources(
            self.library.data['settings'].get('disabled_sources', []))
        for source in sources:
            row = Adw.ActionRow(title=source.name, subtitle='Configured by the download API')
            row.set_use_markup(False)
            switch = Gtk.Switch(valign=Gtk.Align.CENTER)
            switch.set_active(source_registry.is_enabled(source.id))

            def on_toggled(control, _, source_id=source.id):
                enabled = control.get_active()
                source_registry.set_enabled(source_id, enabled)
                disabled = set(self.library.data.get('settings', {}).get('disabled_sources', []))
                if enabled:
                    disabled.discard(source_id)
                else:
                    disabled.add(source_id)
                self.library.data.setdefault('settings', {})['disabled_sources'] = sorted(disabled)
                try:
                    self.library._write()
                except (OSError, ValueError):
                    pass

            switch.connect('notify::active', on_toggled)
            row.add_suffix(switch)
            row.set_activatable_widget(switch)
            self.group.add(row)
            self._rows.append(row)
        return False
