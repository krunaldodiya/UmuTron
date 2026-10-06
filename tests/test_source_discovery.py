import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from umutron.sources.cache import DownloadSourceCache, search_game_releases
from umutron.sources.model import DownloadRelease
from umutron.sources.registry import DownloadSource, SourceProviderRegistry
from umutron.download_service import download_manager


SOURCES = [
    {'id': 'source-a', 'name': 'Source A', 'enabled': True},
    {'id': 'source-b', 'name': 'Source B', 'enabled': True},
    {'id': 'source-c', 'name': 'Source C', 'enabled': True},
    {'id': 'source-d', 'name': 'Source D', 'enabled': True},
    {'id': 'source-e', 'name': 'Source E', 'enabled': True},
]


def release(source_id, name, identity=None):
    sources_by_id = {source['id']: source['name'] for source in SOURCES}
    return {
        'id': identity or f'{source_id}-{name}',
        'source_id': source_id,
        'source_name': sources_by_id[source_id],
        'title': name,
        'file_size': '10 GB',
        'upload_date': '2026-01-01',
        'uris': [f'magnet:?xt=urn:btih:{source_id}-{name}'],
    }


class SourceDiscoveryTests(unittest.TestCase):
    def test_registry_replaces_sources_from_api_and_keeps_only_valid_local_disables(self):
        registry = SourceProviderRegistry((DownloadSource('old', 'Old source'),))
        registry.set_enabled('old', False)
        payload = {'sources': SOURCES}
        self.assertEqual(registry.load_sources('https://api.example', transport=lambda _: payload),
                         [DownloadSource(source['id'], source['name']) for source in SOURCES])
        self.assertEqual([source.id for source in registry.providers(only_enabled=True)],
                         [source['id'] for source in SOURCES])
        registry.set_enabled('source-c', False)
        registry.load_sources('https://api.example', transport=lambda _: payload)
        self.assertFalse(registry.is_enabled('source-c'))
        self.assertEqual(len(registry.providers()), 5)


    def test_api_disabled_sources_are_excluded_from_registry(self):
        registry = SourceProviderRegistry()
        payload = {'sources': [
            {'id': 'enabled', 'name': 'Enabled', 'enabled': True},
            {'id': 'disabled', 'name': 'Disabled', 'enabled': False},
        ]}
        registry.load_sources('https://api.example', transport=lambda _: payload)
        self.assertEqual([source.id for source in registry.providers()], ['enabled'])
        self.assertIsNone(registry.get('disabled'))


    def test_current_enabled_only_api_response_remains_usable(self):
        registry = SourceProviderRegistry()
        payload = {'sources': [
            {'id': 'source-a', 'name': 'Source A', 'url': 'https://feeds.example/a.json', 'is_protected': False},
        ]}
        self.assertEqual(registry.load_sources('https://api.example', transport=lambda _: payload),
                         [DownloadSource('source-a', 'Source A')])
    def test_search_queries_every_api_source_even_when_locally_disabled(self):
        registry = SourceProviderRegistry()
        releases = [release(source['id'], 'Game Edition') for source in SOURCES]
        calls = []

        def transport(url):
            parsed = urlparse(url)
            calls.append(url)
            if parsed.path.endswith('/api/sources'):
                return {'sources': SOURCES}
            self.assertEqual(parsed.path, '/api/downloads')
            return {'data': releases, 'has_more': False}

        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            with patch('umutron.sources.cache.source_registry', registry), \
                    patch('umutron.sources.cache.source_cache', cache):
                registry.load_sources('https://api.example', transport=lambda _: {'sources': SOURCES})
                registry.set_enabled('source-c', False)
                found = search_game_releases('https://api.example', 'Game', transport=transport)
                self.assertEqual([item.provider_id for item in found],
                                 [source['id'] for source in SOURCES])
                self.assertFalse(registry.is_enabled('source-c'))
                self.assertTrue(any('/api/sources' in url for url in calls))
                self.assertTrue(any('/api/downloads' in url for url in calls))
                repeated = search_game_releases('https://api.example', 'Game', transport=transport)
                self.assertEqual([item.provider_id for item in repeated],
                                 [source['id'] for source in SOURCES])
                self.assertEqual(sum('/api/downloads' in url for url in calls), 1)

    def test_search_reads_bounded_pages_until_all_sources_are_found(self):
        registry = SourceProviderRegistry()
        page_calls = []
        page_one = [release(source['id'], 'Game Edition') for source in SOURCES[:3]]
        page_two = [release(source['id'], 'Game Alternate') for source in SOURCES[3:]]

        def transport(url):
            parsed = urlparse(url)
            if parsed.path.endswith('/api/sources'):
                return {'sources': SOURCES}
            page = int(parse_qs(parsed.query)['page'][0])
            page_calls.append(page)
            return {'data': page_one if page == 1 else page_two, 'has_more': page == 1}

        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            with patch('umutron.sources.cache.source_registry', registry), \
                    patch('umutron.sources.cache.source_cache', cache):
                found = search_game_releases('https://api.example', 'Game', transport=transport)
        self.assertEqual(page_calls, [1, 2])
        self.assertEqual({item.provider_id for item in found}, {source['id'] for source in SOURCES})

    def test_force_refresh_bypasses_release_cache_and_uses_updated_api_data(self):
        registry = SourceProviderRegistry()
        current = [release('source-a', 'Old release')]

        def transport(url):
            parsed = urlparse(url)
            if parsed.path.endswith('/api/sources'):
                return {'sources': [SOURCES[0]]}
            return {'data': list(current), 'has_more': False}

        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            with patch('umutron.sources.cache.source_registry', registry), \
                    patch('umutron.sources.cache.source_cache', cache):
                self.assertEqual(search_game_releases('https://api.example', 'Game', transport=transport)[0].title,
                                 'Old release')
                current[:] = [release('source-a', 'Refreshed release')]
                self.assertEqual(search_game_releases('https://api.example', 'Game', transport=transport,
                                                      force_refresh=True)[0].title,
                                 'Refreshed release')
                self.assertEqual(search_game_releases('https://api.example', 'Game', transport=transport)[0].title,
                                 'Refreshed release')

    def test_cache_is_scoped_to_dynamic_source_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            identity = (('source-a', 'Source A'), ('source-b', 'Source B'))
            item = DownloadRelease('source-a', 'Source A', 'Edition', '10 GB', 'magnet:?xt=urn:btih:a')
            cache.set('Game', item, identity, 'https://api-one.example')
            cached = cache.get('Game', identity, 'https://api-one.example')
            assert isinstance(cached, list)
            self.assertEqual(cached[0].title, 'Edition')
            self.assertIsNone(cache.get('Game', identity, 'https://api-two.example'))

    def test_provider_filtered_query_does_not_cache_partial_source_results(self):
        registry = SourceProviderRegistry()
        rows = [release(source['id'], 'Game Edition') for source in SOURCES]
        download_calls = []

        def transport(url):
            parsed = urlparse(url)
            if parsed.path.endswith('/api/sources'):
                return {'sources': SOURCES}
            download_calls.append(url)
            return {'data': rows, 'has_more': False}

        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            with patch('umutron.sources.cache.source_registry', registry), \
                    patch('umutron.sources.cache.source_cache', cache):
                selected = search_game_releases('https://api.example', 'Game', transport=transport,
                                                provider_id='source-a')
                all_sources = search_game_releases('https://api.example', 'Game', transport=transport)
        self.assertEqual([item.provider_id for item in selected], ['source-a'])
        self.assertEqual({item.provider_id for item in all_sources}, {source['id'] for source in SOURCES})
        self.assertEqual(len(download_calls), 2)

    def test_unknown_release_does_not_auto_select_an_arbitrary_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            game_executable = folder / 'game.exe'
            game_executable.write_bytes(b'inert fixture')
            self.assertIsNone(download_manager.find_setup_exe(folder))
            installer = folder / 'setup.exe'
            installer.write_bytes(b'inert fixture')
            self.assertEqual(download_manager.find_setup_exe(folder), installer)

    def test_legacy_byxatab_adapter_remains_isolated_compatibility_code(self):
        from umutron.sources.providers.byxatab import ByXatabProvider

        provider = ByXatabProvider()
        repack = {'title': 'Game Repack'}
        portable = {'title': 'Game [Папка игры]'}
        self.assertEqual(provider.filter_candidates([repack, portable]), [portable])
        self.assertEqual(provider.get_install_strategy(portable), 'portable')
        self.assertEqual(provider.get_install_strategy(repack), 'installer')


if __name__ == '__main__':
    unittest.main()
