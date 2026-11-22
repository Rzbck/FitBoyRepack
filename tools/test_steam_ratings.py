#!/usr/bin/env python3
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import update_steam_ratings as bot


def entity(appid):
    return {"claims": {"P1733": [{"rank": "normal", "mainsnak": {"datavalue": {"value": str(appid)}}}]}}


class SteamRatingBotTests(unittest.TestCase):
    def test_wikidata_claims(self):
        self.assertEqual(bot.steam_id_from_entity(entity(12345)), 12345)
        self.assertIsNone(bot.steam_id_from_entity({"claims": {}}))
        self.assertIsNone(bot.steam_id_from_entity({"claims": {"P1733": [
            {"mainsnak": {"datavalue": {"value": "111"}}},
            {"mainsnak": {"datavalue": {"value": "222"}}},
        ]}}))

    def test_normalization_and_qids(self):
        self.assertEqual(bot.normalize("Pokémon: RÉTRO"), "pokemon retro")
        self.assertEqual(bot.qid_from_metadata({"evidence_urls": ["https://www.wikidata.org/wiki/Q123"]}), "Q123")
        self.assertIsNone(bot.qid_from_metadata({"evidence_urls": ["https://example.com/wiki/Q123"]}))
        self.assertEqual(bot.clean_title("Sample Game - v1.2 + 3 DLCs"), "Sample Game")

    def test_incremental_cache_and_new_games(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            games = [{"id": "a", "title": "First", "post_date": "2026-11-21T00:00:00Z"}]
            metadata = {"metadata_version": 1, "games": {
                "a": {"evidence_urls": ["https://www.wikidata.org/wiki/Q111"]},
                "b": {"evidence_urls": ["https://www.wikidata.org/wiki/Q222"]},
            }}
            source = directory / "games.json"
            meta = directory / "meta.json"
            output = directory / "ratings.json"
            def write():
                source.write_text(json.dumps({"games": games}), encoding="utf-8")
                meta.write_text(json.dumps(metadata), encoding="utf-8")
            write()
            args = Namespace(resolve_limit=10, reviews_limit=10, fallback_limit=0, pause=0, dry_run=False)
            calls = []
            def fetch_reviews(appid, pause):
                calls.append(appid)
                return {"status": "rated", "positive": 90, "negative": 10,
                        "total_reviews": 100, "positive_percent": 90,
                        "review_checked_at": bot.iso(bot.utc_now())}
            with patch.object(bot, "CATALOG", source), patch.object(bot, "METADATA", meta), \
                 patch.object(bot, "OUTPUT", output), patch.object(bot, "wikidata_entities",
                             side_effect=lambda q: {qid: entity(int(qid[1:])) for qid in q}), \
                 patch.object(bot, "collect_steam_reviews", side_effect=fetch_reviews):
                self.assertEqual(bot.update(args)["rated"], 1)
                initial = output.read_text(encoding="utf-8")
                self.assertEqual(bot.update(args)["steam_calls_this_run"], 0)
                self.assertEqual(output.read_text(encoding="utf-8"), initial)
                games.insert(0, {"id": "b", "title": "Second", "post_date": "2026-11-22T00:00:00Z"})
                write()
                self.assertEqual(bot.update(args)["rated"], 2)
                self.assertEqual(calls, [111, 222])
                self.assertEqual(set(json.loads(output.read_text(encoding="utf-8"))["games"]), {"a", "b"})

    def test_rate_limit_preserves_cache(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            source = directory / "games.json"
            meta = directory / "metadata.json"
            output = directory / "cache.json"
            source.write_text(json.dumps({"games": [{"id": "c", "title": "Another"}]}), encoding="utf-8")
            meta.write_text(json.dumps({"metadata_version": 1, "games": {
                "c": {"evidence_urls": ["https://www.wikidata.org/wiki/Q333"]}
            }}), encoding="utf-8")
            with patch.object(bot, "CATALOG", source), patch.object(bot, "METADATA", meta), \
                 patch.object(bot, "OUTPUT", output), patch.object(bot, "wikidata_entities",
                              return_value={"Q333": entity(333)}), \
                 patch.object(bot, "collect_steam_reviews", side_effect=bot.Cooldown("HTTP 429")):
                result = bot.update(Namespace(resolve_limit=10, reviews_limit=10,
                                               fallback_limit=0, pause=0, dry_run=False))
                self.assertEqual(result["pending"], 1)
                cache = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(cache["games"]["c"]["steam_appid"], 333)
                self.assertNotIn("positive_percent", cache["games"]["c"])

    def test_bounded_sparql_primary(self):
        qid="Q140630760"
        bindings=[{"item":{"value":"http://www.wikidata.org/entity/"+qid},"steam":{"value":"2502780"}}]
        with patch.object(bot,"get_json",return_value={"results":{"bindings":bindings}}) as request:
            data=bot.wikidata_entities([qid])
        self.assertEqual(bot.steam_id_from_entity(data[qid]),2502780)
        self.assertEqual(request.call_count,1)

    def test_action_api_fallback_when_sparql_unavailable(self):
        qid="Q140630760"
        with patch.object(bot,"get_json",side_effect=[{"error":"unexpected"},
                                                     {"entities":{qid:entity(2502780)}}]) as request:
            data=bot.wikidata_entities([qid])
        self.assertEqual(bot.steam_id_from_entity(data[qid]),2502780)
        self.assertEqual(request.call_count,2)

    def test_bad_steam_app_does_not_block_following_game(self):
        from urllib.error import HTTPError
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            source = directory / "games.json"
            metadata = directory / "metadata.json"
            output = directory / "ratings.json"
            source.write_text(json.dumps({"games": [
                {"id": "a", "title": "Bad app", "post_date": "2026-11-22T00:00:00Z"},
                {"id": "b", "title": "Good app", "post_date": "2026-11-21T00:00:00Z"},
            ]}), encoding="utf-8")
            metadata.write_text(json.dumps({"metadata_version": 1, "games": {
                "a": {"evidence_urls": ["https://www.wikidata.org/wiki/Q111"]},
                "b": {"evidence_urls": ["https://www.wikidata.org/wiki/Q222"]},
            }}), encoding="utf-8")
            def fake_review(appid, pause):
                if appid == 111:
                    raise HTTPError("https://api.steampowered.com", 404, "Missing", {}, None)
                return {"status": "rated", "positive": 90, "negative": 10,
                        "total_reviews": 100, "positive_percent": 90,
                        "review_checked_at": bot.iso(bot.utc_now())}
            with patch.object(bot, "CATALOG", source), patch.object(bot, "METADATA", metadata), \
                 patch.object(bot, "OUTPUT", output), patch.object(bot, "wikidata_entities",
                             side_effect=lambda q: {qid: entity(int(qid[1:])) for qid in q}), \
                 patch.object(bot, "collect_steam_reviews", side_effect=fake_review):
                summary = bot.update(Namespace(resolve_limit=10, reviews_limit=10,
                                               fallback_limit=0, pause=0, dry_run=False))
            records = json.loads(output.read_text(encoding="utf-8"))["games"]
            self.assertEqual(records["a"]["status"], "unavailable")
            self.assertEqual(records["b"]["status"], "rated")
            self.assertEqual(summary["rated"], 1)


if __name__ == "__main__":
    unittest.main()
