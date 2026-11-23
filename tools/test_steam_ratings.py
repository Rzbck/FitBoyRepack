#!/usr/bin/env python3
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import update_steam_ratings as bot
import steam_schedule_guard as cadence
from datetime import datetime, timedelta, timezone


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
                 patch.object(bot, "collect_steam_reviews", side_effect=fetch_reviews), \
                 patch.object(bot, "store_details", side_effect=lambda appid: {
                     "name": {111: "First", 222: "Second"}[appid], "type": "game"}):
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
                 patch.object(bot, "collect_steam_reviews", side_effect=bot.Cooldown("HTTP 429")), \
                 patch.object(bot, "store_details", return_value={"name": "Another", "type": "game"}):
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
                 patch.object(bot, "collect_steam_reviews", side_effect=fake_review), \
                 patch.object(bot, "store_details", side_effect=lambda appid: {
                     "name": {111: "Bad app", 222: "Good app"}[appid], "type": "game"}):
                summary = bot.update(Namespace(resolve_limit=10, reviews_limit=10,
                                               fallback_limit=0, pause=0, dry_run=False))
            records = json.loads(output.read_text(encoding="utf-8"))["games"]
            self.assertEqual(records["a"]["status"], "unavailable")
            self.assertEqual(records["b"]["status"], "rated")
            self.assertEqual(summary["rated"], 1)


    def test_strict_store_title_identity(self):
        cyberpunk = {
            "title": "Cyberpunk 2077: Ultimate Edition - v2.5 + DLCs",
        }
        self.assertIn("cyberpunk 2077", bot.game_title_variants(
            cyberpunk, {"canonical_title": "Cyberpunk 2077: Ultimate Edition"}))
        self.assertTrue(bot.store_verified(
            cyberpunk, {}, {"name": "Cyberpunk 2077", "type": "game"}))
        self.assertFalse(bot.store_verified(
            cyberpunk, {}, {"name": "Cyberpunk 2077: Phantom Liberty", "type": "dlc"}))
        self.assertFalse(bot.store_verified(
            cyberpunk, {}, {"name": "Cyberpunk 2078", "type": "game"}))

        wrong_qid = {"title": "Call of Duty: Modern Warfare II, v9.7 (Campaign)"}
        wrong_meta = {"canonical_title": "Call of Duty: Modern Warfare III"}
        self.assertNotIn("call of duty modern warfare iii",
                         bot.game_title_variants(wrong_qid, wrong_meta))
        self.assertFalse(bot.store_verified(wrong_qid, wrong_meta, {
            "name": "Call of Duty®: Modern Warfare® III", "type": "game"}))
        self.assertTrue(bot.store_verified(wrong_qid, wrong_meta, {
            "name": "Call of Duty®: Modern Warfare® II", "type": "game"}))
        self.assertTrue(bot.store_verified(
            {"title": "Disney Dreamlight Valley: Ultimate Edition - v1.26.1"},
            {}, {"name": "Disney Dreamlight Valley", "type": "game"}))
        self.assertTrue(bot.store_verified(
            {"title": "Dragonkin: The Banished - Blood Scales Edition, v1.2.64"},
            {"canonical_title": "Dragonkin: The Banished"},
            {"name": "Dragonkin: The Banished", "type": "game"}))
        self.assertTrue(bot.store_verified(
            {"title": "Talisman: Digital 5th Edition - Complete, Build 86150"},
            {"canonical_title": "Talisman: Digital 5th Edition"},
            {"name": "Talisman: Digital 5th Edition", "type": "game"}))
        self.assertTrue(bot.store_verified(
            {"title": "Screamer: Digital Deluxe Edition + 3 DLCs"},
            {"canonical_title": "Screamer"},
            {"name": "Screamer", "type": "game"}))
        self.assertTrue(bot.store_verified(
            {"title": "NBA 2K26: Superstar Edition - v5.0 + 22 DLCs"},
            {"canonical_title": "NBA 2K26"},
            {"name": "NBA 2K26", "type": "game"}))

    def test_store_search_requires_unique_exact_name(self):
        sample = {"title": "Cyberpunk 2077: Ultimate Edition - v2.5"}
        with patch.object(bot, "get_json", return_value={"items": [
            {"id": 1091500, "name": "Cyberpunk 2077"},
            {"id": 2138330, "name": "Cyberpunk 2077: Phantom Liberty"},
        ]}):
            self.assertEqual(bot.exact_store_search(sample, {}), 1091500)
        with patch.object(bot, "get_json", return_value={"items": [
            {"id": 1091500, "name": "Cyberpunk 2077"},
            {"id": 2000000, "name": "Cyberpunk 2077"},
        ]}):
            self.assertIsNone(bot.exact_store_search(sample, {}))

    def test_wikidata_retry_after_maxlag(self):
        with patch.object(bot, "get_json", side_effect=[
            bot.Cooldown("maxlag"), bot.Cooldown("HTTP 429"), {"entities": {}}
        ]) as request, patch.object(bot.time, "sleep") as sleeper:
            result = bot.wikidata_with_retry(bot.WIKIDATA, {"action": "wbgetentities"})
            self.assertEqual(result, {"entities": {}})
            self.assertEqual(request.call_count, 3)
            self.assertEqual(sleeper.call_count, 2)

    def test_wrong_sequel_never_receives_ratings(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            source, meta, cache = [folder / name for name in
                                   ("games.json", "meta.json", "cache.json")]
            source.write_text(json.dumps({"games": [{
                "id": "cod-ii", "title": "Call of Duty: Modern Warfare II, v9.7",
                "post_date": "2026-11-01T00:00:00Z"}]}), encoding="utf-8")
            meta.write_text(json.dumps({"metadata_version": 1, "games": {
                "cod-ii": {"canonical_title": "Call of Duty: Modern Warfare III",
                           "evidence_urls": ["https://www.wikidata.org/wiki/Q123"]}}}), encoding="utf-8")
            with patch.object(bot, "CATALOG", source), patch.object(bot, "METADATA", meta), \
                 patch.object(bot, "OUTPUT", cache), patch.object(bot, "wikidata_entities",
                     return_value={"Q123": entity(2519060)}), \
                 patch.object(bot, "store_details",
                     return_value={"type": "game", "name": "Call of Duty: Modern Warfare III"}), \
                 patch.object(bot, "collect_steam_reviews") as reviews:
                result = bot.update(Namespace(
                    resolve_limit=10, reviews_limit=10, fallback_limit=0,
                    store_fallback_limit=0, pause=0, dry_run=False))
            row = json.loads(cache.read_text(encoding="utf-8"))["games"]["cod-ii"]
            self.assertEqual(row["status"], "mismatch")
            self.assertEqual(row["invalid_steam_appid"], 2519060)
            self.assertNotIn("positive_percent", row)
            self.assertEqual(result["rated"], 0)
            reviews.assert_not_called()

    def test_exact_store_fallback_recovers_missing_wikidata_identifier(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            source, meta, cache = [folder / name for name in
                                   ("games.json", "meta.json", "cache.json")]
            source.write_text(json.dumps({"games": [{
                "id": "cyberpunk", "title": "Cyberpunk 2077: Ultimate Edition - v2.5",
                "post_date": "2026-11-01T00:00:00Z"}]}), encoding="utf-8")
            meta.write_text(json.dumps({"metadata_version": 1, "games": {
                "cyberpunk": {"canonical_title": "Cyberpunk 2077: Ultimate Edition",
                              "evidence_urls": ["https://www.wikidata.org/wiki/Q456"]}}}), encoding="utf-8")
            review = {"status": "rated", "positive": 90, "negative": 10,
                      "total_reviews": 100, "positive_percent": 90,
                      "review_checked_at": bot.iso(bot.utc_now())}
            with patch.object(bot, "CATALOG", source), patch.object(bot, "METADATA", meta), \
                 patch.object(bot, "OUTPUT", cache), \
                 patch.object(bot, "wikidata_entities", return_value={}), \
                 patch.object(bot, "exact_store_search", return_value=1091500), \
                 patch.object(bot, "store_details",
                     return_value={"type": "game", "name": "Cyberpunk 2077"}), \
                 patch.object(bot, "collect_steam_reviews", return_value=review):
                result = bot.update(Namespace(
                    resolve_limit=10, reviews_limit=10, fallback_limit=0,
                    store_fallback_limit=1, pause=0, dry_run=False))
            row = json.loads(cache.read_text(encoding="utf-8"))["games"]["cyberpunk"]
            self.assertEqual(row["status"], "rated")
            self.assertEqual(row["steam_appid"], 1091500)
            self.assertEqual(row["resolution"], "steam_store_exact")
            self.assertEqual(result["rated"], 1)



    def test_redundant_cron_gate_only_skips_recent_schedules(self):
        with tempfile.TemporaryDirectory() as root:
            cache = Path(root) / "steam-ratings.json"
            now = datetime(2026, 11, 23, 10, 30, tzinfo=timezone.utc)
            cache.write_text(json.dumps({
                "generated_at": (now - timedelta(minutes=20)).isoformat()
            }), encoding="utf-8")
            self.assertFalse(cadence.should_run("schedule", cache, now))
            self.assertTrue(cadence.should_run("workflow_dispatch", cache, now))
            cache.write_text(json.dumps({
                "generated_at": (now - timedelta(minutes=42)).isoformat()
            }), encoding="utf-8")
            self.assertTrue(cadence.should_run("schedule", cache, now))
            cache.write_text("{invalid", encoding="utf-8")
            self.assertTrue(cadence.should_run("schedule", cache, now))

    def test_non_game_app_never_gets_score(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            source, meta, cache = [folder / name for name in
                                   ("games.json", "meta.json", "cache.json")]
            source.write_text(json.dumps({"games": [{
                "id": "expansion", "title": "Example Expansion",
                "post_date": "2026-11-01T00:00:00Z"}]}), encoding="utf-8")
            meta.write_text(json.dumps({"metadata_version": 1, "games": {
                "expansion": {"evidence_urls": ["https://www.wikidata.org/wiki/Q456"]}}}),
                encoding="utf-8")
            with patch.object(bot, "CATALOG", source), patch.object(bot, "METADATA", meta), \
                 patch.object(bot, "OUTPUT", cache), \
                 patch.object(bot, "wikidata_entities", return_value={"Q456": entity(555)}), \
                 patch.object(bot, "store_details",
                     return_value={"type": "dlc", "name": "Example Expansion"}), \
                 patch.object(bot, "collect_steam_reviews") as reviews:
                result = bot.update(Namespace(
                    resolve_limit=10, reviews_limit=10, fallback_limit=0,
                    store_fallback_limit=0, pause=0, dry_run=False))
            row = json.loads(cache.read_text(encoding="utf-8"))["games"]["expansion"]
            self.assertEqual(row["status"], "mismatch")
            self.assertEqual(result["mismatched"], 1)
            reviews.assert_not_called()


if __name__ == "__main__":
    unittest.main()
