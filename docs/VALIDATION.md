# Fullscreen detail simplification — 0.4.18, 2026-10-02

Removed only the “Your next adventure” heading and separate logo widget above the fullscreen game title. The summary starts directly with the title; GTK closes the removed widgets' spacing. Left cover, contextual Play/Stop, backdrop, metadata and Game Info remain. The home hero, desktop edit/setup controls, Settings Activity/Appearance access and stored artwork are unchanged.

The extended focused native checks detected the old heading before the edit and pass afterward. They verify one retained detail cover, no redundant heading/logo, title as the first summary child, preserved home hero/backdrop, and existing navigation, cancellation, Prefix/setup and launch-state contracts. All 85 core tests, Ruff and compilation pass. The full native UI smoke passes using the corrected capture helper and unchanged focus assertions. Isolated native detail renders at 1920×1080 and 1024×600 were inspected; 1280×720 and missing-art renders are also retained. These are test renders with Play disabled, not live desktop screenshots.

Delivery uses the existing installer with an idle operation lock, current-source conflict checks, visible source/install backups and library/artwork hash verification. No real game, installer, live app or desktop is restarted. Explicit Exit and reopen when idle loads the new UI. Physical gamepad and live desktop capture were not performed; existing GTK deprecation/measurement warnings remain in fixture logs.

---

# Tray menu simplification — 0.4.17, 2026-10-02

Activity and Appearance are removed only from the tray menu and its event routes. Settings keeps its Appearance control and adds a small Activity action in Diagnostic logs. It closes Settings and opens the existing viewer, including when that viewer was already open; no new logging behavior was added. The remaining tray order is Show UmuTron, Switch to Fullscreen, Switch to Desktop, Settings, Exit. Fullscreen rendering and the remaining Settings behavior are unchanged.

The new native `tools/settings_checks.py` failed before the Activity route existed and passes afterward; it checks Appearance theme changes and first/repeated Activity entry without launching anything. Three menu-contract tests failed before the change and pass afterward; the full suite now has 85 passing tests. Private-bus tray integration passes for registration, host loss, icon activation, menu contents and every retained action. The existing single-instance integration passes with isolated app data/private D-Bus; the test-only wrapper substitutes the Broadway renderer for its desktop Cairo default without changing its assertions. Compilation and Ruff checks pass. The complete native UI smoke now passes, including the original Play-focus and navigation assertions. The earlier focus failure was reproduced identically on the hash-verified pre-tray 0.4.16 runtime and final 0.4.17 runtime under the same isolated renderer. In both, Play remained the logical focused control while the screenshot helper's hide/present cycle made the window inactive and removed its outline. A minimal native probe showed Game Info open/close preserved focus; capture remapping caused the failure; restoring the saved logical focus through GTK restored the normal focus notification and outline. The smoke screenshot helper now restores its prior fullscreen focus after capture. No assertion was removed or weakened, and no production focus/rendering code was changed. Native desktop tray capture is unavailable; menu contents are verified through the actual DBusMenu protocol, not a live desktop screenshot.

Delivery uses the existing installer only while the operation lock is idle, with current-source hash checks, visible source/install backups, and library/artwork preservation checks. No active application, game, installer or desktop is restarted. Explicit Exit and reopen when idle is needed to refresh an already-running tray.

---

# Fullscreen cinematic redesign — 0.4.16, 2026-10-02

The implementation remains Python GTK4/libadwaita. No website or web prototype was created.

- 82 core regression tests pass with system Python and a private temporary runtime directory.
- Compilation and Ruff undefined/unused-code checks pass.
- The complete `tools/ui_smoke.py` passes using GTK's isolated Broadway display and temporary inert fixtures. Coverage includes metadata-first Add Game, readonly detail, metadata Save/Cancel, installer/preinstalled setup and confirmation, launch guard/Stop, ZIP, Proton Manager, search/options, keyboard/controller navigation, immediate Back selection, reduced-motion rail behavior and controller scrolling.
- `tools/fullscreen_checks.py` adds equal-cover dimensions, corrupt/missing art clearing, empty library, keyboard/grid navigation, queued detail focus after immediate Back, late metadata completion after Cancel, Prefix preservation, Stop cancellation, runtime progress and a visible primary action at 1024×600.
- `tools/fullscreen_preview.py` renders actual GTK widgets at 1920×1080, 1280×720 and 1024×600. It refuses to use a live desktop backend. Optional library input copies public metadata/artwork into temporary demo data, discards launch/prefix configuration and disables Play. Saved previews are isolated native test renders, not live desktop screenshots.

