"""Inert responsive detail checks; no real desktop, network or execution."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from unittest.mock import Mock,patch
from uuid import uuid4

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
assert os.environ.get('GDK_BACKEND')=='broadway'
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).parent)]
from game_library.app import Application,Window
from game_library.demo import prepare_demo
from catalog_fixtures import FixtureCatalog
from fullscreen_preview import capture,settle
from navigation_fixture import ready
from gi.repository import Adw,Gio,Gtk,Pango

# This headless renderer has no browser to acknowledge animation frames.
# Keep production animation policy unchanged; exercise final native positions.
Gtk.Settings.get_default().set_property('gtk-enable-animations',False)
checks=[];images=[];geometries=[]
def check(condition,name):
    checks.append({'check':name,'passed':bool(condition)})
    assert condition,name

def widgets(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from widgets(child);child=child.get_next_sibling()

def bounds(widget,parent):
    valid,rect=widget.compute_bounds(parent);assert valid
    return [rect.get_x(),rect.get_y(),rect.get_width(),rect.get_height()]

def visible(widget,parent):
    x,y,width,height=bounds(widget,parent)
    return x>=-1 and y>=-1 and x+width<=parent.get_width()+1 and y+height<=parent.get_height()+1

class Catalog(FixtureCatalog):
    def detail(self,identity):
        value=super().detail(identity);value['images']={};return value

library=prepare_demo(True);normal=library.games()[0]
long=deepcopy(normal);long.update(id=str(uuid4()),title='Across the distant stars: a very long journey through a remarkable universe and the complete collection',artwork={},description='A long fictional description for bounded overview and full Game Info access. '*40);library.save(long)
before=library.games();app=Application(demo=True);app.set_flags(Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
with patch('game_library.app.Controller') as controller:
    controller.return_value.name=controller.return_value.error='';w=Window(app,library,demo=True,catalog_provider=Catalog())
app.window=w;w.proton_manager.releases=lambda *args,**kwargs:[]
w.launcher.start=Mock(side_effect=AssertionError('Execution forbidden'))
w.installations.start=Mock(side_effect=AssertionError('Installer forbidden'))
# Production sensitivity with inert services: demo disables Play, which cannot
# receive GTK focus and therefore cannot exercise focus-driven scrolling.
w.demo=False
w.catalog.image_transport=Mock(side_effect=AssertionError('No network'))
w.update_tv_clock=lambda:False;w.tv_clock.set_text('12:00 PM')
for child in w.layout:
    if isinstance(child,Adw.Banner):child.set_visible(False)
try:
    cases=[('desktop-dark',False,2,1120,800,normal),('desktop-light',False,1,1120,800,normal),('fullscreen',True,2,1120,800,normal),('desktop-wide',False,2,1920,1080,normal),('fullscreen-wide',True,2,1920,1080,normal),('desktop-compact',False,2,900,600,normal),('fullscreen-compact',True,2,900,600,normal),('desktop-narrow',False,2,640,600,normal),('desktop-long-missing',False,2,900,600,long),('fullscreen-long-missing',True,2,900,600,long)]
    for name,tv,theme,width,height,game in cases:
        w.set_tv_mode(False);w.theme.set_selected(theme);w.set_tv_mode(tv);w.unfullscreen();w.set_visible(False);w.unrealize()
        w.set_size_request(width,height);w.set_default_size(width,height);w.present();settle(150)
        w.show_game(game);settle(150);w.resize_console(w,None);settle(200)
        image=a.output/(name+'.png');capture(w,image)
        images.append({'path':image.name,'label':'Synthetic native GTK test render; fictional games; execution disabled'})
        title=next(c for c in widgets(w.detail_row) if c.has_css_class('detail-title'))
        copy=next(c for c in widgets(w.detail_row) if c.has_css_class('detail-copy'))
        panel=w.detail_row.get_parent();small=width<1400 or height<850
        check((w.get_width(),w.get_height())==(width,height),name+' exact viewport')
        check(title.get_lines()==2 and copy.get_lines()==3,name+' bounded title/overview')
        check(title.get_ellipsize()==Pango.EllipsizeMode.END,name+' complete title retains native accessible text')
        check(round(title.get_pango_context().get_font_description().get_size()/Pango.SCALE)==(34 if small else 46),name+' shared responsive title scale')
        check(panel.get_width()<=1140 and panel.get_width()<=width,name+' panel width bounded')
        check(not w.cover.get_visible() if width<700 else w.cover.get_visible(),name+' narrow cover adapts')
        check(w.detail_backdrop.get_paintable() is None if game is long else w.detail_backdrop.get_paintable() is not None,name+' missing artwork clears stale backdrop')
        if not visible(w.detail_primary,w.detail_scroll):
            # Fullscreen already exposes LB/RB paging for unusually tall content.
            # Exercise that existing path rather than claiming a disabled demo
            # button or an inactive renderer performs physical focus scrolling.
            with patch.object(w,'navigation_window',return_value=w):w.controller_action('pagedown')
            settle(200)
        w.set_focus(None);w.detail_primary.grab_focus();ready(w,lambda:visible(w.detail_primary,w.detail_scroll),name+' primary reachable after navigation')
        check(visible(w.detail_primary,w.detail_scroll),name+' primary reachable')
        w.detail_gear.grab_focus();ready(w,lambda:visible(w.detail_gear,w.detail_scroll),name+' options focus scroll')
        check(visible(w.detail_gear,w.detail_scroll),name+' options reachable')
        more=next(c for c in widgets(panel) if isinstance(c,Gtk.Button) and c.get_label()=='Game Info')
        more.grab_focus();ready(w,lambda:visible(more,w.detail_scroll),name+' info focus scroll');check(visible(more,w.detail_scroll),name+' Game Info reachable')
        check(not any(isinstance(c,(Gtk.Entry,Gtk.DropDown)) for c in widgets(panel)),name+' overview remains read only')
        geometries.append({'case':name,'panel':bounds(panel,w),'primary':bounds(w.detail_primary,w),'font':title.get_pango_context().get_font_description().get_size()/Pango.SCALE})
        w.show_game_info(game);settle(100)
        info=next(c for c in Gtk.Window.get_toplevels() if c.get_visible() and c.get_title()=='Game Info')
        check(any(isinstance(c,Gtk.Label) and c.get_text()==game['description'] for c in widgets(info)),name+' full description available in Game Info')
        info.close();settle(100)
    for tv in (False,True):
        w.set_tv_mode(tv);w.unfullscreen();w.show_game(normal);settle(100)
        with patch.object(w.launcher,'current',return_value={'game_id':normal['id'],'state':'Running','title':normal['title']}),patch.object(w.launcher,'active',return_value=True):
            w.refresh_launch_state()
            check(w.detail_primary.get_label()=='Stop' and w.detail_primary.has_css_class('destructive-action'),'Active game shows Stop with shared destructive appearance in '+('fullscreen' if tv else 'desktop'))
            check(w.detail_primary.get_sensitive(),'Owned running game keeps Stop enabled')
            settle(100)
            color=w.detail_primary.get_style_context().get_color()
            check(abs(color.red-69/255)<.01 and abs(color.green-19/255)<.01 and abs(color.blue-22/255)<.01,'Stop retains shared foreground tokens')
            stop_image=a.output/('fullscreen-stop.png' if tv else 'desktop-stop.png');capture(w,stop_image)
            images.append({'path':stop_image.name,'label':'Synthetic native GTK Stop state; mocked running session; no game execution'})
        with patch.object(w.launcher,'current',return_value={'game_id':str(uuid4()),'state':'Running','title':'Other fixture'}),patch.object(w.launcher,'active',return_value=True):
            w.refresh_launch_state()
            check(not w.detail_primary.get_sensitive() and not w.detail_primary.has_css_class('destructive-action'),'Another active game keeps the one-game guard and no owned Stop style')
        w.refresh_launch_state()
    w.set_tv_mode(False);w.show_game(normal);w.open_manage();settle(100)
    saved=deepcopy(library.games());w.launch_args.get_buffer().set_text('discarded draft');w.cancel_editor();settle()
    check(w.editor is None and library.games()==saved,'Desktop Setup cancellation preserves saved metadata')
    check(library.games()==before,'Mode changes, detail navigation and information dialogs preserve saved games')
    w.launcher.start.assert_not_called();w.installations.start.assert_not_called()
finally:
    for child in list(Gtk.Window.get_toplevels()):
        if child is not w:child.destroy()
    w.exiting=True;w.catalog_cancel();w.catalog_pool.shutdown(wait=True,cancel_futures=True);w.controller.close();w.destroy();w.pool.shutdown(wait=True,cancel_futures=True)
    (a.output/'results.json').write_text(json.dumps({'checks':checks,'images':images,'geometry':geometries,'scope':'Native synthetic method/signal and rendered layout checks; no physical-input claim'},indent=2)+'\n')
print(str(len(checks))+' responsive detail assertions passed')
