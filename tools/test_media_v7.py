#!/usr/bin/env python3
from enrich_media_v7 import MEDIA_VERSION, extract_media_v7

HTML = """
<html><body>
  <div class="entry-content">
    <a href="https://cdn.example/game-full.gif">
      <img src="https://cdn.example/game-preview.gif">
    </a>
    <a href="https://cdn.example/screen-01.jpg">
      <img src="https://cdn.example/screen-01.jpg.240p.jpg">
    </a>
    <img src="https://cdn.example/screen-02.jpg.240p.jpg"
         srcset="https://cdn.example/screen-02-medium.jpg 640w, https://cdn.example/screen-02-full.jpg 1920w">
  </div>
</body></html>
"""

media = extract_media_v7(HTML, "https://fitgirl-repacks.site/example/", "")
assert MEDIA_VERSION == 7
assert media[0] == {
    "url": "https://cdn.example/game-full.gif",
    "preview_url": "https://cdn.example/game-preview.gif",
    "type": "gif",
}, media
assert {
    "url": "https://cdn.example/screen-01.jpg",
    "preview_url": "https://cdn.example/screen-01.jpg.240p.jpg",
    "type": "image",
} in media, media
assert {
    "url": "https://cdn.example/screen-02-full.jpg",
    "preview_url": "https://cdn.example/screen-02.jpg.240p.jpg",
    "type": "image",
} in media, media
print("media v7 preview/full pairing OK")
