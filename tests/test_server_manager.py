import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from umutron.server_manager import (
    ServerEnvironment,
    ServerError,
    ServerManager,
)


def fake_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / 'app').mkdir()
    (root / 'docker-compose.yml').write_text('services: {}\n')
    (root / '.env.example').write_text(
        '# local server settings\nAPP_BASE_URL=http://127.0.0.1:8000\n'
        'INTERNAL_API_KEY=\nCATALOG_MODE=mock\nENABLE_LIVE_IGDB=0\n'
        'TWITCH_CLIENT_ID=\nTWITCH_CLIENT_SECRET=\n'
    )
    return root


class Runner:
    def __init__(self, fail: bool = False):
        self.calls = []
        self.fail = fail

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        return subprocess.CompletedProcess(command, 1 if self.fail else 0, '', 'boom' if self.fail else '')


class ServerManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = fake_repo(self.root / 'repo')
        self.manager = ServerManager(
            config_dir=self.root / 'config',
            clone_dir=self.root / 'clone',
            repo_dir=self.repo,
            runner=Runner(),
            health_transport=lambda url, timeout: True,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_environment_round_trip_permissions_and_catalog(self):
        original = self.manager.read_environment()
        self.assertEqual(original.internal_api_key, '')
        saved = self.manager.save_environment(
            self.repo,
            ServerEnvironment(
                internal_api_key='',
                twitch_client_id='client123',
                twitch_client_secret='secret456',
                live_catalog=True,
            ),
        )
        self.assertEqual(len(saved.internal_api_key), 64)
        self.assertEqual(saved.twitch_client_id, 'client123')
        self.assertTrue(saved.live_catalog)
        raw = (self.repo / '.env').read_text()
        self.assertIn('# local server settings', raw)
        self.assertIn('CATALOG_MODE=igdb', raw)
        self.assertIn('ENABLE_LIVE_IGDB=1', raw)
        self.assertEqual(stat.S_IMODE((self.repo / '.env').stat().st_mode), 0o600)
        catalog = self.manager.write_catalog_config()
        self.assertEqual(json.loads(catalog.read_text()), {'APP_BASE_URL': 'http://127.0.0.1:8000'})
        self.assertEqual(stat.S_IMODE(catalog.stat().st_mode), 0o600)

        saved = self.manager.save_environment(
            self.repo,
            ServerEnvironment(
                internal_api_key=saved.internal_api_key,
                twitch_client_id='client123',
                twitch_client_secret='secret456',
                live_catalog=False,
            ),
        )
        self.assertFalse(saved.live_catalog)
        raw = (self.repo / '.env').read_text()
        self.assertIn('CATALOG_MODE=mock', raw)
        self.assertIn('ENABLE_LIVE_IGDB=0', raw)
        self.assertEqual(raw.count('INTERNAL_API_KEY='), 1)

    def test_live_catalog_requires_twitch_credentials(self):
        with self.assertRaises(ServerError):
            self.manager.save_environment(
                self.repo,
                ServerEnvironment(internal_api_key='a' * 32, live_catalog=True),
            )
        with self.assertRaises(ServerError):
            self.manager.save_environment(
                self.repo,
                ServerEnvironment(internal_api_key='a' * 32, twitch_client_id='bad-id!', live_catalog=True),
            )
        with self.assertRaises(ServerError):
            self.manager.save_environment(
                self.repo,
                ServerEnvironment(internal_api_key='short', live_catalog=False),
            )

    def test_env_symlink_is_not_followed(self):
        target = self.root / 'outside.env'
        target.write_text('INTERNAL_API_KEY=' + 'x' * 64 + '\n')
        os.symlink(target, self.repo / '.env')
        self.assertEqual(self.manager.read_environment().internal_api_key, '')
        self.manager.save_environment(
            self.repo,
            ServerEnvironment(internal_api_key='k' * 64),
        )
        self.assertFalse((self.repo / '.env').is_symlink())
        self.assertEqual((self.repo / '.env').stat().st_mode & 0o777, 0o600)
        self.assertIn('INTERNAL_API_KEY=' + 'x' * 64, target.read_text())
        self.assertNotIn('INTERNAL_API_KEY=' + 'x' * 64, (self.repo / '.env').read_text())

    def test_status_and_clone(self):
        status = self.manager.status()
        self.assertTrue(status.healthy)
        self.assertTrue(status.repo_installed)
        self.assertTrue(status.docker_available)

        clone_root = self.root / 'clone'
        manager = ServerManager(
            config_dir=self.root / 'clone-config',
            clone_dir=clone_root,
            repo_dir=self.root / 'missing',
            runner=Runner(),
            health_transport=lambda url, timeout: False,
            environ={'PATH': os.environ.get('PATH', ''), 'XDG_CONFIG_HOME': str(self.root / 'clone-config')},
        )
        def cloning_runner(command, **kwargs):
            target = Path(command[4])
            fake_repo(target)
            return subprocess.CompletedProcess(command, 0, '', '')
        with patch('umutron.server_manager.shutil.which',
                   side_effect=lambda name: '/usr/bin/gh' if name == 'gh' else None), \
             patch('umutron.server_manager.__file__', str(self.root / 'isolated' / 'umutron' / 'server_manager.py')):
            manager.runner = cloning_runner
            cloned = manager.clone()
            self.assertEqual(cloned, clone_root)
            self.assertTrue(manager.is_repo(cloned))
            self.assertEqual(json.loads((self.root / 'clone-config' / 'server.json').read_text())['repo_dir'], str(clone_root))

    def test_start_and_stop_commands(self):
        runner = Runner()
        self.manager.runner = runner
        self.manager.start(self.repo, build=True, recreate_api=True)
        self.assertEqual(runner.calls[-1][0][:6], ['docker', 'compose', 'up', '-d', '--build', '--force-recreate'])
        self.manager.stop(self.repo)
        self.assertEqual(runner.calls[-1][0], ['docker', 'compose', 'stop'])

    def test_apply_restarts_only_when_healthy(self):
        runner = Runner()
        self.manager.runner = runner
        self.manager.health_transport = lambda url, timeout: True
        saved = self.manager.apply_environment(
            self.repo,
            ServerEnvironment(internal_api_key='z' * 64),
        )
        self.assertEqual(saved.internal_api_key, 'z' * 64)
        self.assertIn('--force-recreate', runner.calls[-1][0])


if __name__ == '__main__':
    unittest.main()
