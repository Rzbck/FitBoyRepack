#!/usr/bin/env python3
from catalog_classifier import classify_record


def record(title, genres=None, size="N/A", image="", description="", media=None):
    return {
        "id": title.lower().replace(" ", "-"),
        "title": title,
        "source_url": "https://fitgirl-repacks.site/example/",
        "image_url": image,
        "genres": genres or [],
        "repack_size": size,
        "details": {"description": description} if description else {},
        "media": media or [],
    }


def expect(title, expected, **kwargs):
    decision = classify_record(record(title, **kwargs))
    assert decision["kind"] == expected, f"{title!r}: expected {expected}, got {decision}"
    return decision


for title in (
    "A Call for Donations",
    "Donations page updonated",
    "HyperVisor Cracks – Status Update",
    "About Hypervisor Cracks",
    "DQH2 & TWWH2 Proper Cracks Added",
    "Horizon: Forbidden West – Complete Edition Updates posted",
    "Hellblade: Senua’s Sacrifice Repack Updated",
    "Outer Wilds Repack Updated",
    "Detroit: Become Human – Updated Repack test",
    "Man O’ War: Corsair Repack Updated",
    "The Issue with Direct Download Links Should Be Fixed Now",
    "Yet another fix for MEA repack :)",
    "Some people just can’t be fixed",
    "Installer fixes",
    "Updates Digest #42",
    "Upcoming Repacks",
):
    expect(title, "non_game")

expect(
    "Fallout 4: High Resolution Texture Pack – for v1.10.980.0+",
    "non_game",
    genres=["Action", "Shooter"],
    size="34.8 GB",
    image="https://example.invalid/fallout-textures.jpg",
)

for title in (
    "Bō: Path of the Teal Lotus – Soundtrack Bundle, v1.2.7 + Bonus OST",
    "Captain Contraption’s Chocolate Factory – Soundtrack Bundle, v1.22 + Bonus OST",
    "Homura Hime: Soundtrack Bundle, v1.0.8 + Bonus OST",
    "Keylocker: Turn Based Cyberpunk Action – Soundtrack Bundle, Build 16635931 + Bonus OST",
    "ROBOTICS;NOTES ELITE + Mini-soundtrack",
    "Republic of Pirates: Soundtrack Bundle – v0.24.3 + Bonus OST",
    "THE TAG-ALONG OBSESSION: Soundtrack Bundle, Update 10/04 + Bonus OST",
):
    expect(
        title,
        "game",
        genres=["Adventure"],
        size="2.4 GB",
        image="https://example.invalid/cover.jpg",
        description="A complete game description.",
        media=[{"type": "image", "url": "https://example.invalid/shot.jpg"}],
    )

expect(
    "eFootball PES 2021 Season Update – v1.01.00 Data Pack 1.00",
    "game",
    genres=["Sports", "Soccer"],
    size="25.0 GB",
)
expect("Get To The Top + Windows 7 Fix", "game", genres=["Arcade", "Side"], size="2.0 GB")
expect(
    "V Rising + DLC Bundle, v1.1.13.0 + Dedicated Server + Windows 7 Fix",
    "game",
    genres=["RPG", "Open world"],
    size="7.2 GB",
)
expect("Overmorrow + Bonus Soundtrack", "game", genres=["Adventure", "Isometric"], size="280 MB")
expect("Example Game – Deluxe Edition, v1.0 + HD Texture Pack", "game", genres=["Action"], size="12 GB")

review = expect("A mysterious uncategorized post", "review", image="https://example.invalid/post.jpg")
assert review["score"] < 3
expect(
    "Old Game",
    "game",
    description="A complete gameplay description.",
    media=[{"type": "image", "url": "https://example.invalid/shot.jpg"}],
)

print("catalog classifier OK")
