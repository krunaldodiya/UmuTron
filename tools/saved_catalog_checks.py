"""Saved Store detail enrichment; inert private native fixture in both modes."""
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import sys
from threading import Event
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
assert os.environ.get('GDK_BACKEND') == 'broadway'
assert Path(os.environ['HOME']).is_relative_to('/tmp')
def guard(event, args):
    if event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn'):
        raise RuntimeError('Execution disabled')
    if event in ('socket.connect', 'socket.bind') and getattr(args[0], 'family', None) != socket.AF_UNIX:
        raise RuntimeError('Network disabled')
sys.addaudithook(guard)

from fullscreen_preview import settle
from navigation_fixture import ready
from game_library.app import Application, Window
from game_library.demo import prepare_demo
from game_library.catalog import validate_item
from gi.repository import Gio, Gtk


class Provider:
    def __init__(self): self.calls = []
    def genres(self): return []
    def browse(self, *_):
        return {'page': 1, 'has_next': False, 'items': [
            {'id': i, 'name': 'Provider title', 'game_type': 'Bundle', 'platforms': []}
            for i in (10, 11, 12)]}
    def detail(self, identity):
        self.calls.append(identity)
        return {**next(i for i in self.browse()['items'] if i['id'] == identity),
                'summary': 'Remote description must not replace local edits.',
                'platforms': [{'id': 6, 'name': 'PC (Microsoft Windows)'}],
                'relationships': {'bundles': [{'id': 20, 'name': 'Containing bundle'}],
                                  'parent_game': {'id': 21, 'name': 'Related game'},
                                  'expanded_games': [{'id': 22, 'name': 'Expanded version'}],
                                  'version_parent': {'id': 23, 'name': 'Edition parent'},
                                  'bundle_contents': {'items': [{'id': 11 if identity != 11 else 12,
                                                                'name': 'Reported component'}],
                                                      'complete': True}}}


