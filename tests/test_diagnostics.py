import fcntl
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from game_library import diagnostics


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def log(self,data=b'test',mtime=100):
        p=self.root/'diagnostics'/str(uuid4())/'steam-default.log';p.parent.mkdir(parents=True)
        p.write_bytes(data);os.utime(p,(mtime,mtime));return p
    def test_age_size_total_and_preservation(self):
        old=self.log(mtime=1);large=self.log(b'0123456789',80);other=self.log(b'abcdef',90)
        untouched=self.root/'prefixes'/'user.reg';untouched.parent.mkdir();untouched.write_text('save')
        with patch.multiple(diagnostics,MAX_FILE=6,MAX_TOTAL=6,MAX_AGE=50):
            diagnostics.cleanup(self.root,now=100)
        self.assertFalse(old.exists());self.assertFalse(large.exists());self.assertEqual(other.read_bytes(),b'abcdef')
        self.assertEqual(untouched.read_text(),'save')
    def test_truncation_keeps_tail(self):
        p=self.log(b'0123456789')
        with patch.object(diagnostics,'MAX_FILE',4):diagnostics.cleanup(self.root,now=100)
        self.assertEqual(p.read_bytes(),b'6789')
    def test_clear_only_logs_and_ignore_links(self):
        p=self.log();note=p.parent/'notes.txt';note.write_text('keep')
        outside=self.root/'outside.log';outside.write_text('keep');(p.parent/'link.log').symlink_to(outside)
        linked=self.root/'diagnostics'/str(uuid4());linked.symlink_to(p.parent,target_is_directory=True)
        self.assertEqual(diagnostics.clear_all(self.root),1)
        self.assertTrue(note.exists());self.assertEqual(outside.read_text(),'keep')
    def test_active_lock_prevents_all_clearing(self):
        p=self.log()
        with (self.root/'launch.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError,'active game'):diagnostics.clear_all(self.root)
        self.assertTrue(p.exists());diagnostics.clear_all(self.root);self.assertFalse(p.exists())
