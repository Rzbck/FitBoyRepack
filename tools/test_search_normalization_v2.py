#!/usr/bin/env python3
import batched_metadata_bootstrap_v2 as v2


def main() -> None:
    cases = {
        "Batman: Arkham City – Game of The Year Edition": "Batman: Arkham City",
        "ARK: Survival Evolved – Ultimate Survivor Edition": "ARK: Survival Evolved",
        "Black Mesa: Definitive Edition": "Black Mesa",
        "Barotrauma: Supporter Bundle": "Barotrauma",
        "Automobilista 2: All-Inclusive Bundle": "Automobilista 2",
        "Blair Witch: Deluxe Edition – v08302019/Update 1": "Blair Witch",
        "BlazBlue: Cross Tag Battle – Special Edition, v2.0 + 14 DLCs": "BlazBlue: Cross Tag Battle",
        "Ace Combat 7: Skies Unknown – Deluxe Edition – v1.8.2.8 + All DLCs": "Ace Combat 7: Skies Unknown",
    }
    for raw, expected in cases.items():
        actual = v2.aggressive_search_title(raw)
        assert actual == expected, (raw, actual, expected)

    # A subtitle without package/edition semantics must be preserved.
    assert v2.aggressive_search_title("BLADESTORM: Nightmare") == "BLADESTORM: Nightmare"

    client = object.__new__(v2.NormalizedSearchClient)
    queries: list[str] = []

    def fake_get(params):
        query = str(params["search"])
        queries.append(query)
        if len(queries) == 1:
            return {"search": []}
        return {"search": [{"id": "Q123"}]}

    client._get = fake_get  # type: ignore[method-assign]
    ids = client.search("Black Mesa: Definitive Edition", 3)
    assert ids == ["Q123"]
    assert queries == ["Black Mesa: Definitive Edition", "Black Mesa"]

    queries.clear()

    def primary_hit(params):
        queries.append(str(params["search"]))
        return {"search": [{"id": "Q999"}]}

    client._get = primary_hit  # type: ignore[method-assign]
    ids = client.search("Official Game: Deluxe Edition", 3)
    assert ids == ["Q999"]
    assert queries == ["Official Game: Deluxe Edition"]

    print("search normalization v2 OK")


if __name__ == "__main__":
    main()
