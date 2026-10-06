# UmuTron — standalone game library, installer and launcher

## Branding — 0.4.14

The user-facing application name is exactly **UmuTron**. Window/header, Settings information, exit prompt, desktop menu and tray title/tooltip use that name. The original orbital/play SVG is shared by the desktop, GTK window icon and tray. Technical identities remain unchanged: `game-library-launcher` install/data/config paths, desktop/icon names and distribution name; `game_library` Python package; `io.github.game_library_launcher` Gio ID (including the existing demo suffix); game UUIDs and prefix ownership markers. No migration or user-data rewrite is part of branding.

## GNOME dock identity — 0.4.15

The visible application entry is now `io.github.game_library_launcher.desktop`, matching the unchanged GTK/Gio application ID. GNOME could not associate the earlier `game-library-launcher.desktop` name with the running window, resulting in a generic dock icon and missing pin/favorites action. The installer retains that older desktop ID as a launchable `NoDisplay=true` compatibility entry, with the same Exec and icon, so existing shortcuts and Workstation Modes still work without a duplicate applications-menu item. It is not marked `Hidden` or deleted.

The canonical entry declares `StartupWMClass=io.github.game_library_launcher`; GTK's program name is set to the same identity before startup for X11 matching. The existing `game-library-launcher` icon name, install/data/config directories, Python package, library IDs and Workstation `app:game-library-launcher` resource stay unchanged. No favorites are added, removed or reordered. New pinning uses the canonical desktop ID. Close/reopen an older running instance with its normal explicit Exit action if necessary; no game or desktop session restart is needed.

