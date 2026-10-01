# FitBoyRepack AI enrichment on the VPS

This worker is project-specific, but the LLM is not. It calls the reusable localhost OpenAI-compatible service documented in `../llm/`.

## First bootstrap

The first run queues the full rich catalog and keeps processing until no `pending` game remains:

```bash
python tools/ai_catalog_bootstrap.py --init --run --limit 0 --status \
  --db /var/lib/fitboy/ai/catalog_enrichment.sqlite3
```

The SQLite database is resumable. A reboot/interruption is recovered by the next `--init` run. Existing `done` games are skipped unless their source fingerprint or `AI_VERSION` changes.

A game is `done` only when the worker has a canonical identity, an exact release date, at least one genre, at least one supplied evidence URL and confidence >= 0.80. Lower-confidence/incomplete matches stay in `review`; request/network/model errors are `failed`.

AI results are deliberately kept outside `site/data/games.json` during bootstrap. That lets us audit quality before any AI field becomes public/site data.

## Automatic incremental mode

Install `ai-enrichment.service` and `ai-enrichment.timer` in `/etc/systemd/system/`, create `/var/lib/fitboy/ai`, then enable the timer:

```bash
sudo install -d -o fitboy -g fitboy /var/lib/fitboy/ai
sudo systemctl daemon-reload
sudo systemctl enable --now ai-enrichment.timer
```

The first activation consumes the full queue. Later activations only queue/process new or changed games. The project worker is limited separately from the LLM process (`CPUQuota=50%`, `MemoryMax=1G`).

Useful commands:

```bash
# Queue/status only
python tools/ai_catalog_bootstrap.py --init --status --db /var/lib/fitboy/ai/catalog_enrichment.sqlite3

# Retry transient failures after fixing connectivity/model issues
python tools/ai_catalog_bootstrap.py --retry-failed --run --limit 0 --status --db /var/lib/fitboy/ai/catalog_enrichment.sqlite3

# Re-evaluate manually reviewed cases if the prompt/model/evidence improves
python tools/ai_catalog_bootstrap.py --retry-review --run --limit 0 --status --db /var/lib/fitboy/ai/catalog_enrichment.sqlite3
```

The worker uses Wikidata and English Wikipedia over HTTPS with no account/API key. Python retrieves compact evidence; the local LLM matches the game, normalizes metadata and translates the existing source description into French without inventing unsupported facts.
