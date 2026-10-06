"""Provider registration and all-source discovery orchestration."""
from .providers import default_providers


class SourceProviderRegistry:
    def __init__(self, providers=None):
        self._providers = {}
        self._disabled = set()
        for provider in default_providers() if providers is None else providers:
            self.register(provider)

    def register(self, provider):
        self._providers[provider.id] = provider

    def get(self, provider_id):
        return self._providers.get(provider_id)

    def set_enabled(self, provider_id, enabled):
        if enabled:
            self._disabled.discard(provider_id)
        else:
            self._disabled.add(provider_id)

    def is_enabled(self, provider_id):
        return provider_id not in self._disabled

    def apply_disabled_sources(self, disabled):
        self._disabled = set(disabled) & set(self._providers)

    def providers(self, only_enabled=False):
        providers = sorted(self._providers.values(), key=lambda provider: provider.priority)
        return [provider for provider in providers if self.is_enabled(provider.id)] if only_enabled else providers

    def search_all(self, base_url, title, api_key=None, transport=None):
        releases = []
        seen = set()
        for provider in self.providers():
            try:
                for release in provider.search(base_url, title, api_key=api_key, transport=transport):
                    identity = (release.provider_id, release.title, release.magnet)
                    if identity not in seen:
                        seen.add(identity)
                        releases.append(release)
            except Exception:
                continue
        return releases


source_registry = SourceProviderRegistry()
