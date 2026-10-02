"""Runner preparation/removal contracts using inert archives and real supervisors."""
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from game_library.library import Library
from game_library.launcher import Launcher, build_command, defaults
from game_library.proton_manager import ProtonManager, validate_release
from game_library.runner_guard import acquire
from game_library.runner_preparation import prepare_runner
from game_library.runner_selection import release_selector


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir(mode=0o700)
        self.env = patch.dict(os.environ, XDG_RUNTIME_DIR=str(self.runtime), XDG_DATA_HOME=str(self.root/'data'))
        self.env.start()
        self.addCleanup(self.env.stop)
        self.lib = Library(self.root / 'library')
        self.archive = self.root / 'fixture.tar.gz'
        with tarfile.open(self.archive, 'w:gz') as archive:
            data = b'inert proton fixture'
            item = tarfile.TarInfo('GE-Proton11-fixture/proton')
            item.size, item.mode = len(data), 0o755
            archive.addfile(item, io.BytesIO(data))
        tag = 'GE-Proton11-fixture'
        self.release = dict(family='GE-Proton', version=tag, name=tag+'.tar.gz', architecture='x86_64',
                            url=f'https://github.com/GloriousEggroll/proton-ge-custom/releases/download/{tag}/{tag}.tar.gz',
                            size=self.archive.stat().st_size, digest='sha256:'+hashlib.sha256(self.archive.read_bytes()).hexdigest(), checksum_url='')
        self.selector = release_selector(self.release)
        self.manager = ProtonManager(self.lib.root / 'proton-manager', downloader=self.download, arch='x86_64')
        self.cache()
        self.exe = self.root / 'files/game.exe'
        self.exe.parent.mkdir()
        self.exe.write_text('inert')
        self.executed = self.root / 'executed'
        self.umu = self.root / 'umu'
        self.umu.write_text('#!/usr/bin/python3\nimport os\nfrom pathlib import Path\nPath('+repr(str(self.executed))+').write_text(os.environ["PROTONPATH"])\n')
        self.umu.chmod(0o700)
        self.game = self.lib.new_game()
        self.game.update(title='Fixture', executable=str(self.exe), launch={'runner':str(self.umu), 'proton':self.selector})
        self.launcher = Launcher(self.lib.root)

    def cache(self):
        r = self.release
        asset = dict(name=r['name'], size=r['size'], digest=r['digest'], browser_download_url=r['url'])
        payload = [dict(tag_name=r['version'], assets=[asset])]
        (self.manager.root / 'releases-GE-Proton-1.json').write_text(json.dumps(payload))

    def download(self, url, path, limit, cancel, progress):
        if cancel.is_set():
            raise InterruptedError('Fixture cancellation')
        Path(path).write_bytes(self.archive.read_bytes())
        progress(self.archive.stat().st_size)

    def install(self):
        return self.manager.ensure(self.release, threading.Event())

    def wait(self, predicate, timeout=6):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue(predicate())

    def supervisor(self, mode='success'):
        # Replace network transport only in an actual independent supervisor.
        bootstrap = '''
import json,sys,time
from pathlib import Path
from game_library import runner_preparation,launch_supervisor
from game_library.proton_manager import ProtonManager
archive,mode,root=sys.argv[2:]
def download(url,path,limit,cancel,progress):
    Path(root,'download-started').write_text('started')
    if mode=='cancel':
        while not cancel.is_set():time.sleep(.02)
        raise InterruptedError('Fixture cancelled download')
    if mode=='failure':raise OSError('Fixture offline')
    Path(path).write_bytes(Path(archive).read_bytes());progress(Path(archive).stat().st_size)
runner_preparation.ProtonManager=lambda root:ProtonManager(root,downloader=download,arch='x86_64')
launch_supervisor.main(sys.argv[1])
'''
        original = subprocess.Popen
        def spawn(argv, **kwargs):
            return original([sys.executable, '-c', bootstrap, argv[-1], str(self.archive), mode, str(self.root)], **kwargs)
        with patch('game_library.launcher.subprocess.Popen', side_effect=spawn):
            self.launcher.start(self.game)

    def test_missing_exact_runner_is_verified_before_execution_and_keeps_pin(self):
        with self.assertRaisesRegex(ValueError, 'not installed'):
            build_command(self.game, self.lib.root)
        self.assertEqual(build_command(self.game, self.lib.root, allow_prepare=True)[2]['PROTONPATH'], self.selector)
        self.supervisor()
        self.wait(lambda: not self.launcher.active())
        expected = str(self.manager.target(self.release))
        self.assertEqual(self.executed.read_text(), expected)
        self.assertEqual(self.launcher.current()['state'], 'Finished')
        self.assertEqual(self.launcher.current()['proton'], expected)
        self.assertEqual(self.game['launch']['proton'], self.selector)
        self.assertEqual(self.manager.installed_release(self.selector), expected)
        self.assertEqual(self.manager.local_origin(expected), 'Verified managed installation')
        self.assertEqual(build_command(self.game, self.lib.root)[2]['PROTONPATH'], expected)

    def test_failure_and_cancellation_never_execute_and_retry_succeeds(self):
        for mode, state in (('failure', 'Error'), ('cancel', 'Stopped')):
            self.supervisor(mode)
            if mode == 'cancel':
                self.wait(lambda: (self.root/'download-started').exists() and bool(self.launcher.current().get('supervisor_pid')))
                self.launcher.stop(self.game['id'])
            self.wait(lambda: not self.launcher.active())
            self.assertEqual(self.launcher.current()['state'], state)
            self.assertFalse(self.executed.exists())
            self.assertFalse(self.manager.target(self.release).exists())
            self.assertFalse(Path(defaults(self.game, self.lib.root)['prefix']).exists())
            self.assertFalse(list((self.manager.root/'staging').glob('install-*')))
            (self.root/'download-started').unlink(missing_ok=True)
        self.supervisor()
        self.wait(lambda: not self.launcher.active())
        self.assertTrue(self.executed.exists())

    def test_duplicate_waiter_cancellation_does_not_cancel_owner(self):
        began, gate = threading.Event(), threading.Event()
        calls = []
        def slow(*args):
            calls.append(args[0]);began.set();gate.wait(3);self.download(*args)
        first = ProtonManager(self.manager.root, downloader=slow, arch='x86_64')
        first.install(self.release)
        self.assertTrue(began.wait(2))
        second = ProtonManager(self.manager.root, downloader=self.download, arch='x86_64')
        second.install(self.release)
        second.cancel(self.release)
        self.wait(lambda: not second.busy())
        self.assertEqual(second.status(self.release)['state'], 'Cancelled')
        self.assertTrue(first.busy())
        gate.set()
        self.wait(lambda: not first.busy())
        self.assertEqual(first.status(self.release)['state'], 'Installed')
        self.assertEqual(len(calls), 1)
        self.assertEqual(second.status(self.release)['state'], 'Installed')
        self.assertEqual(second.ensure(self.release, threading.Event()), str(self.manager.target(self.release)))

    def test_two_processes_reuse_one_atomic_install(self):
        counter = self.root/'calls'
        program = '''
import json,sys,threading,time
from pathlib import Path
from game_library.proton_manager import ProtonManager
root,archive,release,counter=sys.argv[1:]
def download(url,path,limit,cancel,progress):
    with open(counter,'a') as f:f.write('download\\n')
    time.sleep(.15);Path(path).write_bytes(Path(archive).read_bytes());progress(Path(archive).stat().st_size)
p=ProtonManager(root,downloader=download,arch='x86_64').ensure(json.loads(release),threading.Event())
print(p)
'''
        argv = [sys.executable, '-c', program, str(self.manager.root), str(self.archive), json.dumps(self.release), str(counter)]
        first = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        second = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out1, err1 = first.communicate(timeout=8)
        out2, err2 = second.communicate(timeout=8)
        self.assertEqual((first.returncode, second.returncode), (0, 0), err1+err2)
        self.assertEqual(out1, out2)
        self.assertEqual(counter.read_text().splitlines(), ['download'])

    def test_global_inheritance_and_prefix_inspection_use_same_exact_build(self):
        path = self.install()
        self.lib.set_default_proton(self.selector)
        self.game['launch']['proton'] = 'default'
        self.game['installation']['proton'] = '/legacy/pin'
        from game_library.prefix_inventory import context
        self.assertEqual(defaults(self.game, self.lib.root)['proton'], self.selector)
        self.assertEqual(context(self.game, self.lib.root)['proton'], path)
        self.assertEqual(build_command(self.game, self.lib.root)[2]['PROTONPATH'], path)
        self.game['launch']['proton'] = ''
        self.assertEqual(defaults(self.game, self.lib.root)['proton'], '/legacy/pin')
        with self.assertRaises(ValueError):
            self.lib.set_default_proton('default')

    def test_uninstall_requires_reassignment_and_leaves_games_prefixes_custom_paths(self):
        path = self.install()
        self.lib.set_default_proton(self.selector)
        with self.assertRaisesRegex(ValueError, 'App default'):
            self.manager.uninstall(path)
        self.lib.set_default_proton('UMU-Latest')
        self.lib.save(self.game)
        with self.assertRaisesRegex(ValueError, 'Fixture'):
            self.manager.uninstall(path)
        self.game['launch']['proton'] = ''
        self.game['installation']['proton'] = path
        self.lib.save(self.game)
        with self.assertRaisesRegex(ValueError, 'Fixture'):
            self.manager.uninstall(path)
        self.game['launch']['proton'] = 'default'
        self.lib.save(self.game)
        prefix = Path(defaults(self.game, self.lib.root)['prefix'])
        prefix.mkdir(parents=True)
        save = prefix/'save';save.write_text('keep')
        with patch('game_library.runner_guard.ensure_idle'):
            self.manager.uninstall(path)
        self.assertFalse(Path(path).exists())
        self.assertEqual(save.read_text(), 'keep')
        self.assertEqual(self.exe.read_text(), 'inert')
        self.assertEqual(len(self.lib.games()), 1)
        custom = self.root/'custom';custom.mkdir();(custom/'proton').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'Only runners'):
            self.manager.uninstall(custom)
        alias = self.manager.tools/'alias';alias.symlink_to(custom)
        with self.assertRaises(ValueError):
            self.manager.uninstall(alias)
        self.assertEqual((custom/'proton').read_text(), 'keep')

    def test_shared_runner_and_active_operation_locks_block_removal(self):
        path = self.install()
        request = {'env':{'PROTONPATH':self.selector}, 'record':str(self.lib.root/'launch-state.json')}
        fd = prepare_runner(request, threading.Event(), lambda **_:None, self.manager)
        try:
            with self.assertRaisesRegex(RuntimeError, 'in use'):
                self.manager.uninstall(path)
        finally:
            os.close(fd)
        fd = os.open(self.lib.root/'launch.lock', os.O_CREAT|os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            with self.assertRaisesRegex(RuntimeError, 'active game'):
                self.manager.uninstall(path)
        finally:
            os.close(fd)

    def test_supervisor_retains_runner_lease_for_orphaned_descendant(self):
        path = self.install()
        ready = self.root/'child-ready'
        self.umu.write_text('#!/usr/bin/python3\nimport subprocess,sys\nsubprocess.Popen([sys.executable,"-c",'+repr('from pathlib import Path;import time;Path('+repr(str(ready))+').write_text("ready");time.sleep(.7)')+'])\n')
        self.launcher.start(self.game)
        self.wait(ready.exists)
        try:
            with self.assertRaises(RuntimeError):
                acquire(path, exclusive=True)
            self.assertTrue(self.launcher.active())
        finally:
            self.wait(lambda: not self.launcher.active())
        fd = acquire(path, exclusive=True)
        os.close(fd)

    def test_exact_source_architecture_checksum_and_space_validation(self):
        for changes in ({'url':self.release['url'].replace('/GE-Proton11-fixture/', '/other/')}, {'architecture':'aarch64'}, {'digest':''}, {'size':True}, {'name':'../tool.tar.gz'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_release({**self.release, **changes}, 'x86_64')
        with patch('game_library.proton_manager.shutil.disk_usage', return_value=type('Space', (), {'free':0})()):
            with self.assertRaisesRegex(ValueError, 'free space'):
                self.install()
        self.assertFalse(self.manager.target(self.release).exists())
        self.release['digest'] = 'sha256:'+'0'*64
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.install()
        self.assertFalse(self.manager.target(self.release).exists())

    def test_umu_owned_runners_are_discovered_read_only_without_client_scanning(self):
        umu = self.manager.umu_tools / 'UMU-Latest'
        umu.mkdir(parents=True)
        (umu/'proton').write_text('inert')
        (umu/'version').write_text('1774856027 UMU-Proton-10.0-4\n')
        other = self.root/'data/Steam/steamapps/common/Proton 11.0'
        other.mkdir(parents=True);(other/'proton').write_text('client fixture')
        unrelated = self.manager.umu_tools/'unrelated-tool'
        unrelated.mkdir();(unrelated/'proton').write_text('unrelated')
        self.lib.set_default_proton('UMU-Latest')
        before = self.lib.path.read_bytes()
        self.assertEqual(self.manager.installed(), [str(umu)])
        self.assertFalse(self.manager.managed(umu))
        self.assertIn('UMU-managed', self.manager.local_origin(umu))
        with self.assertRaisesRegex(ValueError, 'Only runners'):
            self.manager.uninstall(umu)
        self.assertEqual((umu/'proton').read_text(), 'inert')
        self.assertEqual(self.lib.path.read_bytes(), before)

    def test_unverified_existing_folder_is_never_overwritten_or_reused_as_verified(self):
        path = self.manager.target(self.release)
        path.mkdir();(path/'proton').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'preserved'):
            self.install()
        self.assertEqual((path/'proton').read_text(), 'keep')
        self.assertIsNone(self.manager.installed_release(self.selector))
        self.assertEqual(self.manager.status(self.release)['state'], 'Available')
        self.assertEqual(self.manager.status(self.release)['path'], '')
        self.assertIn('unverified', self.manager.local_origin(path))
        self.lib.set_default_proton(self.selector)
        self.game['launch']['proton']='default'
        self.assertEqual(build_command(self.game, self.lib.root, allow_prepare=True)[2]['PROTONPATH'], self.selector)
        self.supervisor()
        self.wait(lambda:not self.launcher.active())
        self.assertEqual(self.launcher.current()['state'], 'Error')
        self.assertFalse(self.executed.exists())
        self.assertEqual((path/'proton').read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
