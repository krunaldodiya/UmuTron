from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from game_library.library import Library


class GameUninstallTests(unittest.TestCase):
    def setUp(self):
        from game_library.game_uninstall import GameUninstall
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        runtime=patch.dict(os.environ,{'XDG_RUNTIME_DIR':str(self.root/'runtime')});runtime.start();self.addCleanup(runtime.stop)
        self.library=Library(self.root/'library');self.folder=self.root/'Games'/'Fixture';self.folder.mkdir(parents=True)
        (self.folder/'bin').mkdir();self.exe=self.folder/'bin/game.exe';self.exe.write_bytes(b'inert game')
        self.folder.chmod(0o700);(self.folder/'bin').chmod(0o700);self.exe.chmod(0o600)
        self.game=self.library.new_game();self.game.update(title='Fixture',executable=str(self.exe),working_dir=str(self.folder));self.library.save(self.game)
        self.service=GameUninstall(self.library,idle_check=lambda *_:None,runtime_root=self.root/'locks')

    def test_confirm_reuses_folder_but_does_not_delete_then_uninstall_removes_entry_only_after_files(self):
        receipt=self.service.inspect(self.game,self.folder)
        self.service.confirm(self.game,receipt)
        self.assertTrue(self.exe.is_file());self.assertEqual(len(self.library.games()),1)
        plan=self.service.plan(self.game)
        self.service.execute(plan)
        self.assertFalse(self.folder.exists());self.assertEqual(self.library.games(),[])

    def test_unconfirmed_imported_or_shared_root_and_binary_subfolder_are_rejected(self):
        with self.assertRaises(ValueError):self.service.plan(self.game)
        for folder in (self.root/'Games',self.folder/'bin',Path.home(),Path('/')):
            with self.subTest(folder=folder),self.assertRaises(ValueError):self.service.inspect(self.game,folder)
        other=self.library.new_game();other.update(title='Other',executable=str(self.folder/'other.exe'));self.library.save(other)
        with self.assertRaises(ValueError):self.service.inspect(self.game,self.folder)

    def test_symlink_savedata_unknown_files_and_nested_mount_fail_closed(self):
        for name in ('save.sav','personal.txt'):
            file=self.folder/name;file.write_text('keep')
            with self.assertRaises(ValueError):self.service.inspect(self.game,self.folder)
            file.unlink()
        link=self.folder/'linked.dll';link.symlink_to(self.exe)
        with self.assertRaises(ValueError):self.service.inspect(self.game,self.folder)
        link.unlink()
        with patch('game_library.game_uninstall.mount_points',return_value={str(self.folder/'bin')}):
            with self.assertRaises(ValueError):self.service.inspect(self.game,self.folder)

    def test_changed_root_or_new_files_invalidate_confirmation(self):
        receipt=self.service.inspect(self.game,self.folder);self.service.confirm(self.game,receipt)
        plan=self.service.plan(self.game);(self.folder/'new.dll').write_text('new')
        with self.assertRaises(ValueError):self.service.execute(plan)
        self.assertTrue(self.exe.is_file());self.assertEqual(len(self.library.games()),1)

    def test_live_operation_and_stale_library_block_before_mutation(self):
        receipt=self.service.inspect(self.game,self.folder);self.service.confirm(self.game,receipt);plan=self.service.plan(self.game)
        self.service.idle_check=lambda *_: (_ for _ in ()).throw(RuntimeError('busy'))
        with self.assertRaises(RuntimeError):self.service.execute(plan)
        self.service.idle_check=lambda *_:None
        changed=dict(self.game,title='Changed');self.library.save(changed)
        with self.assertRaises(ValueError):self.service.execute(plan)
        self.assertTrue(self.exe.is_file())

    def test_partial_failure_keeps_record_and_recovers_only_remaining_approved_files(self):
        receipt=self.service.inspect(self.game,self.folder);self.service.confirm(self.game,receipt);plan=self.service.plan(self.game)
        original=self.service._delete_tree
        self.service._delete_tree=lambda *_: (_ for _ in ()).throw(OSError('fixture failure'))
        with self.assertRaises(OSError):self.service.execute(plan)
        self.assertEqual(len(self.library.games()),1)
        self.service._delete_tree=original
        self.service.execute(self.service.plan(self.game))
        self.assertEqual(self.library.games(),[])

    def test_metadata_write_failure_keeps_recoverable_entry(self):
        receipt=self.service.inspect(self.game,self.folder);self.service.confirm(self.game,receipt);plan=self.service.plan(self.game)
        with patch.object(self.library,'delete',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.service.execute(plan)
        self.assertEqual(len(self.library.games()),1)
        self.service.execute(self.service.plan(self.game));self.assertEqual(self.library.games(),[])

    def test_other_game_symlink_alias_blocks_confirmation_and_execution(self):
        self.service.confirm(self.game,self.service.inspect(self.game,self.folder));plan=self.service.plan(self.game)
        alias=self.root/'Alias';alias.symlink_to(self.folder,target_is_directory=True)
        other=self.library.new_game();other.update(title='Alias game',executable=str(alias/'bin/game.exe'));self.library.save(other)
        with self.assertRaisesRegex(ValueError,'Another library'):self.service.inspect(self.game,self.folder)
        with self.assertRaisesRegex(ValueError,'Another library'):self.service.execute(plan)
        self.assertTrue(self.exe.exists());self.assertEqual(len(self.library.games()),2)

    def test_source_swap_is_captured_but_never_deleted(self):
        from game_library.game_uninstall import move_exclusive
        self.service.confirm(self.game,self.service.inspect(self.game,self.folder));plan=self.service.plan(self.game)
        replacement=self.root/'personal.dll';replacement.write_bytes(b'personal data');replacement.chmod(0o600)
        def swap(source,destination,source_fd,destination_fd):
            if source=='game.exe':
                os.rename(source,'original.exe',src_dir_fd=source_fd,dst_dir_fd=source_fd)
                os.rename(replacement,source,dst_dir_fd=source_fd)
            return move_exclusive(source,destination,source_fd,destination_fd)
        with patch('game_library.game_uninstall.move_exclusive',side_effect=swap):
            with self.assertRaisesRegex(ValueError,'unexpected captured'):self.service.execute(plan)
        self.assertEqual(len(self.library.games()),1)
        staged=list(self.folder.parent.glob('UmuTron-uninstall-stage-*/*'))
        self.assertEqual([p.read_bytes() for p in staged],[b'personal data'])
        with self.assertRaises(ValueError):self.service.plan(self.game)

    def test_final_journal_failure_is_retryable_after_payload_is_gone(self):
        from game_library.game_uninstall import atomic_write
        self.service.confirm(self.game,self.service.inspect(self.game,self.folder));plan=self.service.plan(self.game)
        def fail(path,data):
            if str(path).endswith('-uninstall.json') and json.loads(data)['stage']=='files-removed':raise OSError('disk full')
            return atomic_write(path,data)
        with patch('game_library.game_uninstall.atomic_write',side_effect=fail):
            with self.assertRaises(OSError):self.service.execute(plan)
        self.assertFalse(self.folder.exists());self.assertEqual(len(self.library.games()),1)
        self.assertEqual(self.service.plan(self.game)['journal']['stage'],'payload-empty')
        self.service.execute(self.service.plan(self.game));self.assertEqual(self.library.games(),[])

    def test_capture_interruption_recovers_verified_staged_file(self):
        from game_library.game_uninstall import move_exclusive
        self.service.confirm(self.game,self.service.inspect(self.game,self.folder));plan=self.service.plan(self.game)
        def interrupt(source,destination,source_fd,destination_fd):
            move_exclusive(source,destination,source_fd,destination_fd)
            if source=='game.exe':raise OSError('interrupted after capture')
        with patch('game_library.game_uninstall.move_exclusive',side_effect=interrupt):
            with self.assertRaises(OSError):self.service.execute(plan)
        self.assertEqual(len(self.library.games()),1)
        self.service.execute(self.service.plan(self.game));self.assertEqual(self.library.games(),[])

    def test_tilde_shared_paths_follow_launch_expansion(self):
        with patch.dict(os.environ,{'HOME':str(self.root)}):
            other=self.library.new_game();other.update(title='Other',executable='~/Games/Fixture/bin/game.exe',working_dir='~/Games/Fixture');self.library.save(other)
            with self.assertRaisesRegex(ValueError,'Another library'):self.service.inspect(self.game,self.folder)
        self.assertTrue(self.exe.exists())

    def test_journal_directory_is_synced_before_terminal_removal_and_metadata_before_cleanup(self):
        from game_library.game_uninstall import atomic_write
        self.service.confirm(self.game,self.service.inspect(self.game,self.folder));plan=self.service.plan(self.game)
        receipt,journal=self.service._paths(self.game['id']);events=[];real_sync=os.fsync;real_rmdir=os.rmdir;real_unlink=os.unlink
        def sync(fd):
            info=os.fstat(fd);events.append(('sync',info.st_dev,info.st_ino));return real_sync(fd)
        def write(path,data):
            result=atomic_write(path,data)
            if path==journal:events.append(('stage',json.loads(data)['stage']))
            return result
        def remove(name,**kwargs):events.append(('rmdir',name));return real_rmdir(name,**kwargs)
        def unlink(path,**kwargs):events.append(('unlink',str(path)));return real_unlink(path,**kwargs)
        with patch('game_library.game_uninstall.atomic_write',side_effect=write),patch('os.fsync',side_effect=sync),patch('os.rmdir',side_effect=remove),patch('os.unlink',side_effect=unlink):
            self.service.execute(plan)
        info=receipt.parent.stat();journal_sync=('sync',info.st_dev,info.st_ino)
        empty=events.index(('stage','payload-empty'));terminal=next(i for i,event in enumerate(events) if event[0]=='rmdir' and str(event[1]).startswith('UmuTron-uninstall-'))
        self.assertIn(journal_sync,events[empty+1:terminal])
        info=self.library.path.parent.stat();meta_sync=('sync',info.st_dev,info.st_ino)
        cleanup=events.index(('unlink',str(journal)))
        self.assertIn(meta_sync,events[events.index(('stage','files-removed'))+1:cleanup])

    def test_first_use_receipt_directory_parent_is_durable_before_first_rename(self):
        from game_library.game_uninstall import move_exclusive
        events=[];real_sync=os.fsync;parent=self.library.root.stat();identity=(parent.st_dev,parent.st_ino)
        def sync(fd):
            info=os.fstat(fd);events.append(('sync',info.st_dev,info.st_ino));return real_sync(fd)
        def move(*args):events.append(('move',));return move_exclusive(*args)
        with patch('os.fsync',side_effect=sync),patch('game_library.game_uninstall.move_exclusive',side_effect=move):
            self.service.confirm(self.game,self.service.inspect(self.game,self.folder));self.service.execute(self.service.plan(self.game))
        self.assertIn(('sync',*identity),events[:events.index(('move',))])
