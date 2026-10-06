import unittest

from game_library.download_service import build_search_queries, detail_actions
from game_library.sources.base import normalize_title
from game_library.sources.providers.fitgirl import FitGirlProvider


class FitGirlInstallTests(unittest.TestCase):
    def test_normalize_title_cleans_quotes_and_dashes(self):
        self.assertEqual(normalize_title("Baldur’s Gate: Dark Alliance"), "Baldur's Gate: Dark Alliance")
        self.assertEqual(normalize_title("The Witcher 3: Wild Hunt – Remastered"), "The Witcher 3: Wild Hunt - Remastered")
        self.assertEqual(normalize_title(""), "")

    def test_build_search_queries_generates_normalizations(self):
        queries = build_search_queries("Dark Souls: Remastered")
        self.assertIn("Dark Souls: Remastered", queries)
        self.assertIn("Dark Souls Remastered", queries)
        self.assertIn("Dark Souls", queries)

    def test_build_search_queries_roman_numerals(self):
        queries = build_search_queries("Grand Theft Auto V")
        self.assertIn("Grand Theft Auto V", queries)
        self.assertIn("Grand Theft Auto 5", queries)

    def test_search_fitgirl_repack_filters_patches_and_finds_full_game(self):
        def mock_transport(_url):
            return {
                "data": [
                    {
                        "id": "patch-1",
                        "title": "The Witcher 3: Wild Hunt - Patch from v1.21 to v1.22",
                        "file_size": "327 MB",
                        "uris": ["magnet:?xt=urn:btih:patch123"],
                    },
                    {
                        "id": "full-1",
                        "title": "The Witcher 3: Wild Hunt - Complete Edition",
                        "file_size": "35 GB",
                        "uris": ["magnet:?xt=urn:btih:full123"],
                    },
                ]
            }

        results = FitGirlProvider().search("https://mock-api.local", "The Witcher 3: Wild Hunt", transport=mock_transport)
        self.assertTrue(len(results) > 0)
        # Full release is preferred over patch
        self.assertEqual(results[0]["id"], "full-1")
        self.assertEqual(results[0]["magnet"], "magnet:?xt=urn:btih:full123")

    def test_detail_actions_play_if_installed_else_install(self):
        unconfigured = {}
        state = detail_actions(unconfigured, saved=True, fullscreen=False)
        self.assertEqual(state["primary"], "Install")

        configured = {"executable": "/game.exe"}
        state_configured = detail_actions(configured, saved=True, fullscreen=False, payload_exists=True)
        self.assertEqual(state_configured["primary"], "Play")

    def test_detail_actions_unsaved_shows_install(self):
        state = detail_actions({}, saved=False, fullscreen=False)
        self.assertEqual(state["primary"], "Install")


if __name__ == "__main__":
    unittest.main()
