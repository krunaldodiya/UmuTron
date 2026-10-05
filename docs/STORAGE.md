# Storage registry and inactive automatic-install boundary — 0.4.27

Settings > Storage now connects a read-only UDisks2/kernel observer to an app-private SQLite partition registry. Add drive is explicit and metadata-only. No directory, partition, game file or prefix is created or moved. Mounts and permissions are never changed. The interactive demo uses an empty disabled service.

**Registrations apply only to future automatic downloads and installs.** Existing-file Setup, Setup Save/Confirm, the Windows installer under Setup > More, and Play/Stop remain independent of Storage. Their original paths, including external paths, remain supported. Manual installers choose their own destination. Automatic torrent/archive transfer is unavailable: the existing ledger and `InstallDriveDialog` are tested boundaries, not connected execution or a transfer implementation.

## Internal partition discovery

Mounted partition roots require correlated device, mount and partition evidence. Fully verified internal provenance is required for managed cache/archive authority. A narrowly bounded metadata-only PCIe NVMe registration exception is described below. UDisks Block/Partition/Drive data must correlate with the kernel block device, parent partition table, current mountinfo and opened root. USB, FireWire, removable/ejectable/power-off drives and external buses reject. Direct AHCI SATA requires readable controller/port evidence with external SATA, hotplug, presence-switch and multiplier flags clear. PCIe ancestry requires explicit readable fixed-port capability before accepting a native NVMe or downstream AHCI endpoint. Unknown, inaccessible or unsupported topology is unavailable with a reason. Whole disks, virtual devices, partial/subvolume mounts, multiply mounted filesystems, read-only mounts and ambiguous identities cannot be selected. Neither a mount path nor SATA transport alone proves internal status.

The UI enumerates observations; it has no path editor or folder chooser. Different partitions of one physical drive are allowed. The same observed partition/filesystem identity cannot be registered twice, even for a different role. Already registered choices are disabled. Cache and install roles attach to one registration UUID and appear on one card. Model schema 2 preserves the isolated schema-1 prototype as unsupported rather than silently rewriting it; no schema-1 Storage registry was deployed.

Discovery uses bounded read-only GetManagedObjects (1.5-second D-Bus timeout), mountinfo and sysfs properties. No mount, format, power, authentication or device mutation methods are used. Registration and snapshots run on a worker; closed views discard callbacks. Refresh updates availability. Every registration mutation and future admission re-observes the mount. No background automount occurs.

**PCIe NVMe registration exception (separate candidate):** Linux normally exposes only the 64-byte PCI header to an ordinary user. A direct NVMe endpoint below one PCIe root port may be registered as metadata-only when that bridge header is valid, its capability list starts beyond the readable header, every existing UDisks/partition/sysfs identity and PCIe transport check passes, and no known external/removable/hotplug evidence is present. This does not prove fixed internal attachment. It carries a visible limited-verification message in Add Drive and its Storage card; cache roles and every archive quote/reservation remain blocked by managed_reason, even if the root is private. The strict InternalPartitions call still returns UNKNOWN for this case. Missing/malformed headers, additional bridges, non-NVMe endpoints and other unknown states still reject. No root helper or host setting change is used. `/run/media` itself remains allowed.

Manual registration of an otherwise eligible internal NTFS partition does not grant managed-write or uninstall authority. The existing private/writable-root check still blocks cache/managed archive admission on unsuitable roots, including observed 0777 roots. This release does not solve that writer limitation. Registration alone creates neither EmuGames nor UmuTronCache.

