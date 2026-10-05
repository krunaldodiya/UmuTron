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


## GE/UMU manager simplification — 0.4.20

106 core tests, Ruff F checks and Python compilation pass. The native Proton fixture asserts exactly GE-Proton/UMU-Proton tabs, preserves a saved Valve global default and custom symlink selection without rewriting the library, and distinguishes two installed same-version UMU copies while retaining their selectors and removal rules. Cached/background results, pagination, explicit install/default/uninstall, cancellation, offline retry and stale Setup callbacks remain covered. The complete native UI smoke suite also passes.

Inspected actual GTK test renders at 660×720 show both tabs and the differentiated copy headings without clipping. These are temporary Broadway fixtures with inert runners, not live-desktop screenshots or real vendor installations. No launch/download/uninstall implementation changed. Existing runners, prefixes and saved configuration are not migrated or removed.


## Single protected UMU baseline — 0.4.21

108 core tests, Ruff F checks and compilation pass. New persistence fixtures establish that fresh libraries inherit UMU-Latest without installing GE or persisting a version pin, and existing explicit GE/UMU/custom selections survive reopen.

The focused native GTK fixture verifies exactly one protected baseline row despite separate same-version installations, no removal action or verified-receipt claim for the UMU-managed folder, unchanged baseline presentation under a wrong receipt elsewhere, and no downloads or UMU catalog calls when Settings opens. A manual GE default survives reopen and background refresh; explicit baseline selection retains the mutable alias as its reported version changes. Saved custom paths and existing folders remain intact. GE catalog/pagination/install/default/removal guards/cancel/offline and stale Setup callbacks pass. The full native UI smoke suite passes.

Inspected 660×720 GTK test renders show a single baseline and optional GE catalog without copy labels. No real runner, game, installer or prefix was created/deleted by these fixtures; no live-desktop or hardware-controller QA is claimed. Prefix/runtime recovery remains a separate undeployed POC.


## UMU catalog and tab synchronization — 0.4.22

108 core tests, Ruff F checks and Python compilation pass. The focused native GTK fixture checks header active/checked/accent states and mapped page content through 30 rapid switches, repeated selected-tab activation, Left/Right/Home/End navigation, held background refreshes for both catalogs and Settings reopen. It restores UMU cached/background/paginated results, exercises inert UMU installation and default selection, and verifies an older installed release targets its own removal path. The protected baseline appears once despite a separate same-version installation; wrong receipts cannot confer identity, exact defaults remain exact, and UMU-Latest remains mutable. Opening Settings never downloads a runner. Offline caches, preserved custom paths, cancellation, reference guards and stale Setup callbacks remain covered. The full native UI smoke suite passes. A read-only official GitHub catalog check parsed seven available x86_64 UMU releases; no runner archives were fetched.

The initial standard GtkStackSwitcher probe did not reproduce the reported mismatch. The explicit header binding and hidden-page focus guard address the synchronization risk; live-desktop reproduction is not claimed. Inspected 660×720 native GTK test renders show the active GE/UMU header matching its content and one baseline plus older UMU entries. These are isolated Broadway fixtures with inert archives, not live-desktop screenshots. No real game, installer, runner or prefix is created or removed; the separate prefix recovery POC remains undeployed by this update.


## Single-screen Setup and installer modal — 0.4.23

114 core tests pass, including new read-only setup-state boundaries for preinstalled files, disconnected/missing configured paths, incomplete/legacy installer records, wrong executable selection and unavailable working directories. Ruff F checks and Python compilation pass. The initial native contract assertion failed against the old stage/Prefix tabs before implementation.

The isolated native Setup fixture covers one tab-free form; Install game… and Reinstall… in the same More popover; repeated modal opening, Back/Escape and focus return; preserved arguments, runner selection and installer drafts; parent Cancel; stale picker results and stale/changed confirmations; an operation becoming active after confirmation; busy controls and owned installer progress/cancellation visibility in a fixed footer, with bounds checked to avoid scrolling; and explicit final-confirmation dispatch. A legacy installer record without a session accepts an existing executable through the real validation service without creating a prefix or executing anything. The fixture initially rejected a prefix placed beneath its game folder; the fixture layout was corrected and the validation rule was kept.

The full native UI smoke includes real execution of an inert local installer stub, saved prefix/runner continuity, reopening Setup, retry-modal access and explicit installed-executable confirmation. Proton and fullscreen regressions cover catalog/default preservation, stale Setup callbacks, metadata-first Add Game, read-only details, keyboard navigation, Play/Stop and the one-game guard. No vendor installer, game or runner download/uninstall is used by these checks.

Inspected GTK test renders cover 780×700 Setup, 640×560 installer, both More menu variants, reinstall confirmation, active installer controls and 480×540 Setup. These are native Broadway/WidgetPaintable test renders with temporary synthetic data, not live-desktop screenshots or hardware-controller acceptance. Existing GTK deprecation/focus/measurement warnings are present in fixture logs; behavior assertions and rendered layouts pass. The runtime/installer services and independent prefix-recovery POC are unchanged.


