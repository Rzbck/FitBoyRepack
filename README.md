# FitBoyRepack

Lightweight static game metadata catalog.

## Architecture

`source -> GitHub Action -> metadata normalizer -> site/data/games.json -> static frontend -> GitHub Pages`

The runtime site has no Flask server, no database, no Supabase dependency, and no authentication service.

## Local preview

```bash
python -m http.server 8080 -d site
```

Then open `http://localhost:8080`.

## Repository layout

- `site/` — production static site
- `site/data/games.json` — generated catalog
- `tools/update_catalog.py` — lightweight metadata updater
- `tools/validate_catalog.py` — schema/data validation
- `tools/check_site.py` — static frontend smoke checks
- `.github/workflows/ci.yml` — parallel verification robots
- `.github/workflows/update-catalog.yml` — scheduled catalog refresh
- `.github/workflows/pages.yml` — GitHub Pages deployment

## Safety boundary

The catalog stores public metadata and links back to source pages. It does not index magnet URIs or download mirrors.
