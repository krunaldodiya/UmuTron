# FitGirl source adapter

Provider ID: `fitgirl`. Search uses the UmuTron downloads API with `link_type=magnet` and returns the API's stored release title, file-size label, magnet URI and upload date. FitGirl results use the `installer` strategy; they require explicit installer execution through the existing UMU/Proton installation flow. Filtering excludes patch-only records. API file size is a reported source value, not installed size or a verified payload size.

Keep source-specific matching/filtering in `provider.py`; shared HTTP/API handling belongs in `umutron/sources/base.py`. Never add provider credentials or execute a release during lookup.
