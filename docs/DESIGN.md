# Standalone game library, installer and launcher — 0.3.4

## Contract
Manage preinstalled executables or explicitly run a trusted Windows installer with UMU/Proton. No Steam client/account or sync integration is required. Steam's public catalogue is the credential-free default metadata source; IGDB and SteamGridDB remain optional with accurate attribution.

## Interface
Home retains compact cards, search, readiness count and Play/Stop. Add Game opens title/ID search with public Steam default and optional supported provider selection. Selecting a result fetches and saves metadata plus available artwork, creates a library entry and opens details; launch fields are not required. Manual metadata entry is a fallback. Metadata-only entries show Set up to play. Details are read-only: hero, cover, logo, title, description and related information. Pencil opens Edit Metadata; controller opens Manage Game. Dialog Save commits locally; Cancel discards draft metadata/file settings. Late metadata results cannot modify a cancelled draft.

Manage Game separates installation and executable selection into stage tabs; it contains executable, working directory, installer selection/status/logs/Run/Cancel/Confirm. Advanced launch settings are collapsed by default, with runner/default selection, dedicated prefix, structured arguments and Reset to defaults. Reset clears explicit overrides while retaining an installer’s pinned prefix/runner. Existing overrides stay valid; no broad configuration rewrite occurs.

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

## Two-stage installer setup

Already installed shows executable and working-directory selection only. Install from installer first shows setup selection and installation controls; game executable selection is hidden until the installation attempt ends. Step 2 uses the same executable/working-directory flow and requires explicit confirmation, retaining the installer prefix and Proton version. Failed or cancelled attempts may also leave files, so selection remains available for recovery without implying success.

## Stage tabs

Manage Game uses two stage tabs, Install and Game setup, with only one enabled at a time. The I already have installed the game switch skips/disables Install and activates Game setup. Otherwise Install is active until the attempt ends, then Game setup becomes active for executable confirmation. Return to installation / retry switches back safely without deleting files or losing prefix/runner context. The switch is disabled while an operation is active.

## Display modes — 0.4.0
Desktop owns all creation, installation, editing and configuration. Fullscreen is exclusively shared-library browsing and explicit Play/Stop, with no title bar/native controls. Its settings popover only exits fullscreen. There is no duplicate library or launch path. Header and mutation controls are hidden; entry points enforce desktop-only editing. Unconfigured entries stay visible but cannot launch. The mode can switch via F11, tray or desktop button; modal drafts block switching.

The optional persisted default_display_mode is desktop/fullscreen, with desktop fallback for legacy data. ZIPs preserve it. Runtime switches do not rewrite games or affect owned operations. Optional SDL2 mapped controller input is debounced and gated by focus on this window or its owned modal. Held action buttons cannot trigger on refocus. LB/RB scroll details. No input injection, global grab or unrelated process action is introduced.

## Console navigation refinement — 0.4.1
Fullscreen has Home, Games and Library navigation plus settings and current wall-clock time. Games contains all library metadata entries, using compact square game tiles over a whole-screen hero and lower summary/actions. Library contains entries with an executable and, for installer entries, confirmed executable selection. This is configuration-based: unavailable/unmounted executable locations do not silently remove saved entries. Neither view changes stored metadata or files.

Library cards have square artwork and a reserved two-line title area, equal dimensions and top alignment; they never fill the screen height. Missing/corrupt artwork uses the same-size fallback. View state and selection are in memory only. Focus traversal selects visible enabled buttons/menu buttons; labels and descriptions are not selectable/focusable in fullscreen. Desktop text selection is retained. Shoulder buttons scroll details without focusing text. There is no media/search/profile/achievement/playtime panel.


## Fullscreen navigation and typography — 0.4.2
Games and Library are the only top-level fullscreen tabs. Repeated Back/B/Escape returns within fullscreen and never exits it. Start/F11 opens options; the gear popup offers exactly **Exit fullscreen** and **Exit**, with the existing active-operation warning for app exit. Desktop Activity, Settings, Appearance and Exit are available from the tray instead of the header. The focused game uses one prominent bold title, a compact two-line description and subdued release/genre information; the duplicate row title and logo heading are omitted. Existing library, artwork, launch configuration and prefixes remain unchanged.