## Native Home / Library / Store candidate — unreleased

See [the complete candidate validation record](CATALOG-VALIDATION.md) for 139 core tests, native route/Setup/Proton checks, isolated lifecycle checks, independent uninstall/history review and visual limitations. This candidate is separate from the installed Setup 0.4.23 and the published 0.4.22 main branch.


## 0.4.25 scoped regression release

182 isolated core tests pass. The native UI smoke and dedicated history, membership and detail-action fixtures pass. Process detection now ignores unresolvable or exiting non-game helpers without weakening selected-file/ancestry/PID evidence. Home refreshes atomic history updates. Steam-linked Store details reuse the existing UUID and preserve local configuration, with unknown/ambiguous mappings remaining unmerged. The shared fullscreen detail composition is restored from matched 0.4.23/0.4.24 native test renders at 1920x1080 and 1280x720; desktop and missing-art/long-title compact checks remain separate evidence. No real game run, retrospective history insertion or live desktop capture was performed.

## Home setup chronology — 0.4.26

The separate Home extension has 190 passing core tests. Eight focused setup-history cases cover metadata-only/canceled exclusion, successful persistence, unchanged saves, launch-preference edits, changed executable paths, installer confirmation, missing files, legacy undated ordering, persistence rollback, timestamp validation and ZIP restore. The existing installation lifecycle case additionally checks no timestamp at installer start, a timestamp after executable confirmation, and no bump on repeated confirmation.

`tools/home_readiness_checks.py` passes with a temporary inert library at1920x1080,1280x720,1024x600fullscreen and900x700desktop. It verifies Save/Cancel/noop, separate play/setup lists, legacy dates left absent, unavailable-file labels, full-card visibility, Down scrolling, return-to-hero focus, shared detail Back including a game present in both sections, controller method navigation and reload. The focused between-frame reveal is guarded by the current route/generation and logical focus. The history fixture now preserves the actual selected existing-setup game when the first play-history record arrives, rather than assuming an initially empty Home has no selectable game.

Recent-play refresh, fullscreen route/async/cancellation/focus and full native smoke all pass on the final candidate. The smoke includes Store/shared detail, Setup cancellation/save, inert installer confirmation/prefix continuity, runtime/one-game guards, backup, Proton and tray/Exit fixtures. Ruff F and compile checks pass. Test-only subprocess and loopback fixtures required approved execution outside the restricted shell sandbox; core tests used a private temporary runtime directory. No real game/installer or profile was started.

The Home images are isolated GTK Broadway/WidgetPaintable test renders with copied public artwork and synthetic play/setup timestamps, clearly labeled and Play disabled. They are not live desktop screenshots or evidence of real gameplay. Inspected outputs include fullscreen top/grid, missing-art and missing-file state, compact layouts and windowed layout. No hardware gamepad was exercised. Older configured records remain undated; there is no metadata or history migration.

Independent review identified and reproduced one inconsistent hero status for a ready setup absent from play history. The corrected selected-game lookup includes both Home collections; the native fixture now explicitly asserts Play with no contradictory Setup message when history is empty. Independent persistence review passed eight focused tests and eleven additional probes. The fixture also requests a native frame before post-Back geometry checks: a background Broadway route can retain zero allocation until that frame, which is not a completed layout. Geometry assertions remain enforced after positive allocation.


## Header search cleanup and aligned detail actions — 0.4.26

The final local release retains the independently reviewed Home chronology extension. The redundant fullscreen header search and its separate modal are removed; Library and Store retain independent scoped search state. All shared detail primary states use one horizontal action row with centered gear/Game Info controls. Responsive layout no longer reparents the primary action into a separate cover column. Status and preparation progress sit below that shared row.

The pre-fix native reproduction measured Play 66 pixels below the gear and Game Info. `tools/header_action_checks.py` verifies 40 actual native control geometries: Add, Setup, Play and Stop; short text/art and long title/description with missing art; fullscreen 1920x1080, 1280x720 and 1024x600, and desktop 1120x800 and 640x540. Compact content remains vertically scrollable; the fixture scrolls to expose and verify full action-row bounds. Header Store/options navigation, responsive focus retention, independent Library/Store query restoration and unfiltered Home are exercised. No hardware controller or real game is used.

All 190 core tests, the full native smoke, focused Home chronology, fullscreen async/focus/cancellation and detail action-policy checks pass. Ruff F and Python compilation pass. Inspected previews use GTK Broadway/WidgetPaintable with inert synthetic state and public artwork, clearly labeled as test renders with Play disabled. The existing production HTTPS catalog configuration is preserved.


## Combined hotfix, Home/header and controller candidate — 0.4.26

The combined candidate has 212 passing core tests and 30 focused setup/history tests (16 accepted Cuphead regressions, eight existing chronology cases and six integration cases). The integration proves that valid Save and explicit confirmation preserve `installer_attempt` and stamp setup chronology once, while legacy hotfix-confirmed records remain undated on no-op; metadata/runner changes preserve dates, cancellation/invalid/non-success attempts never stamp, failed persistence rolls back all fields, and backup/reopen preserve identity and chronology together. Ruff F and Python compilation pass. Original installer, symlink/hardlink, changed-draft, retry-session and final Play guards remain covered. No source-feed, download-adapter or storage work is included.

