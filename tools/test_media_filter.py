#!/usr/bin/env python3
from enrich_media import MEDIA_VERSION, extract_media

HTML = """
<html><body>
  <div class="entry-content">
    <img src="https://widgets.example/registered-users.png" alt="Registered users widget">
    <img src="https://cdn.example/game-cover.jpg" alt="cover">
    <a href="https://cdn.example/screen-01.jpg"><img src="https://cdn.example/screen-01.jpg.240p.jpg"></a>
    <a href="https://cdn.example/screen-02.png"><img data-lazy-src="https://cdn.example/screen-02.jpg.240p.jpg"></a>
    <img src="https://cdn.example/animation.gif">
    <img src="https://cdn.example/site-logo.jpg" class="logo">
    <img src="https://cdn.example/random-entry-image.jpg">
  </div>
</body></html>
"""

media = extract_media(HTML, "https://fitgirl-repacks.site/example/", "https://cdn.example/game-cover.jpg")
assert MEDIA_VERSION == 2
assert media == [
    {"url": "https://cdn.example/screen-01.jpg", "type": "image"},
    {"url": "https://cdn.example/screen-02.png", "type": "image"},
    {"url": "https://cdn.example/animation.gif", "type": "gif"},
], media
assert all("registered-users" not in item["url"] for item in media)
assert all("random-entry-image" not in item["url"] for item in media)
print("media filter OK")
