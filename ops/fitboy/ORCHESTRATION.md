# Catalog orchestration

GitHub's scheduled workflows can be delayed. A single coordinator checks the latest
runs and dispatches at most one eligible job per tick. It does not bypass the
existing catalog-writer concurrency lock or change the data processing limits.
The intended intervals are 60 minutes for Steam and catalog refresh, 15 minutes
for media and 24 hours for full backfill. The read-only RSS watcher retains
its independent 10-minute schedule and also participates in coordinator
catch-up when overdue. It only requests a writer for new URLs or an
unavailable feed. The coordinator ticks every five minutes. These are targets,
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

RSS catch-up shares the same fail-closed history and active-run checks.
No second scheduled RSS run is requested while an observed worker or RSS run
is active; the independent RSS schedule remains a fallback.

## Independent VPS heartbeat
Install the reviewed dispatcher as root-owned /usr/local/lib/fitboy/dispatch_guard.py
(not in the mutable worker checkout). Install fitboy-dispatch.service and timer.
The service runs under a separate DynamicUser and receives a dedicated
fine-grained PAT via systemd LoadCredential, never via source or arguments.
Root-only /etc/fitboy/github-dispatch.token must be provisioned interactively.
Grant Actions read/write only on Rzbck/FitBoyRepack, with an expiration; no
Contents write or administration permissions. The token still has repository-wide
Actions permission; the dispatcher itself allows only the fixed coordinator URL
and main ref, blocks redirects, never logs response bodies or tokens.
The heartbeat checks every five minutes; queued/running or recent coordinator
runs are skipped. Failed requests back off 15 minutes. The GitHub coordinator
retains its own worker concurrency and eligibility checks. GitHub runner queue
delays and external outages remain possible. Do not enable before provisioning.