Primary references: [UDisks Block](https://storaged.org/doc/udisks2-api/latest/gdbus-org.freedesktop.UDisks2.Block.html), [Drive](https://storaged.org/doc/udisks2-api/latest/gdbus-org.freedesktop.UDisks2.Drive.html), [Partition](https://storaged.org/doc/udisks2-api/latest/gdbus-org.freedesktop.UDisks2.Partition.html), [Linux AHCI flag definitions](https://github.com/torvalds/linux/blob/master/drivers/ata/ahci.h), and [AHCI sysfs implementation](https://github.com/torvalds/linux/blob/master/drivers/ata/libahci.c). UDisks removability is a hint; the classifier requires additional kernel topology evidence.

## User policy

The inactive automatic-install ledger requires exactly one configured download-cache role and at least one installation role before admission. Manual Setup and installers have no such prerequisite. Select a discovered mounted drive/partition root, never an arbitrary nested path. Intended install paths are `<current mount root>/EmuGames`. Proposed cache paths are `<current mount root>/UmuTronCache`, with future job-owned UUID directories beneath them. These paths are displayed, not created by this model.

Installation drives support an explicit default. An offline default is shown as offline; no automatic fallback selects a different drive. Removing registration changes local metadata only. Existing `Games` folders, library executable paths, prefixes and saves are not migrated or rewritten. Active reservations prevent removal or cache replacement.

For verified archive size A and verified expanded size E:

- Cache: **A + cache_extra** (archive × 1).
- Installation: **E + ceil(E/2) + install_extra** (expanded × 1.5).
- Both budgets must fit before START. Unknown or unverified A or E yields `fits=None` and blocks reservation/START. This slice has no estimated-ratio or upper-bound admission mode. Unknown E also cannot authorize extraction.
- If cache and installation use the same filesystem, combine their budgets. Two paths are never independent free-space pools.
- Extra temporary/metadata/copy requirements are independent integer byte fields. The UI shows these separately from the 0.5E installation margin. Same-filesystem renames are not extra copies.
- `additional_floor` defaults to **zero**. A nonzero floor is disclosed, held once per affected filesystem, and combined with other active jobs using the maximum requested floor, not summed per job.

The old 2.5x archive proposal and prototype 16 MiB floor are not defaults. Web size labels are not verified sizes. The model trusts the future adapter to establish manifest provenance before constructing a verified plan.

## Exact current Python boundary

`game_library/storage.py` has no GUI imports or filesystem payload operations.

| Interface | Result / authority |
|---|---|
| `Volume(volume_id, mount_id, root, label, free_bytes, total_bytes, read_only=False, support_reason='', is_root=True)` | A trusted observer's temporal snapshot. `volume_id` must represent the actual shared filesystem; `mount_id` must include a boot/session fence. |
| `StorageModel(StateStore(path), observer)` | Explicitly injected fixture backend. `observer()` returns the current `Volume` sequence. `configured_storage(root)` supplies a private store and LinuxVolumes observer for registration; transfer remains disconnected. |
| `discover()` | Current observations; no mount/unmount action. |
| `register(observed, 'cache' or 'install')` | Revalidate identity/root/mount, reject an already registered partition, then persist one registration with its initial role. Returns a UUID. Use `add_role(id, role)` on that same UUID to share cache/install; `remove_role` retains the other role. Active commitments protect role removal. |
| `snapshot()` | Registration state, current root/free/total, status/reason, default and busy flags. Last-known roots are display-only when offline. |
| `set_default(id)`, `remove(id)` | Registry metadata only. Cannot remove an actively reserved registration. |
| `SizePlan(archive_bytes, expanded_bytes, cache_extra=0, install_extra=0, additional_floor=0, verified=True)` | Exact nonnegative integer byte policy. `None` or `verified=False` cannot authorize admission. Booleans, floats, negative or oversized integers are rejected. |
| `quote(install_id, plan)` | `CapacityQuote(volumes, cache_path, install_path)`; each volume has free/required/other/floor/roles and computed `fits`. A quote is not authorization. |
| `reserve(job_uuid, generation, install_id, plan)` | Fresh two-volume checks under one transaction; returns `ReservationToken(job_id,generation,nonce)`. Generation is a durable reservation epoch, separate from transfer callback generations. Same active request is idempotent; changed/released requests reject. |
| `revalidate(token, phase)` | Fresh checks at `stage`, `start`, `resume`, `extraction`, or `commit`. A mount/root change invalidates the active token. |
| `reconcile(token, owned_cache_allocation, owned_install_allocation)` | Trusted, measured allocation boundary; same job/mount/generation only. Allocation cannot exceed its role's footprint. The install margin is never credited as allocated. This function does not measure/verify filesystem ownership itself. |
| `release(token, confirmed_stopped=True)` | Remove future commitment only after the caller established stop/handoff. Leaves all files untouched. Released generations cannot be replayed. |

Exact field names are intentionally documented for the transfer owner. Snapshot progress counters are not accepted by reconciliation; there is no `bytes_done` parameter. Archive and extraction allocations must be measured, owned, deduplicated and associated with the bound filesystem before calling. Credit is capped to the fulfilled role footprint; raw filesystem block rounding can exceed logical bytes and must not be passed blindly. Actual additional allocation/metadata needs belong in disclosed extras; do not silently discard material unbudgeted allocation. Until that adapter is reviewed, retaining the whole commitment is the conservative option.

## Durable reservation semantics

`StateStore` keeps registry, default and all generations in one local SQLite state row with `BEGIN IMMEDIATE` and `synchronous=FULL`. Admission locks before observing free space and updates both volume commitments together. Independent threads/processes share the same ledger file. Exceptions roll back. Corrupt/unsupported state is preserved and blocks operation; it is never reset to an empty ledger. A 4 MiB state bound fails closed and requires a future reviewed archival policy for old terminal generations.

The choice follows SQLite's [single-writer transaction behavior](https://www.sqlite.org/lang_transaction.html) and Python's [SQLite connection/timeout interface](https://docs.python.org/3/library/sqlite3.html). The implementation uses explicit transactions and does not depend on implicit transaction upgrades.

Admission requires `this job remaining requirement + other active jobs remaining commitments + max disclosed floor <= current free`. Free already excludes physically allocated blocks. Reconciliation reduces commitments only for measured allocation fulfilling the same role on the same mount. Sparse logical length, engine counters and another job's allocation must not become credit. Updating measured allocation can persist even if the next capacity check fails; the next I/O checkpoint remains blocked. Paused/canceled/uncertain-stop jobs retain future commitments until explicit confirmed release. Retained partials still consume filesystem space after release; resume must re-admit.

Retain the same journaled reservation token/epoch across pause, cancel and resume; a transfer callback generation change must not call `reserve` with a new reservation generation. Released-partial recovery currently re-reserves the full budget before reconciliation and can conservatively reject a tight-space job whose partial data already exists. Automatic space-efficient re-admission is **not supported** in this slice; it needs a separately reviewed atomic verified initial-allocation/recovery path. Keeping the reservation through resumable states avoids that gap.

## Native behavior and tests

`StoragePage` shows one card per registered partition with role labels, a single capacity bar, a read-only root, default state and unavailable reasons. Add drive disables registered/unsupported identities. Role changes happen in the card menu; no second Add is needed for shared cache/install. Removal requires confirmation and changes registry metadata only. An offline default is not silently replaced. `InstallDriveDialog` is fixture-only and returns a fresh capacity quote; it never reserves or starts anything.

Production registry writes use `PrivateStateStore`: private owner-only parent/file, no symlinks or hardlinks, bounded database, SQLite rollback and durable synchronization. Corrupt/unsafe state is preserved. The factory does not open the database until Storage is queried. Registry data is separate from portable library backups. Real host observations during development were read-only; no real registration was created.

Run `python -m unittest discover -s tests -v`, Ruff F checks, compileall and existing native regression fixtures. `tools/storage_integration_checks.py --output <visible-directory>` uses an owned isolated Broadway display and injected inert volumes. It proves zero-registration manual Setup/external-path Save and manual installer opening, selector eligibility/duplicates/shared roles, delayed callback cancellation and the disconnected managed chooser. `test_storage_manual.py` proves explicit manual installer confirmation reaches a mocked existing installer service without consulting Storage. No game or installer executes in these checks.

Future production transfer work still requires separately reviewed destination creation, archive provenance/expanded sizes, reservation adapters, extraction, resume/recovery, atomic commit, cleanup and UI integration. No current checkbox, selection, capacity quote or reservation token grants filesystem-write authority.

The restricted-header behavior is implemented in [Linux pci-sysfs.c](https://github.com/torvalds/linux/blob/master/drivers/pci/pci-sysfs.c): normal reads use 64 bytes; full configuration requires CAP_SYS_ADMIN. This candidate does not attempt to obtain that capability.