def widgets(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from widgets(child)
        child = child.get_next_sibling()


checks = []
def check(value, name):
    assert value, name
    checks.append(name)
    print('PASS ' + name, flush=True)


def info(window):
    window.show_game_info(window.game)
    settle(50)
    return next(d for d in Gtk.Window.get_toplevels() if d.get_visible() and d.get_title() == 'Game Info')


def references(dialog):
    return [c.catalog_reference_id for c in widgets(dialog) if hasattr(c, 'catalog_reference_id')]


library = prepare_demo(True)
local = library.games()[0]
local.update(title='My edited title', description='My edited description',
             metadata_source={'provider': 'igdb', 'id': 10}, metadata_app_id=620,
             working_dir='/inert/preserved', arguments='--local-setting')
library.save(local)
provider = Provider()
app = Application(demo=True)
app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
app.register(None)
with patch('game_library.app.Controller') as controller:
    controller.return_value.name = controller.return_value.error = ''
    w = Window(app, library, demo=True, catalog_provider=provider)
app.window = w
w.launcher.start = Mock(side_effect=AssertionError('No execution'))
w.installations.start = Mock(side_effect=AssertionError('No installer'))
w.proton_manager.releases = lambda *a, **k: []
w.present()
settle(100)
observations = []
try:
    # Collect both baseline failures before asserting, so one failed mode cannot
    # conceal the other. Start from the actual browse tile, never detail input.
    before = library.path.read_bytes()
    for fullscreen in (False, True):
        w.set_tv_mode(fullscreen); w.unfullscreen(); w.show_store()
        ready(w, lambda: len(w.collection_tiles) == 3 and not w.catalog_futures, 'Store ready')
        provider.calls.clear()
        w.collection_tiles[10].emit('clicked')
        ready(w, lambda: not w.catalog_futures, 'Saved Store detail settles')
        dialog = info(w)
        observations.append({'fullscreen': fullscreen, 'detail_calls': list(provider.calls),
                             'references': references(dialog), 'local_unchanged': w.game == local})
        dialog.close(); settle(40)
    print('SAVED_STORE_OBSERVATIONS ' + json.dumps(observations), flush=True)
    for result in observations:
        mode = str(result['fullscreen'])
        check(result['detail_calls'] == [10], 'Saved Store card requests exact detail in ' + mode)
        check(result['references'] == [11, 20, 22, 21, 23], 'All directed relationships reachable in ' + mode)
        check(result['local_unchanged'] and library.path.read_bytes() == before, 'Saved metadata preserved in ' + mode)

    for fullscreen in (False, True):
        w.set_tv_mode(fullscreen); w.unfullscreen()
        mode = str(fullscreen)
        browse = validate_item(provider.browse()['items'][0])
        started, release = Event(), Event()
        def held(identity):
            started.set()
            assert release.wait(6)
            return validate_item(provider.detail(identity))
        with patch.object(w.catalog, 'detail', held):
            w.open_catalog_item(browse)
            ready(w, started.is_set, 'Saved enrichment held')
            primary = w.detail_primary
            policy = (primary.get_label(), primary.get_sensitive())
            dialog = info(w); focus = dialog.get_focus()
            check(any(isinstance(c, Gtk.Label) and c.get_text() == 'Loading catalog information…'
                      for c in widgets(dialog)), 'Game Info exposes pending enrichment in ' + mode)
            release.set()
            ready(w, lambda: 11 in references(dialog), 'Open Game Info enriched in place')
        check(dialog.get_visible() and dialog.get_focus() is focus,
              'Enrichment preserves current Game Info and focus in ' + mode)
        check(w.detail_primary is primary and (primary.get_label(), primary.get_sensitive()) == policy,
              'Saved primary action remains intact in ' + mode)
        check(w.game == local and w.original == local and library.path.read_bytes() == before,
              'No local metadata or Setup rewrite in ' + mode)
        dialog.close(); settle(40)
        # Hard failure, then old-schema response: local information remains usable.
        with patch.object(w.catalog, 'detail', side_effect=ValueError('Fixture unavailable')):
            w.open_catalog_item(browse)
            ready(w, lambda: not w.catalog_futures, 'Saved failure settles')
        dialog = info(w)
        check(any(isinstance(c, Gtk.Label) and 'Catalog information unavailable' in c.get_text()
                  for c in widgets(dialog)), 'Failure is visible in Game Info in ' + mode)
        check(w.game == local and (w.detail_primary.get_label(), w.detail_primary.get_sensitive()) == policy,
              'Failure retains local action and metadata in ' + mode)
        dialog.close(); settle(40)
        with patch.object(w.catalog, 'detail', return_value=browse):
            w.open_catalog_item(browse)
            ready(w, lambda: not w.catalog_futures, 'Old detail schema settles')
        dialog = info(w)
        check(not references(dialog) and not w.detail_catalog_pending, 'Old schema completes without invented links in ' + mode)
        dialog.close(); settle(40)
        # The normal CatalogService offline snapshot path still enriches safely.
        with patch.object(provider, 'detail', side_effect=ValueError('Offline fixture')):
            w.open_catalog_item(browse)
            ready(w, lambda: not w.catalog_futures, 'Offline saved detail settles')
        dialog = info(w)
        check(w.detail_item['cached'] and 11 in references(dialog), 'Cached enrichment is available offline in ' + mode)
        dialog.close(); settle(40)
        # Closing the modal and navigating Back invalidates held completion.
        started, release, finished = Event(), Event(), Event()
        def stale(identity):
            started.set()
            assert release.wait(6)
            finished.set()
            return validate_item(provider.detail(identity))
        with patch.object(w.catalog, 'detail', stale):
            w.open_catalog_item(browse); ready(w, started.is_set, 'Cancelable saved detail held')
            dialog = info(w); dialog.close(); w.show_library(); release.set()
            ready(w, finished.is_set, 'Canceled work returns'); settle(80)
        check(w.route == 'library' and not dialog.get_visible() and library.path.read_bytes() == before,
              'Closed modal and navigation reject late saved enrichment in ' + mode)
        # An explicit Add followed by reopening its browse card must fetch again.
        added_id = 11 if not fullscreen else 12
        added_browse = validate_item(next(i for i in provider.browse()['items'] if i['id'] == added_id))
        w.open_catalog_item(added_browse)
        ready(w, lambda: not w.catalog_futures, 'Unsaved detail loaded')
        w.detail_action(); ready(w, w.saved_detail, 'Explicit Add saved')
        added = deepcopy(w.game); before = library.path.read_bytes()
        w.show_store(); ready(w, lambda: len(w.collection_tiles) == 3 and not w.catalog_futures, 'Store after Add')
        provider.calls.clear(); w.collection_tiles[added_id].emit('clicked')
        ready(w, lambda: not w.catalog_futures, 'Reopened saved detail loaded')
        dialog = info(w)
        check(provider.calls == [added_id] and references(dialog) and w.game == added,
              'Reopen after Add enriches same saved UUID in ' + mode)
        dialog.close(); settle(40)
        check(library.path.read_bytes() == before, 'Reopen after Add writes no game data in ' + mode)

    # Native Setup remains intact if enrichment finishes during an unsaved edit.
    w.set_tv_mode(False); w.unfullscreen()
    started, release = Event(), Event()
    with patch.object(w.catalog, 'detail', held):
        w.open_catalog_item(browse); ready(w, started.is_set, 'Setup enrichment held')
        w.open_manage(); editor = w.editor; field = w.fields['working_dir']
        field.set_text('/inert/unsaved-edit'); release.set()
        ready(w, lambda: not w.catalog_futures, 'Enrichment during Setup completes')
        check(w.editor is editor and w.fields['working_dir'] is field and field.get_text() == '/inert/unsaved-edit',
              'In-flight enrichment cannot reset unsaved Setup')
        w.cancel_editor()
    check(w.game == local and library.path.read_bytes() == before, 'Setup cancellation preserves saved metadata')
    # A mode rebuild during a held fetch must resume with a fresh generation.
    started, release = Event(), Event()
    with patch.object(w.catalog, 'detail', held):
        w.open_catalog_item(browse); ready(w, started.is_set, 'Mode transition enrichment held')
        check(w.set_tv_mode(True), 'Mode transition remains available during enrichment')
        w.unfullscreen(); release.set()
        ready(w, lambda: not w.catalog_futures and 'relationships' in w.detail_item, 'Mode transition enrichment finishes')
    check(w.tv_mode and w.game == local and library.path.read_bytes() == before,
          'Mode rebuild resumes enrichment without changing local metadata')
    check(not w.launcher.start.called and not w.installations.start.called, 'No game or installer dispatch')
finally:
    for dialog in list(Gtk.Window.get_toplevels()):
        if dialog is not w: dialog.destroy()
    w.exiting = True; w.catalog_cancel()
    w.catalog_pool.shutdown(wait=True, cancel_futures=True); w.pool.shutdown(wait=True, cancel_futures=True)
    w.controller.close(); w.destroy(); app.quit()
print(f'PASS: {len(checks)} saved catalog enrichment assertions; synthetic native fixture only.')
