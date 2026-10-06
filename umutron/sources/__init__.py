"""Multi-source game release discovery."""
from .base import BaseSourceProvider, build_search_queries, normalize_title
from .cache import (
    DownloadSourceCache,
    fitgirl_cache,
    search_fitgirl_repack,
    search_game_release,
    search_game_releases,
    source_cache,
)
from .model import DownloadRelease, parse_size_bytes
from .providers import AnkerGamesProvider, ByXatabProvider, DODIProvider, FitGirlProvider
from .registry import SourceProviderRegistry, source_registry

__all__ = [
    'AnkerGamesProvider',
    'BaseSourceProvider',
    'ByXatabProvider',
    'DODIProvider',
    'DownloadRelease',
    'DownloadSourceCache',
    'FitGirlProvider',
    'SourceProviderRegistry',
    'build_search_queries',
    'fitgirl_cache',
    'normalize_title',
    'parse_size_bytes',
    'search_fitgirl_repack',
    'search_game_release',
    'search_game_releases',
    'source_cache',
    'source_registry',
]
