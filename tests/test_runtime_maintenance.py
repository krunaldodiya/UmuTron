import fcntl
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_prefix_inventory import pe, prefix_at

from game_library.launcher import Launcher
from game_library.prefix_guard import acquire, process_conflicts
from game_library.prefix_inventory import RECIPES
from game_library.runtime_maintenance import (
    confirmation_text,
    install_plan,
    prepare,
    trusted,
    verify,
)


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prefix = prefix_at(self.root)
        self.proton = self.root / 'UMU-Proton-test'
        self.proton.mkdir()
        (self.proton / 'proton').write_text('inert')
        self.runner = self.root / 'umu-run'
        self.runner.write_text('inert')
        self.runner.chmod(0o700)
        self.game = {'id': '6d4f2270-447b-467b-91b3-dd9cf26b8a19', 'title': 'Fixture', 'launch': {
            'prefix': str(self.prefix), 'proton': str(self.proton), 'runner': str(self.runner)}}
        self.lib = self.root / 'library'
        self.lib.mkdir()

    def plan(self):
        return install_plan(self.game, self.lib, 'vc14-x64')

    def test_no_created_prefix_and_alias_runner_are_blocked(self):
        self.game['launch']['proton'] = 'UMU-Latest'
        with self.assertRaisesRegex(ValueError, 'concrete'):
            self.plan()
        self.game['launch']['prefix'] = str(self.root / 'not-created')
        with self.assertRaisesRegex(ValueError, 'initialized'):
            self.plan()
        self.assertFalse((self.root / 'not-created').exists())

    def test_satisfied_native_requirement_blocks_and_no_download(self):
        for dll in RECIPES['vc14-x64'].dlls:
            pe(self.prefix / 'drive_c/windows/system32' / dll)
        with self.assertRaisesRegex(ValueError, 'positively satisfied'):
            self.plan()

    def test_confirmation_license_scope_arch_and_install_only(self):
        plan = self.plan()
        text = confirmation_text(plan)
        for value in (str(self.prefix), str(self.proton), 'x64', 'license', 'upgrade', 'external', 'unknown'):
            self.assertIn(value, text)
        self.assertEqual(plan['game']['launch']['arguments'], [])
        self.assertEqual(plan['game']['launch']['dll_overrides'], '')
        for key in ('dotnet', 'directx', 'uninstall', 'vcrun2022'):
            with self.assertRaises(ValueError):
                install_plan(self.game, self.lib, key)

    def test_download_hosts_are_allowlisted_and_redirects_checked(self):
        self.assertEqual(trusted(RECIPES['vc14-x64'].url), RECIPES['vc14-x64'].url)
        for url in ('http://aka.ms/x', 'https://aka.ms.evil/x', 'https://user@aka.ms/x', 'https://example.com/x', 'https://aka.ms:444/x'):
            with self.assertRaises(ValueError):
                trusted(url)

    def request(self):
        plan = self.plan()
        return {'record': str(self.lib / 'launch-session.json'), 'runtime_game': plan['game'],
                'recipe': plan['recipe'], 'runtime_context': list(plan['context'])}

    def test_prepare_matches_exact_context_interactive_args_and_verify(self):
        request = self.request()
        def download(req, path, cancelled, progress):
            pe(path)
            return 'fixture-digest', (14, 44, 35211, 0)
        with patch('game_library.runtime_maintenance.download_installer', side_effect=download), patch('game_library.prefix_guard.ensure_idle'):
            temp, argv, cwd, env, digest = prepare(request, lambda: False, lambda _: None)
            try:
                self.assertEqual(argv[0], str(self.runner))
                self.assertEqual(argv[2:], ['/install', '/norestart'])
                self.assertEqual(env['WINEPREFIX'], str(self.prefix))
                self.assertEqual(env['PROTONPATH'], str(self.proton))
                self.assertNotIn('WINEDLLOVERRIDES', env)
                self.assertEqual(env['PROTONFIXES_DISABLE'], '1')
                self.assertFalse(verify(request)[0])
            finally:
                temp.cleanup()
        request['runtime_context'][0] = '/wrong-prefix'
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            prepare(request, lambda: False, lambda _: None)

    def test_cancel_before_download_and_failure_never_mark_installed(self):
        request = self.request()
        with patch('game_library.runtime_maintenance.download_installer') as download:
            with self.assertRaises(InterruptedError):
                prepare(request, lambda: True, lambda _: None)
            download.assert_not_called()
        self.assertFalse(verify(request)[0])

    def test_cross_library_prefix_lock_and_global_guard(self):
        env = {'XDG_RUNTIME_DIR': str(self.root / 'locks')}
        with patch.dict(os.environ, env), patch('game_library.prefix_guard.ensure_idle'):
            fd = acquire(self.prefix)
            try:
                with self.assertRaisesRegex(RuntimeError, 'owns this prefix'):
                    acquire(self.prefix)
            finally:
                os.close(fd)
        launch = Launcher(self.lib)
        with (self.lib / 'launch.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            plan = self.plan()
            with patch('subprocess.Popen') as popen, self.assertRaises(RuntimeError):
                launch.start(plan['game'], operation='runtime', runtime_recipe=plan['recipe'], runtime_context=plan['context'])
            popen.assert_not_called()

    def test_external_process_sharing_prefix_blocks(self):
        proc = self.root / 'proc'
        directory = proc / '987654'
        directory.mkdir(parents=True)
        (directory / 'environ').write_bytes(b'WINEPREFIX=' + os.fsencode(self.prefix) + b'\0')
        conflicts, uncertain = process_conflicts(self.prefix, proc)
        self.assertEqual(conflicts, ['987654'])
        self.assertFalse(uncertain)

    def test_cancel_context_cannot_be_omitted(self):
        launch = Launcher(self.lib)
        with self.assertRaisesRegex(ValueError, 'confirmation'):
            launch.start(self.game, operation='runtime', runtime_recipe='vc14-x64')

    def test_ambiguous_native_files_block_safe_install(self):
        pe(self.prefix / 'drive_c/windows/system32/vcruntime140.dll', origin='unknown')
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            self.plan()

    def test_newer_explicit_minimum_is_not_satisfied_by_older_core(self):
        for dll in RECIPES['vc14-x64'].dlls:
            pe(self.prefix / 'drive_c/windows/system32' / dll)
        plan = install_plan(self.game, self.lib, 'vc14-modern-x64')
        self.assertEqual(plan['requirement'].minimum, (14, 44, 35211, 0))
        self.assertIn('14.44.35211.0', confirmation_text(plan))

    def test_runner_replacement_invalidates_confirmation(self):
        request = self.request()
        (self.proton / 'proton').write_text('replacement build')
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            prepare(request, lambda: False, lambda _: None)

    def test_download_failure_releases_global_and_prefix_locks_without_execution(self):
        import subprocess
        import sys
        import time
        original = subprocess.Popen
        bootstrap = '''
import sys
from game_library import runtime_maintenance, launch_supervisor
runtime_maintenance.download_installer = lambda *a: (_ for _ in ()).throw(OSError('fixture network failure'))
launch_supervisor.main(sys.argv[1])
'''
        launch = Launcher(self.lib)
        plan = self.plan()
        def fixture_supervisor(argv, **kwargs):
            return original([sys.executable, '-c', bootstrap, argv[-1]], **kwargs)
        with patch('game_library.launcher.subprocess.Popen', side_effect=fixture_supervisor):
            launch.start(plan['game'], operation='runtime', runtime_recipe=plan['recipe'], runtime_context=plan['context'])
        deadline = time.monotonic() + 5
        while launch.active() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertFalse(launch.active())
        self.assertEqual(launch.current()['state'], 'Error')
        self.assertIn('fixture network failure', '\n'.join(launch.current()['logs']))
        self.assertFalse(verify(self.request())[0])
        fd = acquire(self.prefix)
        os.close(fd)

    def test_runtime_supervisor_success_requires_native_evidence(self):
        import subprocess
        import sys
        import time
        original = subprocess.Popen
        bootstrap = '''
import sys
sys.path.insert(0, 'tests')
from test_prefix_inventory import pe
from game_library import runtime_maintenance, launch_supervisor

def download(req, dest, cancelled, progress):
    pe(dest)
    return 'fixture', (14, 0, 24212, 0)
runtime_maintenance.download_installer = download
launch_supervisor.main(sys.argv[1])
'''
        # This inert runner copies synthetic PE images inside the temporary test prefix only.
        payload = self.root / 'payload'
        for dll in RECIPES['vc14-x64'].dlls:
            pe(payload / dll)
        self.runner.write_text('#!/usr/bin/python3\nimport os,pathlib,shutil\n'
                               + 'source=pathlib.Path(' + repr(str(payload)) + ')\n'
                               + 'dest=pathlib.Path(os.environ["WINEPREFIX"])/"drive_c/windows/system32"\n'
                               + 'for p in source.iterdir():shutil.copyfile(p,dest/p.name)\n')
        launch = Launcher(self.lib)
        plan = self.plan()
        def fixture_supervisor(argv, **kwargs):
            return original([sys.executable, '-c', bootstrap, argv[-1]], **kwargs)
        with patch('game_library.launcher.subprocess.Popen', side_effect=fixture_supervisor):
            launch.start(plan['game'], operation='runtime', runtime_recipe=plan['recipe'], runtime_context=plan['context'])
        deadline = time.monotonic() + 5
        while launch.active() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertFalse(launch.active())
        self.assertEqual(launch.current()['state'], 'Finished', launch.current())
        self.assertTrue(launch.current()['runtime_verified'])
        self.assertFalse((self.lib / 'installation-sessions').exists())

    def test_cancellation_keeps_both_locks_until_owned_fixture_exits(self):
        import subprocess
        import sys
        import time
        original = subprocess.Popen
        bootstrap = '''
import sys
sys.path.insert(0, 'tests')
from test_prefix_inventory import pe
from game_library import runtime_maintenance, launch_supervisor

def download(req, dest, cancelled, progress):
    pe(dest)
    return 'fixture', (14, 0, 24212, 0)
runtime_maintenance.download_installer = download
launch_supervisor.main(sys.argv[1])
'''
        sentinel = self.root / 'started'
        self.runner.write_text('#!/usr/bin/python3\nimport pathlib,time\n'
                               + 'pathlib.Path(' + repr(str(sentinel)) + ').write_text("started")\n'
                               + 'time.sleep(20)\n')
        launch = Launcher(self.lib)
        plan = self.plan()
        def fixture_supervisor(argv, **kwargs):
            return original([sys.executable, '-c', bootstrap, argv[-1]], **kwargs)
        with patch('game_library.launcher.subprocess.Popen', side_effect=fixture_supervisor):
            launch.start(plan['game'], operation='runtime', runtime_recipe=plan['recipe'], runtime_context=plan['context'])
        deadline = time.monotonic() + 5
        while not sentinel.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue(sentinel.exists(), launch.current())
        with self.assertRaisesRegex(RuntimeError, 'owns this prefix'):
            acquire(self.prefix)
        self.assertTrue(Launcher(self.lib).active())
        launch.stop(self.game['id'])
        while launch.active() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertFalse(launch.active())
        self.assertEqual(launch.current()['state'], 'Stopped')
        self.assertFalse(launch.current()['runtime_verified'])
        fd = acquire(self.prefix)
        os.close(fd)


    def test_newer_partial_component_appearing_during_download_blocks_downgrade(self):
        request = self.request()
        def download(req, destination, cancelled, progress):
            pe(destination)
            pe(self.prefix / 'drive_c/windows/system32/vcruntime140.dll', version=(14, 99, 0, 0))
            return 'fixture', (14, 44, 35211, 0)
        with patch('game_library.runtime_maintenance.download_installer', side_effect=download), patch('game_library.prefix_guard.ensure_idle'):
            with self.assertRaisesRegex(RuntimeError, 'downgrade blocked'):
                prepare(request, lambda: False, lambda _: None)
