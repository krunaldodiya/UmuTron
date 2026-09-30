# Product and interface specification

## Scope

Manage non-Steam game metadata locally and sync manually to Steam. Existing purchased Steam games are outside editing scope. Never launch a game, alter its files (including steam_appid.txt), choose a compatibility tool, or change a Proton prefix.

## Screens

1. Library: header with search, Add Game, backup menu and appearance menu. Responsive cover cards show title and Not synced / Changes pending / Synced status. A helpful empty state offers Add Game. Include an accessible list option.
2. Add Game: choose executable, search a name or store ID, review matching covers/titles/release dates, select a match, preview and save. Metadata matching must not execute or inspect game binaries.
3. Details: artwork hero, title and status; tabs for Overview, Artwork and Steam settings. Overview contains editable description, release date, developers, publishers and genres. Steam settings includes editable executable, working directory and arguments. Missing files show a Relink action without deleting metadata.
4. Sync preview: list exact additions/updates, selected Steam account and artwork changes. Explicit confirmation is required. Steam must be fully closed; never close it automatically. Errors leave local work intact.
5. Backup and restore: ZIP export; import preview with duplicate/conflict choices. Restoration never syncs automatically. Missing game paths can be repaired later.

## Appearance and usability

Light, Dark and Follow System modes, persisted locally. Prefer native GTK/libadwaita styling and controls. Do not force a dark-only palette. Keyboard navigation, meaningful focus order, readable contrast and labelled icon actions are required. Status must include text, not color alone. Network work runs outside the UI thread with loading, retry, empty and error states. Prevent duplicate operations. Keep library navigation fast by caching thumbnails and preserving scroll position.

Save only affects the local library. Save & Sync saves then opens the sync preview. Sync to Steam handles already saved changes. No background or automatic Steam synchronization.

## Identity and data safety

Each entry has a stable local UUID. The Steam store ID used to look up metadata is separate from the non-Steam shortcut ID used to launch and track a game. Changing a title or executable must retain an existing shortcut ID. Detect existing shortcuts before adding duplicates. Preserve unrelated shortcuts and compatibility settings.

Before Steam writes, keep restorable backups and validate existing files. Refuse malformed input rather than overwrite it. Undo must detect subsequent Steam changes before restoring. Development uses temporary fixture libraries, never the owner's live library.

ZIP backups contain metadata, artwork and portable application settings only. Exclude binaries, saves, Steam credentials and account authentication. Validate archive paths, sizes and schema. Offer merge/replace conflict previews; never blindly extract an archive. Imported Steam mappings require review for the destination account.

## Architecture

Native Python GTK 4/libadwaita UI with separate local-library, metadata-provider, archive and Steam adapters. Core modules must remain testable without a display or Steam installation. Store full metadata locally; standard Steam shortcuts do not support description/release-info display. Missing remote artwork is an explicit supported state. Public source and tests must contain no personal paths, credentials or downloaded game artwork.
