"""Native Library / Store routes and one shared, state-driven detail page."""
from copy import deepcopy
import os
from pathlib import Path
import re
from gi.repository import Adw, Gio, GLib, Gtk, Pango

from .catalog import CatalogService, configured_catalog, add_item, item_game, members, related_members, entity_label, validate_item, needs_membership_lookup, MAX_PAGE
from .collection import genre_choices, library_page, page_numbers
from .browse_controls import BrowseChoice
from .dialogs import style_surface, modal_window, dialog_body, dialog_footer
from .catalog_work import CatalogWork
from .download_service import (
    UnavailableInstallService, configured_game, detail_actions, search_fitgirl_repack,
    download_manager, parse_size_bytes, format_size, estimate_space_requirements, fitgirl_cache
)
from .fullscreen import cover as console_cover, set_art, CoverPicture, CoverLayout
from .library import description_excerpt

CSS = b'''
.collection-page { padding: 24px 32px; }
.collection-heading { font-size: 30px; font-weight: 800; }
.collection-card { padding: 10px; border-radius: 14px; background: alpha(@window_fg_color,.045); }
.collection-card:hover { background: alpha(@accent_color,.12); }
.collection-card:focus { outline: 3px solid #7de8d3; outline-offset: 1px; }
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
.tv-mode .collection-page { padding: 24px 42px; }
.tv-mode .shared-detail { background: alpha(#0e1422,.94); }
.tv-mode .detail-title { font-size: 42px; }
.tv-mode .shared-detail { background: alpha(#0d1523,.86); border: 1px solid alpha(#b4c7e5,.10); padding: 30px; }
.tv-mode .shared-detail .detail-title { font-size: 46px; letter-spacing: -1px; line-height: 1.06; }
.tv-mode .shared-detail .detail-copy { color: #d5ddea; font-size: 20px; line-height: 1.4; }
.tv-mode .shared-detail .detail-meta { color: #acb9ce; font-size: 17px; opacity: 1; }
.tv-mode.tv-compact .shared-detail { padding: 22px; }
.tv-mode.tv-compact .shared-detail .detail-title { font-size: 34px; }
.tv-mode.tv-compact .shared-detail .detail-copy { font-size: 17px; }
.tv-mode .collection-card { background: alpha(#26334d,.4); }
.collection-page.collection-compact { padding-top: 14px; padding-bottom: 14px; }
.collection-pager button { min-width: 20px; padding: 8px 12px; }
.tv-mode .collection-pager button { min-height: 32px; }
.collection-pager .current-page { background: #82e9d0; color: #102a29; opacity: 1; }
.collection-short .collection-card { padding: 8px; }
.browse-choice { border-radius: 10px; }
.browse-choice.control-focused > button:focus { outline: none; }
.browse-choice popover button.suggested-action { background: #ceeae3; color: #155448; }
.desktop-dark .browse-choice popover button.suggested-action,
.tv-mode .browse-choice popover button.suggested-action { background: #243d44; color: #85efd4; }

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
.desktop-mode .control-focused, .desktop-mode button:focus-visible, .desktop-mode .collection-card:focus,
.desktop-mode .collection-page .browse-search.control-focused { outline: 3px solid #267c6c; outline-offset: 2px; }
.desktop-mode.desktop-dark .control-focused, .desktop-mode.desktop-dark button:focus-visible,
.desktop-mode.desktop-dark .collection-card:focus, .desktop-mode.desktop-dark .collection-page .browse-search.control-focused { outline-color: #a6f5df; }
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
        self.game_install_service=UnavailableInstallService()
        from .game_uninstall import GameUninstall
        self.game_uninstall=GameUninstall(self.library)

    def catalog_cancel(self):
        self.catalog_generation+=1
        for future in self.catalog_futures:future.cancel()
        self.catalog_futures=[];self.store_item_futures=[]

    def catalog_job(self,work,done,failed=None,*,image=False,background=False,valid=None):
        generation=self.catalog_generation
        future=self.catalog_pool.submit_image(work) if image else self.catalog_pool.submit(work,background=background)
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
            compact=self.get_width()<1000
            toolbar.set_orientation(Gtk.Orientation.VERTICAL if compact else Gtk.Orientation.HORIZONTAL)
            filters.set_halign(Gtk.Align.END)
            short=self.get_height()<700
            subtitle.set_visible(not short);page.set_spacing(10 if short else 16)
            if short:page.add_css_class('collection-compact')
            else:page.remove_css_class('collection-compact')
            if self.tv_mode:
                if self.get_width()<1400 or self.get_height()<850:self.add_css_class('tv-compact')
                else:self.remove_css_class('tv-compact')
            if short:self.collection_flow.add_css_class('collection-short')
            else:self.collection_flow.remove_css_class('collection-short')
            for _,tile in self.tv_tiles:
                compact_card=(short,compact)
                if getattr(tile,'collection_compact',None)==compact_card:continue
                tile.collection_compact=compact_card;tile.console_width=136 if short else 156;tile.queue_resize()
                tile.console_cover.set_size_request((80 if compact else 96) if short else 136,(120 if compact else 144) if short else 204)
                tile.console_cover.set_halign(Gtk.Align.CENTER if short else Gtk.Align.FILL)
                tile.console_title.set_size_request(116 if short else 136,42 if short else 48)
                tile.collection_badge.set_visible(not short)
            size=(self.get_width(),self.get_height())
            if getattr(toolbar,'browse_size',None)!=size:
                toolbar.browse_size=size
                # The same card can remain focused across a column/height
                # change. Recheck its visibility after native layout settles.
                self.reveal_browse_control(self.focused_control(self))
            return True
        toolbar.add_tick_callback(resize_toolbar)
        self.collection_status=label('','dim-label',xalign=0,wrap=True);page.append(self.collection_status)
        self.collection_flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,min_children_per_line=1,max_children_per_line=10,column_spacing=16,row_spacing=20)
        self.collection_flow.set_valign(Gtk.Align.START)
        self.collection_flow.set_margin_start(24);self.collection_flow.set_margin_end(24)
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
        state=self.collection_shell('library')
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

    def make_card(self,title,identity,callback,path=None,badge=''):
        box,button,label,_,_=ui()
        tile=button(title,callback,'collection-card');tile.set_halign(Gtk.Align.CENTER);tile.set_valign(Gtk.Align.START)
        tile.console_width=156;tile.set_layout_manager(CoverLayout())
        tile.set_tooltip_text('View '+title)
        content=box(spacing=10);tile.set_child(content)
        cover=console_cover(path,136,204);content.append(cover)
        caption=label(title,'collection-title',xalign=0,wrap=True,lines=2,ellipsize=Pango.EllipsizeMode.END,width_chars=1,max_width_chars=1)
        caption.set_size_request(136,48);content.append(caption)
        tag=label(badge,'collection-badge',xalign=0);tag.set_size_request(-1,18);content.append(tag)
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
                self.reveal_browse_control(selected)
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
            self.make_card(game['title'],game['id'],lambda g=game:self.show_game(g),self.library.art_dir/name if name else None,'Ready to play' if game['executable'] else 'Set up to play')
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
        # Classification stays visible in short windows, unlike the optional
        # membership badge. Reserve equal space so async detail cannot jump rows.
        _,_,label,_,_=ui()
        tile.catalog_context=label('','collection-kind',xalign=0,wrap=True,lines=2,
                                   ellipsize=Pango.EllipsizeMode.END,width_chars=1,max_width_chars=1)
        tile.catalog_context.set_size_request(-1,48)
        tile.get_child().insert_child_after(tile.catalog_context,tile.console_title)
        return tile

    def update_store_identity(self,tile,item):
        tile.catalog_context.set_text(entity_label(item,compact=True))
        badge='In library' if members(self.library,item) else 'Related saved entry' if related_members(self.library,item) else ''
        tile.collection_badge.set_text(badge)
        tile.set_tooltip_text('\n'.join(filter(None,('View '+item['name'],entity_label(item),badge+' · shared Steam link' if badge=='Related saved entry' else badge))))

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
            placeholder=console_cover(None,136,204);cover=tile.console_cover
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
        base_url=getattr(getattr(self.catalog,'provider',None),'base','https://umu-tron-api.vercel.app')
        unwarmed=[it['name'] for it in data.get('items',[]) if it.get('name') and fitgirl_cache.get(it['name']) is None]
        if unwarmed and not self.exiting:
            def warm_cards():
                for name in unwarmed[:8]:search_fitgirl_repack(base_url,name)
            self.catalog_job(warm_cards,lambda _:None,lambda _:None,background=True)

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
        panel_limit=Adw.Clamp(maximum_size=1140,tightening_threshold=1140);panel_limit.set_halign(Gtk.Align.START);panel_limit.set_child(panel);outer.append(panel_limit)
        row=box(False,28);panel.append(row);self.detail_row=row
        cover_column=box(spacing=14);cover_column.set_valign(Gtk.Align.START);row.append(cover_column)
        name=game['artwork'].get('portrait') or game['artwork'].get('landscape');self.cover=console_cover(self.library.art_dir/name if name else None,160,240);cover_column.append(self.cover)
        info=box(spacing=16 if self.tv_mode else 14);info.set_hexpand(True)
        summary=Adw.Clamp(maximum_size=960,tightening_threshold=960);summary.set_hexpand(True);summary.set_halign(Gtk.Align.START);summary.set_child(info);row.append(summary)
        info.append(label(game['title'],'detail-title',xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,lines=2,ellipsize=Pango.EllipsizeMode.END))
        entity_text=entity_label(item) if item else ''
        self.detail_entity=label(entity_text,'detail-meta',xalign=0,wrap=True,lines=2,ellipsize=Pango.EllipsizeMode.END)
        self.detail_entity.set_visible(bool(entity_text))
        info.append(self.detail_entity)
        meta=label(' · '.join(filter(None,(game.get('release_date'),game.get('genres')))) or 'Game details','dim-label',xalign=0,wrap=True);meta.add_css_class('detail-meta');info.append(meta)
        excerpt=description_excerpt(game.get('description','')) or 'No description available for this title.'
        info.append(label(excerpt,'detail-copy',xalign=0,wrap=True,lines=3,ellipsize=Pango.EllipsizeMode.END))
        credits=' · '.join(dict.fromkeys(filter(None,(game.get('developers'),game.get('publishers')))))
        credit=label(credits,'dim-label',xalign=0,wrap=True,lines=2,ellipsize=Pango.EllipsizeMode.END);credit.add_css_class('detail-meta');info.append(credit)
        self.detail_size=label('Installation size · Unknown','detail-meta',xalign=0,wrap=True)
        info.append(self.detail_size)
        actions=box(False,12);panel.append(actions);self.detail_actions_box=actions
        saved=self.saved_detail();installed=configured_game(game) and bool(game.get('executable') and Path(game['executable']).is_file())
        if installed:
            primary=button('Play',self.detail_action);primary.add_css_class('suggested-action')
            self.play_buttons={game['id']:primary}
        else:
            primary=button('Install',self.install_detail);primary.add_css_class('suggested-action')
        primary.add_css_class('detail-primary');primary.set_valign(Gtk.Align.CENTER);self.detail_primary=primary
        actions.append(primary)
        if saved:
            lib_btn=button('Remove from library',self.remove_detail);lib_btn.add_css_class('detail-primary')
        else:
            lib_btn=button('Add to library',self.detail_action);lib_btn.add_css_class('detail-primary')
        lib_btn.set_valign(Gtk.Align.CENTER);actions.append(lib_btn)
        self.detail_gear=Gtk.MenuButton(icon_name='emblem-system-symbolic');self.detail_gear.add_css_class('circular');self.detail_gear.set_tooltip_text('Game options');self.detail_gear.set_valign(Gtk.Align.CENTER);actions.append(self.detail_gear)
        popover=style_surface(Gtk.Popover());menu=box(spacing=6);margins(menu,8);popover.set_child(menu);self.detail_gear.set_popover(popover)
        def menu_action(callback):self.detail_gear.popdown();callback()
        menu.append(button('Setup',lambda:menu_action(self.setup_detail)))
        if installed:menu.append(button('Uninstall…',lambda:menu_action(self.review_uninstall)))
        menu.append(button('Game Info',lambda:menu_action(lambda:self.show_game_info(self.game))))
        self.detail_repack=None;self.detail_install_pending=False
        self.detail_download_box=box(spacing=8)
        self.detail_download_box.set_visible(False)
        self.detail_progress_bar=Gtk.ProgressBar()
        self.detail_progress_bar.set_hexpand(True)
        self.detail_progress_bar.add_css_class('suggested-action')
        self.detail_progress_label=label('','caption',xalign=0)
        self.detail_download_box.append(self.detail_progress_bar)
        self.detail_download_box.append(self.detail_progress_label)
        panel.append(self.detail_download_box)
        if download_manager.active_jobs.get(game['id']):
            self.track_download_progress(game['id'])
        game_title=(self.detail_item.get('name') if self.detail_item else self.game.get('title')) or self.game.get('title','')
        cached_repack=fitgirl_cache.get(game_title) if game_title else None
        self.detail_repack=cached_repack;self.detail_install_pending=False
        if cached_repack:
            sz=(cached_repack.get('file_size') or '').strip()
            self.detail_size.set_text(f'FitGirl Repack · Download: {sz}' if sz else 'FitGirl Repack · Available')
        elif cached_repack is False:
            self.detail_size.set_text('Installation size · Unknown')
        else:
            self.detail_size.set_text('Checking FitGirl availability…')
            if game_title and not installed:
                base_url=getattr(getattr(self.catalog,'provider',None),'base','https://umu-tron-api.vercel.app')
                def check_fg_repack():return search_fitgirl_repack(base_url,game_title)
                def fg_repack_loaded(repacks):
                    if repacks:
                        self.detail_repack=repacks[0]
                        sz=(self.detail_repack.get('file_size') or '').strip()
                        if hasattr(self,'detail_size') and self.detail_size:
                            self.detail_size.set_text(f'FitGirl Repack · Download: {sz}' if sz else 'FitGirl Repack · Available')
                        if getattr(self,'detail_install_pending',False):
                            self.detail_install_pending=False
                            self.install_detail()
                    else:
                        self.detail_repack=False
                        if hasattr(self,'detail_size') and self.detail_size:
                            self.detail_size.set_text('Installation size · Unknown')
                        if getattr(self,'detail_install_pending',False):
                            self.detail_install_pending=False
                            self.prompt_no_repack(game_title)
                def fg_repack_failed(error):
                    self.detail_repack=False
                    if hasattr(self,'detail_size') and self.detail_size:
                        self.detail_size.set_text('Installation size · Unknown')
                    if getattr(self,'detail_install_pending',False):
                        self.detail_install_pending=False
                        self.notify(f'Could not reach FitGirl API: {error}')
                self.catalog_job(check_fg_repack,fg_repack_loaded,fg_repack_failed,background=True)
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
            compact=self.get_width()<700
            if self.tv_mode:
                small=self.get_width()<1400 or self.get_height()<850
                if small:self.add_css_class('tv-compact')
                else:self.remove_css_class('tv-compact')
                width=144 if small else 180
                outer.set_margin_start(32 if small else 48);outer.set_margin_end(32 if small else 48)
                outer.set_margin_top(12 if small else 20);outer.set_margin_bottom(20 if small else 28)
            else:
                small=self.get_width()<1400 or self.get_height()<850
                if small:scene.add_css_class('detail-compact')
                else:scene.remove_css_class('detail-compact')
                width=144 if small else 180
                outer.set_margin_start(24 if small else 48);outer.set_margin_end(24 if small else 48)
                outer.set_margin_top(12 if small else 20);outer.set_margin_bottom(24 if small else 28)
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
            else:
                if self.tv_mode and not self.set_tv_mode(False):return
                self.open_manage()
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
    def setup_detail(self):
        if self.saved_detail():
            if self.tv_mode and not self.set_tv_mode(False):return
            self.open_manage()
            return
        if not self.detail_item or self.detail_adding:return
        existing=members(self.library,self.detail_item)
        if len(existing)>1:self.notify('Multiple saved copies exist. Open the desired copy in Library.');return
        if existing:
            self.show_shared_detail(existing[0],self.detail_item)
            if self.tv_mode and not self.set_tv_mode(False):return
            self.open_manage()
            return
        item=deepcopy(self.detail_item)
        draft=item_game(item,preview=False)
        self.game=deepcopy(draft);self.original=deepcopy(draft)
        if self.tv_mode and not self.set_tv_mode(False):return
        self.open_manage()

    def install_detail(self):
        drives=[]
        if hasattr(self,'storage_service') and self.storage_service:
            try:
                state=self.storage_service.snapshot()
                for r in state.get('registrations',[]):
                    if 'install' in r.get('roles',[]):drives.append(r)
            except Exception:pass
        if not drives:
            body=('No install drive has been configured yet.\n\n'
                  'An install drive is required before downloading and installing games. '
                  'Open Settings → Storage to add an install drive.')
            def open_storage():
                if hasattr(self,'open_settings'):self.open_settings(section='storage')
            self.confirm('No Install Drive Configured',body,'Open Settings → Storage',open_storage)
            return

        if not self.saved_detail():
            item=deepcopy(self.detail_item) if self.detail_item else None
            if item:
                draft=item_game(item,preview=False)
                self.game=deepcopy(draft);self.original=deepcopy(draft)
        title=(self.detail_item.get('name') if self.detail_item else self.game.get('title')) or self.game.get('title','')
        if self.detail_repack and isinstance(self.detail_repack,dict):
            self.show_install_repack_dialog(self.detail_repack)
            return
        if self.detail_repack is False:
            self.prompt_no_repack(title)
            return
        self.detail_install_pending=True
        self.detail_status.set_text(f'Finding FitGirl repack for "{title}"…')

    def show_install_repack_dialog(self,repack):
        title=self.game.get('title','Game')
        repack_title=repack.get('title',title)
        repack_size=(repack.get('file_size') or 'Unknown size').strip()
        magnet=repack.get('magnet','')
        drives=[];default_drive=None
        if hasattr(self,'storage_service') and self.storage_service:
            try:
                state=self.storage_service.snapshot()
                for r in state.get('registrations',[]):
                    if 'install' in r.get('roles',[]):drives.append(r)
                default_id=state.get('default_install')
                if default_id:default_drive=next((d for d in drives if d.get('id')==default_id),None)
            except Exception:pass
        if not default_drive and drives:default_drive=drives[0]

        installer_bytes=parse_size_bytes(repack_size)
        installer_b,installed_b,total_req_b=estimate_space_requirements(installer_bytes)
        inst_str=format_size(installer_b)
        game_str=format_size(installed_b)
        req_str=format_size(total_req_b)

        dialog=modal_window(self,f'Install {title}',width=640,height=520,subtitle=f'FitGirl Repack · {repack_size}')
        content=dialog_body(dialog)
        _,button_fn,_,_,_=ui()
        repack_group=Adw.PreferencesGroup(title='Matched FitGirl Repack')
        repack_row=Adw.ActionRow(title=repack_title,subtitle=f'Installer download size: {repack_size}')
        repack_row.set_use_markup(False);repack_row.set_subtitle_lines(3);repack_group.add(repack_row);content.append(repack_group)

        space_group=Adw.PreferencesGroup(title='Storage Requirement')
        content.append(space_group)
        space_row=Adw.ActionRow(title=f'Total Required Space: ~{req_str}')
        space_row.set_subtitle(f'Installer: {inst_str} + Estimated Game: {game_str}')
        space_row.set_use_markup(False);space_row.set_subtitle_lines(2);space_group.add(space_row)

        drive_group=Adw.PreferencesGroup(title='Installation Drive',description='Choose the destination drive for this game.')
        content.append(drive_group)
        selected_drive_path=[default_drive['path'] if default_drive else str(Path.home()/'Games')]
        target_preview=Adw.ActionRow(title='Destination folder');target_preview.set_use_markup(False)

        def get_free_bytes(p):
            curr=Path(p)
            while not curr.exists() and curr!=curr.parent:
                curr=curr.parent
            try:
                st=os.statvfs(curr)
                return st.f_bavail*st.f_frsize
            except Exception:
                for d in drives:
                    if d.get('path')==p and d.get('free'):
                        return d['free']
                return 0
        install_btn=button_fn('Download & Install',None,'suggested-action')

        def update_space_and_target():
            sanitized=re.sub(r'[^\w\s-]','',title).strip() or 'Game'
            target_preview.set_subtitle(f'{selected_drive_path[0]}/{sanitized}')
            free_b=get_free_bytes(selected_drive_path[0])
            free_str=format_size(free_b)
            if free_b < total_req_b:
                space_row.set_title(f'⚠️ Insufficient Disk Space: Requires ~{req_str}')
                space_row.set_subtitle(f'Installer ({inst_str}) + Game ({game_str}) = ~{req_str}. Selected drive only has {free_str} free.')
                install_btn.set_sensitive(False)
            else:
                space_row.set_title(f'✓ Sufficient Disk Space: ~{req_str} Required')
                space_row.set_subtitle(f'Installer: {inst_str} + Game: {game_str} ({free_str} available on selected drive)')
                install_btn.set_sensitive(True)

        if drives:
            options_group=None
            for entry in drives:
                is_default=(default_drive and entry.get('id')==default_drive.get('id'))
                free_str=f" · {entry['free']//(1024**3)} GB free" if entry.get('free') else ""
                row=Adw.ActionRow(title=entry.get('label','Drive')+(' · Default' if is_default else ''),subtitle=entry.get('path','')+free_str)
                row.set_use_markup(False)
                check=Gtk.CheckButton(valign=Gtk.Align.CENTER)
                if options_group is None:options_group=check
                else:check.set_group(options_group)
                if is_default:check.set_active(True)
                def on_toggle(btn,p=entry.get('path')):
                    if btn.get_active():
                        selected_drive_path[0]=p;update_space_and_target()
                check.connect('toggled',on_toggle);row.add_suffix(check);row.set_activatable_widget(check);drive_group.add(row)

        drive_group.add(target_preview)
        update_space_and_target()

        footer=dialog_footer();content.append(footer)
        cancel_btn=button_fn('Cancel',dialog.close);footer.append(cancel_btn)

        def on_confirm():
            dialog.close()
            sanitized=re.sub(r'[^\w\s-]','',title).strip() or 'Game'
            dest_dir=f'{selected_drive_path[0]}/{sanitized}'
            download_dir=f'{selected_drive_path[0]}/.umutron-downloads/{self.game["id"]}'
            self.game['working_dir']=dest_dir
            self.start_fitgirl_download(magnet,download_dir,dest_dir,repack_title,inst_str)

        install_btn.connect('clicked',lambda *_:on_confirm())
        footer.append(install_btn);dialog.present()

    def start_fitgirl_download(self,magnet,download_dir,dest_dir,repack_title,inst_str):
        title=self.game.get('title','Game')
        game_id=self.game['id']
        try:
            download_manager.start_download(magnet,download_dir,game_id,title)
        except Exception as error:
            self.error(error);return
        self.track_download_progress(game_id,download_dir,dest_dir,inst_str)

    def track_download_progress(self,game_id,download_dir=None,dest_dir=None,inst_str=None):
        if hasattr(self,'detail_download_box'):
            self.detail_download_box.set_visible(True)
        if hasattr(self,'detail_primary'):
            self.detail_primary.set_label('Pause')
            self.detail_primary.set_tooltip_text('Pause downloading FitGirl repack')

            def toggle_pause(*_):
                job=download_manager.get_status(game_id)
                if job and job.get('status')=='paused':
                    download_manager.resume(game_id)
                    self.detail_primary.set_label('Pause')
                else:
                    download_manager.pause(game_id)
                    self.detail_primary.set_label('Resume')

            self.detail_primary.connect('clicked',toggle_pause)

        if not hasattr(self,'detail_cancel_btn') or not self.detail_cancel_btn.get_parent():
            _,button_fn,_,_,_=ui()
            self.detail_cancel_btn=button_fn('Cancel Download',lambda:self.cancel_fitgirl_download(game_id),'destructive-action')
            self.detail_actions_box.append(self.detail_cancel_btn)

        def poll_tick():
            if self.route!='detail' or not self.game or self.game['id']!=game_id:
                return False
            job=download_manager.get_status(game_id)
            if not job:return False
            status=job.get('status')
            if status=='complete':
                self.on_fitgirl_download_complete(game_id,download_dir or job.get('dir'),dest_dir,inst_str)
                return False
            elif status=='paused':
                self.detail_primary.set_label('Resume')
                pct=job.get('percent',0.0)
                self.detail_progress_bar.set_fraction(pct/100.0)
                self.detail_progress_label.set_text(f"Paused · {pct:.1f}% ({format_size(job.get('completed_bytes'))} / {format_size(job.get('total_bytes'))})")
            elif status=='active':
                self.detail_primary.set_label('Pause')
                pct=job.get('percent',0.0)
                self.detail_progress_bar.set_fraction(pct/100.0)
                speed_str=job.get('speed_text','0 B/s')
                eta_str=f" · ETA {job['eta_text']}" if job.get('eta_text') else ""
                self.detail_progress_label.set_text(f"{pct:.1f}% · {format_size(job.get('completed_bytes'))} / {format_size(job.get('total_bytes'))} · {speed_str}{eta_str}")
            return True

        GLib.timeout_add(1000,poll_tick)

    def cancel_fitgirl_download(self,game_id):
        def do_cancel():
            download_manager.cancel(game_id,cleanup=True)
            if any(g['id']==game_id for g in self.library.games()):
                self.show_shared_detail(self.game,self.detail_item)
            elif getattr(self,'detail_item',None):
                self.show_shared_detail(item_game(self.detail_item,preview=True),self.detail_item)
            else:
                self.show_collection()
            self.notify('Download cancelled and files cleaned up.')
        self.confirm('Cancel Download?','This will stop the download and remove any partial download files.','Cancel Download',do_cancel,destructive=True)

    def on_fitgirl_download_complete(self,game_id,download_dir,dest_dir,inst_str):
        if hasattr(self,'detail_primary'):
            self.detail_primary.set_label('Installing...')
            self.detail_primary.set_sensitive(False)
        if hasattr(self,'detail_progress_bar'):
            self.detail_progress_bar.set_fraction(1.0)
        if hasattr(self,'detail_progress_label'):
            self.detail_progress_label.set_text('Download complete. Launching FitGirl installer through UMU…')
        setup_exe=download_manager.find_setup_exe(download_dir)
        if not setup_exe:
            self.notify('Could not find setup.exe in downloaded files.')
            return

        title=self.game.get('title','Game')
        self.game['installation']={
            'mode':'installer',
            'installer':str(setup_exe),
            'confirmed':False
        }
        self.game['working_dir']=dest_dir
        if not any(g['id']==self.game['id'] for g in self.library.games()) and getattr(self,'detail_item',None):
            self._save_detail_item_artwork(self.game)

        try:
            self.installations.start(self.game)
            self.refresh_launch_state()
            self.notify(f'FitGirl installer started for {title}.')
        except Exception as error:
            self.error(error)

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
            self.library.delete(game['id']);self.return_from_detail();self.notify('Removed from library. Game files, saves and prefixes were kept.')
        def confirmed():
            try:remove()
            except Exception as error:self.error(error)
        self.confirm('Remove '+game['title']+' from library?','Only its library entry is removed. Game files, saves, prefixes and Proton are kept.','Remove from library',confirmed,True)

    def review_uninstall(self):
        game=deepcopy(self.game)
        from .game_uninstall import detect_game_root, folder_summary, remove_game_directory
        detected_root=detect_game_root(game,self.library)
        if not detected_root or not Path(detected_root).is_dir():
            body=('Could not safely isolate a dedicated installation folder for this game.\n\n'
                  'To protect against unintended data loss, automatic folder deletion is disabled. '
                  'You can remove this game card from your library using "Remove from library".')
            self.confirm('Uninstall '+game['title']+'?',body,'Remove from library',self.remove_detail)
            return
        file_count,total_size,size_str=folder_summary(detected_root)
        body=(f'Game folder to remove:\n{detected_root}\n\n'
              f'({size_str} · {file_count} files)\n\n'
              'This will permanently delete this game installation folder and remove its library record. '
              'Game saves and Wine prefixes are kept separate.')
        def do_uninstall():
            if self.demo:self.error(ValueError('File deletion is disabled in the visual demo.'));return
            if self.launcher.active():self.error(RuntimeError('Finish the active game or installer first.'));return
            if not self.game or self.game['id']!=game['id']:return
            def run_delete():
                remove_game_directory(detected_root)
                self.library.delete(game['id'])
            def complete(_):
                self.return_from_detail()
                self.notify(f'{game["title"]} uninstalled and files removed.')
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
