import unittest
from steam_library.game import Game


class GameTests(unittest.TestCase):
    def test_new_entries_have_unique_local_identity(self):
        self.assertNotEqual(Game('Example', '/games/a.exe').id,
                            Game('Example', '/games/a.exe').id)

    def test_metadata_match_does_not_replace_shortcut_identity(self):
        game = Game('Example', '/games/a.exe', shortcut_id=123)
        game.set_metadata_source(456)
        self.assertEqual(game.shortcut_id, 123)
        self.assertEqual(game.metadata_app_id, 456)

    def test_relink_retains_game_and_shortcut_identity(self):
        game = Game('Example', '/games/a.exe', shortcut_id=123)
        identity = game.id
        game.relink('/new/location/a.exe')
        self.assertEqual(game.id, identity)
        self.assertEqual(game.shortcut_id, 123)
        self.assertEqual(game.executable, '/new/location/a.exe')

    def test_invalid_metadata_id_rejected(self):
        for value in (0, -1, True, '123'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Game('Example', '/games/a.exe').set_metadata_source(value)

    def test_empty_relink_rejected_without_changing_path(self):
        game = Game('Example', '/games/a.exe')
        with self.assertRaises(ValueError):
            game.relink(' ')
        self.assertEqual(game.executable, '/games/a.exe')
