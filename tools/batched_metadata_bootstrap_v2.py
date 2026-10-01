#!/usr/bin/env python3
"""Batched metadata bootstrap with a search-only normalization fallback.

The existing batched worker remains authoritative for queue handling, scoring,
progress output, caching, batching and rate-limit behavior. This wrapper changes
only title discovery: a normal cleaned-title query is tried first; only when it
returns no candidate IDs do we retry once with an aggressively normalized search
variant intended to remove repack/package/version suffixes.
"""
from __future__ import annotations

import re

import batched_metadata_bootstrap as base
from fast_metadata_bootstrap import clean_fast_title as conservative_clean


_PACKAGE_WORDS = (
    r"edition|bundle|collection|pack|content|soundtrack|ost|"
    r"game\s+of\s+the\s+year|goty"
)


def aggressive_search_title(title: str) -> str:
    """Return a base-game-oriented title used only after a zero-result search."""
    value = conservative_clean(title)

    # Versions/builds that survive the conservative cleaner because they contain
    # slashes, update annotations or unusual vendor formatting.
    value = re.sub(
        r"\s*[,–—-]\s*(?:"
        r"v(?:ersion)?\s*[0-9][^,–—]*|"
        r"ver\.?\s*[0-9][^,–—]*|"
        r"build\s+[0-9][^,–—]*|"
        r"update\s+[0-9][^,–—]*"
        r")$",
        "",
        value,
        flags=re.I,
    )

    # Repack/platform-fix notes are not part of the canonical game identity.
    value = re.sub(
        r"\s*(?:\([^)]*(?:repack|portable|crack|fix)[^)]*\)|"
        r"\[[^]]*(?:repack|portable|crack|fix)[^]]*\])\s*$",
        "",
        value,
        flags=re.I,
    )

    # Search fallback only: if the normal title had no result, remove a trailing
    # package/edition subtitle. The normal query always gets first chance, so an
    # official title that really includes this suffix is not discarded eagerly.
    value = re.sub(
        rf"\s*[:–—-]\s*[^:–—]{{0,90}}\b(?:{_PACKAGE_WORDS})\b\s*$",
        "",
        value,
        flags=re.I,
    )

    # Common marketing suffixes that do not necessarily end in the literal word
    # 'Edition' after conservative cleaning.
    value = re.sub(
        r"\s*[:–—-]\s*(?:"
        r"deluxe|ultimate|gold|complete|special|definitive|anniversary|"
        r"supporter|collector(?:'s)?|digital\s+deluxe|all[- ]inclusive"
        r")[^:–—]{0,80}$",
        "",
        value,
        flags=re.I,
    )

    value = re.sub(r"\s{2,}", " ", value).strip(" ,;:-–—")
    return value or conservative_clean(title)


class NormalizedSearchClient(base.BatchWikidataClient):
    def _search_query(self, query: str, limit: int) -> list[str]:
        data = self._get({
            "action": "wbsearchentities",
            "search": query,
            "language": "en",
            "uselang": "en",
            "type": "item",
            "limit": limit,
        })
        return [
            str(item["id"])
            for item in data.get("search", [])
            if isinstance(item, dict) and item.get("id")
        ]

    def search(self, title: str, limit: int) -> list[str]:
        primary = conservative_clean(title)
        ids = self._search_query(primary, limit)
        if ids:
            return ids

        fallback = aggressive_search_title(title)
        if not fallback or fallback.casefold() == primary.casefold():
            return []
        return self._search_query(fallback, limit)


# Scoring/progress should compare the discovered Wikidata candidate against the
# same base-game title used by the fallback, while queue/cache semantics remain
# unchanged in the underlying worker.
base.BatchWikidataClient = NormalizedSearchClient
base.clean_fast_title = aggressive_search_title


if __name__ == "__main__":
    base.main()
