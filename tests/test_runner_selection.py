from copy import deepcopy
import unittest

from game_library.runner_selection import INHERIT, effective_selector, parse_release, release_selector


class RunnerSelectionTests(unittest.TestCase):
    def test_global_default_and_explicit_game_override(self):
        game = {'launch': {}, 'installation': {}}
        self.assertEqual(effective_selector(game, 'global'), 'global')
        game['launch']['proton'] = '/pinned/GE-Proton'
        self.assertEqual(effective_selector(game, 'global'), '/pinned/GE-Proton')
        game['launch']['proton'] = INHERIT
        self.assertEqual(effective_selector(game, 'global'), 'global')

    def test_legacy_installer_pin_is_preserved_until_deliberate_use_default(self):
        game = {'launch': {'proton': ''}, 'installation': {'proton': '/old/pinned'}}
        before = deepcopy(game)
        self.assertEqual(effective_selector(game, 'new-global'), '/old/pinned')
        self.assertEqual(game, before)
        game['launch']['proton'] = INHERIT
        self.assertEqual(effective_selector(game, 'new-global'), 'new-global')

    def test_legacy_automatic_policy_and_custom_spelling_are_not_rewritten(self):
        for value in ('UMU-Latest', 'GE-Latest', '/custom/runner-link'):
            game = {'launch': {'proton': value}}
            self.assertEqual(effective_selector(game, '/other'), value)
            self.assertEqual(game['launch']['proton'], value)

    def test_exact_release_selector_roundtrip_and_validation(self):
        release = {'family': 'GE-Proton', 'version': 'GE-Proton11-7'}
        selected = release_selector(release)
        self.assertEqual(parse_release(selected), ('GE-Proton', 'GE-Proton11-7'))
        self.assertIsNone(parse_release('/custom/Proton'))
        for value in ('release:Other:1', 'release:GE-Proton:../escape',
                      'release:UMU-Proton:', 'release:GE-Proton:.', 'release:GE-Proton:x/y'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_release(value)
