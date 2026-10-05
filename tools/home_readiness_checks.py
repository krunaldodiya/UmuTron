"""Home setup chronology/navigation on isolated native GTK; no real games or data."""
import argparse
# Explicit fixture minima prevent the default 1024x768 Broadway monitor from
# clamping a requested test viewport. Native size/bounds assertions stay intact.
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fullscreen_preview import settle,capture
from catalog_fixtures import FixtureCatalog
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from game_library.library import Library
from game_library.play_history import record
from gi.repository import Adw,Gio

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='umutron-home-ready-') as temporary:
    os.environ['XDG_CACHE_HOME']=temporary
    library=prepare_demo(True);legacy=library.games();original=library.path.read_bytes()
    app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
    with patch('game_library.app.Controller') as controller:
        controller.return_value.name='';controller.return_value.error=''
        w=Window(app,library,demo=True,catalog_provider=FixtureCatalog())
    app.window=w;w.navigation_window=lambda:w;w.present();w.theme.set_selected(2)
    w.proton_manager.releases=lambda *args,**kwargs:[]
    for child in w.layout:
        if isinstance(child,Adw.Banner):child.set_title('NATIVE TEST RENDER · synthetic setup and play history · Play disabled')
    settle();original=library.path.read_bytes();w.show_home();settle()
    assert library.path.read_bytes()==original,'Browsing must not invent setup dates'
    assert not w.tv_games and not w.home_setup_tiles
    assert len(library.games())==3 and all('setup_completed_at' not in g for g in library.games())
    metadata=library.new_game();metadata['title']='New setup fixture';library.save(metadata)
    w.show_game(metadata);w.open_manage();w.fields['executable'].set_text(legacy[0]['executable']);w.cancel_editor()
    assert 'setup_completed_at' not in library.games()[-1]
    w.open_manage();w.fields['executable'].set_text(legacy[0]['executable'])
    with patch('game_library.setup_history.time.time',return_value=1700000000):w.save_editor()
    saved=next(g for g in library.games() if g['id']==metadata['id']);assert saved['setup_completed_at']==1700000000
    w.open_manage()
    with patch('game_library.setup_history.time.time',return_value=1800000000):w.save_editor()
    assert next(g for g in library.games() if g['id']==saved['id'])['setup_completed_at']==1700000000
    w.show_home();w.set_tv_mode(True);settle();w.refresh_launch_state()
    assert w.tv_selected_game()['id']==saved['id'] and w.tv_launch_status.get_text()=='', 'Dated ready setups with no play history must not request Setup'
    assert w.tv_play.get_label()=='Play'
    w.set_tv_mode(False);settle()
    for i in range(8):
        game=library.new_game();sample=legacy[i%3]
        game.update(title=sample['title']+' '+str(i+1),artwork=sample['artwork'],description=sample['description'])
        library.save(game);game['executable']=sample['executable']
        with patch('game_library.setup_history.time.time',return_value=1700000010+i):library.save_setup(game)
    missing=library.games()[-1];missing['executable']=str(Path(temporary)/'unmounted/game.exe');library.save(missing)
    record(library.root,legacy[0]['id'],str(uuid4()),100)
    record(library.root,saved['id'],str(uuid4()),200)
    metadata_only=library.new_game();metadata_only['title']='Still metadata only';library.save(metadata_only)
    before=library.path.read_bytes()
    for fullscreen,width,height in ((True,1920,1080),(True,1280,720),(True,1024,600),(False,900,700)):
        w.set_tv_mode(fullscreen);w.unfullscreen();settle();w.set_visible(False);w.unrealize();w.set_default_size(width,height);w.set_size_request(width,height);w.present();settle(600)
        w.home_selected_id=legacy[0]['id'];w.home_focus_section='recent';w.show_home();settle(500)
        assert (w.get_width(),w.get_height())==(width,height)
        assert len(w.tv_games)==2 and len(w.home_setup_tiles)==9
        assert not any(g['id'] in {old['id'] for old in legacy} for g in w.home_setup_games)
        assert w.home_setup_games[0]['id']==missing['id']
        assert 'Files unavailable' in w.home_setup_tiles[0][1].get_tooltip_text()
        w.tv_page.get_vadjustment().set_value(0);capture(w,args.output/f'home-top-{width}.png')
        w.tv_tiles[0][1].grab_focus();settle()
        w.move_control_focus(w,'down');settle()
        assert w.focused_control(w) in [tile for _,tile in w.home_setup_tiles], 'Down should reach new setup grid'
        assert w.tv_page.get_vadjustment().get_value()>0,('Keyboard focus must scroll to setup section',width,w.focused_control(w).compute_bounds(w.tv_page),w.tv_page.get_vadjustment().get_upper(),w.tv_page.get_vadjustment().get_page_size())
        capture(w,args.output/f'home-setups-{width}.png')
        focused=w.focused_control(w);valid,bounds=focused.compute_bounds(w.tv_page)
        assert valid and bounds.get_y()>=-1 and bounds.get_y()+bounds.get_height()<=w.tv_page.get_height()+1, (width,bounds.get_y(),bounds.get_height(),w.tv_page.get_height())
        chosen=w.tv_selected_game();w.show_game(chosen);w.return_from_detail();settle()
        # Broadway may delay allocation of a rebuilt route until a fresh frame.
        capture(w,args.output/f'home-return-{width}.png')
        assert w.home_stage.get_height()>0
        assert w.route=='home' and w.home_focus_section=='setup'
        assert w.focused_control(w) in [tile for _,tile in w.home_setup_tiles], 'Back should restore the setup grid'
        if fullscreen:
            w.controller_action('right');w.controller_action('left');w.controller_action('up');settle()
        accepted=w.tv_open.grab_focus();settle();_,bounds=w.tv_open.compute_bounds(w.tv_page.get_child().get_child())
        print('RETURN HERO',width,accepted,w.focused_control(w) is w.tv_open,w.outlined_control is w.tv_open,w.tv_open.is_ancestor(w.tv_page),bounds.get_y(),w.tv_page.get_vadjustment().get_value(),w.home_stage.get_height(),flush=True)
        assert w.tv_page.get_vadjustment().get_value()<w.home_stage.get_height()
    overlap=next(t for gid,t in w.home_setup_tiles if gid==saved['id']);overlap.grab_focus();settle()
    w.show_game(saved);w.return_from_detail();settle()
    assert w.home_focus_section=='setup' and w.focused_control(w) in [t for _,t in w.home_setup_tiles]
    assert library.path.read_bytes()==before
    w.library=Library(library.root);w.show_home();assert w.home_setup_games[0]['id']==missing['id']
    w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.pool.shutdown(wait=True);w.destroy();app.quit()
print('PASS: setup save/cancel/noop chronology, no metadata-only entries, unchanged legacy dates, missing-file state, responsive Home, down-scroll/focus/back/controller navigation and reload; no execution.')
