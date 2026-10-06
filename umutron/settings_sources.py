"""Settings page for enabling/disabling download sources."""
from gi.repository import Adw, Gtk

from .download_service import source_registry

class SourcesPage(Adw.PreferencesPage):
    def __init__(self, library, window=None):
        super().__init__(title='Sources', icon_name='network-server-symbolic')
        self.library = library
        self.window = window
        self.build_ui()

    def build_ui(self):
        group = Adw.PreferencesGroup(
            title='Download Providers',
            description='Enable or disable download sources used for discovering, downloading, and installing games.'
        )
        self.add(group)

        source_registry.apply_disabled_sources(self.library.data.get('settings', {}).get('disabled_sources', []))

        for provider in source_registry.providers(only_enabled=False):
            desc = {
                'fitgirl': 'High compression installer repacks · BitTorrent',
                'byxatab': 'Pre-installed loose game folders &amp; repacks · Direct-to-play BitTorrent',
                'dodi': 'Fast installation repacks &amp; updates · BitTorrent',
                'ankergames': 'Direct pre-installed downloads &amp; repacks'
            }.get(provider.id, f'{provider.name} catalog source')

            row = Adw.ActionRow(title=provider.name, subtitle=desc)
            row.set_use_markup(False)
            switch = Gtk.Switch(valign=Gtk.Align.CENTER)
            switch.set_active(source_registry.is_enabled(provider.id))

            def on_toggled(sw, _, pid=provider.id):
                is_on = sw.get_active()
                source_registry.set_enabled(pid, is_on)
                current_disabled = set(self.library.data.get('settings', {}).get('disabled_sources', []))
                if is_on:
                    current_disabled.discard(pid)
                else:
                    current_disabled.add(pid)
                self.library.data.setdefault('settings', {})['disabled_sources'] = list(current_disabled)
                try:
                    self.library._write()
                except (OSError, ValueError):
                    pass

            switch.connect('notify::active', on_toggled)
            row.add_suffix(switch)
            row.set_activatable_widget(switch)
            group.add(row)
