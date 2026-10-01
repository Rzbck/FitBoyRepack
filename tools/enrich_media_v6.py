#!/usr/bin/env python3
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import enrich_media_v5 as v5

base = v5.base
MEDIA_VERSION = 6
MAX_GIF_PROBES = 6
GIF_HEADER_BYTES = 32
GIF_HINT_ATTR_RE = re.compile(r"(?:src|href|url|file|orig|full|large|gif)", re.IGNORECASE)
RESIZE_QUERY_KEYS = {"w", "width", "h", "height", "resize", "fit", "crop"}


def strip_resize_query(url):
    if not url:
        return ""
    parts = urlsplit(url)
    if not base.GIF_RE.search(parts.path):
        return url
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    kept = [(key, value) for key, value in pairs if key.casefold() not in RESIZE_QUERY_KEYS]
    if len(kept) == len(pairs):
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


def _add_candidate(ranked, url, score):
    if not url or not base.GIF_RE.search(url):
        return
    previous = ranked.get(url)
    if previous is None or score > previous:
        ranked[url] = score


def _gif_urls_from_attr(node, source_url, ranked, base_score):
    if not node:
        return
    for key, raw in node.attrs.items():
        if not GIF_HINT_ATTR_RE.search(str(key)):
            continue
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        for value in values:
            text = str(value or "")
            for part in text.split(","):
                token = part.strip().split()[0] if part.strip() else ""
                url = base.clean_url(source_url, token)
                if url and base.GIF_RE.search(url):
                    _add_candidate(ranked, url, base_score)


def gif_candidates(img, source_url):
    ranked = {}
    parent = img.find_parent("a", href=True)
    if parent:
        linked = base.clean_url(source_url, parent.get("href"))
        _add_candidate(ranked, linked, 100000.0)
        _gif_urls_from_attr(parent, source_url, ranked, 94000.0)

    for index, attr in enumerate(v5.GIF_DATA_ATTRS):
        value = base.clean_url(source_url, img.get(attr))
        _add_candidate(ranked, value, 92000.0 - index)

    for score, value in v5.srcset_gif_candidates(img, source_url):
        _add_candidate(ranked, value, 76000.0 + score)

    picture = img.find_parent("picture")
    if picture:
        for source in picture.find_all("source"):
            for score, value in v5.srcset_gif_candidates(source, source_url):
                _add_candidate(ranked, value, 80000.0 + score)
            _gif_urls_from_attr(source, source_url, ranked, 79000.0)

    _gif_urls_from_attr(img, source_url, ranked, 88000.0)

    source = base.img_src(img, source_url)
    if source and base.GIF_RE.search(source):
        promoted = v5.promote_resized_gif(source)
        _add_candidate(ranked, promoted, 70000.0)
        _add_candidate(ranked, strip_resize_query(promoted), 69000.0)
        _add_candidate(ranked, strip_resize_query(source), 68000.0)
        _add_candidate(ranked, source, 60000.0)

    return sorted(((score, url) for url, score in ranked.items()), reverse=True)


def probe_gif_dimensions(client, url):
    if client is None or not url:
        return (0, 0, 0)
    try:
        headers = {"Range": f"bytes=0-{GIF_HEADER_BYTES - 1}", "Accept": "image/gif,*/*;q=0.8"}
        prefix = bytearray()
        total_bytes = 0
        with client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            content_range = response.headers.get("content-range", "")
            match = re.search(r"/(\d+)$", content_range)
            if match:
                total_bytes = int(match.group(1))
            else:
                try:
                    total_bytes = int(response.headers.get("content-length") or 0)
                except ValueError:
                    total_bytes = 0
            for chunk in response.iter_bytes(chunk_size=GIF_HEADER_BYTES):
                prefix.extend(chunk)
                if len(prefix) >= GIF_HEADER_BYTES:
                    break
        if len(prefix) < 10 or bytes(prefix[:6]) not in {b"GIF87a", b"GIF89a"}:
            return (0, 0, total_bytes)
        width = int.from_bytes(prefix[6:8], "little")
        height = int.from_bytes(prefix[8:10], "little")
        if width <= 0 or height <= 0:
            return (0, 0, total_bytes)
        return (width, height, total_bytes)
    except Exception:
        return (0, 0, 0)


def best_gif_url(img, source_url, client=None):
    candidates = gif_candidates(img, source_url)
    if not candidates:
        return ""
    if client is None or len(candidates) == 1:
        return candidates[0][1]

    best = None
    for heuristic, url in candidates[:MAX_GIF_PROBES]:
        width, height, total_bytes = probe_gif_dimensions(client, url)
        if not width or not height:
            continue
        score = (width * height, total_bytes, heuristic)
        if best is None or score > best[0]:
            best = (score, url)
    return best[1] if best else candidates[0][1]


def extract_media_v6(html, source_url, cover_url, client=None):
    soup = base.BeautifulSoup(html, "lxml")
    content = soup.select_one("div.entry-content")
    if not content:
        return []

    cover = base.normalize_identity(cover_url or "")
    gif = ""
    for img in content.find_all("img"):
        source = base.img_src(img, source_url)
        alt = img.get("alt", "")
        classes = " ".join(img.get("class", []))
        parent = img.find_parent("a", href=True)
        linked = base.clean_url(source_url, parent.get("href")) if parent else ""
        if base.has_skip_hint(source, linked, alt, classes):
            continue
        candidate = best_gif_url(img, source_url, client=client)
        identity = base.normalize_identity(candidate)
        if candidate and identity and identity != cover:
            gif = candidate
            break

    legacy = v5.v4.extract_media_v4(html, source_url, cover_url)
    images = [item for item in legacy if item.get("type") == "image"]
    media = []
    if gif:
        media.append({"url": gif, "type": "gif"})
    media.extend(images[: max(0, base.MAX_MEDIA_PER_GAME - len(media))])
    return media


def enrich_one(client, game):
    html = base.request_text(client, game["source_url"])
    return (
        game["id"],
        extract_media_v6(html, game["source_url"], game.get("image_url"), client=client),
        base.extract_details(html),
    )


base.MEDIA_VERSION = MEDIA_VERSION
base.HEADERS["User-Agent"] = "Mozilla/5.0 (compatible; FitBoyRepackDetails/6.0)"
base.extract_media = lambda html, source_url, cover_url: extract_media_v6(html, source_url, cover_url)
base.enrich_one = enrich_one

if __name__ == "__main__":
    base.main()
