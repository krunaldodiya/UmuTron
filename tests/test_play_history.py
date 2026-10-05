from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
from game_library.library import Library
from game_library.play_history import PlayMilestone,record,recent,revision


class PlayHistoryTests(unittest.TestCase):
    def test_preparation_installer_cancel_and_transient_process_do_not_count(self):
        for operation,evidence,stopping in [('installer',True,False),('runtime',True,False),('play',False,False),('play',True,True)]:
            milestone=PlayMilestone()
            self.assertFalse(milestone.observe(operation,evidence,stopping,1))
            self.assertFalse(milestone.observe(operation,evidence,stopping,4))
        milestone=PlayMilestone()
        self.assertFalse(milestone.observe('play',True,False,1))
        self.assertFalse(milestone.observe('play',False,False,2))
        self.assertFalse(milestone.observe('play',True,False,4))
        self.assertTrue(milestone.observe('play',True,False,6))
        self.assertFalse(milestone.observe('play',True,False,9))

    def test_add_only_absent_and_repeat_play_updates_order(self):
        with tempfile.TemporaryDirectory() as temp:
            library=Library(Path(temp));a=library.new_game();a['title']='A';library.save(a)
            b=library.new_game();b['title']='B';library.save(b)
            self.assertEqual(recent(library),[])
            record(library.root,a['id'],str(uuid4()),100);record(library.root,b['id'],str(uuid4()),200)
            self.assertEqual([g['title'] for g in recent(library)],['B','A'])
            record(library.root,a['id'],str(uuid4()),300)
            self.assertEqual([g['title'] for g in recent(library)],['A','B'])

    def test_history_revision_changes_and_restart_reads_records(self):
        with tempfile.TemporaryDirectory() as temp:
            library=Library(Path(temp));game=library.new_game();game['title']='Played';library.save(game)
            self.assertIsNone(revision(library.root))
            record(library.root,game['id'],str(uuid4()),100);first=revision(library.root)
            self.assertIsNotNone(first)
            record(library.root,game['id'],str(uuid4()),200)
            self.assertNotEqual(revision(library.root),first)
            self.assertEqual([g['id'] for g in recent(Library(library.root))],[game['id']])
