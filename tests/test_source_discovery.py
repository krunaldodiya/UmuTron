import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, quote, urlparse

from umutron.sources.cache import DownloadSourceCache, _releases_from_response, search_game_releases
from umutron.sources.model import DownloadRelease, filter_source_links
from umutron.sources.registry import DownloadSource, SourceProviderRegistry
from umutron.download_service import download_manager
from umutron.sources.base import is_multipart_link, is_multipart_release, is_multipart_title


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
        'uris': [f'magnet:?xt=urn:btih:{source_id}-{quote(name)}'],
    }


class PublicLinkFilterTests(unittest.TestCase):
    def test_public_releases_keep_each_provided_link_and_direct_only_editions(self):
        mixed = release('source-a', 'Game')
        mixed['uris'] = [
            'https://example.com/Game.torrent',
            'https://example.com/Game.zip',
            'magnet:?xt=urn:btih:game',
            'https://example.com/secret.zip?token=hidden',
            'https://127.0.0.1/internal.exe',
        ]
        direct_only = release('source-a', 'Direct')
        direct_only['uris'] = ['https://example.com/Direct.torrent']
        results, has_more = _releases_from_response(
            {'data': [mixed, direct_only], 'has_more': False},
            {'source-a': 'Source A'},
        )
        self.assertFalse(has_more)
        self.assertEqual([entry.title for entry in results], ['Game', 'Direct'])
        self.assertEqual(results[0].uris, mixed['uris'])
        self.assertEqual(results[0].magnet, 'magnet:?xt=urn:btih:game')
        self.assertEqual(results[1].uris, direct_only['uris'])
        self.assertEqual(results[1].magnet, '')


