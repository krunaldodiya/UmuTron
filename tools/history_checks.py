"""Native recent-play refresh checks using temporary, inert records only."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullscreen_preview import settle
from catalog_fixtures import FixtureCatalog
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library.library import Library
from game_library.play_history import record
from gi.repository import Gio


with tempfile.TemporaryDirectory(prefix='umutron-history-ui-') as temp:
    os.environ['XDG_CACHE_HOME']=temp
    library=prepare_demo(True);games=library.games();before=library.path.read_bytes()
    app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name='';controller.return_value.error=''
        w=Window(app,library,demo=True,catalog_provider=FixtureCatalog())
    app.window=w;w.present();settle(400)
    w.navigation_window=lambda:w
    w.show_home();assert w.tv_games==[]
    record(library.root,games[0]['id'],str(uuid4()),100)
    w.refresh_launch_state();settle()
    assert [g['id'] for g in w.tv_games]==[games[0]['id']]
    selected=w.tv_selected_id  # Home may retain a selected existing setup below the new rail.
    w.tv_open.grab_focus()
    record(library.root,games[1]['id'],str(uuid4()),200)
    w.refresh_launch_state();settle()
    assert [g['id'] for g in w.tv_games]==[games[1]['id'],games[0]['id']]
    assert w.tv_selected_id==selected and w.get_focus() is w.tv_open
    w.navigation_window=lambda:None
    record(library.root,games[2]['id'],str(uuid4()),300)
    w.refresh_launch_state();assert len(w.tv_games)==2
    w.navigation_window=lambda:w;w.refresh_launch_state();assert len(w.tv_games)==3
    old=w.tv_rail
    w.refresh_launch_state();assert w.tv_rail is old
    w.show_library();record(library.root,games[0]['id'],str(uuid4()),400)
    w.refresh_launch_state();assert w.route=='library'
    w.show_game(games[0]);w.refresh_launch_state();assert w.route=='detail'
    w.show_home();assert w.tv_games[0]['id']==games[0]['id']
    for fullscreen in (True,False):
        assert w.set_tv_mode(fullscreen);w.unfullscreen();settle()
        assert w.route=='home' and len(w.tv_games)==3
    w.library=Library(library.root);w.show_home()
    assert [g['id'] for g in w.tv_games]==[games[0]['id'],games[2]['id'],games[1]['id']]
    assert library.path.read_bytes()==before
    w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True);w.destroy();app.quit()
print('PASS: empty Home updates, stable selection/action focus, modal deferral, unchanged history avoids rebuild, route/mode/restart reload, unchanged library and no execution.')