Current native GTK gates pass: accepted Setup Save/reopen; combined Home/header behavior; full ui_smoke; 40 action-row geometries across fullscreen 1920×1080, 1280×720, 1024×600 and desktop 1120×800, 640×540; Home chronology/navigation at 1920×1080, 1280×720, 1024×600 and 900×700; fullscreen async/cancellation/navigation; observed-play refresh; detail Add/Setup/Play/Stop policy; and Setup modal/picker/confirmation cancellation. The fixtures use synthetic libraries and inert executables. The full smoke's installer stub is inert; no vendor installer, real game or user record is run or modified. Existing GTK deprecation/event warnings remain in logs without failed assertions.

The first multi-size attempt was clamped by Broadway's default virtual monitor to 1024×768 and correctly failed its requested-size assertion. Standard GTK fixture minimum-size requests now enforce each intended viewport; the actual width/height, bounds, alignment, no-overlap and scrolling assertions remain unchanged. Rendering uses the existing WidgetPaintable helper on an owned loopback Broadway daemon without a browser client. No browser-protocol manipulation, alternate screenshot utility, desktop capture, raw input or host display setting is used. All owned daemons are stopped.

A separate reviewer inspected only the controller navigation methods and independently ran 28 native-widget assertions against their exact source hash. This establishes scoped source/behavior review of the MenuButton admission and open-detail-popover handling. It is not an independent whole-candidate source review or release acceptance. The final combined immutable candidate still requires that review. Full-window native screenshots and method-driven keyboard/controller behavior are separate evidence; no physical-gamepad or live-desktop acceptance is claimed.

See `../design-qa.md` for paired visual comparison against the frozen pending design, exact dimensions, content/state normalization, typography/layout/color/asset/copy checks and limitations. All renders are labeled synthetic with Play disabled. Installed 0.4.25+cuphead.1 and original frozen artifacts remain untouched by this reconciliation; later delivery requires independent acceptance and fresh idle guards. No commit or push is performed.


## Desktop arrows and dynamic tray mode — 0.4.27

The exact accepted 0.4.26 source reproduces the missing desktop key routing: 18 of 27 focused native assertions fail across Home, Library and Store headers/cards. The corrected fixture has 76 passing native assertions. It checks header/card arrows, full focused-card visibility, three Back cycles per route, saved collection scroll, route changes, paging, resized desktop behavior, native search/selector/Tab/modified keys, modal/popover containment and fullscreen keyboard continuity. The wait conditions require the exact intended focus, real allocation and scroll values; elapsed time alone cannot pass them.

Stricter repeated-Back checks exposed Home cards that reflowed after a one-shot scroll adjustment, and deeper collection cards that remained outside the viewport. Focused browsing controls now recheck their scroll bounds through two stable native layout frames, fenced by the current route generation and actual focus. No long animation or timing sleep is added to application behavior.

The tray's five unit tests cover one opposite-mode action, menu revisions, query-time mode changes and stale action rejection. The native tray fixture has 63 passing assertions for repeated requests/acknowledgments, actual isolated window hide/restore, F11/options callbacks and Show/Exit dispatch. Production reads `Gtk.Window.is_fullscreen()` and `notify::fullscreened`; it never equates the requested layout flag with acknowledged window mode.

**Validation boundary:** isolated Broadway without a browser does not acknowledge fullscreen requests. The tray fixture therefore injects the getter's acknowledged values and emits normal GObject notifications, explicitly labeled in its report. The private-bus protocol exercises actual Gio DBusMenu calls/signals. These checks are not a live compositor/tray or hardware keyboard/gamepad acceptance test. Desktop key tests emit the in-process GTK key-controller signal and inspect real native widget focus and geometry. No host desktop APIs, raw input or protocol bypass is used.

The full core suite passes 214 tests, preserving the accepted Cuphead identity/setup chronology, Home, catalog, one-game and guarded-uninstall checks. All eight existing Setup, installer, Play and Stop method ASTs remain equal to 0.4.26. Storage assertion work is excluded. Final serial native/private-bus gate results and source hashes are attached to the immutable review record; local delivery remains gated on independent acceptance.

All 12 final serial fixture groups pass: desktop navigation, desktop tray mode, full UI smoke, header action geometry, Home readiness, fullscreen behavior, history, detail actions, Setup, controller navigation, tray protocol and single-instance lifecycle. The owned Broadway server is stopped. The run used nice 10 and idle I/O priority; recorded pre-gate I/O pressure stayed below its pause thresholds. Directly inspected 1120×800 Home, Library and Store renders show intact focused-card bounds and visible focus treatment; Home intentionally retains its scrolled Existing setups position. These images remain explicitly labeled native test renders with synthetic data and Play disabled.


## Browse navigation follow-up — 0.4.28 review 1, superseded

