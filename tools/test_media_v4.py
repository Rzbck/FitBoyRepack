#!/usr/bin/env python3
from enrich_media_clustered import partition_candidates, worker_allocation
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

items = [{"id": str(i)} for i in range(8)]
groups = partition_candidates(items, 4)
assert [len(group) for group in groups] == [2, 2, 2, 2], groups
assert [group[0]["id"] for group in groups] == ["0", "1", "2", "3"], groups
assert worker_allocation(20, 4) == [5, 5, 5, 5]
assert worker_allocation(7, 4) == [2, 2, 2, 1]

print("media v4 full-size selection and clustered workers OK")
