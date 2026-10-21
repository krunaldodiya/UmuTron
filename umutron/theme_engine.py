"""Unified Theme Engine and Semantic Design Token Architecture for UmuTron."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, Gtk

BUNDLED_THEMES: dict[str, dict[str, Any]] = {
    'steamos-dark': {
        'id': 'steamos-dark',
        'name': 'SteamOS Dark',
        'dark': True,
        'description': 'Classic Steam Deck deep navy and cyan theme.',
        'tokens': {
            '--umu-bg-base': '#0b101a',
            '--umu-bg-surface': '#141d2b',
            '--umu-bg-elevated': '#1e2c3f',
            '--umu-bg-hover': '#26374e',
            '--umu-fg-primary': '#edf3ff',
            '--umu-fg-secondary': '#acb9ce',
            '--umu-fg-muted': '#687a94',
            '--umu-accent': '#85efd4',
            '--umu-accent-fg': '#0e2621',
            '--umu-accent-hover': '#a6f5df',
            '--umu-ready': '#58c9a8',
            '--umu-warning': '#f0b74d',
            '--umu-warning-fg': '#1c1508',
            '--umu-destructive': '#e05260',
            '--umu-destructive-fg': '#ffffff',
            '--umu-border': 'rgba(180, 199, 229, 0.12)',
            '--umu-border-subtle': 'rgba(180, 199, 229, 0.06)',
        },
    },
    'oled-midnight': {
        'id': 'oled-midnight',
        'name': 'OLED Midnight',
        'dark': True,
        'description': 'True pitch-black canvas with high-contrast emerald accents for OLED displays.',
        'tokens': {
            '--umu-bg-base': '#000000',
            '--umu-bg-surface': '#0e0e11',
            '--umu-bg-elevated': '#18181c',
            '--umu-bg-hover': '#24242a',
            '--umu-fg-primary': '#f3f4f6',
            '--umu-fg-secondary': '#9ca3af',
            '--umu-fg-muted': '#6b7280',
            '--umu-accent': '#34d399',
            '--umu-accent-fg': '#062419',
            '--umu-accent-hover': '#6ee7b7',
            '--umu-ready': '#10b981',
            '--umu-warning': '#fbbf24',
            '--umu-warning-fg': '#1c1508',
            '--umu-destructive': '#f87171',
            '--umu-destructive-fg': '#ffffff',
            '--umu-border': 'rgba(255, 255, 255, 0.14)',
            '--umu-border-subtle': 'rgba(255, 255, 255, 0.07)',
        },
    },
    'nord-frost': {
        'id': 'nord-frost',
        'name': 'Nord Frost',
        'dark': True,
        'description': 'Arctic, north-bluish clean color palette.',
        'tokens': {
            '--umu-bg-base': '#242933',
            '--umu-bg-surface': '#2e3440',
            '--umu-bg-elevated': '#3b4252',
            '--umu-bg-hover': '#434c5e',
            '--umu-fg-primary': '#eceff4',
            '--umu-fg-secondary': '#d8dee9',
            '--umu-fg-muted': '#4c566a',
            '--umu-accent': '#88c0d0',
            '--umu-accent-fg': '#1c2b30',
            '--umu-accent-hover': '#8fbcbb',
            '--umu-ready': '#a3be8c',
            '--umu-warning': '#ebcb8b',
            '--umu-warning-fg': '#242010',
            '--umu-destructive': '#bf616a',
            '--umu-destructive-fg': '#ffffff',
            '--umu-border': 'rgba(216, 222, 233, 0.12)',
            '--umu-border-subtle': 'rgba(216, 222, 233, 0.06)',
        },
    },
    'clean-slate-light': {
        'id': 'clean-slate-light',
        'name': 'Clean Slate Light',
        'dark': False,
        'description': 'Crisp daylight theme with cool slate tones for bright environments.',
        'tokens': {
            '--umu-bg-base': '#f0f4f8',
            '--umu-bg-surface': '#ffffff',
            '--umu-bg-elevated': '#e2e8f0',
            '--umu-bg-hover': '#cbd5e1',
            '--umu-fg-primary': '#0f172a',
            '--umu-fg-secondary': '#475569',
            '--umu-fg-muted': '#94a3b8',
            '--umu-accent': '#0284c7',
            '--umu-accent-fg': '#ffffff',
            '--umu-accent-hover': '#38bdf8',
            '--umu-ready': '#10b981',
            '--umu-warning': '#d97706',
            '--umu-warning-fg': '#ffffff',
            '--umu-destructive': '#ef4444',
            '--umu-destructive-fg': '#ffffff',
            '--umu-border': 'rgba(15, 23, 42, 0.12)',
            '--umu-border-subtle': 'rgba(15, 23, 42, 0.06)',
        },
    },
}

BASE_STYLESHEET = """
/* =========================================================================
   UmuTron Universal Design Token Stylesheet
   ========================================================================= */

