# FitBoyRepack

Lightweight static game metadata catalog.

## Architecture

The repository keeps one rich source catalog for the robots, while the public site is built into lightweight browser payloads:

`source -> GitHub Actions -> site/data/games.json -> build_site_data.py -> catalog.json + games/<id>.json + health.json -> GitHub Pages`

- `site/data/games.json` is the rich generated source used by update/enrichment robots.
- `site/data/catalog.json` is generated only for the Pages artifact and contains lightweight listing/search/filter fields.
- `site/data/games/<id>.json` is generated per game and fetched lazily when its detail view opens.
- `site/data/health.json` is generated with catalog/media coverage and remaining enrichment counts.
- The deployment removes the rich `games.json` monolith from the public artifact after generating the V2 payloads.

The runtime site has no Flask server, no database, no Supabase dependency, and no authentication service.

## Catalog V2

The static frontend includes fuzzy instant search and suggestions, year/size/media filters, a mobile filter drawer, shareable `#game=<id>` detail links with previous/next navigation, lazy Description / Game Features / Repack Features / gallery / GIF content, home rails, local collections with JSON import/export, local recommendations, and catalog health status.

## Automation

Catalog writers share the `catalog-writer` concurrency group. Each queued writer checks out the latest `main` only after it acquires the writer slot, preventing a stale event SHA from conflicting with a previous robot's `games.json` update.

- `Catalog Refresh` updates the newest listing pages hourly.
- `Full Catalog Backfill` periodically scans every discoverable listing page.
- `Media Enrichment` fills descriptions, feature lists, screenshots and GIF metadata in accelerated batches.
- `Deploy Pages` builds the lightweight V2 artifact, runs static checks, deploys it, then health-checks the public `catalog.json`, `health.json` and a lazy game payload.

## Local preview

Build the public V2 payloads before serving the site:

```bash
python tools/build_site_data.py
python -m http.server 8080 -d site
```

Then open `http://localhost:8080`.

## Repository layout

- `site/` — production static site
- `site/data/games.json` — rich generated source catalog (repository-side)
- `tools/update_catalog.py` — lightweight metadata updater
- `tools/enrich_media.py` — detail/media enrichment worker
- `tools/build_site_data.py` — builds lightweight catalog, health and lazy detail payloads
- `tools/validate_catalog.py` — schema/data validation
- `tools/check_site.py` — static frontend smoke checks
- `.github/workflows/ci.yml` — parallel verification robots
- `.github/workflows/update-catalog.yml` — scheduled recent catalog refresh
- `.github/workflows/backfill-catalog.yml` — full catalog scanner
- `.github/workflows/enrich-media.yml` — scheduled detail/media enrichment
- `.github/workflows/pages.yml` — V2 build, deployment and production healthcheck

## Safety boundary

The catalog stores public metadata and links back to source pages. It does not index magnet URIs or download mirrors.
