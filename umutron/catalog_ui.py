"""Native Library / Store routes and one shared, state-driven detail page."""
from copy import deepcopy
import time
import os
from pathlib import Path
import re
from gi.repository import Adw, Gdk, GLib, Gtk, Pango

from .catalog import CatalogService, configured_catalog, add_item, item_game, members, related_members, entity_label, validate_item, needs_membership_lookup, MAX_PAGE
from .collection import library_page, page_numbers
from .browse_controls import BrowseChoice
from .dialogs import style_surface, modal_window, dialog_body, dialog_footer
from .catalog_work import CatalogWork
from .download_service import configured_game
from .sources.model import source_link_kind
from .fullscreen import cover as console_cover, set_art, CoverPicture, CoverLayout
from .library import description_excerpt

CSS = b'''
.collection-page { padding: 24px 32px; }
.collection-heading { font-size: 30px; font-weight: 800; }
.collection-card { padding: 7px; border-radius: 12px; background: alpha(@window_fg_color,.045); border: 2px solid transparent; outline: none; }
.collection-card:hover { background: alpha(@accent_color,.12); border-color: alpha(#85efd4,.5); }
.collection-card:focus, .collection-card.control-focused { border-color: #85efd4; outline: none; }
.collection-card.game-ready { border: 2px solid transparent; }
.collection-card.game-ready:hover, .collection-card.game-ready:focus, .collection-card.game-ready.control-focused { border-color: #85efd4; outline: none; }
.collection-card.game-not-ready { border: 2px solid transparent; }
.collection-card.game-not-ready:hover, .collection-card.game-not-ready:focus, .collection-card.game-not-ready.control-focused { border-color: #f0b74d; outline: none; }
.collection-page .browse-search.control-focused { outline: 3px solid #7de8d3; outline-offset: 2px; }
.collection-title { font-size: 16px; font-weight: 700; }
.collection-badge { font-size: 12px; color: #70cebb; }
.collection-kind { font-size: 14px; font-weight: 500; }
.tv-mode .collection-kind { font-size: 16px; }
.shared-detail { padding: 28px; border-radius: 20px; background: alpha(@window_bg_color,.91); }
.detail-title { font-size: 34px; font-weight: 800; }
.detail-copy { font-size: 17px; line-height: 1.45; }
.detail-primary { padding: 12px 24px; font-size: 18px; font-weight: 800; }
.detail-primary.suggested-action { background: #82e9d0; color: #102a29; }
.tv-mode .collection-heading { font-size: 36px; }
.tv-mode .collection-title { font-size: 18px; }
.tv-mode .collection-page { padding: 24px 48px; }
.tv-mode .shared-detail { background: alpha(#0e1422,.94); }
.tv-mode .detail-title { font-size: 42px; }
.tv-mode .shared-detail { background: alpha(#0d1523,.86); border: 1px solid alpha(#b4c7e5,.10); padding: 30px; }
.tv-mode .shared-detail .detail-title { font-size: 46px; letter-spacing: -1px; line-height: 1.06; }
.tv-mode .shared-detail .detail-copy { color: #d5ddea; font-size: 20px; line-height: 1.4; }
.tv-mode .shared-detail .detail-meta { color: #acb9ce; font-size: 17px; opacity: 1; }
.tv-mode.tv-compact .shared-detail { padding: 22px; }
.tv-mode.tv-compact .shared-detail .detail-title { font-size: 34px; }
.tv-mode.tv-compact .shared-detail .detail-copy { font-size: 17px; }
.tv-mode .collection-card { background: #141d2b; padding: 7px; border-radius: 12px; }
.collection-page.collection-compact { padding-top: 14px; padding-bottom: 14px; }
.collection-pager button { min-width: 20px; padding: 8px 12px; }
.tv-mode .collection-pager button { min-height: 32px; }
.collection-pager .current-page { background: #82e9d0; color: #102a29; opacity: 1; }
.collection-short .collection-card { padding: 7px; }
.browse-choice { border-radius: 10px; }
.browse-choice.control-focused > button:focus { outline: none; }
.browse-choice popover button.suggested-action { background: #ceeae3; color: #155448; }
.desktop-dark .browse-choice popover button.suggested-action,
.tv-mode .browse-choice popover button.suggested-action { background: #243d44; color: #85efd4; }
.scale-large .collection-page { padding: 32px 48px; }
.scale-large .collection-heading { font-size: 42px; }
.scale-large .collection-title { font-size: 22px; }
.scale-large .collection-kind { font-size: 18px; }
.scale-large .collection-badge { font-size: 15px; }
.scale-large .shared-detail { padding: 38px; border-radius: 24px; }
.scale-large .detail-title { font-size: 54px; }
.scale-large .detail-copy { font-size: 22px; }
.scale-large .detail-meta { font-size: 20px; }
.scale-large .detail-primary { padding: 14px 30px; font-size: 21px; }

.scale-xlarge .collection-page { padding: 40px 64px; }
.scale-xlarge .collection-heading { font-size: 52px; }
.scale-xlarge .collection-title { font-size: 26px; }
.scale-xlarge .collection-kind { font-size: 21px; }
.scale-xlarge .collection-badge { font-size: 18px; }
.scale-xlarge .shared-detail { padding: 48px; border-radius: 28px; }
.scale-xlarge .detail-title { font-size: 66px; }
.scale-xlarge .detail-copy { font-size: 26px; }
.scale-xlarge .detail-meta { font-size: 24px; }
.scale-xlarge .detail-primary { padding: 18px 38px; font-size: 25px; }


/* Desktop keeps native density and theme choice, with the console's identity. */
.desktop-mode { background: #f3f6f8; color: #172b36; }
.desktop-mode.desktop-dark { background: #0e1520; color: #edf3ff; }
.desktop-mode .desktop-header { background: #e9eff2; box-shadow: inset 0 -1px alpha(#172b36,.08); }
.desktop-mode.desktop-dark .desktop-header { background: #101b29; box-shadow: inset 0 -1px alpha(#b4c7e5,.10); }
.desktop-mode .desktop-nav { border-radius: 10px; padding-left: 16px; padding-right: 16px; }
.desktop-mode .desktop-nav.suggested-action { background: #ceeae3; color: #155448; }
.desktop-mode.desktop-dark .desktop-nav.suggested-action { background: #243d44; color: #85efd4; }
.desktop-mode .collection-card { background: #e7edf1; }
.desktop-mode .collection-card:hover { background: #d6e7e5; }
.desktop-mode.desktop-dark .collection-card { background: #192434; }
.desktop-mode.desktop-dark .collection-card:hover { background: #243749; }
.desktop-mode .collection-badge { color: #23675b; }
.desktop-mode.desktop-dark .collection-badge { color: #85d9c7; }
.desktop-mode .control-focused, .desktop-mode button:focus-visible,
.desktop-mode .collection-page .browse-search.control-focused { outline: 3px solid #267c6c; outline-offset: 2px; }
.desktop-mode.desktop-dark .control-focused, .desktop-mode.desktop-dark button:focus-visible,
.desktop-mode.desktop-dark .collection-page .browse-search.control-focused { outline-color: #a6f5df; }
.desktop-mode .home-surface .control-focused, .desktop-mode .home-surface button:focus-visible { outline-color: #b3ffe9; }
.desktop-mode .shared-detail { background: alpha(#f5f8fa,.96); border: 1px solid alpha(#29465b,.12); }
.desktop-mode.desktop-dark .shared-detail { background: alpha(#101b29,.94); border-color: alpha(#b4c7e5,.12); }
.desktop-mode .detail-meta { opacity: 1; color: #506373; }
.desktop-mode.desktop-dark .detail-meta { color: #acb9ce; }
.desktop-mode .detail-primary { min-width: 96px; }
.desktop-mode .shared-detail button:not(.detail-primary) { min-height: 26px; }
.desktop-mode .shared-detail menubutton { border-radius: 10px; }
.desktop-mode .shared-detail menubutton.control-focused > button:focus { outline: none; }

/* Detail uses the same artwork-led composition in both display modes. Native
   desktop chrome and Settings retain the selected light/dark appearance. */
.desktop-mode .detail-surface { background: #0b101a; color: #f3f6ff; }
.desktop-mode .detail-scrim { background: linear-gradient(90deg, #0b101a 0%, alpha(#0b101a,.90) 25%, alpha(#0b101a,.12) 78%), linear-gradient(0deg, #0b101a 0%, alpha(#0b101a,.04) 65%, alpha(#0b101a,.30) 100%); }
.desktop-mode .detail-surface .shared-detail { background: alpha(#0d1523,.86); border: 1px solid alpha(#b4c7e5,.10); padding: 30px; }
.desktop-mode .detail-surface .detail-title { font-size: 46px; letter-spacing: -1px; line-height: 1.06; color: #f3f6ff; }
.desktop-mode .detail-surface .detail-copy { color: #d5ddea; font-size: 20px; line-height: 1.4; }
.desktop-mode .detail-surface .detail-meta { color: #acb9ce; font-size: 17px; opacity: 1; }
.desktop-mode .detail-surface.detail-compact .shared-detail { padding: 22px; }
.desktop-mode .detail-surface.detail-compact .detail-title { font-size: 34px; }
.desktop-mode .detail-surface.detail-compact .detail-copy { font-size: 17px; }
.desktop-mode .detail-surface .tv-cover { background: #202b3c; border-radius: 7px; }
.desktop-mode .detail-surface button { min-height: 30px; padding: 8px 16px; border-radius: 12px; font-size: 18px; font-weight: 600; background: #232f40; color: #edf3ff; }
.desktop-mode .detail-surface .detail-primary.suggested-action { background: #82e9d0; color: #102a29; font-weight: 800; }
.desktop-mode .detail-surface .detail-primary.destructive-action { background: #f8aaad; color: #451316; }
.desktop-mode .detail-surface button:disabled { background: #33464a; color: #9aabaa; opacity: 1; }
.desktop-mode .detail-surface button:hover { background: #314355; }
.desktop-mode .detail-surface .detail-primary.suggested-action:hover { background: #a0f1dc; }
.tv-mode .shared-detail .detail-primary.destructive-action, .desktop-mode .detail-surface .detail-primary.destructive-action { background: #f8aaad; color: #451316; }
.tv-mode .shared-detail .detail-primary.destructive-action:hover, .desktop-mode .detail-surface .detail-primary.destructive-action:hover { background: #ffc1c2; color: #451316; }
.desktop-mode .detail-surface .control-focused, .desktop-mode .detail-surface button:focus-visible { outline: 3px solid #b3ffe9; outline-offset: 3px; box-shadow: 0 0 0 6px alpha(#0b101a,.72); }
'''