/* Main Canvas & Surface Hierarchy */
window.desktop-mode, .umu-surface, .home-surface {
  background-color: var(--umu-bg-base);
  color: var(--umu-fg-primary);
}

headerbar.desktop-header, .umu-surface headerbar {
  background-color: var(--umu-bg-surface);
  color: var(--umu-fg-primary);
  box-shadow: inset 0 -1px var(--umu-border);
}

.umu-surface .umu-body {
  padding: 24px;
  background-color: var(--umu-bg-surface);
}

.umu-surface .umu-footer {
  padding-top: 16px;
  border-top: 1px solid var(--umu-border);
}

/* Base Buttons & Interactive Controls */
button {
  border-radius: 8px;
  min-height: 28px;
  background-image: none;
  background-color: var(--umu-bg-elevated);
  color: var(--umu-fg-primary);
  border: 1px solid transparent;
}

button:hover {
  background-color: var(--umu-bg-hover);
}

button.suggested-action, .detail-primary.suggested-action {
  background-color: var(--umu-accent);
  color: var(--umu-accent-fg);
  font-weight: 800;
}

button.suggested-action:hover, .detail-primary.suggested-action:hover {
  background-color: var(--umu-accent-hover);
}

button.destructive-action, .detail-primary.destructive-action {
  background-color: var(--umu-destructive);
  color: var(--umu-destructive-fg);
  font-weight: 600;
}

button.destructive-action:hover, .detail-primary.destructive-action:hover {
  filter: brightness(1.15);
}

button.warning-action {
  background-color: var(--umu-warning);
  color: var(--umu-warning-fg);
  font-weight: 600;
}

button.warning-action:hover {
  filter: brightness(1.12);
}

button:disabled {
  opacity: 0.45;
}

button.flat, headerbar button {
  background-color: transparent;
  border-color: transparent;
}

button.flat:hover, headerbar button:hover {
  background-color: var(--umu-border-subtle);
}

/* Focus Rings (No Double Borders on Cards) */
.control-focused, button:focus-visible {
  outline: 3px solid var(--umu-accent);
  outline-offset: 2px;
}

.collection-card, .collection-card:focus, .collection-card.control-focused,
.tv-card, .tv-card:focus, .tv-card.control-focused {
  outline: none;
  outline-offset: 0;
}

/* Cards (Desktop & TV Mode) */
.collection-card, .tv-card {
  padding: 7px;
  border-radius: 12px;
  background: var(--umu-bg-surface);
  border: 2px solid transparent;
}

.collection-card:hover, .tv-card:hover {
  background: var(--umu-bg-elevated);
  border-color: var(--umu-border-subtle);
}

.collection-card.game-ready, .tv-card.game-ready {
  border: 2px solid transparent;
}

.collection-card.game-ready:hover, .collection-card.game-ready:focus,
.tv-card.game-ready:hover, .tv-card.game-ready:focus, .tv-card.game-ready.selected-game {
  border-color: var(--umu-accent);
  outline: none;
}

.collection-card.game-not-ready, .tv-card.game-not-ready {
  border: 2px solid transparent;
}

.collection-card.game-not-ready:hover, .collection-card.game-not-ready:focus,
.tv-card.game-not-ready:hover, .tv-card.game-not-ready:focus, .tv-card.game-not-ready.selected-game {
  border-color: var(--umu-warning);
  outline: none;
}

/* Navigation Pills & Active States */
.desktop-mode .desktop-nav {
  border-radius: 10px;
  padding: 6px 16px;
}

.desktop-mode .desktop-nav.suggested-action, .tv-mode .tv-tab-active {
  background-color: var(--umu-accent);
  color: var(--umu-accent-fg);
  font-weight: 700;
}

/* Detail Surface Panels */
.shared-detail, .tv-detail-panel {
  padding: 28px;
  border-radius: 20px;
  background: var(--umu-bg-surface);
  border: 1px solid var(--umu-border);
}

.detail-title, .tv-title {
  color: var(--umu-fg-primary);
  font-size: 34px;
  font-weight: 800;
}

.detail-copy, .tv-description {
  color: var(--umu-fg-primary);
  font-size: 17px;
  line-height: 1.45;
}

.detail-meta, .tv-meta, .dim-label {
  color: var(--umu-fg-secondary);
}

/* Entries and Inputs */
entry, textview {
  background-color: var(--umu-bg-elevated);
  color: var(--umu-fg-primary);
  border: 1px solid var(--umu-border);
  border-radius: 8px;
  padding: 6px 10px;
}

entry:focus-within, textview:focus-within {
  border-color: var(--umu-accent);
  outline: 2px solid var(--umu-accent);
}

