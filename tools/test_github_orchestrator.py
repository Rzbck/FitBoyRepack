import unittest
from datetime import datetime, timedelta, timezone
from github_orchestrator import choose, INTERVALS, summarize

NOW = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)

def run(age, conclusion="success", status="completed"):
    t = (NOW - timedelta(minutes=age)).isoformat()
    return dict(created_at=t, updated_at=t, run_started_at=t, conclusion=conclusion, status=status)

def fresh():
    return {name: [run(1)] for name in INTERVALS}

class OrchestratorTests(unittest.TestCase):
    def test_idle(self):
        self.assertIsNone(choose(fresh(), NOW)[0])
    def test_active(self):
        r = fresh(); r["steam-ratings.yml"] = [run(5, None, "in_progress")]
        r["enrich-media.yml"] = [run(100)]
        self.assertIsNone(choose(r, NOW)[0])
    def test_most_overdue(self):
        r = fresh(); r["steam-ratings.yml"] = [run(120)]
        r["enrich-media.yml"] = [run(25)]
        self.assertEqual(choose(r, NOW)[0], "steam-ratings.yml")
    def test_retry_cooldown(self):
        r = fresh(); r["steam-ratings.yml"] = [run(3,"failure"),run(120)]
        r["enrich-media.yml"] = [run(25)]
        self.assertEqual(choose(r,NOW)[0], "enrich-media.yml")
        r["steam-ratings.yml"][0] = run(20,"failure")
        self.assertEqual(choose(r,NOW)[0], "steam-ratings.yml")
    def test_no_history(self):
        r = fresh(); r["backfill-catalog.yml"] = []
        self.assertEqual(choose(r,NOW)[0], "backfill-catalog.yml")
    def test_incomplete_history(self):
        with self.assertRaises(ValueError): choose({},NOW)
    def test_monitor_distinguishes_failed_and_stale(self):
        r = fresh(); r["steam-ratings.yml"] = [run(2,"failure"), run(180)]
        status = summarize(r,NOW)["steam-ratings.yml"]
        self.assertEqual(status["last_success_age_minutes"],180)
        self.assertEqual(status["last_conclusion"],"failure")
        self.assertTrue(status["overdue"])
    def test_pending(self):
        r = fresh(); r["enrich-media.yml"] = [run(1,None,"queued")]
        r["steam-ratings.yml"] = [run(120)]
        self.assertIsNone(choose(r,NOW)[0])

if __name__ == "__main__":
    unittest.main()
