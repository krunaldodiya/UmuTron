from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from game_library.process_evidence import selected_game_evidence
from game_library.play_history import PlayMilestone


class SelectedGameEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.proc=self.root/'proc';self.proc.mkdir();self.prefix=self.root/'prefix';(self.prefix/'dosdevices').mkdir(parents=True)
        self.selected=self.root/'Selected'/'game.exe';self.selected.parent.mkdir();self.selected.write_bytes(b'inert')
        self.other=self.root/'Other'/'game.exe';self.other.parent.mkdir();self.other.write_bytes(b'other')
        self.process(101,1,'12345','supervisor');self.process(102,101,'12346',str(self.selected))

    def process(self,pid,parent,start,arg):
        folder=self.proc/str(pid);folder.mkdir(exist_ok=True)
        fields=['S',str(parent)]+['0']*17+[start]
        (folder/'stat').write_text(f'{pid} (fixture) '+ ' '.join(fields))
        (folder/'cmdline').write_bytes(arg.encode()+b'\0')

    def evidence(self):return selected_game_evidence(101,'12345',self.selected,self.prefix,self.proc)

    def test_same_basename_wrapper_argument_relative_path_and_unknown_drive_do_not_count(self):
        for arg in (str(self.other),'game.exe','wine\0'+str(self.selected),r'Q:\Selected\game.exe'):
            with self.subTest(arg=arg):
                self.process(102,101,'12346',arg);self.assertIsNone(self.evidence())

    def test_exact_unix_path_and_explicit_wine_mapping_count(self):
        token=self.evidence();self.assertEqual(token[:2],(102,'12346'))
        (self.prefix/'dosdevices'/'c:').symlink_to(self.root,target_is_directory=True)
        self.process(102,101,'12346',r'C:\Selected\game.exe');self.assertEqual(self.evidence(),token)

    def test_unrelated_process_duplicate_candidate_and_pid_reuse_do_not_count(self):
        self.process(102,1,'12346',str(self.selected));self.assertIsNone(self.evidence())
        self.process(102,101,'12346',str(self.selected));self.process(103,101,'12347',str(self.selected));self.assertIsNone(self.evidence())
        self.process(101,1,'99999','supervisor');self.assertIsNone(self.evidence())

    def test_new_process_token_restarts_two_second_milestone(self):
        milestone=PlayMilestone();a=(102,'12346',1,2);b=(103,'12347',1,2)
        self.assertFalse(milestone.observe('play',a,False,0))
        self.assertFalse(milestone.observe('play',b,False,2))
        self.assertTrue(milestone.observe('play',b,False,4))

    def test_unresolved_helper_does_not_hide_verified_game(self):
        expected=self.evidence()
        for arg in ('/runtime-only/libexec/helper',r'C:\windows\system32\missing.exe'):
            with self.subTest(arg=arg):
                self.process(103,101,'12347',arg)
                self.assertEqual(self.evidence(),expected)

    def test_exiting_helper_does_not_hide_verified_game(self):
        expected=self.evidence();self.process(103,101,'12347','helper')
        (self.proc/'103'/'cmdline').unlink()
        self.assertEqual(self.evidence(),expected)

    def test_unreadable_helper_does_not_hide_verified_game(self):
        expected=self.evidence();self.process(103,101,'12347','helper')
        original=Path.open
        def opened(path,*args,**kwargs):
            if path==self.proc/'103'/'cmdline':raise PermissionError('fixture')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',opened):self.assertEqual(self.evidence(),expected)

    def test_missing_selected_process_or_reused_candidate_never_counts(self):
        (self.proc/'102'/'cmdline').unlink();self.assertIsNone(self.evidence())
        self.process(102,101,'12346',str(self.selected));original=Path.open
        def opened(path,*args,**kwargs):
            if path==self.proc/'102'/'cmdline':
                fields=['S','101']+['0']*17+['99999']
                (self.proc/'102'/'stat').write_text('102 (fixture) '+' '.join(fields))
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',opened):self.assertIsNone(self.evidence())

    def test_verified_game_with_helpers_reaches_play_milestone(self):
        self.process(103,101,'12347','/runtime-only/libexec/helper')
        milestone=PlayMilestone()
        self.assertFalse(milestone.observe('play',self.evidence(),False,10))
        self.assertTrue(milestone.observe('play',self.evidence(),False,12))
