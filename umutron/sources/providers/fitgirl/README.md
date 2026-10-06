# Historical FitGirl adapter

This provider-specific adapter remains only for compatibility tests. The application discovers sources and release metadata from the configured public UmuTron API; it does not register this adapter, keep a provider roster, or use its strategy classification. Shared API/cache behavior lives in `umutron/sources/`.

Lookup never executes a release. Reported file size is not installed size or verified payload size. Do not add credentials to the desktop.