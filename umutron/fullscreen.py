"""Native fullscreen presentation helpers; no persistence or launch behavior."""
from functools import lru_cache
from pathlib import Path

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk


CSS = b'''
.tv-mode { background: #0b101a; color: #f3f6ff; font-size: 18px; }
.tv-mode button { min-height: 40px; padding: 10px 20px; border-radius: 12px; font-weight: 600; }
.tv-mode .tv-controls { margin: 0; padding: 20px 40px; background: alpha(#0b101a, .72); }
.tv-mode .tv-controls button { min-height: 32px; padding: 8px 18px; }
.tv-mode .tv-brand { font-size: 23px; font-weight: 800; margin-right: 34px; }
.tv-mode .tv-clock { font-size: 18px; color: #c6cfdf; margin-left: 16px; }
.tv-mode .tv-tab-active { color: #85efd4; background: alpha(#85efd4, .10); }
.tv-mode .tv-scrim { background: linear-gradient(90deg, #0b101a 0%, alpha(#0b101a,.90) 25%, alpha(#0b101a,.12) 78%), linear-gradient(0deg, #0b101a 0%, alpha(#0b101a,.04) 65%, alpha(#0b101a,.30) 100%); }
.tv-mode .tv-summary { margin: 24px 48px; }
.tv-mode .tv-title { font-size: 52px; font-weight: 800; letter-spacing: -1px; line-height: 1.06; }
.tv-mode .tv-eyebrow { color: #85efd4; font-size: 14px; font-weight: 700; letter-spacing: 2px; }
.tv-mode .tv-description { color: #d5ddea; font-size: 20px; line-height: 1.4; }
.tv-mode .tv-meta { color: #acb9ce; font-size: 17px; }
.tv-mode .tv-play { min-width: 140px; min-height: 40px; background: #85efd4; color: #092b2c; font-weight: 800; }
.tv-mode .tv-play:disabled { background: #33464a; color: #9aabaa; }
.tv-mode .tv-play.destructive-action { background: #f8aaad; color: #451316; }
.tv-mode .tv-collection { background: alpha(#0b101a,.88); padding-top: 14px; }
.tv-mode .tv-section-heading { font-size: 22px; font-weight: 700; margin: 0 48px 4px; }
.tv-mode .tv-counter { color: #acb9ce; font-size: 15px; margin-right: 48px; }
.tv-mode .tv-card { padding: 7px; border: 1px solid alpha(#b4c7e5,.09); background: #141d2b; border-radius: 12px; }
.tv-mode .tv-card:hover { background: #223349; }
.tv-mode .tv-card.selected-game { border-color: #85efd4; background: #243d44; }
.tv-mode .tv-card-title { font-size: 17px; font-weight: 600; line-height: 1.2; color: #edf3ff; }
.tv-mode .tv-cover { background: #202b3c; border-radius: 7px; }
.tv-mode .tv-cover-missing { color: #7b91ae; font-size: 12px; }
.tv-mode .home-setups { padding: 32px 48px 48px; background: #0b101a; }
.tv-mode .home-setups .tv-section-heading { margin: 0; }
.tv-mode .home-setup-state { font-size: 14px; color: #acb9ce; min-height: 34px; }
.tv-mode .home-setups flowboxchild { padding: 6px; }
.tv-mode .tv-hints { font-size: 14px; color: #aab9cf; margin: 10px 40px 14px; }
.tv-mode .tv-detail-panel { background: alpha(#0d1523,.86); border: 1px solid alpha(#b4c7e5,.10); border-radius: 20px; padding: 30px; }
.tv-mode .tv-detail-panel .tv-title { font-size: 46px; }
.tv-mode .tv-detail-content { margin: 20px 48px 28px; }
.tv-mode .tv-detail-logo { margin-bottom: 10px; }
.tv-mode .tv-secondary { background: alpha(#becde4,.10); }
.tv-mode .control-focused, .tv-mode button:focus-visible { outline: 3px solid #b3ffe9; outline-offset: 3px; box-shadow: 0 0 0 6px alpha(#0b101a,.72); }
.tv-mode.tv-compact button { min-height: 30px; padding: 8px 16px; }
.tv-mode.tv-compact .tv-play { min-width: 112px; }
.tv-mode.tv-compact .tv-controls { padding: 12px 28px; }
.tv-mode.tv-compact .tv-brand { margin-right: 18px; font-size: 20px; }
.tv-mode.tv-compact .tv-title { font-size: 36px; }
.tv-mode.tv-compact .tv-summary { margin: 12px 32px; }
.tv-mode.tv-compact .tv-description { font-size: 17px; }
.tv-mode.tv-compact .tv-section-heading { margin-left: 32px; font-size: 20px; }
.tv-mode.tv-compact .tv-card-title { font-size: 15px; }
.tv-mode.tv-compact .tv-detail-content { margin: 12px 32px 20px; }
.tv-mode.tv-compact .tv-detail-panel { padding: 22px; }
.tv-mode.tv-compact .tv-detail-panel .tv-title { font-size: 34px; }
.tv-mode.tv-compact .home-setups { padding: 24px 32px 36px; }
.tv-mode.tv-compact .home-setup-state { font-size: 13px; }
.tv-mode.tv-compact .tv-hints { margin: 8px 28px 10px; font-size: 13px; }

.scale-large { font-size: 21px; }
.tv-mode.scale-large button { min-height: 48px; padding: 12px 24px; font-size: 19px; border-radius: 14px; }
.scale-large .tv-controls { padding: 24px 50px; }
.scale-large .tv-controls button { min-height: 42px; padding: 10px 22px; font-size: 19px; }
.scale-large .tv-brand { font-size: 28px; margin-right: 40px; }
.scale-large .tv-clock { font-size: 21px; }
.scale-large .tv-title { font-size: 64px; }
.scale-large .tv-eyebrow { font-size: 17px; }
.scale-large .tv-description { font-size: 23px; line-height: 1.45; }
.scale-large .tv-meta { font-size: 19px; }
.scale-large .tv-play { min-width: 170px; min-height: 48px; font-size: 20px; }
.scale-large .tv-secondary { font-size: 19px; }
.scale-large .tv-section-heading { font-size: 28px; margin: 0 54px 6px; }
.scale-large .tv-counter { font-size: 18px; margin-right: 54px; }
.scale-large .tv-card { padding: 9px; border-radius: 14px; }
.scale-large .tv-card-title { font-size: 20px; }
.scale-large .tv-detail-panel { padding: 38px; border-radius: 24px; }
.scale-large .tv-detail-panel .tv-title { font-size: 56px; }
.scale-large .tv-hints { font-size: 17px; margin: 14px 48px 18px; }

.scale-xlarge { font-size: 25px; }
.tv-mode.scale-xlarge button { min-height: 56px; padding: 14px 30px; font-size: 22px; border-radius: 16px; }
.scale-xlarge .tv-controls { padding: 30px 64px; }
.scale-xlarge .tv-controls button { min-height: 48px; padding: 12px 26px; font-size: 22px; }
.scale-xlarge .tv-brand { font-size: 34px; margin-right: 48px; }
.scale-xlarge .tv-clock { font-size: 25px; }
.scale-xlarge .tv-title { font-size: 78px; }
.scale-xlarge .tv-eyebrow { font-size: 20px; }
.scale-xlarge .tv-description { font-size: 27px; line-height: 1.45; }
.scale-xlarge .tv-meta { font-size: 23px; }
.scale-xlarge .tv-play { min-width: 210px; min-height: 56px; font-size: 24px; }
.scale-xlarge .tv-secondary { font-size: 22px; }
.scale-xlarge .tv-section-heading { font-size: 34px; margin: 0 64px 8px; }
.scale-xlarge .tv-counter { font-size: 22px; margin-right: 64px; }
.scale-xlarge .tv-card { padding: 12px; border-radius: 16px; }
.scale-xlarge .tv-card-title { font-size: 24px; }
.scale-xlarge .tv-detail-panel { padding: 48px; border-radius: 28px; }
.scale-xlarge .tv-detail-panel .tv-title { font-size: 68px; }
.scale-xlarge .tv-hints { font-size: 20px; margin: 18px 56px 24px; }
'''


