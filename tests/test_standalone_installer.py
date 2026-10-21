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

    @patch('shutil.which', return_value='/usr/bin/wine')
    def test_pick_and_run_global_installer_success(self, mock_which):
        window = Window(self.app, self.library, demo=True)
        try:
            exe_file = self.root / 'setup.exe'
            exe_file.write_bytes(b'MZfake')
            with patch('subprocess.Popen') as mock_popen:
                # Mock choose_file to immediately invoke callback with exe_file
                with patch.object(window, 'choose_file', side_effect=lambda title, cb, **kw: cb(str(exe_file))):
                    with patch.object(window, 'notify') as mock_notify:
                        window.pick_and_run_global_installer()
                        mock_popen.assert_called_once()
                        cmd = mock_popen.call_args[0][0]
                        self.assertEqual(cmd[0], '/usr/bin/wine')
                        self.assertEqual(cmd[1], str(exe_file))
                        mock_notify.assert_called_once()
                        self.assertIn('Launched setup.exe with system Wine', mock_notify.call_args[0][0])
        finally:
            window.pool.shutdown(wait=False)
            window.destroy()


if __name__ == '__main__':
    unittest.main()
