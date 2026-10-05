from copy import deepcopy
import unittest

from game_library.download_service import InstallUnavailable, UnavailableInstallService, detail_actions


class DetailActionTests(unittest.TestCase):
    def test_unsaved_preview_shows_install_in_both_modes(self):
        for fullscreen in (False, True):
            state = detail_actions({'executable': '/irrelevant.exe'}, False, fullscreen, True)
            self.assertEqual(state['primary'], 'Play')
            self.assertFalse(any(state[k] for k in ('setup', 'remove', 'uninstall', 'resume_uninstall')))

    def test_saved_uninstalled_shows_install_in_both_modes(self):
        for fullscreen in (False, True):
            state = detail_actions({}, True, fullscreen)
            self.assertEqual(state['primary'], 'Install')
            self.assertFalse(state['setup'])
            self.assertTrue(state['remove']); self.assertFalse(state['uninstall'])

    def test_configured_game_keeps_play_but_uninstall_requires_present_payload(self):
        game = {'executable': '/game.exe'}
        for fullscreen in (False, True):
            for exists in (False, True):
                state = detail_actions(game, True, fullscreen, exists)
                self.assertEqual(state['primary'], 'Play')
                self.assertEqual(state['uninstall'], exists)
                self.assertEqual(state['setup'], not fullscreen)

    def test_unconfirmed_installer_is_not_a_completed_install(self):
        game = {'executable': '/game.exe', 'installation': {'mode': 'installer', 'confirmed': False}}
        self.assertEqual(detail_actions(game, True, False, True)['primary'], 'Install')
        self.assertFalse(detail_actions(game, True, False, True)['uninstall'])
        game['installation']['confirmed'] = True
        self.assertEqual(detail_actions(game, True, True, True)['primary'], 'Play')

    def test_interrupted_uninstall_remains_recoverable_when_payload_is_staged(self):
        state = detail_actions({'executable': '/staged-away.exe'}, True, True, False, True)
        self.assertFalse(state['uninstall']); self.assertTrue(state['resume_uninstall'])

    def test_unavailable_service_never_starts_or_fabricates_jobs(self):
        service = UnavailableInstallService(); request = {'game_id': 'fixture', 'destination': '/never-written'}
        before = deepcopy(request)
        self.assertFalse(service.availability('fixture', {'provider': 'igdb', 'id': 1})['available'])
        for operation, argument in ((service.start, request), (service.snapshot, 'missing'),
                                    (service.cancel, 'missing'), (service.resume, 'missing')):
            with self.assertRaises(InstallUnavailable): operation(argument)
        self.assertEqual(request, before)


if __name__ == '__main__':
    unittest.main()
