"""Nonsecret catalog config fixtures; never load user config or credentials."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from game_library.catalog import configured_catalog, RemoteCatalog, UnconfiguredCatalog


class CatalogConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='umutron-catalog-config-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'catalog.json'

    def write(self, value): self.path.write_text(json.dumps(value))

    def test_persistent_https_config_and_no_network_during_resolution(self):
        self.write({'APP_BASE_URL': 'https://catalog.example.test'})
        with patch('game_library.catalog.api_request') as request:
            provider = configured_catalog({}, config_path=self.path)
        self.assertIsInstance(provider, RemoteCatalog); request.assert_not_called()
        self.assertEqual(provider.base, 'https://catalog.example.test')

    def test_primary_environment_config_and_legacy_precedence(self):
        self.write({'APP_BASE_URL': 'https://file.example.test'})
        self.assertEqual(configured_catalog({'APP_BASE_URL':'https://env.example.test'}, config_path=self.path).base, 'https://env.example.test')
        self.assertEqual(configured_catalog({'UMUTRON_CATALOG_URL':'https://legacy.example.test'}, config_path=self.path).base, 'https://file.example.test')
        self.assertIsInstance(configured_catalog({'APP_BASE_URL':''}, config_path=self.path), UnconfiguredCatalog)
        self.path.unlink()
        self.assertEqual(configured_catalog({'UMUTRON_CATALOG_URL':'https://legacy.example.test'}, config_path=self.path).base, 'https://legacy.example.test')

    def test_invalid_primary_file_never_falls_back(self):
        legacy = {'UMUTRON_CATALOG_URL':'https://legacy.example.test'}
        for value in ({'APP_BASE_URL':''}, {'APP_BASE_URL':None}, {'APP_BASE_URL':False},
                      {'APP_BASE_URL':'https://host.test/v1'}, {'APP_BASE_URL':'http://remote.test'},
                      {'APP_BASE_URL':'https://host.test', 'secret':'must-not-be-echoed'}, [], {}):
            self.write(value)
            provider = configured_catalog(legacy, config_path=self.path)
            self.assertIsInstance(provider, UnconfiguredCatalog)
            self.assertNotIn('must-not-be-echoed', provider.message)
        for contents in ('{', 'x' * 16385):
            self.path.write_text(contents)
            self.assertIsInstance(configured_catalog(legacy, config_path=self.path), UnconfiguredCatalog)

    def test_file_http_requires_explicit_environment_dev_opt_in(self):
        self.write({'APP_BASE_URL':'http://localhost:3000'})
        self.assertIsInstance(configured_catalog({}, config_path=self.path), UnconfiguredCatalog)
        self.assertEqual(configured_catalog({'UMUTRON_ALLOW_LOOPBACK_HTTP':'1'}, config_path=self.path).base, 'http://127.0.0.1:3000')

    def test_symlink_directory_and_fifo_are_rejected_without_blocking(self):
        target = Path(self.temp.name) / 'other.json'; target.write_text('{"APP_BASE_URL":"https://other.test"}')
        self.path.symlink_to(target)
        self.assertIsInstance(configured_catalog({}, config_path=self.path), UnconfiguredCatalog)
        self.path.unlink(); self.path.mkdir()
        self.assertIsInstance(configured_catalog({}, config_path=self.path), UnconfiguredCatalog)
        self.path.rmdir(); os.mkfifo(self.path)
        self.assertIsInstance(configured_catalog({}, config_path=self.path), UnconfiguredCatalog)

    def test_real_resolution_uses_xdg_config_and_injected_environment_stays_isolated(self):
        path = Path(self.temp.name) / 'game-library-launcher' / 'catalog.json'; path.parent.mkdir()
        path.write_text('{"APP_BASE_URL":"https://configured.example.test"}')
        with patch.dict('os.environ', {'XDG_CONFIG_HOME':self.temp.name}, clear=True):
            self.assertEqual(configured_catalog().base, 'https://configured.example.test')
            self.assertIsInstance(configured_catalog({}), UnconfiguredCatalog)


if __name__ == '__main__': unittest.main()
