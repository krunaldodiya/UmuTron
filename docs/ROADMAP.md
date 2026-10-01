# Version 0.4.1 delivery scope

- [x] Metadata-first Add Game, automatic metadata/artwork save and optional later launch setup; persistent installer journals and prefix/runtime continuity.
- [x] Installer failure/cancel/retry and explicit installed-executable confirmation; never rerun setup from Play.
- [x] Shared one-operation guard, owned Stop and early session-scoped cancellation.
- [x] Close to tray, Show/Exit, single-instance activation and no-host fallback.
- [x] Credential-free default public catalogue metadata, optional IGDB/artwork providers.
- [x] Read-only hero details, modal metadata/file management, collapsed advanced overrides/reset.
- [x] Existing Proton Manager, artwork, portable backups, identities and custom overrides preserved.
- [x] Isolated core, native GUI and private-bus regression coverage.
- [ ] User review of actual desktop tray and real installer/game compatibility (not automated acceptance).

No new launcher platforms or provider expansion are planned in this change. Existing game files/saves/prefixes are never deleted on cancel or update.

- [x] Desktop/fullscreen modes; console-inspired readonly library/details, no window chrome, desktop-only editing/setup.
- [x] Focus-gated controller/keyboard navigation, fullscreen Exit option, tray switching and persisted default mode.
- [x] Virtual SDL controller, native fullscreen, mode/operation preservation and default-setting regression checks.
- [ ] Physical controller/TV gameplay acceptance on the user's display (no real game executed by automated checks).

- [x] Console-style Games/Home/Library navigation, compact tiles, whole-screen hero, installed grid with equal-height cards and control-only focus.


## Fullscreen navigation and typography — 0.4.2
Games and Library are the only top-level fullscreen tabs. Repeated Back/B/Escape returns within fullscreen and never exits it. Start/F11 opens options; the gear popup offers exactly **Exit fullscreen** and **Exit**, with the existing active-operation warning for app exit. Desktop Activity, Settings, Appearance and Exit are available from the tray instead of the header. The focused game uses one prominent bold title, a compact two-line description and subdued release/genre information; the duplicate row title and logo heading are omitted. Existing library, artwork, launch configuration and prefixes remain unchanged.


## Runtime download visibility — 0.4.3
During UMU preparation/download the app shows a live status panel in desktop and fullscreen: current stage, observed archive bytes in MiB when UMU reports its temporary .parts file, and an indeterminate spinner. UMU does not always supply a total size, so no estimated percentage is invented. The panel hides when running/finished; full operation logs remain available. Carriage-return progress updates are captured by launch supervision. Never stop a user's launch just to test the panel.