Independent review found a Home horizontal-rail regression that the short recent-history fixture below missed. Review 1 and its prepared delivery plan are blocked and preserved as historical evidence. The following results describe that candidate; they do not establish acceptance of the long-rail behavior.

The isolated installed-0.4.27 probe reproduces skipped Library/Store search inputs and unchanged bottom scroll when route controls take focus in both layouts. The requested Home headings also fail against that baseline, as expected. Fixture data includes genuine synthetic setup dates plus a separate undated game; production library files are never used or modified.

The candidate admits the native search control, preserves caret/Tab behavior and provides Escape to the current route. It reveals top content for route controls, fences stale layout/restore callbacks, and excludes window decorations from spatial navigation. The stricter fullscreen check reproduced a 306-pixel card in a 313-pixel viewport with impossible 10-pixel margins, plus a 196-pixel card in only 128 pixels at 900×600. Bounded reveal margins and a shared heading/card scroll area address those geometric constraints without reducing test visibility requirements.

The final matrix passes 511 assertions across 20 cases: Home/Library/Store in desktop/fullscreen modes at actual 1120×800, 900×600 and 1920×1080 allocations, plus two delayed Store-response cases. It verifies bottom-to-top visibility, rapid direction reversal, repeated Back, paging, native search keys, controller query submission, off-page selection fallback and stale queued restoration. Frame-based checks wait for actual focus/allocation/scroll conditions; elapsed time cannot establish success. The corrected baseline probe has 14 expected failures and 15 passes. Storage and the separately planned catalog-cache performance delta are excluded.

All 214 core tests, Ruff F, compilation and 14 native/private-bus fixture groups pass, including the new browse matrix, 76 prior desktop navigation assertions, 63 tray-mode assertions, 40 detail action-row geometries, Setup/modal cancellation, controller menu containment and single-instance lifecycle. Ten native images were directly inspected, including 1080p Home/detail and compact layouts. Captures are synthetic with Play disabled; no physical keyboard/gamepad or live desktop acceptance is claimed.

Validation ran serially at nice 10 and idle I/O priority. When system I/O stalls returned, only the exact owned header fixture was interrupted, and its renderer stopped. Previously successful groups were retained; the remaining groups ran after parent clearance and a low-pressure check. The interrupted diagnostic is preserved. The controller method-extraction fixture initially omitted the new mark_browse_input dependency; it now binds that actual method and passes its rerun. This fixture-only correction did not change the application bytes tested by the matrix or core suite. No required gate was waived. Source and evidence are frozen together for independent review before any local update.


## Long recent-rail regression — 0.4.28 review 2

The preserved review-1 probe reproduces five expected failures with 24 recently played games: Right steps 7–10 leave the focused card horizontally offscreen, and the scroll adjustment never advances. GTK focus-enter precedes notify::focus-widget, so the old focus-revision comparison cancels the animation that the same focus change just scheduled. The corrected animation follows its actual focused tile, route generation and scroll widget. A second reproduced race came from an initial allocation callback scrolling to a card after newer focus; that callback now also requires its original focused tile and route generation. These are the only two application methods changed from review 1.

The new long-rail fixture passes 468 assertions across desktop/fullscreen at actual 900×600, 1120×800 and 1920×1080 window allocations. It checks ten consecutive Right moves, direct deep-rail focus, rapid reversals, both-axis visibility, leaving for the vertical grid, stale callback cancellation, route replacement, an explicitly superseded initial allocation callback, detail Back, reduced motion, wraparound and unchanged saved records. Play remains disabled and all history/setup dates are synthetic.

An intermediate 1080p failure was traced to the screenshot helper hiding/presenting the fixture between input actions, which temporarily changed card allocation. All animation ticks retained the correct owner but saw compact geometry; the larger allocation arrived afterward. Navigation captures now optionally snapshot an already allocated frame without remapping. Exact size, focus and full-card visibility checks remain enforced; other fixture captures retain the existing default. Failed traces and the explanation are preserved in the review evidence, and no speculative per-frame target change remains in application code.

The fresh broader matrix passes all 511 assertions in 20 cases, including delayed Store completion in both layouts. The same runtime also passes all 214 core tests. Six long-rail renders were directly inspected, along with compact Library/Store and fullscreen detail examples. These are isolated native GTK renders, not live desktop or physical-input acceptance. The intermediate fullscreen Home test render has hero copy flush to the left edge; this callback fix does not change hero styling, and the separate visual-parity work remains outside this candidate.

All 13 established native/private-bus groups pass again on a fresh validation copy: reconciliation, desktop navigation, desktop tray mode, full UI smoke, 40 detail action-row geometries, Home readiness, fullscreen behavior, history, detail action policy, Setup/modal cancellation, controller navigation, tray protocol and single-instance lifecycle. Together with the browse and long-rail matrices, this is 15 fixture groups. Ruff F checks and compilation of application, tests and tools pass. The entire execution was serial at nice 10 and idle I/O priority, with low-pressure admission checks; the owned renderer stopped normally.