# Home shares its cinematic composition in desktop and fullscreen modes.
# Compact state lives on the window; the Home surface is its descendant.
# Keep the original fullscreen rules intact and scope this adaptation to desktop.
CSS += CSS.replace(b'.tv-mode.tv-compact', b'.desktop-mode.tv-compact .home-surface').replace(b'.tv-mode', b'.home-surface')


@lru_cache(maxsize=24)
def _texture(path, modified, width, height, trim):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, width, height, True)
    if trim and pixbuf.get_has_alpha():
        # Provider logos may include large transparent canvases. Fit visible ink.
        pixels = pixbuf.get_pixels()
        stride, channels = pixbuf.get_rowstride(), pixbuf.get_n_channels()
        points = [(x, y) for y in range(pixbuf.get_height()) for x in range(pixbuf.get_width())
                  if pixels[y * stride + x * channels + channels - 1] > 16]
        if points:
            xs, ys = zip(*points)
            pixbuf = pixbuf.new_subpixbuf(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)
    return Gdk.Texture.new_for_pixbuf(pixbuf)


def set_art(picture, path, width=1920, height=1080, trim=False):
    """Clear stale art on missing/corrupt files and bound decoded image memory."""
    try:
        path = Path(path) if path else None
        texture = _texture(str(path), path.stat().st_mtime_ns, width, height, trim) if path else None
    except (OSError, GLib.Error):
        texture = None
    picture.set_paintable(texture)
    return texture is not None


class CoverLayout(Gtk.LayoutManager):
    """Keep rail and grid cards independent of their title's natural width."""

    def do_get_request_mode(self, widget):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, widget, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return widget.console_width, widget.console_width, -1, -1
        return widget.get_child().measure(orientation, widget.console_width)

    def do_allocate(self, widget, width, height, baseline):
        widget.get_child().allocate(width, height, baseline, None)


class CoverPicture(Gtk.Picture):
    """Artwork fills the fixed cover slot without imposing its source dimensions."""

    def do_measure(self, orientation, for_size):
        return 0, 0, -1, -1


def cover(path, width, height):
    frame = Gtk.Box()
    frame.add_css_class('tv-cover')
    frame.set_hexpand(False)
    frame.set_vexpand(False)
    frame.set_size_request(width, height)
    frame.set_overflow(Gtk.Overflow.HIDDEN)
    picture = CoverPicture(content_fit=Gtk.ContentFit.COVER, can_shrink=True, hexpand=True, vexpand=True)
    if set_art(picture, path, 480, 720):
        frame.append(picture)
    else:
        fallback = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, hexpand=True, vexpand=True)
        fallback.append(Gtk.Image(icon_name='applications-games-symbolic', pixel_size=40))
        caption = Gtk.Label(label='No cover art', wrap=True, justify=Gtk.Justification.CENTER)
        caption.set_max_width_chars(8)
        fallback.append(caption)
        fallback.add_css_class('tv-cover-missing')
        frame.append(fallback)
    return frame
