#!/usr/bin/env python3
from enrich_media_v4 import MEDIA_VERSION, extract_media_v4, promote_thumbnail

HTML = """
<html><body>
  <div class="entry-content">
    <img src="https://cdn.example/animation.gif">
    <a href="https://cdn.example/screen-01.jpg"><img src="https://cdn.example/screen-01.jpg.240p.jpg"></a>
    <img src="https://cdn.example/screen-02.jpg.240p.jpg"
         srcset="https://cdn.example/screen-02-medium.jpg 640w, https://cdn.example/screen-02-full.jpg 1920w">
    <img src="https://cdn.example/screen-03.jpg.240p.jpg">
  </div>
</body></html>
"""

media = extract_media_v4(HTML, "https://fitgirl-repacks.site/example/", "")
assert MEDIA_VERSION == 4
assert media == [
    {"url": "https://cdn.example/animation.gif", "type": "gif"},
    {"url": "https://cdn.example/screen-01.jpg", "type": "image"},
    {"url": "https://cdn.example/screen-02-full.jpg", "type": "image"},
    {"url": "https://cdn.example/screen-03.jpg", "type": "image"},
], media
assert promote_thumbnail("https://cdn.example/folder/name.jpg.240p.jpg") == "https://cdn.example/folder/name.jpg"
assert promote_thumbnail("https://cdn.example/folder/name.jpg") == "https://cdn.example/folder/name.jpg"
print("media v4 full-size selection OK")
