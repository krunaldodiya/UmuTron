# UmuTron — standalone game library, installer and launcher

## Branding — 0.4.14

The user-facing application name is exactly **UmuTron**. Window/header, Settings information, exit prompt, desktop menu and tray title/tooltip use that name. The original orbital/play SVG is shared by the desktop, GTK window icon and tray. Technical identities remain unchanged: `game-library-launcher` install/data/config paths, desktop/icon names and distribution name; `game_library` Python package; `io.github.game_library_launcher` Gio ID (including the existing demo suffix); game UUIDs and prefix ownership markers. No migration or user-data rewrite is part of branding.

## GNOME dock identity — 0.4.15

The visible application entry is now `io.github.game_library_launcher.desktop`, matching the unchanged GTK/Gio application ID. GNOME could not associate the earlier `game-library-launcher.desktop` name with the running window, resulting in a generic dock icon and missing pin/favorites action. The installer retains that older desktop ID as a launchable `NoDisplay=true` compatibility entry, with the same Exec and icon, so existing shortcuts and Workstation Modes still work without a duplicate applications-menu item. It is not marked `Hidden` or deleted.

The canonical entry declares `StartupWMClass=io.github.game_library_launcher`; GTK's program name is set to the same identity before startup for X11 matching. The existing `game-library-launcher` icon name, install/data/config directories, Python package, library IDs and Workstation `app:game-library-launcher` resource stay unchanged. No favorites are added, removed or reordered. New pinning uses the canonical desktop ID. Close/reopen an older running instance with its normal explicit Exit action if necessary; no game or desktop session restart is needed.

