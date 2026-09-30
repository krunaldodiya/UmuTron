# Game Library Launcher

A native Linux desktop library for managing installed games, metadata and artwork, and playing directly through **UMU + Proton**. No game-client installation, account or library is required.

![Library](docs/screenshots/library-dark.png)

## Version 0.2

- Compact game cards, search, light/dark/system appearance, detailed metadata and artwork.
- IGDB metadata search and optional community artwork from SGDB; manual entry/local images work without provider accounts.
- Explicit **Play** / **Stop**, strict one-game-at-a-time protection, preparing/download/running/finished/error status and bounded output.
- Per-game executable, working directory, argument list, Proton override and dedicated prefix.
- Settings → **Proton Manager**: installed runners, default selection, official GE-Proton/UMU-Proton releases, paginated history, checksum-verified installation, cancellation/retry.
- Portable ZIP export/import with conflict preview. Imported settings never execute automatically.

This app does not install games, manage purchased-client libraries or synchronize client shortcuts. Deleting an entry keeps game files, saves and prefixes.

## Install and run

Ubuntu dependencies: system `python3`, `python3-gi`, `python3-cairo`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`. Direct Play additionally requires [umu-run](https://github.com/Open-Wine-Components/umu-launcher) and an appropriate graphics driver. Install UMU from its official packaging instructions; the app reports a missing executable.

```sh
/usr/bin/python3 tools/install.py
/usr/bin/python3 run.py
```

The installer creates a user application/menu entry under `~/.local/opt/game-library-launcher`. Re-run after pulling updates. No administrator access is needed for the application installer. Use system Python for GTK.

## Workflow

1. Add a game; search IGDB with your own credentials or enter details manually.
2. Set its executable and working directory in **Game files**. Review artwork and metadata.
3. In **Direct Play**, use an installed Proton folder, the app default, `UMU-Latest`, or `GE-Latest`. Set optional arguments, **one argument per line**; spaces on a line remain in one argument.
4. Save. Choose Play and review the executable's launch configuration. UMU may download official runtime/Proton assets at first use; output and preparation status remain visible.
5. While a game is active its button becomes Stop. Other games cannot start. Stop asks about unsaved in-game progress and targets only this launch's owned processes. Keep the launcher open during normal play; after an unexpected app exit it can reconnect to the surviving supervisor.

Compatibility is game-dependent. A running process or successful start is not proof that every game or every gameplay feature works.

## Proton Manager

Installed runners can be discovered in known compatibility-tool folders; detection is optional and does not require the associated client. New runners live in the app's own `proton-manager/runners` folder.

Available downloads are **official stable GE-Proton and UMU-Proton releases for x86_64/aarch64**, from version 9 onward where a published checksum is available. Refresh loads 20 upstream releases per page; Load older versions continues that family's history. Older unsupported builds, other families and client-only releases are excluded. This is not a promise of every Proton build ever made. UMU resolves the release's required runtime when launching.

Downloads verify published SHA-256 and/or SHA-512 checksums. Extraction rejects unsafe paths/links/devices, limits expanded size, checks disk space, stages on the destination filesystem and never overwrites an existing runner. Cancel keeps installed runners intact; retry discards only stale app-owned installation staging directories. No uninstall/update action is offered. Downloads are temporary staging files; no personal installer archive location is assumed.

## Providers and attribution

Settings → Providers accepts your Twitch/IGDB credentials and optional community-artwork API key. Credentials are permission-restricted local files, not encrypted and not exported. IGDB and SteamGridDB are independent metadata/artwork services; SteamGridDB's service name is attribution, not client integration. Existing records fetched from the former public Steam Store provider retain their metadata/artwork, but new searches use IGDB. The old store adapter and sync feature were removed.

UMU and Proton internally use Valve runtime components. Their licenses and upstream behavior still apply; this app does not remove or disguise that dependency. See [UMU documentation](https://github.com/Open-Wine-Components/umu-launcher), [GE-Proton releases](https://github.com/GloriousEggroll/proton-ge-custom/releases), [UMU-Proton releases](https://github.com/Open-Wine-Components/umu-proton/releases), [IGDB](https://api-docs.igdb.com/) and [SteamGridDB](https://www.steamgriddb.com/api/v2).

## Data, migration and backup

- Data/artwork: `~/.local/share/game-library-launcher`; config: `~/.config/game-library-launcher/providers.json`. XDG overrides are honored.
- Existing metadata-manager version-1 libraries and credentials are copied on first use when no new library exists. Originals remain intact. UUIDs, paths, metadata, artwork and legacy identity fields are preserved. Legacy recovery journals remain in their original folder; no client files or shortcuts are changed.
- Version-1 backups remain importable. Launch configuration is an optional validated extension. Old launch text becomes visible as structured Direct Play arguments when editing; it is never a shell expression.
- Dedicated prefixes: `prefixes/<game UUID>`. Custom prefixes must be new/empty or previously created by this app; unrelated prefixes are refused. Reinstall/import does not delete prefixes or copy saved games.
- ZIPs include metadata, artwork, appearance, default-runner selection and launch path/configuration strings. They exclude binaries, saves, prefixes, runner downloads, credentials and session logs. Review/relink paths after restoring on another PC.
- Session journals are local/private. The supervisor holds a filesystem lock across app instances and tracks descendant start times, including orphaned processes. It does not inspect or stop games launched elsewhere.

## Isolated demo and tests

```sh
/usr/bin/python3 run.py --demo
python3 -m unittest discover -s tests -v
python3 -m compileall -q game_library
/usr/bin/python3 tools/ui_smoke.py
```

Demo Play is disabled. Tests use temporary mock runners, game files and archives. They never execute the user's games. See [design](docs/DESIGN.md) and [validation](docs/VALIDATION.md).
