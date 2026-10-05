# Catalog entities — candidate on 0.4.33

This local delta is separate from installed Storage/detail 0.4.33. Release numbering and installation await joint API/native acceptance. No real library migration is performed.

The desktop accepts the additive backend contract from the independently reviewed backend candidate's CONTRACT.md and NATIVE-INTEGRATION.md. Browse/detail may provide `game_type: string | null` (up to 64 characters) and `platforms: {id,name}[]` (up to 100 distinct positive safe IDs, nonblank names up to 200 characters). Old responses/snapshots without these fields remain readable. Missing type displays Catalog entry; missing platforms add no compatibility claim. Known Bundle and Expanded Game labels distinguish same-title records without title-specific branches. PC (Microsoft Windows) is abbreviated only on cards; complete names remain in tooltips, detail and Game Info.

Game Info may display optional `relationships`:

| Field | Meaning |
| --- | --- |
| `bundles` | Containing bundles |
| `parent_game` | Related main game or bundle; not inferred as an original |
| `expanded_games` | Expanded versions of the selected record |
| `version_parent` | Main game of an edition |
| `bundle_contents` | Optional inverse result `{items,complete}` |
| `expanded_from` | Optional inverse result `{items,complete}` |

References contain exact IGDB ID/name. Lists are bounded to 100, IDs are unique within each list, and self references are rejected. Names are bounded to 1000 characters. Absence means unknown/not queried; complete false is visibly partial; an empty complete result says only that IGDB reported none. The desktop does not perform inverse queries, recursively prefetch references, infer ownership, or replace an entity with its parent. Explicit reference selection opens the existing detail route by exact ID. Closed or stale Game Info controls do nothing; weak callback ownership allows closed windows to release.

`In library` requires exact saved `{provider:"igdb",id:<selected ID>}` metadata. A verified shared Steam link produces Related saved entry, never membership. An explicit Open saved entry action opens a unique related UUID unchanged. Multiple related records open Library for manual selection. Explicit Add creates the separately tracked catalog record, preserves every existing record, and is idempotent for repeated/concurrent Add of that exact ID. Multiple exact saved copies still block automatic selection. Optional title-based detail lookups remain bounded discovery hints only. They cannot establish relationships from titles, replace current page metadata with older cached classification, or revive a departed route.

Opening an already-saved exact IGDB entry from Store also requests detail. The saved UUID, local metadata, artwork, Setup fields and primary action stay intact; only the catalog view is enriched. An open Game Info dialog updates in place. Pending mode/editor rebuilds resume with a new generation; leaving the selection or closing its dialog cannot revive it on completion. Old-schema results remain readable, cached responses identify offline data, and an unavailable request leaves local information/actions usable with a message in Game Info. Library/Home do not initiate this enrichment.

The candidate does not rewrite old Steam-only records or add new classification fields to persisted game records. Library/Home details continue to show their saved metadata; Store detail and Game Info use the selected catalog response. Existing Setup, manual installers, Play/Stop, one-game guard, Storage, Proton, transport configuration, artwork source validation, 24-item paging, total handling and request cap remain unchanged.

Backend fields come from `game_type.type,platforms.name`; directed detail fields are `bundles.name,parent_game.name,expanded_games.name,version_parent.name`. The backend supplies inverse lists; the desktop consumes them. See the [official IGDB Game documentation](https://api-docs.igdb.com/#game). The public production API may still lack the enrichment until separately deployed; local mocks and proposed-contract renders do not establish live provider results.
