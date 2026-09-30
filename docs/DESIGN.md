# Standalone game library and launcher

## Contract

Manage installed-game executables, metadata and artwork; Play explicitly through UMU and Proton. No game-client account/library is required. No shortcut synchronization, compatibility mapping edits or client-library writes. Keep third-party runtime/legal attribution accurate.

## Interface

Home: compact cards with 0/3–3/3 readiness count, title and Play/Stop. Details: full checklist (metadata, executable, direct launch), Overview, Artwork, Game files and Direct Play tabs. Metadata lookup starts with IGDB search or manual entry. Settings contains General backup/restore/appearance, Providers, and Proton Manager.

Save/import/metadata selection are local data operations. Play requires saved settings and a visible launch review. Only explicit Play executes the runner. Stop warns about unsaved in-game progress. A strict shared launch lock blocks duplicate or cross-game launches. The active entry retains Stop through navigation; other Play controls explain which game is active. UI remains responsive during launch, output and downloads. Demo Play is always disabled.

## Process and launch safety

Validated argv, cwd and allowlisted environment; never shell expansion or root execution. Direct arguments are a list, distinct from preserved legacy argument text. Catalog IDs never become UMU GAMEID/STORE identifiers. Default prefix is dedicated to the local UUID. Existing unrelated prefixes are refused. No modifications/deletion of game files or saves by the app.

A Linux subreaper supervisor holds the launch lock until owned descendants end. Detached children are adopted and tracked by PID/start time. Stop signals only verified descendants and escalates after a grace interval. No killall or shared wineserver control. Session state permits app reconnect after an unexpected desktop exit. Normal close asks users to finish/stop first.

## Runners

Use installed runners or UMU automatic tokens. Default selection is an app preference; per-game overrides are separate. Official GE-Proton/UMU-Proton release pages are cached, paginated and architecture-filtered. Available is distinct from Installed. Explicit installs run off the UI thread, provide progress/cancel/retry, verify published hashes, enforce bounded extraction and finalize atomically. No runner replacement/removal is supported. Downloads, cache and prefixes stay out of portable metadata ZIPs.

## Compatibility and preservation

Version-1 library schema gains optional validated launch settings. Historical metadata/identity fields remain accepted; direct launch edits are excluded from legacy sync digests. Migration copies validated data/artwork/credentials to new branded directories while preserving originals. Old ZIPs remain importable; import clears legacy machine mapping and never executes anything. No games or game-client settings are migrated, erased or reconfigured.

## Verification

Tests remain isolated. Exercise argv/environment boundaries, legacy libraries/archives, prefix ownership, rapid/concurrent launch attempts, crash/exit/Stop, detached descendants, instance locks, release/cache/pagination, hashes, cancellation, archive escapes and native UI/navigation. Do not launch real games during development. Document unverified compatibility instead of promising universal game support.
