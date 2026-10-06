"""Local cache and compatibility entry points for source release search."""
import json
import os
from pathlib import Path

from .model import DownloadRelease
from .registry import source_registry


class DownloadSourceCache:
    def __init__(self, cache_file=None):
        if cache_file is None:
            root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'umutron'
            cache_file = root / 'source-releases-cache.json'
        self.path = Path(cache_file)
        self.legacy_path = self.path.parent / 'fitgirl-cache.json'
        self.data = {}
        self._load()

    def _load(self):
        if self.path.is_file():
            try:
                value = json.loads(self.path.read_text())
                if isinstance(value, dict):
                    self.data = value
            except (OSError, ValueError):
                pass
        elif self.legacy_path.is_file():
            try:
                legacy = json.loads(self.legacy_path.read_text())
                if isinstance(legacy, dict):
                    for key, value in legacy.items():
                        if isinstance(value, dict):
                            value.setdefault('provider_id', 'fitgirl')
                            value.setdefault('provider_name', 'FitGirl')
                            value.setdefault('install_strategy', 'installer')
                        self.data[key] = value
            except (OSError, ValueError):
                pass

    @staticmethod
    def _key(title, provider_ids):
        return f"{title.strip().lower()}|sources:{','.join(provider_ids)}"

    def get(self, title, provider_ids=None):
        if not title:
            return None
        if provider_ids is None:
            provider_ids = tuple(provider.id for provider in source_registry.providers())
        else:
            provider_ids = tuple(provider_ids)
        value = self.data.get(self._key(title, provider_ids))
        if value is None:
            # Legacy cache entries contain only one FitGirl release; use them
            # only for a FitGirl-only selection, never as complete multi-source results.
            legacy = self.data.get(title.strip().lower())
            if isinstance(legacy, dict) and provider_ids == ('fitgirl',):
                legacy.setdefault('provider_id', 'fitgirl')
                legacy.setdefault('provider_name', 'FitGirl')
                legacy.setdefault('install_strategy', 'installer')
                return [DownloadRelease.from_dict(legacy)]
            return None
        if value is False:
            return False
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            return None
        return [release for entry in value if (release := DownloadRelease.from_dict(entry))]

    def set(self, title, releases, provider_ids=None):
        if not title:
            return
        if provider_ids is None:
            provider_ids = tuple(provider.id for provider in source_registry.providers())
        else:
            provider_ids = tuple(provider_ids)
        key = self._key(title, provider_ids)
        if releases is False:
            self.data[key] = False
        elif isinstance(releases, DownloadRelease):
            self.data[key] = [releases.to_dict()]
        elif isinstance(releases, list):
            self.data[key] = [release.to_dict() if isinstance(release, DownloadRelease) else release
                              for release in releases]
        else:
            self.data[key] = []
        try:
            from ..library import atomic_write
            atomic_write(self.path, json.dumps(self.data, indent=2).encode())
        except (OSError, TypeError, ValueError):
            pass


source_cache = DownloadSourceCache()
fitgirl_cache = source_cache


def search_game_releases(base_url, title, api_key=None, transport=None, provider_id=None,
                         force_refresh=False):
    providers = source_registry.providers()
    if provider_id is not None:
        providers = [provider for provider in providers if provider.id == provider_id]
    provider_ids = tuple(provider.id for provider in providers)
    if not provider_ids:
        return []
    cached = None if force_refresh else source_cache.get(title, provider_ids)
    if cached is not None:
        return [] if cached is False else cached

    if provider_id is None:
        releases = source_registry.search_all(base_url, title, api_key=api_key, transport=transport)
    else:
        releases = providers[0].search(base_url, title, api_key=api_key, transport=transport)
    source_cache.set(title, releases if releases else False, provider_ids)
    return releases


def search_game_release(base_url, title, api_key=None, transport=None, provider_id=None,
                        force_refresh=False):
    releases = search_game_releases(base_url, title, api_key=api_key, transport=transport,
                                    provider_id=provider_id, force_refresh=force_refresh)
    return releases[0] if releases else None


def search_fitgirl_repack(base_url, title, api_key=None, transport=None):
    provider = source_registry.get('fitgirl')
    if provider is None:
        return []
    return provider.search(base_url, title, api_key=api_key, transport=transport)
