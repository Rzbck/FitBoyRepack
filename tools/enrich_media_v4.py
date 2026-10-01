#!/usr/bin/env python3
import re
from urllib.parse import urlsplit, urlunsplit

import enrich_media as base

MEDIA_VERSION = 4
THUMB_PATH_RE = re.compile(r"\.jpg\.240p\.jpg$", re.IGNORECASE)


def srcset_candidates(img, base_url):
    candidates = []
    for attr in ("data-srcset", "srcset"):
        raw = img.get(attr) or ""
        for part in raw.split(","):
            bits = part.strip().split()
            if not bits:
                continue
            url = base.clean_url(base_url, bits[0])
            if not url or not base.IMAGE_EXT_RE.search(url):
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
    return [url for _, url in sorted(candidates, key=lambda item: item[0], reverse=True)]


def promote_thumbnail(url):
    if not url:
        return ""
    parts = urlsplit(url)
    path = THUMB_PATH_RE.sub(".jpg", parts.path)
    if path == parts.path:
        return url
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def extract_media_v4(html, source_url, cover_url):
    soup = base.BeautifulSoup(html, "lxml")
    content = soup.select_one("div.entry-content")
    if not content:
        return []

    cover = base.normalize_identity(cover_url or "")
    media = []
    seen = set()

    for img in content.find_all("img"):
        source = base.img_src(img, source_url)
        if not source:
            continue
        alt = img.get("alt", "")
        classes = " ".join(img.get("class", []))
        parent = img.find_parent("a", href=True)
        linked = base.clean_url(source_url, parent.get("href")) if parent else ""
        if base.has_skip_hint(source, linked, alt, classes):
            continue
        candidate = linked if linked and base.GIF_RE.search(linked) else source
        identity = base.normalize_identity(candidate)
        if base.GIF_RE.search(candidate) and identity and identity != cover:
            seen.add(identity)
            media.append({"url": candidate, "type": "gif"})
            break

    for img in content.find_all("img"):
        source = base.img_src(img, source_url)
        if not source or not base.SCREENSHOT_THUMB_RE.search(source):
            continue
        alt = img.get("alt", "")
        classes = " ".join(img.get("class", []))
        parent = img.find_parent("a", href=True)
        linked = base.clean_url(source_url, parent.get("href")) if parent else ""
        if base.has_skip_hint(source, linked, alt, classes):
            continue

        candidate = ""
        if linked and base.IMAGE_EXT_RE.search(linked) and not base.SCREENSHOT_THUMB_RE.search(linked):
            candidate = linked
        if not candidate:
            for srcset_url in srcset_candidates(img, source_url):
                if not base.SCREENSHOT_THUMB_RE.search(srcset_url):
                    candidate = srcset_url
                    break
        if not candidate:
            candidate = promote_thumbnail(source)

        if base.has_skip_hint(candidate):
            continue
        identity = base.normalize_identity(candidate)
        if not identity or identity == cover or identity in seen:
            continue
        seen.add(identity)
        media.append({"url": candidate, "type": "image"})
        if len(media) >= base.MAX_MEDIA_PER_GAME:
            break

    return media


base.MEDIA_VERSION = MEDIA_VERSION
base.HEADERS["User-Agent"] = "Mozilla/5.0 (compatible; FitBoyRepackDetails/4.0)"
base.extract_media = extract_media_v4

if __name__ == "__main__":
    base.main()
