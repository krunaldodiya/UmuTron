# DODI source adapter

Provider ID: `dodi`. Search uses the UmuTron downloads API with `link_type=magnet` and excludes patch-only records. Results use the `installer` strategy and remain subject to explicit UMU/Proton installation confirmation.

Keep source-specific matching/filtering in `provider.py`; shared HTTP/API handling belongs in `umutron/sources/base.py`. Reported API file size is not installed size or verified payload size. Never add credentials or execute a release during lookup.
