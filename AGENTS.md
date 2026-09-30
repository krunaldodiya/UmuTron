# Project instructions

Canonical contract: docs/DESIGN.md. This is a standalone Linux installed-game launcher.

- Direct Play is explicit, through UMU and Proton. Save/import/metadata lookup never execute a game. No shell commands are built from game data. Never use sudo for games.
- One app-owned game at a time. The launch supervisor owns descendants and retains the lock through their lifetime. Stop targets only verified owned PIDs; never broad process matching or shared wineserver termination.
- Never overwrite game binaries, saves, unrelated prefixes, or installed runners. No integration writes to a client library. Legacy metadata and backups remain readable; preserve original data during migration.
- Runner downloads use official GE-Proton/UMU-Proton releases, published checksums, archive limits and staged atomic installation. Never replace an in-use runner.
- Keep credentials, logs, prefixes, downloads and user paths out of Git and portable exports. Demo Play is disabled. Core and UI tests use inert temporary fixtures only.
- Use system Python for GTK. Required checks: python3 -m unittest discover -s tests -v; python3 -m compileall -q game_library; /usr/bin/python3 tools/ui_smoke.py on a desktop. Inspect synthetic screenshots for UI changes.
- Preserve active user work. Do not start/stop real games or unrelated services during development.
