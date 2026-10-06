"""Local cache and API-backed release discovery."""
import json
import os
from pathlib import Path
from urllib.parse import urlencode

from .base import build_search_queries, is_multipart_link, is_multipart_release
from .model import DownloadRelease
from .registry import source_registry
from ..providers import api_request


MAX_SEARCH_PAGES = 4


class DownloadSourceCache:
    def __init__(self, cache_file=None):
        if cache_file is None:
            root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'umutron'
            cache_file = root / 'source-releases-cache.json'
        self.path = Path(cache_file)
        self.data = {}
        self._load()

    def _load(self):
        if not self.path.is_file():
            return
        try:
            value = json.loads(self.path.read_text())
            if isinstance(value, dict):
                self.data = value
        except (OSError, ValueError):
            pass

    @staticmethod
    def _key(title, source_identity, base_url=None):
        identity = json.dumps(list(source_identity), ensure_ascii=True, separators=(',', ':'))
        origin = (base_url or '').strip().rstrip('/').lower()
        return f"origin:{origin}|{title.strip().lower()}|sources:{identity}"

    def get(self, title, source_identity, base_url=None):
        if not title:
            return None
        value = self.data.get(self._key(title, source_identity, base_url))
        if value is None:
            return None
        if value is False:
            return False
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            return None
        return [release for entry in value if (release := DownloadRelease.from_dict(entry))]

    def set(self, title, releases, source_identity, base_url=None):
        if not title:
            return
        key = self._key(title, source_identity, base_url)
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


def _request(base_url, path, params, transport):
    endpoint = f'{base_url.rstrip("/")}{path}?{urlencode(params)}'
    return transport(endpoint) if transport is not None else api_request(endpoint)


def _releases_from_response(payload, source_ids, provider_id=None):
    if (not isinstance(payload, dict) or not isinstance(payload.get('data'), list)
            or type(payload.get('has_more')) is not bool):
        raise ValueError('The download source API returned an invalid response.')
    releases = []
    for item in payload['data']:
        if not isinstance(item, dict):
            continue
        source_id = item.get('source_id')
        if not isinstance(source_id, str) or source_id not in source_ids:
            continue
        if provider_id is not None and source_id != provider_id:
            continue
        title = item.get('title')
        if not isinstance(title, str) or not title.strip():
            continue
        uris = item.get('uris')
        if not isinstance(uris, list):
            continue
        if is_multipart_release(title, uris):
            continue
        magnets = [uri for uri in uris
                   if isinstance(uri, str) and uri.startswith('magnet:') and len(uri) <= 1024
                   and not is_multipart_link(uri)][:2]
        if not magnets:
            continue
        source_name = source_ids[source_id]
        file_size = item.get('file_size')
        upload_date = item.get('upload_date')
        release_id = item.get('id')
        raw = {
            'source_id': source_id,
            'source_name': source_name,
            'title': title.strip()[:240],
            'file_size': file_size[:120] if isinstance(file_size, str) else 'Unknown size',
            'upload_date': upload_date[:80] if isinstance(upload_date, str) else None,
            'uris': magnets,
        }
        if isinstance(release_id, (str, int)) and not isinstance(release_id, bool):
            raw['id'] = str(release_id)[:160]
        releases.append(DownloadRelease(
            provider_id=source_id,
            provider_name=source_name,
            title=raw['title'],
            file_size=raw['file_size'],
            magnet=magnets[0],
            uris=magnets,
            upload_date=raw['upload_date'],
            raw=raw,
        ))
    return releases, payload['has_more']


def search_game_releases(base_url, title, transport=None, provider_id=None, force_refresh=False):
    if not isinstance(title, str) or not title.strip():
        return []
    title = title.strip()
    sources = source_registry.load_sources(base_url, transport=transport)
    source_ids = {source.id: source.name for source in sources}
    if not sources or (provider_id is not None and provider_id not in source_ids):
        return []
    source_identity = tuple((source.id, source.name) for source in sources)
    use_cache = provider_id is None
    cached = None if force_refresh or not use_cache else source_cache.get(
        title, source_identity, base_url)
    if cached is False:
        return []
    if cached is not None:
        return cached

    queries = []
    for candidate in build_search_queries(title):
        query = candidate.strip()[:120]
        if len(query) >= 2 and query not in queries:
            queries.append(query)
    wanted = {provider_id} if provider_id is not None else set(source_ids)
    found = {}
    for query in queries:
        for page in range(1, MAX_SEARCH_PAGES + 1):
            payload = _request(base_url, '/api/downloads',
                               {'q': query, 'page': page}, transport)
            results, has_more = _releases_from_response(payload, source_ids, provider_id)
            for release in results:
                identity = (release.provider_id, release.get('id'), release.title, release.magnet)
                found.setdefault(identity, release)
            if not has_more:
                break
            if page == MAX_SEARCH_PAGES:
                break
        if {release.provider_id for release in found.values()} >= wanted:
            break

    releases = list(found.values())
    if use_cache:
        source_cache.set(title, releases if releases else False, source_identity, base_url)
    return releases


def search_game_release(base_url, title, transport=None, provider_id=None, force_refresh=False):
    releases = search_game_releases(base_url, title, transport=transport,
                                    provider_id=provider_id, force_refresh=force_refresh)
    return releases[0] if releases else None
