from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from game_library.library import Library
from game_library.proton_manager import ProtonManager
from game_library.runner_selection import INHERIT, effective_selector, global_selector, parse_release, release_selector


class RunnerSelectionTests(unittest.TestCase):
    def test_fresh_library_uses_umu_without_installing_ge_or_persisting_a_pin(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);library=Library(root/'library')
            before=deepcopy(library.data)
            self.assertFalse(library.path.exists())
            manager=ProtonManager(library.root/'proton-manager',umu_root=root/'umu',create=False)
            self.assertEqual(global_selector(library.root),'UMU-Latest')
            self.assertEqual(effective_selector(library.new_game(),global_selector(library.root)),'UMU-Latest')
            self.assertEqual(manager.installed(),[])
            self.assertFalse(manager.tools.exists())
            self.assertEqual(library.data,before)
            self.assertFalse(library.path.exists())

    def test_existing_explicit_default_survives_library_reopen(self):
        with tempfile.TemporaryDirectory() as temp:
            library=Library(Path(temp)/'library')
            for value in ('release:GE-Proton:GE-Proton11-7','release:UMU-Proton:UMU-Proton-10.0-4','/custom/UMU-Proton-10.0-4','GE-Latest'):
                library.set_default_proton(value);before=library.path.read_bytes()
                reopened=Library(library.root)
                self.assertEqual(global_selector(reopened.root),value)
                self.assertEqual(reopened.path.read_bytes(),before)

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
