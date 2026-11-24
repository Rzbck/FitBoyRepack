import unittest
from build_site_data import year_from_date

class ReleaseYearTests(unittest.TestCase):
    def test_years(self):
        for value, expected in [("1989-01-01",1989),("1999",1999),("2000-01-01",2000),("2026-03-04",2026),(None,None),("",None),("unknown",None),("20260",None)]:
            self.assertEqual(year_from_date(value),expected)
if __name__ == "__main__":
    unittest.main()
