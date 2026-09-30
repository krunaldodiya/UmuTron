# Validation — version 0.3.1

Validated on Ubuntu 26.04, 2026-09-30, with system Python and native GTK/libadwaita.

## Final checks

- All 37 isolated regression tests pass.
- Python compilation and Ruff undefined/unused-code checks pass.
- Native GUI smoke passes: read-only detail, hero/cover/logo, modal Save/Cancel, metadata-first search/select/save/detail with artwork and no launch configuration, optional manual fallback cancellation, subsequent executable/shortcut/installer configuration, harmless installer execution and executable confirmation, advanced settings/reset, scrolling, default public metadata and missing-credential provider switching, active operation controls, ZIP recovery and Proton Manager.
- Private-session D-Bus tray integration passes: registration, host detection/loss, Show Launcher, activation and Exit menu.
- Separate-process instance test passes: the second launch activates the first instance and exits without launching a game or installer.
- Live credential-free public Steam search and details lookup passed for Portal 2. No account/client is required.

## Preservation and lifecycle

Temporary inert runners exercise completed/nonzero installer runs, cancellation including initial preparation, retry, reopen recovery, executable confirmation, pinned prefix/runner continuity and duplicate/cross-instance launch rejection. Installer exit alone leaves selection pending. Play rejects setup executables and unconfirmed installations. Cancel never deletes installed files. Stop addresses only verified app-owned process identities; detached descendants remain tracked.

Native modal Cancel preserves saved metadata/art references and launch overrides. ZIP/library tests retain UUIDs, artwork hashes, legacy records and optional installation context. Backups exclude binaries, saves, prefixes, credentials and journals. No real game, downloaded repack installer or new license agreement was run/accepted for validation.

Close hides only with a registered tray host; otherwise it minimizes. Reopening reuses the existing window. Host loss restores accessibility. Active explicit Exit warns and permits cancellation; confirmed Exit leaves the owned supervisor operation running, recoverable on reopen. It does not stop unrelated processes.

## Remaining acceptance boundaries

Real Windows installer compatibility, gameplay and real desktop tray-menu visual acceptance remain user checks. Authenticated IGDB/SteamGridDB requests and full upstream runner downloads are covered by fixtures rather than credentialed live calls. Accessibility labels/tooltips are checked, not a comprehensive accessibility audit. GTK focus and deprecated test-API warnings occurred without test failures; the private-bus instance test emits portal warnings because it isolates the normal session.

Forced OS/supervisor termination is outside graceful cancellation guarantees. Mutable external runner files can change independently of the app. Backups of game data/prefixes remain separate from library ZIPs.

## Installed delivery

User-level installation and desktop-entry validation passed. All installed Python modules match final source bytes. The existing library/artwork snapshot (existing files) was unchanged by installation; saves, prefixes and game files were not touched. Version 0.3.1 was opened normally with no startup errors in its journal. The current desktop reports a registered tray host and the app StatusNotifierItem. Real icon/menu interaction remains a user visual acceptance check.

The fresh instance is already open; reopening is not required. No game or installer was automatically started. Source and documentation are delivered together.
