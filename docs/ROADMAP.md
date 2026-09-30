# Version 0.3.3 delivery scope

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
