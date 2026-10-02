# Prefix feature validation

Candidate 0.4.13 based on clean `c75aace` / 0.4.12. Runtime/data migration: none. Game library schema remains unchanged. Changes remain local; no push, PR or publication is authorized.

Risk classification: R3 because runtime replacement and process lifetime/locking affect shared prefixes. Risk owner is the requesting user. Feature confirmation is required for every actual maintenance operation; implementation/testing approval does not authorize downloading or installing a real runtime.

## Observed checks

- Baseline: 51 unit tests passed before integration.
- Candidate: 79 tests passed with system Python, including existing launcher/installer regressions and 28 new checks.
- `XDG_RUNTIME_DIR=/tmp/game-library-prefix-tests /usr/bin/python3 -m unittest discover -s tests -v` — passed (7 seconds).
- `ruff check --isolated --select E9,F63,F7,F82,F401 game_library tests` — passed.
- `/usr/bin/python3 -m compileall -q game_library tests` — passed.
- System GTK imports of `game_library.app.Window` and `game_library.prefix_tab.PrefixPanel` — passed without opening a window.
- Actual stage-transition method exercised with inert widgets: Prefix remains selected during polling; original installer/executable stages and confirmation still transition correctly.

Fixtures cover uncreated prefix with no writes; native VC2015/2019 file versions independent of seeded registry version; Wine builtin false-positive rejection; wrong architecture, below-minimum and incomplete native files; game-local isolation; 1,290 broken links; mapping/symlink avoidance; hardlink deduplication; sparse allocation; cancelled/bounded scans; explicit recipes and architecture/minimum selection; satisfied-requirement denial; exact context change denial; trusted-host rejection; global and cross-library prefix locking; external process detection; network failure; cancellation with lock retention; and native-evidence verification after a synthetic installer process. All child processes are inert fixture scripts in temporary directories. Network is mocked in runtime supervisor tests.

## Failures found and corrected

Initial fixture execution used the sandbox's read-only `/run/user/1000`; subsequent runs use an isolated private `/tmp` runtime directory, including child supervisors. Initial cancellation was caught by a broad `OSError` path in size inspection; `InterruptedError` now propagates. Both corrections are exercised by the passing suite. The bounded dropdown follow-up briefly introduced an undefined label variable in the separate Advanced selector; lint identified it before review/deployment, and that unrelated selector was restored.

## Boundaries and remaining validation

Native desktop control is explicitly unavailable in this task. `tools/ui_smoke.py` and screenshot inspection were not run; raw input, AT-SPI and alternate screenshots were not used. GTK import and inert widget checks do not establish layout or interactive EULA behavior. No real runtime was downloaded, no license accepted, no real prefix changed, and no game/installer started or stopped.

Inventory is bounded and conservative. Native origin is based on PE metadata/Wine image markers, not Authenticode. Missing registry/file evidence can produce Unknown or Partial. Only selected core runtime DLLs and adjacent game files are inspected. Game-specific prerequisites and optional runtime components remain unknown. Process/advisory locking does not stop a user from launching an external tool after the check.

## Primary references consulted

- [Wine registry template](https://github.com/wine-mirror/wine/blob/master/loader/wine.inf.in): VC runtime registrations can be seeded by Wine.
- [UMU manual](https://github.com/Open-Wine-Components/umu-launcher/blob/main/docs/umu.1.scd): WINEPREFIX and PROTONPATH identify the selected context.
- [Microsoft supported VC++ downloads](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist): architecture and minimum-version requirements; current official v14 links; legacy support boundaries.
- [Microsoft redistributable options](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files): install versus repair/uninstall, interactive defaults and no-restart option.
- [Microsoft .NET versions](https://learn.microsoft.com/en-us/dotnet/framework/install/versions-and-dependencies): .NET Framework 4.x in-place replacement.

Initial independent review found no blocking findings and independently passed all 74 tests then present. Additional runner-version, post-download downgrade and dropdown regression coverage raises the final suite to 79 tests; the changed candidate is submitted for scoped re-review before deployment.


## Final independent review
The independent reviewer reported no blocking findings, reran all 79 tests successfully (6.916 seconds), and matched every production Python file against `candidate-hashes.json`. Reviewed changes include the post-download downgrade recheck and the approved dropdown label/discovery correction. Native GUI and real runtime limitations remain unchanged.
