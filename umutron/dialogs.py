"""Shared presentation for native dialogs; callers retain action/lifecycle policy.

MessageDialog keeps native response semantics, PreferencesWindow keeps its page
navigation, and popovers keep their menu ownership. FileChooserNative is owned
by the desktop portal and intentionally stays outside app-specific styling.
"""
from gi.repository import Adw, Gdk, GObject, Gtk, Pango


CSS = b'''
/* Same slate, mint and light surfaces as Library and the shared detail page. */
.umu-surface { background-color: #f3f6f8; color: #172b36; }
.umu-surface.umu-dark { background-color: #101b29; color: #edf3ff; }
.umu-surface headerbar { background: #e9eff2; color: #172b36;
  box-shadow: inset 0 -1px alpha(#172b36,.08); }
.umu-surface.umu-dark headerbar { background: #101b29; color: #edf3ff;
  box-shadow: inset 0 -1px alpha(#b4c7e5,.10); }
.umu-surface .umu-body { padding: 24px; }
.umu-surface .umu-footer { padding-top: 16px;
  border-top: 1px solid alpha(#29465b,.12); }
.umu-surface.umu-dark .umu-footer { border-color: alpha(#b4c7e5,.12); }
.umu-surface button { border-radius: 10px; min-height: 28px;
  background-image: none; background-color: #e1e9ed; color: #172b36; }
.umu-surface.umu-dark button { background-color: #263446; color: #edf3ff; }
.umu-surface button:hover { background-color: #d3e3e3; }
.umu-surface.umu-dark button:hover { background-color: #33495c; }
.umu-surface button.suggested-action { background-color: #267c6c; color: white; }
.umu-surface.umu-dark button.suggested-action { background-color: #82e9d0; color: #102a29; }
.umu-surface button.suggested-action:hover { background-color: #206a5c; }
.umu-surface.umu-dark button.suggested-action:hover { background-color: #a6f5df; }
.umu-surface button.destructive-action { background-color: #b83043; color: white; }
.umu-surface.umu-dark button.destructive-action { background-color: #a93249; color: white; }
.umu-surface button.destructive-action:hover { background-color: #cc3d50; }
.umu-surface button:disabled { opacity: .45; }
.umu-surface button.flat, .umu-surface headerbar button { background-color: transparent; }
.umu-surface button.flat:hover, .umu-surface headerbar button:hover { background-color: alpha(#648596,.15); }
.umu-surface button:focus, .umu-surface button:focus-visible, .umu-surface .control-focused,
.umu-surface checkbutton:focus, .umu-surface checkbutton:focus-visible,
.umu-surface entry:focus-within, .umu-surface textview:focus-within {
  outline: 3px solid #267c6c; outline-offset: 2px; }
.umu-surface.umu-dark button:focus, .umu-surface.umu-dark button:focus-visible, .umu-surface.umu-dark .control-focused,
.umu-surface.umu-dark checkbutton:focus, .umu-surface.umu-dark checkbutton:focus-visible,
.umu-surface.umu-dark entry:focus-within, .umu-surface.umu-dark textview:focus-within { outline-color: #a6f5df; }
.umu-surface notebook.source-picker-tabs > header > tabs > tab:focus {
  outline: 3px solid #267c6c; outline-offset: 2px; }
.umu-surface.umu-dark notebook.source-picker-tabs > header > tabs > tab:focus {
  outline-color: #a6f5df; }
.umu-surface notebook.source-picker-tabs:focus {
  outline: 3px solid #267c6c; outline-offset: 2px; }
.umu-surface.umu-dark notebook.source-picker-tabs:focus {
  outline-color: #a6f5df; }
.umu-surface menubutton.control-focused > button:focus { outline: none; }
.umu-surface entry, .umu-surface textview, .umu-surface textview text,
.umu-surface list.boxed-list { background-color: #e7edf1; color: #172b36; }
.umu-surface.umu-dark entry, .umu-surface.umu-dark textview,
.umu-surface.umu-dark textview text, .umu-surface.umu-dark list.boxed-list {
  background-color: #192434; color: #edf3ff; }
.umu-surface .dim-label, .umu-surface .subtitle { color: #506373; opacity: 1; }
.umu-surface.umu-dark .dim-label, .umu-surface.umu-dark .subtitle { color: #acb9ce; }
.umu-surface .umu-footer button { min-width: 80px; padding: 8px 16px; font-weight: 700; }
.umu-surface.umu-tv { font-size: 18px; }
.umu-surface.umu-tv button { min-height: 38px; }
.umu-surface.umu-tv .umu-body { padding: 28px; }
.umu-surface.umu-tv .umu-footer button { min-width: 100px; }

/* AdwMessageDialog supplies bounded wrapping and responsive response layout. */
messagedialog.umu-surface .heading { font-size: 22px; font-weight: 800; }
messagedialog.umu-surface.umu-tv .heading { font-size: 28px; }
messagedialog.umu-surface .response-area button { padding: 10px 16px; }

/* Popovers remain menus, with the same surface and focus vocabulary. */
popover.umu-surface { background: transparent; }
popover.umu-surface > contents { background: #f3f6f8; color: #172b36;
  border: 1px solid alpha(#29465b,.16); border-radius: 14px; padding: 4px; }
popover.umu-surface.umu-dark > contents { background: #101b29; color: #edf3ff;
  border-color: alpha(#b4c7e5,.18); }
popover.umu-surface > arrow { background: #f3f6f8; }
popover.umu-surface.umu-dark > arrow { background: #101b29; }
popover.umu-surface button { padding: 8px 12px; }
popover.umu-surface button.suggested-action { background: #ceeae3; color: #155448; }
popover.umu-surface.umu-dark button.suggested-action { background: #243d44; color: #85efd4; }
'''


