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
from .library import Library, ART_KINDS, image_extension
from .metadata import search, fetch_game
from .steam import SteamSync, discover_accounts
from .providers import Credentials, IGDB, SteamGridDB
from . import metadata


def label(text, css=None, **kwargs):
    result=Gtk.Label(label=text,**kwargs)
    if css: result.add_css_class(css)
    return result


def button(text, callback, css=None, icon=None):
    result=Gtk.Button(label=text)
    if icon: result.set_icon_name(icon); result.set_tooltip_text(text)
    if css: result.add_css_class(css)
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
        super().__init__(application=app,title='Steam Library Metadata Manager',default_width=1120,default_height=800)
        self.demo=demo
        self.library=library; self.engine=SteamSync(library, running=lambda:False) if demo else SteamSync(library)
        self.credentials=Credentials(library.root/'demo-provider-settings') if demo else Credentials(); self.igdb=IGDB(self.credentials); self.sgdb=SteamGridDB(self.credentials)
        self.pool=ThreadPoolExecutor(max_workers=2)
        self.busy=False; self.game=None; self.original=None; self.fields={}; self.log_lines=[]
        self.connect('close-request',self.close_requested)
        self.toast=Adw.ToastOverlay(); self.set_content(self.toast)
        self.layout=box(spacing=0); self.toast.set_child(self.layout)
        self.header=Adw.HeaderBar()
        self.back=button('Back to library',self.go_back,icon='go-previous-symbolic')
        self.back.set_visible(False); self.header.pack_start(self.back)
        self.heading=Adw.WindowTitle(title='Your game library',subtitle='Non-Steam metadata · manual sync')
        self.header.set_title_widget(self.heading)
        self.theme=Gtk.DropDown.new_from_strings(['Follow system','Light','Dark'])
        self.theme.set_tooltip_text('Appearance')
        self.theme.set_selected(['system','light','dark'].index(self.library.data['settings'].get('theme','system')))
        self.theme.connect('notify::selected',self.theme_changed)
        self.header.pack_end(self.theme)
        self.header.pack_end(button('Settings',self.open_settings,icon='preferences-system-symbolic'))
        self.layout.append(self.header)
        if demo:
            demo_banner=Adw.Banner(title='DEMO · fictional games and a mock Steam folder · your real library is untouched',revealed=True)
            self.layout.append(demo_banner)
        self.progress=box(False,8); margins(self.progress,10)
        self.spinner=Gtk.Spinner(); self.progress.append(self.spinner)
        self.progress_label=label(''); self.progress.append(self.progress_label)
        self.progress.set_visible(False); self.layout.append(self.progress)
        self.body=box(spacing=0); self.body.set_vexpand(True); self.layout.append(self.body)
        log_button=button('Activity',self.toggle_log,icon='view-list-symbolic'); self.header.pack_end(log_button)
        self.log_revealer=Gtk.Revealer(); self.log_text=Gtk.TextView(editable=False,cursor_visible=False,wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.log_text.set_top_margin(10); self.log_text.set_left_margin(16)
        log_scroll=Gtk.ScrolledWindow(min_content_height=110,max_content_height=160,propagate_natural_height=True)
        log_scroll.set_child(self.log_text); self.log_revealer.set_child(log_scroll); self.layout.append(self.log_revealer)
        self.apply_theme(); self.show_library()

    def log(self,text):
        self.log_lines.append(datetime.now().strftime('%H:%M')+'  '+str(text))
        self.log_lines=self.log_lines[-100:]
        self.log_text.get_buffer().set_text('\n'.join(self.log_lines))

    def notify(self,text):
        self.log(text); self.toast.add_toast(Adw.Toast.new(text))

    def error(self,error):
        self.log('Error: '+str(error))
        dialog=Adw.MessageDialog.new(self,'Could not complete this action',str(error)[:2000])
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
        self.busy=True; self.body.set_sensitive(False); self.header.set_sensitive(False)
        modal_windows=[w for w in Gtk.Window.get_toplevels() if w.get_transient_for()==self]
        for modal in modal_windows: modal.set_sensitive(False)
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
        dialog=Adw.MessageDialog.new(self,title,body)
        dialog.add_response('cancel','Cancel'); dialog.add_response('confirm',action)
        dialog.set_default_response('cancel'); dialog.set_close_response('cancel')
        dialog.set_response_appearance('confirm',Adw.ResponseAppearance.DESTRUCTIVE if destructive else Adw.ResponseAppearance.SUGGESTED)
        dialog.connect('response',lambda _,response:callback() if response=='confirm' else None)
        dialog.present()

    def choose_file(self,title,callback,save=False,folder=False,filename=None):
        action=Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.OPEN
        dialog=Gtk.FileChooserNative.new(title,self,action,'Save' if save else 'Select','Cancel')
        if filename: dialog.set_current_name(filename)
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
        self.game=None; self.original=None; clear(self.body)
        self.theme.set_selected(['system','light','dark'].index(self.library.data['settings'].get('theme','system'))); self.apply_theme()
        self.heading.set_title('Your game library'); self.heading.set_subtitle('Non-Steam metadata · manual sync'); self.back.set_visible(False)
        panel=box(); margins(panel); self.body.append(panel)
        top=box(False); panel.append(top)
        intro=box(spacing=4); intro.set_hexpand(True)
        intro.append(label('Make your library yours','title-1',xalign=0))
        intro.append(label('Organize artwork and details. Sync to Steam when you choose.','dim-label',xalign=0,wrap=True))
        top.append(intro); top.append(button('Add game',self.add_game,'suggested-action'))
        toolbar=box(False,8); panel.append(toolbar)
        self.filter=Gtk.SearchEntry(placeholder_text='Search your library',hexpand=True)
        self.filter.connect('search-changed',lambda _:self.render_cards())
        toolbar.append(self.filter)
        self.library_status=label('','dim-label',xalign=0); panel.append(self.library_status)
        self.library_stack=Gtk.Stack(); self.library_stack.set_vexpand(True); self.body.append(self.library_stack)
        empty=Adw.StatusPage(title='A home for your non-Steam games',description='Add an executable, find its metadata, and choose the artwork you like. Nothing is sent to Steam until you confirm a sync.',icon_name='applications-games-symbolic')
        empty_button=button('Add your first game',self.add_game,'suggested-action'); empty_button.set_halign(Gtk.Align.CENTER)
        empty.set_child(empty_button)
        self.library_stack.add_named(empty,'empty')
        self.flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=12,row_spacing=12,homogeneous=True,min_children_per_line=1,max_children_per_line=7)
        self.flow.set_valign(Gtk.Align.START); self.flow.set_halign(Gtk.Align.START); margins(self.flow)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER); scroll.set_child(self.flow)
        self.library_stack.add_named(scroll,'games')
        self.render_cards()

    def render_cards(self):
        clear(self.flow)
        games=self.library.games(); query=self.filter.get_text().casefold()
        shown=[g for g in games if query in g['title'].casefold()]
        self.library_status.set_text(f'{len(games)} games · {sum(self.library.status(g)!="Synced" for g in games)} not synced or changed')
        self.library_stack.set_visible_child_name('empty' if not games else 'games')
        if not shown and games:
            self.flow.append(label('No games match your search.','dim-label')); return
        for game in sorted(shown,key=lambda g:g['title'].casefold()):
            tile=Gtk.Button(); tile.add_css_class('card'); tile.add_css_class('game-card')
            tile.set_tooltip_text('Edit '+game['title']); tile.connect('clicked',lambda _,g=game:self.show_game(g))
            content=box(spacing=8)
            content.append(self.picture(game['artwork'].get('portrait'),128,170))
            title=label(game['title'],'heading',width_chars=18,max_width_chars=18,ellipsize=Pango.EllipsizeMode.END,xalign=0); content.append(title)
            for done,text in self.progress_items(game):
                content.append(label(('✓ ' if done else '○ ')+text,'caption',xalign=0))
            if not Path(game['executable']).is_file(): content.append(label('Relink needed','warning',xalign=0))
            tile.set_child(content); self.flow.append(tile)

    def add_game(self):
        self.show_game(self.library.new_game())
        self.find_metadata(new_game=True)

    def entry(self,container,key,title,hint=None):
        wrapper=box(spacing=6); wrapper.append(label(title,'heading',xalign=0))
        entry=Gtk.Entry(text=self.game.get(key,''),hexpand=True)
        entry.set_tooltip_text(title); wrapper.append(entry); self.fields[key]=entry
        if hint: wrapper.append(label(hint,'caption',xalign=0,wrap=True))
        container.append(wrapper); return entry

    def show_game(self,game):
        self.game=deepcopy(game); self.original=deepcopy(game); self.fields={}; clear(self.body)
        self.back.set_visible(True); self.heading.set_title(game['title'] or 'Add a game')
        self.heading.set_subtitle(self.library.status(game))
        top=box(False,18); top.set_vexpand(False); margins(top); self.body.append(top)
        self.cover=self.picture(game['artwork'].get('portrait'),105,145); top.append(self.cover)
        summary=box(spacing=8); summary.set_hexpand(True); top.append(summary)
        summary.append(label('Game details','title-1',xalign=0))
        summary.append(label('Metadata stays here. Steam receives shortcut details and artwork.','dim-label',wrap=True,xalign=0))
        self.source_label=label(self.source_text(),'caption',xalign=0); summary.append(self.source_label)
        summary.append(button('Find metadata by name or provider ID',self.find_metadata))
        self.progress_labels=[]
        progress=box(False,12); summary.append(progress)
        for _ in range(3):
            item=label('', 'caption', xalign=0, wrap=True); progress.append(item); self.progress_labels.append(item)
        tabs=Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE); self.detail_tabs=tabs
        tabs.set_vexpand(True); switcher=Gtk.StackSwitcher(stack=tabs,halign=Gtk.Align.CENTER)
        self.body.append(switcher); self.body.append(tabs)
        overview=box(); margins(overview)
        self.entry(overview,'title','Title')
        row=box(False); overview.append(row)
        for key,title in (('release_date','Release date'),('developers','Developers'),('publishers','Publishers')):
            col=box(); col.set_hexpand(True); row.append(col); self.entry(col,key,title)
        self.entry(overview,'genres','Genres')
        overview.append(label('Description','heading',xalign=0))
        self.description=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.description.set_top_margin(12); self.description.set_bottom_margin(12); self.description.set_left_margin(12); self.description.set_right_margin(12)
        self.description.get_buffer().set_text(game['description'])
        desc_scroll=Gtk.ScrolledWindow(min_content_height=190); desc_scroll.add_css_class('card'); desc_scroll.set_child(self.description); overview.append(desc_scroll)
        tabs.add_titled(self.scrolled(overview),'overview','Overview')
        self.art_page=box(); margins(self.art_page); self.render_artwork()
        tabs.add_titled(self.scrolled(self.art_page),'artwork','Artwork')
        launch=box(); margins(launch)
        self.entry(launch,'executable','Game executable','This app never runs the selected file.')
        launch.append(button('Choose / relink executable',self.pick_executable))
        self.path_warning=label('','warning',xalign=0,wrap=True); launch.append(self.path_warning)
        self.fields['executable'].connect('changed',lambda _:self.update_path_warning())
        self.entry(launch,'working_dir','Working directory','Leave blank to use the executable’s folder.')
        launch.append(button('Choose working directory',lambda:self.choose_file('Working directory',lambda p:self.fields['working_dir'].set_text(str(p)),folder=True)))
        self.entry(launch,'arguments','Launch arguments','Copied to Steam as text; never executed here. Choose Proton in Steam yourself.')
        launch.append(label('Steam store metadata ID and your non-Steam shortcut ID are kept separate. Relinking updates the existing shortcut after you explicitly sync.','dim-label',wrap=True,xalign=0))
        tabs.add_titled(self.scrolled(launch),'steam','Steam settings')
        footer=box(False,10); margins(footer,16); footer.add_css_class('toolbar')
        note=label('Save is local. Sync always asks first.','dim-label',xalign=0,hexpand=True); footer.append(note)
        delete=button('Delete game',self.delete_game,icon='user-trash-symbolic')
        delete.set_sensitive(any(g['id']==game['id'] for g in self.library.games())); footer.append(delete)
        footer.append(button('Sync',self.sync_saved))
        footer.append(button('Save',lambda:self.save_game(False)))
        footer.append(button('Save & Sync',lambda:self.save_game(True),'suggested-action'))
        self.body.append(footer); self.update_path_warning()
        for widget in self.fields.values(): widget.connect('changed',lambda _:self.update_progress())
        self.description.get_buffer().connect('changed',lambda _:self.update_progress())
        self.update_progress()

    def progress_items(self,game):
        metadata=bool(game.get('metadata_source') or game.get('metadata_app_id') or (game['title'].strip() and game['description'].strip()))
        executable=bool(game['executable'] and Path(game['executable']).is_file())
        synced=self.library.status(game)=='Synced'
        return zip((metadata,executable,synced),('Game metadata added','Game executable connected','Synced to Steam'))

    def update_progress(self):
        for item,(done,text) in zip(self.progress_labels,self.progress_items(self.collect())):
            item.set_text(('✓ ' if done else '○ ')+text)
            item.set_tooltip_text(('Complete: ' if done else 'Pending: ')+text)

    def source_text(self):
        source=self.game.get('metadata_source',{})
        if source: return source['provider'].upper()+' metadata ID: '+str(source['id'])
        return 'Steam metadata ID: '+str(self.game['metadata_app_id']) if self.game['metadata_app_id'] else 'No metadata match yet · you can enter details manually'

    @staticmethod
    def scrolled(child):
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,vscrollbar_policy=Gtk.PolicyType.AUTOMATIC); scroll.set_vexpand(True); scroll.set_child(child); return scroll

    def collect(self):
        game=deepcopy(self.game)
        for key,widget in self.fields.items(): game[key]=widget.get_text()
        buf=self.description.get_buffer(); game['description']=buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False)
        return game

    def dirty(self): return self.game is not None and self.collect()!=self.original

    def go_back(self):
        if self.dirty(): self.confirm('Leave without saving?','Your unsaved edits will be discarded.','Discard edits',self.show_library,True)
        else: self.show_library()

    def close_requested(self,*_):
        if self.busy:
            self.notify('An operation is still running. Please wait before closing.'); return True
        if self.dirty():
            self.confirm('Close without saving?','Your unsaved edits will be discarded.','Discard and close',self.destroy,True); return True
        return False

    def update_path_warning(self):
        path=self.fields['executable'].get_text()
        self.path_warning.set_text('Executable not found. Metadata can still be saved; relink before syncing.' if not path or not Path(path).is_file() else '')

    def pick_executable(self):
        def selected(path):
            self.fields['executable'].set_text(str(path))
            if not self.fields['working_dir'].get_text(): self.fields['working_dir'].set_text(str(path.parent))
            if not self.fields['title'].get_text(): self.fields['title'].set_text(path.stem)
        self.choose_file('Choose game executable',selected)

    def render_artwork(self):
        if 'arguments' in self.fields: self.update_progress()
        clear(self.art_page)
        self.art_page.append(label('Your artwork collection','title-2',xalign=0))
        self.art_page.append(button('Browse SteamGridDB artwork',self.find_sgdb))
        self.art_page.append(label('Steam artwork availability varies. Choose local PNG or JPEG files for missing images.','dim-label',wrap=True,xalign=0))
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
        dialog=Gtk.Window(title='Find game metadata',transient_for=self,modal=True,default_width=620,default_height=530)
        content=box(); margins(content); dialog.set_child(content)
        content.append(label('Find the right game','title-1',xalign=0))
        content.append(label('Choose a provider, then search by title or its game ID. Selecting a match fills your local draft.','dim-label',wrap=True,xalign=0))
        row=box(False); content.append(row)
        provider=Gtk.DropDown.new_from_strings(['Steam','IGDB']); provider.set_tooltip_text('Metadata provider'); row.append(provider)
        query=Gtk.Entry(placeholder_text='Game name or provider ID',hexpand=True,text=self.fields['title'].get_text()); row.append(query)
        results=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE); results.add_css_class('boxed-list')
        scroll=self.scrolled(results); scroll.set_vexpand(True)
        status=label('','dim-label',wrap=True,xalign=0)
        chosen=[False]
        def cancel():
            dialog.destroy()
            if new_game and not chosen[0]: self.show_library()
        def selected(item):
            chosen[0]=True
            selected_provider='steam' if provider.get_selected()==0 else 'igdb'
            dialog.destroy()
            def loaded(result):
                info,art,missing=result
                self.game=self.collect(); self.game.update(info)
                self.game['metadata_source']={'provider':selected_provider,'id':item['id']}
                if selected_provider=='igdb': self.game['metadata_app_id']=None
                for kind,data in art.items():
                    try:
                        image_extension(data)
                        Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
                        self.game['artwork'][kind]=self.library.add_image(data)
                    except (ValueError,GLib.Error): missing.append(kind)
                original=self.original
                self.show_game(self.game); self.original=original
                if new_game: self.detail_tabs.set_visible_child_name('steam')
                self.notify('Metadata loaded. Review and save locally.'+(' Missing artwork: '+', '.join(missing)+'.' if missing else ''))
            self.async_job('Fetching metadata and artwork…',lambda:fetch_game(item['id']) if selected_provider=='steam' else self.igdb.fetch(item['id']),loaded)
        def run_search():
            if self.busy: return
            search_button.set_sensitive(False); query.set_sensitive(False); clear(results); status.set_text('Searching provider…')
            def loaded(items):
                search_button.set_sensitive(True); query.set_sensitive(True)
                status.set_text(f'{len(items)} matches. Select one to preview its metadata.' if items else 'No matching games. Try another title or ID.')
                for item in items:
                    action=Adw.ActionRow(title=item['name'],subtitle='Provider ID '+str(item['id']))
                    choose=button('Select',lambda i=item:selected(i)); choose.set_valign(Gtk.Align.CENTER)
                    action.set_use_markup(False); action.add_suffix(choose); action.set_activatable_widget(choose); results.append(action)
            # Restore dialog controls on failures as well as successes.
            def work():
                try: return search(query_text) if provider_index==0 else self.igdb.search(query_text)
                finally: GLib.idle_add(lambda:(search_button.set_sensitive(True),query.set_sensitive(True),False)[-1])
            query_text=query.get_text(); provider_index=provider.get_selected()
            self.async_job('Searching game metadata…',work,loaded)
        search_button=button('Search',run_search,'suggested-action'); row.append(search_button)
        query.connect('activate',lambda _:run_search())
        content.append(status); content.append(scroll)
        bottom=box(False)
        bottom.append(button('Cancel',cancel))
        if new_game: bottom.append(button('Enter details manually',dialog.destroy))
        content.append(bottom)
        dialog.connect('close-request',lambda _:(self.show_library() if new_game and not chosen[0] else None,False)[-1])
        dialog.present(); query.grab_focus()

    def open_settings(self):
        dialog=Adw.PreferencesWindow(title='Settings',transient_for=self,modal=True,default_width=660,default_height=740)
        page=Adw.PreferencesPage(title='General',icon_name='preferences-system-symbolic'); dialog.add(page)
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
            ('Import library','Preview new entries and conflicts before restoring.','Import ZIP',self.import_backup),
            ('Undo latest Steam sync','Recover previous Steam files while Steam is closed.','Review undo',self.undo)):
            row=Adw.ActionRow(title=title,subtitle=subtitle)
            control=button(action,lambda c=callback:leave_then(c)); control.set_valign(Gtk.Align.CENTER)
            row.add_suffix(control); backup.add(row)
        providers_page=Adw.PreferencesPage(title='Providers',icon_name='network-server-symbolic'); dialog.add(providers_page)
        group=Adw.PreferencesGroup(title='Metadata and artwork',description='Steam needs no credentials. IGDB supplies details; SteamGridDB supplies community artwork. IGN is not included.'); providers_page.add(group)
        settings=self.credentials.load(); fields={}
        for key,title in (('igdb_client_id','IGDB / Twitch client ID'),('igdb_client_secret','IGDB / Twitch client secret'),('steamgriddb_key','SteamGridDB API key')):
            entry=Adw.PasswordEntryRow(title=title) if key!='igdb_client_id' else Adw.EntryRow(title=title)
            entry.set_text(settings[key]); group.add(entry); fields[key]=entry
        info=Adw.PreferencesGroup(description='Credentials are saved in a private local file readable only by your user, outside library ZIP backups. They are not encrypted. Clear a field and save to remove it.'); providers_page.add(info)
        links=box(False)
        links.append(Gtk.LinkButton.new_with_label('https://api-docs.igdb.com/#getting-started','IGDB setup'))
        links.append(Gtk.LinkButton.new_with_label('https://www.steamgriddb.com/profile/preferences/api','Get SteamGridDB key'))
        info.add(links)
        def save():
            try:
                self.credentials.save({k:v.get_text() for k,v in fields.items()})
                self.igdb=IGDB(self.credentials); self.sgdb=SteamGridDB(self.credentials)
                self.notify('Provider settings saved privately.')
            except Exception as e: self.error(e)
        info.add(button('Save provider settings',save,'suggested-action'))
        dialog.present()

    def find_sgdb(self):
        dialog=Gtk.Window(title='SteamGridDB artwork',transient_for=self,modal=True,default_width=650,default_height=520)
        content=box(); margins(content); dialog.set_child(content)
        content.append(label('Find artwork for your game','title-1',xalign=0))
        row=box(False); query=Gtk.Entry(text=self.fields['title'].get_text(),placeholder_text='Game name',hexpand=True); row.append(query)
        status=label('Requires your SteamGridDB API key in Settings → Providers.','dim-label',wrap=True,xalign=0)
        results=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE); results.add_css_class('boxed-list')
        def chosen(item): dialog.destroy(); self.art_gallery(item)
        def do_search():
            query_text=query.get_text()
            if not query_text.strip(): return
            clear(results); status.set_text('Searching…')
            def loaded(items):
                status.set_text(f'{len(items)} matching games')
                for item in items:
                    action=Adw.ActionRow(title=item['name'],subtitle='SteamGridDB ID '+str(item['id']))
                    select=button('Choose',lambda i=item:chosen(i)); select.set_valign(Gtk.Align.CENTER)
                    action.set_use_markup(False); action.add_suffix(select); results.append(action)
            self.async_job('Searching SteamGridDB…',lambda:self.sgdb.search(query_text),loaded)
        row.append(button('Search',do_search,'suggested-action')); query.connect('activate',lambda _:do_search())
        content.append(row); content.append(status)
        scroll=self.scrolled(results); scroll.set_vexpand(True); content.append(scroll)
        content.append(button('Close',dialog.destroy)); dialog.present()

    def art_gallery(self,item):
        dialog=Gtk.Window(title='Choose SteamGridDB artwork',transient_for=self,modal=True,default_width=800,default_height=650)
        content=box(); margins(content); dialog.set_child(content)
        content.append(label(item['name'],'title-1',xalign=0))
        kind=Gtk.DropDown.new_from_strings([k.capitalize() for k in ART_KINDS]); content.append(kind)
        status=label('Select an artwork category and load its options.','dim-label',wrap=True,xalign=0); content.append(status)
        flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,min_children_per_line=1,max_children_per_line=3,column_spacing=12,row_spacing=12,homogeneous=True)
        scroll=self.scrolled(flow); scroll.set_vexpand(True)
        def choose(art,selected_kind):
            def work(): return metadata.request(art['url'],20*1024*1024)
            def done(data):
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
            self.async_job('Loading SteamGridDB artwork…',work,loaded)
        content.append(button('Load artwork',load,'suggested-action')); content.append(scroll)
        content.append(button('Done',dialog.destroy)); dialog.present(); load()

    def delete_game(self):
        game_id=self.game['id']; title=self.fields['title'].get_text()
        def remove():
            try:
                self.library.delete(game_id); self.show_library()
                self.notify('Removed from this library. Game files and Steam shortcuts were kept.')
            except Exception as e: self.error(e)
        self.confirm('Delete '+title+'?', 'This removes the local metadata entry. Your game files and any existing Steam shortcut remain untouched. Export a backup first if you want to restore the metadata later.', 'Delete from library', remove, True)

    def save_game(self,sync=False):
        try:
            game=self.collect(); self.library.save(game); self.game=deepcopy(game); self.original=deepcopy(game)
            self.update_progress()
            self.heading.set_title(game['title']); self.heading.set_subtitle(self.library.status(game)); self.notify('Saved locally. Steam has not been changed.')
            if sync: self.select_account(game)
        except Exception as e: self.error(e)

    def sync_saved(self):
        if self.dirty(): self.error(ValueError('Save your changes first, or use Save & Sync.')); return
        saved=next((g for g in self.library.games() if g['id']==self.game['id']),None)
        if saved is None: self.error(ValueError('Save this game before syncing.')); return
        self.select_account(saved)

    def select_account(self,game):
        accounts=[self.library.root/'steam/userdata/123'] if self.demo else discover_accounts()
        dialog=Gtk.Window(title='Choose Steam account',transient_for=self,modal=True,default_width=600)
        content=box(); margins(content); dialog.set_child(content)
        content.append(label('Choose the destination','title-2',xalign=0))
        content.append(label('Exit Steam completely first. No game is launched and no Proton settings are changed.','dim-label',xalign=0,wrap=True))
        def selected(path):
            dialog.destroy()
            self.async_job('Preparing Steam change preview…',lambda:self.engine.preview(game,path),self.show_sync_preview)
        for path in accounts:
            content.append(button('Steam account '+path.name,lambda p=path:selected(p)))
        if not accounts: content.append(label('No native Steam accounts detected. Sign into Steam once, then exit it.','warning',wrap=True))
        if not self.demo:
            content.append(button('Choose userdata account folder…',lambda:self.choose_file('Choose Steam userdata account folder',selected,folder=True)))
        content.append(button('Cancel',dialog.destroy)); dialog.present()

    def show_sync_preview(self,plan):
        dialog=Gtk.Window(title='Review Steam changes',transient_for=self,modal=True,default_width=660,default_height=500)
        content=box(); margins(content); dialog.set_child(content)
        content.append(label('Ready to sync?','title-1',xalign=0))
        content.append(label(plan['title']+' · account '+Path(plan['account']).name,'heading',xalign=0))
        details=label('\n\n'.join(plan['changes'])+'\n\nLaunch ID: '+str(plan['shortcut_id'])+'\n\nFull descriptions and release information stay in this app. Steam receives its supported fields only. A backup will be kept for Undo.',xalign=0,wrap=True,selectable=True)
        scroll=self.scrolled(details); scroll.set_vexpand(True); content.append(scroll)
        actions=box(False); actions.append(button('Cancel',dialog.destroy))
        def apply():
            dialog.destroy()
            def done(_):
                current=next(g for g in self.library.games() if g['id']==plan['game_id'])
                self.show_game(current); self.notify('Synced. You can reopen Steam now.')
            self.async_job('Applying reviewed changes and saving recovery backup…',lambda:self.engine.apply(plan),done)
        actions.append(button('Confirm sync to Steam',apply,'suggested-action')); content.append(actions); dialog.present()

    def export_backup(self):
        def selected(path):
            if path.suffix.lower()!='.zip': raise ValueError('Use a filename ending in .zip.')
            self.async_job('Exporting metadata and artwork backup…',lambda:self.library.export_zip(path),lambda _:self.notify('ZIP backup exported. Games and Steam credentials are not included.'))
        self.choose_file('Export library backup',selected,save=True,filename='game-library-backup.zip')

    def import_backup(self):
        def selected(path):
            def preview(result):
                dialog=Adw.MessageDialog.new(self,'Import backup?',f"{result['new']} new games and {result['conflicts']} existing games.\n\n"+'\n'.join(result['titles'][:12])+'\n\nChoose how to handle conflicts. Nothing will sync to Steam.')
                dialog.add_response('cancel','Cancel'); dialog.add_response('keep','Keep existing'); dialog.add_response('replace','Replace conflicts')
                dialog.set_response_appearance('replace',Adw.ResponseAppearance.DESTRUCTIVE)
                def response(_,choice):
                    if choice in ('keep','replace'):
                        self.async_job('Restoring local library…',lambda:self.library.import_zip(path,choice),lambda _:(self.show_library(),self.notify('Backup imported locally. Review paths before manually syncing.')))
                dialog.connect('response',response); dialog.present()
            self.async_job('Validating backup…',lambda:self.library.preview_import(path),preview)
        self.choose_file('Import library backup',selected)

    def undo(self):
        try:
            backup=self.engine.latest_backup()
            if backup is None: self.notify('No Steam sync to undo yet.'); return
            def perform():
                self.async_job('Restoring the previous Steam files…',lambda:self.engine.undo(backup),lambda _:(self.show_library(),self.notify('Last sync undone. Local metadata has been kept.')))
            self.confirm('Undo the most recent sync?','Steam must be closed. Files changed since that sync will not be overwritten. Your local library remains saved.','Undo sync',perform)
        except Exception as e: self.error(e)


class Application(Adw.Application):
    def __init__(self,demo=False):
        self.demo=demo
        super().__init__(application_id='io.github.steam_library_metadata_manager'+('.demo' if demo else ''),flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.connect('activate',self.activate_window)
    def activate_window(self,*_):
        window=self.get_active_window()
        if not window:
            css=Gtk.CssProvider()
            css.load_from_data(b'.art-frame { background: alpha(@window_fg_color, 0.055); border-radius: 12px; padding: 8px; } .game-card { padding: 10px; } .game-card:hover { background: alpha(@accent_color, 0.09); }')
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            try:
                if self.demo:
                    from .demo import prepare_demo
                    library=prepare_demo()
                else: library=Library()
                window=Window(self,library,self.demo)
            except Exception as e:
                window=Adw.ApplicationWindow(application=self,title='Library could not be opened')
                window.set_content(Adw.StatusPage(title='Could not open your library',description=str(e),icon_name='dialog-error-symbolic'))
        window.present()


def main():
    demo='--demo' in sys.argv
    args=[arg for arg in sys.argv if arg!='--demo']
    return Application(demo).run(args)
