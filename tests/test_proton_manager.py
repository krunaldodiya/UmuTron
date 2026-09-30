import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import threading
import time
import unittest
from game_library.proton_manager import ProtonManager, extract, release_items


class ProtonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.archive=self.root/'source.tar.gz'
        with tarfile.open(self.archive,'w:gz') as t:
            item=tarfile.TarInfo('GE-Proton11-test/proton');data=b'#!/bin/sh\nexit 0\n';item.size=len(data);item.mode=0o755;t.addfile(item,io.BytesIO(data))
        self.release={'family':'GE-Proton','version':'GE-Proton11-test','name':'GE-Proton11-test.tar.gz','architecture':'x86_64','url':'https://github.com/GloriousEggroll/proton-ge-custom/releases/download/test/GE-Proton11-test.tar.gz','size':self.archive.stat().st_size,'digest':'sha256:'+hashlib.sha256(self.archive.read_bytes()).hexdigest(),'checksum_url':''}
    def wait(self,manager):
        deadline=time.monotonic()+4
        while manager.busy() and time.monotonic()<deadline:time.sleep(.01)
        self.assertFalse(manager.busy())
    def fake(self,url,path,limit,cancel,progress):
        if cancel.is_set():raise InterruptedError('cancelled')
        Path(path).write_bytes(self.archive.read_bytes());progress(self.archive.stat().st_size)
    def test_install_verified_and_never_overwrite(self):
        manager=ProtonManager(self.root/'manager',downloader=self.fake)
        self.assertEqual(manager.status(self.release)['state'],'Available')
        manager.install(self.release);self.wait(manager)
        self.assertEqual(manager.status(self.release)['state'],'Installed')
        self.assertTrue((Path(manager.status(self.release)['path'])/'proton').is_file())
        with self.assertRaises(ValueError):manager.install(self.release)
    def test_failure_cancel_and_duplicate_click(self):
        gate=threading.Event()
        def slow(url,path,limit,cancel,progress):
            gate.wait(2)
            if cancel.is_set():raise InterruptedError('cancelled')
            self.fake(url,path,limit,cancel,progress)
        manager=ProtonManager(self.root/'manager',downloader=slow);manager.install(self.release)
        with self.assertRaises(RuntimeError):manager.install(self.release)
        manager.cancel(self.release);gate.set();self.wait(manager)
        self.assertEqual(manager.status(self.release)['state'],'Cancelled')
        bad=dict(self.release,digest='sha256:'+'0'*64);manager.downloader=self.fake;manager.install(bad);self.wait(manager)
        self.assertEqual(manager.status(bad)['state'],'Failed')
        self.assertFalse(list(manager.tools.glob('.install-*')))
    def test_archive_traversal_external_links_and_devices_rejected(self):
        for name,link in [('../outside',None),('tool/link','../../escape'),('/absolute',None)]:
            archive=self.root/'bad.tar.gz'
            with tarfile.open(archive,'w:gz') as t:
                item=tarfile.TarInfo(name)
                if link:item.type=tarfile.SYMTYPE;item.linkname=link;t.addfile(item)
                else:item.size=1;t.addfile(item,io.BytesIO(b'x'))
            destination=self.root/'extract';destination.mkdir(exist_ok=True)
            with self.subTest(name=name),self.assertRaises(ValueError):extract(archive,destination,threading.Event())
        self.assertFalse((self.root/'outside').exists())
    def test_cached_paginated_releases_and_architecture(self):
        calls=[]
        asset={'name':self.release['name'],'size':self.release['size'],'digest':self.release['digest'],'browser_download_url':self.release['url']}
        arm=dict(asset,name='GE-Proton11-test-aarch64.tar.gz')
        payload=[{'tag_name':'GE-Proton11-test','assets':[asset,arm]}]
        def transport(url):calls.append(url);return payload
        manager=ProtonManager(self.root/'manager',transport=transport,arch='x86_64')
        self.assertEqual(len(manager.releases('GE-Proton')),1)
        manager.releases('GE-Proton');self.assertEqual(len(calls),1)
        manager.releases('GE-Proton',page=2);self.assertIn('page=2',calls[-1])
        manager.releases('GE-Proton',refresh=True);self.assertEqual(len(calls),3)
        self.assertEqual(release_items(payload,'GE-Proton','aarch64')[0]['architecture'],'aarch64')
        manager.arch='unknown'
        with self.assertRaises(ValueError):manager.releases('GE-Proton')

    def test_safe_internal_link_extracts_and_stale_stage_is_cleaned(self):
        with tarfile.open(self.archive,'w:gz') as t:
            data=b'runner';item=tarfile.TarInfo('GE-Proton11-test/bin/real');item.size=len(data);item.mode=0o755;t.addfile(item,io.BytesIO(data))
            link=tarfile.TarInfo('GE-Proton11-test/proton');link.type=tarfile.SYMTYPE;link.linkname='bin/real';t.addfile(link)
        self.release.update(size=self.archive.stat().st_size,digest='sha256:'+hashlib.sha256(self.archive.read_bytes()).hexdigest())
        manager=ProtonManager(self.root/'manager',downloader=self.fake)
        stale=manager.tools/'.install-interrupted';stale.mkdir();(stale/'partial').write_bytes(b'partial')
        manager.install(self.release);self.wait(manager)
        self.assertEqual(manager.status(self.release)['state'],'Installed')
        self.assertFalse(stale.exists())
        self.assertEqual((Path(manager.status(self.release)['path'])/'proton').read_bytes(),b'runner')
