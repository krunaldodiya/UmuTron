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