This follows [GNOME's application-ID contract](https://developer.gnome.org/documentation/tutorials/application-id.html) and [desktop entry NoDisplay/StartupWMClass semantics](https://specifications.freedesktop.org/desktop-entry-spec/latest/recognized-keys.html).

## Contract
Manage preinstalled executables or explicitly run a trusted Windows installer with UMU/Proton. No external launcher, client account or sync integration is required. The Store uses official IGDB data through the separate UmuTron-API backend. The desktop receives normalized game information and official image links, never Twitch credentials or access tokens. Existing Steam/manual/IGDB metadata and custom artwork remain readable and are not rewritten.

## Interface
Home, Library and Store are separate native routes in both display modes. Home preserves its cinematic hero and Recently played rail, containing local observed-play history newest first (up to 24). Below it, Recently ready to play lists genuinely dated successful setup changes newest first. Home has no undated legacy section. Those games remain unchanged in Library and may appear in Recently played when observed play history exists; no date is fabricated. Library contains every saved title in a responsive portrait grid, with title search, local genre filtering, title/recently-added sort and 48-item pages. The fullscreen header contains Home, Library, Store and options; search belongs only to its Library or Store route. Its Search button/Enter, genre and pagination controls match Store while keeping independent query, genre, page, focus and scroll state. Local genre labels come from all saved records, including legacy metadata; title and exact genre filtering and sorting run before pagination, never against just the current page. Library browsing performs no provider calls and works offline. Removing the last result on a page clamps to the new last page without clearing filters. Store has title search, official IGDB genres and 24-item pages, with In library badges. No price, external-launcher or unrelated filter is shown.

Both routes have First/Previous, a bounded window of five numbered pages with current-page highlight and ellipses, and Next/Last. Library has an exact filtered total. Store accepts optional `total_items` (nonnegative safe integer) and `total_pages=max(1,ceil(total_items/24))`, together or neither. Counts must agree with page length and accessible `has_next`. Cached counts are validated in the same way. Without totals, Store displays First/Previous/current/Next and explicitly says the total is unavailable. The request cap of 1,000 is never called the last page: true totals remain visible, Next stops at the cap, and Last is unavailable when beyond it with guidance to narrow the search. An out-of-range counted response retains its requested page; the UI refetches the actual last page. Search/filter/sort changes reset page and position. No catalog-wide prefetch is used.

All three routes open one shared read-only detail implementation. Unsaved Store previews show Add to library; saved unconfigured entries show primary Setup in desktop mode. Fullscreen offers Open desktop Setup: only explicit activation changes mode and opens that same saved UUID in the existing Setup form. A blocked mode switch opens no editor; cancellation preserves the record. No duplicate fullscreen form or fullscreen installer execution is introduced. Configured or active games retain Play/Stop in either mode. Automatic downloads remain unavailable; no Install action, source request or fake progress is exposed. Setup becomes secondary to Install only after a future working download integration is separately accepted. The gear offers Setup for configured games only in desktop mode, Remove from library only for saved records, and fresh Uninstall only for configured games whose executable is present. Resume uninstall remains available for an interrupted, journaled removal even when the payload has already moved to staging. Configured games on unavailable/unmounted storage retain Play for the normal launch validation; they are not silently reclassified as uninstalled. Desktop Setup retains its More → local installer workflow and existing-file configuration; it is not presented as a download pipeline. The proposed separate integration boundary is in [DOWNLOAD-SERVICE-CONTRACT.md](DOWNLOAD-SERVICE-CONTRACT.md), including a distinct paused phase. Back retains the originating route, query, genre, page, scroll and focus. Add never launches or installs anything, waits for available artwork, is idempotent by exact IGDB identity and cancels its write if the user leaves first. Multiple existing copies require choosing one in Library. Steam IDs are optional validated related-entry links, never library membership, ownership, entitlement or UMU gamefix IDs. An exact IGDB match opens the existing local UUID without rewriting its metadata, artwork, Setup or history. A shared Steam link offers explicit navigation to a related saved entry; it never merges or marks a different IGDB entity as saved. Conflicting or multiple local matches require manual choice in Library; no records are merged or deleted. Enhanced and Legacy AppIDs remain distinct. List responses may omit Steam IDs, so same-name saved games trigger bounded detail lookups only as a discovery hint; titles alone never establish membership or a relationship. Detail completion and Add both recheck current membership. Add callers sharing the app library serialize their membership check and save. Missing artwork and empty/offline/loading states retain stable layout. Fullscreen shared details retain the approved cinematic composition: full-strength key art under legibility gradients, a bounded lower-left information panel, larger typography, and one shared horizontal row for the primary action, gear and Game Info controls. The same renderer and state policy serve Store, Home and Library; the removed marketing heading and redundant game logo remain absent.

The old metadata/Add search dialog, pencil editor, manual metadata authoring and artwork chooser are removed from the user flow. Stored custom content is preserved. Setup stays separate from read-only details; Cancel preserves saved data. Late catalog and picker callbacks cannot repaint another route or save a canceled action.

Manage Game opens one Setup form with executable, working directory, arguments and a per-game runner selector. More contains Install game… or Reinstall… in the same position according to saved/draft configuration. Installer selection, status, logs, explicit start and cancellation live in a separate transient modal. There are no stage or Prefix tabs. Advanced launch settings are collapsed by default, with runner/default selection, dedicated prefix, structured arguments and Reset to defaults. Reset clears explicit overrides while retaining an installer’s pinned prefix/runner. Existing overrides stay valid; no broad configuration rewrite occurs.

Settings retains General backup/restore/appearance, IGDB attribution and the existing Proton Manager; credential-entry Providers UI is removed. Metadata lookup/search/save/import never execute a game or installer.

## Catalog connection and ownership

Release 0.4.26 preserves the locally tested Setup 0.4.23 with Home, Library, Store and shared details. Set nonsecret `APP_BASE_URL` in the environment or `$XDG_CONFIG_HOME/game-library-launcher/catalog.json` (default `~/.config`) to the approved HTTPS backend origin (scheme/host/optional port only, no endpoint path); the client calls GET `/v1/genres`, `/v1/games?q=&genre=&page=`, and `/v1/games/<id>`. The environment primary overrides the config primary. An absent or invalid URL leaves Library usable offline and gives Store a connection state. Config reads are bounded to 16 KiB and malformed content fails closed without displaying its contents. No fallback scraper or direct Twitch credential flow is activated. The Next.js backend is owned by the separate UmuTron-API project; Vercel deployment and production account-wide rate/token coordination are outside this desktop change. Unfinished Storage and automatic-download prototypes are excluded.

The previous `UMUTRON_CATALOG_URL` is consulted only if `APP_BASE_URL` is absent from both environment and config. An explicit empty/invalid primary or malformed config cannot fall back to another host. Both names require an origin; endpoint suffixes remain `/v1/...`. There is no built-in remote default. `IGDB_API_BASE_URL` is the backend's upstream configuration and is not read by the native app. Backend `.env.local` is not automatically loaded by the desktop process.

Local development may explicitly set `APP_BASE_URL=http://localhost:3000` and `UMUTRON_ALLOW_LOOPBACK_HTTP=1`. The default `RemoteCatalog` still requires HTTPS. Only exact localhost or numeric loopback HTTP is accepted with that opt-in; ambiguous numeric forms, IPv4-mapped/scoped IPv6, LAN addresses, credentials, invalid ports, paths, queries and fragments are rejected as base URLs. Localhost is converted to a literal IPv4 loopback destination before requests. The loopback transport bypasses environment proxies, refuses all redirects, sets no auth/cookie headers, uses GET only, uses a 20-second network timeout and reads at most 4 MiB plus one limit-detection byte. Request paths are restricted to the agreed catalog routes. It receives no saved library/configuration/prefix paths or provider credentials. This exception is for local integration only; production remains HTTPS mandatory.

Catalog snapshots are bounded to 100 JSON files and 160 artwork files under local catalog-cache, separate from saved library artwork. Provider failure can reuse a validated saved page marked Offline. Imported metadata cannot choose network endpoints. Only normalized IGDB image URLs are fetched, with bounded image validation. One catalog service lock serializes requests; generation tokens discard stale UI completions. Active requests use bounded transport timeouts; queued work is canceled on navigation/Exit.

## Recent-play evidence

Recently played has no fabricated migration or added-game fallback. The supervisor records a machine-local timestamp after two continuous seconds of the same selected-file process evidence during a Play operation. Evidence must be a verified owned descendant with stable PID/start time and an absolute Unix path or explicit Wine drive mapping resolving to the selected file identity. Bare basenames, wrappers, log text, installers, runtime operations, canceled preparation and ambiguous paths do not count. This is process evidence, not proof of rendered gameplay or a completed session. Existing Running status detection remains independent. Play history is not in portable backups. Exiting or unresolved non-game helpers do not invalidate separately verified game evidence. Home observes atomic history updates while active, preserves selected games and action focus, defers during modal interactions, and reloads on navigation or restart. No historical session is reconstructed from log text.

## Guarded game removal and recovery

Remove from library deletes metadata only after confirmation; game files, saves, prefixes and Proton are retained. Uninstall is separate and requires a fresh machine-local ownership receipt. Setup reuses the saved working directory as its candidate, with an optional alternate folder picker and a separate explicit Verify confirmation. Verification changes no executable or working-directory fields and deletes nothing. Draft configuration must be saved first.

The receipt pins the exact library record, dedicated root and bounded inventory. Root/home/shared containers, binary subfolders, nested mounts, links, multiple hard links, mixed ownership/writable shared files, known save/prefix directories and unclassified file extensions fail closed. Every other saved game path is expanded and canonicalized to reject overlaps, including symlink aliases. Conservative inventory rules may reject valid installations; no unsafe fallback is offered.

Execution revalidates the receipt under the app launch, root and prefix guards and checks observable process use. The payload moves atomically to a visible same-filesystem `UmuTron-uninstall-<operation>` folder. Each file is atomically captured without replacement into a private visible `UmuTron-uninstall-stage-<operation>` folder, revalidated, then removed. Unexpected captured objects are retained for manual review. Staging, inventory and journals support interrupted retries. The durable `payload-empty` transition precedes terminal directory removal; metadata is durably removed only after file removal succeeds, before recovery records are discarded. Directory durability barriers include first-use receipt-folder creation. Failures retain recoverable metadata/journals whenever deletion is incomplete.

These are Linux filesystem/process checks and cooperative app locks, not isolation from a malicious process running as the same user or a guarantee about unobservable external writers. No real game files are used in acceptance tests. Saves outside the verified root, prefixes and runtimes are always separate. Portable exports do not carry deletion authority.

## Native visual and navigation contract

The original UmuTron orbital/play SVG, large hero artwork, restrained gradients, mint focus ring and consistent portrait frames remain native GTK widgets. Library/Store navigation is bounded per page for 200+ entries; keyboard PageUp/PageDown and existing controller LB/RB move pages. Detail LB/RB scrolls information. Home selection is independent from Library focus. Existing arrows, Enter/A, Escape/B, X focus-to-Play and F11/Start options semantics remain. No new hardware-gamepad support is claimed. Small detail windows suppress the secondary cover and retain readable content/actions in the scroll area. Windowed and fullscreen share routes and data without altering workstation profiles.

## Operations and installation continuity
One shared lock covers both games and installers across rapid clicks and application instances. Installer uses a dedicated UUID prefix and saved runner context. Its own bounded session journal persists even when a later game launch changes the current operation journal. Finished setup means Select installed executable, not playable acceptance. Failed/cancelled/interrupted setup is retryable in the same prefix. Cancellation never deletes installed files, registries, runtimes or saves.

Confirmation requires an existing game executable distinct from setup and a valid working directory/runtime. Play is blocked until confirmed and never substitutes the saved installer for the game executable. Changing the installed executable in Manage Game clears confirmation. Automatic runner resolution is observed from owned child environment and retained; if unresolved, choose a concrete installed runner and retry setup. No game launches during development except inert owned fixtures.

## Ownership and lifecycle
Validated argv/cwd and allowlisted environment; never shell expansion or root execution. Catalogue IDs do not become UMU runtime identity variables. A Linux subreaper holds the operation lock through owned descendants, including detached/reparented children. PID/start-time checks protect against reuse. Stop targets verified owned descendants only. Early cancellation is tied to the unique session, so stale cancellation cannot stop a retry. Logs are bounded and sensitive environment text is filtered.

Running is detected using the selected executable under the verified supervisor’s ancestry, not only a log marker. Shared Wine helpers/unrelated games are never killed by name. OS or forced supervisor termination is outside graceful Stop guarantees; stale state is recoverable, not accepted as successful installation.

## Background/tray behavior
The Gio application ID enforces one instance. Close hides the window only after a live StatusNotifier host accepts the icon; otherwise it minimizes with a visible explanation. Host loss reveals a hidden window. Tray exposes Show UmuTron and Exit through StatusNotifierItem/DBusMenu using Gio, without mixing GTK3 and GTK4.

Explicit Exit presents a cancellable warning. Active game/installer continues under its independent supervisor after Exit; reopening reconnects. No operation is silently stopped. Runner and destructive maintenance jobs must finish before Exit; catalog callbacks are canceled on explicit Exit and outstanding network reads remain timeout-bounded. Dialog drafts are discarded only after explicitly confirmed Exit.

## Runners and storage
Proton Manager retains official release paging/cache/architecture selection, installed/default/per-game choices, checksum verification, safe extraction, staging, cancellation/retry and no runner overwrite/removal. App updates never modify game files, saves or prefixes.

Version-1 libraries/ZIPs accept optional validated installation and launch settings. Metadata/artwork and historical identities remain readable. ZIPs exclude executable binaries, prefixes, saves, credentials, runner downloads and operation/installation journals. Restore/relink file paths explicitly; backup game saves/prefixes separately.

## Verification
Core fixtures cover installer modes, persistence, pinned context, failure/cancel/retry, early cancellation, duplicate guard, process ownership and archive/provider boundaries. Native tests exercise readonly pages, modal Save/Cancel, public default search and missing-key IGDB switching, scrolling, actual inert installer execution/confirmation, tray/fallback/Exit warnings and existing Proton Manager. Private-bus tests exercise DBusMenu, tray host registration/loss and single-instance activation. No downloaded installer or real game is used for these tests.

## Historical release notes

The sections below document earlier releases. The current Interface and catalog/removal contracts above take precedence where older navigation or metadata flows differ.

## Two-stage installer setup — historical, superseded by 0.4.23

Already installed shows executable and working-directory selection only. Install from installer first shows setup selection and installation controls; game executable selection is hidden until the installation attempt ends. Step 2 uses the same executable/working-directory flow and requires explicit confirmation, retaining the installer prefix and Proton version. Failed or cancelled attempts may also leave files, so selection remains available for recovery without implying success.

## Stage tabs — historical, superseded by 0.4.23

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


## Single-screen Setup — 0.4.23

Setup has one form and a consistent More menu. Install game… is offered before configuration; Reinstall… is secondary in the same menu position for configured/preinstalled games and prior installation attempts. Existence checks distinguish a connected game executable from an unavailable saved path; an unavailable path does not promote reinstall into first installation. Completed installer attempts still require their session and explicit executable confirmation. A legacy installer draft without a session offers Use existing game executable, which explicitly switches it to preinstalled mode only after the existing validation succeeds. Advanced overrides, arguments, per-game runner selection and stored installation context remain intact. The per-game Prefix tab is removed; global prefix management/recovery remains a separate change.

Both menu actions only open an installer modal. The destination remains a choice inside the Windows installer, as in the existing workflow. The app does not redirect or reset prefixes or erase game files. Closing the modal retains the installer choice in the parent Setup draft; only Save or explicit start persists it. Cancelling Setup discards all unstarted draft changes. Existing persisted installer selections reopen normally. The final confirmation identifies reinstall separately, defaults to Cancel and warns that the Windows installer may modify game files. The existing installation service performs validation, session persistence, execution and prefix/runner continuity.

An active operation disables launch configuration edits, Save, installer selection and new starts. An owned installer retains its progress/logs and a cancellation action in the fixed footer when the modal reopens; closing either dialog does not stop execution. Escape returns from the installer to Setup and focus returns to More. Modal/picker callbacks are scoped to the original editor/dialog, and stale or changed confirmation drafts cannot start an installation. No runner/install/backend lifecycle implementation is changed.


## Setup chronology on Home — 0.4.26

The optional positive integer `setup_completed_at` records an explicit successful transition to a connected executable and valid working directory, or a meaningful successful executable/directory/installer-session configuration change. Normal Setup Save stamps through `Library.save_setup`; an installer stamps only after the existing confirmation and command validation succeed. A failed save cannot leave a timestamp or partial in-memory update. Merely opening Setup, saving unchanged fields, editing metadata or runner preferences, Add, and canceled drafts do not create or bump a date. Old configured records are not backfilled from file times, add order, launch logs or play history. Tied actual timestamps sort by title then UUID. The field persists with its library record and portable backup; observed Play history remains separate and machine-local.

Home shows the selected title's artwork and the existing Play/Stop policy above Recently played. Scrolling or controller Down reaches the new setup grids without shrinking the opening composition. Existing configured records without a recorded setup date have a separate alphabetical group. Previously set-up records stay visible when storage is disconnected, with Files unavailable or Setup needed instead of Ready to play. Readiness describes connected/confirmed local files, not proof that a game launched or rendered. Metadata-only records without a successful setup never enter these groups. Covers open the shared read-only detail and Back restores the originating Home section even when the same title appears in both rails. Focus reveal is route/generation guarded; no new hardware-gamepad support is added.


## Accepted Cuphead identity and Home chronology integration — 0.4.26

Manage Setup Save uses the accepted 0.4.25+cuphead.1 executable validator for a matching installer session that finished successfully with integer exit code zero. Invalid selections leave the editor and saved record intact. Canceled, failed, interrupted, missing or mismatched sessions do not acquire confirmation through Save. No installer or game runs during Save. The accepted top-level `installer_attempt` preserves the session UUID and resolved completed-installer path separately from the next unstarted installer draft. Save, explicit confirmation, readiness and Play reject that original installer, including currently resolvable symlink/hardlink aliases. New explicit starts replace the binding; drafts, reopen and backups preserve it.

Both normal Setup Save and explicit confirmation persist through `Library.save_setup`. A valid explicit confirmation stamps the successful setup transition; unchanged ready configurations, metadata edits and runner-preference changes keep their date. A hotfix-confirmed legacy record without a date remains undated on an unchanged Save. Failure/cancel writes neither confirmation, attempt metadata nor chronology. Existing observed-play history is not inferred from setup activity. There is no migration or real-record repair.

The attempt metadata remains outside the strict `installation` object so 0.4.25 can read, resave and back up it. That older code does not enforce the new identity guard. Legacy journals have no recorded executable, so explicit Save/Confirm binds the previously saved installer selection rather than the new draft; an installer path replaced before this update or an old symlink target cannot be reconstructed from the journal.

## Detail controller navigation and header preservation — 0.4.26

Global fullscreen Search remains removed; Library and Store keep independent scoped searches. The shared detail action row retains centered primary, gear and Game Info controls. No layout, artwork, typography or advanced-setting exposure is added by the reconciliation.

The baseline focus collector skipped GTK MenuButton because its outer focusable flag is false while its internal toggle owns focus. Eligible mapped/sensitive menu buttons are now included. When the current detail gear popover is open, controller navigation stays among its eligible actions; Up/Down and Next/Previous move through them, Select activates only the focused menu action, and Back closes the popover and restores gear focus without leaving detail. Background Play, page and fullscreen-options shortcuts are contained while that popover is open. Other modal handling and hidden/disabled-control filtering remain intact. This repairs existing controller-method behavior; no new hardware-gamepad capability is claimed.


## Desktop keyboard and tray mode correction — 0.4.27

Desktop arrows navigate the Home/Library/Store headers and cards using native control geometry. Home's recent rail retains its horizontal sequence, while setup and collection grids move between rows. Text/editable controls, native dropdowns/ranges, mapped popovers and launcher-owned modal windows keep their keys. Tab and modified arrows remain GTK-native. Keyboard support does not enable desktop gamepad input; the existing fullscreen controller gate remains intact. Paging shortcuts do not run behind text input or modal/popover surfaces.

The tray contains one mode command, opposite `Gtk.Window.is_fullscreen()`. Its menu revision and `LayoutUpdated` signal follow `notify::fullscreened`; each query and action also refreshes the getter to close stale-menu races. A click for the now-hidden mode ID is ignored. Explicit mode requests are reapplied when native fullscreen state differs from the layout flag. Show, Settings, Exit, close-to-tray and single-instance behavior retain their existing callbacks. No Storage assertion/registry changes are included in this correction.


## Browse focus and final Home layout — 0.4.28 candidate

Library and Store include their SearchEntry in keyboard/controller navigation. Down from a route control enters search; native keyboard caret and Tab behavior stays with GTK. Escape leaves editing for the current route. Controller Select submits the query through the same SearchEntry action as Enter. Controller Down enters the cards, falling back to the first current card when the previously selected title is absent from this page, and Up/Back returns to the route. Up from toolbar actions explicitly returns to the current route, instead of competing geometrically with window decorations.

The app owns browse scroll reveal in both directions, including top-of-content reveal for route/toolbar controls outside the scroll viewport. Browse viewports do not also run GTK animated focus scrolling. Collection headings/search and cards share one scroll area so short windows retain room for a complete card; pagination remains outside it. Reveal padding is capped by the actual viewport/card height difference. Focus revisions cancel older reveal callbacks, including rapid A–B–A reversals. Input revisions distinguish newer user input from GTK fallback focus during route rebuilding; queued detail/route restoration yields to the former. Store completion carries the input revision from request start so a delayed response cannot reclaim focus from newer input. Detail scrolling keeps its existing behavior.

The Home composition contains only the cinematic hero, Recently played and Recently ready to play. Metadata, undated records and setup/play chronology are unchanged. This correctness delta does not change the approved fullscreen design, ship Storage or alter catalog cache policy; performance and desktop visual parity remain separate work.

The horizontal recent rail owns each animation by its actual focused tile, route generation and scroll widget. GTK can emit focus-enter before notify::focus-widget, so that initiating notification must not cancel the same card's reveal. A new rail request removes the previous timer, while leaving the rail cancels its pending animation. The initial allocation callback also yields when its original card no longer owns focus or the route generation has changed. This keeps rapid reversals and route/detail returns from scrolling to an older selection.


## Store cache-first browsing — 0.4.29 candidate

Store shows a validated saved page immediately, then refreshes it. The saved taxonomy is loaded during route construction; page and genre refreshes run independently, so genre availability is not a prerequisite for usable cards. The status distinguishes a saved page currently refreshing from an offline fallback after a failed provider request. No snapshot age proves that the network is offline. Previous unscoped snapshots are not assumed to belong to the configured backend.

Snapshot keys include the validated backend origin and normalized query, genre and page. The envelope, timestamp, identity, items and optional exact totals are validated again before display. Malformed, oversized, nonregular or mismatched files are cache misses. Reads are bounded to 4 MiB, and the disposable cache retains at most 100 metadata files and 160 image files after eviction. Actual page totals above 1,000 remain unchanged, with the existing request cap and unavailable true Last behavior.

Metadata and images have separate bounded worker groups: three metadata workers and two artwork workers, each with at most 32 pending tasks. Foreground metadata takes precedence over queued optional enrichment. Canceling a queued task releases its slot immediately. Identical in-flight requests share transport without sharing mutable returned items; at most eight distinct service flights can exist. Transport does not hold the file locks. Existing request deadlines still apply; running work is allowed to finish and populate only its own disposable cache after the UI leaves.

Card text and actions do not wait for covers. Artwork updates existing cover slots, and metadata refresh reuses cards when their ordered IDs are unchanged. Search drafts, newer focus, genre selection and valid pager focus survive refresh. Removed selected cards use the existing first-card fallback; a removed numbered page control yields focus to search. Route generation and render revision fence late detail, membership and image callbacks, including old image requests for widgets reused by the same-page refresh. Executor shutdown owns both groups. Explicit Add still saves metadata and available artwork without downloading or executing a game.

The revision leaves Home and detail composition, manual Add/Setup, installer and preinstalled flows, Play/Stop, one-game ownership, Proton and Prefix lifecycle unchanged. Storage integration, desktop/fullscreen visual parity and production catalog rollout remain separate. The installed 0.4.28 release is not updated by this candidate.


## Desktop visual parity — 0.4.30

Desktop Home now applies its compact typography and action spacing through the window's existing compact state. Its 1080p composition and the original fullscreen rules remain intact. Desktop Library and Store share mint selection/focus treatment, cool card surfaces and the existing orbital/play icon in the native header. Explicit light/dark palettes follow libadwaita's effective appearance, including system changes and returning from fullscreen; native title buttons and desktop density remain.

Desktop detail uses a centered panel bounded to 1140px, a 180px cover at wide sizes and a deliberate primary-action width. Compact detail remains scrollable, long metadata wraps, and artwork-free content retains the same structure. The single shared detail page, metadata-first Add, separate Setup and Game Info, Play/Stop and navigation callbacks are unchanged. Presentation selectors are scoped to desktop so the accepted fullscreen layout remains independent.

## Search and Filter — 0.4.31 candidate

Library and Store expose only Search and Filter in both desktop and fullscreen layouts. Sort was removed at the user's request. Library keeps its deterministic default title order; Store keeps the existing provider default/relevance behavior and sends only q, genre and page. No new backend sorting capability is required.

Keyboard/controller navigation follows search input → Search → Filter → cards, with a reverse path back to the active route. Native search editing keeps its caret and text keys. The Filter popover owns navigation, contains unrelated page/Play actions, returns focus on cancel or selection, and keeps focus when genre data arrives. Removed menu rows cannot activate a replacement choice. The currently focused card is revealed after window resizing without changing selection. Query, filter, page, scroll and selection stay independent between Library and Store.

Installation-size information requires a separate release-bound contract. Existing catalog metadata does not provide installed size, source feed byte lengths are not game sizes, and the Storage policy's 1.5× expansion reservation is not installation size. Installed game details hide source availability controls instead of presenting a source-reported size as installed size. Unconfigured details show only source-reported download size when available; it is not installed size.

## Multi-source release selection — feature-branch candidate

The shared detail page discovers source identities and names from the configured public UmuTron API; the desktop contains no provider roster or API key. It queries every API-enabled source regardless of local source toggles. Local toggles only filter source tabs and persist as user preferences. Store remains read-only until explicit Add or Install. Release discovery sends only the catalog title and page to bounded public search endpoints, returns persisted magnet classifications, and caches against the API origin and complete discovered-source identity set.

The detail page exposes the selected source's reported download size and a refresh action that bypasses cache. The picker has one tab per locally enabled source with matching releases. Arrow keys navigate tabs and editions on desktop; D-pad navigation moves through tabs, editions and actions in fullscreen with visible focus. The options menu labels manual setup **Add an installed game**. Install remains disabled while availability is pending and is restored after success, empty results or errors. Installed-game details hide source controls.

The public release contract reports magnet metadata but no verified package layout. The app never classifies layout from a provider name or title; after explicit Install, it auto-selects only a `setup.exe`. Other downloaded executables are not launched automatically and require explicit manual selection through Add an installed game.

`file_size` is source-reported download metadata, not installed size, verified payload size, archive contents, executable identity or proof of readiness. Public API results contain only bounded persisted magnet data and normalized enabled source identity; the endpoint is read-only and has no desktop secret. Historical provider adapters remain for compatibility tests only and do not define app sources or user-facing strategy. The selection delta does not broaden filesystem ownership, uninstall, UMU/Proton launch or operation-lock authority.



## Consistent native dialogs — 0.4.32 candidate

App-owned message dialogs, Setup, the local installer, Game Info, fullscreen options, Settings and app popovers share the existing slate/mint light/dark palette, visible focus treatment and action styling. Fullscreen surfaces inherit readable larger controls through their transient owner chain, including nested messages. Effective desktop theme changes update already-open surfaces. System/portal file pickers retain their system-native appearance.

Native message dialogs keep their response semantics, destructive action marking and cancellation defaults. Short title-only prompts do not gain filler subtitles. Long bodies use a bounded accessible scroll area outside the response buttons, retain the complete existing bounded error text, and support the existing fullscreen information paging action. Settings keeps its native preferences navigation; popovers retain their own menu ownership.

Setup, local installer, Game Info and fullscreen options share a native header. Form and information windows keep a fixed action footer, and body content scrolls independently. Window titles remain bound to changing installation status; meaningful game context appears in the header subtitle. Escape invokes the existing close/cancel handler, preserving draft cancellation and installer-to-Setup focus return. Game Info begins its read-only description at the top.

This is a presentation candidate only: Play/Stop, one-operation ownership, metadata Add, local installer/reinstall execution, stale confirmation checks, backup conflict choices and Proton actions keep their existing callbacks. Search and Filter remain focusable, Sort stays removed. Automatic installation and Storage integration are still disconnected; no backend contract, catalog request, user data or installed app is changed by candidate creation.


### Dialog lifetime correction — 0.4.32 review 2

The global theme manager observes only mapped surfaces through native weak receivers. Unmap/unrealize explicitly disconnects the subscription; mapping again resynchronizes appearance and reconnects once. This preserves live theme changes and popup reparenting without retaining discarded widgets or leaving dead callbacks. The shared Escape key handler obtains its window from the event controller instead of capturing the window in a closure. Native parent/child lifetime semantics remain: after a destroyed parent's external references are released, its destroy-with-parent prompt loses its native window. The stylesheet, dialog actions and response policy are unchanged.

## Shared detail and global Storage candidate — 0.4.33

Desktop detail now adapts the fullscreen composition: the same full artwork scene and legibility gradient, bounded bottom-aligned panel, responsive 46/34px title hierarchy, three-line overview, consistent cover and action group, and Game Info for complete text. Desktop chrome keeps its selected theme; the artwork surface uses the console palette. Narrow windows omit the cover, keep actions reachable and use native scrolling for tall metadata. Fullscreen layout remains unchanged. Both modes show the owned active action as Stop with the same destructive colors; the one-game guard is unchanged. Metadata editing, Setup and all launch/installer actions keep their existing separate workflows.

Settings includes Storage. Fullscreen options can open the same Storage page without switching display mode. This reconciles the previously uninstalled Storage integration; it is not a second registry. Registrations are metadata only, keyed by observed stable partition identity rather than mount path. A partition can carry installation/cache roles on one card; distinct partitions on one physical disk are allowed, duplicate identities are rejected. The UI shows current free/total capacity and availability. Current mounted roots replace last-known paths after remount; offline records retain their identity/default without resolving a stale path against the parent filesystem. Read-only, ambiguous, unsupported or non-private managed targets remain unavailable. Registration does not mount, format, repartition, change permissions or create payload directories. No automatic transfer is connected. Existing-file Setup, local Windows installers and Play remain independent of registration.

The separate catalog entity candidate consumes additive optional `game_type` and `platforms` on browse/detail. Store cards reserve a two-line classification slot that remains visible in compact windows; detail shows the complete platform names. Unknown old responses/snapshots show Catalog entry and no invented platform. These labels report catalog metadata, not UMU/Proton compatibility. An optional related-entry detail lookup fills missing classification only, so an older cached lookup cannot overwrite freshly displayed browse metadata. The candidate does not migrate or rewrite existing Library records or persist new classification fields into them.

Optional directed relationships are validated, cached and shown only in Game Info. `bundles` means containing bundles; `expanded_games` means expanded versions; `parent_game` can be a main game or bundle; `version_parent` means the main game of an edition. Optional inverse `bundle_contents`/`expanded_from` carry bounded items and `complete`; absent remains unknown, partial is labeled, and empty complete results state only that IGDB reported none. Selecting a reference explicitly opens its exact IGDB detail and adds nothing. Closed modal controls cannot reopen a route. Different catalog IDs remain separate even with identical names, artwork, release dates or Steam IDs; no title-specific branch, alias, inferred ownership or Steam-ID uniqueness is used. Metadata-only Add retains each exact IGDB identity and never changes related entries' UUIDs, setup, launch configuration or artwork. Multiple exact saved copies still require manual choice in Library; multiple merely related entries offer Open Library. The installed Storage/detail 0.4.33 release remains separate pending joint API/native review.

### Storage review 2: native navigation and lifetime

Grouped partition checkboxes participate in the existing controller traversal and Select dispatch, with the shared modal focus outline. Controller navigation first contains any visible menu in the active owned modal; Back dismisses that menu and restores its owner before closing a Settings window. This changes native method handling only, not physical input transport.

Closing Storage cancels discovery, disconnects its parent and child action callbacks, releases picker/removal references and clears the main window's Settings/page ownership. Closed Preferences views release their retained Proton/default controls; Proton's existing inactive guard is set before its dialog reference is released. General Settings callbacks resolve the parent through a native weak reference and reject stale activation. These lifetime changes do not run/cancel a real game, installer or transfer.

Storage replacement has the same ownership boundary as close: disconnect Storage-owned action callbacks on every old preference group before detaching it during refresh. Retained native events from discarded menus must not operate on the current registry or keep the page alive.


## Limited PCIe NVMe registration — separate candidate

A direct PCIe NVMe partition with validated non-removable UDisks/sysfs ancestry but a normal-user 64-byte bridge header can be registered only as metadata. The UI states that attachment details remain unavailable; this is not proof of fixed internal attachment. The prior strict classifier and all managed cache/archive gates remain conservative. Known external/hotplug, malformed/missing evidence, multi-bridge topology and other unknown classes remain blocked. No real drive is registered by development or install. See docs/STORAGE.md.