## Runtime download visibility — 0.4.3
During UMU preparation/download the app shows a live status panel in desktop and fullscreen: current stage, observed archive bytes in MiB when UMU reports its temporary .parts file, and an indeterminate spinner. UMU does not always supply a total size, so no estimated percentage is invented. The panel hides when running/finished; full operation logs remain available. Carriage-return progress updates are captured by launch supervision. Never stop a user's launch just to test the panel.


## Compact game information — 0.4.4
Home and detail descriptions display at most 300 characters, ending with ... when truncated. Stored/provider metadata remains complete. Game Info is available only on detail and opens a scrollable read-only full-description dialog. Detail Play/Stop sits directly under the cover, at its width. Preparation/download feedback appears below the local compact operation status, not in a global header banner. Focused buttons have a persistent outline for controller/keyboard navigation.

Fullscreen header tabs/gear activate only on A/click; game-card focus changes the preview, while card activation opens detail without launching. Only explicit Play/Stop button activation executes/stops an operation. X focuses that button without executing it.

The desktop header has no Fullscreen utility action; use the tray mode commands. Missing game-file configuration is labeled Setup. Fullscreen setup remains a desktop-only management task.


## Header navigation and Library background — 0.4.5
Left/right on the fullscreen header stays within Games, Library and Settings. Activating a section keeps focus on its tab; Down moves into the game cards. Library remains a grid-only view: focused-card changes update just the subdued hero background, without adding metadata panels. Game icons never launch an operation.

## Detail navigation — 0.4.6

Back restores the selected card in Games and Library rather than resetting to the first item. Desktop Back also retains the library filter and scroll position. The redundant detail launch-status label is removed; Play/Stop and live preparation progress remain. Native regression checks cover returning to a non-first card in both fullscreen sections and a filtered desktop library.

## Play confirmation — 0.4.7
Play confirmation shows only the game title question and Cancel/Play actions, without executable, prefix or runtime details. Stop and Exit safety warnings remain unchanged.

## Immediate Back focus — 0.4.8
Library rebuilding keeps other cards out of automatic focus fallback until the selected card receives focus synchronously. Selection/background never pass through the first card on Back. A layout callback adjusts scrolling only and does not move focus. Native checks record every preview during Back and require immediate selected-card focus, with no intermediate first-game preview.

## Gaming profile activation — 0.4.9
The --fullscreen option opens fullscreen for this activation only, forwarding to the existing app instance when already open. It does not save a new default mode or launch a game. Workstation Modes uses this option on Gaming activation.

## Fullscreen input, sliding rail and Search — 0.4.10
Keyboard navigation is captured before grid children consume arrows, using the same control-only routing as gamepads. Games pans its overflowing icon rail smoothly toward the focused card, with no horizontal scrollbar; reduced-motion settings disable the transition and Back restores position immediately. Search sits left of Settings and filters the saved library; selecting a result opens read-only detail, never Play. Native checks cover grid arrow dispatch, intermediate/end animation positions, reduced motion, header navigation and local search.

Games-only icon artwork is reduced to 88px; selected/focused chips render at full size and the others at two-thirds scale (1.5× selection ratio), with a short transition and stable row height. Library grid cards have no scale effect and retain their previous dimensions.

Fullscreen Settings is a separate modal (like Search), with Exit fullscreen and Exit actions; controller Back dismisses it without leaving fullscreen. Game arguments belong to Manage Game → Game setup, alongside executable and working directory. Advanced runner/prefix reset preserves those arguments.

## Per-game compatibility and automatic diagnostics — 0.4.11

UMU play and installer launches automatically request focused Proton exception/module logs. The latest Proton log for each game is stored locally under the app data directory `diagnostics/<game UUID>`; Manage Game → Open diagnostic logs opens that folder. If Proton fails before initializing, the operation log still records its failure and the folder may contain no Proton log. Logs can contain personal paths and are never included in portable ZIP backups. New attempts can replace the previous Proton log for the same game.

Manage Game → Advanced launch settings includes optional DLL compatibility overrides, for example `winmm=n,b`. These are validated, passed as a process environment value without a shell, and apply only to that game's launch. Blank does not inject an override and preserves existing prefix registry settings. Save persists the override; Cancel discards changes; Reset to defaults clears the draft launch override but does not edit the prefix registry or erase installer continuity. Portable metadata backups retain the saved compatibility preference but not diagnostic logs. No blanket automatic DLL fixes or guessed UMU identifiers are applied. Existing runner choice, prefixes, game files and saves are preserved.
