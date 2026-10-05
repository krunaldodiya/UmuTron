"""Explicit native browse menus with owned focus and bounded choice lists."""
from gi.repository import GObject, Gtk, Pango
from .dialogs import style_surface


class BrowseChoice(Gtk.MenuButton):
    """A labeled choice button; the selected-index API matches native selectors."""

    def __init__(self, title, choices):
        super().__init__()
        self.title = title
        self.model = Gtk.StringList.new(choices)
        self._selected = 0
        self.rows = []
        self.model_revision = 0
        self.add_css_class('browse-choice')
        content = Gtk.Box(spacing=8)
        self.caption = Gtk.Label(ellipsize=Pango.EllipsizeMode.END, max_width_chars=24)
        content.append(self.caption)
        content.append(Gtk.Image.new_from_icon_name('pan-down-symbolic'))
        self.set_child(content)
        self.menu = style_surface(Gtk.Popover())
        self.menu.browse_owner = self
        self.menu.connect('closed', self.closed)
        self.menu.connect('notify::visible', self.opened)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for edge in ('top', 'bottom', 'start', 'end'):
            getattr(self.list, 'set_margin_' + edge)(8)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                   min_content_width=240, max_content_height=340,
                                   propagate_natural_height=True)
        # NEVER horizontal policy otherwise measures ellipsized rows at their
        # tiny minimum width. Keep a readable, bounded menu in compact windows.
        scroll.set_size_request(320, -1)
        scroll.set_child(self.list)
        self.scroll = scroll
        self.menu.set_child(scroll)
        self.set_popover(self.menu)
        self.rebuild()

    @GObject.Property(type=int, default=0, minimum=0)
    def selected(self):
        return self._selected

    @selected.setter
    def selected(self, value):
        self._selected = min(value, max(0, self.model.get_n_items() - 1))
        self.refresh_caption()

    def get_selected(self):
        return self.selected

    def set_selected(self, value):
        if value != self._selected:
            self.selected = value
        else:
            self.refresh_caption()

    def get_model(self):
        return self.model

    def set_model(self, model):
        self.model = model
        self._selected = min(self._selected, max(0, model.get_n_items() - 1))
        self.rebuild()

    def refresh_caption(self):
        selected = self.model.get_string(self._selected) or ''
        caption = self.title + (' · ' + selected if selected else '')
        self.caption.set_text(caption)
        self.set_tooltip_text(caption)
        self.update_property([Gtk.AccessibleProperty.LABEL], [caption])
        for index, row in enumerate(self.rows):
            if index == self._selected:
                row.add_css_class('suggested-action')
            else:
                row.remove_css_class('suggested-action')

    def rebuild(self):
        focused = self.get_root().get_focus() if self.get_root() else None
        in_menu = focused is not None and focused.is_ancestor(self.menu)
        previous = focused.get_label() if focused in self.rows else None
        while self.list.get_first_child():
            self.list.remove(self.list.get_first_child())
        self.model_revision += 1
        revision = self.model_revision
        self.rows = []
        for index in range(self.model.get_n_items()):
            row = Gtk.Button(label=self.model.get_string(index), halign=Gtk.Align.FILL)
            row.get_child().set_ellipsize(Pango.EllipsizeMode.END)
            row.get_child().set_max_width_chars(34)
            row.set_tooltip_text(self.model.get_string(index))
            row.connect('clicked', lambda _, i=index, r=revision: self.choose(i, r))
            self.list.append(row)
            self.rows.append(row)
        self.refresh_caption()
        if in_menu and self.rows:
            next((row for row in self.rows if row.get_label() == previous),
                 self.rows[self._selected]).grab_focus()

    def choose(self, index, revision):
        if revision != self.model_revision or self.get_root() is None or not self.get_mapped():
            return
        self.popdown()
        self.set_selected(index)
        root = self.get_root()
        if root is not None and self.get_mapped():
            # A selection can synchronously rebuild cards. Its queued restore
            # must yield to the user's explicit return to this menu button.
            root.mark_browse_input()
            self.grab_focus()
            root.update_focus_outline()

    def opened(self, *_):
        if self.menu.get_visible() and self.rows:
            root = self.get_root()
            if root:
                root.mark_browse_input()
            self.rows[self._selected].grab_focus()

    def closed(self, *_):
        root = self.get_root()
        focus = root.get_focus() if root else None
        if root and self.get_mapped() and (focus is None or focus.is_ancestor(self.menu)):
            self.grab_focus()
            root.update_focus_outline()