Broadway fixture checks wait for allocations rather than assuming a fixed delay. Render capture remaps only the temporary test window because background browser frame acknowledgements may be throttled. Manual Page Up/Down uses current viewport bounds, without pulling the page back to a focused button; moving focus or focusing Play restores native focus scrolling.

Native test logs include deprecated Adw/GTK test API notices and GTK measurement/focus warnings. They are retained as limitations rather than treated as full accessibility or desktop-integration acceptance. No live Wayland/X11 capture/control, physical gamepad/TV, real game, downloaded installer, desktop restart or Gaming-profile activation was performed. Tray/single-instance implementation is unchanged; the separate live-desktop instance check was not run.

The established user-level installer is used only with the operation lock idle. Delivery checks candidate/source identity, preserves pre-existing dirty work, retains source/installed backups in the visible task folder and compares library/artwork hashes before and after. Existing app windows are not restarted; explicit Exit and reopen loads the new code.

---

# UmuTron validation — 0.4.15, 2026-10-02

The user's generic gear icon and dock menu containing only All Windows/Quit exposed a real application-to-desktop-entry identity mismatch. The running Gio ID was `io.github.game_library_launcher`, but a lookup of `io.github.game_library_launcher.desktop` failed. Checking only the old entry's display name and tray icon had missed this; a stale menu cache was not an adequate explanation for the dock symptoms.

- Three new regression tests failed before the fix and pass afterward: canonical desktop ID resolution with one visible entry, a launchable NoDisplay legacy entry without a competing WM_CLASS claim, and the actual GTK initializer executed with inert stubs to check shared app/program identity. The complete 82-test suite passes with a temporary runtime directory.
- Ruff `--select F`, Python compilation and whitespace checks pass. Both installed desktop entries pass `desktop-file-validate`; all installed Python modules and `run.py` match source.
- Fresh GLib lookup resolves the canonical entry, UmuTron name, existing icon and exact StartupWMClass. GLib's visible catalog has exactly one UmuTron entry. The compatibility entry is still resolvable and launchable, with `NoDisplay=true` and no `Hidden=true`.
- Normal launches through both installed entries succeeded and reached the same D-Bus application instance after deployment. The installed 0.4.15 code started a new process normally; no app was killed and the desktop session was not restarted. The application exports no remote quit action.
- GNOME favorites were read and retained byte-for-byte; no launcher favorite existed and none was added. Workstation profiles and all 73 library/artwork hashes remain unchanged. The existing operation lock was idle during installation; no real game, installer or live mode switch was executed.

Native UI APIs remain disabled. The Wayland mapping is grounded in the preserved Gio ID, GTK's application identity contract and the now-matching desktop filename, not a native window inspection or screenshot. Actual dock artwork, pin menu behavior, and X11 window properties remain visual/session acceptance checks. The private-bus tray protocol check is recorded separately from visual dock acceptance.

## Earlier branding verification — 0.4.14


- All 79 launcher regression tests pass with system Python and a temporary `XDG_RUNTIME_DIR`; runtime/game/installer fixtures are inert. The initial sandbox run could not write runtime locks, so the successful run isolated that directory. No real game, installer or runtime maintenance was executed.
- Compilation, Ruff `--select F` with caching disabled, and `git diff --check` pass. Compilation output was redirected outside the checkout.
- Private-bus tray protocol tests pass, including the stable item ID, **UmuTron** title/tooltip, **Show UmuTron** menu action and shared `game-library-launcher` icon name. The existing Gio registration deprecation warning is non-fatal.
- The original `assets/umutron.svg` parses without external references and renders through GdkPixbuf at 16, 22, 24, 32, 48, 64, 128 and 256 pixels. Rendered asset previews were inspected on light/dark backgrounds; no generated bitmap was added to the repository.
- A no-write installer rehearsal verified every output. The existing user installer then updated the installed app, desktop entry and SVG. All 18 installed Python modules plus `run.py` match source bytes; the installed SVG matches the source; desktop-entry validation passes.
- Before installation, the existing operation lock was idle and host inspection found no relevant launcher/game processes. Installation did not start, stop or restart an app or operation. All 73 existing library/artwork file hashes remained unchanged; prefixes, saves and external game files were not read or modified for branding.
- Workstation Modes now displays **UmuTron (fullscreen)**. Its 43 isolated non-GUI tests, compilation, lint and whitespace checks pass. Installed-target inspection with unrelated discovery mocked confirms `/usr/bin/python3 ~/.local/opt/game-library-launcher/run.py --fullscreen`, stable `app:game-library-launcher` resource identity and the existing saved Gaming `start` choice. The saved profiles file is byte-for-byte unchanged.
- The prior local 0.4.13 feature changes were preserved. Technical app/storage/package IDs, existing install paths and Git remotes were retained. No commit, push, publication or account change was made.