/* TV Mode Rail & Section Headings */
.tv-mode .tv-collection {
  background: var(--umu-bg-base);
  padding-top: 14px;
}

.tv-mode .tv-section-heading {
  color: var(--umu-fg-primary);
  font-size: 22px;
  font-weight: 700;
  margin: 0 48px 4px;
}

.tv-mode .tv-counter {
  color: var(--umu-fg-secondary);
  font-size: 15px;
  margin-right: 48px;
}

.tv-mode .tv-cover {
  background: var(--umu-bg-elevated);
  border-radius: 8px;
}

.tv-mode .tv-card-title, .collection-title {
  color: var(--umu-fg-primary);
  font-size: 16px;
  font-weight: 700;
}
.collection-badge {
  color: var(--umu-accent);
  font-size: 12px;
}

/* Popovers & Menus */
popover > contents {
  background-color: var(--umu-bg-surface);
  color: var(--umu-fg-primary);
  border: 1px solid var(--umu-border);
  border-radius: 14px;
  padding: 6px;
}
popover > arrow {
  background-color: var(--umu-bg-surface);
}
popover button.suggested-action {
  background-color: var(--umu-accent);
  color: var(--umu-accent-fg);
}

/* Dialogs & Lists */
messagedialog .heading {
  font-size: 22px;
  font-weight: 800;
}
messagedialog .response-area button {
  padding: 10px 16px;
}
list.boxed-list {
  background-color: var(--umu-bg-elevated);
  color: var(--umu-fg-primary);
}
notebook.source-picker-tabs > header > tabs > tab:focus,
notebook.source-picker-tabs:focus {
  outline: 3px solid var(--umu-accent);
  outline-offset: 2px;
}

/* Artwork Frame & Pager */
.art-frame {
  background: var(--umu-border-subtle);
  border-radius: 12px;
  padding: 8px;
}
.game-card {
  padding: 10px;
}
.game-card:hover {
  background: var(--umu-border-subtle);
}
.collection-pager .current-page {
  background: var(--umu-accent);
  color: var(--umu-accent-fg);
  opacity: 1;
}

/* TV Mode Compact & Large Responsive Scales */
.tv-mode.tv-compact button { min-height: 30px; padding: 8px 16px; }
.tv-mode.tv-compact .tv-play { min-width: 112px; }
.tv-mode.tv-compact .tv-title { font-size: 36px; }
.tv-mode.tv-compact .tv-description { font-size: 17px; }
.tv-mode.tv-compact .tv-section-heading { margin-left: 32px; font-size: 20px; }
.tv-mode.tv-compact .tv-card-title { font-size: 15px; }
.tv-mode.tv-compact .tv-detail-panel { padding: 22px; }

.scale-large { font-size: 21px; }
.tv-mode.scale-large button { min-height: 48px; padding: 12px 24px; font-size: 19px; border-radius: 14px; }
.scale-large .tv-title { font-size: 64px; }
.scale-large .tv-description { font-size: 23px; line-height: 1.45; }
.scale-large .tv-section-heading { font-size: 28px; margin: 0 54px 6px; }
.scale-large .tv-card { padding: 9px; border-radius: 14px; }
.scale-large .tv-card-title { font-size: 20px; }
.scale-large .tv-detail-panel { padding: 38px; border-radius: 24px; }

.scale-xlarge { font-size: 25px; }
.tv-mode.scale-xlarge button { min-height: 56px; padding: 14px 30px; font-size: 22px; border-radius: 16px; }
.scale-xlarge .tv-title { font-size: 78px; }
.scale-xlarge .tv-description { font-size: 27px; line-height: 1.45; }
.scale-xlarge .tv-section-heading { font-size: 34px; margin: 0 64px 8px; }
.scale-xlarge .tv-card { padding: 12px; border-radius: 16px; }
.scale-xlarge .tv-card-title { font-size: 24px; }
.scale-xlarge .tv-detail-panel { padding: 48px; border-radius: 28px; }

