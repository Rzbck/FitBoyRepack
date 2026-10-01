#!/usr/bin/env python3
import enrich_media_v6 as v6

base = v6.base
MEDIA_VERSION = 7


def _media_item(full_url, preview_url, kind):
    item = {"url": full_url, "type": kind}
    if preview_url and base.normalize_identity(preview_url) != base.normalize_identity(full_url):
        item["preview_url"] = preview_url
    return item


def _valid_preview(url):
    return bool(url and (base.IMAGE_EXT_RE.search(url) or base.GIF_RE.search(url)))


def extract_media_v7(html, source_url, cover_url, client=None):
    soup = base.BeautifulSoup(html, "lxml")
    content = soup.select_one("div.entry-content")
    if not content:
        return []

    cover = base.normalize_identity(cover_url or "")
    media = []
    seen = set()

    # GIF: keep the lightweight source rendered by the page for the card preview,
    # while V6 still probes all candidates and stores the largest accessible GIF
    # as the full-size/lightbox URL.
    for img in content.find_all("img"):
        preview = base.img_src(img, source_url)
        alt = img.get("alt", "")
        classes = " ".join(img.get("class", []))
        parent = img.find_parent("a", href=True)
        linked = base.clean_url(source_url, parent.get("href")) if parent else ""
        if base.has_skip_hint(preview, linked, alt, classes):
            continue
        full = v6.best_gif_url(img, source_url, client=client)
        identity = base.normalize_identity(full)
        if not full or not identity or identity == cover:
            continue
        if not _valid_preview(preview):
            preview = ""
        media.append(_media_item(full, preview, "gif"))
        seen.add(identity)
        break

    # Screenshots: the source site exposes a 240p thumbnail plus a linked/srcset
    # original. Keep both so the dialog appears quickly without sacrificing the
    # full-resolution lightbox.
    for img in content.find_all("img"):
        preview = base.img_src(img, source_url)
        if not preview or not base.SCREENSHOT_THUMB_RE.search(preview):
            continue
        alt = img.get("alt", "")
        classes = " ".join(img.get("class", []))
        parent = img.find_parent("a", href=True)
        linked = base.clean_url(source_url, parent.get("href")) if parent else ""
        if base.has_skip_hint(preview, linked, alt, classes):
            continue

        full = ""
        if linked and base.IMAGE_EXT_RE.search(linked) and not base.SCREENSHOT_THUMB_RE.search(linked):
            full = linked
        if not full:
            for srcset_url in v6.v5.v4.srcset_candidates(img, source_url):
                if not base.SCREENSHOT_THUMB_RE.search(srcset_url):
                    full = srcset_url
                    break
        if not full:
            full = v6.v5.v4.promote_thumbnail(preview)

        if base.has_skip_hint(full):
            continue
        identity = base.normalize_identity(full)
        if not identity or identity == cover or identity in seen:
            continue
        seen.add(identity)
        media.append(_media_item(full, preview, "image"))
        if len(media) >= base.MAX_MEDIA_PER_GAME:
            break

    return media


def enrich_one(client, game):
    html = base.request_text(client, game["source_url"])
    return (
        game["id"],
        extract_media_v7(html, game["source_url"], game.get("image_url"), client=client),
        base.extract_details(html),
    )


base.MEDIA_VERSION = MEDIA_VERSION
base.HEADERS["User-Agent"] = "Mozilla/5.0 (compatible; FitBoyRepackDetails/7.0)"
base.extract_media = lambda html, source_url, cover_url: extract_media_v7(html, source_url, cover_url)
base.enrich_one = enrich_one

if __name__ == "__main__":
    base.main()
