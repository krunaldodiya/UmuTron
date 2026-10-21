import json
import tempfile
import unittest
from pathlib import Path

from umutron.theme_engine import BUNDLED_THEMES, ThemeEngine


class ThemeEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.custom_dir = Path(self.temp_dir.name)
        self.engine = ThemeEngine(custom_themes_dir=self.custom_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_bundled_themes_exist(self):
        themes = self.engine.list_themes()
        theme_ids = {t['id'] for t in themes}
        self.assertIn('steamos-dark', theme_ids)
        self.assertIn('oled-midnight', theme_ids)
        self.assertIn('nord-frost', theme_ids)
        self.assertIn('clean-slate-light', theme_ids)

    def test_get_theme_fallback(self):
        theme = self.engine.get_theme('non-existent-theme')
        self.assertEqual(theme['id'], 'steamos-dark')

    def test_generate_css(self):
        theme = self.engine.get_theme('oled-midnight')
        css = self.engine.generate_css(theme)
        self.assertIn('--umu-bg-base: #000000;', css)
        self.assertIn('--umu-accent: #34d399;', css)
        self.assertIn('window.desktop-mode', css)

    def test_custom_user_theme_discovery(self):
        user_theme_dir = self.custom_dir / 'my-cyberpunk'
        user_theme_dir.mkdir(parents=True)
        custom_data = {
            'id': 'my-cyberpunk',
            'name': 'Cyberpunk Neon',
            'dark': True,
            'tokens': {
                '--umu-bg-base': '#0d0221',
                '--umu-accent': '#00f0ff',
            },
        }
        (user_theme_dir / 'theme.json').write_text(json.dumps(custom_data))
        (user_theme_dir / 'style.css').write_text('.custom-badge { color: yellow; }\n')

        themes = self.engine.list_themes()
        theme_ids = {t['id'] for t in themes}
        self.assertIn('my-cyberpunk', theme_ids)

        cyber_theme = self.engine.get_theme('my-cyberpunk')
        css = self.engine.generate_css(cyber_theme)
        self.assertIn('--umu-bg-base: #0d0221;', css)
        self.assertIn('--umu-accent: #00f0ff;', css)
        self.assertIn('.custom-badge { color: yellow; }', css)


if __name__ == '__main__':
    unittest.main()
