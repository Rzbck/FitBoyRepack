#!/usr/bin/env python3
import httpx

from enrich_media_v6 import (
    MEDIA_VERSION,
    best_gif_url,
    extract_media_v6,
    probe_gif_dimensions,
    strip_resize_query,
)
import enrich_media_v6 as v6


def gif_header(width, height):
    return b"GIF89a" + int(width).to_bytes(2, "little") + int(height).to_bytes(2, "little") + b"\x00" * 22


GIFS = {
    "/linked.gif": (480, 270, 140_000),
    "/full.gif": (1280, 720, 1_100_000),
    "/small.gif": (640, 360, 350_000),
    "/small-320x180.gif": (320, 180, 95_000),
}


def handler(request):
    info = GIFS.get(request.url.path)
    if not info:
        return httpx.Response(404, request=request)
    width, height, total = info
    return httpx.Response(
        206,
        request=request,
        headers={"Content-Type": "image/gif", "Content-Range": f"bytes 0-31/{total}"},
        content=gif_header(width, height),
    )


HTML = """
<html><body>
  <div class="entry-content">
    <a href="https://cdn.example/linked.gif">
      <img src="https://cdn.example/small-320x180.gif?resize=320%2C180"
           data-original="https://cdn.example/full.gif">
    </a>
    <a href="https://cdn.example/screen-01.jpg"><img src="https://cdn.example/screen-01.jpg.240p.jpg"></a>
    <img src="https://cdn.example/screen-02.jpg.240p.jpg"
         srcset="https://cdn.example/screen-02-medium.jpg 640w, https://cdn.example/screen-02-full.jpg 1920w">
  </div>
</body></html>
"""

assert MEDIA_VERSION == 6
assert strip_resize_query("https://cdn.example/a.gif?resize=320%2C180&w=320&token=x") == "https://cdn.example/a.gif?token=x"
assert strip_resize_query("https://cdn.example/a.jpg?w=320") == "https://cdn.example/a.jpg?w=320"

soup = v6.base.BeautifulSoup(HTML, "lxml")
img = soup.find("img")
with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
    assert probe_gif_dimensions(client, "https://cdn.example/full.gif")[:2] == (1280, 720)
    # The linked GIF has the strongest HTML hint, but the robot must choose the
    # genuinely larger data-original candidate after probing real dimensions.
    assert best_gif_url(img, "https://fitgirl-repacks.site/example/", client=client) == "https://cdn.example/full.gif"
    media = extract_media_v6(HTML, "https://fitgirl-repacks.site/example/", "", client=client)

assert media[0] == {"url": "https://cdn.example/full.gif", "type": "gif"}, media
assert {"url": "https://cdn.example/screen-01.jpg", "type": "image"} in media
assert {"url": "https://cdn.example/screen-02-full.jpg", "type": "image"} in media
print("media v6 real-dimension GIF selection OK")