Review 2 freezes the corrected source, exact-source test receipts, ten inspected image hashes, reproduction evidence and both the full 0.4.27-to-candidate patch and incremental review-1 correction. Installed 0.4.27 remains unchanged pending independent re-review. Review 1 and its blocked delivery plan remain preserved; no Storage, cache-performance, backend rollout, commit or push is included.


## Store cache-first candidate — 0.4.29

All 231 core tests pass on the final Python source, including 17 new cache/work-queue regressions. These cover origin/query/genre/page separation, corrupt and oversized envelopes, nonregular cache files, invalid image content, atomic-cache-write failures, known totals above the request cap, exact snapshot fallback, bounded eviction, independent image/metadata work, coalesced same-key transport with independent returned values, in-flight limits, queue priority, cancellation capacity and shutdown ownership. Ruff F and compilation pass.

The targeted native performance fixture passes 31 assertions per layout (62 total). Cold cards appear while genres and artwork remain held, and a card opens the shared detail before those operations finish. Warm and reopened snapshots are visible before the held network refresh is released. Same-ID refresh preserves actual card widgets and focus; changed IDs retain newer search drafts or fall back to the first current card. Genre and pager changes preserve valid selection/focus. Old queries and obsolete artwork cannot repaint the newer route/render. Offline failure keeps validated results. Metadata/image provider peaks remain within three/two workers, and saved records stay unchanged.

The preserved-feature suite passes all 16 groups: browse navigation (490 assertions across three sizes and both layouts, plus delayed completion), catalog/Add, membership, setup/history reconciliation, desktop navigation, desktop tray mode, UI smoke, 40 detail action-row geometries, Home readiness, fullscreen behavior, history, detail action policy, Setup/modal cancellation, controller navigation methods, private-bus tray and single-instance lifecycle. Tests are serial with low I/O pressure admission and owned renderer teardown. No game, installer, profile or installed application is started.

An expanded test exposed an unsafe saved-taxonomy model replacement inside a Gtk.DropDown selection notification. The candidate now loads the saved taxonomy only when constructing the route; fresh taxonomy still arrives through guarded idle completion. Both final layouts pass the transition without the warning. An earlier untraced signal-11 fixture exit is preserved with its limits; its exact crash site was not established. Separately, the 1080p browse fixture was observing cached cards before their responsive allocation tick: 120-pixel covers later became 204 pixels and the required scroll advanced to 313 pixels. Its readiness check now requires current responsive flags and actual cover height before testing overflow. The legacy catalog fixture now explicitly opens Library and asserts explicit fullscreen/compact allocations. These fixture changes do not alter application geometry or waive behavior checks.

A second identical finite-delay fixture collected 36 samples: three repetitions for each source, layout and cold/warm/reopened phase, with source order alternated. Controlled provider delays are page 120 ms, genres 350 ms and uncached images 800 ms. Median first mapped, sensitive, fully visible cards for desktop were baseline 1,318/1,375/1,138 ms versus candidate 644/855/114 ms (cold/warm/reopen); fullscreen was 1,342/1,415/1,134 ms versus 375/589/100 ms. Raw samples, ranges, provider call timelines, model construction and native render delay are recorded separately. Warm/reopened page-plus-genre cache reads totaled 0.463–2.025 ms. The baseline has no immediate successful snapshot-read path. These are descriptive synthetic measurements, not public API latency or a production speedup claim; native scheduling remains variable.

Inspected images show the held-artwork first-card state and completed covers in both layouts at 1120×800, compact offline Store at 780×640, and the unchanged shared detail at 1920×1080. Every preview is an isolated native GTK test render with fictional data and Play disabled. The existing placeholder says “No cover art” while loading; distinct loading copy belongs to the separate visual-parity audit. No host recording, physical-input test or assistive-technology compliance is claimed. Read-only comparisons confirm installed/repository runtime remains accepted 0.4.28. The 0.4.29 source and evidence are frozen for independent review; delivery, Storage and backend rollout remain outside this candidate.


## Desktop visual parity — 0.4.30

The separate presentation candidate is based on the independently accepted 0.4.29 source; installed 0.4.28 remains unchanged. The new inert native fixture passes 83 assertions covering the compact Home font, long titles, missing artwork, bounded detail, palette changes, action visibility, fully revealed cards, native search keys, empty-query recovery and return from fullscreen. All 17 native groups pass, including 492 browse assertions at three sizes in both layouts, 40 action-row geometries, metadata Add/membership, asynchronous state, Setup save/cancel, Play/Stop and one-game guards, history, controller method dispatch and private-bus tray/instance behavior.

Screenshots are synthetic native GTK test renders with fictional data and Play disabled. Banner-free captures preserve production viewport geometry and are labeled through filenames and evidence receipts. They do not verify a live compositor, physical controller, assistive technology or actual gameplay. The review evidence includes matched baseline/candidate source hashes and pixel comparisons; no source or installed-app delivery is part of this candidate.

