# Historical ByXatab adapter

This provider-specific adapter remains only for compatibility tests. The application discovers sources and release metadata from the configured public UmuTron API; it does not register this adapter, keep a provider roster, or use its title-based strategy classification. Shared API/cache behavior lives in `umutron/sources/`.

A title is not proof of archive contents, executable identity, ownership or readiness. Reported size is not installed size. Lookup never executes a release; installation and game execution remain explicit.