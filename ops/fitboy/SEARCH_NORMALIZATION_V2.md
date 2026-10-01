# Search normalization v2

The batched metadata worker first queries Wikidata with the normal cleaned title.
If that search returns no candidate IDs, it retries once with a more aggressive
search-only normalization that removes repack/package suffixes such as Deluxe,
Gold, Ultimate, Complete, Special, Definitive, Anniversary, Supporter and bundle
labels. The aggressive variant is used only for discovery; accepted canonical
metadata still comes from Wikidata and must pass the existing confidence checks.
