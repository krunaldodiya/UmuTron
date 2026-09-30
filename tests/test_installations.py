from pathlib import Path
import tempfile
import time
import unittest
from game_library.library import Library
from game_library.launcher import Launcher,defaults
from game_library.installations import Installations,validate_installation


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.lib=Library(self.root/'library');self.launcher=Launcher(self.lib.root);self.service=Installations(self.lib,self.launcher)
        self.runner=self.root/'runner';self.runner.write_text('#!/usr/bin/python3\nprint("fixture installer completed",flush=True)\n');self.runner.chmod(0o700)
        self.proton=self.root/'Proton';self.proton.mkdir();(self.proton/'proton').write_text('inert')
        (self.root/'files').mkdir();self.setup=self.root/'files/setup.exe';self.setup.write_text('inert setup')
        self.exe=self.root/'files/game.exe';self.exe.write_text('inert game')
        self.game=self.lib.new_game();self.game.update(title='Installer fixture',launch={'runner':str(self.runner),'proton':str(self.proton)},installation={'mode':'installer','installer':str(self.setup)})
    def finish(self):
        deadline=time.monotonic()+6
        while self.launcher.active() and time.monotonic()<deadline:time.sleep(.02)
        self.assertFalse(self.launcher.active())
    def test_installer_requires_confirmation_and_preserves_runtime_on_reopen(self):
        saved=self.service.start(self.game);self.finish()
        with self.assertRaisesRegex(ValueError,'Confirm'):self.launcher.start(saved)
        reopened=Library(self.lib.root);service=Installations(reopened,Launcher(reopened.root));saved=reopened.games()[0]
        self.assertEqual(service.status(saved)['phase'],'Select installed executable')
        saved['executable']=str(self.setup)
        with self.assertRaisesRegex(ValueError,'not its setup'):service.confirm(saved)
        saved['executable']=str(self.exe);confirmed=service.confirm(saved)
        self.lib.set_default_proton('GE-Latest')
        settings=defaults(confirmed,self.lib.root)
        self.assertEqual(settings['prefix'],saved['installation']['prefix']);self.assertEqual(settings['proton'],str(self.proton))
        self.launcher.start(confirmed);self.finish()
        request=__import__('json').loads((self.lib.root/'launch-request.json').read_text())
        self.assertEqual(request['argv'][1],str(self.exe));self.assertNotEqual(request['argv'][1],str(self.setup))
    def test_failure_cancel_retry_keep_installed_files_and_block_other_operations(self):
        self.runner.write_text('#!/usr/bin/python3\nimport sys\nsys.exit(8)\n')
        saved=self.service.start(self.game);self.finish();self.assertEqual(self.service.status(saved)['phase'],'Failed')
        prefix=Path(saved['installation']['prefix']);(prefix/'keep.save').write_text('keep')
        self.runner.write_text('#!/usr/bin/python3\nimport time\ntime.sleep(30)\n')
        retry=self.service.start(saved)
        try:
            with self.assertRaises(RuntimeError):self.service.start(saved)
            with self.assertRaises(RuntimeError):self.launcher.start(dict(self.game,installation={},executable=str(self.exe)))
            deadline=time.monotonic()+3
            while not self.launcher.current().get('supervisor_pid') and time.monotonic()<deadline:time.sleep(.02)
            self.launcher.stop(saved['id']);self.finish()
        finally:
            if self.launcher.active():self.launcher.stop(saved['id']);self.finish()
        self.assertEqual(self.service.status(retry)['phase'],'Cancelled');self.assertEqual((prefix/'keep.save').read_text(),'keep')
        self.runner.write_text('#!/usr/bin/python3\npass\n');again=self.service.start(retry);self.finish()
        self.assertEqual(again['installation']['prefix'],str(prefix));self.assertEqual((prefix/'keep.save').read_text(),'keep')
    def test_installed_mode_does_not_run_setup_and_archive_retains_continuity(self):
        self.game.update(executable=str(self.exe),installation={'mode':'installed'})
        self.lib.save(self.game);self.launcher.start(self.game);self.finish()
        self.assertFalse((self.lib.root/'installation-sessions').exists())
        for config in ({'mode':'bad'},{'confirmed':1},{'installer':'a\x00'},{'session_id':'bad'}):
            with self.assertRaises(ValueError):validate_installation(config)

    def test_automatic_runner_resolution_and_interrupted_resume_are_persistent(self):
        self.game['launch']['proton']='GE-Latest'
        self.runner.write_text('#!/usr/bin/python3\nimport os,subprocess,sys\nos.environ["PROTONPATH"]='+repr(str(self.proton))+'\np=subprocess.Popen([sys.executable,"-c","import time;time.sleep(.8)"])\np.wait()\n')
        saved=self.service.start(self.game);self.finish()
        self.assertEqual(self.service.status(saved)['proton'],str(self.proton))
        saved['executable']=str(self.exe);confirmed=self.service.confirm(saved)
        self.assertEqual(confirmed['launch']['proton'],str(self.proton))
        archive=self.root/'portable.zip';self.lib.export_zip(archive);restored=Library(self.root/'restored');restored.import_zip(archive)
        self.assertEqual(restored.games()[0]['installation']['prefix'],confirmed['installation']['prefix'])
        # A stale preparing record is resumable, never proof of installation.
        import json
        record=self.lib.root/'installation-sessions'/(saved['id']+'.json')
        value=json.loads(record.read_text());value['state']='Preparing';record.write_text(json.dumps(value))
        saved['installation']['confirmed']=False
        self.assertEqual(self.service.status(saved)['phase'],'Interrupted')

    def test_immediate_cancel_during_preparation_is_safe_and_retryable(self):
        self.runner.write_text('#!/usr/bin/python3\nimport time\ntime.sleep(30)\n')
        saved=self.service.start(self.game)
        self.launcher.stop(saved['id']);self.finish()
        self.assertEqual(self.service.status(saved)['phase'],'Cancelled')
        self.runner.write_text('#!/usr/bin/python3\npass\n');saved=self.service.start(saved);self.finish()
        self.assertEqual(self.service.status(saved)['phase'],'Select installed executable')
