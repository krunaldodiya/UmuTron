from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from steam_library import vdf
from steam_library.library import Library
from steam_library.steam import SteamSync


class SteamTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.account=self.root/'steam/userdata/123'
        (self.account/'config').mkdir(parents=True)
        self.lib=Library(self.root/'library')
        self.game=self.lib.new_game(); self.game.update(title='Demo',executable=str(self.root/'demo.exe'),metadata_app_id=620)
        Path(self.game['executable']).write_bytes(b'fixture; never execute')
        self.lib.save(self.game)
        self.engine=SteamSync(self.lib, running=lambda:False)

    def test_round_trip_keeps_unknown_fields_and_types(self):
        tree={'shortcuts':(0,{'0':(0,{'appid':vdf.integer(0xf1234567),'AppName':vdf.text('Game'),'extra':(7,b'12345678')})})}
        raw=vdf.dumps(tree)
        self.assertEqual(vdf.dumps(vdf.loads(raw)),raw)
        with self.assertRaises(ValueError): vdf.loads(raw[:-1])

    def test_preview_has_no_side_effect_then_sync_and_relink_keep_id(self):
        plan=self.engine.preview(self.game,self.account)
        target=self.account/'config/shortcuts.vdf'
        self.assertFalse(target.exists())
        self.assertNotEqual(plan['shortcut_id'],620)
        self.engine.apply(plan)
        first=target.read_bytes()
        saved=self.lib.games()[0]
        new=self.root/'moved.exe'; new.write_bytes(b'fixture')
        saved['executable']=str(new); saved['title']='Renamed'; self.lib.save(saved)
        second=self.engine.preview(saved,self.account)
        self.assertEqual(second['shortcut_id'],plan['shortcut_id'])
        self.engine.apply(second)
        entries=vdf.loads(target.read_bytes())['shortcuts'][1]
        self.assertEqual(len(entries),1)
        self.assertNotEqual(first,target.read_bytes())
        self.engine.undo(self.engine.latest_backup())
        self.assertEqual(target.read_bytes(),first)
        self.assertEqual(self.lib.status(self.lib.games()[0]),'Changes pending')

    def test_existing_executable_adopted_without_duplicate(self):
        target=self.account/'config/shortcuts.vdf'
        entry={'appid':vdf.integer(998),'AppName':vdf.text('Old'),'Exe':vdf.text('"'+self.game['executable']+'"'),'custom':vdf.text('keep')}
        target.write_bytes(vdf.dumps({'shortcuts':(0,{'0':(0,entry)})}))
        plan=self.engine.preview(self.game,self.account)
        self.assertEqual(plan['shortcut_id'],998)
        self.engine.apply(plan)
        entry=vdf.loads(target.read_bytes())['shortcuts'][1]['0'][1]
        self.assertEqual(vdf.value(entry,'custom'),'keep')

    def test_running_steam_blocks_writes(self):
        plan=self.engine.preview(self.game,self.account)
        self.engine.running=lambda:True
        with self.assertRaises(RuntimeError): self.engine.apply(plan)
        self.assertFalse((self.account/'config/shortcuts.vdf').exists())

    def test_external_change_invalidates_preview(self):
        plan=self.engine.preview(self.game,self.account)
        target=self.account/'config/shortcuts.vdf'; target.write_bytes(b'external')
        with self.assertRaises(RuntimeError): self.engine.apply(plan)
        self.assertEqual(target.read_bytes(),b'external')

    def test_undo_refuses_changed_files(self):
        self.engine.apply(self.engine.preview(self.game,self.account))
        target=self.account/'config/shortcuts.vdf'; target.write_bytes(b'external')
        with self.assertRaises(RuntimeError): self.engine.undo(self.engine.latest_backup())
        self.assertEqual(target.read_bytes(),b'external')

    def test_unrelated_shortcut_and_compat_settings_unchanged(self):
        config=self.account/'config'
        compat=config/'config.vdf'; compat.write_bytes(b'untouched compatibility settings')
        unrelated={'appid':vdf.integer(33),'AppName':vdf.text('Other'),'Exe':vdf.text('/other.exe')}
        target=config/'shortcuts.vdf'; target.write_bytes(vdf.dumps({'shortcuts':(0,{'0':(0,unrelated)})}))
        self.engine.apply(self.engine.preview(self.game,self.account))
        self.assertEqual(vdf.loads(target.read_bytes())['shortcuts'][1]['0'][1],unrelated)
        self.assertEqual(compat.read_bytes(),b'untouched compatibility settings')

    def test_write_failure_rolls_back_shortcuts(self):
        plan=self.engine.preview(self.game,self.account)
        with patch.object(self.lib,'mark_synced',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.engine.apply(plan)
        self.assertFalse((self.account/'config/shortcuts.vdf').exists())
        self.assertIsNone(self.engine.latest_backup())

    def test_missing_mapped_shortcut_reuses_id(self):
        first=self.engine.preview(self.game,self.account); self.engine.apply(first)
        (self.account/'config/shortcuts.vdf').unlink()
        game=self.lib.games()[0]; game['title']='Different'; self.lib.save(game)
        second=self.engine.preview(game,self.account)
        self.assertEqual(first['shortcut_id'],second['shortcut_id'])

    def test_two_library_entries_cannot_take_over_same_shortcut(self):
        self.engine.apply(self.engine.preview(self.game,self.account))
        other=self.lib.new_game(); other.update(title='Duplicate',executable=self.game['executable']); self.lib.save(other)
        with self.assertRaisesRegex(ValueError,'already managed'): self.engine.preview(other,self.account)

    def test_interrupted_sync_can_recover_before_next_sync(self):
        import json
        self.engine.apply(self.engine.preview(self.game,self.account))
        backup=self.engine.latest_backup(); data=json.loads(backup.read_text()); data['state']='prepared'; backup.write_text(json.dumps(data))
        plan=self.engine.preview(self.lib.games()[0],self.account)
        with self.assertRaisesRegex(RuntimeError,'interrupted'): self.engine.apply(plan)
        self.engine.undo(backup)
        self.assertFalse((self.account/'config/shortcuts.vdf').exists())

    def test_failed_undo_bookkeeping_can_recover(self):
        self.engine.apply(self.engine.preview(self.game,self.account))
        backup=self.engine.latest_backup()
        with patch.object(self.lib,'mark_unsynced',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.engine.undo(backup)
        self.assertEqual(self.engine.latest_backup(),backup)
        self.engine.undo(backup)
        self.assertFalse((self.account/'config/shortcuts.vdf').exists())
        self.assertIsNone(self.engine.latest_backup())

    def test_noop_preview_still_detects_external_shortcut_change(self):
        self.engine.apply(self.engine.preview(self.game,self.account))
        plan=self.engine.preview(self.lib.games()[0],self.account)
        self.assertEqual(plan['files'],{})
        target=self.account/'config/shortcuts.vdf'; target.write_bytes(b'external change')
        with self.assertRaises(RuntimeError): self.engine.apply(plan)
        self.assertEqual(target.read_bytes(),b'external change')

    def test_failure_does_not_rollback_over_external_change(self):
        target=self.account/'config/shortcuts.vdf'
        plan=self.engine.preview(self.game,self.account)
        def external_change(*args):
            target.write_bytes(b'written by another process')
            raise OSError('simulated failure')
        with patch.object(self.lib,'mark_synced',side_effect=external_change):
            with self.assertRaises(RuntimeError): self.engine.apply(plan)
        self.assertEqual(target.read_bytes(),b'written by another process')
        import json
        self.assertEqual(json.loads(self.engine.latest_backup().read_text())['state'],'prepared')
