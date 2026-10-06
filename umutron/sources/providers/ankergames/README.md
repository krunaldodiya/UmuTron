# AnkerGames source adapter

Provider ID: `ankergames`. Search uses the UmuTron downloads API with `link_type=magnet`; results use the existing `portable` strategy.

Keep source-specific matching in `provider.py`; shared HTTP/API handling belongs in `umutron/sources/base.py`. A portable strategy does not prove that a result is a verified loose game folder. Reported file size is not installed size or verified payload size. Never launch based on lookup alone; installation remains an explicit user action under the guarded installation contract.
