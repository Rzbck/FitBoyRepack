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

## Final stability
CI uses a pinned Playwright Chromium, retries only browser startup and retains
desktop/mobile and detail assertions. The coordinator reacts to trusted main
CI completions (even when a browser fails) and successful Pages deployments;
it runs its own selection tests before dispatch. GitHub event and cron limits
still apply. An independent VPS dispatch timer requires a separately authorized,
repository-scoped Actions write credential; existing publisher credentials are
not repurposed.
The monitor includes main push CI failures. With FITBOY_NTFY_URL configured,
two consecutive observations of an issue trigger a notification; identical
persistent issues are not repeated, and recovery is announced once.
External snapshots can be pulled via SSH using pull_external_backup.py, with
SHA-256 and SQLite validation before atomic publication. Run it from a separate
machine on a regular schedule; if that machine is off, the next run catches up.


### French translation quality
The existing Helsinki-NLP opus-mt-tc-big-en-fr model (CC BY 4.0,
https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-fr) runs locally
with INT8 CTranslate2. Translation quality rules are versioned separately
from the public storage schema; a metadata-only change does not discard an
accepted translation whose source hash is unchanged. New outputs use bounded
glossary protection, placeholder multiplicity, numeric and simple negation
checks. If a masked attempt is rejected, one unmasked attempt is validated
against the same rules. These checks are heuristic, not proof of semantic fidelity.
Up to six previous rejected fields per run are retried within the existing
24-field limit; a private SQLite marker prevents retrying the same source
indefinitely. A small source-anchored correction pass fixes confirmed legacy
terminology errors once per quality version. The Steam description link is
constructed only from verified app IDs; no localized Steam prose is imported
without a confirmed reuse grant.
