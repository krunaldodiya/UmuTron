"""Render native GTK fixtures on an isolated Broadway display, never the desktop.

Run gtk4-broadwayd bound to loopback, open it in a browser, then use
GDK_BACKEND=broadway BROADWAY_DISPLAY=:N python3 tools/fullscreen_preview.py.
Optional source library copies only public metadata/artwork into a temporary demo.
All execution remains disabled; no saved executable, prefix or launch settings load.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if os.environ.get('GDK_BACKEND') != 'broadway':
    raise SystemExit('Use an isolated Broadway display; this fixture never opens on the desktop.')
os.environ.setdefault('GSK_RENDERER', 'broadway')
os.environ.setdefault('GSETTINGS_BACKEND', 'memory')
from game_library.app import Application, Window
from game_library.demo import prepare_demo
from gi.repository import Adw, Gio, GLib, Gtk


def settle(ms=400):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        time.sleep(.01)


def capture(window, path):
    # Remap this isolated fixture to request a fresh frame even when the browser
    # throttles background frame acknowledgements. This is not a desktop capture.
    window.set_visible(False)
    window.present()
    settle(800)
    # Broadway may acknowledge remapping before delivering another frame tick.
    # Apply the native responsive layout against the allocated viewport before
    # exporting its widget tree, rather than capturing the transient zero size.
    window.console_size = None
    window.resize_console(window, None)
    settle(300)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        paintable = Gtk.WidgetPaintable.new(window)
        snapshot = Gtk.Snapshot()
        paintable.snapshot(snapshot, window.get_width(), window.get_height())
        node = snapshot.to_node()
        if node is not None and window.get_renderer():
            window.get_renderer().render_texture(node, None).save_to_png(str(path))
            return
        settle(50)
    raise RuntimeError('No native frame available; connect the Broadway browser first.')



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-library', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='umutron-preview-') as temp:
        os.environ['XDG_CACHE_HOME'] = temp
        library = prepare_demo(seed=not args.source_library)
        if args.source_library:
            source = json.loads(args.source_library.read_text())
            for original in source['games']:
                game = library.new_game()
                for key in ('title', 'description', 'release_date', 'genres', 'developers', 'publishers'):
                    game[key] = original.get(key, '')
                for kind, name in original.get('artwork', {}).items():
                    art = args.source_library.parent / 'artwork' / name
                    if art.is_file():
                        game['artwork'][kind] = library.add_image(art.read_bytes())
                executable = Path(temp) / (game['id'] + '.exe')
                executable.write_text('Inert test fixture. Never execute.')
                game['executable'] = str(executable)
                library.save(game)
        app = Application(demo=True)
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        app.register(None)
        with patch('game_library.app.Controller') as controller:
            controller.return_value.name = ''
            controller.return_value.error = ''
            window = Window(app, library, demo=True)
        app.window = window
        for child in window.layout:
            if isinstance(child, Adw.Banner):
                child.set_title('ISOLATED NATIVE PREVIEW · temporary library · Play is disabled')
        window.present()
        window.set_tv_mode(True)
        window.unfullscreen()
        settle()
        selected = next((g for g in library.games() if g['title'] == 'God of War'), library.games()[0])
        for width, height in ((1920, 1080), (1280, 720), (1024, 600)):
            window.set_visible(False)
            window.unrealize()
            window.set_default_size(width, height)
            window.present()
            window.tv_section = 'games'
            window.tv_selected_id = selected['id']
            window.show_library()
            settle(700)
            window.tv_page.get_vadjustment().set_value(0)
            capture(window, args.output / f'home-{width}.png')
            print('home', width, window.get_width(), window.get_height(), 'rail', window.tv_scroll.get_hadjustment().get_upper(), window.tv_scroll.get_hadjustment().get_page_size(), 'tile', window.tv_tiles[0][1].get_width(), window.tv_tiles[0][1].get_height(), flush=True)
            window.show_game(selected)
            capture(window, args.output / f'detail-{width}.png')
            window.set_tv_section('library')
            capture(window, args.output / f'library-{width}.png')
        missing = deepcopy(selected)
        missing['artwork'] = {}
        missing['description'] = ''
        window.show_game(missing)
        capture(window, args.output / 'detail-missing-art.png')
        window.set_tv_mode(False)
        capture(window, args.output / 'desktop-detail.png')
        window.controller.close()
        window.destroy()
        window.pool.shutdown(wait=True)
    print('Saved native GTK test renders to', args.output)


if __name__ == '__main__':
    main()
