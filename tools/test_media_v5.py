#!/usr/bin/env python3
from enrich_media_clustered import partition_candidates, worker_allocation
from enrich_media_v5 import MEDIA_VERSION, best_gif_url, extract_media_v5, promote_resized_gif
import enrich_media_v5 as v5

HTML = """
<html><body>
  <div class="entry-content">
    <picture>
      <source srcset="https://cdn.example/game-640.gif 640w, https://cdn.example/game-1280.gif 1280w">
      <img src="https://cdn.example/game-320x180.gif" data-original="https://cdn.example/game-original.gif">
    </picture>
    <a href="https://cdn.example/screen-01.jpg"><img src="https://cdn.example/screen-01.jpg.240p.jpg"></a>
    <img src="https://cdn.example/screen-02.jpg.240p.jpg"
         srcset="https://cdn.example/screen-02-medium.jpg 640w, https://cdn.example/screen-02-full.jpg 1920w">
  </div>
</body></html>
"""

media = extract_media_v5(HTML, "https://fitgirl-repacks.site/example/", "")
assert MEDIA_VERSION == 5
assert media[0] == {"url": "https://cdn.example/game-original.gif", "type": "gif"}, media
assert {"url": "https://cdn.example/screen-01.jpg", "type": "image"} in media
assert {"url": "https://cdn.example/screen-02-full.jpg", "type": "image"} in media
assert promote_resized_gif("https://cdn.example/game-480x270.gif") == "https://cdn.example/game.gif"
assert promote_resized_gif("https://cdn.example/game.gif") == "https://cdn.example/game.gif"

soup = v5.base.BeautifulSoup(
    '<div class="entry-content"><a href="https://cdn.example/full.gif"><img src="https://cdn.example/small.gif"></a></div>',
    "lxml",
)
img = soup.find("img")
assert best_gif_url(img, "https://fitgirl-repacks.site/example/") == "https://cdn.example/full.gif"

items = [{"id": str(i)} for i in range(8)]
groups = partition_candidates(items, 4)
assert [len(group) for group in groups] == [2, 2, 2, 2], groups
assert worker_allocation(20, 4) == [5, 5, 5, 5]

print("media v5 GIF source selection and clustered workers OK")
