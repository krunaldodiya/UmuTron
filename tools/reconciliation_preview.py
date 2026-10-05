"""Matched native Home renders from a chosen code snapshot; synthetic data only."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4

if os.environ.get('GDK_BACKEND')!='broadway':raise SystemExit('Use an isolated Broadway fixture only.')
source=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]).resolve();output.mkdir(parents=True,exist_ok=True)
sys.path[:0]=[str(source),str(source/'tools')]
from fullscreen_preview import capture,settle
from catalog_fixtures import FixtureCatalog
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library.play_history import record
from gi.repository import Adw,Gio

with tempfile.TemporaryDirectory(prefix='umutron-matched-render-') as temporary:
    os.environ['XDG_CACHE_HOME']=temporary;library=prepare_demo(True);games=library.games()
    for i,game in enumerate(games):record(library.root,game['id'],str(uuid4()),300-i)
    for i in range(8):
        game=library.new_game();sample=games[i%len(games)]
        game.update(title=sample['title']+' '+str(i+1),artwork=deepcopy(sample['artwork']),description=sample['description'],executable=sample['executable'])
        with patch('game_library.setup_history.time.time',return_value=1700000000+i):library.save_setup(game)
    missing=library.games()[-1];missing['executable']=str(Path(temporary)/'unmounted/game.exe');library.save(missing)
    app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name='';controller.return_value.error=''
        w=Window(app,library,demo=True,catalog_provider=FixtureCatalog())
    app.window=w;w.navigation_window=lambda:w;w.present();w.theme.set_selected(2)
    before=library.path.read_bytes()
    for child in w.layout:
        if isinstance(child,Adw.Banner):child.set_title('NATIVE TEST RENDER · synthetic setup and play history · Play disabled')
    try:
        for width,height in ((1920,1080),(1024,600)):
            w.set_tv_mode(True);w.unfullscreen();settle();w.set_visible(False);w.unrealize()
            w.set_default_size(width,height);w.set_size_request(width,height);w.present();settle(400)
            w.home_selected_id=games[0]['id'];w.home_focus_section='recent';w.show_home();settle(400)
            w.tv_home_tab.grab_focus();settle(200)
            w.tv_scroll.get_hadjustment().set_value(0);w.tv_page.get_vadjustment().set_value(0)
            capture(w,output/f'home-top-{width}.png')
            print('STATE',width,'top',w.tv_scroll.get_hadjustment().get_value(),w.tv_page.get_vadjustment().get_value(),flush=True)
            assert (w.get_width(),w.get_height())==(width,height)
            w.home_setup_tiles[0][1].grab_focus();settle(300)
            w.tv_scroll.get_hadjustment().set_value(0)
            capture(w,output/f'home-setups-{width}.png')
            print('STATE',width,'setups',w.tv_scroll.get_hadjustment().get_value(),w.tv_page.get_vadjustment().get_value(),flush=True)
            assert library.path.read_bytes()==before
    finally:
        w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True);w.destroy();app.quit()
print('PASS: paired synthetic native Home top/grid at exact 1920x1080 and 1024x600; final scroll offsets logged above; Play disabled.')