Native UI control and screenshots were explicitly disabled for this task. `tools/ui_smoke.py` and the GUI-dependent `tools/instance_smoke.py` were therefore not run; desktop/tray visual acceptance and actual single-instance activation remain unverified for this revision. Earlier screenshots and historical GUI results below predate the rename. Live Gaming/Development activation remains on hold and was not performed; development services, tests and extraction work were not interrupted.

To load changed code, use explicit **Exit** and reopen UmuTron after any active operation finishes; closing alone can hide to tray. Close/reopen Workstation Modes to load the changed catalog label. No data or profile migration is required.

---

# Validation — version 0.3.5

Validated on Ubuntu 26.04, 2026-09-30, with system Python and native GTK/libadwaita.

## Final checks

- All 39 isolated regression tests pass.
- Python compilation and Ruff undefined/unused-code checks pass.
- Native GUI smoke passes: read-only detail, hero/cover/logo, modal Save/Cancel, metadata-first search/select/save/detail with artwork and no launch configuration, optional manual fallback cancellation, subsequent executable/installer configuration, harmless installer execution and executable confirmation, advanced settings/reset, scrolling, default public metadata and missing-credential provider switching, active operation controls, ZIP recovery and Proton Manager.
- Private-session D-Bus tray integration passes: registration, host detection/loss, Show Launcher, activation and Exit menu.
- Separate-process instance test passes: the second launch activates the first instance and exits without launching a game or installer.
- Live credential-free public Steam search and details lookup passed for Portal 2. No account/client is required.

## Preservation and lifecycle

Temporary inert runners exercise completed/nonzero installer runs, cancellation including initial preparation, retry, reopen recovery, executable confirmation, pinned prefix/runner continuity and duplicate/cross-instance launch rejection. Installer exit alone leaves selection pending. Play rejects setup executables and unconfirmed installations. Cancel never deletes installed files. Stop addresses only verified app-owned process identities; detached descendants remain tracked.

Native modal Cancel preserves saved metadata/art references and launch overrides. ZIP/library tests retain UUIDs, artwork hashes, legacy records and optional installation context. Backups exclude binaries, saves, prefixes, credentials and journals. No real game, downloaded repack installer or new license agreement was run/accepted for validation.

Close hides only with a registered tray host; otherwise it minimizes. Reopening reuses the existing window. Host loss restores accessibility. Active explicit Exit warns and permits cancellation; confirmed Exit leaves the owned supervisor operation running, recoverable on reopen. It does not stop unrelated processes.

## Remaining acceptance boundaries

Real Windows installer compatibility, gameplay and real desktop tray-menu visual acceptance remain user checks. Authenticated IGDB/SteamGridDB requests and full upstream runner downloads are covered by fixtures rather than credentialed live calls. Accessibility labels/tooltips are checked, not a comprehensive accessibility audit. GTK focus and deprecated test-API warnings occurred without test failures; the private-bus instance test emits portal warnings because it isolates the normal session.

Forced OS/supervisor termination is outside graceful cancellation guarantees. Mutable external runner files can change independently of the app. Backups of game data/prefixes remain separate from library ZIPs.

## Installed delivery

User-level installation and desktop-entry validation passed. All installed Python modules match final source bytes. The existing library/artwork snapshot (existing files) was unchanged by installation; saves, prefixes and game files were not touched. The previous 0.3.1 instance was opened normally without startup errors; the 0.3.5 change was exercised through the isolated native GUI checks. The current desktop reports a registered tray host and the app StatusNotifierItem. Real icon/menu interaction remains a user visual acceptance check.

