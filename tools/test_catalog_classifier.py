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
    "A warning to all MegaUpload users!",
    "AMD (and old Intel) CPU owners wanted for testing",
    "About PRAGMATA Release",
    "About compression speed",
    "Agents of Mayhem, Patch to v1.03",
    "All Genres/Tags Are Now Links",
    "All game uploads restored!",
    "Anno.1800.Crackfix-EMPRESS",
    "Another DDoS",
    "Assassin’s Creed: Origins Repack Vote",
    "Black Ops 3 Repack Status",
    "Browser Mining FAQ Added",
    "Browser Mining as a Way of Donating",
    "CPY cracked RotTR, I guess more cracks incoming",
    "CPY is on fire!",
    "CS.RIN.RU Needs Your Help",
    "CoD: WWII – rip or repack?",
    "CoDs repacks status",
    "DMC5-related Decompression Test",
    "DNS Problems",
    "DOOM Rip, anyone need it?",
    "DOOM: IDDQD Repack details",
    "Day of Requests Results",
    "Day of Requests: Stage 1",
    "Decompression Test #2 – STRESS IT!",
    "Delays in repacking",
    "Denuvo versus Voksi",
    "Amelie Report October 2021",
):
    expect(title, "non_game")

# Aggregate posts may contain perfectly valid metadata copied from games they
# mention. They must still be excluded, which is the regression seen in prod.
for title in (
    "Upcoming Repacks",
    "Updates Digest for September 28, 2026",
):
    expect(
        title,
        "non_game",
        genres=["Management", "Strategy", "Item crafting"],
        size="10.3 GB",
        image="https://example.invalid/embedded-game-cover.jpg",
        description="Rich editorial content mentioning several games.",
        media=[{"type": "image", "url": "https://example.invalid/embedded-shot.jpg"}],
    )

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

for title in (
    "Age of Wonders 3: Eternal Lords",
    "Ashes of the Singularity",
    "BLADESTORM: Nightmare",
    "Batman: Arkham Knight",
    "Battle Fantasia -Revised Edition-",
    "Cosmonautica: A Space Trading Adventure",
    "Crusader Kings 2: Horse Lords v2.4.1 + 57 DLCs",
    "Danganronpa: Trigger Happy Havoc – Limited Edition",
    "Darksiders 2: Deathinitive Edition + Update 2",
    "DiRT 3: Complete Edition",
):
    # Old listing records may only have a cover. They stay in review rather
    # than being deleted because their titles themselves look like game names.
    expect(title, "review", image="https://example.invalid/cover.jpg")

# Strong metadata still wins for generic editorial-looking phrases that are not
# known aggregate pages.
expect(
    "Example Game Repack Status",
    "game",
    genres=["Action"],
    size="12 GB",
    description="A complete gameplay description.",
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
