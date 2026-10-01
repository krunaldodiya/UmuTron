import json
from pathlib import Path
import tempfile
import time
import unittest
from game_library.library import Library, digest
from game_library.launcher import preparation_progress, Launcher, build_command, discover, defaults, validate_settings


class LaunchTests(unittest.TestCase):
    def test_runtime_progress_observed_bytes_and_unknown_total(self):
        with tempfile.TemporaryDirectory() as directory:
            part=Path(directory)/'runtime.tar.gz.parts';part.write_bytes(b'x'*1024)
            record={'state':'Downloading runtime','logs':['Downloading runtime.tar.gz...',f'Writing: {part}']}
            self.assertEqual(preparation_progress(record),{'stage':'Downloading runtime.tar.gz...','bytes':1024})
            part.unlink();self.assertIsNone(preparation_progress(record)['bytes'])
            self.assertEqual(preparation_progress({'state':'Preparing','logs':[]})['stage'],'Preparing')

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.lib=Library(self.root/'library')
        self.game=self.lib.new_game(); self.game.update(title='Fixture', executable=str(self.root/'games'/'game ; $.exe'))
        Path(self.game['executable']).parent.mkdir()
        Path(self.game['executable']).write_text('inert')
        self.runner=self.root/'runner'; self.runner.write_text('#!/usr/bin/python3\nimport sys,time\nprint("download runtime",flush=True)\ntime.sleep(.15)\nprint("waitforexitandrun",flush=True)\ntime.sleep(.2)\n'); self.runner.chmod(0o700)
        self.proton=self.root/'Proton'; self.proton.mkdir(); (self.proton/'proton').write_text('inert')
        self.game['launch']={'runner':str(self.runner),'proton':str(self.proton),'prefix':'','arguments':['a b','$(touch no)','--x']}

    def test_argv_env_and_no_shell_interpolation(self):
        argv,cwd,env=build_command(self.game,self.lib.root,{'HOME':str(self.root),'DISPLAY':':1','SECRET_TOKEN':'never','GAMEID':'wrong','STORE':'steam','SteamAppId':'123'})
        self.assertEqual(argv,[str(self.runner),self.game['executable'],'a b','$(touch no)','--x'])
        self.assertEqual(cwd,str(self.root/'games')); self.assertNotIn('SECRET_TOKEN',env)
        for key in ('GAMEID','STORE','SteamAppId'): self.assertNotIn(key,env)
        self.assertEqual(env['PROTONPATH'],str(self.proton)); self.assertFalse(Path(env['WINEPREFIX']).exists())

    def test_missing_and_unsafe_paths(self):
        for key,value in [('runner','/missing'),('proton','/missing'),('prefix',str(self.root/'games'/'game ; $.exe'))]:
            copy=json.loads(json.dumps(self.game)); copy['launch'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): build_command(copy,self.lib.root)
        Path(self.game['executable']).unlink()
        with self.assertRaises(ValueError): build_command(self.game,self.lib.root)

    def test_existing_foreign_prefix_is_not_reused(self):
        prefix=self.root/'foreign';prefix.mkdir();(prefix/'system.reg').write_text('private')
        self.game['launch']['prefix']=str(prefix)
        with self.assertRaises(ValueError): build_command(self.game,self.lib.root)
        self.assertEqual((prefix/'system.reg').read_text(),'private')

    def test_schema_and_legacy_zip_do_not_execute_or_change_identity(self):
        legacy=self.lib.new_game();legacy.pop('launch',None);legacy['title']='Old';self.lib.save(legacy)
        self.lib.mark_synced(legacy['id'],'/fixture',456)
        loaded=self.lib.games()[0];before=digest(loaded);loaded['launch']=self.game['launch'];self.lib.save(loaded)
        self.assertEqual(digest(loaded),before);self.assertEqual(self.lib.status(loaded),'Synced')
        archive=self.root/'archive.zip';self.lib.export_zip(archive)
        other=Library(self.root/'restored');other.import_zip(archive)
        self.assertEqual(other.games()[0]['launch'],self.game['launch']);self.assertEqual(other.games()[0]['id'],legacy['id'])
        self.assertFalse((self.lib.root/'prefixes').exists())
        for settings in ({'arguments':'bad'},{'runner':'x\x00'},{'sudo':True},{'arguments':[1]}):
            with self.assertRaises(ValueError):validate_settings(settings)

    def test_lifecycle_duplicate_and_prefix_creation_only_on_play(self):
        launcher=Launcher(self.lib.root);launcher.start(self.game)
        with self.assertRaises(RuntimeError):launcher.start(self.game)
        deadline=time.monotonic()+4
        while launcher.active() and time.monotonic()<deadline:time.sleep(.02)
        state=launcher.snapshot(self.game['id'])
        self.assertEqual(state['state'],'Finished');self.assertEqual(state['code'],0)
        self.assertTrue((Path(defaults(self.game,self.lib.root)['prefix'])/'.metadata-manager-prefix').exists())
        self.assertIn('download runtime','\n'.join(state['logs']))
        self.assertFalse((self.root/'no').exists())

    def test_nonzero_and_spawn_failure_are_visible(self):
        self.runner.write_text('#!/usr/bin/python3\nimport sys\nsys.exit(7)\n')
        launcher=Launcher(self.lib.root);launcher.start(self.game)
        deadline=time.monotonic()+3
        while launcher.active() and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(launcher.snapshot(self.game['id'])['state'],'Error')
        self.assertEqual(launcher.snapshot(self.game['id'])['code'],7)
        self.runner.write_text('not executable format')
        launcher.start(self.game)
        while launcher.active() and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(launcher.snapshot(self.game['id'])['state'],'Error')

    def test_discovery_and_bounded_logs(self):
        found=discover(self.root)
        self.assertIsInstance(found['protons'],list)
        launcher=Launcher(self.lib.root)
        self.runner.write_text('#!/usr/bin/python3\nfor _ in range(1000): print("x"*5000)\n')
        launcher.start(self.game);deadline=time.monotonic()+15
        while launcher.active() and time.monotonic()<deadline:time.sleep(.02)
        self.assertFalse(launcher.active())
        logs=launcher.snapshot(self.game['id'])['logs']
        self.assertLessEqual(len(logs),200);self.assertTrue(all(len(line)<=2000 for line in logs))

    def test_cross_instance_and_cross_game_guard_then_stop(self):
        self.runner.write_text('#!/usr/bin/python3\nimport time\nprint("waitforexitandrun",flush=True)\ntime.sleep(30)\n')
        first=Launcher(self.lib.root);other=Launcher(self.lib.root);first.start(self.game)
        second=self.lib.new_game();second.update(self.game);second['id']=self.lib.new_game()['id']
        with self.assertRaises(RuntimeError):other.start(second)
        deadline=time.monotonic()+3
        while not first.current().get('supervisor_pid') and time.monotonic()<deadline:time.sleep(.02)
        other.stop(self.game['id'])
        while first.active() and time.monotonic()<deadline+3:time.sleep(.02)
        self.assertFalse(first.active());self.assertEqual(first.snapshot(self.game['id'])['state'],'Stopped')

    def test_wrapper_exit_still_tracks_detached_child(self):
        child=self.root/'child.py';child.write_text('import time\ntime.sleep(30)\n')
        self.runner.write_text('#!/usr/bin/python3\nimport subprocess,sys\nsubprocess.Popen([sys.executable,'+repr(str(child))+'],start_new_session=True)\n')
        launcher=Launcher(self.lib.root);launcher.start(self.game)
        time.sleep(.4)
        self.assertTrue(launcher.active())
        launcher.stop(self.game['id']);deadline=time.monotonic()+5
        while launcher.active() and time.monotonic()<deadline:time.sleep(.03)
        self.assertFalse(launcher.active())

    def test_running_detected_without_umu_log_marker_while_wrapper_lives(self):
        self.runner.write_text('#!/usr/bin/python3\nimport subprocess,time\nprint("fsync: up and running.",flush=True)\np=subprocess.Popen(['+repr(self.game['executable'])+',"30"],executable="/bin/sleep")\np.wait()\n')
        launcher=Launcher(self.lib.root);launcher.start(self.game)
        try:
            deadline=time.monotonic()+3
            while launcher.snapshot(self.game['id'])['state']!='Running' and time.monotonic()<deadline:time.sleep(.02)
            self.assertEqual(launcher.snapshot(self.game['id'])['state'],'Running')
            self.assertTrue(launcher.active())
        finally:
            launcher.stop(self.game['id'])
            deadline=time.monotonic()+5
            while launcher.active() and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(launcher.snapshot(self.game['id'])['state'],'Stopped')
