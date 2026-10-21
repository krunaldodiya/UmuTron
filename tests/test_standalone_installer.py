import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from umutron.app import Application, Window
from umutron.library import Library


class StandaloneInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / 'library.json').write_text('{"version": 1, "games": [], "settings": {}}')
        self.library = Library(self.root)
        self.app = Application(demo=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_pick_and_run_global_installer_with_proton(self):
        window = Window(self.app, self.library, demo=True)
        try:
            runner_dir = self.root / 'GE-Proton11-11-x86_64'
            runner_dir.mkdir()
            (runner_dir / 'proton').write_text('#!/bin/sh\n')
            window.proton_manager.installed = MagicMock(return_value=[str(runner_dir)])
            exe_file = self.root / 'setup.exe'
            exe_file.write_bytes(b'MZfake')
            with patch('shutil.which', side_effect=lambda name: '/usr/bin/umu-run' if name == 'umu-run' else '/usr/bin/wine'):
                with patch('subprocess.Popen') as mock_popen:
                    with patch.object(window, 'choose_file', side_effect=lambda title, cb, **kw: cb(str(exe_file))):
                        with patch.object(window, 'notify') as mock_notify:
                            window.pick_and_run_global_installer()
                            mock_popen.assert_called_once()
                            cmd = mock_popen.call_args[0][0]
                            self.assertEqual(cmd[0], '/usr/bin/umu-run')
                            self.assertEqual(cmd[1], str(exe_file))
                            mock_notify.assert_called_once()
                            self.assertIn('Launched setup.exe with Proton', mock_notify.call_args[0][0])
        finally:
            window.pool.shutdown(wait=False)
            window.destroy()


if __name__ == '__main__':
    unittest.main()
