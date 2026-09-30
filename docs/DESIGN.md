# Standalone game library, installer and launcher — 0.3.1

## Contract
Manage preinstalled executables or explicitly run a trusted Windows installer with UMU/Proton. No Steam client/account or sync integration is required. Steam's public catalogue is the credential-free default metadata source; IGDB and SteamGridDB remain optional with accurate attribution.

## Interface
Home retains compact cards, search, readiness count and Play/Stop. Add Game opens title/ID search with public Steam default and optional supported provider selection. Selecting a result fetches and saves metadata plus available artwork, creates a library entry and opens details; launch fields are not required. Manual metadata entry is a fallback. Metadata-only entries show Set up to play. Details are read-only: hero, cover, logo, title, description and related information. Pencil opens Edit Metadata; controller opens Manage Game. Dialog Save commits locally; Cancel discards draft metadata/file settings. Late metadata results cannot modify a cancelled draft.

Manage Game offers Already installed, Existing Windows launcher / shortcut (.exe/.lnk), and Install from installer; it contains executable, working directory, installer selection/status/logs/Run/Cancel/Confirm. Advanced launch settings are collapsed by default, with runner/default selection, dedicated prefix, structured arguments and Reset to defaults. Reset clears explicit overrides while retaining an installer’s pinned prefix/runner. Existing overrides stay valid; no broad configuration rewrite occurs.

Settings retains General backup/restore/appearance, Providers and the full Proton Manager. Metadata lookup/search/save/import never execute a game or installer.

## Operations and installation continuity
One shared lock covers both games and installers across rapid clicks and application instances. Installer uses a dedicated UUID prefix and saved runner context. Its own bounded session journal persists even when a later game launch changes the current operation journal. Finished setup means Select installed executable, not playable acceptance. Failed/cancelled/interrupted setup is retryable in the same prefix. Cancellation never deletes installed files, registries, runtimes or saves.

Confirmation requires an existing game executable distinct from setup and a valid working directory/runtime. Play is blocked until confirmed and never substitutes the saved installer for the game executable. Changing the installed executable in Manage Game clears confirmation. Automatic runner resolution is observed from owned child environment and retained; if unresolved, choose a concrete installed runner and retry setup. No game launches during development except inert owned fixtures.

## Ownership and lifecycle
Validated argv/cwd and allowlisted environment; never shell expansion or root execution. Catalogue IDs do not become UMU runtime identity variables. A Linux subreaper holds the operation lock through owned descendants, including detached/reparented children. PID/start-time checks protect against reuse. Stop targets verified owned descendants only. Early cancellation is tied to the unique session, so stale cancellation cannot stop a retry. Logs are bounded and sensitive environment text is filtered.

Running is detected using the selected executable under the verified supervisor’s ancestry, not only a log marker. Shared Wine helpers/unrelated games are never killed by name. OS or forced supervisor termination is outside graceful Stop guarantees; stale state is recoverable, not accepted as successful installation.

## Background/tray behavior
The Gio application ID enforces one instance. Close hides the window only after a live StatusNotifier host accepts the icon; otherwise it minimizes with a visible explanation. Host loss reveals a hidden window. Tray exposes Show Launcher and Exit through StatusNotifierItem/DBusMenu using Gio, without mixing GTK3 and GTK4.

Explicit Exit presents a cancellable warning. Active game/installer continues under its independent supervisor after Exit; reopening reconnects. No operation is silently stopped. Pending metadata/runner jobs must finish or be cancelled before Exit. Dialog drafts are discarded only after explicitly confirmed Exit.

## Runners and storage
Proton Manager retains official release paging/cache/architecture selection, installed/default/per-game choices, checksum verification, safe extraction, staging, cancellation/retry and no runner overwrite/removal. App updates never modify game files, saves or prefixes.

Version-1 libraries/ZIPs accept optional validated installation and launch settings. Metadata/artwork and historical identities remain readable. ZIPs exclude executable binaries, prefixes, saves, credentials, runner downloads and operation/installation journals. Restore/relink file paths explicitly; backup game saves/prefixes separately.

## Verification
Core fixtures cover installer modes, persistence, pinned context, failure/cancel/retry, early cancellation, duplicate guard, process ownership and archive/provider boundaries. Native tests exercise readonly pages, modal Save/Cancel, public default search and missing-key IGDB switching, scrolling, actual inert installer execution/confirmation, tray/fallback/Exit warnings and existing Proton Manager. Private-bus tests exercise DBusMenu, tray host registration/loss and single-instance activation. No downloaded installer or real game is used for these tests.
