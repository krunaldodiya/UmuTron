# Project instructions

This is the canonical project instruction file. The product contract is in docs/DESIGN.md.

- This app manages metadata and explicitly syncs supported Steam shortcut/artwork fields. It must never launch games, modify game files, choose Proton, or modify compatibility mappings.
- Save and import are local-only. Every Steam write requires a fresh change preview and explicit user confirmation. Refuse writes while Steam runs. Preserve unrelated shortcuts and existing launch IDs.
- Keep tests isolated. Never test against a real Steam installation or user games. tools/ui_smoke.py uses a temporary mock Steam folder.
- Credentials stay in the private provider configuration, outside exported ZIPs and Git. Do not commit downloaded game artwork, private paths, account identifiers, logs or user libraries.
- Use the system Python for GTK. Keep core logic independently testable with standard-library Python.
- Required checks: python3 -m unittest discover -s tests -v and python3 -m compileall -q steam_library. For GUI changes on a desktop: /usr/bin/python3 tools/ui_smoke.py and inspect resulting synthetic screenshots.
- Preserve current user work when refreshing the demo. Never stop Steam, running games or unrelated development services.
