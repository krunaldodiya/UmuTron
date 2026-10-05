# UmuTron 0.4.33 — detail and Storage visual QA

Result: **passed for the responsive detail and Storage presentation scope** in isolated native GTK test renders. Independent whole-candidate review is pending. The original Store duplicate is **not fixed** and is not covered by this visual pass.

## References and method

The source reference is accepted installed 0.4.32 (`dialog-consistency-review-2`, manifest SHA-256 `68e156a89cbc9eae7f9e0262aa56d3754948f8fbbdf4958caf15b7d0a00a05cd`). Its fullscreen detail composition is the chosen design reference. The candidate reuses that composition responsively in the existing Python GTK4/libadwaita application.

Evidence accompanies the frozen source in `../detail-storage-review-evidence-1/`. `visual/before/` and `visual/after/` use identical public game metadata and artwork copied into a temporary library, a fixed clock, the same native renderer/theme/fonts, and exact allocated viewports. No executable, prefix or real game record is used. These are **synthetic native test renders**, not captures of the user's running app. Native desktop capture is unavailable; no alternative desktop APIs, raw input or host security changes were used.

The baseline desktop, selected fullscreen reference and candidate desktop were opened together in one comparison input at original resolution. Baseline/candidate light and compact pairs were also opened together. Fullscreen 1080p images were compared together; pixel/byte checks additionally confirm unchanged fullscreen 1120×800 and 1920×1080 images. All final comparison images include the original UmuTron orbital/play icon through the fixture's private icon installation. Earlier behavioral fixtures have a missing icon placeholder because their private HOME lacks the installed desktop icon; production assets are unchanged.

| Matched state | Size | Observation |
| --- | --- | --- |
| Desktop dark before/after | 1120×800 | The opaque top panel becomes a bounded lower panel over legible key art, matching fullscreen's hierarchy. Title, cover, summary, metadata and actions remain readable. |
| Fullscreen reference/candidate | 1120×800 and 1920×1080 | Ordinary Setup-state renders are byte-identical. Existing navigation, artwork crop and panel placement remain. The deliberate shared Stop color update is covered separately. |
| Desktop light before/after | 1120×800 | Native chrome stays light; the detail scene uses the consistent dark cinematic palette and scrim. |
| Compact desktop before/after | 900×600 | Bounded overview prevents the old long text from consuming the surface. Actions and explanatory text remain visible, with useful art above the panel. |
| Store duplicate replay | 1120×800 | Both versions show two upstream IDs, with one In library badge. The image documents the unresolved issue, not a repaired state. |

## Visual assessment

- **Typography and hierarchy:** wide title 46px, compact title 34px; description 20/17px; metadata 17px. Desktop now matches the fullscreen hierarchy instead of using a smaller disconnected panel. Title/summary/credits are bounded; full information remains available in Game Info.
- **Composition and artwork:** one artwork scene with a legibility gradient, dark fallback, bounded translucent panel, consistent cover and an aligned action row. The cover hides below 700px so text/actions have room. No blur or new animation is added. The original branding is preserved.
- **Actions and focus:** the primary action, options and Game Info stay aligned. Play/Setup use mint; owned Stop uses a readable pink/red semantic surface in both modes. The mint focus ring has a dark separation from the background. Final Stop screenshots use mocked ownership and never execute a process.
- **Responsive states:** a 640×600 native fixture shows the cover-free title, metadata, description and complete focused action row without overlap. Long/missing-art states remain scrollable and retain the complete Game Info dialog. Exceptionally tall fullscreen metadata uses existing LB/RB page scrolling; not every element is claimed initially visible.
- **Storage:** Settings has a Storage tab; fullscreen options opens the same page with console typography. Add Drive has explicit Cancel/Add actions, visible capacity and eligibility, one row per partition, and disabled unsupported choices. Registered cards disclose free/total capacity, connected/writable status, roles and current path. Offline cards retain identity and disclose the last-known path instead of claiming available capacity. Long fullscreen lists scroll within native preferences.

No actionable P0–P2 visual defect was found in this scoped review. This is visual inspection, not measured WCAG conformance, transition benchmarking, assistive-technology or physical controller acceptance.

## Functional evidence and boundaries

All 280 core unittests, compilation and Ruff F pass. All 11 aggregate native groups pass, including 297 browse assertions, 94 dialog assertions, 33 lifecycle assertions, 28 controller-method assertions and six Storage integration flow groups. A later CSS-only Stop-color adjustment leaves executable AST unchanged and is covered by a final exact-runtime run with 130 detail assertions and 12 renders. Runtime bindings disclose the distinction; they do not claim the aggregate run used byte-identical CSS.

