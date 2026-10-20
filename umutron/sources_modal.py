"""Dedicated modal window for managing download sources and searching game links."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import re
from urllib.request import Request, build_opener, ProxyHandler
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

from .download_service import source_registry
from .sources.model import source_link_kind
from .sources.cache import search_game_releases
from . import metadata


def resolve_id_to_title(query_id: str, base_url: str = 'http://127.0.0.1:8000') -> str | None:
    query_id = query_id.strip()
    if not query_id.isdecimal():
        return None
    app_id = int(query_id)
    # 1. Try Steam store API (e.g. 292030 -> The Witcher 3: Wild Hunt)
    try:
        det = metadata.details(app_id)
        if det and det.get('title'):
            title = det['title'].strip()
            title = re.sub(r'[\u2122\u00ae\u00a9]', '', title)
            title = re.sub(r'\s*[\u2014\-]\s*(Remastered|Game of the Year Edition|Definitive Edition).*$', '', title, flags=re.I)
            if title.strip():
                return title.strip()
    except Exception:
        pass

    # 2. Try IGDB catalog via FastAPI endpoint (e.g. 1942 -> The Witcher 3: Wild Hunt, 1020 -> Grand Theft Auto V)
    try:
        url = f'{base_url.rstrip("/")}/v1/games/{app_id}'
        req = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'UmuTron/id-resolver'})
        with build_opener(ProxyHandler({})).open(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if isinstance(data, dict) and data.get('name'):
                return data['name'].strip()
    except Exception:
        pass
    return None

class SourcesPage(Adw.PreferencesPage):
    """View and toggle all API-configured download sources."""

    def __init__(self, library, window=None):
        super().__init__(title='Sources', icon_name='network-server-symbolic')
        self.library = library
        self.window = window
        self._rows = []
        self._switches = {}
        self._request_generation = 0

        self.group = Adw.PreferencesGroup(
            title='Download sources',
            description='Sources are loaded from the local FastAPI backend. '
                        'Toggle sources on or off to include or exclude them from link searches.',
        )
        self.add(self.group)

        # Header controls
        controls_row = Adw.ActionRow(title='Source controls')
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)
        
        self.enable_all_btn = Gtk.Button(label='Enable all', valign=Gtk.Align.CENTER)
        self.enable_all_btn.connect('clicked', lambda *_: self._set_all_enabled(True))
        btn_box.append(self.enable_all_btn)

        self.disable_all_btn = Gtk.Button(label='Disable all', valign=Gtk.Align.CENTER)
        self.disable_all_btn.connect('clicked', lambda *_: self._set_all_enabled(False))
        btn_box.append(self.disable_all_btn)

        self.refresh_btn = Gtk.Button(icon_name='view-refresh-symbolic', valign=Gtk.Align.CENTER)
        self.refresh_btn.set_tooltip_text('Refresh sources from API')
        self.refresh_btn.connect('clicked', lambda *_: self.load_sources())
        btn_box.append(self.refresh_btn)

        self.sync_cache_btn = Gtk.Button(label='Sync Cache', valign=Gtk.Align.CENTER)
        self.sync_cache_btn.add_css_class('suggested-action')
        self.sync_cache_btn.set_tooltip_text('Trigger background upstream fetch and database cache sync')
        self.sync_cache_btn.connect('clicked', lambda *_: self.trigger_backend_sync())
        btn_box.append(self.sync_cache_btn)

        controls_row.add_suffix(btn_box)
        self.group.add(controls_row)

        self._set_status('Loading configured sources…')
        self.load_sources()

    def _base_url(self):
        catalog = getattr(self.window, 'catalog', None)
        provider = getattr(catalog, 'provider', None)
        base = getattr(provider, 'base', None)
        return base or os.environ.get('APP_BASE_URL') or 'http://127.0.0.1:8000'

    def _clear_group(self):
        for row in self._rows:
            self.group.remove(row)
        self._rows.clear()
        self._switches.clear()

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
        self._set_status('Loading configured sources…')
        base_url = self._base_url()

        def do_load():
            return source_registry.load_sources(base_url)

        if pool is not None:
            try:
                future = pool.submit_source(do_load)
                future.add_done_callback(
                    lambda completed: GLib.idle_add(self._loaded, completed, generation))
                return
            except (AttributeError, RuntimeError):
                pass

        # Fallback thread if catalog pool is unavailable
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(do_load)
        future.add_done_callback(
            lambda completed: GLib.idle_add(self._loaded, completed, generation))

    def _loaded(self, future, generation):
        if generation != self._request_generation:
            return False
        try:
            sources = future.result()
        except Exception as error:
            self._set_status(f'Could not load sources: {error}', retry=True)
            return False
        self._clear_group()
        if not sources:
            self._set_status('No sources are configured in the API.', retry=True)
            return False
        self.library.data.setdefault('settings', {})
        source_registry.apply_disabled_sources(
            self.library.data['settings'].get('disabled_sources', []))
        for source in sorted(sources, key=lambda s: s.name.lower()):
            escaped_name = GLib.markup_escape_text(source.name)
            row = Adw.ActionRow(title=escaped_name, subtitle=f'ID: {source.id}')
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
            self._switches[source.id] = switch
        return False

    def _set_all_enabled(self, enabled: bool):
        for switch in self._switches.values():
            switch.set_active(enabled)

    def trigger_backend_sync(self):
        base_url = self._base_url()
        key = os.environ.get('INTERNAL_API_KEY') or os.environ.get('UMUTRON_API_KEY') or ''
        if not key:
            server = getattr(self.window, 'server', None)
            if server and hasattr(server, 'read_environment'):
                key = server.read_environment().internal_api_key
        if self.window and hasattr(self.window, 'notify'):
            self.window.notify('Triggering source feed fetch & cache sync in background…')
        self.sync_cache_btn.set_sensitive(False)

        def do_sync():
            try:
                url = f"{base_url.rstrip('/')}/api/fetcher/refresh"
                headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
                if key:
                    headers['x-api-key'] = key
                data = json.dumps({'sync': True, 'wait': False}).encode()
                req = Request(url, data=data, headers=headers, method='POST')
                with build_opener(ProxyHandler({})).open(req, timeout=10) as resp:
                    return json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                return {'error': str(e)}

        def on_done(future):
            self.sync_cache_btn.set_sensitive(True)
            res = future.result()
            if 'error' in res:
                if self.window and hasattr(self.window, 'notify'):
                    self.window.notify(f'Source cache sync failed: {res["error"]}')
            else:
                if self.window and hasattr(self.window, 'notify'):
                    self.window.notify('Source cache sync started in background!')
                GLib.idle_add(self.load_sources)

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(do_sync)
        future.add_done_callback(lambda done: GLib.idle_add(on_done, done))


class LinksPage(Adw.PreferencesPage):
    """Search engine for game download links across all enabled sources."""

    def __init__(self, library, window=None):
        super().__init__(title='Links', icon_name='insert-link-symbolic')
        self.library = library
        self.window = window
        self._search_generation = 0
        self._result_rows = []
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='umutron-links-search')

        # Search box group
        search_group = Adw.PreferencesGroup(
            title='Search game links',
            description='Enter a game title, Steam App ID (e.g. 292030), or IGDB ID (e.g. 1942). '
                        'Automatically resolves numeric IDs to game names and searches all enabled download sources.',
        )
        self.add(search_group)

        search_row = Adw.ActionRow(title='Search query')
        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text('Game title, Steam App ID, or IGDB ID (e.g. 292030, 1942, The Witcher 3)…')
        self.search_entry.set_hexpand(True)
        self.search_entry.set_valign(Gtk.Align.CENTER)
        self.search_entry.connect('activate', lambda *_: self.start_search())
        search_row.add_suffix(self.search_entry)

        self.search_btn = Gtk.Button(label='Search', valign=Gtk.Align.CENTER)
        self.search_btn.add_css_class('suggested-action')
        self.search_btn.connect('clicked', lambda *_: self.start_search())
        search_row.add_suffix(self.search_btn)
        search_group.add(search_row)

        # Results group
        self.results_group = Adw.PreferencesGroup(
            title='Available download links',
            description='Download links are provided for manual installation.',
        )
        self.add(self.results_group)
        self._set_results_status('Enter a game title or Steam/IGDB ID to search.')

    def _base_url(self):
        catalog = getattr(self.window, 'catalog', None)
        provider = getattr(catalog, 'provider', None)
        base = getattr(provider, 'base', None)
        return base or os.environ.get('APP_BASE_URL') or 'http://127.0.0.1:8000'

    def set_search_query(self, query: str):
        if hasattr(self, 'search_entry'):
            self.search_entry.set_text(query.strip())

    def _clear_results(self):
        for row in self._result_rows:
            self.results_group.remove(row)
        self._result_rows.clear()

    def _set_results_status(self, title: str, spinning: bool = False):
        self._clear_results()
        row = Adw.ActionRow(title=title)
        if spinning:
            spinner = Gtk.Spinner(spinning=True, valign=Gtk.Align.CENTER)
            row.add_prefix(spinner)
        self.results_group.add(row)
        self._result_rows.append(row)

    def start_search(self):
        raw_query = self.search_entry.get_text().strip()
        if not raw_query:
            self._set_results_status('Enter a game title or Steam/IGDB ID to search.')
            return
        self._search_generation += 1
        gen = self._search_generation
        if raw_query.isdecimal():
            self._set_results_status(f'Resolving ID {raw_query} and searching enabled sources…', spinning=True)
        else:
            self._set_results_status(f'Searching enabled sources for "{raw_query}"…', spinning=True)
        base_url = self._base_url()

        future = self._pool.submit(self._execute_search, base_url, raw_query)
        future.add_done_callback(lambda done: GLib.idle_add(self._search_done, done, gen, raw_query))

    def _execute_search(self, base_url: str, raw_query: str):
        search_title = raw_query
        resolved_title = None
        if raw_query.isdecimal():
            resolved_title = resolve_id_to_title(raw_query, base_url)
            if resolved_title:
                search_title = resolved_title

        queries_to_try = [search_title]
        if resolved_title and raw_query not in queries_to_try:
            queries_to_try.append(raw_query)

        results = []
        seen = set()
        for q in queries_to_try:
            releases = search_game_releases(base_url, q, force_refresh=True)
            for r in releases:
                key = (r.provider_id, r.title, tuple(r.uris))
                if key not in seen:
                    seen.add(key)
                    results.append(r)
        return results, resolved_title

    def _search_done(self, future, gen: int, query: str):
        if gen != self._search_generation:
            return False
        try:
            releases, resolved_title = future.result()
        except Exception as error:
            self._set_results_status(f'Search error: {error}')
            return False
        self._clear_results()
        display_title = f'{resolved_title} (ID: {query})' if resolved_title else query
        if not releases:
            self._set_results_status(
                f'No download links found for "{display_title}". '
                'Verify the title or Steam/IGDB ID, or ensure sources are enabled in the Sources tab.'
            )
            return False
        sources_map = {}
        for release in releases:
            pid = release.provider_id
            pname = release.provider_name or pid
            sources_map.setdefault((pid, pname), []).append(release)

        notebook = Gtk.Notebook()
        notebook.set_scrollable(True)
        notebook.set_hexpand(True)
        notebook.set_vexpand(True)
        notebook.set_focusable(True)
        notebook.add_css_class('source-picker-tabs')

        for (provider_id, provider_name), source_releases in sorted(sources_map.items(), key=lambda item: item[0][1].lower()):
            group = Adw.PreferencesGroup()
            for release in source_releases:
                title = GLib.markup_escape_text(release.title or query)
                size = (release.file_size or 'Unknown size').strip()
                uris = list(release.uris) if release.uris else []
                links_count = len(uris)
                magnet = release.magnet or next((u for u in uris if u.startswith('magnet:')), '')

                expander = Adw.ExpanderRow(
                    title=title,
                    subtitle=f'Download size: {size} · {links_count} links',
                )
                expander.set_use_markup(False)

                if magnet:
                    quick_copy = Gtk.Button(label='Copy Magnet', valign=Gtk.Align.CENTER)
                    quick_copy.add_css_class('suggested-action')
                    quick_copy.connect('clicked', lambda *_, m=magnet: self._copy_link(m, 'magnet link'))
                    expander.add_suffix(quick_copy)

                    quick_open = Gtk.Button(icon_name='external-link-symbolic', valign=Gtk.Align.CENTER)
                    quick_open.set_tooltip_text('Open magnet link in default torrent app')
                    quick_open.connect('clicked', lambda *_, m=magnet: self._open_uri(m))
                    expander.add_suffix(quick_open)
                elif uris:
                    first_uri = uris[0]
                    quick_copy = Gtk.Button(label='Copy Link', valign=Gtk.Align.CENTER)
                    quick_copy.connect('clicked', lambda *_, u=first_uri: self._copy_link(u, 'download link'))
                    expander.add_suffix(quick_copy)

                for idx, uri in enumerate(uris, 1):
                    kind = source_link_kind(uri) or 'Download link'
                    display_uri = uri if len(uri) <= 80 else uri[:77] + '…'
                    sub_row = Adw.ActionRow(title=f'{kind} #{idx}')
                    sub_row.set_use_markup(False)
                    sub_row.set_subtitle(display_uri)

                    copy_btn = Gtk.Button(label='Copy', valign=Gtk.Align.CENTER)
                    copy_btn.connect('clicked', lambda *_, u=uri, k=kind: self._copy_link(u, k))
                    sub_row.add_suffix(copy_btn)

                    open_btn = Gtk.Button(icon_name='external-link-symbolic', valign=Gtk.Align.CENTER)
                    open_btn.set_tooltip_text(f'Open {kind} in default application / browser')
                    open_btn.connect('clicked', lambda *_, u=uri: self._open_uri(u))
                    sub_row.add_suffix(open_btn)

                    expander.add_row(sub_row)

                group.add(expander)

            page = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
            page.set_min_content_height(340)
            page.set_child(group)
            tab_label = Gtk.Label(label=f"{provider_name} ({len(source_releases)})")
            notebook.append_page(page, tab_label)

        self.results_notebook = notebook
        self.results_group.add(notebook)
        self._result_rows.append(notebook)
        return False

    def _copy_link(self, uri: str, kind: str):
        display = Gdk.Display.get_default()
        if display:
            display.get_clipboard().set(uri)
        if self.window and hasattr(self.window, 'notify'):
            self.window.notify(f'Copied {kind} to clipboard.')

    def _open_uri(self, uri: str):
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except Exception as error:
            if self.window and hasattr(self.window, 'notify'):
                self.window.notify(f'Could not open link: {error}')


class SourcesLinksDialog(Adw.PreferencesWindow):
    """Modal dialog combining Download Sources management and Link search."""

    def __init__(self, library, window=None):
        pw = window.get_width() if window and window.get_width() > 0 else 1200
        ph = window.get_height() if window and window.get_height() > 0 else 800
        self.target_w = max(920, pw - 48)
        self.target_h = max(620, ph - 48)
        super().__init__(
            title='Download Sources & Links',
            transient_for=window,
            modal=True,
            default_width=self.target_w,
            default_height=self.target_h,
        )
        self.library = library
        self.window = window

        self.sources_page = SourcesPage(library, window)
        self.add(self.sources_page)

        self.links_page = LinksPage(library, window)
        self.add(self.links_page)
        from .dialogs import expand_clamps
        expand_clamps(self, max_width=max(1200, self.target_w - 64))
    def open_tab(self, tab: str = 'sources', query: str | None = None):
        if tab == 'links':
            self.set_visible_page(self.links_page)
            if query:
                self.links_page.set_search_query(query)
                self.links_page.start_search()
        else:
            self.set_visible_page(self.sources_page)
