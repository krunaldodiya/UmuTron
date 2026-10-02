import os
import struct
import tempfile
import threading
import unittest
from pathlib import Path

from game_library.launcher import MARKER
from game_library.prefix_inventory import (
    RECIPES,
    directory_usage,
    inspect_prefix,
    pe_evidence,
    runtime_row,
)


def pe(path, arch='x64', version=(14, 0, 24212, 0), origin='native'):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = bytearray(2048)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 128)
    data[128:132] = b'PE\0\0'
    struct.pack_into('<HH', data, 132, 0x8664 if arch == 'x64' else 0x14c, 1)
    struct.pack_into('<H', data, 148, 0)
    data[152:160] = b'.rsrc\0\0\0'
    struct.pack_into('<II', data, 168, 1024, 512)
    if origin == 'builtin':
        data[64:80] = b'Wine builtin DLL'
    struct.pack_into('<IIII', data, 512, 0xfeef04bd, 0x10000,
                     version[0] * 65536 + version[1], version[2] * 65536 + version[3])
    publisher = ('Microsoft Corporation' if origin == 'native' else 'Wine project' if origin == 'builtin' else 'Unknown').encode('utf-16le')
    data[600:600 + len(publisher)] = publisher
    path.write_bytes(data)
    return path


def prefix_at(root, arch='x64', claim=True):
    prefix = root / 'prefix'
    (prefix / 'drive_c/windows/system32').mkdir(parents=True)
    (prefix / MARKER).write_text('fixture')
    text = '#arch=win64\n' if arch == 'x64' else '#arch=win32\n'
    if claim:
        for architecture in ('x64', 'x86'):
            text += '[Software\\\\Microsoft\\\\VisualStudio\\\\14.0\\\\VC\\\\Runtimes\\\\' + architecture + ']\n"Installed"=dword:00000001\n"Version"="14.42.34433.0"\n'
    (prefix / 'system.reg').write_text(text)
    return prefix


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prefix = prefix_at(self.root)
        self.game = {'id': 'fixture', 'launch': {'prefix': str(self.prefix), 'runner': '/missing', 'proton': '/missing'}}

    def test_not_created_inspection_has_no_side_effects(self):
        self.game['launch']['prefix'] = str(self.root / 'absent')
        info = inspect_prefix(self.game, self.root)
        self.assertEqual(info['state'], 'Not created')
        self.assertFalse((self.root / 'absent').exists())
        self.assertIn('Unknown', info['requirements'])

    def test_seeded_registry_builtin_and_broken_links_are_not_native(self):
        for dll in RECIPES['vc14-x64'].dlls:
            pe(self.prefix / 'drive_c/windows/system32' / dll, origin='builtin')
        folder = self.prefix / 'drive_c/windows/syswow64'
        folder.mkdir()
        for i in range(1290):
            (folder / f'removed-ge-{i}.dll').symlink_to('/missing/GE-Proton11-7/dll')
        info = inspect_prefix(self.game, self.root)
        self.assertEqual(info['usage']['broken_links'], 1290)
        self.assertEqual(info['runtimes'][0]['status'], 'Unknown')
        self.assertEqual(info['runtimes'][1]['status'], 'Unknown')
        self.assertTrue(info['builtins'])

    def test_native_2015_and_2019_versions_are_read_from_files(self):
        for version in ((14, 0, 24212, 0), (14, 29, 30139, 0)):
            for dll in RECIPES['vc14-x64'].dlls:
                pe(self.prefix / 'drive_c/windows/system32' / dll, version=version)
            info = inspect_prefix(self.game, self.root)
            row = next(row for row in info['runtimes'] if row['key'] == 'vc14-x64')
            self.assertEqual(row['status'], 'Installed')
            self.assertEqual(row['version'], '.'.join(map(str, version)))
            self.assertNotEqual(row['version'], '14.42.34433.0')

    def test_architecture_version_and_missing_members_produce_partial(self):
        req = RECIPES['vc14-x64']
        for dll in req.dlls:
            pe(self.prefix / 'drive_c/windows/system32' / dll)
        from game_library.prefix_inventory import registry
        sections, arch, okay = registry(self.prefix)
        def status():
            return runtime_row(req, self.prefix, arch, sections, okay, self.root)['status']
        self.assertEqual(status(), 'Installed')
        pe(self.prefix / 'drive_c/windows/system32' / req.dlls[0], arch='x86')
        self.assertEqual(status(), 'Partial')
        pe(self.prefix / 'drive_c/windows/system32' / req.dlls[0], version=(14, 0, 0, 0))
        self.assertEqual(status(), 'Partial')
        (self.prefix / 'drive_c/windows/system32' / req.dlls[0]).unlink()
        self.assertEqual(status(), 'Partial')

    def test_local_native_does_not_satisfy_prefix_requirement(self):
        exe = pe(self.root / 'game/game.exe')
        for dll in RECIPES['vc14-x64'].dlls:
            pe(exe.parent / dll)
        self.game['executable'] = str(exe)
        info = inspect_prefix(self.game, self.root)
        self.assertEqual(len(info['local']), 3)
        self.assertTrue(all(row['status'] != 'Installed' for row in info['runtimes']))

    def test_usage_no_mapped_disks_dedup_sparse_and_links(self):
        root = self.root / 'usage'
        root.mkdir()
        data = root / 'sparse'
        with data.open('wb') as stream:
            stream.seek(64 * 1024 * 1024)
            stream.write(b'x')
        before = directory_usage(root)
        os.link(data, root / 'hardlink')
        self.assertEqual(directory_usage(root)['allocated'], before['allocated'])
        external = self.root / 'external'
        external.mkdir()
        (external / 'large').write_bytes(b'x' * 100000)
        (root / 'linked').symlink_to(external, target_is_directory=True)
        drives = root / 'dosdevices'
        drives.mkdir()
        (drives / 'real-mapping').mkdir()
        (drives / 'real-mapping/file').write_bytes(b'x' * 100000)
        usage = directory_usage(root)
        self.assertLess(usage['allocated'], 50000)
        self.assertGreater(usage['apparent'], 64 * 1024 * 1024)
        self.assertEqual(usage['links'], 1)
        self.assertEqual(usage['skipped'], 1)
        self.assertFalse(directory_usage(root, limit=1)['complete'])
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(InterruptedError):
            directory_usage(root, cancel)

    def test_external_file_link_not_read_and_corrupt_file_unknown(self):
        file = pe(self.root / 'outside/native.dll')
        link = self.prefix / 'external.dll'
        link.symlink_to(file)
        self.assertEqual(pe_evidence(link, (self.prefix,))['origin'], 'Unknown')
        file.write_text('MZbroken')
        self.assertEqual(pe_evidence(file)['origin'], 'Unknown')
        file.unlink()
        self.assertEqual(pe_evidence(link)['origin'], 'Missing')


    def test_runner_version_comes_from_metadata_not_mutable_folder_name(self):
        runner = self.root / 'UMU-Latest'
        runner.mkdir()
        (runner / 'version').write_text('1774856027 UMU-Proton-10.0-4\n')
        self.game['launch']['proton'] = str(runner)
        info = inspect_prefix(self.game, self.root)
        self.assertEqual(info['runner_version'], 'UMU-Proton-10.0-4')
        (runner / 'version').unlink()
        self.assertIn('Unknown', inspect_prefix(self.game, self.root)['runner_version'])