The installed 0.3.5 update does not restart an existing window. Use explicit Exit and reopen to load it; closing alone hides to tray. No game or installer was automatically started. Source and documentation are delivered together.

## Two-stage installer setup

Already installed shows executable and working-directory selection only. Install from installer first shows setup selection and installation controls; game executable selection is hidden until the installation attempt ends. Step 2 uses the same executable/working-directory flow and requires explicit confirmation, retaining the installer prefix and Proton version. Failed or cancelled attempts may also leave files, so selection remains available for recovery without implying success.

## Stage tabs

Manage Game uses two stage tabs, Install and Game setup, with only one enabled at a time. The I already have installed the game switch skips/disables Install and activates Game setup. Otherwise Install is active until the attempt ends, then Game setup becomes active for executable confirmation. Return to installation / retry switches back safely without deleting files or losing prefix/runner context. The switch is disabled while an operation is active.

## Public catalogue artwork repair — 0.3.5
Steam asset manifests supply modern hash-qualified cover and hero URLs, with legacy fallback. Cricket 26 cover/hero were downloaded live and added to its existing entry without replacing saved artwork or changing launch configuration. Its separate logo was unavailable through these public endpoints. Fixture tests cover hash paths, rejected paths and API failure fallback; native smoke uses isolated data.

## Fullscreen delivery — 0.4.0, 2026-10-01
42 isolated core tests pass, including action debounce/background suppression and default-mode validation/persistence/ZIP. Native GUI checks exercise library/detail navigation, readonly guards, no title bar/window controls, Exit fullscreen popover, detail scrolling, default next-start mode and active-operation preservation with inert fixtures. SDL2 virtual-controller checks cover face buttons, stick movement and suppression outside focused UI. Private D-Bus tray checks include both mode actions; the separate-process instance check remains required. Lint and compilation are run against final source. No real game or installer is launched. Physical gamepad/TV/gameplay behavior remains user acceptance; synthetic screenshot fixtures are not added to the user's library.

Fullscreen layout checks include 1920×1080, 1280×720 and 1024×600 allocations, reachable scrollable content, horizontal selection scrolling and stable hero/rail position across games with differing artwork/text. Physical TV scaling and controller acceptance remain user checks.

## Console navigation refinement — 0.4.1
42 core tests pass. Extended native smoke exercises Games/Library/Home, installed-only filtering, missing/portrait artwork and one/two-line titles, equal card heights/top alignment, header tab activation through controller input, control-only focus cycling, stable row positioning, 1080p/720p/1024×600 allocations and small-display grids. Native screenshots use only fictional temporary data. Compilation and lint pass; game execution code is unchanged. Physical TV/controller gameplay remains a user acceptance check.


## 0.4.2 verification
Native checks cover repeated Back remaining fullscreen, removal of Home and desktop header utility actions, the two fullscreen exit options, and existing responsive grid/navigation flows. Tray checks exercise Activity, Settings and Appearance callbacks alongside mode switching and Exit. Core regression tests, lint and compilation are required before installation. Real games and installers are not run.


## 0.4.3 verification
43 core tests pass, including observed download bytes and missing-file/unknown-total behavior. Native regression coverage exercises increasing archive bytes, the visible preparation panel and hiding it when Running. Synthetic fixtures only; no real game was launched during validation.


## 0.4.4 verification
Regression coverage includes bounded descriptions, complete source preservation, full-description Game Info, focused-button CSS, cover/Play layout and local download status placement. Native screenshots use synthetic fixtures; real games are not launched.

Final 0.4.4 validation: 44 core tests and the native GUI smoke pass. Header focus is separate from activation; game-card activation and X do not launch. Play/Stop and cover bounds match; full-description dialog and shortened views preserve source text. Physical controller/TV acceptance remains a user check.


## 0.4.5 verification
44 core tests pass. Final native smoke verifies Games → Library → Settings direction navigation, section activation retaining header focus, Down entering the cards, and the Library hero changing without extra metadata panels. Native synthetic screenshots were inspected; compilation, lint and whitespace checks pass. No real game was launched.

## Detail navigation — 0.4.6

