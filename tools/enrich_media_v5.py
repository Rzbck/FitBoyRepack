#!/usr/bin/env python3
import re
from urllib.parse import urlsplit, urlunsplit

import enrich_media_v4 as v4

base = v4.base
MEDIA_VERSION = 5

GIF_SIZE_SUFFIX_RE = re.compile(r"-\d{2,5}x\d{2,5}(?=\.gif$)", re.IGNORECASE)
GIF_DATA_ATTRS = (
    "data-original",
    "data-full",
    "data-orig-file",
    "data-large-file",
    "data-lazy-src",
    "data-src",
    "src",
)


def promote_resized_gif(url):
    if not url:
        return ""
    parts = urlsplit(url)
    path = GIF_SIZE_SUFFIX_RE.sub("", parts.path)
    if path == parts.path:
        return url
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def srcset_gif_candidates(node, base_url):
    candidates = []
    for attr in ("data-srcset", "srcset"):
        raw = node.get(attr) or ""
        for part in raw.split(","):
            bits = part.strip().split()
            if not bits:
                continue
            url = base.clean_url(base_url, bits[0])
            if not url or not base.GIF_RE.search(url):
                continue
            score = 0.0
            if len(bits) > 1:
                descriptor = bits[1].lower()
                try:
                    if descriptor.endswith("w"):
                        score = float(descriptor[:-1])
                    elif descriptor.endswith("x"):
                        score = float(descriptor[:-1]) * 1000
                except ValueError:
                    score = 0.0
            candidates.append((score, url))
    return sorted(candidates, key=lambda item: item[0], reverse=True)


def best_gif_url(img, source_url):
    ranked = []
    parent = img.find_parent("a", href=True)
    if parent:
        linked = base.clean_url(source_url, parent.get("href"))
        if linked and base.GIF_RE.search(linked):
            ranked.append((100000.0, linked))

    for index, attr in enumerate(GIF_DATA_ATTRS):
        value = base.clean_url(source_url, img.get(attr))
        if value and base.GIF_RE.search(value):
            ranked.append((90000.0 - index, value))

    for score, value in srcset_gif_candidates(img, source_url):
        ranked.append((70000.0 + score, value))

    picture = img.find_parent("picture")
    if picture:
        for source in picture.find_all("source"):
            for score, value in srcset_gif_candidates(source, source_url):
                ranked.append((75000.0 + score, value))

    source = base.img_src(img, source_url)
    promoted = promote_resized_gif(source)
    if promoted and promoted != source and base.GIF_RE.search(promoted):
        ranked.append((60000.0, promoted))
    if source and base.GIF_RE.search(source):
        ranked.append((50000.0, source))

    if not ranked:
        return ""
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def extract_media_v5(html, source_url, cover_url):
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
        candidate = best_gif_url(img, source_url)
        identity = base.normalize_identity(candidate)
        if candidate and identity and identity != cover:
            gif = candidate
            break

    legacy = v4.extract_media_v4(html, source_url, cover_url)
    images = [item for item in legacy if item.get("type") == "image"]
    media = []
    if gif:
        media.append({"url": gif, "type": "gif"})
    media.extend(images[: max(0, base.MAX_MEDIA_PER_GAME - len(media))])
    return media


base.MEDIA_VERSION = MEDIA_VERSION
base.HEADERS["User-Agent"] = "Mozilla/5.0 (compatible; FitBoyRepackDetails/5.0)"
base.extract_media = extract_media_v5

if __name__ == "__main__":
    base.main()
