# Catalog orchestration

GitHub's scheduled workflows can be delayed. A single coordinator checks the latest
runs and dispatches at most one eligible job per tick. It does not bypass the
existing catalog-writer concurrency lock or change the data processing limits.
The intended intervals are 60 minutes for Steam and catalog refresh, 15 minutes
for media and 24 hours for full backfill. The read-only RSS watcher retains
its independent 10-minute schedule and only requests a writer for new URLs
or an unavailable feed. The coordinator ticks every five minutes. These are targets,
not guarantees. Overdue jobs are selected by absolute lateness; failures cool
down for 15 minutes. A failed API read stops dispatch. Manual worker dispatch
remains available; catalog updates still request immediate media and Pages work.
RSS success without new URLs no longer requests a redundant catalog refresh;
an unavailable RSS feed still requests a listing scan. Hourly full refresh
continues to catch edits to existing posts.

The VPS publisher token is intentionally not changed. A future external timer
requires an explicitly authorized GitHub Actions write credential.

Coordinator triggers also include completed trusted main-branch CI, RSS and
worker runs. CI failures do not trigger writers. This adds event-driven
opportunities to catch up without relying solely on cron, but GitHub limits
workflow_run chains and can delay scheduled events. Existing writer lock,
cooldown and fail-closed checks remain. No external dispatch credential is
added. The health timer monitors public Actions histories independently.