All 231 core tests, Ruff F and compilation pass on the final runtime. Separate held-response Store fixtures pass 62 assertions across desktop/fullscreen. The matched gallery contains 28 before/after pairs plus 14 focused edge-case images; all 12 fullscreen pairs are byte-identical. Two stale-painted desktop Store images are explicitly rejected and replaced with fresh single-route captures from identical source and fixture with matching viewport, focus and geometry. Originals and provenance remain in evidence. No live compositor or hardware acceptance is inferred.

Evidence clarification after independent acceptance of 0.4.30: the two original Store images and their repeated captures have identical SHA-256 values. The prior stale-paint correction narrative is unsupported by the saved PNGs. Treat those pairs as corroborating duplicate rerenders. The accepted immutable evidence is unchanged; the separate visual-parity-accepted.json records this correction and the acceptance receipt.

## Search/Filter and honest size disclosure — 0.4.31

The user's final scope removes Sort from Library and Store in both modes. The final catalog transport/cache module is byte-identical to accepted 0.4.30; no new sort parameter or backend sort deployment is needed. Library keeps its default title order, and Store keeps existing provider default/relevance ordering. The detail adds one read-only Installation size · Unknown row. No download lookup, payload action or fabricated byte value is introduced. Source-provided file_size is not established as installed size; backend feed size_bytes is not a game size.

The Search/Filter fixture passes 297 navigation/state assertions across both routes and desktop/fullscreen at 1120×800 and 900×600. A separate Filter selection matrix passes 97 assertions, including page reset, retained independent route state, a bounded long menu, stale row rejection, cancel/selection focus and late taxonomy updates. All these browse methods and other runtime files remain identical after the subsequent one-method static detail-row addition; the exact before/after hashes and AST comparison are preserved in DETAIL-SIZE-SCOPE.json. The one-row detail delta is covered by the final-source native groups.

All nine final-source native groups pass: Library, desktop presentation (83 checks), catalog, desktop navigation (76 assertions), UI smoke, header/action layout (40 geometries with explicit Unknown-size and unchanged action assertions), detail actions, Setup cancellation and controller navigation. Cache-first Store checks pass 31 assertions in each mode (62 total): usable cold cards, warm/reopened snapshots, independent artwork, focus/search-draft preservation, stale query and image rejection, exact snapshot ownership, offline fallback and bounded worker concurrency. Existing Add/Setup/Play/Stop and unavailable automatic download behavior remain intact.

The corrected Library fixture first established actual focused-card visibility and allocated scroll readiness instead of a fixed delay/unrelated scroll value. It then reproduced an existing resize defect on accepted 0.4.30: a focused card's bottom was 384px in a 376px viewport at 1024×600. The candidate schedules the existing focus/generation-owned reveal when window geometry changes. It preserves selection and now passes the same full-card visibility check. Baseline failure, exact runtime identity and corrected fixture are retained.

All 231 core tests pass on final Python source, as do full Ruff F checks and compilation. The first core attempt could not create three owned loopback HTTP fixtures inside the restricted socket sandbox; its failures are preserved separately. The same complete suite passed with fixture socket access. Installer-related unit output refers to inert temporary installation fixtures, not the host app. Native validation ran serially at nice 10 and idle I/O priority with pressure admission checks. Owned renderers stopped normally.

Seven native images were inspected: 1080p and compact Library, compact Store and selected Filter popup, and fullscreen/desktop detail in dark/light layouts. Captures use fictional data and disabled Play; they are not live-desktop or physical-keyboard/gamepad acceptance. The obsolete sort integration is preserved separately as superseded and is excluded from the candidate. Installed 0.4.28, production data, source configuration and desktop integration remain unchanged pending independent review and delivery. The final GTA V Enhanced catalog check remains deferred until the overall app/API work is complete.


## Native dialog consistency candidate — 0.4.32

The isolated candidate passes 231 core unittests, compileall and Ruff F. Native checks pass: 94 focused dialog assertions and 25 synthetic renders; 297 Search/Filter assertions across Library/Store, desktop/fullscreen and 1120×800/900×600; 28 controller-method assertions; existing Setup, detail action and UI smoke groups. Setup exercises repeated open/close/Escape, active-operation controls, canceled drafts and stale picker/confirmation callbacks. Long error text is bounded, wraps within the viewport and keeps its response reachable.

The fixtures run serially at low priority on an owned loopback Broadway display, using fictional data and disabled/mocked execution. No live desktop capture, physical keyboard/controller or real gameplay acceptance is claimed. UI smoke now mocks controller transport rather than opening physical input devices. The test-only long-message scrolling check disables GTK animations before constructing its scroll area because an unconnected Broadway renderer does not acknowledge animated frames; production animation policy is unchanged.

A non-failing GTK warning remains during the synthetic fullscreen-to-desktop transition after the compact message case: GtkBox reported minimum height 25 and natural height 19. All subsequent geometry/navigation assertions pass, with no observed clipping in the reviewed final images. Its cause is not established and it is disclosed for independent review. Deprecation warnings for the pre-existing Adw.MessageDialog API also remain; this candidate retains that supported native response type.

