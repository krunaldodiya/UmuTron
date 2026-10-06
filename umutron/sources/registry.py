"""Dynamic source configuration received from the UmuTron API."""
from dataclasses import dataclass
from threading import RLock

from ..providers import api_request


@dataclass(frozen=True)
class DownloadSource:
    id: str
    name: str


class SourceProviderRegistry:
    def __init__(self, sources=()):
        self._sources = {}
        self._disabled = set()
        self._lock = RLock()
        self.replace_sources(sources)

    @staticmethod
    def _source(value):
        if isinstance(value, DownloadSource):
            source = value
        elif isinstance(value, dict):
            source = DownloadSource(value.get('id', ''), value.get('name', ''))
        else:
            source = DownloadSource(getattr(value, 'id', ''), getattr(value, 'name', ''))
        if not isinstance(source.id, str) or not source.id.strip() or not isinstance(source.name, str) or not source.name.strip():
            raise ValueError('The source API returned an invalid source.')
        return DownloadSource(source.id.strip(), source.name.strip())

    def replace_sources(self, sources):
        if not isinstance(sources, (list, tuple)):
            raise ValueError('The source API returned an invalid source list.')
        values = {}
        for value in sources:
            source = self._source(value)
            if source.id in values:
                raise ValueError('The source API returned duplicate source IDs.')
            values[source.id] = source
        with self._lock:
            self._sources = values
            self._disabled.intersection_update(values)
        return self.providers()

    def load_sources(self, base_url, transport=None):
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError('The download source API is not configured.')
        endpoint = base_url.rstrip('/') + '/api/sources'
        payload = transport(endpoint) if transport is not None else api_request(endpoint)
        if not isinstance(payload, dict) or not isinstance(payload.get('sources'), list):
            raise ValueError('The download source API returned an invalid response.')
        sources = []
        seen = set()
        for value in payload['sources']:
            if not isinstance(value, dict):
                raise ValueError('The download source API returned an invalid source.')
            enabled = value.get('enabled', True)
            if type(enabled) is not bool:
                raise ValueError('The download source API returned an invalid source status.')
            source = self._source(value)
            if source.id in seen:
                raise ValueError('The download source API returned duplicate source IDs.')
            seen.add(source.id)
            if enabled:
                sources.append(source)
        return self.replace_sources(sources)

    def register(self, source):
        source = self._source(source)
        with self._lock:
            self._sources[source.id] = source

    def get(self, source_id):
        with self._lock:
            return self._sources.get(source_id)

    def set_enabled(self, source_id, enabled):
        with self._lock:
            if source_id not in self._sources:
                return
            if enabled:
                self._disabled.discard(source_id)
            else:
                self._disabled.add(source_id)

    def is_enabled(self, source_id):
        with self._lock:
            return source_id in self._sources and source_id not in self._disabled

    def apply_disabled_sources(self, disabled):
        with self._lock:
            self._disabled = set(disabled) & set(self._sources)

    def providers(self, only_enabled=False):
        with self._lock:
            return [source for source in self._sources.values()
                    if not only_enabled or source.id not in self._disabled]


source_registry = SourceProviderRegistry()
