"""End-to-end verification of UmuTron connected to the live FastAPI backend."""
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from headless import ensure_headless
    ensure_headless()
except ImportError:
    pass
os.environ.setdefault('GSK_RENDERER', 'broadway' if os.environ.get('GDK_BACKEND') == 'broadway' else 'cairo')
os.environ.setdefault('GSETTINGS_BACKEND', 'memory')
os.environ['APP_BASE_URL'] = 'http://127.0.0.1:8000'
os.environ['UMUTRON_ALLOW_LOOPBACK_HTTP'] = '1'

from unittest.mock import patch
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from umutron.app import Application, Window
from umutron.demo import prepare_demo
from umutron.server_manager import ServerManager


def pump_until(condition, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError('Native UI condition timed out')


def settle(milliseconds=300):
    ready = [False]
    GLib.timeout_add(milliseconds, lambda: (ready.__setitem__(0, True), False)[-1])
    pump_until(lambda: ready[0])


def widgets(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from widgets(child)
        child = child.get_next_sibling()


def buttons(widget):
    return [i for i in widgets(widget) if isinstance(i, Gtk.Button)]


def capture(target, filename):
    settle(400)
    target.queue_draw()
    settle(200)
    paintable = Gtk.WidgetPaintable.new(target)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, target.get_width(), target.get_height())
    node = snapshot.to_node()
    if node is None:
        raise RuntimeError(f"Could not snapshot {target}")
    texture = target.get_renderer().render_texture(node, None)
    out_dir = Path(__file__).resolve().parents[2] / 'demo-artifacts'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = str(out_dir / filename)
    texture.save_to_png(out_path)
    print(f"Captured: {out_path}")


def main():
    print("Testing ServerManager directly against http://127.0.0.1:8000...")
    manager = ServerManager(api_url='http://127.0.0.1:8000')
    healthy = manager.health()
    print(f"Server health check: {healthy}")
    assert healthy, "FastAPI server must be healthy"

    repo = manager.find_repo()
    print(f"Found server repo: {repo}")
    assert repo is not None, "Server repo must be detected"

    status = manager.status()
    print(f"ServerStatus: healthy={status.healthy}, docker={status.docker_available}, repo={status.repo_installed}")
    assert status.healthy and status.docker_available and status.repo_installed

    with tempfile.TemporaryDirectory(prefix='umutron-fastapi-live-') as temp:
        os.environ['XDG_CACHE_HOME'] = temp
        library = prepare_demo(seed=True)
        app = Application(demo=False)
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        app.register(None)

        print("Testing Application startup gate and health check...")
        app.server_manager = manager
        # Simulate activation
        app.activate_window()
        assert app._startup_state in ('checking', 'ready')
        # Pump until ready
        pump_until(lambda: app._startup_state == 'ready', timeout=5)
        print("Application transitioned to 'ready'!")

        window = getattr(app, 'window', None)
        assert window is not None and isinstance(window, Window), "Main Window must be opened"
        settle(500)

        # 1. Store view
        print("Navigating to Store...")
        window.show_store()
        settle(1000)

        def get_items():
            return window.routes['store'].get('result', {}).get('items', [])

        def is_live():
            res = window.routes['store'].get('result')
            return bool(res and not res.get('cached') and len(res.get('items', [])) > 0)

        print("Waiting for live IGDB store items...")
        pump_until(is_live, timeout=12)
        items = get_items()
        print(f"Store loaded {len(items)} live games from IGDB:")
        for it in items[:5]:
            print(f"  - {it['name']} (ID: {it['id']}, type: {it.get('game_type')})")
        assert len(items) > 0, "Store must load items from FastAPI"
        capture(window, "umutron-store-fastapi.png")

        # 2. Store search
        print("Testing Store search for 'Witcher'...")
        window.collection_search.set_text("Witcher")
        window.collection_search_changed()
        settle(1000)
        pump_until(lambda: is_live() and any("Witcher" in i['name'] for i in get_items()), timeout=12)
        search_items = get_items()
        print(f"Search returned {len(search_items)} games: {[i['name'] for i in search_items[:4]]}")
        capture(window, "umutron-store-search-fastapi.png")

        # 3. Game detail: verify outside button is gone and gear menu has "Search links"
        witcher_item = next(i for i in search_items if i['name'] == 'The Witcher 3: Wild Hunt')
        print(f"Opening detail for: {witcher_item['name']}...")
        window.open_catalog_item(witcher_item)
        print(f"Detail primary button label: {window.detail_primary.get_label()}")
        assert window.detail_primary.get_label() == 'Restore'
        assert hasattr(window, 'add_installer_btn') and window.add_installer_btn.get_visible()
        print("Verified '+' installer button exists in desktop header and primary action is labeled 'Restore'!")
        assert not window.detail_source_row.get_visible(), "Outside source/refresh row must not be visible"
        capture(window, "umutron-detail-clean.png")
        window.detail_gear.popup()
        settle(500)
        capture(window, "umutron-detail-dropdown-search-links.png")
        window.detail_gear.popdown()
        settle(300)

        # Click "Search links" from Game Detail -> opens SourcesLinksDialog on Links tab with clean game title
        print(f"Redirecting from Game Detail using title: {witcher_item['name']}...")
        window.open_detail_links()
        settle(1000)
        sources_links_dlg = next(w for w in Gtk.Window.get_toplevels() if w.get_title() == 'Download Sources & Links' and w.get_visible())
        assert sources_links_dlg.links_page.search_entry.get_text() == witcher_item['name']
        print("Waiting for links search to return results for game title...")
        pump_until(lambda: hasattr(sources_links_dlg.links_page, 'results_notebook') and sources_links_dlg.links_page.results_notebook.get_n_pages() > 0, timeout=15)
        nb = sources_links_dlg.links_page.results_notebook
        provider_tabs = [nb.get_tab_label_text(nb.get_nth_page(idx)) for idx in range(nb.get_n_pages())]
        print(f"Links search returned {nb.get_n_pages()} provider tabs: {provider_tabs}!")
        capture(sources_links_dlg, "umutron-links-search.png")

        # Test smart ID resolution in Links tab: Steam App ID 292030
        print("Testing smart resolution for Steam App ID 292030 in Links tab...")
        delattr(sources_links_dlg.links_page, 'results_notebook')
        sources_links_dlg.links_page.set_search_query('292030')
        sources_links_dlg.links_page.start_search()
        settle(1000)
        pump_until(lambda: hasattr(sources_links_dlg.links_page, 'results_notebook') and sources_links_dlg.links_page.results_notebook.get_n_pages() > 0, timeout=15)
        print(f"Steam ID 292030 resolved and returned {sources_links_dlg.links_page.results_notebook.get_n_pages()} provider tabs!")

        # Test smart ID resolution in Links tab: IGDB ID 1942
        print("Testing smart resolution for IGDB ID 1942 in Links tab...")
        delattr(sources_links_dlg.links_page, 'results_notebook')
        sources_links_dlg.links_page.set_search_query('1942')
        sources_links_dlg.links_page.start_search()
        settle(1000)
        pump_until(lambda: hasattr(sources_links_dlg.links_page, 'results_notebook') and sources_links_dlg.links_page.results_notebook.get_n_pages() > 0, timeout=15)
        print(f"IGDB ID 1942 resolved and returned {sources_links_dlg.links_page.results_notebook.get_n_pages()} provider tabs!")
        sources_links_dlg.close()
        settle(500)

        # 4. Top header icon opens Sources & Links modal (Sources tab with 24 sources)
        print("Clicking top header sources_links_btn...")
        window.sources_links_btn.emit('clicked')
        settle(1000)
        sources_dlg = next(w for w in Gtk.Window.get_toplevels() if w.get_title() == 'Download Sources & Links' and w.get_visible())
        print("Waiting for all 24 sources to load...")
        pump_until(lambda: len(sources_dlg.sources_page._rows) == 24, timeout=10)
        print(f"Loaded all {len(sources_dlg.sources_page._rows)} sources successfully!")
        capture(sources_dlg, "umutron-sources-modal.png")
        sources_dlg.close()
        settle(500)
        # 5. Settings dialog (Sources tab removed)
        print("Testing Settings dialog...")
        window.open_settings(section='server')
        settle(1000)
        settings_dialog = window.settings_dialog
        assert settings_dialog is not None and settings_dialog.get_visible(), "Settings dialog must be visible"
        assert not hasattr(window, 'sources_settings_page') or window.sources_settings_page is None, "Sources tab must be removed from Settings"
        capture(settings_dialog, "umutron-settings-no-sources.png")
        settings_dialog.close()
        settle(500)
        settle(200)
        window.destroy()
        settle(200)
        if hasattr(app, '_startup_pool') and app._startup_pool:
            app._startup_pool.shutdown(wait=True)
        if hasattr(window, 'pool') and window.pool:
            window.pool.shutdown(wait=True)
        if hasattr(window, 'catalog_pool') and window.catalog_pool:
            window.catalog_pool.shutdown(wait=True)

    print("ALL FASTAPI LIVE CHECKS PASSED SUCCESSFULLY!")


if __name__ == '__main__':
    main()
