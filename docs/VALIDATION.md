# Validation — version 0.2.0

Observed on Ubuntu 26.04 on 2026-09-30 using system Python and native GTK/libadwaita.

## Executed checks

- `/usr/bin/python3 -m unittest discover -s tests -q`: 29 isolated tests pass.
- `/usr/bin/python3 -m compileall -q game_library`: passes.
- `ruff check game_library tests tools run.py --select F`: passes.
- `/usr/bin/python3 tools/ui_smoke.py`: passes. Exercises light/dark library screens, compact cards, scrolling at 920×640, local Save/Delete, structured launch settings, active-game navigation, ZIP restore, metadata-first Add Game and Settings → Proton Manager with a synthetic available release. Screenshots are synthetic and were visually inspected.

## Safety and lifecycle coverage

Temporary executable fixtures exercise launch completion, failed start/nonzero exit, bounded logs, duplicate and cross-instance launch rejection, Stop, and detached descendants after a wrapper exits. No actual game runs in these tests. Arguments are argv values, never shell commands; foreign prefixes are refused. Stop targets owned PID identities only. Active-game entries cannot be deleted, and transitional preparation disables premature Stop.

Runner tests exercise checksum failure, cancellation, staged installation, no overwrite, unsafe archives, safe internal links, interrupted-stage cleanup, architecture filtering and cached pagination. Downloads use official upstream repositories; test downloads use inert temporary archives, not real runner packages.

Migration tests copy a version-1 library without changing its original and retain identities; ZIP tests cover launch/default-runner settings, artwork checksums and unsafe archives. Provider fixtures test credential handling and redirects. Portable exports omit credentials, binaries, prefixes, saves and session logs. Existing client shortcuts/files are not written.

## Boundaries

Actual UMU gameplay and full upstream runner downloads through this UI have not been accepted by these isolated checks. Compatibility varies by game, anti-cheat and hardware. Authenticated IGDB/SteamGridDB calls require the user's keys and remain outside fixture coverage. Legacy copied metadata remains usable without a fresh provider lookup. A comprehensive accessibility assessment was not performed. Native tests report harmless deprecated libadwaita test API calls.

The launch supervisor survives an unexpected UI exit. Forced termination of the supervisor or OS is outside graceful Stop guarantees. This app does not track games launched elsewhere. Local credentials and ZIP backups are not encrypted. Backup ZIPs do not replace backups of game saves/prefixes.

## Installed delivery

User installer and desktop-entry validation passed. Installed code was byte-compared with source. First-run migration preserved all five existing game identities and verified copied artwork bytes against original files; the original library remained unchanged. The normal installed app was opened through a user systemd service and remained active with no startup error in its journal. This is process/startup evidence, not a claim that a real game was launched or visually accepted by the user.

Installation: `~/.local/opt/game-library-launcher`; menu entry: `~/.local/share/applications/game-library-launcher.desktop`.