Storage reuses the earlier uninstalled registry/access/observer/topology candidate. Its integration still requires independent review. Registration is metadata-only; no drive is formatted, mounted, repartitioned, chmodded or automatically registered. Managed transfers remain unavailable. Manual Setup, local installers and Play do not require registration. The actual user-supplied Games mount was observed read-only; no attempt was made to change that state.

The current API returns IGDB 334647 and 334254 with the same displayed title/date but only 334647 maps to Steam 3240220. The catalog contract has no verified alias for 334254. No title-only merge, fabricated mapping, user metadata rewrite or Legacy/Enhanced consolidation is included. The separate identity contract request remains pending.

Owned fixture renderers stopped. Source repo, installed 0.4.32 and real library bytes match their baseline. Known existing GTK measurement/deprecation warnings remain disclosed in logs. No installation, commit, push, gameplay, live controller test or production API modification occurred.

## Review 2 correction and focused visual check

Independent review found three functional P2s outside the prior visual acceptance: controller selection could not activate a partition checkbox, Back bypassed a Storage popover, and closed Storage pages/parents remained retained. Review 2 adds actual controller and weak-reference regressions and fixes those paths; the earlier visual pass must not be read as functional acceptance of review 1.

The focused selected-partition native render now shows an enabled Add drive action and the shared mint focus outline around the selected checkbox. Registered and unsupported partitions remain disabled. The window is scrollable and the long fixture title truncates within the header; complete partition labels and status remain in their rows. Ordinary detail composition/CSS and original branding are unchanged from review 1. The separate Settings and Proton native flows cover the parent-reference cleanup. All screenshots retain the synthetic native fixture limitation.

The final selected-partition before/after pair was opened together at original resolution. Before: focus remains on Cancel and Add is disabled. After: partition B is selected with a mint outline and Add enabled; unavailable rows stay disabled. Different temporary directory names are fixture-state differences. All 12 fresh detail renders are byte-identical to review 1. Final evidence, exact regression results, interruption disclosure and gallery are in `../detail-storage-review-evidence-2/REVIEW.md`; the result remains scoped to synthetic native rendering and verified method/signal behavior, with independent rereview pending.

## Separate catalog entity distinction — 2026-10-04

Reviewed native fixture images at 1920×1080, 1120×800, 900×600 and 640×600. Paired accepted-0.4.33/candidate Store and bundle detail views use the same public artwork and temporary Steam-linked record. The candidate makes the two same-title cards distinguishable with Bundle / Expanded game plus platform text. Equal reserved classification height keeps card bottoms aligned; classification remains visible when compact mode hides the optional saved-entry badge. Focus is clearly visible, and toolbar/card/pager geometry stays within the asserted viewport.

The bundle preview remains a separate Add action, with explicit Open saved entry navigation; it no longer silently opens a different saved entity as this catalog record. Full platform names appear on detail and in Game Info. Directed relationships live in Game Info, preserving the uncluttered primary detail actions. Partial lists are labeled. Focus reveals the related-entry control below long text in the fullscreen modal. Unknown metadata/artwork has a stable Catalog entry fallback, and the narrow view keeps Add and Game Info reachable.

Evidence is in the separate catalog-entity review package: baseline/ and after/ paired previews, native logs, and the nine-case API-normalizer compatibility record. Earlier static preview attempts caught headless allocation transients, not a production layout regression; final static renders settle the production resize callback and assert density before and after capture. All nine ordinary native regression groups also pass. New Game Info callback disposal and asynchronous classification-race regressions were fixed before the final candidate.

These are proposed-contract synthetic GTK test renders, not live desktop screenshots, live enriched catalog responses, hardware-controller QA or verified commercial bundle entitlements. The relationship example is intentionally partial UI data using the one known supplied component; it does not claim the backend returned that list. Installed 0.4.33 remains unchanged pending joint review and release approval.

Catalog entity review v2 repairs saved-entry enrichment without changing the visual composition. Game Info shows pending/unavailable/offline catalog status while keeping the saved description and action. Native regression coverage includes an already-open modal, focus preservation, canceled navigation and unsaved Setup fields; final test renders remain synthetic Broadway fixtures, not live desktop captures.

V2 final visual check: all 65 layout assertions passed, producing 13 renders byte-identical to v1. Paired desktop/fullscreen Game Info images were inspected together. The saved-entry state transitions are verified separately by 33 native assertions; these static previews do not claim live saved-entry/provider capture.
