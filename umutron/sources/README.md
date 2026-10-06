# Download source adapters

Each provider lives in `providers/<provider-id>/` with its own adapter, package exports and provider notes. Keep matching rules and release strategy classification local to that provider. Shared title normalization, API search, release modeling, registry and cache code stay in this package root.

## Adding or changing a provider

1. Implement a `BaseSourceProvider` subclass in the provider's directory; use a stable provider ID matching the API's `source_name`.
2. Put only source-specific result filtering and installation-strategy classification in the adapter. Never execute or install from lookup code.
3. Register it in `providers/__init__.py`, expose it from the provider package, and add a `README.md` describing matching behavior and known payload limits.
4. Add deterministic tests with injected transport or fake providers. Do not contact real download APIs in unit tests.
5. Keep the UI's source list synchronized through `SourceProviderRegistry`; persisted disabled IDs are applied before discovery. Results and cache entries are scoped to the enabled provider set.

API `file_size` is only a provider-reported value. It is not installed size, archive verification, executable identity, ownership evidence or proof of readiness. Discovery must not receive library paths, credentials or launch settings. Actual installation remains a separate explicit action and must preserve the project's filesystem and operation-ownership guards.
