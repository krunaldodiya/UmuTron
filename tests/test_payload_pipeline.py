import tempfile
import unittest
from pathlib import Path
from umutron.payload_pipeline import (
    InstallerType, PayloadKind, classify_payload, detect_installer_engine,
    get_silent_installer_arguments, rank_game_executables, stage_portable_game,
)
from umutron.installations import validate_installation
from umutron.download_service import download_manager


class PayloadPipelineTests(unittest.TestCase):
    def test_classify_portable_loose_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'Game_Data').mkdir()
            (folder / 'Game.exe').write_bytes(b'MZ' + b'\x00' * 200)
            (folder / 'unityplayer.dll').write_bytes(b'dll')

            info = classify_payload(folder)
            self.assertEqual(info.kind, PayloadKind.PORTABLE_LOOSE)

    def test_classify_installer_loose_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'setup.exe').write_bytes(b'MZ' + b'Inno Setup' + b'\x00' * 100)
            (folder / 'data1.bin').write_bytes(b'bin data')

            info = classify_payload(folder)
            self.assertEqual(info.kind, PayloadKind.INSTALLER_LOOSE)
            self.assertEqual(info.installer_exe, folder / 'setup.exe')

    def test_rank_game_executables_excludes_auxiliary_and_ranks_best_match(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            bin_dir = folder / 'bin' / 'x64'
            bin_dir.mkdir(parents=True)
            redist = folder / '_redist'
            redist.mkdir()

            # Create dummy binaries
            (folder / 'unins000.exe').write_bytes(b'uninstaller' * 1000)
            (folder / 'UnityCrashHandler64.exe').write_bytes(b'crash' * 1000)
            (redist / 'vcredist_x64.exe').write_bytes(b'redist' * 50000)
            (folder / 'launcher_stub.exe').write_bytes(b'stub' * 100)
            game_bin = bin_dir / 'witcher3.exe'
            game_bin.write_bytes(b'witcher game executable' * 100000)

            ranked = rank_game_executables(folder, title='The Witcher 3: Wild Hunt')
            self.assertGreaterEqual(len(ranked), 1)
            self.assertEqual(ranked[0], game_bin)
            self.assertNotIn(folder / 'unins000.exe', ranked)
            self.assertNotIn(folder / 'UnityCrashHandler64.exe', ranked)
            self.assertNotIn(redist / 'vcredist_x64.exe', ranked)

    def test_stage_portable_game_unwraps_single_subfolder_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as temp:
            staging_root = Path(temp) / 'staging' / 'job123'
            inner_game = staging_root / 'Cyberpunk 2077'
            bin_dir = inner_game / 'bin' / 'x64'
            bin_dir.mkdir(parents=True)
            exe = bin_dir / 'Cyberpunk2077.exe'
            exe.write_bytes(b'cyberpunk game binary' * 1000)

            dest_dir = Path(temp) / 'games' / 'Cyberpunk 2077'

            staged = stage_portable_game(staging_root, dest_dir)
            self.assertEqual(staged.resolve(), dest_dir.resolve())
            self.assertTrue((dest_dir / 'bin' / 'x64' / 'Cyberpunk2077.exe').is_file())
            self.assertFalse(staging_root.exists(), 'Staging directory should be cleaned up after staging')

    def test_download_manager_combination_one_loose_portable_workflow(self):
        with tempfile.TemporaryDirectory() as temp:
            download_dir = Path(temp) / 'downloads' / 'game1'
            download_dir.mkdir(parents=True)
            (download_dir / 'ForzaHorizon5.exe').write_bytes(b'forza binary' * 10000)
            (download_dir / 'data').mkdir()
            (download_dir / 'data' / 'assets.dat').write_bytes(b'data')

            dest_dir = Path(temp) / 'installed_games' / 'Forza Horizon 5'

            payload = download_manager.inspect_payload(download_dir)
            self.assertEqual(payload.kind, PayloadKind.PORTABLE_LOOSE)

            staged_folder = download_manager.stage_portable(download_dir, dest_dir)
            main_exe = download_manager.detect_main_executable(staged_folder, 'Forza Horizon 5')
            self.assertIsNotNone(main_exe)
            assert main_exe is not None
            self.assertEqual(main_exe.name, 'ForzaHorizon5.exe')
            self.assertTrue(main_exe.is_file())
            self.assertFalse(download_dir.exists())

    def test_detect_installer_engine_and_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            inno = folder / 'inno_setup.exe'
            inno.write_bytes(b'MZ' + b'...' + b'Inno Setup SetupLdr' + b'\x00' * 100)
            self.assertEqual(detect_installer_engine(inno), InstallerType.INNO)
            inno_args = get_silent_installer_arguments(InstallerType.INNO, Path('/target/game'))
            self.assertIn('/VERYSILENT', inno_args)
            self.assertIn('/DIR=/target/game', inno_args)

            nsis = folder / 'nsis_setup.exe'
            nsis.write_bytes(b'MZ' + b'...' + b'NullsoftInst' + b'\x00' * 100)
            self.assertEqual(detect_installer_engine(nsis), InstallerType.NSIS)
            nsis_args = get_silent_installer_arguments(InstallerType.NSIS, Path('/target/game'))
            self.assertIn('/S', nsis_args)
            self.assertIn('/D=/target/game', nsis_args)

            msi = folder / 'package.msi'
            msi.write_bytes(b'msi data')
            self.assertEqual(detect_installer_engine(msi), InstallerType.MSI)
            msi_args = get_silent_installer_arguments(InstallerType.MSI, Path('/target/game'))
            self.assertIn('/qn', msi_args)
            self.assertIn('TARGETDIR=/target/game', msi_args)

    def test_validate_installation_accepts_silent_arguments(self):
        config = {
            'mode': 'installer',
            'installer': '/games/setup.exe',
            'arguments': ['/VERYSILENT', '/DIR=C:\\Game'],
        }
        validate_installation(config)

    def test_download_manager_combination_two_loose_installer_workflow(self):
        with tempfile.TemporaryDirectory() as temp:
            download_dir = Path(temp) / 'downloads' / 'game2'
            download_dir.mkdir(parents=True)
            setup_exe = download_dir / 'setup.exe'
            setup_exe.write_bytes(b'MZ' + b'Inno Setup' + b'\x00' * 100)
            (download_dir / 'data1.bin').write_bytes(b'bin data')

            dest_dir = Path(temp) / 'installed_games' / 'Game Two'

            payload = download_manager.inspect_payload(download_dir)
            self.assertEqual(payload.kind, PayloadKind.INSTALLER_LOOSE)
            self.assertEqual(payload.installer_exe, setup_exe)
            self.assertEqual(payload.installer_type, InstallerType.INNO)

            silent_args = download_manager.get_silent_args(payload.installer_type, dest_dir)
            self.assertIn('/VERYSILENT', silent_args)
            self.assertIn(f'/DIR={dest_dir}', silent_args)


    def test_download_manager_combination_three_archive_portable_workflow(self):
        import zipfile
        with tempfile.TemporaryDirectory() as temp:
            download_dir = Path(temp) / 'downloads' / 'game3'
            download_dir.mkdir(parents=True)
            zip_path = download_dir / 'game_portable.zip'

            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('GameFolder/Game.exe', b'MZ' + b'\x00' * 500)
                zf.writestr('GameFolder/data.pak', b'pak data')

            dest_dir = Path(temp) / 'installed_games' / 'Game Three'

            payload = download_manager.inspect_payload(download_dir)
            self.assertEqual(payload.kind, PayloadKind.ARCHIVE)
            self.assertEqual(payload.container, zip_path)

            extract_dir = download_dir / '.extracted'
            self.assertTrue(download_manager.extract_container(payload.container, extract_dir))

            inner_payload = download_manager.inspect_payload(extract_dir)
            self.assertEqual(inner_payload.kind, PayloadKind.PORTABLE_LOOSE)

            staged_folder = download_manager.stage_portable(extract_dir, dest_dir)
            main_exe = download_manager.detect_main_executable(staged_folder, 'Game Three')
            self.assertIsNotNone(main_exe)
            assert main_exe is not None
            self.assertEqual(main_exe.name, 'Game.exe')

    def test_download_manager_combination_four_archive_installer_workflow(self):
        import zipfile
        with tempfile.TemporaryDirectory() as temp:
            download_dir = Path(temp) / 'downloads' / 'game4'
            download_dir.mkdir(parents=True)
            zip_path = download_dir / 'scene_release.iso'

            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('setup.exe', b'MZ' + b'Inno Setup' + b'\x00' * 500)
                zf.writestr('data.bin', b'bin data')
                zf.writestr('CODEX/steam_api64.dll', b'crack dll')

            payload = download_manager.inspect_payload(download_dir)
            self.assertEqual(payload.kind, PayloadKind.ARCHIVE)
            self.assertEqual(payload.container, zip_path)

            extract_dir = download_dir / '.extracted'
            self.assertTrue(download_manager.extract_container(payload.container, extract_dir))

            inner_payload = download_manager.inspect_payload(extract_dir)
            self.assertEqual(inner_payload.kind, PayloadKind.INSTALLER_LOOSE)
            self.assertIsNotNone(inner_payload.installer_exe)
            self.assertIsNotNone(inner_payload.crack_dir)
            assert inner_payload.crack_dir is not None
            self.assertEqual(inner_payload.crack_dir.name, 'CODEX')

    def test_combination_five_direct_download_archive_to_portable_workflow(self):
        import zipfile
        with tempfile.TemporaryDirectory() as temp:
            download_dir = Path(temp) / 'downloads' / 'game5'
            download_dir.mkdir(parents=True)
            archive_path = download_dir / 'SteamRip_Direct_Game.zip'

            with zipfile.ZipFile(archive_path, 'w') as zf:
                zf.writestr('Game_Root/DirectGame.exe', b'MZ' + b'\x00' * 500)
                zf.writestr('Game_Root/game.dat', b'assets')

            dest_dir = Path(temp) / 'installed_games' / 'Direct Game'

            # Step 1: Download completes -> single archive on disk
            payload = download_manager.inspect_payload(download_dir)
            self.assertEqual(payload.kind, PayloadKind.ARCHIVE)
            self.assertEqual(payload.container, archive_path)

            # Step 2: Extract container
            extract_dir = download_dir / '.extracted'
            self.assertTrue(download_manager.extract_container(payload.container, extract_dir))

            # Step 3: Classify extracted payload -> portable
            inner_payload = download_manager.inspect_payload(extract_dir)
            self.assertEqual(inner_payload.kind, PayloadKind.PORTABLE_LOOSE)

            # Step 4: Stage portable game into final destination
            staged_folder = download_manager.stage_portable(extract_dir, dest_dir)
            main_exe = download_manager.detect_main_executable(staged_folder, 'Direct Game')
            self.assertIsNotNone(main_exe)
            assert main_exe is not None
            self.assertEqual(main_exe.name, 'DirectGame.exe')
            self.assertTrue((dest_dir / 'DirectGame.exe').is_file())

    def test_combination_six_direct_download_archive_to_silent_installer_workflow(self):
        import zipfile
        with tempfile.TemporaryDirectory() as temp:
            download_dir = Path(temp) / 'downloads' / 'game6'
            download_dir.mkdir(parents=True)
            archive_path = download_dir / 'GOG_Installer_Setup.zip'

            with zipfile.ZipFile(archive_path, 'w') as zf:
                zf.writestr('setup.exe', b'MZ' + b'Inno Setup' + b'\x00' * 500)
                zf.writestr('setup-1.bin', b'bin data')

            dest_dir = Path(temp) / 'installed_games' / 'GOG Game'

            # Step 1: Download completes -> single archive on disk
            payload = download_manager.inspect_payload(download_dir)
            self.assertEqual(payload.kind, PayloadKind.ARCHIVE)
            self.assertEqual(payload.container, archive_path)

            # Step 2: Extract container
            extract_dir = download_dir / '.extracted'
            self.assertTrue(download_manager.extract_container(payload.container, extract_dir))

            # Step 3: Classify extracted payload -> installer
            inner_payload = download_manager.inspect_payload(extract_dir)
            self.assertEqual(inner_payload.kind, PayloadKind.INSTALLER_LOOSE)
            self.assertEqual(inner_payload.installer_type, InstallerType.INNO)

            # Step 4: Resolve silent arguments
            silent_args = download_manager.get_silent_args(inner_payload.installer_type, dest_dir)
            self.assertIn('/VERYSILENT', silent_args)
            self.assertIn(f'/DIR={dest_dir}', silent_args)

if __name__ == '__main__':
    unittest.main()
