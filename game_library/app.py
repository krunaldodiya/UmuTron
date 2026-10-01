"""GTK desktop UI. Network/archive work stays off the main loop."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sys
import gi

gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango
from .library import description_excerpt, Library, ART_KINDS, image_extension
from .launcher import preparation_progress, Launcher, defaults, build_command
from .proton_manager import ProtonManager
from .installations import Installations
from .tray import Tray, close_action
from .controller import Controller
from .providers import Credentials, IGDB, SteamGridDB
from . import metadata, __version__


def label(text, css=None, **kwargs):
    result=Gtk.Label(label=text,**kwargs)
    if css: result.add_css_class(css)
    return result


def button(text, callback, css=None, icon=None):
    result=Gtk.Button(label=text)
    if icon:
        result.set_icon_name(icon); result.set_tooltip_text(text)
        result.update_property([Gtk.AccessibleProperty.LABEL],[text])
    if css: result.add_css_class(css)
    focus=Gtk.EventControllerFocus();focus.connect('enter',lambda _:result.add_css_class('control-focused'));focus.connect('leave',lambda _:result.remove_css_class('control-focused'));result.add_controller(focus)
    result.connect('clicked',lambda _:callback())
    return result


def box(vertical=True, spacing=12):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,spacing=spacing)


def margins(widget,n=24):
    widget.set_margin_top(n); widget.set_margin_bottom(n)
    widget.set_margin_start(n); widget.set_margin_end(n)
    return widget


def clear(container):
    while container.get_first_child(): container.remove(container.get_first_child())


class Window(Adw.ApplicationWindow):
    def __init__(self, app, library, demo=False):
        super().__init__(application=app,title='Game Library Launcher',default_width=1120,default_height=800)
        css=Gtk.CssProvider()
        css.load_from_data(b'.tv-mode { background: #111723; color: #f5f7fb; font-size: 16px; } .tv-mode button { min-height: 42px; padding: 10px 18px; border-radius: 12px; } .tv-mode .tv-card { padding: 5px; background: alpha(#202938, .8); border-radius: 10px; } .tv-mode .tv-game-chip { transform: scale(.666667); transition: transform 160ms ease-out; } .tv-mode .tv-game-chip.selected-game, .tv-mode .tv-game-chip.control-focused, .tv-mode .tv-game-chip:focus { transform: scale(1); } .tv-mode .tv-card .art-frame { padding: 0; background: transparent; } .tv-mode .tv-tab-active { color: #fff; font-weight: 800; border-bottom: 2px solid #fff; border-radius: 0; } .tv-mode .tv-clock { font-size: 20px; } .tv-mode .tv-controls button { min-height: 30px; padding: 6px 12px; } .control-focused, button:focus, .tv-mode button:focus-visible { outline: 3px solid #82bcff; outline-offset: 2px; } .tv-mode .selected-game { background: alpha(#82bcff, .18); } .tv-mode .tv-title { font-size: 38px; font-weight: 700; } .tv-mode .tv-description { font-size: 16px; font-weight: 400; line-height: 1.4; } .tv-mode .tv-hints { font-size: 13px; color: #c4d0e5; } .art-frame { background: alpha(@window_fg_color, 0.055); border-radius: 12px; padding: 8px; } .game-card { padding: 10px; } .game-card:hover { background: alpha(@accent_color, 0.09); }')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.demo=demo;self.tv_mode=False;self.tv_selected_id=None;self.tv_tiles=[];self.tv_section='games'
        self.library=library; self.launcher=Launcher(library.root); self.proton_manager=ProtonManager(library.root/'proton-manager'); self.launch_fields={}; self.play_buttons={}; self.installations=Installations(library,self.launcher);self.editor=None;self.editor_kind=None;self.exiting=False
        self.credentials=Credentials(library.root/'demo-provider-settings') if demo else Credentials(); self.igdb=IGDB(self.credentials); self.sgdb=SteamGridDB(self.credentials)
        self.pool=ThreadPoolExecutor(max_workers=2)
        self.busy=False; self.game=None; self.original=None; self.fields={}; self.log_lines=[]
        self.connect('close-request',self.close_requested);self.connect('notify::focus-widget',self.update_focus_outline)
        self.toast=Adw.ToastOverlay(); self.set_content(self.toast)
        self.layout=box(spacing=0)
        self.scene=Gtk.Overlay();self.backdrop=Gtk.Picture(content_fit=Gtk.ContentFit.COVER,can_shrink=True,opacity=0);self.backdrop.set_visible(True);self.backdrop.set_can_target(False)
        self.scene.set_child(self.backdrop);self.toast.set_child(self.layout)
        self.header=Adw.HeaderBar()
        self.back=button('Back to library',self.go_back,icon='go-previous-symbolic')
        self.back.set_visible(False); self.header.pack_start(self.back)
        self.heading=Adw.WindowTitle(title='Your game library',subtitle='Your games · UMU and Proton')
        self.header.set_title_widget(self.heading)
        self.theme=Gtk.DropDown.new_from_strings(['Follow system','Light','Dark'])
        self.theme.set_tooltip_text('Appearance')
        self.theme.set_selected(['system','light','dark'].index(self.library.data['settings'].get('theme','system')))
        self.theme.connect('notify::selected',self.theme_changed)
        self.theme.set_visible(False)
        self.exit_button=button('Exit Launcher',self.explicit_exit,icon='application-exit-symbolic');self.exit_button.set_visible(False)
        self.settings_button=button('Settings',self.open_settings,icon='preferences-system-symbolic');self.settings_button.set_visible(False)
        self.mode_button=button('Fullscreen',lambda:self.set_tv_mode(not self.tv_mode));self.mode_button.set_tooltip_text('Switch desktop / fullscreen mode (F11)');self.mode_button.set_visible(False)
        self.layout.append(self.header)
        self.tv_controls=box(False,16);self.tv_controls.add_css_class('tv-controls');margins(self.tv_controls,20);self.tv_controls.set_visible(False)
        self.tv_games_tab=button('Games',lambda:self.set_tv_section('games'));self.tv_games_tab.add_css_class('flat');self.tv_controls.append(self.tv_games_tab)
        self.tv_library_tab=button('Library',lambda:self.set_tv_section('library'));self.tv_library_tab.add_css_class('flat');self.tv_controls.append(self.tv_library_tab)
        spacer=Gtk.Box(hexpand=True);self.tv_controls.append(spacer)
        self.tv_search=button('Search games',self.search_library,icon='system-search-symbolic');self.tv_search.add_css_class('flat');self.tv_controls.append(self.tv_search)
        self.tv_menu=button('Fullscreen options',self.open_tv_options,icon='emblem-system-symbolic');self.tv_menu.add_css_class('flat');self.tv_controls.append(self.tv_menu)
        self.tv_clock=label('','tv-clock');self.tv_controls.append(self.tv_clock);self.update_tv_clock();GLib.timeout_add_seconds(30,self.update_tv_clock)
        self.layout.append(self.tv_controls)
        if demo:
            demo_banner=Adw.Banner(title='DEMO · fictional games · Play is disabled',revealed=True)
            self.layout.append(demo_banner)
        self.progress=box(False,8); margins(self.progress,10)
        self.spinner=Gtk.Spinner(); self.progress.append(self.spinner)
        self.progress_label=label(''); self.progress.append(self.progress_label)
        self.progress.set_visible(False); self.layout.append(self.progress)
        self.runtime_progress=box(False,10);margins(self.runtime_progress,12);self.runtime_spinner=Gtk.Spinner();self.runtime_progress.append(self.runtime_spinner)
        self.runtime_label=label('',wrap=True,xalign=0);self.runtime_label.set_hexpand(True);self.runtime_progress.append(self.runtime_label);self.runtime_progress.set_visible(False);self.runtime_label.add_css_class('caption')
        self.body=box(spacing=0); self.body.set_vexpand(True); self.layout.append(self.body)
        self.log_button=button('Activity',self.toggle_log,icon='view-list-symbolic'); self.log_button.set_visible(False)
        self.log_revealer=Gtk.Revealer(); self.log_text=Gtk.TextView(editable=False,cursor_visible=False,wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.log_text.set_top_margin(10); self.log_text.set_left_margin(16)
        log_scroll=Gtk.ScrolledWindow(min_content_height=110,max_content_height=160,propagate_natural_height=True)
        log_scroll.set_child(self.log_text); self.log_revealer.set_child(log_scroll); self.layout.append(self.log_revealer)
        self.apply_theme(); self.show_library()
        keys=Gtk.EventControllerKey();keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE);self.keyboard_controller=keys;keys.connect('key-pressed',self.on_key);self.add_controller(keys)
        self.controller=Controller(self.controller_action,self.controller_enabled)
        GLib.timeout_add(40,self.controller.poll)
        app.connect('shutdown',lambda *_:self.controller.close())
        if self.library.data['settings'].get('default_display_mode','desktop')=='fullscreen':self.set_tv_mode(True)
        GLib.timeout_add(250,self.refresh_launch_state)

    def set_tv_mode(self,enabled):
        enabled=bool(enabled)
        if self.editor or self.busy or any(w.get_visible() and w.get_modal() and w.get_transient_for() is self for w in Gtk.Window.get_toplevels()):
            self.notify('Save or cancel the current dialog before switching display mode.');return False
        if enabled==self.tv_mode:
            self.present();return True
        current=deepcopy(self.game) if self.game else None
        self.tv_mode=enabled
        self.toast.set_child(None)
        if enabled:
            self.scene.add_overlay(self.layout);self.scene.set_measure_overlay(self.layout,True);self.toast.set_child(self.scene)
        else:
            self.scene.remove_overlay(self.layout);self.toast.set_child(self.layout)
        self.backdrop.set_opacity(.4 if enabled and self.tv_section=='games' else 0)
        self.set_decorated(not enabled);self.header.set_visible(not enabled);self.tv_controls.set_visible(enabled)
        self.mode_button.set_label('Desktop mode' if enabled else 'Fullscreen')
        self.theme.set_visible(False);self.settings_button.set_visible(False);self.log_button.set_visible(False)
        self.log_revealer.set_reveal_child(False)
        self.exit_button.set_visible(False);self.header.set_show_end_title_buttons(not enabled);self.header.set_show_start_title_buttons(not enabled)
        if enabled:
            self.add_css_class('tv-mode');self.fullscreen()
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        else:
            self.remove_css_class('tv-mode');self.unfullscreen();self.apply_theme()
        if current:self.show_game(current)
        else:self.show_library()
        self.present();return True

    def update_tv_clock(self):
        self.tv_clock.set_text(datetime.now().strftime('%I:%M %p').lstrip('0'))
        self.tv_clock.set_focusable(False)
        return not self.exiting

    def set_tv_section(self,section):
        if not self.tv_mode:return
        self.section_tab_focus=self.tv_games_tab if section=='games' else self.tv_library_tab
        self.tv_section=section;self.show_library();self.section_tab_focus=None

    def tv_tile(self,game,grid=False):
        tile=button(game['title'],lambda g=game:self.show_game(g));tile.set_focusable(False);tile.add_css_class('tv-card');tile.set_valign(Gtk.Align.START);tile.set_tooltip_text('Open '+game['title'])
        tile.update_property([Gtk.AccessibleProperty.LABEL],['Open '+game['title']])
        if not grid:tile.add_css_class('tv-game-chip')
        content=box(spacing=8);tile.set_child(content)
        name=game['artwork'].get('portrait') or game['artwork'].get('landscape')
        size=160 if grid else 88
        artwork=Gtk.AspectFrame(xalign=.5,yalign=.5,ratio=1,obey_child=False);artwork.set_size_request(size,size);artwork.set_halign(Gtk.Align.CENTER)
        path=self.library.art_dir/name if name else None
        image=Gtk.Image(icon_name='applications-games-symbolic',pixel_size=48)
        if path and path.is_file():
            try:
                pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path),size,size,True)
                image=Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pixbuf));image.set_can_shrink(True);image.set_content_fit(Gtk.ContentFit.COVER)
            except GLib.Error:pass
        artwork.set_child(image);content.append(artwork)
        if grid:
            title=label(game['title'],'heading',xalign=0,wrap=True,lines=2,ellipsize=Pango.EllipsizeMode.END,max_width_chars=16);title.set_size_request(-1,54);content.append(title)
        focus=Gtk.EventControllerFocus();focus.connect('enter',lambda _,g=game:self.select_tv_game(g));tile.add_controller(focus)
        return tile

    def show_tv_library(self):
        return_id=self.tv_selected_id
        self.game=None;self.original=None;self.fields={};self.launch_fields={};self.description=None;self.play_buttons={};clear(self.body)
        self.back.set_visible(False);self.heading.set_title('Your games');self.heading.set_subtitle('Fullscreen · TV mode')
        for tab,section in ((self.tv_games_tab,'games'),(self.tv_library_tab,'library')):
            if section==self.tv_section:tab.add_css_class('tv-tab-active')
            else:tab.remove_css_class('tv-tab-active')
        self.backdrop.set_opacity(.4 if self.tv_section=='games' else 0)
        self.tv_games=sorted(self.library.games(),key=lambda g:g['title'].casefold());self.tv_tiles=[]
        if self.tv_section=='library':
            self.tv_games=[g for g in self.tv_games if g.get('executable') and (g.get('installation',{}).get('mode')!='installer' or g['installation'].get('confirmed'))]
            self.show_tv_grid(return_id);return
        if not self.tv_games:
            empty=Adw.StatusPage(title='Your library is ready to grow',description='Switch to desktop mode to add games and set them up.',icon_name='applications-games-symbolic');self.body.append(empty);self.tv_games_tab.grab_focus();return
        tv_content=box(spacing=0);tv_content.set_vexpand(True)
        self.tv_page=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,vscrollbar_policy=Gtk.PolicyType.AUTOMATIC);self.tv_page.set_vexpand(True);self.tv_page.set_child(tv_content);self.body.append(self.tv_page)
        # Compact, fixed-height game row above the selected game's hero.
        self.tv_rail=box(False,16);margins(self.tv_rail,24)
        self.tv_scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.EXTERNAL,vscrollbar_policy=Gtk.PolicyType.NEVER);self.tv_scroll.set_child(self.tv_rail);self.tv_scroll.get_child().set_hscroll_policy(Gtk.ScrollablePolicy.NATURAL);tv_content.append(self.tv_scroll)
        self.tv_scroll.get_hadjustment().connect('changed',lambda adjustment:GLib.idle_add(self.pad_tv_rail,adjustment))
        self.tv_selected_title=label('','heading',xalign=0,ellipsize=Pango.EllipsizeMode.END);self.tv_selected_title.set_margin_start(36);self.tv_selected_title.set_margin_end(36);self.tv_selected_title.set_size_request(-1,32);self.tv_selected_title.set_visible(False);tv_content.append(self.tv_selected_title)
        for game in self.tv_games:
            tile=self.tv_tile(game);self.tv_rail.append(tile);self.tv_tiles.append((game['id'],tile))
        self.tv_rail_end=Gtk.Box();self.tv_rail.append(self.tv_rail_end)
        self.tv_hero=Gtk.Picture(content_fit=Gtk.ContentFit.COVER,can_shrink=True,opacity=0)
        hero=Gtk.Overlay();hero.set_child(self.tv_hero);hero.set_vexpand(True);hero.set_size_request(-1,360);tv_content.append(hero)
        summary=box(spacing=10);margins(summary,24);summary.set_valign(Gtk.Align.END);hero.add_overlay(summary)
        self.tv_logo=Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN,can_shrink=True);self.tv_logo.set_halign(Gtk.Align.START);self.tv_logo.set_size_request(280,90)
        brand=Gtk.Overlay();brand.set_child(self.tv_logo);brand.set_size_request(-1,104);self.tv_logo.set_visible(False);summary.append(brand)
        self.tv_title=label('','tv-title',xalign=0,wrap=True,lines=2,ellipsize=Pango.EllipsizeMode.END);self.tv_title.set_size_request(-1,104);brand.add_overlay(self.tv_title)
        self.tv_related=label('','tv-hints',xalign=0,ellipsize=Pango.EllipsizeMode.END);self.tv_related.set_size_request(-1,24);summary.append(self.tv_related)
        self.tv_description=label('','tv-description',xalign=0,wrap=True,lines=2,ellipsize=Pango.EllipsizeMode.END,max_width_chars=70);self.tv_description.set_size_request(-1,48);summary.append(self.tv_description)
        actions=box(False);summary.append(actions)
        self.tv_play=button('Play',lambda:self.play_game(self.tv_selected_game()),'suggested-action');self.tv_play.add_css_class('pill');actions.append(self.tv_play)
        self.tv_launch_status=label('','caption',xalign=0);summary.append(self.tv_launch_status);self.place_runtime_progress(summary)
        self.tv_hints=label('D-pad / stick: Move   A / Enter: Select   B / Esc: Back   X: Focus Play / Stop   Start / F11: Options','tv-hints',wrap=True,xalign=0);margins(self.tv_hints,16);tv_content.append(self.tv_hints)
        game=next((g for g in self.tv_games if g['id']==return_id),self.tv_games[0]);self.select_tv_game(game)
        self.restrict_tv_focus(self.body)
        self.finish_tv_library_focus()

    def show_tv_grid(self,return_id=None):
        title=label('Installed games · '+str(len(self.tv_games)),'tv-title',xalign=0);margins(title,24);self.body.append(title)
        self.tv_grid=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,min_children_per_line=2,max_children_per_line=10,column_spacing=20,row_spacing=20);margins(self.tv_grid,24);self.tv_grid.set_valign(Gtk.Align.START)
        self.tv_scroll=self.scrolled(self.tv_grid);self.body.append(self.tv_scroll)
        if not self.tv_games:
            empty=Adw.StatusPage(title='No installed games yet',description='Set up game files in desktop mode. Your metadata entries are still available under Games.',icon_name='applications-games-symbolic');self.body.append(empty)
            self.tv_library_tab.grab_focus()
        for game in self.tv_games:
            tile=self.tv_tile(game,grid=True);self.tv_grid.append(tile);self.tv_tiles.append((game['id'],tile))
        self.tv_hints=label('D-pad / stick: Move   A / Enter: Game details   B / Esc: Games   X: Focus Play / Stop','tv-hints',wrap=True,xalign=0);margins(self.tv_hints,16);self.body.append(self.tv_hints)
        if self.tv_games:
            game=next((g for g in self.tv_games if g['id']==return_id),self.tv_games[0]);self.select_tv_game(game)
            self.finish_tv_library_focus()
        self.restrict_tv_focus(self.body)

    def restrict_tv_focus(self,widget):
        if isinstance(widget,Gtk.Label):widget.set_selectable(False)
        if isinstance(widget,Gtk.Viewport):widget.set_scroll_to_focus(widget.get_child() is not getattr(self,'tv_rail',None))
        if not isinstance(widget,(Gtk.Button,Gtk.MenuButton)):widget.set_focusable(False)
        child=widget.get_first_child()
        while child:self.restrict_tv_focus(child);child=child.get_next_sibling()

    def focused_control(self,target):
        focus=target.get_focus()
        while focus and not isinstance(focus,(Gtk.Button,Gtk.MenuButton)):focus=focus.get_parent()
        if focus and isinstance(focus.get_parent(),Gtk.MenuButton):return focus.get_parent()
        return focus

    def update_focus_outline(self,*_):
        focused=self.focused_control(self)
        previous=getattr(self,'outlined_control',None)
        if previous is not focused:
            if previous:previous.remove_css_class('control-focused')
            if focused:focused.add_css_class('control-focused')
            self.outlined_control=focused

    def move_control_focus(self,target,action):
        # Explicit control-only navigation; text, scrollbars and containers never become stops.
        controls=[]
        def visit(widget):
            if isinstance(widget,(Gtk.Button,Gtk.MenuButton)):
                if widget.get_mapped() and widget.is_sensitive() and widget.get_focusable():controls.append(widget)
                return
            child=widget.get_first_child()
            while child:visit(child);child=child.get_next_sibling()
        visit(target)
        if not controls:return
        current=self.focused_control(target)
        if current not in controls:controls[0].grab_focus();return
        if action in ('next','previous'):
            controls[(controls.index(current)+(1 if action=='next' else -1))%len(controls)].grab_focus();return
        def center(widget):
            valid,bounds=widget.compute_bounds(target)
            return (bounds.get_x()+bounds.get_width()/2,bounds.get_y()+bounds.get_height()/2) if valid else (0,0)
        x,y=center(current);candidates=[]
        for control in controls:
            if control is current:continue
            cx,cy=center(control);dx,dy=cx-x,cy-y
            along=(dx if action=='right' else -dx if action=='left' else dy if action=='down' else -dy)
            across=abs(dy) if action in ('left','right') else abs(dx)
            if along>1:candidates.append((along+across*3,control))
        if candidates:min(candidates,key=lambda pair:pair[0])[1].grab_focus()

    def tv_selected_game(self):return next(g for g in self.tv_games if g['id']==self.tv_selected_id)

    def finish_tv_library_focus(self):
        tab=getattr(self,'section_tab_focus',None)
        tile=next((tile for gid,tile in self.tv_tiles if gid==self.tv_selected_id),None)
        # Keep every other card out of GTK's automatic focus fallback while rebuilding.
        if tab:tab.grab_focus()
        elif tile:
            tile.set_focusable(True);tile.grab_focus()
        for _,card in self.tv_tiles:card.set_focusable(True)
        self.update_focus_outline()
        if tile and not tab:
            def allocated(widget,clock):
                if widget.get_width()<=0:return True
                if self.tv_section=='games':self.scroll_tv_card_into_view(widget)
                return False
            tile.add_tick_callback(allocated)

    def focus_tv_card(self,animate=True):
        tile=next((t for gid,t in self.tv_tiles if gid==self.tv_selected_id),None)
        if tile:
            tile.grab_focus()
            if self.tv_section=='library':return
            self.scroll_tv_card_into_view(tile,animate)

    def pad_tv_rail(self,adjustment):
        if adjustment!=self.tv_scroll.get_hadjustment():return False
        # Trailing room lets even a short library slide to each selected icon.
        if self.tv_mode and self.game is None and self.tv_section=='games':
            padding=max(24,int(adjustment.get_page_size())-116)
            if hasattr(self,'tv_rail_end') and self.tv_rail_end.get_size_request()[0]!=padding:self.tv_rail_end.set_size_request(padding,-1)
        return False

    def scroll_tv_card_into_view(self,tile,animate=False):
        scroll=self.tv_scroll;adjustment=scroll.get_hadjustment()
        if tile.get_width()<=0:return
        valid,bounds=tile.compute_bounds(self.tv_rail)
        if not valid:return
        left=bounds.get_x()
        target=max(adjustment.get_lower(),min(adjustment.get_upper()-adjustment.get_page_size(),left))
        callback=getattr(self,'rail_animation',None)
        if callback:
            GLib.source_remove(callback);self.rail_animation=None
        settings=Gtk.Settings.get_default()
        if not animate or not settings.get_property('gtk-enable-animations'):
            adjustment.set_value(target);return
        start=adjustment.get_value();started=GLib.get_monotonic_time()
        def frame():
            if self.game is not None or self.tv_section!='games' or self.tv_scroll is not scroll:
                self.rail_animation=None;return False
            progress=min(1,(GLib.get_monotonic_time()-started)/220000)
            eased=1-(1-progress)**3
            adjustment.set_value(start+(target-start)*eased)
            if progress>=1:self.rail_animation=None;return False
            return True
        self.rail_animation=GLib.timeout_add(16,frame)

    def select_tv_game(self,game):
        self.tv_selected_id=game['id']
        for gid,tile in self.tv_tiles:
            if gid==game['id']:tile.add_css_class('selected-game')
            else:tile.remove_css_class('selected-game')
        name=game['artwork'].get('hero') or game['artwork'].get('landscape')
        path=self.library.art_dir/name if name else None
        self.backdrop.set_filename(str(path)) if path and path.is_file() else self.backdrop.set_paintable(None)
        self.backdrop.set_opacity(.22 if self.tv_section=='library' else .4)
        if self.tv_section=='library':return
        self.tv_selected_title.set_text(game['title']);self.tv_title.set_text(game['title']);self.tv_description.set_text(description_excerpt(game['description']))
        self.tv_related.set_text(' · '.join(filter(None,(game.get('release_date'),game.get('genres')))))
        for picture,kind in ((self.tv_hero,'hero'),(self.tv_logo,'logo')):
            name=game['artwork'].get(kind) or (game['artwork'].get('landscape') if kind=='hero' else None)
            path=self.library.art_dir/name if name else None
            picture.set_filename(str(path)) if path and path.is_file() else picture.set_paintable(None)
            if kind=='hero':
                self.backdrop.set_filename(str(path)) if path and path.is_file() else self.backdrop.set_paintable(None)
            if kind=='logo':
                picture.set_visible(False);self.tv_title.set_opacity(1)
        self.play_buttons={game['id']:self.tv_play};self.refresh_launch_state()
        tile=next((tile for gid,tile in self.tv_tiles if gid==game['id']),None)
        if tile and tile.get_width()>0:self.scroll_tv_card_into_view(tile,True)

    def open_tv_options(self):
        dialog=getattr(self,'tv_options_dialog',None)
        if dialog and dialog.get_visible():dialog.present();return
        dialog=Adw.Window(title='Fullscreen options',transient_for=self,modal=True,default_width=420,default_height=230)
        self.tv_options_dialog=dialog
        content=box();margins(content,24);dialog.set_content(content)
        header=box(False);header.append(label('Fullscreen options','title-1',xalign=0,hexpand=True));header.append(button('Close',dialog.close,icon='window-close-symbolic'));content.append(header)
        def exit_fullscreen():
            dialog.close();self.set_tv_mode(False)
        def exit_launcher():
            dialog.close();self.explicit_exit()
        leave=button('Exit fullscreen',exit_fullscreen);content.append(leave);content.append(button('Exit',exit_launcher))
        keys=Gtk.EventControllerKey();keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE);keys.connect('key-pressed',self.on_key);dialog.add_controller(keys)
        dialog.connect('close-request',lambda _:(self.tv_menu.grab_focus(),False)[-1])
        dialog.present();leave.grab_focus()

    def search_library(self):
        dialog=Adw.Window(title='Search games',transient_for=self,modal=True,default_width=640,default_height=520)
        content=box();margins(content,24);dialog.set_content(content)
        header=box(False);header.append(label('Search games','title-1',xalign=0,hexpand=True))
        header.append(button('Close',dialog.close,icon='window-close-symbolic'));content.append(header)
        entry=Gtk.SearchEntry(placeholder_text='Search your library',hexpand=True);content.append(entry)
        results=box(spacing=8);scroll=self.scrolled(results);content.append(scroll)
        def choose(game):
            dialog.close();self.show_game(game)
        def search(*_):
            clear(results);query=entry.get_text().strip().casefold()
            games=[g for g in sorted(self.library.games(),key=lambda g:g['title'].casefold()) if query in g['title'].casefold()]
            for game in games:
                row=button(game['title'],lambda g=game:choose(g));results.append(row)
            if not games:results.append(label('No games found.','dim-label',xalign=0))
        entry.connect('notify::text',search);search()
        keys=Gtk.EventControllerKey();keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE);keys.connect('key-pressed',self.on_key);dialog.add_controller(keys)
        dialog.connect('close-request',lambda _:(self.tv_search.grab_focus(),False)[-1])
        dialog.present();entry.grab_focus()

    def navigation_window(self):
        # Only launcher-owned, focused windows receive controller navigation.
        for window in Gtk.Window.get_toplevels():
            parent=window
            while parent and parent is not self:parent=parent.get_transient_for()
            if parent is self and window.get_visible() and window.is_active():return window
        return None

    def controller_enabled(self):return self.tv_mode and not self.busy and self.navigation_window() is not None

    def controller_action(self,action):
        if not self.controller_enabled():return
        target=self.navigation_window()
        if action=='desktop':
            if target is self:self.tv_menu.grab_focus();self.open_tv_options()
            return
        if action=='back':
            if target is not self:
                if target is self.editor:self.cancel_editor()
                else:target.close()
            elif self.game:self.show_library()
            elif self.tv_section=='library':self.set_tv_section('games')
            else:self.tv_games_tab.grab_focus()
            return
        if action=='play':
            if target is self:
                control=self.play_buttons.get(self.game['id'] if self.game else self.tv_selected_id)
                if control:control.grab_focus();self.update_focus_outline()
            return
        if action in ('pageup','pagedown'):
            if hasattr(target,'info_scroll') or (target is self and self.game and hasattr(self,'detail_scroll')):
                adjustment=(target.info_scroll if hasattr(target,'info_scroll') else self.detail_scroll).get_vadjustment()
                adjustment.set_value(max(adjustment.get_lower(),min(adjustment.get_upper()-adjustment.get_page_size(),adjustment.get_value()+(.8 if action=='pagedown' else -.8)*adjustment.get_page_size())))
            return
        if action in ('left','right','up','down','next','previous'):
            focus=self.focused_control(target)
            header=[self.tv_games_tab,self.tv_library_tab,self.tv_search,self.tv_menu]
            if target is self and focus in header:
                if action in ('left','right'):
                    index=header.index(focus);index=max(0,min(len(header)-1,index+(1 if action=='right' else -1)));header[index].grab_focus();self.update_focus_outline();return
                if action=='down' and self.game is None and self.tv_tiles:self.focus_tv_card();self.update_focus_outline();return
                if action=='up':return
            if target is self and self.game is None and self.tv_section=='games' and self.tv_tiles and focus in [tile for _,tile in self.tv_tiles] and action in ('left','right'):
                index=next(i for i,g in enumerate(self.tv_games) if g['id']==self.tv_selected_id)
                index=(index+(1 if action=='right' else -1))%len(self.tv_games)
                self.select_tv_game(self.tv_games[index]);self.focus_tv_card();return
            self.move_control_focus(target,action);return
        if action=='select':
            focus=self.focused_control(target)
            if focus and focus.is_sensitive():focus.activate()
            else:self.move_control_focus(target,'next')

    def on_key(self,controller,keyval,keycode,state):
        if keyval==Gdk.KEY_F11:
            if self.tv_mode:self.tv_menu.grab_focus();self.open_tv_options()
            else:self.set_tv_mode(True)
            return True
        if not self.tv_mode:return False
        target=controller.get_widget() if controller else self
        focus=target.get_focus()
        if isinstance(focus,(Gtk.Entry,Gtk.Text,Gtk.TextView)) and keyval!=Gdk.KEY_Escape:return False
        if keyval==Gdk.KEY_Tab:self.controller_action('previous' if state&Gdk.ModifierType.SHIFT_MASK else 'next');return True
        action={Gdk.KEY_Left:'left',Gdk.KEY_Right:'right',Gdk.KEY_Up:'up',Gdk.KEY_Down:'down',Gdk.KEY_Return:'select',Gdk.KEY_KP_Enter:'select',Gdk.KEY_Escape:'back',Gdk.KEY_Page_Up:'pageup',Gdk.KEY_Page_Down:'pagedown'}.get(keyval)
        if action:self.controller_action(action);return True
        return False

    def log(self,text):
        self.log_lines.append(datetime.now().strftime('%H:%M')+'  '+str(text))
        self.log_lines=self.log_lines[-100:]
        self.log_text.get_buffer().set_text('\n'.join(self.log_lines))

    def notify(self,text):
        self.log(text); self.toast.add_toast(Adw.Toast.new(text))

    def error(self,error):
        self.log('Error: '+str(error))
        dialog=Adw.MessageDialog.new(self.editor or self,'Could not complete this action',str(error)[:2000])
        dialog.add_response('ok','OK'); dialog.present()

    def toggle_log(self): self.log_revealer.set_reveal_child(not self.log_revealer.get_reveal_child())

    def apply_theme(self):
        mode=self.library.data['settings'].get('theme','system')
        Adw.StyleManager.get_default().set_color_scheme({'system':Adw.ColorScheme.DEFAULT,'light':Adw.ColorScheme.FORCE_LIGHT,'dark':Adw.ColorScheme.FORCE_DARK}[mode])

    def theme_changed(self,*_):
        try:
            self.library.set_theme(['system','light','dark'][self.theme.get_selected()]); self.apply_theme()
        except Exception as e: self.error(e)

    def async_job(self,message,work,done):
        if self.busy: return
        self.set_focus(None)
        self.busy=True; self.body.set_sensitive(False); self.header.set_sensitive(False)
        modal_windows=[w for w in Gtk.Window.get_toplevels() if w.get_transient_for()==self]
        for modal in modal_windows:modal.set_focus(None);modal.set_sensitive(False)
        self.progress_label.set_text(message); self.progress.set_visible(True); self.spinner.start(); self.log(message)
        future=self.pool.submit(work)
        def finish():
            self.busy=False; self.body.set_sensitive(True); self.header.set_sensitive(True)
            for modal in modal_windows: modal.set_sensitive(True)
            self.progress.set_visible(False); self.spinner.stop()
            try: done(future.result())
            except Exception as e: self.error(e)
            return False
        future.add_done_callback(lambda _:GLib.idle_add(finish))

    def confirm(self,title,body,action,callback,destructive=False):
        dialog=Adw.MessageDialog.new(self.editor or self,title,body)
        dialog.add_response('cancel','Cancel'); dialog.add_response('confirm',action)
        dialog.set_default_response('cancel'); dialog.set_close_response('cancel')
        dialog.set_response_appearance('confirm',Adw.ResponseAppearance.DESTRUCTIVE if destructive else Adw.ResponseAppearance.SUGGESTED)
        dialog.connect('response',lambda _,response:callback() if response=='confirm' else None)
        dialog.present()

    def choose_file(self,title,callback,save=False,folder=False,filename=None,start_folder=None):
        action=Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.OPEN
        dialog=Gtk.FileChooserNative.new(title,self.editor or self,action,'Save' if save else 'Select','Cancel')
        if filename: dialog.set_current_name(filename)
        if start_folder and Path(start_folder).is_dir():dialog.set_current_folder(Gio.File.new_for_path(str(start_folder)))
        def response(d,r):
            if r==Gtk.ResponseType.ACCEPT:
                selected=d.get_file()
                if selected and selected.get_path():
                    try: callback(Path(selected.get_path()))
                    except Exception as e: self.error(e)
            d.destroy()
        dialog.connect('response',response); dialog.show()

    def picture(self,name,width,height):
        frame=Gtk.Box(); frame.set_size_request(width,height); frame.set_vexpand(False); frame.set_hexpand(False); frame.set_valign(Gtk.Align.START); frame.add_css_class('art-frame')
        if name and (self.library.art_dir/name).is_file():
            try:
                pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(self.library.art_dir/name),width,height,True)
                texture=Gdk.Texture.new_for_pixbuf(pixbuf)
                image=Gtk.Picture.new_for_paintable(texture)
                image.set_content_fit(Gtk.ContentFit.CONTAIN)
                image.set_can_shrink(True); image.set_hexpand(False); image.set_vexpand(False); image.set_size_request(width,height)
                frame.append(image); return frame
            except GLib.Error: pass
        icon=Gtk.Image.new_from_icon_name('applications-games-symbolic'); icon.set_pixel_size(48)
        icon.set_hexpand(True); icon.set_vexpand(True); icon.add_css_class('dim-label'); frame.append(icon)
        return frame

    def show_library(self):
        if self.tv_mode:return self.show_tv_library()
        self.rebuilding_desktop=True
        self.game=None; self.original=None; self.fields={};self.launch_fields={};self.description=None;self.play_buttons={}; clear(self.body)
        self.theme.set_selected(['system','light','dark'].index(self.library.data['settings'].get('theme','system'))); self.apply_theme()
        self.heading.set_title('Your game library'); self.heading.set_subtitle('Your games · UMU and Proton'); self.back.set_visible(False)
        panel=box(); margins(panel); self.body.append(panel)
        top=box(False); panel.append(top)
        intro=box(spacing=4); intro.set_hexpand(True)
        intro.append(label('Make your library yours','title-1',xalign=0))
        intro.append(label('Organize your games and play directly with UMU and Proton.','dim-label',xalign=0,wrap=True))
        top.append(intro); top.append(button('Add game',self.add_game,'suggested-action'))
        toolbar=box(False,8); panel.append(toolbar)
        self.filter=Gtk.SearchEntry(placeholder_text='Search your library',hexpand=True)
        self.filter.connect('notify::text',lambda *_:self.render_cards())
        toolbar.append(self.filter)
        self.library_status=label('','dim-label',xalign=0); panel.append(self.library_status)
        self.library_stack=Gtk.Stack(); self.library_stack.set_vexpand(True); self.body.append(self.library_stack)
        empty=Adw.StatusPage(title='A home for your games',description='Find a game to save its metadata and artwork. Set up Play whenever you’re ready.',icon_name='applications-games-symbolic')
        empty_button=button('Add your first game',self.add_game,'suggested-action'); empty_button.set_halign(Gtk.Align.CENTER)
        empty.set_child(empty_button)
        self.library_stack.add_named(empty,'empty')
        self.flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=12,row_spacing=12,homogeneous=True,min_children_per_line=1,max_children_per_line=7)
        self.flow.set_valign(Gtk.Align.START); self.flow.set_halign(Gtk.Align.START); margins(self.flow)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER); scroll.set_child(self.flow);self.desktop_library_scroll=scroll
        self.library_stack.add_named(scroll,'games')
        self.filter.set_text(getattr(self,'desktop_library_query',''))
        self.render_cards()
        self.rebuilding_desktop=False
        self.restore_desktop_card()

    def restore_desktop_card(self):
        tile=getattr(self,'desktop_tiles',{}).get(self.tv_selected_id)
        if tile:tile.set_focusable(True);tile.grab_focus()
        for card in self.desktop_tiles.values():card.set_focusable(True)
        self.update_focus_outline()
        if tile:
            scroll=self.desktop_library_scroll;position=getattr(self,'desktop_library_position',0)
            def allocated(widget,clock):
                if widget.get_width()<=0:return True
                scroll.get_vadjustment().set_value(position);return False
            tile.add_tick_callback(allocated)
        return False

    def render_cards(self):
        clear(self.flow);self.desktop_tiles={}
        games=self.library.games(); query=self.filter.get_text().casefold()
        shown=[g for g in games if query in g['title'].casefold()]
        self.library_status.set_text(f'{len(games)} games')
        self.library_stack.set_visible_child_name('empty' if not games else 'games')
        if not shown and games:
            self.flow.append(label('No games match your search.','dim-label')); return
        for game in sorted(shown,key=lambda g:g['title'].casefold()):
            tile=Gtk.Button();tile.set_focusable(False); tile.add_css_class('card'); tile.add_css_class('game-card')
            self.desktop_tiles[game['id']]=tile
            tile.set_tooltip_text('View '+game['title']); tile.connect('clicked',lambda _,g=game:self.show_game(g))
            content=box(spacing=8)
            content.append(self.picture(game['artwork'].get('portrait'),128,170))
            title=label(game['title'],'heading',width_chars=18,max_width_chars=18,ellipsize=Pango.EllipsizeMode.END,xalign=0); content.append(title)
            completed=sum(done for done,_ in self.progress_items(game))
            content.append(label(f'{completed}/3 complete','caption',xalign=0))
            if not game['executable']: content.append(label('Set up to play','dim-label',xalign=0))
            elif not Path(game['executable']).is_file(): content.append(label('Relink needed','warning',xalign=0))
            wrapper=box(spacing=4); tile.set_child(content); wrapper.append(tile)
            play=button('Play',lambda g=game:self.play_game(g)); wrapper.append(play); self.play_buttons[game['id']]=play
            self.flow.append(wrapper)
        if not getattr(self,'rebuilding_desktop',False):
            for tile in self.desktop_tiles.values():tile.set_focusable(True)

    def add_game(self):
        if self.tv_mode:self.notify('Switch to desktop mode to add games.');return
        self.game=self.library.new_game();self.fields={};self.launch_fields={};self.description=None
        self.find_metadata(new_game=True)

    def entry(self,container,key,title,hint=None):
        wrapper=box(spacing=6); wrapper.append(label(title,'heading',xalign=0))
        entry=Gtk.Entry(text=self.game.get(key,''),hexpand=True)
        entry.set_tooltip_text(title); wrapper.append(entry); self.fields[key]=entry
        if hint: wrapper.append(label(hint,'caption',xalign=0,wrap=True))
        container.append(wrapper); return entry

    def show_game(self,game):
        if not self.tv_mode and self.game is None and hasattr(self,'desktop_library_scroll'):
            self.desktop_library_position=self.desktop_library_scroll.get_vadjustment().get_value()
            self.desktop_library_query=self.filter.get_text()
        self.tv_selected_id=game['id']
        self.game=deepcopy(game);self.original=deepcopy(game);self.fields={};self.launch_fields={};self.description=None;self.play_buttons={};self.last_launch_output=None;self.detail_install_status=None;clear(self.body)
        self.back.set_visible(True);self.heading.set_title(game['title'] or 'New game');self.heading.set_subtitle(self.source_text())
        overlay=Gtk.Overlay();overlay.set_size_request(-1,340)
        hero_name=game['artwork'].get('hero') or game['artwork'].get('landscape')
        hero=Gtk.Picture();hero.set_content_fit(Gtk.ContentFit.COVER);hero.set_can_shrink(True);hero.set_opacity(.28)
        if hero_name and (self.library.art_dir/hero_name).is_file():hero.set_filename(str(self.library.art_dir/hero_name))
        if self.tv_mode:
            self.backdrop.set_opacity(.4)
            self.backdrop.set_filename(str(self.library.art_dir/hero_name)) if hero_name and (self.library.art_dir/hero_name).is_file() else self.backdrop.set_paintable(None)
            hero.set_opacity(0)
        overlay.set_child(hero)
        detail_content=box(spacing=0) if self.tv_mode else self.body
        detail_content.append(overlay)
        top=box(False,18);margins(top);top.set_valign(Gtk.Align.CENTER);overlay.add_overlay(top)
        cover_column=box(spacing=8);cover_column.set_halign(Gtk.Align.START);cover_column.set_hexpand(False);top.append(cover_column)
        self.cover=self.picture(game['artwork'].get('portrait'),150,210);cover_column.append(self.cover)
        play=button('Play',lambda:self.play_game(self.game),'suggested-action');play.set_hexpand(False);play.set_size_request(150,-1);play.get_child().set_wrap(True);play.get_child().set_width_chars(1);play.get_child().set_max_width_chars(14);cover_column.append(play);self.play_buttons[game['id']]=play
        summary=box(spacing=8);summary.set_hexpand(True);top.append(summary)
        if not self.tv_mode and game['artwork'].get('logo'):
            logo=self.picture(game['artwork']['logo'],220,65);logo.set_halign(Gtk.Align.START);summary.append(logo)
        summary.set_valign(Gtk.Align.CENTER);summary.append(label(game['title'] or 'New game','tv-title' if self.tv_mode else 'title-1',wrap=True,xalign=0))
        summary.append(label(self.source_text(),'caption',wrap=True,xalign=0))
        self.progress_labels=[]
        for done,text in self.progress_items(game):
            item=label(('✓ ' if done else '○ ')+text,'caption',xalign=0);summary.append(item);self.progress_labels.append(item)
        actions=box(False,6);actions.set_valign(Gtk.Align.START);actions.set_visible(not self.tv_mode);top.append(actions)
        actions.append(button('Edit Metadata',self.open_metadata,icon='document-edit-symbolic'))
        actions.append(button('Manage Game',self.open_manage,icon='input-gaming-symbolic'))
        details=box();margins(details)
        for key,title in (('release_date','Released'),('developers','Developers'),('publishers','Publishers'),('genres','Genres')):
            if game.get(key):details.append(label(title+': '+game[key],'caption',wrap=True,xalign=0,selectable=not self.tv_mode))
        details.append(label(description_excerpt(game['description']) or 'Add a metadata match or description using the pencil button.','body',wrap=True,xalign=0,selectable=not self.tv_mode,max_width_chars=70,lines=3,ellipsize=Pango.EllipsizeMode.END,halign=Gtk.Align.START))
        if game.get('installation',{}).get('mode')=='installer':
            self.detail_install_status=label('Installation: '+self.installations.status(game)['phase'],'heading',wrap=True,xalign=0);details.append(self.detail_install_status)
        info_button=button('Game Info',lambda:self.show_game_info(self.game));info_button.set_halign(Gtk.Align.START);details.append(info_button)
        self.place_runtime_progress(details)
        self.launch_output=Gtk.TextView(editable=False,cursor_visible=False,wrap_mode=Gtk.WrapMode.WORD_CHAR)
        log_group=Adw.ExpanderRow(title='Operation status and logs');log_group.add_row(self.scrolled(self.launch_output));log_group.set_visible(not self.tv_mode);details.append(log_group)
        if self.tv_mode:
            detail_content.append(details);self.detail_scroll=self.scrolled(detail_content)
        else:self.detail_scroll=self.scrolled(details)
        self.body.append(self.detail_scroll)
        footer=box(False,10);margins(footer,16)
        footer.append(label('B / Esc: Back · X: Focus Play / Stop · LB / RB: Scroll' if self.tv_mode else 'Manage files with the controller button.','dim-label',wrap=True,xalign=0,hexpand=True))
        if not self.tv_mode:footer.append(button('Delete game',self.delete_game,icon='user-trash-symbolic'))

        self.body.append(footer);self.refresh_launch_state()
        if self.tv_mode:
            self.restrict_tv_focus(self.body);GLib.idle_add(lambda:(play.grab_focus(),False)[-1])

    def place_runtime_progress(self,container):
        parent=self.runtime_progress.get_parent()
        if parent:parent.remove(self.runtime_progress)
        container.append(self.runtime_progress)

    def show_game_info(self,game):
        dialog=Adw.Window(title='Game Info',transient_for=self,modal=True,default_width=720,default_height=560)
        content=box();margins(content);dialog.set_content(content)
        content.append(label(game['title'],'title-1',wrap=True,xalign=0))
        description=label(game.get('description') or 'No description available.','body',wrap=True,xalign=0,selectable=False)
        scroll=self.scrolled(description);scroll.set_vexpand(True);content.append(scroll);dialog.info_scroll=scroll
        close=button('Close',dialog.close);content.append(close);dialog.present();close.grab_focus()
        if self.tv_mode:self.restrict_tv_focus(content)

    def editor_window(self,title,kind):
        if self.tv_mode:self.notify('Switch to desktop mode to edit or set up games.');return None
        if self.editor:self.editor.present();return None
        self.original=deepcopy(self.game);self.game=deepcopy(self.game);self.fields={};self.launch_fields={};self.description=None
        self.editor_kind=kind
        dialog=Gtk.Window(title=title,transient_for=self,modal=True,default_width=780,default_height=700);self.editor=dialog
        root=box();margins(root,16);dialog.set_child(root)
        content=box();root.append(self.scrolled(content));footer=box(False);root.append(footer)
        footer.append(button('Cancel',self.cancel_editor));footer.append(button('Save',self.save_editor,'suggested-action'))
        dialog.connect('close-request',lambda _: (self.cancel_editor(),True)[-1])
        return dialog,content,footer

    def cancel_editor(self):
        if not self.editor:return
        dialog=self.editor;saved=deepcopy(self.original);self.editor=None;self.editor_kind=None;dialog.destroy()
        if any(g['id']==saved['id'] for g in self.library.games()):self.show_game(saved)
        else:self.show_library()

    def save_editor(self):
        try:
            candidate=self.collect()
            if self.editor_kind=='manage' and self.launcher.active():raise ValueError('Finish the active operation before changing game files.')
            if self.editor_kind=='manage' and candidate.get('installation',{}).get('mode')=='installer' and candidate['executable']!=self.original['executable']:candidate['installation']['confirmed']=False
            self.library.save(candidate);dialog=self.editor;self.editor=None;self.editor_kind=None
            if dialog:dialog.destroy()
            self.show_game(candidate);self.notify('Saved locally.')
        except Exception as error:self.error(error)

    def open_metadata(self):
        result=self.editor_window('Edit Metadata','metadata')
        if not result:return
        dialog,content,_=result
        content.append(button('Find metadata by name or provider ID',self.find_metadata))
        for key,title in (('title','Title'),('release_date','Release date'),('developers','Developers'),('publishers','Publishers'),('genres','Genres')):self.entry(content,key,title)
        content.append(label('Description','heading',xalign=0));self.description=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR);self.description.get_buffer().set_text(self.game['description'])
        scroll=Gtk.ScrolledWindow(min_content_height=150);scroll.set_child(self.description);content.append(scroll)
        self.art_page=box();content.append(self.art_page);self.render_artwork();dialog.present()

    def open_manage(self,new_game=False):
        result=self.editor_window('Manage Game','manage')
        if not result:return
        dialog,content,footer=result
        self.manage_new=new_game
        if new_game:self.entry(content,'title','Game name','You can search public metadata after saving this entry.')
        mode=self.game.get('installation',{}).get('mode','installed')
        self.install_retry_requested=False
        row=box(False);content.append(row)
        row.append(label('I already have installed the game','heading',xalign=0,hexpand=True))
        self.already_installed=Gtk.Switch(active=mode!='installer',valign=Gtk.Align.CENTER)
        self.already_installed.set_tooltip_text('Skip installation and select the installed game executable')
        self.already_installed.update_property([Gtk.AccessibleProperty.LABEL],['I already have installed the game'])
        row.append(self.already_installed)
        tabs=box(False);content.append(tabs)
        self.install_tab=button('1 · Install',lambda:self.stage_stack.set_visible_child_name('install'))
        self.game_tab=button('2 · Game setup',lambda:self.stage_stack.set_visible_child_name('game'))
        tabs.append(self.install_tab);tabs.append(self.game_tab)
        self.stage_stack=Gtk.Stack();self.stage_stack.set_vexpand(True);content.append(self.stage_stack)
        self.installer_panel=box();self.stage_stack.add_named(self.installer_panel,'install')
        self.installer_entry=Gtk.Entry(text=self.game.get('installation',{}).get('installer',''));self.installer_entry.set_tooltip_text('Installer executable')
        self.installer_panel.append(label('Step 1 · Install the game','title-2',xalign=0))
        self.installer_panel.append(label('Installer executable','heading',xalign=0));self.installer_panel.append(self.installer_entry)
        self.installer_panel.append(button('Choose setup.exe',self.pick_installer))
        self.install_status=label('','heading',wrap=True,xalign=0);self.installer_panel.append(self.install_status)
        self.installer_panel.append(label('Setup runs in a dedicated prefix. Its exit does not prove the game is ready. Choose and confirm the game executable afterwards. Cancellation keeps installed files.','caption',wrap=True,xalign=0))
        self.install_button=button('Launch Installer',self.run_installer);self.installer_panel.append(self.install_button)
        self.install_cancel=button('Cancel installation',lambda:self.confirm('Cancel installation?','Only this installer’s owned processes will stop. Installed files and prefix are kept; you can retry or select an executable later.','Cancel installation',lambda:self.stop_game(self.game['id']),True));self.installer_panel.append(self.install_cancel)
        self.manage_logs=Gtk.TextView(editable=False,cursor_visible=False,wrap_mode=Gtk.WrapMode.WORD_CHAR);logs=Gtk.ScrolledWindow(min_content_height=130);logs.set_child(self.manage_logs);self.installer_panel.append(logs)
        self.executable_panel=box();self.stage_stack.add_named(self.executable_panel,'game')
        self.executable_stage=label('Game executable','title-2',xalign=0);self.executable_panel.append(self.executable_stage)
        self.executable_panel.append(label('Game executable','heading',wrap=True,xalign=0))
        self.entry(self.executable_panel,'executable','Game executable','Select the installed game executable; it runs through UMU.');self.executable_panel.append(button('Choose game executable',self.pick_executable))
        self.entry(self.executable_panel,'working_dir','Working directory','Blank uses the executable’s folder.')
        self.executable_panel.append(button('Choose working directory',lambda:self.choose_file('Working directory',lambda p:self.fields['working_dir'].set_text(str(p)),folder=True)))
        self.build_game_arguments(self.executable_panel)
        self.confirm_executable_button=button('Confirm installed game executable',self.confirm_installed);self.executable_panel.append(self.confirm_executable_button)
        self.retry_stage_button=button('Return to installation / retry',self.return_to_installation);self.executable_panel.append(self.retry_stage_button)
        self.already_installed.connect('notify::active',lambda *_:self.update_install_stage())
        advanced=Adw.ExpanderRow(title='Advanced launch settings',subtitle='Optional overrides. Working defaults are applied automatically.');content.append(advanced);self.advanced=advanced
        advanced_content=box();margins(advanced_content,12);advanced.add_row(advanced_content);self.build_advanced(advanced_content)
        advanced_content.append(button('Reset to defaults',self.reset_launch_defaults))
        footer.append(button('Find metadata',self.find_metadata))
        dialog.present();self.refresh_launch_state()

    def return_to_installation(self):
        self.install_retry_requested=True
        self.update_install_stage()

    def update_install_stage(self):
        installer=not self.already_installed.get_active()
        config=self.game.get('installation',{})
        # Completed, failed and cancelled attempts can leave files for recovery.
        selecting=installer and bool(config.get('session_id')) and not self.launcher.active() and not self.install_retry_requested
        game_stage=not installer or selecting
        self.install_tab.set_sensitive(not game_stage)
        self.game_tab.set_sensitive(game_stage)
        for tab,enabled in ((self.install_tab,not game_stage),(self.game_tab,game_stage)):
            if enabled:tab.add_css_class('suggested-action')
            else:tab.remove_css_class('suggested-action')
        self.stage_stack.set_visible_child_name('game' if game_stage else 'install')
        self.executable_stage.set_text('Step 2 · Select the installed game executable' if installer else 'Select the installed game executable')
        self.confirm_executable_button.set_visible(installer and selecting)
        self.retry_stage_button.set_visible(installer and selecting)

    def reset_launch_defaults(self):
        for field in self.launch_fields.values():field.set_text('')
        self.proton_choice.set_selected(0)
        self.game['launch']={}
        self.notify('Defaults selected in this draft. Installer prefix and runner continuity are preserved.')

    def pick_installer(self):
        def selected(path):
            self.installer_entry.set_text(str(path))
            if 'title' in self.fields and not self.fields['title'].get_text():self.fields['title'].set_text(path.parent.name or 'New game')
        self.choose_file('Choose installer',selected)

    def run_installer(self):
        try:
            if self.demo:raise ValueError('Installer execution is disabled in the demo.')
            candidate=self.collect();setup=candidate.get('installation',{}).get('installer','')
            def start():
                try:
                    saved=self.installations.start(candidate);self.game=saved;self.original=deepcopy(saved);self.installer_entry.set_text(saved['installation']['installer']);self.refresh_launch_state()
                    self.already_installed.set_sensitive(False);self.install_retry_requested=False;self.notify('Installer started. Installed files will be kept if cancelled.')
                except Exception as error:self.error(error)
            self.confirm('Run this installer?',setup+'\n\nOnly run a trusted installer. You control its license agreements and destination. It uses this game’s dedicated prefix and blocks other launches.','Run installer',start)
        except Exception as error:self.error(error)

    def confirm_installed(self):
        try:
            saved=self.installations.confirm(self.collect());dialog=self.editor;self.editor=None;self.editor_kind=None
            if dialog:dialog.destroy()
            self.show_game(saved);self.notify('Executable confirmed. Play will use this game executable, not setup.')
        except Exception as error:self.error(error)

    def progress_items(self,game):
        metadata=bool(game.get('metadata_source') or game.get('metadata_app_id') or (game['title'].strip() and game['description'].strip()))
        executable=bool(game['executable'] and Path(game['executable']).is_file())
        try: build_command(game,self.library.root); ready=game.get('installation',{}).get('mode')!='installer' or game['installation'].get('confirmed',False)
        except ValueError: ready=False
        return zip((metadata,executable,ready),('Game metadata added','Game executable connected','Direct Play configured'))

    def source_text(self):
        source=self.game.get('metadata_source',{})
        if source and source['provider']=='igdb': return 'IGDB metadata ID: '+str(source['id'])
        if source and source['provider']=='steam':return 'Steam catalogue metadata ID: '+str(source['id'])
        return 'Saved metadata · public catalogue and optional IGDB lookup' if self.game['description'] else 'No metadata match yet · you can enter details manually'

    @staticmethod
    def scrolled(child):
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,vscrollbar_policy=Gtk.PolicyType.AUTOMATIC); scroll.set_vexpand(True); scroll.set_child(child); return scroll

    def collect(self):
        game=deepcopy(self.game)
        for key,widget in self.fields.items():game[key]=widget.get_text()
        if self.editor_kind=='manage':
            game['launch']=dict(game.get('launch',{}))
            for key,widget in self.launch_fields.items():game['launch'][key]=widget.get_text()
            buffer=self.launch_args.get_buffer();text=buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),False)
            game['launch']['arguments']=text.splitlines() if text else []
            config=dict(game.get('installation',{}));config['mode']='installed' if self.already_installed.get_active() else 'installer';config['installer']=self.installer_entry.get_text();game['installation']=config
        if self.description is not None:
            buf=self.description.get_buffer();game['description']=buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False)
        return game

    def dirty(self):return bool(self.editor and self.game is not None and self.collect()!=self.original)

    def go_back(self):self.show_library()

    def close_requested(self,*_):
        if self.exiting:return False
        app=self.get_application();tray=getattr(app,'tray',None)
        if close_action(bool(tray and tray.available))=='hide':self.set_visible(False)
        else:
            self.notify('No tray host is available. Launcher is minimized instead; reopen it from the applications menu. Use Exit to quit.')
            self.minimize()
        return True

    def explicit_exit(self):
        self.present()  # Tray Exit must make its warning reachable while hidden.
        if self.busy or self.proton_manager.busy():
            self.error(ValueError('Finish or cancel metadata/runner work before exiting.'));return
        current=self.launcher.current();active=self.launcher.active()
        body='Exit the background launcher?'
        if active:body='An installer or game is active: '+current.get('title','current operation')+'. It will CONTINUE running under its supervisor after Exit. Reopen the launcher to track or stop it. Files, saves and prefixes are kept.'
        if self.dirty():body+=' Unsaved dialog edits will be discarded.'
        def exit_app():
            self.exiting=True;self.pool.shutdown(wait=False);app=self.get_application()
            self.controller.close()
            if getattr(app,'tray',None):app.tray.close()
            app.quit()
        self.confirm('Exit Launcher?',body,'Exit; keep operation running' if active else 'Exit',exit_app,active or self.dirty())

    def pick_executable(self):
        def selected(path):
            self.fields['executable'].set_text(str(path))
            if not self.fields['working_dir'].get_text(): self.fields['working_dir'].set_text(str(path.parent))
            if 'title' in self.fields and not self.fields['title'].get_text(): self.fields['title'].set_text(path.stem)
        prefix=self.game.get('installation',{}).get('prefix')
        self.choose_file('Choose game executable',selected,start_folder=Path(prefix)/'drive_c' if prefix else None)

    def render_artwork(self):
        clear(self.art_page)
        self.art_page.append(label('Your artwork collection','title-2',xalign=0))
        self.art_page.append(button('Browse community artwork',self.find_sgdb))
        self.art_page.append(label('Choose local PNG or JPEG images or browse community artwork.','dim-label',wrap=True,xalign=0))
        flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,min_children_per_line=1,max_children_per_line=3,column_spacing=16,row_spacing=16,homogeneous=True)
        for kind in ART_KINDS:
            card=box(spacing=8); margins(card,12); card.add_css_class('card')
            card.append(label(kind.capitalize(),'heading',xalign=0))
            card.append(self.picture(self.game['artwork'].get(kind),200,145))
            card.append(button('Choose image',lambda k=kind:self.choose_art(k)))
            flow.append(card)
        self.art_page.append(flow)

    def choose_art(self,kind):
        def selected(path):
            if path.stat().st_size>20*1024*1024: raise ValueError('Choose an image smaller than 20 MB.')
            content=path.read_bytes()
            image_extension(content)
            Gdk.Texture.new_from_bytes(GLib.Bytes.new(content))
            self.game['artwork'][kind]=self.library.add_image(content); self.render_artwork()
        self.choose_file('Choose '+kind+' image',selected)

    def find_metadata(self,new_game=False):
        dialog=Gtk.Window(title='Find game metadata',transient_for=self.editor or self,modal=True,destroy_with_parent=True,default_width=620,default_height=530)
        content=box(); margins(content); dialog.set_child(content)
        content.append(label('Find the right game','title-1',xalign=0))
        content.append(label('Search by title or provider ID. Select a match to save metadata and available artwork.' if new_game else 'Choose a provider, then search by title or its game ID. Selecting a match fills your local draft.','dim-label',wrap=True,xalign=0))
        row=box(False); content.append(row)
        provider=Gtk.DropDown.new_from_strings(['Steam catalogue (no credentials)','IGDB']);provider.set_tooltip_text('Metadata provider');row.append(provider);self.metadata_provider=provider
        query=Gtk.Entry(placeholder_text='Game name or provider ID',hexpand=True,text=self.fields['title'].get_text() if 'title' in self.fields else self.game['title']); row.append(query)
        results=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE); results.add_css_class('boxed-list')
        scroll=self.scrolled(results); scroll.set_vexpand(True)
        status=label('','dim-label',wrap=True,xalign=0)
        chosen=[False]
        def cancel():
            dialog.destroy()
            if new_game and not chosen[0]: self.show_library()
        def selected(item,selected_provider):
            chosen[0]=True
            selected_id=self.game['id'];selected_editor=self.editor
            dialog.destroy()
            def loaded(result):
                if not self.game or self.game['id']!=selected_id or self.editor is not selected_editor:return
                info,art,missing=result
                self.game=self.collect();self.game.update(info)
                self.game['metadata_source']={'provider':selected_provider,'id':item['id']}
                if selected_provider=='igdb':self.game['metadata_app_id']=None
                for kind,data in art.items():
                    try:
                        image_extension(data);Gdk.Texture.new_from_bytes(GLib.Bytes.new(data));self.game['artwork'][kind]=self.library.add_image(data)
                    except (ValueError,GLib.Error):missing.append(kind)
                for key,field in self.fields.items():
                    if key in info:field.set_text(info[key])
                if self.description is not None:self.description.get_buffer().set_text(self.game['description'])
                if self.editor_kind=='metadata':self.render_artwork()
                if new_game:
                    self.library.save(self.game);self.show_game(self.game)
                    self.notify('Game added. Set up Play later through Manage Game.'+(' Missing artwork: '+', '.join(missing)+'.' if missing else ''))
                else:self.notify('Metadata loaded into draft. Save to keep it.'+(' Missing artwork: '+', '.join(missing)+'.' if missing else ''))
            self.async_job('Fetching metadata and artwork…',lambda:(self.igdb.fetch(item['id']) if selected_provider=='igdb' else metadata.fetch_game(item['id'])),loaded)
        def run_search():
            if self.busy: return
            search_button.set_sensitive(False); query.set_sensitive(False); clear(results); status.set_text('Searching provider…')
            def loaded(items):
                search_button.set_sensitive(True); query.set_sensitive(True)
                status.set_text(f'{len(items)} matches. Select one to preview its metadata.' if items else 'No matching games. Try another title or ID.')
                for item in items:
                    action=Adw.ActionRow(title=item['name'],subtitle='Provider ID '+str(item['id']))
                    choose=button('Select',lambda i=item,p=('igdb' if provider_id==1 else 'steam'):selected(i,p)); choose.set_valign(Gtk.Align.CENTER)
                    action.set_use_markup(False); action.add_suffix(choose); action.set_activatable_widget(choose); results.append(action)
            # Restore dialog controls on failures as well as successes.
            def work():
                try: return self.igdb.search(query_text) if provider_id==1 else metadata.search(query_text)
                finally: GLib.idle_add(lambda:(search_button.set_sensitive(True),query.set_sensitive(True),False)[-1])
            query_text=query.get_text();provider_id=provider.get_selected()
            self.async_job('Searching game metadata…',work,loaded)
        search_button=button('Search',run_search,'suggested-action'); row.append(search_button)
        query.connect('activate',lambda _:run_search())
        content.append(status); content.append(scroll)
        bottom=box(False)
        bottom.append(button('Cancel',cancel))
        if new_game:
            def manual():
                chosen[0]=True;dialog.destroy();self.open_metadata()
            bottom.append(button('Enter details manually',manual))
        content.append(bottom)
        dialog.connect('close-request',lambda _:(self.show_library() if new_game and not chosen[0] else None,False)[-1])
        dialog.present(); query.grab_focus()

    def open_settings(self):
        if self.tv_mode:self.notify('Switch to desktop mode to manage settings.');return
        dialog=Adw.PreferencesWindow(title='Settings',transient_for=self,modal=True,default_width=660,default_height=740)
        page=Adw.PreferencesPage(title='General',icon_name='preferences-system-symbolic'); dialog.add(page)
        modes=Adw.PreferencesGroup(title='Display mode',description='Default mode applies on the next app start. Enter fullscreen from the mode button; leave through fullscreen options or the tray.');page.add(modes)
        mode_row=Adw.ActionRow(title='Default launch mode');self.default_mode_choice=Gtk.DropDown.new_from_strings(['Desktop','Fullscreen / TV']);self.default_mode_choice.set_selected(1 if self.library.data['settings'].get('default_display_mode')=='fullscreen' else 0);mode_row.add_suffix(self.default_mode_choice);modes.add(mode_row)
        self.default_mode_choice.connect('notify::selected',lambda choice,_:self.library.set_default_display_mode('fullscreen' if choice.get_selected()==1 else 'desktop'))
        page.add(Adw.PreferencesGroup(title='Game Library Launcher '+__version__,description='Standalone UMU/Proton game and installer library.'))
        appearance=Adw.PreferencesGroup(title='Appearance',description='Choose how the app looks.'); page.add(appearance)
        theme_row=Adw.ActionRow(title='Theme')
        theme=Gtk.DropDown.new_from_strings(['Follow system','Light','Dark']); theme.set_valign(Gtk.Align.CENTER)
        theme.set_selected(self.theme.get_selected())
        theme.connect('notify::selected',lambda dropdown,_:self.theme.set_selected(dropdown.get_selected()))
        theme_row.add_suffix(theme); appearance.add(theme_row)
        backup=Adw.PreferencesGroup(title='Backup and restore',description='Portable metadata, artwork and appearance. Game files, saves and provider credentials are not included.'); page.add(backup)
        def leave_then(callback): dialog.close(); callback()
        for title,subtitle,action,callback in (
            ('Export library','Create a ZIP backup of the saved library.','Export ZIP',self.export_backup),
            ('Import library','Preview new entries and conflicts before restoring.','Import ZIP',self.import_backup)):
            row=Adw.ActionRow(title=title,subtitle=subtitle)
            control=button(action,lambda c=callback:leave_then(c)); control.set_valign(Gtk.Align.CENTER)
            row.add_suffix(control); backup.add(row)
        self.build_proton_manager_tab(dialog)
        providers_page=Adw.PreferencesPage(title='Providers',icon_name='network-server-symbolic'); dialog.add(providers_page)
        group=Adw.PreferencesGroup(title='Metadata and artwork',description='Public Steam catalogue supplies default metadata without credentials; IGDB is optional; SGDB supplies community artwork. Manual entry and local images need no account.'); providers_page.add(group)
        settings=self.credentials.load(); fields={}
        for key,title in (('igdb_client_id','IGDB / Twitch client ID'),('igdb_client_secret','IGDB / Twitch client secret'),('steamgriddb_key','Community artwork (SGDB) API key')):
            entry=Adw.PasswordEntryRow(title=title) if key!='igdb_client_id' else Adw.EntryRow(title=title)
            entry.set_text(settings[key]); group.add(entry); fields[key]=entry
        info=Adw.PreferencesGroup(description='Credentials are saved in a private local file readable only by your user, outside library ZIP backups. They are not encrypted. Clear a field and save to remove it.'); providers_page.add(info)
        links=box(False)
        links.append(Gtk.LinkButton.new_with_label('https://api-docs.igdb.com/#getting-started','IGDB setup'))
        links.append(Gtk.LinkButton.new_with_label('https://www.steamgriddb.com/profile/preferences/api','Get artwork API key'))
        info.add(links)
        def save():
            try:
                self.credentials.save({k:v.get_text() for k,v in fields.items()})
                self.igdb=IGDB(self.credentials); self.sgdb=SteamGridDB(self.credentials)
                self.notify('Provider settings saved privately.')
            except Exception as e: self.error(e)
        info.add(button('Save provider settings',save,'suggested-action'))
        dialog.present()

    def build_proton_manager_tab(self,dialog):
        page=Adw.PreferencesPage(title='Proton Manager',icon_name='application-x-executable-symbolic');dialog.add(page);self.proton_settings_page=page
        defaults_group=Adw.PreferencesGroup(title='Installed runners',description='Use an installed runner or let UMU obtain a current release. Custom paths are available in Manage Game → Advanced launch settings.');page.add(defaults_group)
        installed=box();defaults_group.add(installed)
        def render_installed():
            clear(installed)
            paths=self.proton_manager.installed();choices=['UMU-Latest','GE-Latest',*paths]
            selected=self.library.data['settings'].get('default_proton') or defaults({'id':'default'},self.library.root)['proton']
            if selected not in choices:choices.append(selected)
            row=box(False);row.append(label('Default Proton','heading',xalign=0));dropdown=Gtk.DropDown.new_from_strings([Path(c).name if c.startswith('/') else c for c in choices]);dropdown.set_hexpand(True);dropdown.set_selected(choices.index(selected));row.append(dropdown);installed.append(row)
            def changed(w,_):
                try:self.library.set_default_proton(choices[w.get_selected()])
                except Exception as error:self.error(error)
            dropdown.connect('notify::selected',changed)
            for path in paths:installed.append(label(Path(path).name+' · '+self.proton_manager.arch+' · Installed','caption',xalign=0))
            if not paths:installed.append(label('No installed runners discovered. Choose an available release below.','caption',wrap=True,xalign=0))
        render_installed()
        available=Adw.PreferencesGroup(title='Available upstream releases',description='GE-Proton and UMU-Proton, matched to this host’s architecture. Load older pages to browse supported historical releases. UMU resolves the required runtime at launch.');page.add(available)
        toolbar=box(False);family=Gtk.DropDown.new_from_strings(['GE-Proton','UMU-Proton']);toolbar.append(family);available.add(toolbar)
        message=label('Choose Refresh to load official releases.','caption',wrap=True,xalign=0);available.add(message)
        rows=box();available.add(rows);seen={};pages=[0];loading=[False];controls=[]
        def load(older=False):
            if loading[0]:return
            if not older:pages[0]=0;seen.clear();controls.clear();clear(rows)
            pages[0]+=1;name=['GE-Proton','UMU-Proton'][family.get_selected()];loading[0]=True;message.set_text('Loading '+name+' releases…')
            def result(items):
                loading[0]=False;message.set_text(f'{len(seen)+len(items)} releases shown · '+self.proton_manager.arch+(' · no more supported releases on this page' if not items else ''))
                for release in items:
                    if release['name'] in seen:continue
                    seen[release['name']]=release
                    card=box();card.add_css_class('card');margins(card,12)
                    card.append(label(release['version']+' · '+release['architecture'],'heading',xalign=0))
                    card.append(label('Source: '+release['source'],'caption',wrap=True,xalign=0))
                    state=label('Available','caption',xalign=0);card.append(state)
                    row=box(False);card.append(row)
                    def install(item=release):
                        try:self.proton_manager.install(item,active_runner=self.launcher.current().get('proton'))
                        except Exception as error:self.error(error)
                    action=button('Install',install);row.append(action)
                    cancel=button('Cancel',lambda item=release:self.proton_manager.cancel(item));row.append(cancel)
                    controls.append((release,state,action,cancel));rows.append(card)
            def work():
                try:return self.proton_manager.releases(name,pages[0],refresh=not older)
                finally:GLib.idle_add(lambda:(loading.__setitem__(0,False),False)[-1])
            self.async_job('Loading official runner releases…',work,result)
        toolbar.append(button('Refresh',load));toolbar.append(button('Load older versions',lambda:load(True)))
        toolbar.append(button('Refresh installed',render_installed))
        family.connect('notify::selected',lambda *_:load())
        remembered={}
        def update():
            if not dialog.get_visible():return False
            refresh=False
            for release,state,action,cancel in controls:
                status=self.proton_manager.status(release);phase=status['state'];active=phase in ('Downloading','Verifying','Installing')
                state.set_text(phase+(f" · {int(status['progress']*100)}%" if active else '')+(' · '+status['error'] if status['error'] else ''))
                action.set_label('Installed' if phase=='Installed' else ('Retry' if phase in ('Failed','Cancelled') else 'Install'));action.set_sensitive(not active and phase!='Installed');cancel.set_sensitive(active)
                if phase=='Installed' and remembered.get(release['name'])!='Installed':refresh=True
                remembered[release['name']]=phase
            if refresh:render_installed()
            return True
        dialog.connect('map',lambda *_:GLib.timeout_add(300,update))

    def find_sgdb(self):
        dialog=Gtk.Window(title='Community artwork (SGDB) artwork',transient_for=self.editor or self,modal=True,destroy_with_parent=True,default_width=650,default_height=520)
        content=box(); margins(content); dialog.set_child(content)
        content.append(label('Find artwork for your game','title-1',xalign=0))
        row=box(False); query=Gtk.Entry(text=self.fields['title'].get_text(),placeholder_text='Game name',hexpand=True); row.append(query)
        status=label('Requires your SGDB API key in Settings → Providers.','dim-label',wrap=True,xalign=0)
        results=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE); results.add_css_class('boxed-list')
        def chosen(item): dialog.destroy(); self.art_gallery(item)
        def do_search():
            query_text=query.get_text()
            if not query_text.strip(): return
            clear(results); status.set_text('Searching…')
            def loaded(items):
                status.set_text(f'{len(items)} matching games')
                for item in items:
                    action=Adw.ActionRow(title=item['name'],subtitle='Community artwork (SGDB) ID '+str(item['id']))
                    select=button('Choose',lambda i=item:chosen(i)); select.set_valign(Gtk.Align.CENTER)
                    action.set_use_markup(False); action.add_suffix(select); results.append(action)
            self.async_job('Searching Community artwork (SGDB)…',lambda:self.sgdb.search(query_text),loaded)
        row.append(button('Search',do_search,'suggested-action')); query.connect('activate',lambda _:do_search())
        content.append(row); content.append(status)
        scroll=self.scrolled(results); scroll.set_vexpand(True); content.append(scroll)
        content.append(button('Close',dialog.destroy)); dialog.present()

    def art_gallery(self,item):
        dialog=Gtk.Window(title='Choose Community artwork (SGDB) artwork',transient_for=self.editor or self,modal=True,destroy_with_parent=True,default_width=800,default_height=650)
        content=box(); margins(content); dialog.set_child(content)
        content.append(label(item['name'],'title-1',xalign=0))
        kind=Gtk.DropDown.new_from_strings([k.capitalize() for k in ART_KINDS]); content.append(kind)
        status=label('Select an artwork category and load its options.','dim-label',wrap=True,xalign=0); content.append(status)
        flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,min_children_per_line=1,max_children_per_line=3,column_spacing=12,row_spacing=12,homogeneous=True)
        scroll=self.scrolled(flow); scroll.set_vexpand(True)
        selected_id=self.game['id'];selected_editor=self.editor
        def choose(art,selected_kind):
            def work(): return metadata.request(art['url'],20*1024*1024)
            def done(data):
                if not self.game or self.game['id']!=selected_id or self.editor is not selected_editor:return
                image_extension(data)
                Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
                self.game['artwork'][selected_kind]=self.library.add_image(data)
                self.render_artwork(); status.set_text(selected_kind.capitalize()+' selected. Save your draft to keep it.')
                self.notify(selected_kind.capitalize()+' artwork added to draft.')
            self.async_job('Downloading selected artwork…',work,done)
        def load():
            selected_kind=ART_KINDS[kind.get_selected()]; clear(flow); status.set_text('Loading artwork previews…')
            def work():
                items=self.sgdb.artwork(item['id'],selected_kind)
                def thumbnail(art):
                    try: return art,metadata.request(art['thumb'],5*1024*1024)
                    except Exception: return art,None
                with ThreadPoolExecutor(max_workers=4) as pool: return list(pool.map(thumbnail,items))
            def loaded(items):
                status.set_text(f'{len(items)} options · select artwork to add it to your draft' if items else 'No static PNG/JPEG artwork in this category.')
                for art,data in items:
                    tile=box(spacing=8); margins(tile,10); tile.add_css_class('card')
                    try:
                        if data: image_extension(data)
                        texture=Gdk.Texture.new_from_bytes(GLib.Bytes.new(data)) if data else None
                        if texture:
                            picture=Gtk.Picture.new_for_paintable(texture); picture.set_size_request(170,145); picture.set_content_fit(Gtk.ContentFit.CONTAIN); tile.append(picture)
                    except (GLib.Error,ValueError): tile.append(label('Preview unavailable'))
                    tile.append(label(art['author'],'caption',wrap=True))
                    tile.append(label(str(art['width'])+' × '+str(art['height']),'caption'))
                    tile.append(button('Use artwork',lambda a=art,k=selected_kind:choose(a,k)))
                    flow.append(tile)
            self.async_job('Loading Community artwork (SGDB) artwork…',work,loaded)
        content.append(button('Load artwork',load,'suggested-action')); content.append(scroll)
        content.append(button('Done',dialog.destroy)); dialog.present(); load()

    def delete_game(self):
        game_id=self.game['id']; title=self.game['title']
        if self.launcher.active() and self.launcher.current().get('game_id')==game_id:
            self.error(ValueError('Finish or stop this game before deleting its library entry.'));return
        def remove():
            try:
                self.library.delete(game_id); self.show_library()
                self.notify('Removed from this library. Game files and prefixes were kept.')
            except Exception as e: self.error(e)
        self.confirm('Delete '+title+'?', 'This removes the local metadata entry. Your game files, saves and prefixes remain untouched. Export a backup first if you want to restore the metadata later.', 'Delete from library', remove, True)

    def build_advanced(self,page):
        settings=self.game.get('launch',{})
        for key,title,hint in (('runner','UMU executable','Blank discovers umu-run on your PATH.'),('proton','Proton folder or release','Blank uses your default. You can also use UMU-Latest or GE-Latest.'),('prefix','Dedicated prefix folder','Blank creates a per-game prefix in app data. Existing unrelated prefixes are preserved.')):
            page.append(label(title,'heading',xalign=0));entry=Gtk.Entry(text=settings.get(key,''));self.launch_fields[key]=entry;page.append(entry)
            page.append(label(hint,'caption',wrap=True,xalign=0))
            if key!='proton':page.append(button('Choose '+title.lower(),lambda k=key:self.choose_file('Choose '+k,lambda p:self.launch_fields[k].set_text(str(p)),folder=k=='prefix')))
            else:
                choices=['Use app default','UMU-Latest','GE-Latest',*self.proton_manager.installed()]
                current=settings.get('proton','')
                if current and current not in choices:choices.append(current)
                select=Gtk.DropDown.new_from_strings([Path(c).name if c.startswith('/') else c for c in choices]);select.set_selected(choices.index(current) if current else 0);select.set_tooltip_text('Installed Proton or automatic release')
                self.proton_choice=select
                select.connect('notify::selected',lambda w,_:self.launch_fields['proton'].set_text('' if w.get_selected()==0 else choices[w.get_selected()]))
                page.append(select);page.append(button('Choose custom Proton folder',lambda:self.choose_file('Choose Proton',lambda p:self.launch_fields['proton'].set_text(str(p)),folder=True)))

    def build_game_arguments(self,page):
        settings=self.game.get('launch',{})
        page.append(label('Game launch arguments — one argument per line','heading',xalign=0))
        import shlex
        try:arguments=settings['arguments'] if 'arguments' in settings else shlex.split(self.game.get('arguments',''))
        except ValueError:arguments=[self.game.get('arguments','')]
        self.launch_args=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR);self.launch_args.get_buffer().set_text('\n'.join(arguments))
        scroll=Gtk.ScrolledWindow(min_content_height=90);scroll.set_child(self.launch_args);page.append(scroll)
        page.append(label('Spaces within one line remain part of that argument. Shell expressions are never evaluated.','caption',wrap=True,xalign=0))
    def play_game(self,game):
        try:
            current=self.launcher.current()
            if self.launcher.active():
                if current.get('game_id')==game['id']:
                    self.confirm('Stop '+current.get('title','game')+'?','This stops only processes owned by this launch. Unsaved in-game progress may be lost.','Stop game',lambda:self.stop_game(game['id']),True)
                    return
                raise RuntimeError(current.get('title','Another game')+' is active. Stop or finish it first.')
            if not game['executable'] or (game.get('installation',{}).get('mode')=='installer' and not game['installation'].get('confirmed')):
                if self.tv_mode:self.notify('Set up this game in desktop mode before playing.');return
                self.show_game(game);self.open_manage();return
            if self.demo:raise ValueError('Play is disabled in the demo. Synthetic game files are inert.')
            settings=defaults(game,self.library.root);settings['proton']=game.get('launch',{}).get('proton') or game.get('installation',{}).get('proton') or self.library.data['settings'].get('default_proton') or settings['proton']
            game=deepcopy(game);game['launch']=settings
            build_command(game,self.library.root)
            if self.editor:raise ValueError('Save or cancel your dialog before playing.')
            def launch():
                try:self.launcher.start(game);self.refresh_launch_state()
                except Exception as error:self.error(error)
            self.confirm('Play '+game['title']+'?', '', 'Play',launch)
        except Exception as error:self.error(error)

    def stop_game(self,game_id):
        try:self.launcher.stop(game_id);self.refresh_launch_state()
        except Exception as error:self.error(error)

    def refresh_launch_state(self):
        self.update_focus_outline()
        current=self.launcher.current();active=self.launcher.active();active_id=current.get('game_id')
        selected_id=self.game['id'] if self.game else self.tv_selected_id if self.tv_mode and self.tv_section=='games' else None
        preparing_runtime=active and active_id==selected_id and current.get('state') in ('Preparing','Downloading runtime')
        if self.tv_mode and self.game is None and hasattr(self,'tv_launch_status'):self.tv_launch_status.set_text(current.get('state','') if active and active_id==selected_id else '')
        self.runtime_progress.set_visible(preparing_runtime)
        if preparing_runtime:
            self.runtime_spinner.start();info=preparation_progress(current)
            amount=(f" · {info['bytes']/1048576:.1f} MiB downloaded" if info['bytes'] is not None else ' · Waiting for UMU progress')
            self.runtime_label.set_text(info['stage']+amount)
        else:self.runtime_spinner.stop()
        for game_id,control in self.play_buttons.items():
            own=active and active_id==game_id;stopping=own and current.get('state')=='Stopping'
            preparing=own and current.get('state')=='Preparing' and not current.get('supervisor_pid')
            installer=own and current.get('operation')=='installer'
            entry=next((g for g in self.library.games() if g['id']==game_id),self.game or {})
            configured=bool(entry.get('executable')) and (entry.get('installation',{}).get('mode')!='installer' or entry['installation'].get('confirmed'))
            control.set_label('Preparing…' if preparing else 'Stopping…' if stopping else ('Stop installer' if installer else 'Stop' if own else 'Play' if configured else 'Setup'))
            control.set_sensitive(not self.demo and not stopping and not preparing and (not active or own) and (not self.tv_mode or configured or own))
            control.set_tooltip_text(('Active: '+current.get('title','game')+'. Finish it before starting another.') if active and not own else 'Stop this game' if own else 'Play through UMU' if configured else 'Configure game files in Manage Game')
        if self.tv_mode and self.game is None and hasattr(self,'tv_hints'):
            status='Controller: '+self.controller.name if hasattr(self,'controller') and self.controller.name else ('Controller unavailable; keyboard/mouse works' if hasattr(self,'controller') and self.controller.error else 'Connect a controller, or use keyboard/mouse')
            self.tv_hints.set_text('D-pad / stick: Move   A / Enter: Select   B / Esc: Back   X: Focus Play / Stop   Start / F11: Options\n'+status)
        if self.game is not None and hasattr(self,'launch_output'):
            if self.detail_install_status is not None:self.detail_install_status.set_text('Installation: '+self.installations.status(self.game)['phase'])
            state=self.launcher.snapshot(self.game['id'])
            text='\n'.join(state.get('logs',[])[-200:])
            if text!=getattr(self,'last_launch_output',None):self.launch_output.get_buffer().set_text(text);self.last_launch_output=text
        if self.editor_kind=='manage':
            self.update_install_stage()
            candidate=self.collect();status=self.installations.status(candidate);self.install_status.set_text(status['phase'])
            self.manage_logs.get_buffer().set_text('\n'.join(status.get('logs',[])[-200:]))
            self.already_installed.set_sensitive(not active);self.confirm_executable_button.set_sensitive(not active);self.install_button.set_sensitive(not self.demo and not active);self.install_cancel.set_sensitive(not self.demo and active and active_id==candidate['id'] and current.get('operation')=='installer')
        return True

    def export_backup(self):
        def selected(path):
            if path.suffix.lower()!='.zip': raise ValueError('Use a filename ending in .zip.')
            self.async_job('Exporting metadata and artwork backup…',lambda:self.library.export_zip(path),lambda _:self.notify('ZIP backup exported. Game files, prefixes and credentials are not included.'))
        self.choose_file('Export library backup',selected,save=True,filename='game-library-backup.zip')

    def import_backup(self):
        def selected(path):
            def preview(result):
                dialog=Adw.MessageDialog.new(self,'Import backup?',f"{result['new']} new games and {result['conflicts']} existing games.\n\n"+'\n'.join(result['titles'][:12])+'\n\nChoose how to handle conflicts. Import never starts a game.')
                dialog.add_response('cancel','Cancel'); dialog.add_response('keep','Keep existing'); dialog.add_response('replace','Replace conflicts')
                dialog.set_response_appearance('replace',Adw.ResponseAppearance.DESTRUCTIVE)
                def response(_,choice):
                    if choice in ('keep','replace'):
                        self.async_job('Restoring local library…',lambda:self.library.import_zip(path,choice),lambda _:(self.show_library(),self.notify('Backup imported locally. Review paths before playing.')))
                dialog.connect('response',response); dialog.present()
            self.async_job('Validating backup…',lambda:self.library.preview_import(path),preview)
        self.choose_file('Import library backup',selected)



class Application(Adw.Application):
    def __init__(self,demo=False):
        self.demo=demo
        super().__init__(application_id='io.github.game_library_launcher'+('.demo' if demo else ''),flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.add_main_option('fullscreen',0,GLib.OptionFlags.NONE,GLib.OptionArg.NONE,'Open in fullscreen for this activation',None)
        self.connect('command-line',self.command_line)
        self.connect('activate',self.activate_window)
    def command_line(self,app,command_line):
        self.activate_window()
        if command_line.get_options_dict().contains('fullscreen'):
            window=self.window
            if not isinstance(window,Window) or not window.set_tv_mode(True):return 1
        return 0
    def activate_window(self,*_):
        window=getattr(self,'window',None)
        if not window:
            try:
                if self.demo:
                    from .demo import prepare_demo
                    library=prepare_demo()
                else: library=Library()
                window=Window(self,library,self.demo)
            except Exception as e:
                window=Adw.ApplicationWindow(application=self,title='Library could not be opened')
                window.set_content(Adw.StatusPage(title='Could not open your library',description=str(e),icon_name='dialog-error-symbolic'))
        self.window=window
        if isinstance(window,Window) and not hasattr(self,'tray') and not self.demo:
            self.hold()
            def availability(available):
                if not available and not window.get_visible():window.present()
            def switch_mode(enabled):
                self.activate_window();window.set_tv_mode(enabled)
            def desktop_action(callback):
                self.activate_window();window.set_tv_mode(False);callback()
            self.tray=Tray(self.activate_window,window.explicit_exit,availability,lambda:switch_mode(True),lambda:switch_mode(False),lambda:desktop_action(window.toggle_log),lambda:desktop_action(window.open_settings),lambda:desktop_action(window.open_settings))
        window.present()
        if isinstance(window,Window) and window.editor:window.editor.present()


def main():
    demo='--demo' in sys.argv
    args=[arg for arg in sys.argv if arg!='--demo']
    return Application(demo).run(args)