def ui():
    # Loaded lazily: app owns common widget helpers and the concrete Window.
    from .app import box, button, label, margins, clear
    return box,button,label,margins,clear


def update_cover(frame,path):
    picture=CoverPicture(content_fit=Gtk.ContentFit.COVER,can_shrink=True,hexpand=True,vexpand=True)
    if set_art(picture,path,480,720):
        while frame.get_first_child():frame.remove(frame.get_first_child())
        frame.append(picture)
        return True
    return False


class CatalogUI:
    def init_catalog(self,provider=None):
        if provider is None:provider=configured_catalog()
        self.catalog=CatalogService(provider,self.library.root/'catalog-cache')

        self.catalog_pool=CatalogWork()
        self.store_item_futures=[];self.store_render_revision=0
        self.catalog_futures=[];self.catalog_generation=0;self.route='library';self.detail_origin='library'
        self.routes={'library':{'query':'','page':1,'genre':None,'sort':0,'scroll':0,'focus':None},
                     'store':{'query':'','page':1,'genre':None,'sort':'popular','scroll':0,'focus':None}}
        self.catalog_genres=[];self.detail_item=None;self.detail_art={}
        from .game_uninstall import GameUninstall
        self.game_uninstall=GameUninstall(self.library)

    def reconnect_catalog(self):
        """Recreate the provider after the local server starts/changes."""
        old=getattr(self,'catalog_pool',None)
        self.catalog_cancel()
        if old is not None:
            try:old.shutdown(wait=False,cancel_futures=True)
            except TypeError:old.shutdown(False)
        self.init_catalog()
        self.show_collection()

    def collection_card_dimensions(self):
        if hasattr(self, 'console_dimensions'):
            return self.console_dimensions()
        scale=getattr(self,'ui_scale_factor',lambda:1.0)()
        w=self.get_width() if hasattr(self,'get_width') and self.get_width()>0 else 1920
        if w>=2400:base_w=180
        elif w<1200:base_w=136
        else:base_w=152
        return (int(base_w*scale),int(base_w*1.5*scale))

    def catalog_cancel(self):
        self.catalog_generation+=1
        for future in self.catalog_futures:future.cancel()
        self.catalog_futures=[];self.store_item_futures=[]

    def catalog_job(self,work,done,failed=None,*,image=False,source=False,background=False,valid=None):
        generation=self.catalog_generation
        future=(self.catalog_pool.submit_source(work) if source else
                self.catalog_pool.submit_image(work) if image else
                self.catalog_pool.submit(work,background=background))
        self.catalog_futures.append(future)
        def finish():
            if future in self.catalog_futures:self.catalog_futures.remove(future)
            if future.cancelled() or generation!=self.catalog_generation or self.exiting or (valid is not None and not valid()):return False
            try:done(future.result())
            except Exception as error:
                if failed:failed(error)
                else:self.notify(str(error))
            return False
        future.add_done_callback(lambda _:GLib.idle_add(finish))
        return future

    def capture_route(self):
        if self.route in self.routes and hasattr(self,'collection_scroll'):
            self.routes[self.route]['scroll']=self.collection_scroll.get_vadjustment().get_value()

    def begin_route(self,route):
        self.capture_route()
        self.catalog_cancel();self.route=route
        _,_,_,_,clear=ui();clear(self.body)
        self.game=None;self.original=None;self.detail_item=None;self.fields={};self.launch_fields={};self.description=None
        self.play_buttons={};self.tv_tiles=[];self.tv_section='library';self.body.remove_css_class('home-surface')
        self.back.set_visible(False);self.backdrop.set_paintable(None)
        self.heading.set_title('UmuTron');self.heading.set_subtitle('Your games · UMU and Proton')
        for control,key in ((self.tv_home_tab,'home'),(self.home_nav,'home'),(self.tv_library_tab,'library'),(self.tv_games_tab,'store'),(self.library_nav,'library'),(self.store_nav,'store')):
            control.remove_css_class('tv-tab-active')
            if route==key:control.add_css_class('tv-tab-active' if self.tv_mode else 'suggested-action')
            else:control.remove_css_class('suggested-action')

    def collection_shell(self,route):
        box,button,label,margins,_=ui();self.begin_route(route);state=self.routes[route]
        page=box(spacing=16);page.add_css_class('collection-page');self.collection_heading=page
        title='Your library' if route=='library' else 'Discover your next game'
        page.append(label(title,'collection-heading',xalign=0))
        subtitle=label('Every game, one place. Pick up where you left off.' if route=='library' else 'Explore the catalog. Save a game, then set up your own files.','dim-label',xalign=0,wrap=True);page.append(subtitle)
        toolbar=box(False,12);page.append(toolbar)
        search_row=box(False,12);search_row.set_hexpand(True);toolbar.append(search_row)
        self.collection_search=Gtk.SearchEntry(placeholder_text='Search your library' if route=='library' else 'Search games',hexpand=True)
        self.collection_search.add_css_class('browse-search')
        self.collection_search.set_text(state['query']);search_row.append(self.collection_search)
        search=self.collection_search
        def search_changed(*_):
            if self.route==route and self.collection_search is search:self.collection_search_changed()
        def search_cleared(*_):
            if self.route==route and self.collection_search is search:
                if not self.collection_search.get_text().strip() and state['query']:
                    self.collection_search_changed()
        self.collection_search.connect('activate',search_changed)
        self.collection_search.connect('search-changed',search_cleared)
        self.collection_search.connect('stop-search',lambda *_:search.set_text(''))
        self.collection_search_button=button('Search',search_changed);search_row.append(self.collection_search_button)
        filters=box(False,12);toolbar.append(filters)
        def resize_toolbar(widget,clock):
            if self.collection_toolbar is not filters or self.route!=route:return False
            compact=self.get_width()<1180 or (self.tv_mode and self.get_width()<1440)
            toolbar.set_orientation(Gtk.Orientation.VERTICAL if compact else Gtk.Orientation.HORIZONTAL)
            filters.set_halign(Gtk.Align.START if compact else Gtk.Align.END)
            short=self.get_height()<700
            subtitle.set_visible(not short);page.set_spacing(10 if short else 16)
            if short:page.add_css_class('collection-compact')
            else:page.remove_css_class('collection-compact')
            if self.tv_mode:
                if self.get_width()<1400 or self.get_height()<850:self.add_css_class('tv-compact')
                else:self.remove_css_class('tv-compact')
            if short:self.collection_flow.add_css_class('collection-short')
            else:self.collection_flow.remove_css_class('collection-short')
            scale=getattr(self,'ui_scale_factor',lambda:1.0)()
            inset=64 if scale>1.55 else 48 if scale>1.15 or self.tv_mode else 32
            self.collection_flow.set_margin_start(inset);self.collection_flow.set_margin_end(inset)
            card_w,card_h=self.collection_card_dimensions()
            card_key=(card_w,card_h,short)
            for _,tile in self.tv_tiles:
                if getattr(tile,'collection_card_state',None)==card_key:continue
                tile.collection_card_state=card_key
                tile.console_width=card_w
                tile.queue_resize()
                tile.console_cover.set_size_request(card_w,card_h)
                tile.console_cover.set_halign(Gtk.Align.CENTER)
                tile.console_title.set_size_request(card_w,int(48*scale))
                badge_text=tile.collection_badge.get_text() if hasattr(tile,'collection_badge') else ''
                tile.collection_badge.set_visible(bool(badge_text) and not short)
            size=(self.get_width(),self.get_height())
            if getattr(toolbar,'browse_size',None)!=size:
                toolbar.browse_size=size
                # The same card can remain focused across a column/height
                # change. Recheck its visibility after native layout settles.
                self.reveal_browse_control(self.focused_control(self))
            return True
        toolbar.add_tick_callback(resize_toolbar)
        self.collection_status=label('','dim-label',xalign=0,wrap=True);page.append(self.collection_status)
        is_tv = getattr(self, 'tv_mode', False)
        self.collection_flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,min_children_per_line=1,max_children_per_line=12,column_spacing=20 if is_tv else 16,row_spacing=24 if is_tv else 20)
        self.collection_flow.set_valign(Gtk.Align.START)
        self.collection_flow.set_halign(Gtk.Align.START)
        self.collection_flow.set_margin_start(48 if is_tv else 24);self.collection_flow.set_margin_end(48 if is_tv else 24)
        # Let the heading/search scroll with the cards. A fixed toolbar can
        # otherwise leave less room than one complete card in a short window.
        content=box(spacing=0);content.append(page);content.append(self.collection_flow)
        self.collection_scroll=self.scrolled(content);self.body.append(self.collection_scroll)
        # App-owned reveal handles both directions and cancellation. GTK's
        # animated focus scroll must not race a newer navigation destination.
        self.collection_scroll.get_child().set_scroll_to_focus(False)
        footer=box(spacing=8);margins(footer,12);self.body.append(footer)
        pager=box(False,8);pager.add_css_class('collection-pager');pager.set_halign(Gtk.Align.CENTER);footer.append(pager)
        self.first_page=button('First',lambda:self.collection_go_page(1));pager.append(self.first_page)
        self.previous_page=button('Previous',lambda:self.collection_page(-1));pager.append(self.previous_page)
        self.collection_numbers=box(False,6);pager.append(self.collection_numbers)
        self.next_page=button('Next',lambda:self.collection_page(1));pager.append(self.next_page)
        self.last_page=button('Last',lambda:self.collection_go_page(self.collection_total_pages));pager.append(self.last_page)
        caption=box(False,12);footer.append(caption)
        self.collection_page_label=label('',hexpand=True,wrap=True);caption.append(self.collection_page_label)
        if route=='store':
            caption.append(Gtk.LinkButton.new_with_label('https://www.igdb.com','Game data by IGDB'))
        self.collection_tiles={};self.collection_toolbar=filters;self.collection_total_pages=None;self.collection_pager_state=None
        return state

    def show_collection(self):
        self.collection_shell('library')
        self.render_collection()

    def browse_toolbar_focus(self,action):
        """Ordered toolbar stops, with spatial navigation retained in the grid."""
        if self.route not in self.routes:return False
        current=self.focused_control(self)
        controls=[self.collection_search,self.collection_search_button]
        if self.route=='store':
            controls.extend([getattr(self,'collection_genre',None),getattr(self,'collection_sort',None)])
        controls=[control for control in controls if control is not None and control.get_mapped() and control.is_sensitive()]
        tiles=[tile for _,tile in self.tv_tiles if tile.get_mapped() and tile.is_sensitive()]
        if current in controls:
            forward=action in ('down','right','next');backward=action in ('up','left','previous')
            if not forward and not backward:return False
            index=controls.index(current)+(1 if forward else -1)
            if index<0:self.focus_browse_route()
            elif index<len(controls):controls[index].grab_focus()
            elif tiles:tiles[0].grab_focus()
            self.update_focus_outline();return True
        if current in tiles and controls:
            first=tiles[0]
            same_row=False
            if action=='up':
                valid,a=current.compute_bounds(self.collection_flow);other,b=first.compute_bounds(self.collection_flow)
                same_row=valid and other and abs(a.get_y()-b.get_y())<2
            if same_row or (current is first and action in ('left','previous')):
                controls[-1].grab_focus();self.update_focus_outline();return True
        return False

    def collection_search_changed(self):
        state=self.routes[self.route];query=self.collection_search.get_text().strip()
        if state['query']==query:return
        state.update(query=query,page=1,scroll=0,focus=None)
        if self.route=='library':self.render_collection()
        else:self.load_store()

    def collection_page(self,delta):
        if self.route not in self.routes:return
        control=self.next_page if delta>0 else self.previous_page
        if not control.is_sensitive():return
        self.collection_go_page(self.routes[self.route]['page']+delta)

    def collection_go_page(self,page):
        if self.route not in self.routes or page is None:return
        state=self.routes[self.route]
        if self.collection_total_pages is not None:page=min(page,self.collection_total_pages)
        if self.route=='store':page=min(page,MAX_PAGE)
        page=max(1,page)
        if page==state['page']:return
        state.update(page=page,scroll=0,focus=None)
        if self.route=='library':self.render_collection()
        else:self.load_store()

    def update_collection_pager(self,page,pages=None,has_next=False,loading=False):
        self.collection_pager_state=(page,pages,has_next,loading)
        _,button,label,_,clear=ui();clear(self.collection_numbers);self.collection_total_pages=pages
        limited=self.route=='store' and pages is not None and pages>MAX_PAGE
        self.first_page.set_sensitive(page>1 and not loading);self.previous_page.set_sensitive(page>1 and not loading)
        self.next_page.set_sensitive(has_next and not loading and (self.route!='store' or page<MAX_PAGE))
        self.last_page.set_visible(pages is not None)
        self.last_page.set_sensitive(pages is not None and page<pages and not limited and not loading)
        self.last_page.set_tooltip_text('Narrow your search to reach the last page' if limited else 'Last page')
        # Bound native button count, even for thousands of catalog pages.
        visible_pages=min(pages,MAX_PAGE) if limited else pages
        for number in page_numbers(page,visible_pages):
            if number is None:self.collection_numbers.append(label('…'));continue
            control=button(str(number),lambda n=number:self.collection_go_page(n),'current-page' if number==page else None)
            control.catalog_page_number=number
            control.set_tooltip_text(f'Page {number}'+(' (current)' if number==page else ''))
            control.set_sensitive(number!=page and not loading);self.collection_numbers.append(control)
        suffix=' · PgUp / PgDn'+(' · LB / RB' if self.tv_mode else '')
        total=f' of {pages}' if pages is not None else ' · total unavailable'
        if limited:total+=' · browsing limited to 1,000 pages; narrow your search'
        self.collection_page_label.set_text(f'Page {page}{total}'+suffix)

    def make_card(self,title,identity,callback,path=None,badge='',is_ready=None):
        box,button,label,_,_=ui()
        card_w,card_h=self.collection_card_dimensions()
        scale=getattr(self,'ui_scale_factor',lambda:1.0)()
        tile=button(title,callback,'collection-card');tile.set_halign(Gtk.Align.START);tile.set_valign(Gtk.Align.START)
        tile.console_width=card_w;tile.set_layout_manager(CoverLayout())
        if is_ready is True:
            tile.add_css_class('game-ready')
            tile.set_tooltip_text(f"{title}\nReady to play")
        elif is_ready is False:
            tile.add_css_class('game-not-ready')
            tile.set_tooltip_text(f"{title}\nLink a game to play")
        else:
            tile.set_tooltip_text('View '+title)
        content=box(spacing=max(10,int(10*scale)));tile.set_child(content)
        cover=console_cover(path,card_w,card_h);content.append(cover)
        caption=label(title,'collection-title',xalign=0,wrap=True,lines=2,ellipsize=Pango.EllipsizeMode.END,width_chars=1,max_width_chars=1)
        caption.set_size_request(card_w,int(48*scale));content.append(caption)
        tag=label(badge,'collection-badge',xalign=0)
        tag.set_visible(bool(badge))
        content.append(tag)
        focus=Gtk.EventControllerFocus()
        def focused(*_):
            if self.route in self.routes:self.routes[self.route]['focus']=identity
            self.tv_selected_id=identity
        focus.connect('enter',focused);tile.add_controller(focus)
        self.collection_flow.append(tile);self.collection_tiles[identity]=tile
        self.tv_tiles.append((identity,tile));tile.console_cover=cover;tile.console_title=caption
        tile.collection_badge=tag
        return cover

    def restore_collection(self,navigation_revision=None):
        state=self.routes[self.route];generation=self.catalog_generation;focused=False;scroll=state['scroll']
        saved_focus=state['focus']
        revision=None;selected=None
        if navigation_revision is None:navigation_revision=getattr(self,'browse_navigation_revision',0)
        def restore(widget,clock):
            nonlocal focused,revision,selected
            if generation!=self.catalog_generation or navigation_revision!=getattr(self,'browse_navigation_revision',0):return False
            if focused and revision!=getattr(self,'browse_focus_revision',0):return False
            if widget.get_width()<=0:return True
            if not focused:
                tile=self.collection_tiles.get(state['focus']) or next(iter(self.collection_tiles.values()),None)
                if tile:tile.grab_focus();self.update_focus_outline()
                selected=tile;revision=getattr(self,'browse_focus_revision',0)
                focused=True;return True
            # Apply saved position after GTK's focus-driven scrolling/layout.
            if selected is not None and self.focused_control(self) is selected:
                self.collection_scroll.get_vadjustment().set_value(scroll)
                if saved_focus is not None or scroll>0:self.reveal_browse_control(selected)
            return False
        self.collection_flow.add_tick_callback(restore)

    def render_collection(self):
        _,button,label,_,clear=ui();self.catalog_cancel();clear(self.collection_flow);self.collection_tiles={};self.tv_tiles=[]
        state=self.routes['library'];games=self.library.games()
        data=library_page(games,state['query'],state['genre'],state['sort'],state['page'])
        if state['page']!=data['page']:state.update(page=data['page'],scroll=0,focus=None)
        self.tv_games=data['items']
        self.collection_status.set_text(f'{data["count"]} games'+(f' · {data["total"]} in your library' if state['query'] or state['genre'] else ''))
        for game in self.tv_games:
            name=game['artwork'].get('portrait') or game['artwork'].get('landscape')
            is_ready=bool(configured_game(game) and game.get('executable') and Path(game['executable']).is_file())
            self.make_card(game['title'],game['id'],lambda g=game:self.show_game(g),self.library.art_dir/name if name else None,badge='',is_ready=is_ready)
        if not data['count']:
            self.collection_flow.append(label('No matching games.' if games else 'Your collection starts in Store.','title-2',wrap=True))
            if not games:self.collection_flow.append(button('Browse Store',self.show_store,'suggested-action'))
        self.update_collection_pager(data['page'],data['pages'],data['page']<data['pages'])
        self.restore_collection()

    def show_store(self,restore=False):
        state=self.collection_shell('store')
        self.collection_genre=BrowseChoice('Filter',['All genres']+[g['name'] for g in self.catalog_genres])
        index=next((i for i,g in enumerate(self.catalog_genres,1) if g['id']==state['genre']),0)
        self.collection_genre.set_selected(index);self.collection_genre.set_tooltip_text('Game genre');self.collection_toolbar.append(self.collection_genre)
        def genre_changed(*_):
            if getattr(self,'catalog_model_updating',False):return
            selected=self.collection_genre.get_selected();genre=self.catalog_genres[selected-1]['id'] if selected and selected<=len(self.catalog_genres) else None
            if genre!=state['genre']:state.update(genre=genre,page=1,scroll=0,focus=None);self.load_store()
        self.collection_genre.connect('notify::selected',genre_changed)
        STORE_SORTS=[('popular','Most popular'),('latest','Latest first'),('rating','Top rated'),('name_asc','Name (A–Z)'),('name_desc','Name (Z–A)')]
        self.store_sort_keys=[k for k,_ in STORE_SORTS]
        self.collection_sort=BrowseChoice('Sort',[label for _,label in STORE_SORTS])
        cur_sort=state.get('sort','popular')
        sort_idx=self.store_sort_keys.index(cur_sort) if cur_sort in self.store_sort_keys else 0
        self.collection_sort.set_selected(sort_idx);self.collection_sort.set_tooltip_text('Store sort order');self.collection_toolbar.append(self.collection_sort)
        def sort_changed(*_):
            idx=self.collection_sort.get_selected()
            if 0<=idx<len(self.store_sort_keys):
                chosen=self.store_sort_keys[idx]
                if chosen!=state.get('sort'):
                    state.update(sort=chosen,page=1,scroll=0,focus=None);self.load_store()
        self.collection_sort.connect('notify::selected',sort_changed)
        # Load the saved taxonomy only while constructing the route. Updating
        # Gtk.DropDown's model inside its own selection notification is unsafe.
        genres=self.catalog.cached_genres()
        if genres is not None:self.store_genres_loaded(genres)
        self.load_store()

    def store_genres_loaded(self,genres):
        state=self.routes['store'];genres=list(genres)
        # Retain the user's selected name if a changing taxonomy omits it.
        if state['genre'] is not None and not any(g['id']==state['genre'] for g in genres):
            previous=next((g for g in self.catalog_genres if g['id']==state['genre']),None)
            if previous:genres.append(previous)
        if genres==self.catalog_genres:return
        self.catalog_genres=genres;self.catalog_model_updating=True
        try:
            current=next((i for i,g in enumerate(genres,1) if g['id']==state['genre']),0)
            self.collection_genre.set_model(Gtk.StringList.new(['All genres']+[g['name'] for g in genres]))
            self.collection_genre.set_selected(current)
        finally:self.catalog_model_updating=False

    def load_store(self):
        self.catalog_cancel();state=self.routes['store'];state.pop('result',None)
        navigation_revision=getattr(self,'browse_navigation_revision',0)
        _,_,_,_,clear=ui();clear(self.collection_flow);self.collection_tiles={};self.tv_tiles=[]
        query,genre,page=state['query'],state['genre'],state['page']
        sort=state.get('sort','popular')
        cached=self.catalog.cached_browse(query,genre,page,sort)
        self.collection_status.set_text('Finding games…');self.update_collection_pager(page,loading=True)
        def loaded(data):
            if data.get('total_pages',state['page'])<state['page']:
                state.update(page=data['total_pages'],scroll=0,focus=None);self.load_store();return
            self.render_store(data,navigation_revision,refresh=state.get('result') is not None)
        def failed(error):
            _,button,label,_,_=ui();self.collection_status.set_text(str(error))
            if state.get('result') is not None:
                self.collection_status.set_text('Refresh unavailable · showing saved catalog results');return
            self.collection_flow.append(label('Store is unavailable','title-2'))
            self.collection_flow.append(button('Try again',self.load_store));self.update_collection_pager(page)
        # Reserve metadata work before optional card enrichment. Genres and
        # images can complete later; neither is a prerequisite for usable cards.
        self.catalog_job(lambda:self.catalog.browse(query,genre,page,sort),loaded,failed)
        self.catalog_job(self.catalog.genres,self.store_genres_loaded,lambda _:None,background=True)
        if cached is not None:self.render_store(cached,navigation_revision)

    def make_store_card(self,item):
        def opened():
            if self.route=='store' and self.collection_tiles.get(item['id']) is tile:self.open_catalog_item(tile.catalog_item)
        self.make_card(item['name'],item['id'],opened)
        tile=self.collection_tiles[item['id']];tile.catalog_item=item;tile.catalog_image_url=None
        return tile

    def update_store_identity(self,tile,item):
        badge='In library' if members(self.library,item) else 'Related saved entry' if related_members(self.library,item) else ''
        tile.collection_badge.set_text(badge)
        tile.collection_badge.set_visible(bool(badge))
        tile.set_tooltip_text('\n'.join(filter(None,('View '+item['name'],badge+' · shared Steam link' if badge=='Related saved entry' else badge))))

    def store_card_jobs(self,tile,item,revision):
        def current():return self.store_render_revision==revision and self.collection_tiles.get(item['id']) is tile
        if needs_membership_lookup(self.library,item):
            def identified(value):
                item['steam_app_id']=value['steam_app_id']
                # This optional relation lookup may return an older detail
                # snapshot. Fill unknown fields, retaining the visible browse
                # classification and platform list until the next page refresh.
                if not item.get('game_type') and value.get('game_type'):item['game_type']=value['game_type']
                if not item.get('platforms') and value.get('platforms'):item['platforms']=value['platforms']
                self.update_store_identity(tile,item)
            self.store_item_futures.append(self.catalog_job(lambda:self.catalog.detail(item['id']),identified,lambda _:None,background=True,valid=current))
        url=item['images'].get('portrait')
        if tile.catalog_image_url is not None and tile.catalog_image_url!=url:
            card_w,card_h=self.collection_card_dimensions()
            placeholder=console_cover(None,card_w,card_h);cover=tile.console_cover
            while cover.get_first_child():cover.remove(cover.get_first_child())
            while placeholder.get_first_child():
                child=placeholder.get_first_child();placeholder.remove(child);cover.append(child)
            tile.catalog_image_url=None
        if url and tile.catalog_image_url!=url:
            def painted(path):
                if update_cover(tile.console_cover,path):tile.catalog_image_url=url
            self.store_item_futures.append(self.catalog_job(lambda:self.catalog.image(url),painted,lambda _:None,image=True,valid=current))

    def render_store(self,data,navigation_revision=None,*,refresh=False):
        _,_,label,_,clear=ui();state=self.routes['store'];current=self.focused_control(self)
        focused_id=next((identity for identity,tile in self.collection_tiles.items() if tile is current),None)
        focused_page=getattr(current,'catalog_page_number',None)
        if refresh:
            state['scroll']=self.collection_scroll.get_vadjustment().get_value()
            if focused_id is not None:state['focus']=focused_id
        for future in self.store_item_futures:future.cancel()
        self.store_item_futures=[];self.store_render_revision+=1;revision=self.store_render_revision
        reuse=refresh and list(self.collection_tiles)==[item['id'] for item in data['items']] and bool(self.collection_tiles)
        if not reuse:clear(self.collection_flow);self.collection_tiles={};self.tv_tiles=[]
        if data.get('refreshing'):status='Saved catalog results · refreshing…'
        elif data['cached']:status='Offline · showing saved catalog results'
        else:status='Choose a game to explore · adding does not download or install it'
        self.collection_status.set_text(status)
        for item in data['items']:
            tile=self.collection_tiles[item['id']] if reuse else self.make_store_card(item)
            tile.catalog_item=item;tile.console_title.set_text(item['name']);self.update_store_identity(tile,item)
            self.store_card_jobs(tile,item,revision)
        if not data['items']:self.collection_flow.append(label('No games found. Try another title or genre.','title-2',wrap=True))
        pager=(data['page'],data.get('total_pages'),data['has_next'],False)
        if pager!=self.collection_pager_state:
            self.update_collection_pager(*pager)
            if refresh and focused_page is not None:
                for control in self.collection_numbers:
                    if getattr(control,'catalog_page_number',None)==focused_page and control.is_sensitive():control.grab_focus();break
                else:self.collection_search.grab_focus()
        state['result']=data
        if not refresh:self.restore_collection(navigation_revision)
        elif not reuse and focused_id is not None:self.restore_collection(getattr(self,'browse_navigation_revision',0))
        elif refresh and focused_id is not None:self.reveal_browse_control(current)

    def open_catalog_item(self,item):
        self.capture_route();self.detail_origin='store';self.detail_item=item
        existing=members(self.library,item)
        if len(existing)>1:self.notify('Multiple saved copies exist. Open the desired copy in Library.');return
        if existing:self.show_shared_detail(existing[0],item,enrich_catalog=True);return
        self.show_shared_detail(item_game(item,preview=True),item)
        self.detail_primary.set_sensitive(False);self.detail_status.set_text('Loading game details…')
        game_id=item['id']
        def loaded(value):
            existing=members(self.library,value)
            if len(existing)>1:
                self.detail_status.set_text('Multiple saved copies exist. Open the desired copy in Library.')
                self.detail_primary.set_sensitive(False);return
            self.show_shared_detail(existing[0] if existing else item_game(value,preview=True),value)
        def failed(error):self.detail_status.set_text(str(error));self.detail_primary.set_sensitive(False)
        self.catalog_job(lambda:self.catalog.detail(game_id),loaded,failed)

    def show_shared_detail(self,game,item=None,*,enrich_catalog=False):
        box,button,label,margins,clear=ui()
        # Mode/editor rebuilds cancel the old generation. Resume only the same
        # saved selection's unfinished enrichment, never a different route.
        enrich_catalog=enrich_catalog or bool(item and self.route=='detail' and getattr(self,'detail_catalog_pending',False)
            and self.game and self.game['id']==game['id'] and self.detail_item and self.detail_item['id']==item['id'])
        if self.route in self.routes or self.route=='home':self.capture_route();self.detail_origin=self.route
        self.catalog_cancel();self.route='detail';self.detail_item=item;self.detail_art={};self.detail_adding=False;self.body.remove_css_class('home-surface')
        self.detail_catalog_pending=False;self.detail_catalog_message=''
        self.game=deepcopy(game);self.original=deepcopy(game);self.fields={};self.launch_fields={};self.description=None;self.play_buttons={};self.tv_tiles=[]
        self.detail_install_status=None;self.last_launch_output=None
        if hasattr(self,'launch_output'):del self.launch_output
        clear(self.body);self.back.set_visible(not self.tv_mode);self.back.set_tooltip_text('Back to '+self.detail_origin.title())
        self.heading.set_title(game['title']);self.heading.set_subtitle('In your library' if self.saved_detail() else 'Store · IGDB')
        outer=box(spacing=24 if self.tv_mode else 16);outer.set_vexpand(True);margins(outer,24)
        back=button('Back',self.return_from_detail,icon='go-previous-symbolic');back.set_halign(Gtk.Align.START);back.set_visible(self.tv_mode);outer.append(back)
        outer.append(Gtk.Box(vexpand=True))
        panel=box(spacing=24);panel.add_css_class('shared-detail')
        scale=getattr(self,'ui_scale_factor',lambda:1.0)()
        max_panel=min(int(1140*scale),max(1140,self.get_width()-int(48*scale)))
        panel_limit=Adw.Clamp(maximum_size=max_panel,tightening_threshold=max_panel);panel_limit.set_halign(Gtk.Align.START);panel_limit.set_child(panel);outer.append(panel_limit)
        row=box(False,int(28*scale));panel.append(row);self.detail_row=row
        cover_column=box(spacing=int(14*scale));cover_column.set_valign(Gtk.Align.START);row.append(cover_column)
        name=game['artwork'].get('portrait') or game['artwork'].get('landscape');self.cover=console_cover(self.library.art_dir/name if name else None,int(160*scale),int(240*scale));cover_column.append(self.cover)
        info=box(spacing=int(16*scale) if self.tv_mode else int(14*scale));info.set_hexpand(True)
        max_sum=min(int(960*scale),max(960,self.get_width()-int(96*scale)))
        summary=Adw.Clamp(maximum_size=max_sum,tightening_threshold=max_sum);summary.set_hexpand(True);summary.set_halign(Gtk.Align.START);summary.set_child(info);row.append(summary)
        info.append(label(game['title'],'detail-title',xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,lines=2,ellipsize=Pango.EllipsizeMode.END))
        self.detail_entity=None
        meta=label(' · '.join(filter(None,(game.get('release_date'),game.get('genres')))) or 'Game details','dim-label',xalign=0,wrap=True);meta.add_css_class('detail-meta');info.append(meta)
        excerpt=description_excerpt(game.get('description','')) or 'No description available for this title.'
        info.append(label(excerpt,'detail-copy',xalign=0,wrap=True,lines=3,ellipsize=Pango.EllipsizeMode.END))
        credits=' · '.join(dict.fromkeys(filter(None,(game.get('developers'),game.get('publishers')))))
        credit=label(credits,'dim-label',xalign=0,wrap=True,lines=2,ellipsize=Pango.EllipsizeMode.END);credit.add_css_class('detail-meta');info.append(credit)
        saved=self.saved_detail();installed=configured_game(game) and bool(game.get('executable') and Path(game['executable']).is_file())
        self.detail_size=button('Search links',self.open_detail_links,icon='edit-find-symbolic')
        self.detail_size.set_visible(False)
        self.detail_refresh=Gtk.Button(icon_name='view-refresh-symbolic')
        self.detail_refresh.set_tooltip_text('Refresh source results')
        self.detail_refresh.set_visible(False)
        self.detail_source_row=box(False,8);self.detail_source_row.set_visible(False)
        self.detail_source_row.append(self.detail_size);self.detail_source_row.append(self.detail_refresh)
        actions=box(False,12);panel.append(actions);self.detail_actions_box=actions
        if installed:
            primary=button('Play',self.detail_action);primary.add_css_class('suggested-action')
            self.play_buttons={game['id']:primary}
        else:
            primary=button('Link a game',self.open_add_installed_game);primary.add_css_class('suggested-action')
        primary.add_css_class('detail-primary');primary.set_valign(Gtk.Align.CENTER);self.detail_primary=primary
        actions.append(primary)
        if saved:
            lib_btn=button('Remove from library',self.remove_detail);lib_btn.add_css_class('detail-primary')
        else:
            lib_btn=button('Add to library',self.detail_action);lib_btn.add_css_class('detail-primary')
        lib_btn.set_valign(Gtk.Align.CENTER);actions.append(lib_btn)
        self.detail_lib_btn = lib_btn
        self.detail_gear=Gtk.Button(icon_name='emblem-system-symbolic');self.detail_gear.add_css_class('circular');self.detail_gear.set_tooltip_text('Game settings');self.detail_gear.set_valign(Gtk.Align.CENTER);self.detail_gear.connect('clicked',lambda *_:self.open_game_settings());actions.append(self.detail_gear)
        self.detail_related=None
        related=related_members(self.library,item) if item and not saved else []
        if related:
            relation=box(spacing=8);panel.append(relation)
            relation.append(label('A saved entry shares this Steam link. It is tracked separately.' if len(related)==1 else f'{len(related)} saved entries share this Steam link. Each is tracked separately.',
                                  'detail-meta',xalign=0,wrap=True))
            self.detail_related=button('Open saved entry' if len(related)==1 else 'Open Library',self.open_related_entry)
            self.detail_related.set_halign(Gtk.Align.START);relation.append(self.detail_related)
        self.detail_status=label('Saved catalog information · offline' if item and item.get('cached') else '', 'dim-label',xalign=0,wrap=True);self.detail_status.add_css_class('detail-meta');panel.append(self.detail_status);self.console_status=self.detail_status
        self.place_runtime_progress(panel);self.detail_scroll=self.scrolled(outer)
        self.detail_backdrop=CoverPicture(content_fit=Gtk.ContentFit.COVER,can_shrink=True,opacity=0 if self.tv_mode else 1)
        scene=Gtk.Overlay();scene.add_css_class('detail-surface');scene.set_child(self.detail_backdrop)
        if not self.tv_mode:
            scrim=Gtk.Box();scrim.add_css_class('detail-scrim');scrim.set_can_target(False);scene.add_overlay(scrim)
        scene.add_overlay(self.detail_scroll);scene.set_measure_overlay(self.detail_scroll,True);scene.set_vexpand(True);self.body.append(scene);self.detail_scene=scene
        hero=game['artwork'].get('hero') or game['artwork'].get('landscape');set_art(self.backdrop,self.library.art_dir/hero if hero else None);set_art(self.detail_backdrop,self.library.art_dir/hero if hero else None);self.backdrop.set_opacity(1 if self.tv_mode else .8)
        if self.tv_mode:self.body.append(label('Esc / B  Back     Enter / A  Select     X  Focus Play / Stop     LB / RB  Scroll','tv-hints',xalign=0,ellipsize=Pango.EllipsizeMode.END))
        if item and not saved:
            for kind,url in item['images'].items():
                def loaded(path,k=kind):
                    self.detail_art[k]=path
                    if k=='portrait':update_cover(self.cover,path)
                    else:set_art(self.backdrop,path);set_art(self.detail_backdrop,path)
                self.catalog_job(lambda u=url:self.catalog.image(u),loaded,lambda _:None,image=True)
        self.refresh_launch_state()
        generation=self.catalog_generation
        def responsive(widget,clock):
            if generation!=self.catalog_generation:return False
            if self.get_width()<=0 or self.get_height()<=0:return True
            scale=getattr(self,'ui_scale_factor',lambda:1.0)()
            compact=self.get_width()<700 and scale<=1.0
            if self.tv_mode:
                small=(self.get_width()<1400 or self.get_height()<850) and scale<=1.0
                if small:self.add_css_class('tv-compact')
                else:self.remove_css_class('tv-compact')
                width=int(144*scale) if small else int(180*scale)
                m_h=int(32*scale) if small else int(48*scale)
                outer.set_margin_start(m_h);outer.set_margin_end(m_h)
                outer.set_margin_top(int(12*scale) if small else int(20*scale));outer.set_margin_bottom(int(20*scale) if small else int(28*scale))
            else:
                small=(self.get_width()<1400 or self.get_height()<850) and scale<=1.0
                if small:scene.add_css_class('detail-compact')
                else:scene.remove_css_class('detail-compact')
                width=int(144*scale) if small else int(180*scale)
                m_h=int(24*scale) if small else int(48*scale)
                outer.set_margin_start(m_h);outer.set_margin_end(m_h)
                outer.set_margin_top(int(12*scale) if small else int(20*scale));outer.set_margin_bottom(int(24*scale) if small else int(28*scale))
            self.cover.set_size_request(width,width*3//2)
            # One stable action row keeps primary/options/info aligned across metadata heights.
            primary.set_size_request(width if not compact else -1,-1)
            row.set_orientation(Gtk.Orientation.VERTICAL if compact else Gtk.Orientation.HORIZONTAL)
            self.cover.set_visible(not compact)
            return True
        self.detail_responsive=responsive;responsive(row,None)
        def focus(widget,clock):
            if generation!=self.catalog_generation:return False
            if not primary.get_mapped():return True
            primary.grab_focus();return False
        primary.add_tick_callback(focus)
        if enrich_catalog and saved:self.enrich_saved_catalog_detail()

    def enrich_saved_catalog_detail(self):
        identity=self.detail_item['id'] if self.detail_item else self.game.get('metadata_source',{}).get('id')
        if not identity:return
        saved_id=self.game['id']
        self.detail_catalog_pending=True;self.detail_catalog_message='Loading catalog information…'
        def valid():
            return bool(self.route=='detail' and self.game and self.game['id']==saved_id
                and any(g['id']==saved_id for g in self.library.games()))
        def loaded(value):
            self.detail_catalog_pending=False;self.detail_item=value
            if self.detail_entity is not None:
                lbl=entity_label(value)
                self.detail_entity.set_text(lbl);self.detail_entity.set_visible(bool(lbl))
            self.detail_catalog_message='Saved catalog information · offline' if value.get('cached') else ''
            if not (self.game.get('artwork',{}).get('hero') or self.game.get('artwork',{}).get('landscape')):
                hero_url=value.get('images',{}).get('hero')
                if hero_url:
                    def hero_loaded(path):
                        set_art(self.backdrop,path);set_art(self.detail_backdrop,path)
                    self.catalog_job(lambda u=hero_url:self.catalog.image(u),hero_loaded,lambda _:None,image=True)
            self.refresh_catalog_info()
        def failed(_):
            self.detail_catalog_pending=False
            self.detail_catalog_message='Catalog information unavailable. Your saved game is unchanged.'
            self.refresh_catalog_info()
        self.catalog_job(lambda:self.catalog.detail(identity),loaded,failed,valid=valid)

    def refresh_catalog_info(self):
        receiver=getattr(self,'catalog_info_dialog',None);dialog=receiver() if receiver else None
        if (dialog is None or not dialog.get_visible() or dialog.catalog_generation!=self.catalog_generation
                or not self.game or dialog.catalog_game_id!=self.game['id']):return
        _,_,_,_,clear=ui();clear(dialog.catalog_content)
        self.append_catalog_info(dialog.catalog_content,self.game,dialog)
        if self.tv_mode:self.restrict_tv_focus(dialog.catalog_content)

    def saved_detail(self):return bool(self.game and any(g['id']==self.game['id'] for g in self.library.games()))

    def open_related_entry(self):
        # Re-read current records on explicit navigation; never copy the catalog
        # item's identity, artwork or launch settings onto a related saved entry.
        if not self.detail_item or self.saved_detail():return
        related=related_members(self.library,self.detail_item)
        if len(related)==1:self.show_shared_detail(related[0])
        else:self.show_collection()

    def append_catalog_info(self,content,game,dialog):
        item=self.detail_item
        if not item or not self.game or self.game['id']!=game['id']:return
        generation=self.catalog_generation
        box,button,label,_,_=ui()
        content.append(label(entity_label(item),'dim-label',xalign=0,wrap=True))
        if self.detail_catalog_message:content.append(label(self.detail_catalog_message,'dim-label',xalign=0,wrap=True))
        relations=item.get('relationships',{})
        groups=[]
        for key,title,empty in (('bundle_contents','Included catalog entries','No contents reported by IGDB.'),
                                ('expanded_from','Expanded from','No originals reported by IGDB.')):
            if key in relations:
                group=relations[key]
                note=('Reported by IGDB.' if group['items'] else empty) if group['complete'] else 'Partial list reported by IGDB.'
                groups.append((title,group['items'],note))
        for key,title in (('bundles','Included in bundles'),('expanded_games','Expanded versions'),
                          ('parent_game','Related main game or bundle'),('version_parent','Edition of')):
            values=relations.get(key)
            if values:groups.append((title,values if isinstance(values,list) else [values],''))
        owner_ref=self.weak_ref();dialog_ref=dialog.weak_ref()
        def open_reference(target):
            owner=owner_ref();current=dialog_ref()
            if owner is None or current is None or not current.get_visible() or generation!=owner.catalog_generation or owner.route!='detail' or not owner.detail_item or owner.detail_item['id']!=item['id']:return
            current.close();owner.open_catalog_item(validate_item(target))
        for title,values,note in groups:
            section=box(spacing=8);section.set_margin_top(8);content.append(section)
            section.append(label(title,'heading',xalign=0))
            if note:section.append(label(note,'dim-label',xalign=0,wrap=True))
            for target in values:
                control=button(target['name'],lambda ref=target:open_reference(ref))
                control.set_child(label(target['name'],xalign=0,wrap=True,lines=2,ellipsize=Pango.EllipsizeMode.END,width_chars=1,max_width_chars=1,hexpand=True))
                control.set_tooltip_text('View catalog entry · '+target['name']);control.catalog_reference_id=target['id']
                section.append(control)

    def detail_action(self):
        if self.saved_detail():
            if configured_game(self.game) or self.launcher.active():self.play_game(self.game)
            else:self.open_add_installed_game()
            return
        if not self.detail_item or self.detail_adding:return
        existing=members(self.library,self.detail_item)
        if len(existing)>1:self.notify('Multiple saved copies exist. Open the desired copy in Library.');return
        if existing:self.show_shared_detail(existing[0],self.detail_item);return
        item=deepcopy(self.detail_item);self.detail_adding=True;self.detail_primary.set_sensitive(False)
        self.detail_status.set_text('Saving game information and available artwork…')
        def artwork():
            result={}
            for kind,url in item['images'].items():
                try:result[kind]=self.catalog.image(url).read_bytes()
                except (OSError,ValueError):pass
            return result
        def saved(art):
            game,created=add_item(self.library,item,art);self.show_shared_detail(game,item)
            if created:self.notify('Added to your library. Set up your game files when ready.')
        def failed(error):
            self.detail_adding=False;self.detail_primary.set_sensitive(True);self.detail_status.set_text(str(error))
        self.catalog_job(artwork,saved,failed,image=True)


    def open_detail_links(self):
        title = (self.detail_item.get('name') if self.detail_item else (self.game.get('title') if self.game else '')) or ''
        title = title.strip()
        if hasattr(self, 'open_sources_links_dialog'):
            self.open_sources_links_dialog(section='links', search_query=title)
        else:
            from .sources_modal import SourcesLinksDialog
            dialog = SourcesLinksDialog(self.library, self)
            dialog.open_tab('links', title)
            dialog.present()

    def show_source_selection_dialog(self):
        self.open_detail_links()

    def show_release_links_dialog(self, release, parent=None):
        title = release.get('title') or 'Download'
        links = [(uri, kind) for uri in (release.get('uris') or [])
                 if (kind := source_link_kind(uri))]
        dialog = modal_window(parent or self, 'Download links', width=720, height=600, subtitle=title)
        content = dialog_body(dialog)
        description = Gtk.Label(
            label='Copy a link to use with your own download and installation tools. Add the installed game from its detail page when it is ready to play.',
            xalign=0, wrap=True)
        description.add_css_class('dim-label')
        content.append(description)
        group = Adw.PreferencesGroup()
        for index, (uri, kind) in enumerate(links, 1):
            row = Adw.ActionRow(title=f'{kind} {index}', subtitle=uri)
            row.set_use_markup(False)
            row.set_subtitle_lines(2)
            copy = Gtk.Button(label='Copy', valign=Gtk.Align.CENTER)
            copy.connect('clicked', lambda _button, value=uri: Gdk.Display.get_default().get_clipboard().set(value))
            row.add_suffix(copy)
            group.add(row)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(group)
        content.append(scroll)
        footer = dialog_footer()
        content.append(footer)
        close = Gtk.Button(label='Close')
        close.connect('clicked', lambda *_: dialog.close())
        footer.append(close)
        dialog.present()
        return dialog

    def ensure_saved_game(self):
        """Ensure current game is a valid library entry with a genuine UUID before install/launch."""
        if self.saved_detail():
            return self.game
        if self.detail_item:
            existing = members(self.library, self.detail_item)
            if existing:
                self.game = deepcopy(existing[0])
                return self.game
            art = {}
            for kind, url in self.detail_item.get('images', {}).items():
                try:
                    p = self.catalog.image(url)
                    if p and Path(p).is_file():
                        art[kind] = Path(p).read_bytes()
                except Exception:
                    pass
            try:
                self.game, _ = add_item(self.library, self.detail_item, art)
                return self.game
            except Exception:
                pass
        from uuid import UUID
        from .library import Library
        if not self.game:
            self.game = Library.new_game()
            if self.detail_item:
                for k in ('title', 'description', 'release_date', 'genres', 'developers', 'publishers',
                          'metadata_app_id', 'metadata_source'):
                    if self.detail_item.get(k):
                        self.game[k] = deepcopy(self.detail_item[k])
            return self.game
        game_id = self.game.get('id', '')
        try:
            UUID(game_id)
            if not any(g['id'] == game_id for g in self.library.games()):
                self.library.save(self.game)
            if hasattr(self, 'detail_lib_btn') and self.detail_lib_btn:
                self.detail_lib_btn.set_label('Remove from library')
                self.detail_lib_btn.connect('clicked', lambda *_: self.remove_detail())
            return self.game
        except (ValueError, TypeError):
            from .library import Library
            new_game = Library.new_game()
            for k in ('title', 'description', 'release_date', 'genres', 'developers', 'publishers',
                      'metadata_app_id', 'metadata_source', 'artwork'):
                if self.game.get(k):
                    new_game[k] = deepcopy(self.game[k])
            if self.game.get('installation'):
                new_game['installation'] = deepcopy(self.game['installation'])
            if self.game.get('working_dir'):
                new_game['working_dir'] = self.game['working_dir']
            self.library.save(new_game)
            self.game = new_game
            if hasattr(self, 'detail_lib_btn') and self.detail_lib_btn:
                self.detail_lib_btn.set_label('Remove from library')
                self.detail_lib_btn.connect('clicked', lambda *_: self.remove_detail())
            return self.game

    def return_from_detail(self):
        if self.detail_origin=='store':self.show_store(restore=True)
        elif self.detail_origin=='home':self.show_home()
        else:self.show_collection()

    def remove_detail(self):
        game=deepcopy(self.game)
        def remove():
            if self.launcher.active():raise ValueError('Finish the current game or installer first.')
            if not self.game or self.game['id']!=game['id']:return
            current=next((g for g in self.library.games() if g['id']==game['id']),None)
            if current!=game:raise ValueError('Game setup changed. Review removal again.')
            if getattr(self,'game_settings_dialog',None):self.game_settings_dialog.close()
            self.library.delete(game['id']);self.return_from_detail();self.notify('Removed from library. Game files, saves and prefixes were kept.')
            self.library.data.setdefault('downloaded_installers', {}).pop(game['id'], None)
            try: self.library._write()
            except Exception: pass
        def confirmed():
            try:remove()
            except Exception as error:self.error(error)
        self.confirm('Remove '+game['title']+' from library?','Only its library entry is removed. Game files, saves, prefixes and Proton are kept.','Remove from library',confirmed,True)

    def review_uninstall(self):
        game=deepcopy(self.game)
        from .game_uninstall import detect_game_root, folder_summary, remove_game_directory
        detected_root=detect_game_root(game,self.library)
        if not detected_root or not Path(detected_root).is_dir():
            self.notify('Could not safely isolate this game’s managed content folder. Its library entry is unchanged.')
            return
        file_count,total_size,size_str=folder_summary(detected_root)
        body=(f'Game folder to remove:\n{detected_root}\n\n'
              f'({size_str} · {file_count} files)\n\n'
              'This permanently deletes this game installation folder. Its library entry remains, so you can add an installed copy again later. '
              'Game saves and Wine prefixes are kept separate.')
        def do_uninstall():
            if self.demo:self.error(ValueError('File deletion is disabled in the visual demo.'));return
            if self.launcher.active():self.error(RuntimeError('Finish the active game or installer first.'));return
            if not self.game or self.game['id']!=game['id']:return
            def run_delete():
                from .game_assets import unlink_game
                remove_game_directory(detected_root)
                unlink_game(game)
                uninstalled=deepcopy(game)
                uninstalled.update(executable='',working_dir='',installation={})
                uninstalled['launch']={**uninstalled.get('launch',{}),'prefix':'','proton':''}
                self.library.save(uninstalled)
                return uninstalled
            def complete(uninstalled):
                if getattr(self,'game_settings_dialog',None):self.game_settings_dialog.close()
                self.game=uninstalled
                self.show_game(uninstalled)
                self.notify(f'{game["title"]} files were uninstalled. Its library entry was kept.')
            self.async_job('Uninstalling game files…',run_delete,complete)
        self.confirm('Uninstall '+game['title']+'?',body,'Delete game folder',do_uninstall,destructive=True)

    def build_installation_folder(self,content):
        box,button,label,margins,_=ui()
        group=Adw.ExpanderRow(title='Installation folder',subtitle='Verify the existing folder once to enable safe uninstall.')
        controls=box(spacing=10);margins(controls,12);group.add_row(controls)
        candidate=self.game_uninstall.root_hint(self.game) or self.game.get('working_dir') or str(Path(self.game['executable']).parent if self.game.get('executable') else '')
        self.installation_root_candidate=candidate
        self.installation_root_label=label(candidate or 'Choose a dedicated game folder.','dim-label',xalign=0,wrap=True);controls.append(self.installation_root_label)
        controls.append(button('Verify this folder…',self.verify_installation_folder))
        def chosen(path):
            self.installation_root_candidate=str(path);self.installation_root_label.set_text(str(path))
        controls.append(button('Choose another folder',lambda:self.choose_file('Game installation folder',chosen,folder=True)))
        content.append(group)

    def verify_installation_folder(self):
        game=self.collect();owner=self.editor
        if self.launcher.active():self.error(ValueError('Finish the active game or installer first.'));return
        def loaded(inspection):
            if self.editor is not owner or self.collect()!=game:return
            files=[name for name,value in inspection['entries'].items() if value['kind']=='file']
            body=(f"Use this existing folder: {inspection['root']['path']}\n\n"
                  f'{len(files)} files belong to this proposed installation. Confirm only if they are game files, with no saves or personal data. '
                  'Working directory and executable stay unchanged. Verification does not delete anything.\n\n'+ '\n'.join(files[:15]))
            if len(files)>15:body+=f'\n… and {len(files)-15} more files.'
            def confirm():
                if self.editor is not owner or self.collect()!=game:return
                try:
                    if self.launcher.active():raise ValueError('Finish the active game or installer first.')
                    self.game_uninstall.confirm(game,inspection);self.notify('Installation folder verified for this saved game.')
                except Exception as error:self.error(error)
            self.confirm('Verify game installation folder?',body,'Confirm game folder',confirm)
        self.async_job('Inspecting the existing game folder…',lambda:self.game_uninstall.inspect(game,self.installation_root_candidate),loaded)
