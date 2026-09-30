# Validation — version 0.1 preview

## Observed on Ubuntu 26.04

- 33 isolated standard-library unit tests pass.
- Native GTK/libadwaita GUI smoke test passes: Light/Dark appearance, compact library cards, details editing, local-only Save, explicit Steam account/preview/confirmation, sync to a temporary mock Steam folder, undo, ZIP import/export, filtering settings navigation, metadata-first Add Game, local-only Delete, and scrolling lower detail fields at 920×640.
- Native screenshots inspected in Light/Dark and detail views. Fixed an expanding header cover that originally squeezed the scroll viewport; added regression assertions for compact header height, useful viewport height and scrolling to lower fields.
- Live Steam search returned matching titles. Steam app 620 details returned title and portrait/landscape/hero/logo images. Data was used for an in-memory integration check, not saved to the user's library or repository.
- Application menu installer runs without root; desktop entry validates.
- Public repository contains source, synthetic test data and fictional demo artwork screenshots only.

## Safety and failure checks

- Metadata lookup ID stays separate from non-Steam launch ID.
- Relinking/renaming preserves an existing shortcut ID; missing mapped shortcuts reuse that ID.
- Duplicate executable matching updates rather than duplicates; ambiguous or already-owned matches are refused.
- Steam-running and file-change guards prevent unreviewed overwrite.
- Unrelated shortcuts and compatibility configuration remain unchanged in fixtures.
- Failed sync rolls back fixture files; interrupted sync/undo can be recovered through the backup journal.
- No-op previews still check for external shortcut changes. Failure recovery preserves concurrent external edits instead of overwriting them.
- Undo refuses subsequent external changes.
- ZIP import rejects path traversal and corrupted artwork checksums; provider credentials are excluded; restored mappings reset to unsynced.
- Provider requests are tested with controlled fixtures; authentication redirects are not followed. Private credentials are written with mode 0600 and never sent in query URLs.

## Limits, not acceptance claims

No real Steam library has been written by development or tests. Real Steam shortcut/artwork display is pending the user's explicit sync and review. IGDB and SteamGridDB adapters have contract/fixture tests but authenticated live requests remain unverified without the user's keys. Native GUI was exercised and screenshots inspected; a comprehensive screen-reader assessment was not performed. Tests show a nonfatal desktop-session IBUS connection warning; it did not prevent UI interactions.

The app is an initial working preview, not a claim of exhaustive compatibility. Keep Steam closed throughout actual sync/undo. Public Steam Store endpoints can change. Local credentials and ZIP backups are not encrypted. Normal application updates do not change the user's game files or Steam settings.
