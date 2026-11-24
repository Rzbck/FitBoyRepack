import unittest
from datetime import datetime, timezone
from dispatch_guard import decision, api

NOW=1800000000
def run(age,status="completed"):
    return {"status":status,"created_at":datetime.fromtimestamp(NOW-age,timezone.utc).isoformat()}

class GuardTests(unittest.TestCase):
    def test_due(self):
        self.assertEqual(decision([run(600)],NOW,{}),"dispatch")
    def test_recent(self):
        self.assertEqual(decision([run(120)],NOW,{}),"recent")
    def test_active(self):
        self.assertEqual(decision([run(800,"queued")],NOW,{}),"active")
    def test_cooldown(self):
        self.assertEqual(decision([],NOW,{"next_attempt":NOW+1}),"cooldown")
    def test_bad_history(self):
        with self.assertRaises(ValueError):decision({},NOW,{})
        with self.assertRaises(KeyError):decision([{}],NOW,{})
    def test_endpoint_fixed(self):
        with self.assertRaises(ValueError):api("https://example.invalid","unused")
if __name__=="__main__":unittest.main()
