#!/usr/bin/env python3
from enrich_media import DETAILS_VERSION, MEDIA_VERSION, extract_details, extract_media

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

    <div class="su-spoiler-title">Game Description</div>
    <div class="su-spoiler-content">
      Explore a large fantasy world with your party.
      <h3>Game Features</h3>
      <ul><li>Turn-based tactical combat</li><li>Online co-op</li></ul>
    </div>
    <h3>Repack Features</h3>
    <ul><li>Based on the latest build</li><li>Nothing ripped</li></ul>
  </div>
</body></html>
"""

media = extract_media(HTML, "https://fitgirl-repacks.site/example/", "https://cdn.example/game-cover.jpg")
assert MEDIA_VERSION == 3
assert media == [
    {"url": "https://cdn.example/animation.gif", "type": "gif"},
    {"url": "https://cdn.example/screen-01.jpg", "type": "image"},
    {"url": "https://cdn.example/screen-02.png", "type": "image"},
], media
assert all("registered-users" not in item["url"] for item in media)
assert all("random-entry-image" not in item["url"] for item in media)
assert sum(item["type"] == "gif" for item in media) == 1

details = extract_details(HTML)
assert DETAILS_VERSION == 1
assert "Explore a large fantasy world" in details["description"]
assert details["game_features"] == ["Turn-based tactical combat", "Online co-op"], details
assert details["repack_features"] == ["Based on the latest build", "Nothing ripped"], details
print("media/details parser OK")