This follows [GNOME's application-ID contract](https://developer.gnome.org/documentation/tutorials/application-id.html) and [desktop entry NoDisplay/StartupWMClass semantics](https://specifications.freedesktop.org/desktop-entry-spec/latest/recognized-keys.html).

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
The Gio application ID enforces one instance. Close hides the window only after a live StatusNotifier host accepts the icon; otherwise it minimizes with a visible explanation. Host loss reveals a hidden window. Tray exposes Show UmuTron and Exit through StatusNotifierItem/DBusMenu using Gio, without mixing GTK3 and GTK4.

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
Games and Library are the only top-level fullscreen tabs. Repeated Back/B/Escape returns within fullscreen and never exits it. Start/F11 opens options; the gear popup offers exactly **Exit fullscreen** and **Exit**, with the existing active-operation warning for app exit. The tray offers Show UmuTron, Switch to Fullscreen, Switch to Desktop, Settings and Exit. Settings retains Appearance and offers an Activity action in Diagnostic logs that opens the existing viewer. The focused game uses one prominent bold title, a compact two-line description and subdued release/genre information; the duplicate row title and logo heading are omitted. Existing library, artwork, launch configuration and prefixes remain unchanged.


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

## Diagnostic retention — 0.4.12
All automatic Proton logs live in the single app-data diagnostics directory, under game UUID folders. Routine logs request errors and exception warnings instead of verbose traces. Before launches and after owned processes finish, completed logs older than 14 days are deleted, each file is trimmed to its last 8 MiB, and oldest files are removed to enforce a 100 MiB total cap. Active log growth is not truncated while Proton is writing; these caps apply after completion.

Settings → General → Diagnostic logs → Clear all diagnostic logs asks for confirmation and removes only regular .log files in managed game folders. Symlinks and other files are ignored. The launch lock blocks clearing while any game or installer is active. Games, saves, prefixes, artwork and operation records are never deleted by this control.

## Prefix inventory and install-only maintenance

Manage Game / Setup retains Install and Game setup and adds an always-selectable **Prefix** tab. Read-only inventory scans run on the existing worker pool. A scan never creates a prefix or runs Wine, UMU, a game, or an installer. It shows the resolved prefix path/name, creation and ownership state, allocated/apparent disk usage, architecture, selected UMU/Proton paths, and resolved runner folder. Size traversal skips `dosdevices` and other-device directories, never descends through symbolic links, deduplicates hardlinks, and uses allocated blocks for sparse files. Bounded or inaccessible scans are explicitly incomplete.

Native VC++ core evidence is evaluated separately per architecture and selected minimum. Native PE publisher metadata, architecture and file versions must corroborate registry presence for Installed. Registry-only claims and Wine builtin images never prove a Microsoft package is installed. Partial, Missing and Unknown remain distinct. File metadata is evidence, not cryptographic publisher authentication. Wine/Proton components, .NET file observations, and known DLLs beside the game executable are shown separately; local files do not satisfy a prefix package. This is bounded inventory, not a complete dependency resolver. No game-specific requirements have been curated yet, so the UI explicitly says they are unknown.

Manual maintenance has curated x86/x64 **VC++ v14 core** profiles, with minima 14.0.24212.0 and 14.44.35211.0. The newer x64 profile also checks `vcruntime140_1.dll`. These are explicit user-selected core requirements, not inferred game requirements or claims about all optional MFC/OpenMP components. Positive satisfaction disables the selected action. A newer explicit minimum remains available when only the older core is present. Legacy VC++ (2010/2012/2013), .NET and legacy DirectX have inventory/support-boundary information only. DXVK/VKD3D remain runner-owned; there are no replacement actions.

Maintenance needs an initialized app-owned unlinked prefix, known architecture, exact installed Proton path and executable UMU launcher. Automatic aliases must resolve through a configured installed path; the confirmation pins prefix inode and runner/launcher identities. Ambiguous file identities are blocked. The confirmation discloses replacement/upgrade risk, affected prefix/runner, official Microsoft download URL, partial cancellation and the requirement to keep external launchers closed. After explicit confirmation only, the supervisor fetches the current official package over HTTPS with redirects restricted to Microsoft hosts, bounded download size and PE publisher/version plausibility checks; it records SHA-256. This is transport and file evidence, not a pinned release hash or Authenticode trust verification.

The installer receives only `/install /norestart`; its own interactive UI presents the EULA. The app never accepts it silently and exposes no remove, reset, repair, uninstall or arbitrary verb controls in this feature. This app-level promise does not constrain the operating system, external tools or Microsoft's installer UI. .NET 4.x in-place replacement and game-specific DirectX requirements are deliberately outside the supported install recipes.

All app launches retain the global game/installer guard and add a per-prefix advisory lock shared across libraries. Runtime maintenance also rejects detected same-user prefix use and fails closed if process inspection cannot establish idleness. The independent supervisor inherits both locks, retains them through download, all owned descendants and verification, and accepts success only after a successful exit plus fresh native-file evidence. Failure/cancellation preserve prefix files and do not imply successful installation. Runtime maintenance has its own operation type and does not overwrite game installer confirmation/session state. External programs do not participate in advisory locks; no OS-wide exclusion claim is made.


## Proton dropdown labels — 0.4.13
Settings → Proton Manager retains the same stored selectors and selection behavior. `UMU-Latest` and `GE-Latest` display as “UMU-Proton — automatic latest” and “GE-Proton — automatic latest”. Installed builds use their bounded `version` file metadata (for example “UMU-Proton-10.0-4 — installed”), falling back to the folder name when metadata is unavailable. Same-version installations at different paths are disambiguated with paths. Discovery deduplicates canonical installed paths; an existing saved symlink/path spelling is retained as the selected value, with no automatic settings migration. This is a label/discovery correction, not a change of runner or download source.


## Cinematic fullscreen presentation — 0.4.16

Games now places a bounded, legible game hero above a portrait-cover collection rail; Library shares the card language in its installed-only grid. The UmuTron masthead uses the existing orbital/play icon and mint focus accent. A dark directional gradient protects text while retaining artwork contrast. Reserved title/excerpt areas and fixed cover slots prevent selection-dependent layout shifts. Missing/corrupt artwork uses the same-sized fallback and clears stale backdrops. At short heights, home omits the excerpt; details and Game Info retain the information. Detail content scrolls, and Play/Stop remains aligned under the cover. Provider logos are fitted by visible alpha bounds for display only; stored artwork is untouched.

Details contain artwork, logo/title, release/genre/credits, concise description, contextual launch state and Game Info. Setup checklists, paths and advanced configuration remain off the fullscreen surface. Games are alphabetically ordered because the model has no reliable play-history data; no recency is inferred. The fixed portrait cards replace the historical 88px scaling chips described above.

Keyboard/controller semantics, deliberate card activation, one-game guard, modal cancellation, search/options, Back selection restoration and reduced-motion rail behavior stay intact. A queued detail-focus callback is scoped to the still-visible game page. The presentation module owns CSS, bounded artwork loading and fixed-size images; persistence and launch services are unchanged. Desktop metadata editing, Manage Game/Prefix, installer and Proton Manager flows remain intact.

Native test previews use GTK's isolated Broadway backend and temporary libraries, optionally copying public metadata/artwork without executable or prefix settings. These are actual GTK widget renders, not a web implementation or live-desktop screenshots. This method does not verify Wayland/X11 integration, a physical TV or controller hardware.


## Fullscreen detail simplification — 0.4.18

The fullscreen detail summary starts directly with the game title. The redundant “Your next adventure” heading and logo beneath it are omitted; their spacing collapses naturally in the existing GTK box. The left cover and contextual Play/Stop, backdrop, metadata, description and Game Info remain. Stored logos/artwork, home hero, desktop metadata/setup controls and every launch flow are unchanged.


## Proton selection and lifecycle — 0.4.19

The manager has three family tabs: Proton (Stable, Experimental, Next and legacy/local versions), GE-Proton, UMU-Proton. There is no external-launcher workflow or broad client-library discovery in this manager. App-managed runners, up to 256 direct UMU compatibility folders, and explicitly saved runner paths are listed. UMU-managed folders are read-only here and remain distinct from receipt-verified downloads. GE/UMU official GitHub metadata is cached by family/page; the UI paints cached choices immediately, refreshes without freezing the dialog, and requests the next page at the scroll boundary. Errors retain cached rows and expose a contextual Retry connection action. No prominent refresh or manual load-more toolbar remains. Valve’s release API currently supplies no direct verified binary assets; its tab explains this and accepts a compatible local Proton folder. It never installs Steam/SteamCMD or substitutes source archives/unofficial binaries.

Normal Setup has a searchable Proton selector outside Advanced. `default` is the explicit inheritance sentinel. Empty/missing legacy overrides still preserve `installation.proton`; explicit inheritance or another game override supersedes that historical pin. The saved global default applies consistently to Play, installer setup and Prefix inventory. `release:<family>:<tag>` is an exact logical official build, not a mutable latest alias. Existing absolute paths and UMU/GE automatic policies stay readable. Reset retains legacy installation continuity; choosing Use default deliberately opts out of the historical runner pin without changing the prefix.

Explicit execution may prepare a missing exact release under the independent supervisor. Source URL/tag/archive/host architecture and published digest are validated; a private staged archive is bounded, verified and traversed safely before atomic rename. A receipt records the installed release identity. An existing folder without a matching receipt is never overwritten or silently reused as a verified download. Catalog rows count only matching receipts as Installed and always save the exact release selector; preserved unreceipted folders are explicitly labeled local installations. Interrupted partial downloads are removed, and retry downloads fresh. A process-shared install lock deduplicates installation; a cancelled waiter does not cancel another requester. No game/installer process starts on failed or cancelled preparation. Existing automatic policies remain delegated to UMU.

Every concrete runner operation holds a shared canonical-path lease through preparation and all owned descendants. Removal requires an exclusive runner lease and the library’s launch guard, rechecks effective saved references, and rejects observed same-user process use or inaccessible process evidence. Only direct, unlinked children of the app’s managed runners folder can be removed after confirmation. Historical installer metadata is retained, but a deliberate replacement selection allows reassignment. Paths, prefixes, saves and custom/external runner folders remain untouched. No OS-wide exclusion is claimed for nonparticipating processes.

Catalog completion is scoped to its living Settings dialog or exact Setup draft, so closing/cancelling cannot mutate a later editor or save a choice. Tests cover real independent inert supervisors and multiprocess install contention, exact selection, inherited defaults, failed/cancelled preparation, retry, orphan descendants, referenced/in-use removal, archive/source/space rejection and native dialog transitions.


## Focused Proton Manager — 0.4.20

The current manager has exactly two tabs, GE-Proton and UMU-Proton, opening on GE-Proton. The former local-only official Proton tab, empty channel groups and folder picker are removed. This supersedes the three-tab presentation in 0.4.19; it does not change runner selection or launch contracts. Existing saved Valve/custom paths, symlink spellings, global defaults and installation pins remain usable and are not migrated or deleted. The per-game selector continues to include saved local runners.

Rows identify their source in the heading: UmuTron download, UMU-managed copy, or Local copy. Two copies reporting the same version remain distinct installations with unchanged selectors, receipt requirements and uninstall safeguards. The change does not merge files, adopt unverified folders, remove runners or touch prefixes.


## Protected UMU baseline — 0.4.21

The UMU-Proton tab shows one baseline using the existing `UMU-Latest` folder's bounded version metadata. It is labeled Managed by UMU and has no install/uninstall action. This is provenance, not proof that the mutable folder matches an exact verified release. Extra managed/local UMU installations and receipts remain intact; they are not listed repeatedly here. GE-Proton remains an optional catalog with no fresh-install runner or default.

The existing fresh-library fallback remains `UMU-Latest`; no settings migration or launch behavior changes. An explicit saved default, including GE, an exact UMU release or custom path, is retained on reopen and refresh. Only an explicit Set as default action changes it. Selecting the baseline saves the mutable alias, never the currently reported version. An existing absolute baseline path remains recognized without rewriting it.

When the baseline is absent, the UI states that the runner is prepared by UMU on first Play, reflecting the existing explicit-launch behavior. Opening Settings performs no runner installation or UMU catalog request. This is unrelated to the separate prefix/runtime recovery POC and does not deploy recovery functionality.


## UMU catalog and tab synchronization — 0.4.22

This revision restores cached, background and paginated UMU-Proton releases alongside the protected baseline, superseding 0.4.21's baseline-only catalog presentation. Only entries reporting the current baseline version are suppressed from the list. Other installed UMU versions and available official releases retain their existing path-specific actions. The baseline stays a nonremovable UMU-managed alias; version text never adopts another installation's receipt, path or exact release identity. A saved exact/default selection for the hidden same-version entry is retained and identified as a separate saved selection rather than falsely marking the mutable baseline as selected.

Two linked native toggle headers derive their checked and accent states from the visible stack page. Left/Right and Home/End select and focus the corresponding family. Background rendering preserves the visible family and restores row focus only within that page. Catalog activity does not install runners or change saved defaults. No launch, download, uninstall, prefix or recovery implementation changes.
