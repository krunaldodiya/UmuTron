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
from .library import description_excerpt, Library
from .launcher import preparation_progress, Launcher, defaults, build_command
from .proton_manager import ProtonManager
from .setup_state import setup_state
from .installations import Installations
from .tray import Tray, close_action
from .controller import Controller
from .catalog_ui import CatalogUI, CSS as CATALOG_CSS
from .download_service import configured_game
from .storage_access import DemoStorage, configured_storage
from .storage_ui import StoragePage
from .dialogs import CSS as DIALOG_CSS, message_dialog, modal_window, dialog_body, dialog_footer, style_surface
from .fullscreen import CSS as FULLSCREEN_CSS, cover as console_cover, set_art, CoverLayout, CoverPicture
from . import APP_ID, APP_NAME, ICON_NAME, __version__


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


class Window(CatalogUI, Adw.ApplicationWindow):
    def __init__(self, app, library, demo=False, catalog_provider=None, storage_service=None):
        super().__init__(application=app,title=APP_NAME,default_width=1120,default_height=800)
        self.add_css_class('desktop-mode')
        Adw.StyleManager.get_default().connect_object('notify::dark',Window.sync_desktop_palette,self)
        self.sync_desktop_palette()
        css=Gtk.CssProvider()
        css.load_from_data(DIALOG_CSS + FULLSCREEN_CSS + CATALOG_CSS + b'.control-focused, button:focus { outline: 3px solid #82bcff; outline-offset: 2px; } .art-frame { background: alpha(@window_fg_color, 0.055); border-radius: 12px; padding: 8px; } .game-card { padding: 10px; } .game-card:hover { background: alpha(@accent_color, 0.09); }')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.demo=demo;self.tv_mode=False;self.tv_selected_id=None;self.tv_tiles=[];self.tv_section='library'
        self.library=library; self.launcher=Launcher(library.root); self.proton_manager=ProtonManager(library.root/'proton-manager',umu_root=library.root/'demo-umu-runners' if demo else None); self.launch_fields={}; self.play_buttons={}; self.installations=Installations(library,self.launcher);self.editor=None;self.editor_kind=None;self.exiting=False
        self.storage_service=storage_service if storage_service is not None else DemoStorage() if demo else configured_storage(library.root)
        self.settings_dialog=None
        self.init_catalog(catalog_provider)
        self.pool=ThreadPoolExecutor(max_workers=2)
        self.busy=False; self.game=None; self.original=None; self.fields={}; self.log_lines=[]
        self.connect('close-request',self.close_requested);self.connect('notify::focus-widget',self.update_focus_outline)
        self.toast=Adw.ToastOverlay(); self.set_content(self.toast)
        self.layout=box(spacing=0)
        self.scene=Gtk.Overlay();self.backdrop=Gtk.Picture(content_fit=Gtk.ContentFit.COVER,can_shrink=True,opacity=0);self.backdrop.set_visible(True);self.backdrop.set_can_target(False)
        self.scene.set_child(self.backdrop);self.toast.set_child(self.layout)
        shade=Gtk.Box();shade.add_css_class('tv-scrim');shade.set_can_target(False);self.scene.add_overlay(shade)
        self.header=Adw.HeaderBar()
        self.header.add_css_class('desktop-header')
        self.back=button('Back to library',self.go_back,icon='go-previous-symbolic')
        self.back.set_visible(False); self.header.pack_start(self.back)
        self.home_nav=button('Home',self.show_home);self.header.pack_start(self.home_nav)
        self.library_nav=button('Library',self.show_library);self.header.pack_start(self.library_nav)
        self.store_nav=button('Store',self.show_store);self.header.pack_start(self.store_nav)
        for control in (self.home_nav,self.library_nav,self.store_nav):control.add_css_class('desktop-nav')
        self.heading=Adw.WindowTitle(title=APP_NAME,subtitle='Your games · UMU and Proton')
        masthead=box(False,8);masthead.set_valign(Gtk.Align.CENTER)
        mark=Gtk.Image.new_from_icon_name(ICON_NAME);mark.set_pixel_size(24);masthead.append(mark);masthead.append(self.heading)
        self.header.set_title_widget(masthead)
        self.theme=Gtk.DropDown.new_from_strings(['Follow system','Light','Dark'])
        self.theme.set_tooltip_text('Appearance')
        self.theme.set_selected(['system','light','dark'].index(self.library.data['settings'].get('theme','system')))
        self.theme.connect('notify::selected',self.theme_changed)
        self.theme.set_visible(False)
        self.exit_button=button('Exit '+APP_NAME,self.explicit_exit,icon='application-exit-symbolic');self.exit_button.set_visible(False)
        self.settings_button=button('Settings',self.open_settings,icon='preferences-system-symbolic');self.settings_button.set_visible(False)
        self.mode_button=button('Fullscreen',lambda:self.set_tv_mode(not self.tv_mode));self.mode_button.set_tooltip_text('Switch desktop / fullscreen mode (F11)');self.mode_button.set_visible(False)
        self.layout.append(self.header)
        self.tv_controls=box(False,16);self.tv_controls.add_css_class('tv-controls');margins(self.tv_controls,0);self.tv_controls.set_visible(False)
        brand=box(False,10);brand.set_valign(Gtk.Align.CENTER);brand.add_css_class('tv-brand')
        brand_icon=Gtk.Image.new_from_icon_name(ICON_NAME);brand_icon.set_pixel_size(34);brand.append(brand_icon);brand.append(label(APP_NAME));self.tv_controls.append(brand)
        self.tv_home_tab=button('Home',self.show_home);self.tv_home_tab.add_css_class('flat');self.tv_controls.append(self.tv_home_tab)
        self.tv_library_tab=button('Library',self.show_library);self.tv_library_tab.add_css_class('flat');self.tv_controls.append(self.tv_library_tab)
        self.tv_games_tab=button('Store',self.show_store);self.tv_games_tab.add_css_class('flat');self.tv_controls.append(self.tv_games_tab)
        spacer=Gtk.Box(hexpand=True);self.tv_controls.append(spacer)
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
        clicks=Gtk.GestureClick();clicks.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        clicks.connect('pressed',lambda *_:self.mark_browse_input());self.add_controller(clicks)
        self.controller=Controller(self.controller_action,self.controller_enabled)
        GLib.timeout_add(40,self.controller.poll)
        app.connect('shutdown',lambda *_:self.controller.close())
        if self.library.data['settings'].get('default_display_mode','desktop')=='fullscreen':self.set_tv_mode(True)
        GLib.timeout_add(250,self.refresh_launch_state)
        self.console_size=None;self.add_tick_callback(self.resize_console)

    def set_tv_mode(self,enabled):
        enabled=bool(enabled)
        if self.editor or self.busy or any(w.get_visible() and w.get_modal() and w.get_transient_for() is self for w in Gtk.Window.get_toplevels()):
            self.notify('Save or cancel the current dialog before switching display mode.');return False
        if enabled==self.tv_mode:
            # The compositor can change fullscreen state independently of the
            # app's layout mode. Reapply an explicit tray request when needed.
            if self.is_fullscreen()!=enabled:
                self.fullscreen() if enabled else self.unfullscreen()
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
            self.remove_css_class('desktop-mode');self.add_css_class('tv-mode');self.fullscreen()
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        else:
            self.remove_css_class('tv-mode');self.add_css_class('desktop-mode');self.unfullscreen();self.apply_theme()
        if current:self.show_shared_detail(current,self.detail_item)
        elif self.route=='store':self.show_store(restore=True)
        elif self.route=='home':self.show_home()
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

    def ui_scale_factor(self):
        setting=self.library.data.get('settings',{}).get('ui_scale','auto')
        if setting=='100':return 1.0
        if setting=='125':return 1.25
        if setting=='150':return 1.5
        if setting=='175':return 1.75
        if setting=='200':return 2.0
        w,h=self.get_width(),self.get_height()
        if self.tv_mode:
            if w>=2500 or h>=1400:return 1.85
            if w>=1800 or h>=950:return 1.5
            if w>=1200:return 1.35
            return 1.0
        if w>=2500 or h>=1400:return 1.6
        if w>=1800 or h>=1000:return 1.3
        return 1.0

    def update_scale_classes(self):
        scale=self.ui_scale_factor()
        for cls in ('scale-compact','scale-normal','scale-large','scale-xlarge'):
            self.remove_css_class(cls)
        if scale<=0.9:self.add_css_class('scale-compact')
        elif scale<=1.15:self.add_css_class('scale-normal')
        elif scale<=1.55:self.add_css_class('scale-large')
        else:self.add_css_class('scale-xlarge')

    def console_dimensions(self):
        scale=self.ui_scale_factor()
        if self.get_height()<650 and scale<=1.0:return (80,120)
        compact=(self.get_width()<1400 or self.get_height()<850) and scale<=1.0
        if compact:return (96,144)
        return (int(152*scale),int(228*scale))

    def resize_console(self,widget,clock):
        self.update_scale_classes()
        scale=self.ui_scale_factor()
        if self.route=='detail':
            resize=getattr(self,'detail_responsive',None)
            if resize:resize(widget,clock)
            return True
        if self.route!='home':return True
        if hasattr(self,'home_stage') and hasattr(self,'tv_page'):
            height=self.tv_page.get_height()
            if height>0 and self.home_stage.get_size_request()[1]!=height:self.home_stage.set_size_request(-1,height)
        size=self.console_dimensions()
        if size==self.console_size:return True
        self.console_size=size
        if hasattr(self,'tv_scroll'):self.tv_scroll.set_min_content_height(size[1]+int(48*scale)+48)
        if size[0]<152 and scale<=1.0:self.add_css_class('tv-compact')
        else:self.remove_css_class('tv-compact')
        if self.game is None and hasattr(self,'tv_title'):
            self.tv_title.set_size_request(-1,int(74*scale) if (size[0]<152 and scale<=1.0) else int(116*scale))
            self.tv_description.set_size_request(-1,int(44*scale) if (size[0]<152 and scale<=1.0) else int(56*scale))
            self.tv_description.set_visible(size[0]!=80 or scale>1.0);self.tv_eyebrow.set_visible(size[0]!=80 or scale>1.0)
        if self.game is not None and hasattr(self,'cover') and self.cover.has_css_class('tv-cover'):
            self.cover.set_size_request(int(144*scale) if (size[0]<152 and scale<=1.0) else int(180*scale),int(216*scale) if (size[0]<152 and scale<=1.0) else int(270*scale))
            play=self.play_buttons.get(self.game['id'])
            if play:play.set_size_request(int(144*scale) if (size[0]<152 and scale<=1.0) else int(180*scale),-1)
        for _,tile in [*self.tv_tiles,*getattr(self,'home_setup_tiles',[])]:
            tile.console_width=size[0];tile.queue_resize()
            tile.console_cover.set_size_request(*size)
            tile.console_title.set_size_request(size[0],int(42*scale) if (size[0]<152 and scale<=1.0) else int(48*scale))
        return True


    def tv_tile(self,game,grid=False):
        tile=button(game['title'],lambda g=game:self.show_game(g));tile.set_focusable(False);tile.add_css_class('tv-card');tile.set_valign(Gtk.Align.START);tile.set_halign(Gtk.Align.CENTER);tile.set_tooltip_text('Open '+game['title'])
        tile.update_property([Gtk.AccessibleProperty.LABEL],['Open '+game['title']])
        if not grid:tile.add_css_class('tv-game-chip')
        content=box(spacing=10);tile.set_child(content)
        name=game['artwork'].get('portrait') or game['artwork'].get('landscape')
        width,height=self.console_dimensions()
        tile.console_width=width;tile.set_layout_manager(CoverLayout())
        artwork=console_cover(self.library.art_dir/name if name else None,width,height);content.append(artwork);tile.console_cover=artwork
        scale=self.ui_scale_factor()
        title=label(game['title'],'tv-card-title',xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,lines=2,ellipsize=Pango.EllipsizeMode.END,width_chars=1,max_width_chars=1);title.set_size_request(width,int(48*scale));content.append(title);tile.console_title=title
        focus=Gtk.EventControllerFocus();focus.connect('enter',lambda _,g=game,t=tile:self.select_home_tile(g,t));tile.add_controller(focus)
        return tile

    def select_home_tile(self,game,tile):
        if self.route=='home':self.home_focus_section=getattr(tile,'home_section','recent')
        self.select_tv_game(game)

    def reveal_browse_control(self,control):
        scroll=getattr(self,'tv_page',None) if self.route=='home' else getattr(self,'collection_scroll',None) if self.route in self.routes else None
        if not scroll or not control or scroll.get_root() is not self:return
        header=[self.home_nav,self.library_nav,self.store_nav,self.tv_home_tab,self.tv_library_tab,self.tv_games_tab,self.tv_menu]
        toolbar=getattr(self,'collection_heading',None) if self.route in self.routes else None
        top=control in header or (toolbar is not None and control.is_ancestor(toolbar))
        if not top and not control.is_ancestor(scroll):return
        generation=self.catalog_generation;route=self.route;revision=getattr(self,'browse_focus_revision',0)
        geometry=None;stable_frames=0
        def reveal(widget,clock):
            nonlocal geometry,stable_frames
            if self.route!=route or generation!=self.catalog_generation or revision!=getattr(self,'browse_focus_revision',0) or self.focused_control(self) is not control:return False
            if control.get_height()<=0:return True
            content=scroll.get_child()
            if isinstance(content,Gtk.Viewport):content=content.get_child()
            valid,bounds=control.compute_bounds(content)
            if valid:
                adjustment=scroll.get_vadjustment();value=adjustment.get_value();page=adjustment.get_page_size()
                padding=min(10,max(0,(page-bounds.get_height())/2))
                edge=bounds.get_y()-padding;bottom=bounds.get_y()+bounds.get_height()+padding
                current=(bounds.get_y(),bounds.get_width(),bounds.get_height(),page)
                if clock is not None:
                    stable_frames=stable_frames+1 if current==geometry else 0
                    geometry=current
                if top:adjustment.set_value(adjustment.get_lower())
                elif edge<value:adjustment.set_value(max(adjustment.get_lower(),edge))
                elif bottom>value+page:adjustment.set_value(min(adjustment.get_upper()-page,bottom-page))
            # Card text and the responsive hero can reflow after initial focus.
            # Finish only after two stable native frames, not a timing delay.
            return not valid or stable_frames<2
        control.add_tick_callback(reveal)
        # Keyboard/controller focus can change between native layout frames.
        GLib.idle_add(lambda:(reveal(control,None),False)[1])

    def focus_browse_route(self):
        controls={'home':self.tv_home_tab if self.tv_mode else self.home_nav,
                  'library':self.tv_library_tab if self.tv_mode else self.library_nav,
                  'store':self.tv_games_tab if self.tv_mode else self.store_nav}
        controls[self.route].grab_focus();self.update_focus_outline()

    def mark_browse_input(self):
        # Distinguish user navigation from GTK's automatic fallback focus while
        # rebuilding a route. A queued restore must yield to newer user input.
        self.browse_navigation_revision=getattr(self,'browse_navigation_revision',0)+1

    def show_home(self):
        return_id=getattr(self,'home_selected_id',None)
        self.begin_route('home');self.tv_section='games';self.body.add_css_class('home-surface')
        self.home_setup_tiles=[];self.home_setup_games=[]
        self.console_size=None
        self.backdrop.set_opacity(1);self.backdrop.set_paintable(None)
        from .play_history import recent,revision
        self.home_history_revision=revision(self.library.root)
        from .setup_history import groups
        dated,_=groups(self.library);self.home_setup_games=dated
        self.tv_games=recent(self.library)[:24];self.tv_tiles=[]
        if not self.tv_games and not self.home_setup_games:
            empty=Adw.StatusPage(title='Your next adventure starts here',description='Browse Store to save a game, then connect its files in Setup. Your recent plays and completed setups will appear here.',icon_name=ICON_NAME);self.body.append(empty);(self.tv_home_tab if self.tv_mode else self.home_nav).grab_focus();return
        tv_content=box(spacing=0);tv_content.set_vexpand(True)
        self.tv_page=self.scrolled(tv_content)
        self.home_backdrop=CoverPicture(content_fit=Gtk.ContentFit.COVER,can_shrink=True)
        home_scene=Gtk.Overlay();home_scene.set_child(self.home_backdrop)
        scrim=Gtk.Box();scrim.add_css_class('tv-scrim');home_scene.add_overlay(scrim)
        home_scene.add_overlay(self.tv_page);home_scene.set_measure_overlay(self.tv_page,True);home_scene.set_vexpand(True);self.body.append(home_scene)
        self.home_stage=box(spacing=0);tv_content.append(self.home_stage)
        scale=self.ui_scale_factor()
        hero=box(spacing=0);hero.set_vexpand(True);hero.set_size_request(-1,max(180,int(180*scale)));self.home_stage.append(hero)
        summary=box(spacing=max(8,int(8*scale)));summary.add_css_class('tv-summary');summary.set_valign(Gtk.Align.END);summary.set_vexpand(True);summary_limit=Adw.Clamp(maximum_size=min(int(790*scale),max(790,self.get_width()-48)),tightening_threshold=min(int(790*scale),max(790,self.get_width()-48)));summary_limit.set_halign(Gtk.Align.START);summary_limit.set_child(summary);hero.append(summary_limit)
        self.tv_eyebrow=label('RECENTLY PLAYED','tv-eyebrow',xalign=0);summary.append(self.tv_eyebrow)
        self.tv_title=label('','tv-title',xalign=0,wrap=True,lines=2,ellipsize=Pango.EllipsizeMode.END,max_width_chars=25,halign=Gtk.Align.START);self.tv_title.set_size_request(-1,74 if self.console_dimensions()[0]<152 else 116);summary.append(self.tv_title)
        self.tv_related=label('','tv-meta',xalign=0,ellipsize=Pango.EllipsizeMode.END);self.tv_related.set_size_request(-1,24);summary.append(self.tv_related)
        self.tv_description=label('','tv-description',xalign=0,wrap=True,lines=2,ellipsize=Pango.EllipsizeMode.END,max_width_chars=62,halign=Gtk.Align.START);self.tv_description.set_size_request(-1,44 if self.console_dimensions()[0]<152 else 56);summary.append(self.tv_description)
        actions=box(False,14);summary.append(actions)
        self.tv_play=button('Play',lambda:self.play_game(self.tv_selected_game()),'tv-play');actions.append(self.tv_play)
        self.tv_open=button('View game',lambda:self.show_game(self.tv_selected_game()),'tv-secondary');actions.append(self.tv_open)
        self.tv_launch_status=label('','tv-meta',xalign=0,ellipsize=Pango.EllipsizeMode.END,width_chars=1,hexpand=True);self.tv_launch_status.set_size_request(-1,24);self.tv_launch_status.set_valign(Gtk.Align.CENTER);actions.append(self.tv_launch_status);self.place_runtime_progress(summary)
        collection=box(spacing=0);collection.add_css_class('tv-collection');self.home_stage.append(collection)
        heading=box(False);heading.append(label('Recently played','tv-section-heading',xalign=0,hexpand=True));self.tv_counter=label('','tv-counter');heading.append(self.tv_counter);collection.append(heading)
        self.tv_rail=box(False,20);margins(self.tv_rail,12);self.tv_rail.set_margin_start(48);self.tv_rail.set_margin_end(48)
        self.tv_scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.EXTERNAL,vscrollbar_policy=Gtk.PolicyType.NEVER);self.tv_scroll.set_child(self.tv_rail);self.tv_scroll.get_child().set_hscroll_policy(Gtk.ScrollablePolicy.NATURAL);collection.append(self.tv_scroll)
        self.tv_scroll.get_hadjustment().connect('changed',lambda adjustment:GLib.idle_add(self.pad_tv_rail,adjustment))
        for game in self.tv_games:
            tile=self.tv_tile(game);self.tv_rail.append(tile);self.tv_tiles.append((game['id'],tile))
        self.tv_rail_end=Gtk.Box();self.tv_rail.append(self.tv_rail_end)
        if not self.tv_games:
            self.tv_scroll.set_visible(False)
            empty=label('Your recent plays will appear here after you start a game.','tv-meta',xalign=0,wrap=True);margins(empty,32);collection.append(empty)
        self.home_setup_section=box(spacing=18);self.home_setup_section.add_css_class('home-setups');tv_content.append(self.home_setup_section)
        self.home_setup_section.append(label('Recently ready to play','tv-section-heading',xalign=0))
        self.home_setup_section.append(label('Your latest completed setups, newest first.','tv-meta',xalign=0,wrap=True))
        if not dated:self.home_setup_section.append(label('Newly completed setups will appear here. Saving metadata does not count as setup.','tv-meta',xalign=0,wrap=True))
        if dated:
            grid=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,min_children_per_line=1,max_children_per_line=12,column_spacing=22,row_spacing=28);grid.set_valign(Gtk.Align.START)
            self.home_setup_section.append(grid)
            for entry in dated:
                tile=self.tv_tile(entry,grid=True);tile.home_section='setup';tile.add_css_class('home-setup-card')
                state=setup_state(entry)
                status='Ready to play' if state['ready'] else 'Files unavailable' if entry.get('executable') and not Path(entry['executable']).is_file() else 'Setup needed'
                tile.set_tooltip_text(entry['title']+' · '+status+' · Setup completed '+datetime.fromtimestamp(entry['setup_completed_at']).strftime('%d %b %Y'))
                caption=label(status,'home-setup-state',xalign=0,wrap=True,lines=2,ellipsize=Pango.EllipsizeMode.END,width_chars=1,max_width_chars=1)
                tile.get_child().append(caption);grid.append(tile);self.home_setup_tiles.append((entry['id'],tile))
        self.tv_hints=label('','tv-hints',xalign=0,ellipsize=Pango.EllipsizeMode.END);self.body.append(self.tv_hints)
        choices=self.tv_games+self.home_setup_games
        game=next((g for g in choices if g['id']==return_id),choices[0])
        if not return_id:self.home_focus_section='recent' if self.tv_games else 'setup'
        self.select_tv_game(game)
        self.console_size=None;self.resize_console(self,None)
        self.restrict_tv_focus(self.body)
        section=getattr(self,'home_focus_section','recent')
        for _,tile in self.home_setup_tiles:tile.set_focusable(True)
        if return_id and section=='setup':
            for _,tile in self.tv_tiles:tile.set_focusable(True)
            self.focus_tv_card(False)
        elif self.tv_tiles:self.finish_tv_library_focus()
        else:self.tv_open.grab_focus()


    def show_tv_library(self):
        return self.show_collection()

    def show_tv_grid(self,return_id=None):
        heading=box(spacing=8);margins(heading,32);heading.set_margin_start(48)
        heading.append(label('READY WHEN YOU ARE','tv-eyebrow',xalign=0))
        heading.append(label('Installed games','tv-title',xalign=0))
        heading.append(label(str(len(self.tv_games))+' games · Choose your next adventure','tv-meta',xalign=0));self.body.append(heading)
        self.tv_grid=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,min_children_per_line=1,max_children_per_line=10,column_spacing=20,row_spacing=24);margins(self.tv_grid,32);self.tv_grid.set_margin_start(40);self.tv_grid.set_margin_top(8);self.tv_grid.set_valign(Gtk.Align.START)
        self.tv_scroll=self.scrolled(self.tv_grid);self.body.append(self.tv_scroll)
        if not self.tv_games:
            self.tv_scroll.set_visible(False)
            empty=Adw.StatusPage(title='A place for your installed games',description='Set up game files in desktop mode. All saved titles are still available in Games.',icon_name='applications-games-symbolic');self.body.append(empty);self.tv_library_tab.grab_focus()
        for game in self.tv_games:
            tile=self.tv_tile(game,grid=True);self.tv_grid.append(tile);self.tv_tiles.append((game['id'],tile))
        self.tv_hints=label('','tv-hints',xalign=0,ellipsize=Pango.EllipsizeMode.END);self.body.append(self.tv_hints)
        if self.tv_games:
            game=next((g for g in self.tv_games if g['id']==return_id),self.tv_games[0]);self.select_tv_game(game);self.finish_tv_library_focus()
        self.restrict_tv_focus(self.body);self.refresh_launch_state()

    def restrict_tv_focus(self,widget):
        if isinstance(widget,Gtk.Label):widget.set_selectable(False)
        if not isinstance(widget,(Gtk.Button,Gtk.MenuButton,Gtk.CheckButton,Gtk.Notebook)):widget.set_focusable(False)
        child=widget.get_first_child()
        while child:self.restrict_tv_focus(child);child=child.get_next_sibling()

    def focused_control(self,target):
        focus=target.get_focus()
        while focus and not isinstance(focus,(Gtk.Button,Gtk.MenuButton,Gtk.CheckButton,Gtk.SearchEntry)):focus=focus.get_parent()
        if focus and isinstance(focus.get_parent(),Gtk.MenuButton):return focus.get_parent()
        return focus

    def update_focus_outline(self,*_):
        focused=self.focused_control(self)
        previous=getattr(self,'outlined_control',None)
        if previous is not focused:
            if previous:previous.remove_css_class('control-focused')
            if focused:focused.add_css_class('control-focused')
            self.outlined_control=focused
            self.browse_focus_revision=getattr(self,'browse_focus_revision',0)+1
            self.reveal_browse_control(focused)
            if self.tv_mode and self.game and hasattr(self,'detail_scroll'):
                viewport=self.detail_scroll.get_child()
                if isinstance(viewport,Gtk.Viewport):viewport.set_scroll_to_focus(True)

    def controller_popover(self,target):
        if target is not self:
            # The active owned modal has its own menus (for example Storage
            # drive options). Contain navigation there before handling Back.
            def visible_menu(widget):
                if isinstance(widget,Gtk.MenuButton):
                    popover=widget.get_popover()
                    if popover and popover.get_visible():return popover
                child=widget.get_first_child()
                while child:
                    found=visible_menu(child)
                    if found:return found
                    child=child.get_next_sibling()
                return None
            return visible_menu(target)
        if target is self and self.route in self.routes:
            for name in ('collection_genre',):
                control=getattr(self,name,None)
                if control and isinstance(control,Gtk.MenuButton) and control.get_root() is self:
                    popover=control.get_popover()
                    if popover and popover.get_visible():return popover
        gear=getattr(self,'detail_gear',None)
        if target is self and self.route=='detail' and gear and gear.get_root() is self:
            popover=gear.get_popover()
            if popover and popover.get_visible():return popover
        return None

    def move_control_focus(self,target,action):
        # Browse search is a navigation stop; its inner editable keeps native keys.
        popover=self.controller_popover(target)
        if target is self and not popover and self.route in self.routes and self.browse_toolbar_focus(action):return
        controls=[]
        def visit(widget):
            if isinstance(widget,Gtk.WindowControls):return
            if isinstance(widget,(Gtk.Button,Gtk.MenuButton,Gtk.CheckButton,Gtk.SearchEntry)):
                # MenuButton delegates focus to its internal toggle; the outer
                # focusable property is false even when grab_focus succeeds.
                if widget.get_mapped() and widget.is_sensitive() and (widget.get_focusable() or isinstance(widget,(Gtk.MenuButton,Gtk.SearchEntry))):controls.append(widget)
                return
            child=widget.get_first_child()
            while child:visit(child);child=child.get_next_sibling()
        visit(popover or target)
        if not controls:return
        current=self.focused_control(target)
        if current not in controls:controls[0].grab_focus();return
        if popover:action={'up':'previous','down':'next'}.get(action,action)
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

    def tv_selected_game(self):
        choices=self.tv_games+(self.home_setup_games if self.route=='home' else [])
        return next(g for g in choices if g['id']==self.tv_selected_id)

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
            generation=self.catalog_generation
            def allocated(widget,clock):
                if generation!=self.catalog_generation or self.focused_control(self) is not widget:return False
                if widget.get_width()<=0:return True
                if self.tv_section=='games':
                    self.pad_tv_rail(self.tv_scroll.get_hadjustment())
                    adjustment=self.tv_scroll.get_hadjustment()
                    if adjustment.get_page_size()<=0 or (len(self.tv_tiles)>1 and adjustment.get_upper()<=adjustment.get_page_size()):return True
                    self.scroll_tv_card_into_view(widget)
                return False
            tile.add_tick_callback(allocated)

    def focus_tv_card(self,animate=True):
        if self.route=='home' and (not self.tv_tiles or getattr(self,'home_focus_section','recent')=='setup'):
            tile=next((t for gid,t in self.home_setup_tiles if gid==self.tv_selected_id),None)
            if tile:tile.grab_focus()
            return
        tile=next((t for gid,t in self.tv_tiles if gid==self.tv_selected_id),self.tv_tiles[0][1] if self.tv_tiles else None)
        if tile:
            tile.grab_focus()
            if self.tv_section=='library':return
            self.scroll_tv_card_into_view(tile,animate)

    def pad_tv_rail(self,adjustment):
        if adjustment!=self.tv_scroll.get_hadjustment():return False
        # Trailing room lets even a short library slide to each selected icon.
        if self.tv_mode and self.game is None and self.tv_section=='games':
            padding=max(24,int(adjustment.get_page_size())-self.console_dimensions()[0]-64)
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
        # Focus-enter can precede notify::focus-widget. Own this request by
        # its tile and route; a newer rail request already removes the old timer.
        generation=self.catalog_generation
        def frame():
            if self.game is not None or self.tv_section!='games' or self.tv_scroll is not scroll or generation!=self.catalog_generation or self.focused_control(self) is not tile:
                self.rail_animation=None;return False
            progress=min(1,(GLib.get_monotonic_time()-started)/220000)
            eased=1-(1-progress)**3
            adjustment.set_value(start+(target-start)*eased)
            if progress>=1:self.rail_animation=None;return False
            return True
        self.rail_animation=GLib.timeout_add(16,frame)

    def select_tv_game(self,game):
        self.tv_selected_id=game['id']
        if self.route=='home':self.home_selected_id=game['id']
        for gid,tile in [*self.tv_tiles,*(self.home_setup_tiles if self.route=='home' else [])]:
            if gid==game['id']:tile.add_css_class('selected-game')
            else:tile.remove_css_class('selected-game')
        name=game['artwork'].get('hero') or game['artwork'].get('landscape')
        set_art(self.backdrop,self.library.art_dir/name if name else None)
        self.backdrop.set_opacity(.38 if self.tv_section=='library' else 1)
        if self.route=='home' and hasattr(self,'home_backdrop'):set_art(self.home_backdrop,self.library.art_dir/name if name else None)
        if self.tv_section=='library':return
        if self.route=='home':
            self.tv_eyebrow.set_text('RECENTLY PLAYED' if getattr(self,'home_focus_section','recent')=='recent' and self.tv_games else 'RECENTLY READY TO PLAY')
        self.tv_title.set_text(game['title']);self.tv_description.set_text(description_excerpt(game['description']) or 'Discover this title in your collection. No description is available.')
        self.tv_related.set_text(' · '.join(filter(None,(game.get('release_date'),game.get('genres')))))
        index=next((i for i,g in enumerate(self.tv_games,1) if g['id']==game['id']),1)
        self.tv_counter.set_text(f'{index:02d} / {len(self.tv_games):02d}' if self.tv_games and getattr(self,'home_focus_section','recent')=='recent' else str(len(self.tv_games))+' recent games' if self.tv_games else '')
        self.play_buttons={game['id']:self.tv_play};self.refresh_launch_state()
        tile=next((tile for gid,tile in self.tv_tiles if gid==game['id']),None)
        if tile and tile.get_width()>0 and (self.route!='home' or getattr(self,'home_focus_section','recent')=='recent'):self.scroll_tv_card_into_view(tile,True)

    def open_tv_options(self):
        dialog=getattr(self,'tv_options_dialog',None)
        if dialog and dialog.get_visible():dialog.present();return
        dialog=modal_window(self,'Fullscreen options',width=440,height=260)
        self.tv_options_dialog=dialog
        content=dialog_body(dialog)
        def exit_fullscreen():
            dialog.close();self.set_tv_mode(False)
        def exit_launcher():
            dialog.close();self.explicit_exit()
        def open_storage():
            dialog.close();self.open_settings('storage')
        content.append(button('Storage',open_storage))
        leave=button('Exit fullscreen',exit_fullscreen);content.append(leave);content.append(button('Exit',exit_launcher))
        def change_scale():
            dialog.close()
            scales=['auto','100','125','150','175','200']
            cur=self.library.data.get('settings',{}).get('ui_scale','auto')
            idx=(scales.index(cur)+1)%len(scales)
            self.library.set_ui_scale(scales[idx])
            self.update_scale_classes()
            labels=['Auto','100%','125%','150%','175%','200%']
            self.notify(f'UI Scale set to {labels[idx]}')
            if self.route=='detail' and self.game:self.show_shared_detail(self.game,self.detail_item)
            elif self.route=='store':self.show_store(restore=True)
            elif self.route=='home':self.show_home()
            else:self.show_library()
        content.append(button('Change UI scale',change_scale))
        keys=Gtk.EventControllerKey();keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE);keys.connect('key-pressed',self.on_key);dialog.add_controller(keys)
        dialog.connect('close-request',lambda _:(self.tv_menu.grab_focus(),False)[-1])
        dialog.present();leave.grab_focus()

    def navigation_window(self):
        # Only launcher-owned, focused windows receive controller navigation.
        for window in Gtk.Window.get_toplevels():
            parent=window
            while parent and parent is not self:parent=parent.get_transient_for()
            if parent is self and window.get_visible() and window.is_active():return window
        return None

    def controller_enabled(self):
        target=self.navigation_window()
        return not self.busy and target is not None and (self.tv_mode or
            (target is self and not self.editor and self.route in ('home','library','store','detail')))

    def controller_action(self,action):
        if not self.controller_enabled():return
        target=self.navigation_window()
        if target is None:return
        if target is self:self.mark_browse_input()
        popover=self.controller_popover(target)
        if popover:
            if action=='back':
                owner=getattr(popover,'browse_owner',None) or popover.get_ancestor(Gtk.MenuButton)
                popover.popdown()
                if owner:owner.grab_focus()
                self.update_focus_outline()
            elif action in ('left','right','up','down','next','previous'):
                self.move_control_focus(target,action)
            elif action=='select':
                focus=self.focused_control(target)
                if focus and focus.is_sensitive() and focus.is_ancestor(popover):focus.activate()
                else:self.move_control_focus(target,'next')
            return
        source_navigation=getattr(target,'source_navigation',None)
        if callable(source_navigation):
            if action in ('left','right','up','down','next','previous'):
                source_navigation(action);return
            focus=target.get_focus()
            notebook=getattr(target,'source_notebook',None)
            if action=='select' and notebook is not None and focus is not None and (focus is notebook or focus.is_ancestor(notebook)):
                source_navigation('down');return
        if action=='desktop':
            if target is self and self.tv_mode:self.tv_menu.grab_focus();self.open_tv_options()
            return
        if target is self and self.route in self.routes and self.focused_control(target) is self.collection_search:
            if action=='select':
                self.collection_search.emit('activate');return
            if action in ('back','up'):
                self.focus_browse_route();return
            if action=='down':
                self.browse_toolbar_focus(action);return
        if action=='back':
            if target is not self:
                if target is self.editor:self.cancel_editor()
                else:target.close()
            elif self.route=='detail':self.return_from_detail()
            elif self.route in ('home','library','store'):self.focus_browse_route()
            return
        if action=='play':
            if target is self:
                control=self.detail_primary if self.route=='detail' else self.play_buttons.get(self.tv_selected_id)
                if control:
                    if self.game and hasattr(self,'detail_scroll'):
                        viewport=self.detail_scroll.get_child()
                        if isinstance(viewport,Gtk.Viewport):viewport.set_scroll_to_focus(True)
                    control.grab_focus();self.update_focus_outline()
            return
        if action in ('pageup','pagedown'):
            if target is self and self.route in self.routes:
                self.collection_page(1 if action=='pagedown' else -1);return
            if hasattr(target,'info_scroll') or (target is self and self.game and hasattr(self,'detail_scroll')):
                scroll=target.info_scroll if hasattr(target,'info_scroll') else self.detail_scroll
                viewport=scroll.get_child()
                if isinstance(viewport,Gtk.Viewport):viewport.set_scroll_to_focus(False)
                adjustment=scroll.get_vadjustment()
                adjustment.set_value(max(adjustment.get_lower(),min(adjustment.get_upper()-adjustment.get_page_size(),adjustment.get_value()+(.8 if action=='pagedown' else -.8)*adjustment.get_page_size())))
            return
        if action in ('left','right','up','down','next','previous'):
            focus=self.focused_control(target)
            header=[self.tv_home_tab,self.tv_library_tab,self.tv_games_tab,self.tv_menu] if self.tv_mode else [self.home_nav,self.library_nav,self.store_nav]
            if target is self and self.route in self.routes and self.browse_toolbar_focus(action):return
            if target is self and focus in header:
                if action in ('left','right'):
                    index=header.index(focus);index=max(0,min(len(header)-1,index+(1 if action=='right' else -1)));header[index].grab_focus();self.update_focus_outline();return
                if action=='down' and self.route in self.routes:
                    self.collection_search.grab_focus();self.update_focus_outline();return
                if action=='down' and self.game is None and (self.tv_tiles or (self.route=='home' and self.home_setup_tiles)):self.focus_tv_card();self.update_focus_outline();return
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

    def native_key_context(self,target):
        """Leave text, native selectors, popovers and modal owners their keys."""
        if target is not self or self.busy or self.editor:return True
        for window in Gtk.Window.get_toplevels():
            if window is self or not window.get_visible() or not window.get_modal():continue
            parent=window.get_transient_for()
            while parent and parent is not self:parent=parent.get_transient_for()
            if parent is self:return True
        focus=self.get_focus()
        while focus and focus is not self:
            if isinstance(focus,(Gtk.Editable,Gtk.TextView,Gtk.DropDown,Gtk.Range,Gtk.Popover)):return True
            focus=focus.get_parent()
        def has_popover(widget):
            if isinstance(widget,Gtk.Popover) and widget.get_mapped():return True
            child=widget.get_first_child()
            while child:
                if has_popover(child):return True
                child=child.get_next_sibling()
            return False
        return has_popover(self)

    def desktop_arrow(self,action):
        if self.route not in ('home','library','store'):return False
        focus=self.focused_control(self);header=[self.home_nav,self.library_nav,self.store_nav]
        if self.route in self.routes and self.browse_toolbar_focus(action):return True
        if focus in header:
            if action in ('left','right'):
                index=max(0,min(len(header)-1,header.index(focus)+(1 if action=='right' else -1)))
                header[index].grab_focus();self.update_focus_outline();return True
            if action=='down':
                if self.route in self.routes:
                    self.collection_search.grab_focus();self.update_focus_outline();return True
                if self.route=='home':
                    choices=self.home_setup_tiles if getattr(self,'home_focus_section','recent')=='setup' else self.tv_tiles
                    choices=choices or self.tv_tiles or self.home_setup_tiles
                else:choices=self.tv_tiles
                tile=next((t for gid,t in choices if gid==self.tv_selected_id),choices[0][1] if choices else None)
                if tile:tile.grab_focus();self.update_focus_outline();return True
        if self.route=='home' and action in ('left','right') and focus in [tile for _,tile in self.tv_tiles]:
            index=next(i for i,(_,tile) in enumerate(self.tv_tiles) if tile is focus)
            self.tv_tiles[(index+(1 if action=='right' else -1))%len(self.tv_tiles)][1].grab_focus()
            self.update_focus_outline();return True
        if focus is None:return False
        self.move_control_focus(self,action);self.update_focus_outline()
        return self.focused_control(self) is not focus

    def on_key(self,controller,keyval,keycode,state):
        target=controller.get_widget() if controller else self
        if target is self:self.mark_browse_input()
        native=self.native_key_context(target)
        modified=bool(state&(Gdk.ModifierType.SHIFT_MASK|Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.ALT_MASK|Gdk.ModifierType.SUPER_MASK|Gdk.ModifierType.META_MASK))
        popover=self.controller_popover(target)
        if popover and getattr(popover,'browse_owner',None):
            if keyval==Gdk.KEY_Tab and not state&(Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.ALT_MASK|Gdk.ModifierType.SUPER_MASK|Gdk.ModifierType.META_MASK):
                self.move_control_focus(target,'previous' if state&Gdk.ModifierType.SHIFT_MASK else 'next');return True
            if keyval==Gdk.KEY_F11:return True
            action={Gdk.KEY_Up:'up',Gdk.KEY_Down:'down',Gdk.KEY_Left:'left',Gdk.KEY_Right:'right',Gdk.KEY_Return:'select',Gdk.KEY_KP_Enter:'select',Gdk.KEY_space:'select',Gdk.KEY_Escape:'back'}.get(keyval)
            if action and not modified:self.controller_action(action);return True
            return False
        if keyval==Gdk.KEY_F11:
            if target is not self or self.editor or any(w.get_visible() and w.get_modal() and w.get_transient_for() is self for w in Gtk.Window.get_toplevels()):return False
            if self.tv_mode or self.is_fullscreen():self.tv_menu.grab_focus();self.open_tv_options()
            else:self.set_tv_mode(True)
            return True
        if keyval in (Gdk.KEY_Page_Up,Gdk.KEY_Page_Down) and self.route in self.routes and not native and not modified:
            self.collection_page(1 if keyval==Gdk.KEY_Page_Down else -1);return True
        if keyval==Gdk.KEY_Escape and not self.tv_mode and self.route=='detail' and not native:
            self.return_from_detail();return True
        if target is self and self.route in self.routes and self.focused_control(self) is self.collection_search:
            if keyval==Gdk.KEY_Escape and not modified:
                self.focus_browse_route();return True
            return False
        if not self.tv_mode:
            action={Gdk.KEY_Left:'left',Gdk.KEY_Right:'right',Gdk.KEY_Up:'up',Gdk.KEY_Down:'down'}.get(keyval)
            return self.desktop_arrow(action) if action and not native and not modified else False
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
        dialog=message_dialog(getattr(self,'installer_dialog',None) or self.editor or self,'Could not complete this action',str(error)[:2000])
        dialog.present()

    def toggle_log(self): self.log_revealer.set_reveal_child(not self.log_revealer.get_reveal_child())

    def sync_desktop_palette(self,*_):
        if Adw.StyleManager.get_default().get_dark():self.add_css_class('desktop-dark')
        else:self.remove_css_class('desktop-dark')

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
        dialog=message_dialog(getattr(self,'installer_dialog',None) or self.editor or self,title,body,
            responses=(('cancel','Cancel'),('confirm',action)),default='cancel',close='cancel',
            destructive='confirm' if destructive else None,suggested=None if destructive else 'confirm')
        dialog.connect('response',lambda _,response:callback() if response=='confirm' else None)
        dialog.present()

    def choose_file(self,title,callback,save=False,folder=False,filename=None,start_folder=None,parent=None):
        action=Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.OPEN
        owner=parent or self.editor or self
        dialog=Gtk.FileChooserNative.new(title,owner,action,'Save' if save else 'Select','Cancel')
        if filename: dialog.set_current_name(filename)
        target=None
        if start_folder:
            p=Path(start_folder)
            if p.is_dir():target=p
            elif p.parent.is_dir():target=p.parent
        if not target and hasattr(self,'fields') and isinstance(self.fields,dict):
            wd=self.fields.get('working_dir')
            if wd and hasattr(wd,'get_text') and wd.get_text():
                p=Path(wd.get_text())
                if p.is_dir():target=p
            if not target:
                ex=self.fields.get('executable')
                if ex and hasattr(ex,'get_text') and ex.get_text():
                    p=Path(ex.get_text())
                    if p.is_file() and p.parent.is_dir():target=p.parent
                    elif p.is_dir():target=p
        if not target and hasattr(self,'storage_service') and self.storage_service:
            try:
                snap=self.storage_service.snapshot()
                def_id=snap.get('default_install')
                for r in snap.get('registrations',[]):
                    if r.get('id')==def_id:
                        p=Path(r.get('path',''))
                        if p.is_dir():target=p;break
            except Exception:pass
        if not target:target=Path.home()
        dialog.set_current_folder(Gio.File.new_for_path(str(target)))
        def response(d,r):
            if r==Gtk.ResponseType.ACCEPT and (owner is self or owner.get_visible()):
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
        return self.show_collection()

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
        self.show_store()

    def entry(self,container,key,title,hint=None):
        wrapper=box(spacing=6); wrapper.append(label(title,'heading',xalign=0))
        entry=Gtk.Entry(text=self.game.get(key,''),hexpand=True)
        entry.set_tooltip_text(title); wrapper.append(entry); self.fields[key]=entry
        if hint: wrapper.append(label(hint,'caption',xalign=0,wrap=True))
        container.append(wrapper); return entry

    def show_game(self,game):
        item = self.detail_item if (self.route=='detail' and self.detail_item and self.game and self.game.get('id')==game.get('id')) else None
        return self.show_shared_detail(game,item,enrich_catalog=True)

    def place_runtime_progress(self,container):
        parent=self.runtime_progress.get_parent()
        if parent:parent.remove(self.runtime_progress)
        container.append(self.runtime_progress)

    def show_game_info(self,game):
        dialog=modal_window(self,'Game Info',width=720,height=560,subtitle=game['title'])
        content=dialog_body(dialog)
        description=label(game.get('description') or 'No description available.','body',wrap=True,xalign=0,selectable=False,valign=Gtk.Align.START)
        overview=box(spacing=16);overview.append(description)
        dialog.catalog_content=box(spacing=16);overview.append(dialog.catalog_content)
        dialog.catalog_generation=self.catalog_generation;dialog.catalog_game_id=game['id']
        self.catalog_info_dialog=dialog.weak_ref();self.append_catalog_info(dialog.catalog_content,game,dialog)
        scroll=self.scrolled(overview);scroll.set_vexpand(True);content.append(scroll);dialog.info_scroll=scroll
        footer=dialog_footer();content.append(footer)
        receiver=dialog.weak_ref()
        def close_info():
            current=receiver()
            if current is not None:current.close()
        close=button('Close',close_info);footer.append(close);dialog.present();close.grab_focus()
        if self.tv_mode:self.restrict_tv_focus(content)

    def editor_window(self,title,kind):
        if self.tv_mode:self.notify('Switch to desktop mode to edit or set up games.');return None
        if self.editor:self.editor.present();return None
        self.original=deepcopy(self.game);self.game=deepcopy(self.game);self.fields={};self.launch_fields={};self.description=None
        self.editor_kind=kind
        dialog=modal_window(self,title,width=780,height=700,subtitle=self.game['title']);self.editor=dialog
        root=dialog_body(dialog)
        content=box();root.append(self.scrolled(content));footer=dialog_footer();root.append(footer)
        footer.append(button('Cancel',self.cancel_editor));self.editor_save=button('Save',self.save_editor,'suggested-action');footer.append(self.editor_save)
        dialog.connect('close-request',lambda _: (self.cancel_editor(),True)[-1])
        return dialog,content,footer

    def cancel_editor(self):
        if not self.editor:return
        if self.editor_kind=='manage':self.close_installer(keep=False)
        dialog=self.editor;saved=deepcopy(self.original);self.editor=None;self.editor_kind=None;dialog.destroy()
        if any(g['id']==saved['id'] for g in self.library.games()):self.show_game(saved)
        elif getattr(self,'detail_item',None):
            from .catalog import item_game
            self.show_shared_detail(item_game(self.detail_item,preview=True),self.detail_item)
        else:self.show_library()

    def save_editor(self):
        try:
            candidate=self.collect()
            if self.editor_kind=='manage' and self.launcher.active():raise ValueError('Finish the active operation before changing game files.')
            if not any(g['id']==candidate['id'] for g in self.library.games()) and getattr(self,'detail_item',None):
                self._save_detail_item_artwork(candidate)
            if self.editor_kind=='manage':candidate=self.installations.prepare_setup_save(candidate)
            if self.editor_kind=='manage':self.close_installer()
            if self.editor_kind=='manage':candidate=self.library.save_setup(candidate)
            else:self.library.save(candidate)
            dialog=self.editor;self.editor=None;self.editor_kind=None
            if dialog:dialog.destroy()
            self.show_game(candidate);self.notify('Saved to your library.')
        except Exception as error:self.error(error)


    def open_manage(self,new_game=False):
        result=self.editor_window('Manage Game','manage')
        if not result:return
        dialog,content,footer=result
        self.manage_new=new_game;self.installer_dialog=None
        self.installer_draft=self.game.get('installation',{}).get('installer','')
        if new_game:self.entry(content,'title','Game name','You can search public metadata after saving this entry.')
        heading=box(False);content.append(heading)
        heading.append(label('Game setup','title-2',xalign=0,hexpand=True))
        self.manage_more=Gtk.MenuButton(label='More');heading.append(self.manage_more)
        popover=style_surface(Gtk.Popover());menu=box(spacing=6);margins(menu,8);popover.set_child(menu);self.manage_more.set_popover(popover)
        self.install_action=button('Install game…',self.open_installer);menu.append(self.install_action)
        self.setup_status=label('','dim-label',wrap=True,xalign=0);content.append(self.setup_status)
        self.executable_panel=box();content.append(self.executable_panel)
        self.entry(self.executable_panel,'executable','Game executable','Select the installed game executable; it runs through UMU.')
        self.executable_panel.append(button('Choose game executable',self.pick_executable))
        self.entry(self.executable_panel,'working_dir','Working directory','Blank uses the executable’s folder.')
        self.executable_panel.append(button('Choose working directory',lambda:self.choose_file('Working directory',lambda p:self.fields['working_dir'].set_text(str(p)),folder=True)))
        self.build_installation_folder(self.executable_panel)
        self.build_game_arguments(self.executable_panel)
        self.confirm_executable_button=button('Confirm installed game executable',self.confirm_installed,'suggested-action');self.executable_panel.append(self.confirm_executable_button)
        advanced=Adw.ExpanderRow(title='Advanced launch settings',subtitle='Optional overrides. Working defaults are applied automatically.');self.advanced=advanced
        advanced_content=box();margins(advanced_content,12);advanced.add_row(advanced_content);self.build_advanced(advanced_content)
        advanced_content.append(button('Reset to defaults',self.reset_launch_defaults))
        from .proton_ui import build_game_selector
        self.proton_section=box();content.append(self.proton_section)
        build_game_selector(self,self.proton_section,dialog)
        content.append(advanced);content.append(button('Open diagnostic logs',self.open_diagnostic_logs))
        for field in ('executable','working_dir'):
            self.fields[field].connect('changed',lambda *_:self.update_install_stage())
        dialog.present();self.refresh_launch_state()

    def open_installer(self):
        if self.editor_kind!='manage' or not self.editor:return
        self.manage_more.popdown()
        if self.installer_dialog:self.installer_dialog.present();return
        candidate=self.collect();state=setup_state(candidate)
        state['reinstall']=state['reinstall'] or setup_state(self.original)['reinstall']
        dialog=modal_window(self.editor,'Reinstall game' if state['reinstall'] else 'Install game',width=640,height=560,subtitle=candidate['title'])
        self.installer_dialog=dialog
        root=dialog_body(dialog)
        content=box();root.append(self.scrolled(content))
        content.append(label('Installer executable','heading',xalign=0))
        self.installer_entry=Gtk.Entry(text=candidate.get('installation',{}).get('installer',''))
        self.installer_entry.update_property([Gtk.AccessibleProperty.LABEL],['Installer executable'])
        content.append(self.installer_entry)
        self.choose_installer_button=button('Choose setup.exe',self.pick_installer);content.append(self.choose_installer_button)
        content.append(label('Installation destination','heading',xalign=0))
        content.append(label('Choose the destination inside the Windows installer. It uses this game’s dedicated prefix. An existing prefix is kept when you start again.','dim-label',wrap=True,xalign=0))
        content.append(label('After setup closes, select and confirm the installed game executable in Game setup. Closing this window keeps an active installation running.','dim-label',wrap=True,xalign=0))
        self.install_status=label('','heading',wrap=True,xalign=0);content.append(self.install_status)
        self.manage_logs=Gtk.TextView(editable=False,cursor_visible=False,wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.manage_logs.update_property([Gtk.AccessibleProperty.LABEL],['Installer activity'])
        logs=Gtk.ScrolledWindow(min_content_height=110);logs.set_child(self.manage_logs);content.append(logs)
        self.install_cancel=button('Cancel installation',lambda:self.confirm('Cancel installation?','Only this installer’s owned processes will stop. Installed files and prefix are kept; you can retry or select an executable later.','Cancel installation',lambda:self.stop_game(candidate['id']),True),'destructive-action')
        footer=dialog_footer();root.append(footer)
        close=button('Back to Setup',self.close_installer);footer.append(close);footer.append(self.install_cancel)
        self.install_button=button('Review reinstall…' if state['reinstall'] else 'Review installation…',self.run_installer,'suggested-action');footer.append(self.install_button)
        dialog.connect('close-request',lambda *_:(self.close_installer(dialog),True)[-1])
        keys=Gtk.EventControllerKey()
        keys.connect('key-pressed',lambda _,key,*args:(self.close_installer(dialog),True)[-1] if key==Gdk.KEY_Escape else False)
        dialog.add_controller(keys)
        dialog.present();self.refresh_launch_state();close.grab_focus()

    def close_installer(self,dialog=None,keep=True):
        current=getattr(self,'installer_dialog',None)
        if not current or (dialog is not None and dialog is not current):return
        if keep:self.installer_draft=self.installer_entry.get_text()
        self.installer_dialog=None;current.destroy()
        if self.editor and self.editor_kind=='manage':self.manage_more.grab_focus()

    def update_install_stage(self):
        if self.editor_kind!='manage':return
        candidate=self.collect();state=setup_state(candidate)
        current=self.launcher.current();active=self.launcher.active();busy=active or self.busy
        own=active and current.get('game_id')==candidate['id'] and current.get('operation')=='installer'
        # An unavailable saved path must never promote a reinstall into a first install.
        reinstall=state['reinstall'] or setup_state(self.original)['reinstall']
        self.install_action.set_label('Installation progress…' if own else 'Reinstall…' if reinstall else 'Install game…')
        status=self.installations.status(candidate)
        self.setup_status.set_text('Installation: '+status['phase'] if own else 'Finish the active operation before changing setup.' if active else state['description'])
        self.confirm_executable_button.set_visible(state['needs_confirmation'])
        self.confirm_executable_button.set_label('Confirm installed game executable' if candidate.get('installation',{}).get('session_id') else 'Use existing game executable')
        self.executable_panel.set_sensitive(not busy);self.proton_section.set_sensitive(not busy);self.advanced.set_sensitive(not busy);self.editor_save.set_sensitive(not busy)
        if self.installer_dialog:
            self.installer_dialog.set_title('Installation progress' if own else 'Reinstall game' if reinstall else 'Install game')
            self.install_button.set_label('Review reinstall…' if reinstall else 'Review installation…')
            self.install_status.set_text(status['phase'])
            self.manage_logs.get_buffer().set_text('\n'.join(status.get('logs',[])[-200:]))
            self.installer_entry.set_sensitive(not busy);self.choose_installer_button.set_sensitive(not busy)
            self.install_button.set_visible(not own);self.install_button.set_sensitive(not self.demo and not busy)
            self.install_cancel.set_visible(own);self.install_cancel.set_sensitive(not self.demo and own and current.get('state')!='Stopping')

    def reset_launch_defaults(self):
        for field in self.launch_fields.values():field.set_text('')
        self.game['launch']={}
        self.notify('Defaults selected in this draft. Installer prefix and runner continuity are preserved.')

    def pick_installer(self):
        dialog=self.installer_dialog;entry=self.installer_entry
        def selected(path):
            if self.installer_dialog is not dialog:return
            entry.set_text(str(path))
            if 'title' in self.fields and not self.fields['title'].get_text():self.fields['title'].set_text(path.parent.name or 'New game')
        self.choose_file('Choose installer',selected,parent=dialog)

    def run_installer(self):
        try:
            if self.editor_kind!='manage' or not self.installer_dialog:return
            if self.demo:raise ValueError('Installer execution is disabled in the demo.')
            if self.busy or self.launcher.active():raise ValueError('Finish the active operation before installing.')
            editor=self.editor;dialog=self.installer_dialog
            candidate=self.collect();config=dict(candidate.get('installation',{}));config['installer']=self.installer_entry.get_text();candidate['installation']=config
            setup=config['installer']
            if not Path(setup).is_absolute() or not Path(setup).is_file():raise ValueError('Choose an existing installer executable.')
            reinstall=setup_state(candidate)['reinstall'] or setup_state(self.original)['reinstall']
            def start():
                if self.editor is not editor or self.installer_dialog is not dialog:return
                try:
                    if self.busy or self.launcher.active():raise ValueError('Finish the active operation before installing.')
                    draft=self.collect();draft['installation']={**draft.get('installation',{}),'installer':self.installer_entry.get_text()}
                    if draft!=candidate:raise ValueError('Setup changed after confirmation. Review the installer again.')
                    saved=self.installations.start(candidate);self.game=saved;self.original=deepcopy(saved);self.refresh_launch_state()
                    self.notify('Installer started. Installed files will be kept if cancelled.')
                except Exception as error:self.error(error)
            explanation='This game already has a setup. Reinstalling may change files through the Windows installer. Check its destination and options.\n\n' if reinstall else ''
            self.confirm('Reinstall this game?' if reinstall else 'Run this installer?',explanation+setup+'\n\nOnly run a trusted installer. You control its license agreements and destination. It uses this game’s dedicated prefix and blocks other launches.','Reinstall' if reinstall else 'Run installer',start,reinstall)
        except Exception as error:self.error(error)

    def confirm_installed(self):
        try:
            candidate=self.collect();config=candidate.get('installation',{})
            if not any(g['id']==candidate['id'] for g in self.library.games()) and getattr(self,'detail_item',None):
                self._save_detail_item_artwork(candidate)
            if config.get('mode')=='installer' and not config.get('session_id'):
                candidate['installation']={**config,'mode':'installed'}
            saved=self.installations.confirm(candidate);self.close_installer();dialog=self.editor;self.editor=None;self.editor_kind=None
            if dialog:dialog.destroy()
            self.show_game(saved);self.notify('Executable confirmed. Play will use this game executable, not setup.')
            self._prompt_clean_installer(saved)
        except Exception as error:self.error(error)

    def progress_items(self,game):
        metadata=bool(game.get('metadata_source') or game.get('metadata_app_id') or (game['title'].strip() and game['description'].strip()))
        executable=bool(game['executable'] and Path(game['executable']).is_file())
        try: build_command(game,self.library.root); ready=game.get('installation',{}).get('mode')!='installer' or game['installation'].get('confirmed',False)
        except ValueError: ready=False
        return zip((metadata,executable,ready),('Game metadata added','Game executable connected','Direct Play configured'))

    def _save_detail_item_artwork(self,candidate):
        item=getattr(self,'detail_item',None)
        if not item or not isinstance(item,dict):return
        images=item.get('images',{})
        art=getattr(self,'detail_art',{})
        for kind in ('portrait','hero'):
            data=None
            cached_path=art.get(kind)
            if cached_path and Path(cached_path).is_file():
                try:data=Path(cached_path).read_bytes()
                except Exception:pass
            url=images.get(kind)
            if not data and url and hasattr(self,'catalog'):
                try:data=self.catalog.image(url).read_bytes()
                except Exception:pass
            if data:
                try:candidate['artwork'][kind]=self.library.add_image(data)
                except Exception:pass

    def _prompt_clean_installer(self,game):
        import shutil
        from .game_uninstall import folder_summary
        installer_file=game.get('installation',{}).get('installer','')
        if not installer_file:return
        p=Path(installer_file)
        if '.umutron-downloads' in p.parts:
            idx=p.parts.index('.umutron-downloads')
            if len(p.parts)>idx+1:
                download_folder=Path(*p.parts[:idx+2])
                if download_folder.is_dir():
                    _,_,size_str=folder_summary(download_folder)
                    def delete_installer():
                        shutil.rmtree(download_folder,ignore_errors=True)
                        self.notify(f'Installer files deleted ({size_str} reclaimed).')
                    self.confirm('Installation Complete',
                                 f"{game['title']} has been successfully installed.\n\n"
                                 f"Would you like to delete the original installer files ({size_str}) to reclaim disk space, or keep them?",
                                 'Delete Installer Files',delete_installer,destructive=True)

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
            installer=self.installer_entry.get_text() if self.installer_dialog else self.installer_draft
            if installer!=game.get('installation',{}).get('installer',''):
                game['installation']={**game.get('installation',{}),'installer':installer}
        if self.description is not None:
            buf=self.description.get_buffer();game['description']=buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False)
        return game

    def dirty(self):return bool(self.editor and self.game is not None and self.collect()!=self.original)

    def go_back(self):
        self.return_from_detail() if self.route=='detail' else self.show_library()

    def close_requested(self,*_):
        if self.exiting:return False
        app=self.get_application();tray=getattr(app,'tray',None)
        if close_action(bool(tray and tray.available))=='hide':self.set_visible(False)
        else:
            self.notify('No tray host is available. '+APP_NAME+' is minimized instead; reopen it from the applications menu. Use Exit to quit.')
            self.minimize()
        return True

    def explicit_exit(self):
        self.present()  # Tray Exit must make its warning reachable while hidden.
        if self.busy or self.proton_manager.busy():
            self.error(ValueError('Finish or cancel metadata/runner work before exiting.'));return
        current=self.launcher.current();active=self.launcher.active()
        body='Exit '+APP_NAME+'?'
        if active:body='An installer or game is active: '+current.get('title','current operation')+'. It will CONTINUE running under its supervisor after Exit. Reopen the launcher to track or stop it. Files, saves and prefixes are kept.'
        if self.dirty():body+=' Unsaved dialog edits will be discarded.'
        def exit_app():
            self.exiting=True;self.catalog_cancel();self.catalog_pool.shutdown(wait=False,cancel_futures=True);self.pool.shutdown(wait=False);app=self.get_application()
            if self.settings_dialog:self.settings_dialog.close()
            self.controller.close()
            if getattr(app,'tray',None):app.tray.close()
            app.quit()
        self.confirm('Exit '+APP_NAME+'?',body,'Exit; keep operation running' if active else 'Exit',exit_app,active or self.dirty())

    def pick_executable(self):
        def selected(path):
            self.fields['executable'].set_text(str(path))
            if not self.fields['working_dir'].get_text(): self.fields['working_dir'].set_text(str(path.parent))
            if 'title' in self.fields and not self.fields['title'].get_text(): self.fields['title'].set_text(path.stem)

        prefix=self.game.get('installation',{}).get('prefix')
        self.choose_file('Choose game executable',selected,start_folder=Path(prefix)/'drive_c' if prefix else None)





    def clear_diagnostic_logs(self):
        def clear_logs():
            try:
                from .diagnostics import clear_all
                count=clear_all(self.library.root);self.notify(f'Cleared {count} diagnostic log files.')
            except Exception as error:self.error(error)
        self.confirm('Clear all diagnostic logs?','Deletes diagnostic log files only. Game files, saves, prefixes and artwork are kept.','Clear all',clear_logs,True)

    def open_settings(self,section=None):
        if self.tv_mode and section!='storage':self.notify('Switch to desktop mode to manage settings.');return
        if self.settings_dialog and self.settings_dialog.get_visible():
            if section=='storage':self.settings_dialog.set_visible_page(self.storage_settings_page)
            elif section=='sources':self.settings_dialog.set_visible_page(getattr(self,'sources_settings_page',self.storage_settings_page))
            self.settings_dialog.present();return self.settings_dialog
        dialog=Adw.PreferencesWindow(title='Settings',transient_for=self,modal=True,default_width=min(660,max(520,self.get_width()-48)),default_height=min(740,max(440,self.get_height()-48)))
        style_surface(dialog,self);self.settings_dialog=dialog
        def clear_settings(owner):
            if self.settings_dialog is owner:self.settings_dialog=None;self.storage_settings_page=None;self.sources_settings_page=None
            for name in ('proton_panel','proton_settings_page','default_mode_choice'):
                control=getattr(self,name,None)
                if control is not None and control.get_root() is owner:
                    if name=='proton_panel':control.alive=False;control.dialog=None
                    setattr(self,name,None)
            return False
        dialog.connect('close-request',clear_settings);dialog.connect('unrealize',clear_settings)
        self.storage_settings_page=StoragePage(self.storage_service,dialog);dialog.add(self.storage_settings_page)
        from .settings_sources import SourcesPage
        self.sources_settings_page=SourcesPage(self.library,self);dialog.add(self.sources_settings_page)
        if section=='storage' and self.tv_mode:
            dialog.set_title('Storage');dialog.present();return
        if section=='sources' and self.tv_mode:
            dialog.set_title('Sources');dialog.present();return
        page=Adw.PreferencesPage(title='General',icon_name='preferences-system-symbolic');dialog.add(page)
        modes=Adw.PreferencesGroup(title='Display mode',description='Default mode applies on the next app start. Enter fullscreen from the mode button; leave through fullscreen options or the tray.');page.add(modes)
        mode_row=Adw.ActionRow(title='Default launch mode');self.default_mode_choice=Gtk.DropDown.new_from_strings(['Desktop','Fullscreen / TV']);self.default_mode_choice.set_selected(1 if self.library.data['settings'].get('default_display_mode')=='fullscreen' else 0);mode_row.add_suffix(self.default_mode_choice);modes.add(mode_row)
        self.default_mode_choice.connect('notify::selected',lambda choice,_:self.library.set_default_display_mode('fullscreen' if choice.get_selected()==1 else 'desktop'))
        from .launcher import gamemode_binary
        gm_available=gamemode_binary() is not None
        gm_row=Adw.ActionRow(title='Feral GameMode',subtitle='Automatically optimize CPU governor, GPU performance, and process priorities while gaming, then revert on exit.' if gm_available else 'GameMode not installed (gamemoderun not found).')
        gm_switch=Gtk.Switch(active=bool(self.library.data.get('settings',{}).get('gamemode',True) and gm_available),valign=Gtk.Align.CENTER)
        gm_switch.set_sensitive(gm_available)
        gm_switch.connect('notify::active',lambda switch,_:self.library.set_gamemode(switch.get_active()))
        gm_row.add_suffix(gm_switch);modes.add(gm_row)
        page.add(Adw.PreferencesGroup(title=APP_NAME+' '+__version__,description='Standalone UMU/Proton game and installer library.'))
        appearance=Adw.PreferencesGroup(title='Appearance',description='Choose how the app looks.'); page.add(appearance)
        theme_row=Adw.ActionRow(title='Theme')
        theme=Gtk.DropDown.new_from_strings(['Follow system','Light','Dark']); theme.set_valign(Gtk.Align.CENTER)
        theme.set_selected(self.theme.get_selected())
        theme.connect('notify::selected',lambda dropdown,_:self.theme.set_selected(dropdown.get_selected()))
        theme_row.add_suffix(theme); appearance.add(theme_row)
        scale_row=Adw.ActionRow(title='UI Scale',subtitle='Adjust interface sizing for desktop monitors vs large 55\" 4K TVs.')
        scale_labels=['Auto (Recommended)','100% (Standard Monitor)','125%','150% (55\" TV Recommended)','175%','200% (4K TV Large)']
        scale_values=['auto','100','125','150','175','200']
        scale_choice=Gtk.DropDown.new_from_strings(scale_labels);scale_choice.set_valign(Gtk.Align.CENTER)
        cur_scale=self.library.data.get('settings',{}).get('ui_scale','auto')
        scale_choice.set_selected(scale_values.index(cur_scale) if cur_scale in scale_values else 0)
        def scale_selected(dropdown,_):
            val=scale_values[dropdown.get_selected()]
            self.library.set_ui_scale(val)
            self.update_scale_classes()
            if self.route=='detail' and self.game:self.show_shared_detail(self.game,self.detail_item)
            elif self.route=='store':self.show_store(restore=True)
            elif self.route=='home':self.show_home()
            else:self.show_library()
        scale_choice.connect('notify::selected',scale_selected)
        scale_row.add_suffix(scale_choice);appearance.add(scale_row)
        diagnostics=Adw.PreferencesGroup(title='Diagnostic logs',description='One local folder per game. Completed logs: 8 MiB per file, 100 MiB total, 14-day retention. Cleanup runs before and after launches; active logs are never cleared.');page.add(diagnostics)
        settings_ref=dialog.weak_ref()
        def show_activity():
            owner=settings_ref()
            if owner is None or not owner.get_visible():return
            owner.close()
            self.log_revealer.set_reveal_child(True)
        diagnostics.add(button('Activity',show_activity))
        diagnostics.add(button('Clear all diagnostic logs',self.clear_diagnostic_logs,'destructive-action'))
        backup=Adw.PreferencesGroup(title='Backup and restore',description='Portable metadata, artwork and appearance. Game files, saves and provider credentials are not included.'); page.add(backup)
        def leave_then(callback):
            owner=settings_ref()
            if owner is not None and owner.get_visible():owner.close();callback()
        for title,subtitle,action,callback in (
            ('Export library','Create a ZIP backup of the saved library.','Export ZIP',self.export_backup),
            ('Import library','Preview new entries and conflicts before restoring.','Import ZIP',self.import_backup)):
            row=Adw.ActionRow(title=title,subtitle=subtitle)
            control=button(action,lambda c=callback:leave_then(c)); control.set_valign(Gtk.Align.CENTER)
            row.add_suffix(control); backup.add(row)
        self.build_proton_manager_tab(dialog)
        catalog_info=Adw.PreferencesGroup(title='Store',description='Game data by IGDB. Catalog service configuration is separate from game setup; your saved library works offline.');page.add(catalog_info)
        catalog_info.add(Gtk.LinkButton.new_with_label('https://www.igdb.com','IGDB'))
        target_page=self.storage_settings_page if section=='storage' else self.sources_settings_page if section=='sources' else page
        dialog.set_visible_page(target_page)
        dialog.present()

    def build_proton_manager_tab(self,dialog):
        from .proton_ui import ProtonPanel
        page=Adw.PreferencesPage(title='Proton Manager',icon_name='application-x-executable-symbolic');dialog.add(page);self.proton_settings_page=page
        group=Adw.PreferencesGroup();page.add(group)
        self.proton_panel=ProtonPanel(self,dialog);group.add(self.proton_panel)



    def delete_game(self):
        self.remove_detail()

    def build_advanced(self,page):
        settings=self.game.get('launch',{})
        for key,title,hint in (('runner','UMU executable','Blank discovers umu-run on your PATH.'),('proton','Custom Proton path or policy','Use the Proton version selector for normal choices. Existing UMU-Latest and GE-Latest policies remain supported.'),('prefix','Dedicated prefix folder','Blank creates a per-game prefix in app data. Existing unrelated prefixes are preserved.')):
            page.append(label(title,'heading',xalign=0));entry=Gtk.Entry(text=settings.get(key,''));self.launch_fields[key]=entry;page.append(entry)
            page.append(label(hint,'caption',wrap=True,xalign=0))
            if key!='proton':page.append(button('Choose '+title.lower(),lambda k=key:self.choose_file('Choose '+k,lambda p:self.launch_fields[k].set_text(str(p)),folder=k=='prefix')))
            else:page.append(button('Choose custom Proton folder',lambda:self.choose_file('Choose Proton',lambda p:self.launch_fields['proton'].set_text(str(p)),folder=True)))

        page.append(label('DLL compatibility overrides','heading',xalign=0))
        overrides=Gtk.Entry(text=settings.get('dll_overrides',''),placeholder_text='Example: winmm=n,b')
        self.launch_fields['dll_overrides']=overrides;page.append(overrides)
        page.append(label('Only apply a verified fix for this game. n = supplied/native DLL, b = Wine built-in, d = disabled. Separate entries with semicolons. Blank keeps the existing prefix defaults.','caption',wrap=True,xalign=0))

    def open_diagnostic_logs(self):
        folder=self.library.root/'diagnostics'/self.game['id']
        if not folder.is_dir():self.notify('No diagnostic logs yet. Logs are recorded automatically when you play or install.');return
        try:Gio.AppInfo.launch_default_for_uri(folder.as_uri(),None)
        except Exception as error:self.error(error)

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
            if not configured_game(game):
                if self.tv_mode:self.notify('Set up this game in desktop mode before playing.');return
                self.show_game(game);self.open_manage();return
            if self.demo:raise ValueError('Play is disabled in the demo. Synthetic game files are inert.')
            settings=defaults(game,self.library.root)
            game=deepcopy(game);game['launch']=settings
            build_command(game,self.library.root,allow_prepare=True)
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
        if getattr(self,'route',None)=='home' and not self.editor and self.navigation_window() is self:
            from .play_history import revision
            if revision(self.library.root)!=getattr(self,'home_history_revision',None):
                focus=self.get_focus()
                action=next((name for name in ('tv_play','tv_open') if focus is not None and focus is getattr(self,name,None)),None)
                self.show_home()
                if action and hasattr(self,action):getattr(self,action).grab_focus()
                elif focus and focus.get_root() is self:focus.grab_focus()
        self.update_focus_outline()
        current=self.launcher.current();active=self.launcher.active();active_id=current.get('game_id')
        selected_id=self.game['id'] if self.game else self.tv_selected_id if self.tv_mode and self.tv_section=='games' else None
        preparing_runtime=active and active_id==selected_id and current.get('state') in ('Preparing','Downloading runtime')
        if self.tv_mode:
            choices=getattr(self,'tv_games',[])+(getattr(self,'home_setup_games',[]) if self.route=='home' else [])
            entry=self.game or next((g for g in choices if g['id']==selected_id),{})
            configured=configured_game(entry)
            status=current.get('state','') if active and active_id==selected_id else ('Another game is active' if active else '' if configured else 'Set up in desktop mode to play')
            status_label=getattr(self,'console_status' if self.game else 'tv_launch_status',None)
            if status_label:status_label.set_text(status)
        self.runtime_progress.set_visible(preparing_runtime)
        if preparing_runtime:
            self.runtime_spinner.start();info=preparation_progress(current)
            amount=(f" · {info['bytes']/1048576:.1f} MiB downloaded" if info['bytes'] is not None else ' · Waiting for UMU progress')
            self.runtime_label.set_text(info['stage']+amount)
        else:self.runtime_spinner.stop()
        for game_id,control in self.play_buttons.items():
            own=active and active_id==game_id;stopping=own and current.get('state')=='Stopping'
            preparing=own and current.get('state')=='Preparing' and not current.get('supervisor_pid')
            installer=own and current.get('operation') in ('installer','runtime')
            entry=next((g for g in self.library.games() if g['id']==game_id),self.game or {})
            configured=configured_game(entry)
            if own:control.add_css_class('destructive-action')
            else:control.remove_css_class('destructive-action')
            detail=getattr(self,'route',None)=='detail' and self.game and self.game['id']==game_id
            setup_needed=detail and not configured and not own
            control.set_label('Preparing…' if preparing else 'Stopping…' if stopping else ('Stop installer' if installer else 'Stop' if own else 'Play' if configured else 'Open desktop Setup' if self.tv_mode and detail else 'Setup'))
            checking=getattr(self,'detail_availability_checking',False) if detail else False
            control.set_sensitive(not checking and not self.demo and not stopping and not preparing and (not active or own) and (not self.tv_mode or configured or own or setup_needed))
            control.set_tooltip_text(('Active: '+current.get('title','game')+'. Finish it before starting another.') if active and not own else 'Stop this game' if own else 'Play through UMU' if configured else 'Switch to desktop mode to set up this game' if self.tv_mode else 'Set up existing game files or a local installer')
            if setup_needed and not active:
                self.detail_status.set_text('Open desktop Setup to choose your game files or a local installer.' if self.tv_mode else 'Set up your existing game files or choose a local installer.')
        if (getattr(self,'route',None)=='detail' and self.game and hasattr(self,'detail_primary')
                and not configured_game(self.game)
                and not (hasattr(self,'detail_download_box') and self.detail_download_box.get_visible())):
            checking=getattr(self,'detail_availability_checking',False)
            adding=getattr(self,'detail_adding',False)
            self.detail_primary.set_sensitive(
                not checking and not adding and not self.demo and not active)
        if self.tv_mode and self.game is None and hasattr(self,'tv_hints'):
            status=' · '+self.controller.name if hasattr(self,'controller') and self.controller.name else ''
            self.tv_hints.set_text('← ↑ ↓ → / D-pad  Browse     Enter / A  View game     Esc / B  Back     X  Focus Play / Stop     F11 / Start  Options'+status)
        if self.game is not None and hasattr(self,'launch_output'):
            if self.detail_install_status is not None:self.detail_install_status.set_text('Installation: '+self.installations.status(self.game)['phase'])
            state=self.launcher.snapshot(self.game['id'])
            text='\n'.join(state.get('logs',[])[-200:])
            if text!=getattr(self,'last_launch_output',None):self.launch_output.get_buffer().set_text(text);self.last_launch_output=text
        if self.editor_kind=='manage':self.update_install_stage()
        return True

    def export_backup(self):
        def selected(path):
            if path.suffix.lower()!='.zip': raise ValueError('Use a filename ending in .zip.')
            self.async_job('Exporting metadata and artwork backup…',lambda:self.library.export_zip(path),lambda _:self.notify('ZIP backup exported. Game files, prefixes and credentials are not included.'))
        self.choose_file('Export library backup',selected,save=True,filename='game-library-backup.zip')

    def import_backup(self):
        def selected(path):
            def preview(result):
                dialog=message_dialog(self,'Import backup?',f"{result['new']} new games and {result['conflicts']} existing games.\n\n"+'\n'.join(result['titles'][:12])+'\n\nChoose how to handle conflicts. Import never starts a game.',
                    responses=(('cancel','Cancel'),('keep','Keep existing'),('replace','Replace conflicts')),
                    default='cancel',close='cancel',destructive='replace')
                def response(_,choice):
                    if choice in ('keep','replace'):
                        self.async_job('Restoring local library…',lambda:self.library.import_zip(path,choice),lambda _:(self.show_library(),self.notify('Backup imported locally. Review paths before playing.')))
                dialog.connect('response',response); dialog.present()
            self.async_job('Validating backup…',lambda:self.library.preview_import(path),preview)
        self.choose_file('Import library backup',selected)



class Application(Adw.Application):
    def __init__(self,demo=False):
        self.demo=demo
        app_id=APP_ID+('.demo' if demo else '')
        GLib.set_prgname(app_id)  # GTK uses this as the X11 WM_CLASS instance.
        GLib.set_application_name(APP_NAME)
        Gtk.Window.set_default_icon_name(ICON_NAME)
        super().__init__(application_id=app_id,flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
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
            self.tray=Tray(self.activate_window,window.explicit_exit,availability,lambda:switch_mode(True),lambda:switch_mode(False),lambda:desktop_action(window.open_settings),mode=window.is_fullscreen)
            window.connect('notify::fullscreened',self.tray.sync_mode)
        window.present()
        if isinstance(window,Window) and window.editor:window.editor.present()


def main():
    demo='--demo' in sys.argv
    args=[arg for arg in sys.argv if arg!='--demo']
    return Application(demo).run(args)
