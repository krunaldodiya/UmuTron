# Native installation service boundary (not connected)

The native detail UI keeps `UnavailableInstallService` disconnected. Current release0.4.24 uses primary Setup for saved unconfigured games in desktop; fullscreen Open desktop Setup explicitly changes mode and opens the same game’s existing form. Configured games keep Play/Stop and unsaved Store previews keep metadata-only Add. No Install action or fabricated progress is exposed. Desktop Setup configures existing files and its More menu can explicitly run a user-selected local installer through the existing UMU lifecycle. A future automatic download implementation must be working and separately accepted before Install becomes primary and Setup secondary in the gear.

The future worker interface is separate from the public metadata catalog. No source adapter, torrent RPC, download binary or extraction implementation is included in this UI delta.

## Proposed interface for integration review

- `availability(game_id, metadata_identity)` returns `available` and a user-safe `reason`.
- `start(request)` returns a stable `job_id` only after explicit user action and destination/source confirmation. Request fields: local `game_id` UUID, public `metadata_identity` (`provider`, `id`, `title`), explicit local `destination`, verified `source_selection` or user-supplied URI, and idempotent `request_id`.
- `snapshot(job_id)` returns `job_id`, `game_id`, `phase`, `bytes_done`, optional `bytes_total`, user-safe `message`, optional `error_code`, `can_cancel`, and `can_resume`.
- `cancel(job_id)` and `resume(job_id)` require the advertised capability. Cancellation and recovery retain the original job identity.

Phases are `resolving`, `downloading`, `paused`, `verifying`, `extracting`, `awaiting_executable`, `complete`, `failed`, and `canceled`. A paused transfer is explicitly `paused`, never mislabeled canceled; it can resume and does not expose cancel unless the service supports that operation. Canceled transfers may retain partials and advertise resume. Byte progress describes the download phase only; extraction may supply separately verified progress. Unknown amounts remain indeterminate. The UI must never imply an overall percentage from arbitrary phase weights or display completion based only on installer exit.

The service owns durable recovery, partial files, verified payload/executable handoff, and coordination with the existing operation lock. Native callbacks must match both job and game identities; stale route callbacks cannot repaint another detail view. Installation does not auto-launch a game. Source login/CAPTCHA or unavailable links surface as explicit states and are not bypassed. Destination selection, third-party source feasibility, filesystem safety, cancellation semantics, and progress transport remain separate integration gates. No personal Library, launch configuration, credentials or user paths are sent to a metadata/source provider by this UI.