Review evidence is separate from installable source. Installed 0.4.31 and repository app files were verified against the accepted baseline and remain unchanged. Release/install and public publication are not performed by these checks.


### Independent-review correction — review 2

The final new lifecycle fixture fails eight of 33 assertions on frozen review 1, reproducing its ten retained destroyed message dialogs and three retained discarded popovers, retained Settings/modal objects and nested-prompt native lifetime. Corrected review 2 passes all 33 assertions: disposable object counts return to zero, live themes/reopening/reparenting remain functional, parent disposal never activates confirmation, and all 22 observed theme subscriptions are disconnected at the end. A scoped GC diagnostic also identified the shared modal Escape lambda retaining its own window; the handler now resolves its owner through its controller.

Fresh checks pass on the corrected runtime: 231 core tests, compileall, Ruff F, 94 dialog assertions, 297 browse assertions, 28 controller assertions, Setup, detail actions, UI smoke, private-bus tray and single-instance tests. The instance fixture substitutes a mocked controller transport in its child app; it never reads a physical controller or launches a game. Theme-helper CSS is byte-identical to review 1.

The native harness uses temporary HOME/XDG and a private bus. An initial private-bus run emitted portal-helper activation warnings; no such helper remained afterward. The final isolation replay removes host display variables and uses a bus without service-activation directories; lifecycle, dialogs, tray and instance checks pass again without activating those helpers. Logs preserve all iterations. Existing non-failing GTK minimum/natural-size warnings remain in the synthetic mode/resize checks, including the documented compact-height warning; no claim of warning-free or real-desktop acceptance is made. No installed app, user records, backend contract or storage/transfer implementation changed.

## Shared detail / Storage reconciliation candidate — 0.4.33

Validation uses isolated GTK/Broadway fixtures, temporary data, mocked execution and no physical input. Matched baseline/current detail renders use identical public metadata/artwork at 1120×800, with additional 1920×1080 and 900×600 views. Ordinary fullscreen detail remains pixel-identical. Fictional detail fixtures cover dark/light desktop, fullscreen, 640px narrow windows, long titles/descriptions, missing artwork, reachable actions, complete Game Info, Setup cancellation, Stop appearance and the one-game guard. The headless fixture disables animations only for final-position checks; production animation policy is unchanged. Exceptionally tall fullscreen content uses the existing page-scroll action.

The reused Storage model/access/observer/topology tests and new persisted path-reconciliation tests cover separate partitions on one disk, duplicate registration, changed mount paths, offline/default behavior, replacement filesystem identity, capacity accounting and manual-flow independence. Native flows cover global Add drive, shared roles, stale discovery after close, canceled removal, remount/offline display and fullscreen Storage/Back. All registrations are inert temporary fixtures; no actual partition is registered or modified. Existing private-bus lifecycle, dialog, browse, Setup, UI, tray and single-instance checks remain required.

The current Store investigation confirms two upstream records with only one verified Steam relationship. No title-only deduplication or alias was invented. The requested consolidation remains blocked on authoritative provider identity evidence; passing UI/Storage tests do not resolve that contract dependency. No production API, installed app or real library changes are part of validation.

Final local results: 280 core tests, compileall and Ruff F pass. All 11 aggregate native groups pass, including 297 browse, 94 dialog, 33 lifecycle and 28 controller-method assertions plus six Storage integration flow groups. The final Stop-color-only CSS change is covered by 130 exact-runtime detail assertions and 12 renders; aggregate executable AST is identical and its CSS delta is explicitly recorded. Five matched detail pairs plus the unchanged Store duplicate replay were captured with original branding resolved in a private icon directory. Both ordinary fullscreen pairs are byte-identical. Source repo (146 baseline files), installed runtime (36 modules and entry point), and real library bytes were rechecked unchanged; no real Storage database was created. The candidate is frozen for independent review, with no installation or publication.

### Independent Storage findings — review 2

The new native regression exercises actual controller dispatch and weak-reference lifetime, pinning only the active owned window because the isolated renderer has no desktop focus. Review 1 passes 9 of 24 assertions and fails 15: eligible checkbox traversal/Select/Add, modal menu containment/Back/focus return, retained Storage pages and Settings windows, and parent-close cleanup. The repaired candidate passes all 24. Three closed Storage pages/parents drop from 3/3 retained to 0/0; repeated real Settings windows/pages also reach 0/0. Late discovery after parent close is rejected and releases the picker. No checkbox set_active shortcut is used for the registration path.

The reviewer's original Storage capture stopped at requested 760×800 versus allocated 660×720. Its failure log is retained. An unchanged-source Unix-renderer replay here passed all six flows, so the sizing failure was not consistently reproduced. The fixture now requests its fullscreen Preferences size before the first present, just as its desktop cases already did, rather than relying on a mapped-window resize acknowledgement from headless Broadway. The exact allocation assertion remains. This is a fixture change; no production window-size workaround was added.

