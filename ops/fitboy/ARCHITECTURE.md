# FitBoyRepack architecture

- site/index.html: static application shell, app.js and details.js entrypoints.
- site/assets/core: API/cache, locale and persistence; catalog: search, identity,
  card window and translation; library: wishlist. Root compatibility exports
  keep older module URLs functional. Layout/media entrypoints retain their paths.
- CSS: base.css, catalog.css, game-sheet.css in this order. Consolidation preserves
  the original cascade exactly; no speculative selector deduplication.
- tools: stable executable entrypoints for Actions and existing VPS units.
- tools/fitboy/catalog and metadata: shared backend helpers. Compatibility imports
  preserve older scripts. The media v4-v7 chain is active, not dead code.
- site/data: source snapshots used by build; Pages receives generated lazy data.
- ops/fitboy: service definitions, backup and operational documentation.

Do not enable legacy ai-enrichment together with metadata-autodrain.
Do not move live SQLite databases or change production service paths during
source-only refactors. Git history retains removed obsolete assets.

## Health
fitboy-health.timer observes systemd timers/services, metadata and translation
queue counts, disk capacity, backup age and public GitHub Actions histories
every 15 minutes. Reports are local to /var/lib/fitboy/health/latest.json and
history.jsonl (672 observations). Warnings appear in the journal; no secrets,
automatic restarts, writes to application tables, or external dispatches.
Public API reads require no credential; failures are reported as unavailable.
Pages is event-driven, so its age alone is not considered an anomaly.
