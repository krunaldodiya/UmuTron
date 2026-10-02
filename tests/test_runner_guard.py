import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from game_library.runner_guard import acquire, ensure_idle


class RunnerGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir(mode=0o700)
        self.env = patch.dict(os.environ, XDG_RUNTIME_DIR=str(self.runtime))
        self.env.start()
        self.addCleanup(self.env.stop)
        self.runner = self.root / 'runner'
        self.runner.mkdir()

    def test_shared_launch_leases_block_exclusive_removal_until_all_close(self):
        first = acquire(self.runner)
        second = acquire(self.runner)
        try:
            with self.assertRaises(RuntimeError):
                acquire(self.runner, exclusive=True)
            os.close(first)
            first = None
            with self.assertRaises(RuntimeError):
                acquire(self.runner, exclusive=True)
        finally:
            if first is not None:
                os.close(first)
            os.close(second)
        removal = acquire(self.runner, exclusive=True)
        try:
            with self.assertRaises(RuntimeError):
                acquire(self.runner)
        finally:
            os.close(removal)

    def test_symlink_aliases_share_the_same_runner_lease(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.runner)
        launch = acquire(alias)
        try:
            with self.assertRaises(RuntimeError):
                acquire(self.runner, exclusive=True)
        finally:
            os.close(launch)

    def test_unsafe_runtime_directory_is_rejected(self):
        self.runtime.chmod(0o777)
        with self.assertRaises(RuntimeError):
            acquire(self.runner)

    def test_external_process_environment_blocks_removal(self):
        proc = self.root / 'proc'
        process = proc / '999999'
        process.mkdir(parents=True)
        (process / 'environ').write_bytes(b'PROTONPATH=' + os.fsencode(self.runner) + b'\0')
        with self.assertRaisesRegex(RuntimeError, 'still use'):
            ensure_idle(self.runner, proc)
        (process / 'environ').write_bytes(b'PROTONPATH=/other/runner\0')
        ensure_idle(self.runner, proc)

    def test_unreadable_same_user_process_fails_closed(self):
        proc = self.root / 'proc'
        process = proc / '999999'
        process.mkdir(parents=True)
        (process / 'environ').write_bytes(b'')
        with patch.object(Path, 'open', side_effect=PermissionError('denied')):
            with self.assertRaisesRegex(RuntimeError, 'Cannot verify'):
                ensure_idle(self.runner, proc)
