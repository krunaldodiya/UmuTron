"""API-backed download source discovery and release contracts."""
from .base import build_search_queries, is_multipart_link, is_multipart_release, normalize_title
from .cache import DownloadSourceCache, search_game_release, search_game_releases, source_cache
from .model import DownloadRelease, parse_size_bytes
from .registry import DownloadSource, SourceProviderRegistry, source_registry

__all__ = [
    'DownloadRelease',
    'DownloadSource',
    'DownloadSourceCache',
    'SourceProviderRegistry',
    'build_search_queries',
    'is_multipart_link',
    'is_multipart_release',
    'normalize_title',
    'parse_size_bytes',
    'search_game_release',
    'search_game_releases',
    'source_cache',
    'source_registry',
]
