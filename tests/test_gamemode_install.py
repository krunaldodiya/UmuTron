import unittest
from unittest.mock import patch
from umutron.gamemode_install import install_command, install_system_gamemode


class GameModeInstallTests(unittest.TestCase):
    def test_pacman_detected(self):
        with patch('shutil.which', side_effect=lambda bin: bin in ('pacman', 'pkexec')):
            self.assertEqual(install_command(), ['pkexec', 'pacman', '-S', '--noconfirm', '--needed', 'gamemode', 'lib32-gamemode'])

    def test_apt_detected(self):
        with patch('shutil.which', side_effect=lambda bin: bin in ('apt-get', 'pkexec')):
            self.assertEqual(install_command(), ['pkexec', 'apt-get', 'install', '-y', 'gamemode'])

    def test_dnf_detected(self):
        with patch('shutil.which', side_effect=lambda bin: bin in ('dnf', 'pkexec')):
            self.assertEqual(install_command(), ['pkexec', 'dnf', 'install', '-y', 'gamemode'])

    def test_missing_pkexec_raises(self):
        with patch('shutil.which', side_effect=lambda bin: False):
            with self.assertRaisesRegex(RuntimeError, 'PolicyKit'):
                install_system_gamemode()


if __name__ == '__main__':
    unittest.main()
