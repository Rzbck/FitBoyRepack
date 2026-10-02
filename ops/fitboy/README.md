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


## Publication des métadonnées vérifiées vers le front

Les workers gardent toujours la base SQLite privée sur le VPS. Le front public ne reçoit
qu'un snapshot JSON minimal généré par `tools/export_public_metadata.py`.

Le snapshot public contient uniquement, pour les jobs actifs en `done` avec confiance >= 0.90 :

- titre canonique ;
- date de sortie du jeu ;
- genres ;
- développeur / éditeur ;
- plateformes ;
- score de confiance ;
- URLs de preuve Wikidata/Wikipedia ;
- date de vérification.

Il n'exporte jamais les prompts, sorties brutes du modèle, erreurs, notes internes, files de jobs
ou autres données de fonctionnement.

Génération locale sur le VPS :

```bash
python tools/export_public_metadata.py \
  --db /var/lib/fitboy/ai/catalog_enrichment.sqlite3 \
  --output /var/lib/fitboy/ai/metadata-enrichment.json
```

Le build statique fusionne ce snapshot sans modifier `site/data/games.json`. Les champs publics
sont ajoutés sous `verified_metadata` dans les fiches lazy et quelques champs légers sont ajoutés
au catalogue pour la recherche.

### Publication automatique GitHub

`metadata-publish.service` publie uniquement le fichier généré vers
`site/data/metadata-enrichment.json`. Il nécessite un jeton GitHub finement limité au dépôt
`Rzbck/FitBoyRepack` avec uniquement la permission **Contents: Read and write**.

Créer le fichier local sans jamais le committer :

```bash
sudo install -d -m 0750 -o root -g fitboy /etc/fitboy
sudo install -m 0640 -o root -g fitboy ops/fitboy/metadata-publisher.env.example /etc/fitboy/metadata-publisher.env
sudoedit /etc/fitboy/metadata-publisher.env
```

Puis installer les unités et activer le timer :

```bash
sudo install -m 0644 ops/fitboy/metadata-publish.service /etc/systemd/system/metadata-publish.service
sudo install -m 0644 ops/fitboy/metadata-publish.timer /etc/systemd/system/metadata-publish.timer
sudo systemctl daemon-reload
sudo systemctl enable --now metadata-publish.timer
```

Le publisher compare le snapshot distant avant d'écrire. S'il n'y a aucun changement, aucun commit
n'est créé et GitHub Pages n'est pas redéployé inutilement. En cas de changement, la mise à jour de
`site/data/metadata-enrichment.json` déclenche automatiquement le workflow Pages.