/* Scrim and Detail Backdrop */
.desktop-mode .detail-surface {
  background: var(--umu-bg-base);
  color: var(--umu-fg-primary);
}
.desktop-mode .detail-scrim {
  background: linear-gradient(90deg, var(--umu-bg-base) 0%, rgba(0,0,0,0.85) 25%, rgba(0,0,0,0.12) 78%),
              linear-gradient(0deg, var(--umu-bg-base) 0%, rgba(0,0,0,0.04) 65%, rgba(0,0,0,0.30) 100%);
}
"""


class ThemeEngine:
    def __init__(self, custom_themes_dir: Path | str | None = None):
        self.custom_dir = Path(custom_themes_dir or (Path.home() / '.config' / 'umutron' / 'themes')).expanduser().resolve()
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        self.provider = Gtk.CssProvider()
        self._provider_installed = False
        self.active_theme_id: str = 'steamos-dark'
        self._init_custom_template()

    def _init_custom_template(self):
        """Create a sample custom theme template with documentation if none exists."""
        template_dir = self.custom_dir / 'custom-template'
        if not template_dir.exists():
            try:
                template_dir.mkdir(parents=True, exist_ok=True)
                sample_json = {
                    'id': 'custom-template',
                    'name': 'Custom Template (Sample)',
                    'author': 'Your Name',
                    'dark': True,
                    'description': 'Customize these tokens or add CSS rules in style.css.',
                    'tokens': {
                        '--umu-bg-base': '#12141a',
                        '--umu-bg-surface': '#1b1e26',
                        '--umu-bg-elevated': '#252934',
                        '--umu-bg-hover': '#2f3542',
                        '--umu-fg-primary': '#f1f2f6',
                        '--umu-fg-secondary': '#a4b0be',
                        '--umu-fg-muted': '#747d8c',
                        '--umu-accent': '#70a1ff',
                        '--umu-accent-fg': '#0c1a30',
                        '--umu-accent-hover': '#90b7ff',
                        '--umu-ready': '#2ed573',
                        '--umu-warning': '#ffa502',
                        '--umu-warning-fg': '#1c1508',
                        '--umu-destructive': '#ff4757',
                        '--umu-destructive-fg': '#ffffff',
                        '--umu-border': 'rgba(255, 255, 255, 0.12)',
                        '--umu-border-subtle': 'rgba(255, 255, 255, 0.06)',
                    },
                }
                (template_dir / 'theme.json').write_text(json.dumps(sample_json, indent=2))
                (template_dir / 'style.css').write_text("/* Add extra custom GTK CSS rules here */\n")
                readme = """# Custom Themes for UmuTron

Create a subfolder here (e.g. `cyberpunk/`) with a `theme.json` file.
You can override palette variables and optionally add custom CSS in `style.css`.
"""
                (self.custom_dir / 'README.md').write_text(readme)
            except OSError:
                pass

    def list_themes(self) -> list[dict[str, Any]]:
        """Return all available themes (bundled + valid user themes)."""
        themes = list(BUNDLED_THEMES.values())
        if self.custom_dir.is_dir():
            for folder in sorted(self.custom_dir.iterdir()):
                if folder.is_dir() and (folder / 'theme.json').is_file():
                    try:
                        data = json.loads((folder / 'theme.json').read_text())
                        if isinstance(data, dict) and data.get('name'):
                            theme_id = data.get('id') or folder.name
                            if not any(t['id'] == theme_id for t in themes):
                                data['id'] = theme_id
                                data['custom_path'] = str(folder)
                                themes.append(data)
                    except (OSError, json.JSONDecodeError):
                        pass
        return themes

    def get_theme(self, theme_id: str) -> dict[str, Any]:
        """Resolve theme definition by id, falling back to steamos-dark."""
        for t in self.list_themes():
            if t['id'] == theme_id:
                return t
        return BUNDLED_THEMES['steamos-dark']

    def generate_css(self, theme: dict[str, Any]) -> str:
        """Construct full GTK4 CSS from theme tokens and custom stylesheet."""
        tokens = dict(BUNDLED_THEMES['steamos-dark']['tokens'])
        tokens.update(theme.get('tokens', {}))
        
        token_lines = [f"  {k}: {v};" for k, v in tokens.items()]
        root_block = ":root {\n" + "\n".join(token_lines) + "\n}\n"
        
        css = root_block + BASE_STYLESHEET
        
        # If user custom theme provides extra style.css, append it
        if theme.get('custom_path'):
            custom_style = Path(theme['custom_path']) / 'style.css'
            if custom_style.is_file():
                try:
                    css += "\n/* User Custom Overrides */\n" + custom_style.read_text()
                except OSError:
                    pass
        return css

    def apply_theme(self, theme_id: str):
        """Compile and inject theme CSS into display-level GTK StyleContext."""
        theme = self.get_theme(theme_id)
        self.active_theme_id = theme['id']
        
        # Apply dark/light scheme for libadwaita
        is_dark = theme.get('dark', True)
        Adw.StyleManager.get_default().set_color_scheme(
            Adw.ColorScheme.FORCE_DARK if is_dark else Adw.ColorScheme.FORCE_LIGHT
        )
        
        css_content = self.generate_css(theme)
        self.provider.load_from_data(css_content.encode('utf-8'))
        
        if not self._provider_installed:
            display = Gdk.Display.get_default()
            if display:
                Gtk.StyleContext.add_provider_for_display(
                    display, self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
                self._provider_installed = True
        return theme
