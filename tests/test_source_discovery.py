import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from umutron.sources.cache import DownloadSourceCache, search_game_releases
from umutron.sources.model import DownloadRelease
from umutron.sources.registry import SourceProviderRegistry


class FakeProvider:
    def __init__(self, provider_id, priority, releases):
        self.id = provider_id
        self.name = provider_id.title()
        self.priority = priority
        self.releases = releases
        self.calls = 0

    def search(self, *_args, **_kwargs):
        self.calls += 1
        return list(self.releases)


def release(provider_id, name):
    return DownloadRelease(provider_id, provider_id.title(), name, '10 GB',
                           f'magnet:?xt=urn:btih:{provider_id}-{name}')


class SourceDiscoveryTests(unittest.TestCase):
    def test_registry_searches_all_providers_regardless_of_enabled_state(self):
        first = FakeProvider('first', 10, [release('first', 'Edition A')])
        second = FakeProvider('second', 20, [release('second', 'Edition B')])
        third = FakeProvider('third', 30, [release('third', 'Edition C')])
        registry = SourceProviderRegistry((third, first, second))

        found = registry.search_all('https://api.example', 'Game')
        self.assertEqual([item.provider_id for item in found], ['first', 'second', 'third'])

        registry.set_enabled('second', False)
        found = registry.search_all('https://api.example', 'Game')
        self.assertEqual([item.provider_id for item in found], ['first', 'second', 'third'])
        self.assertEqual([first.calls, second.calls, third.calls], [2, 2, 2])

    def test_persisted_disabled_source_set_replaces_registry_state(self):
        first = FakeProvider('first', 10, [])
        second = FakeProvider('second', 20, [])
        registry = SourceProviderRegistry((first, second))
        registry.apply_disabled_sources(['second', 'unknown'])
        self.assertEqual([provider.id for provider in registry.providers(only_enabled=True)], ['first'])
        registry.apply_disabled_sources([])
        self.assertEqual([provider.id for provider in registry.providers(only_enabled=True)], ['first', 'second'])

    def test_byxatab_prefers_preinstalled_release_and_classifies_repack(self):
        from umutron.sources.providers.byxatab import ByXatabProvider

        provider = ByXatabProvider()
        candidates = [
            {'title': 'Game Repack'},
            {'title': 'Game [Папка игры]'},
            {'title': 'Game patch from v1.0'},
            {'title': 'Game патч'},
        ]
        self.assertEqual(provider.filter_candidates(candidates), [candidates[1]])
        self.assertEqual(provider.get_install_strategy(candidates[1]), 'portable')
        self.assertEqual(provider.get_install_strategy(candidates[0]), 'installer')

    def test_search_cache_covers_all_sources_independent_of_enabled_state(self):
        first = FakeProvider('first', 10, [release('first', 'First release')])
        second = FakeProvider('second', 20, [release('second', 'Second release')])
        registry = SourceProviderRegistry((first, second))
        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            with patch('umutron.sources.cache.source_registry', registry), \
                    patch('umutron.sources.cache.source_cache', cache):
                all_results = search_game_releases('https://api.example', 'Game')
                self.assertEqual([item.provider_id for item in all_results], ['first', 'second'])
                self.assertEqual([first.calls, second.calls], [1, 1])

                registry.set_enabled('second', False)
                repeated_results = search_game_releases('https://api.example', 'Game')
                self.assertEqual([item.provider_id for item in repeated_results], ['first', 'second'])
                self.assertEqual([first.calls, second.calls], [1, 1])

    def test_force_refresh_bypasses_cache_and_replaces_full_source_results(self):
        first = FakeProvider('first', 10, [release('first', 'Old release')])
        second = FakeProvider('second', 20, [])
        registry = SourceProviderRegistry((first, second))
        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            with patch('umutron.sources.cache.source_registry', registry), \
                    patch('umutron.sources.cache.source_cache', cache):
                self.assertEqual(search_game_releases('https://api.example', 'Game')[0].title,
                                 'Old release')
                first.releases = [release('first', 'Refreshed release')]
                self.assertEqual(search_game_releases(
                    'https://api.example', 'Game', force_refresh=True)[0].title,
                    'Refreshed release')
                self.assertEqual(first.calls, 2)
                self.assertEqual(search_game_releases('https://api.example', 'Game')[0].title,
                                 'Refreshed release')

    def test_legacy_single_release_cache_round_trips(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            item = release('fitgirl', 'Legacy entry')
            cache.set('Game', item, ('fitgirl',))
            self.assertEqual(cache.get('Game', ('fitgirl',))[0].title, 'Legacy entry')
            self.assertIs(cache.get('Game', ('fitgirl', 'dodi')), None)

    def test_legacy_fitgirl_only_cache_is_not_treated_as_complete_multi_source_result(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = DownloadSourceCache(Path(temp) / 'releases.json')
            cache.data['game'] = {'title': 'Legacy FitGirl release', 'file_size': '10 GB',
                                  'magnet': 'magnet:?xt=urn:btih:legacy'}
            self.assertIsNone(cache.get('Game', ('fitgirl', 'dodi')))
            self.assertEqual(cache.get('Game', ('fitgirl',))[0].provider_id, 'fitgirl')



if __name__ == '__main__':
    unittest.main()
