# UmuTron

[Source repository](https://github.com/krunaldodiya/UmuTron)

A native Linux library for preinstalled games and Windows installers, metadata/artwork, and explicit Play through **UMU + Proton**. No Steam client, account or synchronization is required. Public Steam catalogue search works without credentials.

![Game details](docs/screenshots/details-dark.png)

## GNOME dock identity — 0.4.15

The visible application entry is now `io.github.game_library_launcher.desktop`, matching the unchanged GTK/Gio application ID. GNOME could not associate the earlier `game-library-launcher.desktop` name with the running window, resulting in a generic dock icon and missing pin/favorites action. The installer retains that older desktop ID as a launchable `NoDisplay=true` compatibility entry, with the same Exec and icon, so existing shortcuts and Workstation Modes still work without a duplicate applications-menu item. It is not marked `Hidden` or deleted.

The canonical entry declares `StartupWMClass=io.github.game_library_launcher`; GTK's program name is set to the same identity before startup for X11 matching. The existing `game-library-launcher` icon name, install/data/config directories, Python package, library IDs and Workstation `app:game-library-launcher` resource stay unchanged. No favorites are added, removed or reordered. New pinning uses the canonical desktop ID. Close/reopen an older running instance with its normal explicit Exit action if necessary; no game or desktop session restart is needed.

This follows [GNOME's application-ID contract](https://developer.gnome.org/documentation/tutorials/application-id.html) and [desktop entry NoDisplay/StartupWMClass semantics](https://specifications.freedesktop.org/desktop-entry-spec/latest/recognized-keys.html).

## UmuTron branding — 0.4.14

The app now appears as **UmuTron** in its window, Settings information, application menu and tray, with an original orbital/play SVG icon. Existing `game-library-launcher` install/data/config paths, compatibility desktop and icon identifiers, Python package name and Gio application ID remain stable. The rename requires no library or prefix migration. Prefix runtime maintenance and Proton labels from 0.4.13 are retained. Earlier screenshots below predate this branding update.

## Features

- Metadata-first **Add Game**: search by title/ID, select, then automatically save metadata/artwork and open details. No executable or runtime settings required.
- Persistent installation status/logs; cancel/retry keeps installed files. Select and confirm the game executable after setup. Setup exit alone never means the game is ready.
- Reuse the installer prefix, registry/runtimes and resolved Proton version for Play. Play never reruns setup.
- Read-only game details with hero/cover/logo; **pencil → Edit Metadata**, **controller → Manage Game**. Normal Play/Stop remains on cards/details.
- Optional overrides in collapsed **Advanced launch settings**, including Reset to defaults and custom paths. Normal Proton selection is visible in Setup.
- Close to tray; **Show UmuTron** and explicit **Exit**. Without a supported tray host, close minimizes instead of making the app inaccessible. Reopening activates the existing instance.
- One app-owned game or installer at a time. Stop targets only that launch's verified owned processes. Active operations continue under their supervisor if you explicitly Exit; reopening reconnects.
- Three-tab Proton Manager: official **Proton**, **GE-Proton**, **UMU-Proton**. Cached catalogs update in the background and load older releases while scrolling. Installed/default/available states share one list. Verified GE/UMU downloads support cancellation, retry and guarded uninstall of managed runners.
- Local ZIP import/export, compact cards, filtering, light/dark/system themes and provider artwork.

## Desktop and fullscreen

Desktop handles adding/installing games, metadata/artwork editing, launch setup, settings, Prefix maintenance and Proton Manager. Fullscreen is a native GTK console view: UmuTron branding, Games and Library tabs, local Search, Options and a clock. Games pairs cinematic artwork and a legible hero with a consistent portrait-cover collection rail. Library uses the same cover language in an installed-only grid. Details show game artwork, title, concise metadata and a prominent Play/Stop below the cover; Game Info opens the full description. Setup and advanced launch settings remain in desktop dialogs.

Arrow keys / the existing controller mappings move focus. Card activation opens details; only explicit Play/Stop activation can start or stop an operation. Back restores the selected card. Motion follows GTK's reduced-motion preference. Cards and text adapt to 1080p, 720p and smaller windows; very short windows omit the home excerpt and keep full information on details. Metadata-only games stay visible with a desktop-setup explanation. No play history or Continue/Recent data is invented.

Use **F11** or the tray's **Switch to Fullscreen / Switch to Desktop** actions. Fullscreen Options offers **Exit fullscreen** and **Exit**. Settings → General → **Default launch mode** selects the next-start mode and is included in library ZIP backups. Switching modes preserves the current selection and active operation; save/cancel an open editing dialog first.

Controller: D-pad/left stick navigates, A selects, B goes back, X invokes Play/Stop confirmation, Start returns to desktop, and LB/RB scroll details. Keyboard arrows, Enter, Escape and Page Up/Down are also supported. Optional native SDL2 (`libsdl2-2.0-0` on Ubuntu) reads mapped controllers only while the launcher has focus; it does not inject keys, grab the controller or consume game input in the background. Keyboard/mouse remain available without SDL2 or a controller.

![Fullscreen library](docs/screenshots/fullscreen-library-dark.png)

## Install

Use native Ubuntu packages `python3-gi python3-cairo gir1.2-gtk-4.0 gir1.2-adw-1`. The UI runs with the system Python, not an arbitrary environment without GI. Install UMU separately following [upstream instructions](https://github.com/Open-Wine-Components/umu-launcher). `umu-run` must be available on PATH or selected in advanced settings.

```sh
/usr/bin/python3 tools/install.py
```

This user-level installer writes code to `~/.local/opt/game-library-launcher` and creates the application menu entry. No root, game execution or library rewrite is performed. Open **UmuTron**. Use explicit **Exit**, then reopen an older running app to load the updated code (closing alone hides it to the tray); do not restart a game just to update its UI.

## Proton versions

Settings → Proton Manager has exactly three family tabs. **Proton** groups local official Stable, Experimental, Next and legacy builds; **GE-Proton** and **UMU-Proton** browse their official release archives for this computer’s architecture. Valve distributes official binaries through Steam and currently exposes no direct verified binary assets in its GitHub release feed. UmuTron can use a compatible local official build through UMU; it does not install Steam/SteamCMD, fetch source archives as runners, or integrate external launcher libraries.

Choose **Set as default** on a build. Manage Game → **Proton version** offers **Use default** and exact available/installed versions. Saving a choice never downloads or executes a game. After explicit Play or Launch Installer, a missing exact GE/UMU build downloads, checks its published digest, installs atomically, and only then starts UMU with its absolute path. Failed/cancelled preparation never starts the game; retry keeps the selected version. Concurrent requests reuse the same completed verified installation. Partial archives are discarded and retries fetch a fresh copy.

Existing `UMU-Latest`/`GE-Latest` policies remain UMU-managed automatic selections. Existing custom paths and legacy installer pins stay readable without migration. Deliberate **Use default** overrides a historical installer runner pin while preserving the prefix; a blank legacy setting retains that pin. The installer’s resolved exact build is pinned at executable confirmation.

**Uninstall** applies only to UmuTron-managed runner folders and requires confirmation. Reassign the app default and affected game selections first. Active operations and runner leases block removal; detectable same-user process use is also checked. These advisory locks do not exclude programs outside UmuTron. Game files, prefixes, saves and custom runner folders are never removed by this action.

## Add and play

Choose Add Game, search the public Steam catalogue (or select IGDB), and select a result. Metadata and available artwork are saved automatically; the read-only detail page opens. Manual entry is an optional fallback. Metadata-only entries are valid and show **Set up to play**.

Later, controller → Manage Game uses an already-installed switch and installation/setup stage tabs. Select executable/working directory when ready. UMU is discovered on PATH. The visible Proton version selector inherits the app default or selects a specific installed/downloadable build. Configuration never runs anything by itself.

For Install from installer, select a trusted setup executable and Run installer. The review is explicit; you handle its agreements and destination. Watch status/logs in Manage Game. On success, failure or cancellation, files stay intact. Reopen Manage Game later to retry or select/confirm the installed game executable and working directory. The picker opens the owned prefix's drive_c when available. Play uses the confirmed game file and pinned prefix/runtime. An unresolved automatic runner requires a concrete installed version and a retry rather than silently switching an installed game's runtime.

Never run games/installers with root/admin privileges. Compatibility, anti-cheat and hardware vary; an installer may create external files or require user interactions beyond this app's controls.

## Metadata and artwork

Add Game searches metadata first; pencil → Find metadata can change an existing match. Default **Steam catalogue (no credentials)** searches titles or public store IDs. No client/account is needed. These public endpoints may change or be region-restricted. Optional IGDB requires Twitch/IGDB credentials only when selected; missing keys do not block public search. SteamGridDB supplies optional community artwork in the metadata dialog. Manual text and local PNG/JPEG images work without accounts.

Credentials are permission-restricted local files, not encrypted and never exported. Service/runtime attribution remains accurate: [Steam catalogue](https://store.steampowered.com), [IGDB](https://api-docs.igdb.com/), [SteamGridDB](https://www.steamgriddb.com/api/v2), [UMU](https://github.com/Open-Wine-Components/umu-launcher), [GE-Proton](https://github.com/GloriousEggroll/proton-ge-custom/releases), [UMU-Proton](https://github.com/Open-Wine-Components/umu-proton/releases). Proton/UMU use Valve runtime components internally.

## Data and backup

Data/artwork: `~/.local/share/game-library-launcher`; credentials: `~/.config/game-library-launcher/providers.json`. XDG overrides are honored. Dedicated prefixes live under app data; custom paths are optional. Existing unrelated prefixes are refused. Installer history is private under `installation-sessions/<UUID>.json`; current journal/lock reconnect across UI restarts.

Earlier version-1 libraries/archives and custom overrides remain readable. The earlier metadata-manager library/credentials are copied only if the new library is absent, preserving originals and identities. No existing game, save, prefix, artwork or Steam shortcut is deleted by this update.

ZIP backups include metadata/artwork, appearance and launch/installation path settings. They exclude game files, saves, prefixes, credentials, runner downloads and operation logs. Import never executes anything. Review/relink paths on a new PC and back up saves/prefixes separately.

## Verification

```sh
/usr/bin/python3 -m unittest discover -s tests -q
/usr/bin/python3 -m compileall -q game_library
ruff check game_library tests tools run.py --select F
/usr/bin/python3 tools/ui_smoke.py
dbus-run-session -- /usr/bin/python3 tools/tray_smoke.py
dbus-run-session -- /usr/bin/python3 tools/instance_smoke.py
```

`--demo` is isolated and cannot execute games/installers. Tests use inert temporary fixtures and synthetic artwork. See [design](docs/DESIGN.md) and [validation](docs/VALIDATION.md). No real repack installer, new license acceptance or campaign/gameplay test is performed automatically.

## Two-stage installer setup

Already installed shows executable and working-directory selection only. Install from installer first shows setup selection and installation controls; game executable selection is hidden until the installation attempt ends. Step 2 uses the same executable/working-directory flow and requires explicit confirmation, retaining the installer prefix and Proton version. Failed or cancelled attempts may also leave files, so selection remains available for recovery without implying success.

## Stage tabs

Manage Game uses two stage tabs, Install and Game setup, with only one enabled at a time. The I already have installed the game switch skips/disables Install and activates Game setup. Otherwise Install is active until the attempt ends, then Game setup becomes active for executable confirmation. Return to installation / retry switches back safely without deleting files or losing prefix/runner context. The switch is disabled while an operation is active.

## Public catalogue artwork repair — 0.3.5
Steam asset manifests supply modern hash-qualified cover and hero URLs, with legacy fallback. Cricket 26 cover/hero were downloaded live and added to its existing entry without replacing saved artwork or changing launch configuration. Its separate logo was unavailable through these public endpoints. Fixture tests cover hash paths, rejected paths and API failure fallback; native smoke uses isolated data.

Fullscreen layout checks include 1920×1080, 1280×720 and 1024×600 allocations, reachable scrollable content, horizontal selection scrolling and stable hero/rail position across games with differing artwork/text. Physical TV scaling and controller acceptance remain user checks.

## Per-game compatibility and automatic diagnostics — 0.4.11

UMU play and installer launches automatically request focused Proton exception/module logs. The latest Proton log for each game is stored locally under the app data directory `diagnostics/<game UUID>`; Manage Game → Open diagnostic logs opens that folder. If Proton fails before initializing, the operation log still records its failure and the folder may contain no Proton log. Logs can contain personal paths and are never included in portable ZIP backups. New attempts can replace the previous Proton log for the same game.

Manage Game → Advanced launch settings includes optional DLL compatibility overrides, for example `winmm=n,b`. These are validated, passed as a process environment value without a shell, and apply only to that game's launch. Blank does not inject an override and preserves existing prefix registry settings. Save persists the override; Cancel discards changes; Reset to defaults clears the draft launch override but does not edit the prefix registry or erase installer continuity. Portable metadata backups retain the saved compatibility preference but not diagnostic logs. No blanket automatic DLL fixes or guessed UMU identifiers are applied. Existing runner choice, prefixes, game files and saves are preserved.

## Diagnostic retention — 0.4.12
All automatic Proton logs live in the single app-data diagnostics directory, under game UUID folders. Routine logs request errors and exception warnings instead of verbose traces. Before launches and after owned processes finish, completed logs older than 14 days are deleted, each file is trimmed to its last 8 MiB, and oldest files are removed to enforce a 100 MiB total cap. Active log growth is not truncated while Proton is writing; these caps apply after completion.

Settings → General → Diagnostic logs → Clear all diagnostic logs asks for confirmation and removes only regular .log files in managed game folders. Symlinks and other files are ignored. The launch lock blocks clearing while any game or installer is active. Games, saves, prefixes, artwork and operation records are never deleted by this control.


### Prefix information and runtime maintenance (0.4.13)
Setup / Manage Game now includes **Prefix** alongside Install and Game setup. It displays read-only prefix storage, creation state, runner version and conservative native/builtin/game-local runtime evidence. Game-specific requirements remain explicitly unknown. Manual VC++ v14 core installation requires a separate confirmation and interactive Microsoft license acceptance; .NET, legacy DirectX and runner components have no manual install/replacement actions. See [the behavior contract](docs/DESIGN.md#prefix-inventory-and-install-only-maintenance) and [validation and limitations](docs/PREFIX-VALIDATION.md).

Proton Manager distinguishes automatic latest selectors from installed versions without changing existing selections.