class SourceDiscoveryTests(unittest.TestCase):
    def test_registry_replaces_sources_from_api(self):
        registry = SourceProviderRegistry((DownloadSource('old', 'Old source'),))
        payload = {'sources': SOURCES}
        self.assertEqual(registry.load_sources('https://api.example', transport=lambda _: payload),
                         [DownloadSource(source['id'], source['name']) for source in SOURCES])
        self.assertEqual([source.id for source in registry.providers()],
                         [source['id'] for source in SOURCES])


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
    def test_search_uses_one_bounded_backend_request_and_caches_result(self):
        registry = SourceProviderRegistry()
        releases = [release(source['id'], 'Game Edition') for source in SOURCES]
        calls = []

        def transport(url):
            parsed = urlparse(url)
            calls.append(url)
            self.assertEqual(parsed.path, '/api/downloads')
            self.assertEqual(parse_qs(parsed.query)['page'], ['1'])
            return {'data': releases, 'has_more': False}

        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            with patch('umutron.sources.cache.source_registry', registry), \
                    patch('umutron.sources.cache.source_cache', cache):
                found = search_game_releases('https://api.example', 'Game', transport=transport)
                self.assertEqual([item.provider_id for item in found],
                                 [source['id'] for source in SOURCES])
                repeated = search_game_releases('https://api.example', 'Game', transport=transport)
                self.assertEqual([item.provider_id for item in repeated],
                                 [source['id'] for source in SOURCES])
        self.assertEqual(len(calls), 1)

    def test_link_filter_uses_already_fetched_releases(self):
        registry = SourceProviderRegistry()
        magnet_release = release('source-a', 'Game')
        direct_release = release('source-b', 'Game')
        direct_release['uris'] = ['https://downloads.example/game.zip']
        calls = []

        def transport(url):
            calls.append(url)
            return {'data': [magnet_release, direct_release], 'has_more': False}

        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            with patch('umutron.sources.cache.source_registry', registry), \
                    patch('umutron.sources.cache.source_cache', cache):
                releases = search_game_releases('https://api.example', 'Game', transport=transport)

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [filter_source_links(release.uris, 'p2p') for release in releases],
            [[magnet_release['uris'][0]], []],
        )
        self.assertEqual(
            [filter_source_links(release.uris, 'direct') for release in releases],
            [[], direct_release['uris']],
        )
        with self.assertRaises(ValueError):
            filter_source_links(releases[0].uris, 'invalid')

    def test_search_aggregates_every_bounded_page_and_title_variant(self):
        registry = SourceProviderRegistry()
        calls = []

        def transport(url):
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            query = params['q'][0]
            page = int(params['page'][0])
            calls.append((query, page))
            if query == 'Grand Theft Auto V' and page == 1:
                return {'data': [release('source-a', 'GTA V')], 'has_more': True}
            if query == 'Grand Theft Auto V' and page == 2:
                return {'data': [release('source-b', 'GTA V')], 'has_more': False}
            if query == 'Grand Theft Auto 5' and page == 1:
                return {'data': [release('source-c', 'GTA 5')], 'has_more': False}
            self.fail(f'unexpected request: {query!r} page {page}')

        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            with patch('umutron.sources.cache.source_registry', registry), \
                    patch('umutron.sources.cache.source_cache', cache):
                found = search_game_releases('https://api.example', 'Grand Theft Auto V', transport=transport)

        self.assertEqual([item.provider_id for item in found], ['source-a', 'source-b', 'source-c'])
        self.assertEqual(calls, [
            ('Grand Theft Auto V', 1),
            ('Grand Theft Auto V', 2),
            ('Grand Theft Auto 5', 1),
        ])

    def test_search_uses_title_variant_only_when_exact_query_has_no_results(self):
        registry = SourceProviderRegistry()
        queries = []

        def transport(url):
            parsed = urlparse(url)
            query = parse_qs(parsed.query)['q'][0]
            queries.append(query)
            return {
                'data': [] if query == 'Grand Theft Auto V' else [release('source-a', 'GTA 5')],
                'has_more': False,
            }

        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            with patch('umutron.sources.cache.source_registry', registry), \
                    patch('umutron.sources.cache.source_cache', cache):
                found = search_game_releases('https://api.example', 'Grand Theft Auto V', transport=transport)
        self.assertEqual(queries, ['Grand Theft Auto V', 'Grand Theft Auto 5'])
        self.assertEqual([item.title for item in found], ['GTA 5'])

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


    def test_multipart_link_identification(self):
        split_uris = [
            'https://example.com/games/release.part1.rar',
            'https://example.com/games/release.part02.rar',
            'https://example.com/games/release.part003.rar',
            'https://example.com/games/release.part1.exe',
            'https://example.com/games/release.7z.001',
            'https://example.com/games/release.zip.001',
            'https://example.com/games/release.rar.001',
            'https://example.com/games/release.r00',
            'https://example.com/games/release.r01',
            'https://example.com/games/release.z01',
            'https://example.com/games/release.001',
            'magnet:?xt=urn:btih:abc&dn=Game.Release.part1.rar',
            'magnet:?xt=urn:btih:abc&dn=Game.Release.7z.001',
        ]
        for uri in split_uris:
            self.assertTrue(is_multipart_link(uri), f'Expected split link: {uri}')

        valid_uris = [
            'https://example.com/games/release.zip',
            'https://example.com/games/release.rar',
            'https://example.com/games/release.7z',
            'https://example.com/games/release.iso',
            'https://example.com/games/setup.exe',
            'magnet:?xt=urn:btih:abc&dn=Game.Complete.Edition',
            'magnet:?xt=urn:btih:abc&dn=The+Witcher+3+Wild+Hunt',
        ]
        for uri in valid_uris:
            self.assertFalse(is_multipart_link(uri), f'Expected valid link: {uri}')

    def test_multipart_title_identification(self):
        split_titles = [
            'Game Name (Part 1 of 4)',
            'Game Name [Part 1/5]',
            'Game Name - CD 1 of 2',
            'Game Name - Disc 1/3',
            'Game.Name.part1.rar',
            'Game.Name.7z.001',
        ]
        for title in split_titles:
            self.assertTrue(is_multipart_title(title), f'Expected split title: {title}')

        valid_titles = [
            'The Last of Us Part 1',
            '.hack//Infection Part 1',
            'Mario Party Megamix',
            'A Fold Apart',
            'Game Name v1.001',
            'Cyberpunk 2077: Ultimate Edition',
            'The Witcher 3: Wild Hunt - Complete Edition',
        ]
        for title in valid_titles:
            self.assertFalse(is_multipart_title(title), f'Expected valid title: {title}')

    def test_search_game_releases_preserves_multipart_entries_for_picker(self):
        registry = SourceProviderRegistry()
        items = [
            {
                'id': 'full-game',
                'source_id': 'source-a',
                'source_name': 'Source A',
                'title': 'Complete Adventure',
                'file_size': '20 GB',
                'upload_date': '2026-01-01',
                'uris': ['magnet:?xt=urn:btih:complete-adventure'],
            },
            {
                'id': 'split-title',
                'source_id': 'source-a',
                'source_name': 'Source A',
                'title': 'Complete Adventure [Part 1 of 3]',
                'file_size': '7 GB',
                'upload_date': '2026-01-01',
                'uris': ['magnet:?xt=urn:btih:part-one-title'],
            },
            {
                'id': 'split-magnet',
                'source_id': 'source-a',
                'source_name': 'Source A',
                'title': 'Adventure Chunk',
                'file_size': '5 GB',
                'upload_date': '2026-01-01',
                'uris': ['magnet:?xt=urn:btih:chunk&dn=Adventure.part1.rar'],
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            with patch('umutron.sources.cache.source_registry', registry), \
                    patch('umutron.sources.cache.source_cache', cache):
                registry.load_sources('https://api.example', transport=lambda _: {'sources': SOURCES})
                def transport(url):
                    if '/api/sources' in url:
                        return {'sources': SOURCES}
                    return {'data': items, 'has_more': False}

                results = search_game_releases(
                    'https://api.example',
                    'Adventure',
                    transport=transport,
                    force_refresh=True,
                )
        self.assertEqual([result.title for result in results],
                         ['Complete Adventure', 'Complete Adventure [Part 1 of 3]', 'Adventure Chunk'])
        self.assertEqual(results[0].magnet, 'magnet:?xt=urn:btih:complete-adventure')

if __name__ == '__main__':
    unittest.main()