The original Store identity issue remains unresolved. The evidence handoff provides exact public backend URLs/IGDB IDs and distinguishes verified Steam mapping from unverified candidate IGDB slugs. No provider-credential lookup, title-based consolidation or production API edit is included.

Final review-2 verification: the byte-identical final navigation/lifetime fixture reports 9/24 on exact review-1 runtime and 24/24 on exact review-2 runtime. The clean final source passes all 280 core tests, compileall and Ruff F. Fourteen native groups pass across the completed first six groups and eight resumed groups, including Settings and Proton checks. The execution-service disconnection and interrupted wrapper are preserved separately; dialogs onward were rerun, and the resumed owned renderer stopped. All 12 fresh fictional detail renders are byte-identical to review 1. Final bindings cover all 41 runtime modules. All 146 baseline repository files, 36 installed modules plus entry point, and real library bytes remain unchanged; no real Storage database exists.

### Review 3: dispose replaced Storage groups

Independent review found that populated refresh bypassed review 2's close-only cleanup: removed groups no longer belonged to the tree traversed on close. The runtime delta now calls the existing disconnect_actions helper before each group is detached. No other runtime file changes relative to review 2.

The same new 27-assertion native fixture runs on exact review-2 and review-3 runtime. Before: 23/27 pass; manual refresh and automatic role-change refresh each retain three pages after three close cycles, although parents release. A retained old menu action can still change fixture roles. After: 27/27 pass; no-refresh, repeated manual refresh and role-change refresh all release zero pages/parents, and the retired action is inert. The fixture never creates payload directories or touches a real registry.

All seven final native groups pass: refresh/disposal (27), existing Storage navigation/lifetime (24), Storage integration (six groups), prior dialog lifecycle (33), controller methods (28), Settings and UI smoke. Runtime snapshots are exact; the owned private Unix renderer stopped. This scope changes callback lifetime only, so review-2 visual evidence and unchanged detail/CSS remain applicable. No new live-desktop or physical-input claim is made. Review 3 remains separate from the subsequent catalog bundle/component design work.

The final review-3 source also passes all 280 core tests, compileall and Ruff F. Its new refresh fixture is byte-identical in the saved red/green runs; all 41 runtime hashes are bound to final core/native results. The two earlier frozen candidates and their evidence remain unchanged. Both the one-candidate delta and combined installed-baseline patch are application-checked before handoff; no installation or publication is performed.

## Separate catalog entity candidate, 2026-10-04

This is a local candidate on the installed 0.4.33 baseline; no new release, installation or push has occurred. Three runtime modules change: catalog validation/identity, Store/detail presentation, and Game Info composition/weak Close ownership.

- 287 core tests, compileall and Ruff F pass on the final Python sources.
- Nine serial private-native groups pass: membership (26 assertions), catalog navigation/Add/offline, Store performance (31), browse controls (297), detail actions, dialogs (94), dialog lifetime (33), controller navigation (28), and UI smoke.
- Nine actual outputs from the frozen API candidate's pure normalizers pass desktop parsing, including absent/unknown metadata, all forward relation directions, complete/empty/100-item partial inverse lists, casing and Unicode. Exact-ID tracking keeps same-Steam bundle/component records separate. No live route/provider calls or API repository writes were used.
- Final proposed-contract preview: 65 assertions, 13 native images; same fixture against accepted baseline: 18 assertions, 10 images. Viewports: 1920×1080, 1120×800, 900×600 and candidate-only 640×600 missing-art/unknown-metadata state; desktop dark/light and fullscreen. Fullscreen Game Info's related link is revealed by focus through its scroll area with a long description. Main detail remains read-only.
- A reproduced optional-detail race was fixed by filling only unknown card classification fields; a older detail snapshot cannot replace fresh browse classification. A new disposal regression reproduced retained relationship dialogs; weak native window references now permit disposal even with a stale button explicitly retained. Closed controls stay inert.

Native fixtures use private HOME/XDG, private Unix Broadway and a private bus; new identity and preview fixtures block INET and process execution. Static preview captures explicitly settle the existing toolbar resize callback over three allocation passes to avoid unacknowledged Broadway remap transients; final dimensions, density and visible controls are asserted. The separate native navigation suites keep ordinary callbacks. These are synthetic renders/method-signal checks, not live desktop screenshots or physical-controller/gameplay validation.

GTA visual inputs replay recorded public metadata/art with parent-verified type/platform enrichment. The Game Info partial relationship example intentionally contains only the supplied known component to test presentation; it is not an observed backend inverse-query response. Actual provider contents, originals and the missing component Steam mapping remain unverified until a separately authorized live backend check. Current production responses and old snapshots may omit the additive fields. No saved Library records are migrated or given inferred ownership.

Saved Store enrichment v2: tools/saved_catalog_checks.py reproduces the missing detail call in both desktop/fullscreen on review v1, then checks exact requests, all directed links, reopen-after-Add, pending-modal updates/focus, intact local metadata/actions, failure/old-schema/offline behavior, late response cancellation, Setup edits and mode rebuilds on the repaired candidate. All use private synthetic records and blocked network/dispatch.
