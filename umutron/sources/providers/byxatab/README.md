# ByXatab source adapter

Provider ID: `byxatab`. Search uses the UmuTron downloads API with `link_type=magnet`. Patch-only records are excluded; titles marked `Папка игры` are preferred as loose preinstalled folders. Those records use the `portable` strategy; explicit repack titles use the `installer` strategy. Ambiguous titles currently retain the existing portable default.

Keep source-specific matching and strategy classification in `provider.py`; shared HTTP/API handling belongs in `umutron/sources/base.py`. A release label or title is not proof of archive contents, executable identity, installation ownership or readiness. Never launch based on lookup alone; installation must remain an explicit detail-page action and obey the guarded local installation contract.