Back restores the selected card in Games and Library rather than resetting to the first item. Desktop Back also retains the library filter and scroll position. The redundant detail launch-status label is removed; Play/Stop and live preparation progress remain. Native regression checks cover returning to a non-first card in both fullscreen sections and a filtered desktop library.

## Immediate Back focus — 0.4.8
Library rebuilding keeps other cards out of automatic focus fallback until the selected card receives focus synchronously. Selection/background never pass through the first card on Back. A layout callback adjusts scrolling only and does not move focus. Native checks record every preview during Back and require immediate selected-card focus, with no intermediate first-game preview.

## Fullscreen input, sliding rail and Search — 0.4.10
Keyboard navigation is captured before grid children consume arrows, using the same control-only routing as gamepads. Games pans its overflowing icon rail smoothly toward the focused card, with no horizontal scrollbar; reduced-motion settings disable the transition and Back restores position immediately. Search sits left of Settings and filters the saved library; selecting a result opens read-only detail, never Play. Native checks cover grid arrow dispatch, intermediate/end animation positions, reduced motion, header navigation and local search.

Games-only icon artwork is reduced to 88px; selected/focused chips render at full size and the others at two-thirds scale (1.5× selection ratio), with a short transition and stable row height. Library grid cards have no scale effect and retain their previous dimensions.

Fullscreen Settings is a separate modal (like Search), with Exit fullscreen and Exit actions; controller Back dismisses it without leaving fullscreen. Game arguments belong to Manage Game → Game setup, alongside executable and working directory. Advanced runner/prefix reset preserves those arguments.

Final validation: 44 core tests pass, native isolated GUI smoke passes (including modal Save/Cancel, keyboard grid navigation, sliding/reduced-motion behavior, Search and Settings modal, and arguments retention). Lint, compilation and whitespace checks pass. Synthetic screenshots inspected; no real game/installer or physical TV/controller test performed.

## Per-game compatibility and diagnostics — 0.4.11

47 core tests pass. New cases cover validated per-game DLL overrides, rejection of injected/malformed settings, inherited override isolation, ZIP preference round-trip with diagnostic exclusion, and a harmless failing runner writing its log into the automatically prepared folder. Native GUI smoke passes with collapsed advanced settings, compatibility Save/Cancel/Reset, and existing browse/installer/tray/runner flows. Updated synthetic Manage Game screenshots inspected. Compilation, lint and whitespace checks pass. No real game or installer executed or stopped for this release; physical controller and real-game diagnostic replay remain untested.

## Diagnostic retention — 0.4.12
51 tests pass, including age expiry, per-file tail trimming, total-size eviction, preservation of non-log files/prefixes, symlink exclusion, and active-operation lock protection for Clear all. Native GUI smoke passes with Clear all confirm/cancel. Diagnostic settings screenshot inspected. Compilation, lint and whitespace checks pass. No real game started/stopped for this update. Live log files are not truncated until the operation completes.


## Proton Manager lifecycle — 0.4.19

Native isolated GTK Broadway fixtures cover the three family tabs, cached-first background catalogs, automatic scroll pagination, installed/default/uninstall states, referenced removal refusal, cached offline state, a visible Setup selector and late-response cancellation. Previews use synthetic release metadata and inert local archives, never live runner downloads or desktop capture. `tools/proton_checks.py --output <visible-folder>` must run with `GDK_BACKEND=broadway`, an isolated loopback Broadway display and a connected browser.

Core tests exercise the actual launch supervisor with only its network transport replaced by a local fixture archive: exact PROTONPATH after verified install, no execution/prefix on download failure or cancellation, successful retry, and runner leases retained for an orphaned descendant. Two separate Python processes request the same build and perform one download. Additional checks cover inherited defaults, installer continuity, checksum/source/architecture/space rejection, cancellation isolation, reference reassignment, and managed-only removal preserving fixtures representing games, saves and prefixes.

Legacy UMU/GE automatic policy resolution, actual vendor binaries, real game compatibility, hardware controllers, Valve distribution, and Wayland/X11 capture remain outside this isolated acceptance run. No live games, installers, runner installations/removals or profile activation are performed. CI uses Ubuntu’s system Python and native GI packages because tray tests require GLib; a generic setup-python interpreter lacks that binding.