def _fullscreen(widget):
    """Inherit mode across transient owners, including nested confirmations."""
    seen = set()
    while widget is not None and id(widget) not in seen:
        seen.add(id(widget))
        if getattr(widget, 'tv_mode', False) or widget.has_css_class('umu-tv'):
            return True
        widget = widget.get_transient_for() if isinstance(widget, Gtk.Window) else widget.get_root()
    return False


def _sync_palette(surface, *_):
    fullscreen = _fullscreen(surface.get_transient_for() if isinstance(surface, Gtk.Window) else surface.get_root())
    dark = fullscreen or Adw.StyleManager.get_default().get_dark()
    for name, enabled in (('umu-dark', dark), ('umu-tv', fullscreen)):
        (surface.add_css_class if enabled else surface.remove_css_class)(name)


def _stop_palette(surface, state):
    handler = state.pop('handler', None)
    manager = Adw.StyleManager.get_default()
    if handler is not None and manager.handler_is_connected(handler):
        manager.disconnect(handler)


def _watch_palette(surface, state):
    _sync_palette(surface)
    if 'handler' in state:
        return
    # A native weak reference remains valid when GTK owns the widget but its
    # temporary Python wrapper has been collected. It never owns the widget.
    receiver = surface.weak_ref()

    def theme_changed(*_):
        target = receiver()
        if target is not None:
            _sync_palette(target)

    state['handler'] = Adw.StyleManager.get_default().connect('notify::dark', theme_changed)


def style_surface(surface, parent=None):
    """Apply once; follow live theme changes without keeping closed windows alive."""
    if surface.has_css_class('umu-surface'):
        return surface
    surface.add_css_class('umu-surface')
    if parent is not None and isinstance(surface, Gtk.Window):
        surface.set_transient_for(parent)
        surface.set_destroy_with_parent(True)
    # connect_object retains the receiver in this PyGObject environment. Watch
    # only while mapped and explicitly detach before disposal; finalization can
    # be delayed by native/Python window cycles. Signal data contains no widget.
    state = {}
    surface.connect('map', _watch_palette, state)
    surface.connect('unmap', _stop_palette, state)
    surface.connect('unrealize', _stop_palette, state)
    _sync_palette(surface)
    if surface.get_mapped():
        _watch_palette(surface, state)
    return surface


def message_dialog(parent, title, body='', *, responses=(('ok', 'OK'),),
                   default='ok', close='ok', suggested=None, destructive=None):
    """Create, but do not present or bind actions to, a native response dialog."""
    lengthy = len(body) > 400 or body.count('\n') > 6
    dialog = Adw.MessageDialog.new(parent, title, '' if lengthy else body)
    style_surface(dialog, parent)
    if lengthy:
        # AdwMessageDialog's ordinary body can exceed a short parent. Keep full
        # text in a public extra-child scroll area, leaving responses outside it.
        text = Gtk.Label(label=body, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR,
                         xalign=0, valign=Gtk.Align.START, max_width_chars=44)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                   min_content_width=260,
                                   overlay_scrolling=False,
                                   propagate_natural_height=True,
                                   max_content_height=min(280, max(96, (parent.get_height() or 600) - 260)))
        scroll.set_focusable(True)
        scroll.update_property([Gtk.AccessibleProperty.LABEL], ['Message details'])
        scroll.set_child(text)
        dialog.set_extra_child(scroll)
        # Existing fullscreen PageUp/PageDown controller handling supports this
        # same read-only information-scroll contract as Game Info.
        dialog.info_scroll = scroll
    for response, caption in responses:
        dialog.add_response(response, caption)
    dialog.set_default_response(default)
    dialog.set_close_response(close)
    if suggested:
        dialog.set_response_appearance(suggested, Adw.ResponseAppearance.SUGGESTED)
    if destructive:
        dialog.set_response_appearance(destructive, Adw.ResponseAppearance.DESTRUCTIVE)
    return dialog


def _close_on_escape(controller, key, *_):
    owner = controller.get_widget()
    if key == Gdk.KEY_Escape and owner is not None:
        owner.close()
        return True
    return False


def modal_window(parent, title, *, width=640, height=560, subtitle=''):
    """Shared native header. Window title stays in sync with progress updates."""
    # Keep Gtk.Window content semantics used by the editor and existing tests.
    if parent.get_width() > 0:
        width = min(width, max(320, parent.get_width() - 48))
    if parent.get_height() > 0:
        height = min(height, max(240, parent.get_height() - 48))
    dialog = Gtk.Window(title=title, modal=True, default_width=width, default_height=height)
    style_surface(dialog, parent)
    header = Adw.HeaderBar()
    heading = Adw.WindowTitle(title=title, subtitle=subtitle)
    dialog.bind_property('title', heading, 'title', GObject.BindingFlags.SYNC_CREATE)
    header.set_title_widget(heading)
    dialog.set_titlebar(header)
    keys = Gtk.EventControllerKey()
    keys.connect('key-pressed', _close_on_escape)
    dialog.add_controller(keys)
    return dialog


def dialog_body(dialog):
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
    content.add_css_class('umu-body')
    dialog.set_child(content)
    return content


def dialog_footer():
    footer = Gtk.Box(spacing=12, halign=Gtk.Align.FILL)
    footer.add_css_class('umu-footer')
    # An expanding spacer aligns actions while the separator spans the body.
    footer.append(Gtk.Box(hexpand=True))
    return footer
