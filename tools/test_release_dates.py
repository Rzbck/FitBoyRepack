import unittest
from release_dates import normalize_date,steam_date,release_choice

class ReleaseDates(unittest.TestCase):
    def test_precision(self):
        for raw,expected in [("1995-00-00","1995"),("2019-02-00","2019-02"),("2016-05-09","2016-05-09"),("2023-02-29",None),("2019-13-01",None),("2019-00-05",None),(None,None)]:
            self.assertEqual(normalize_date(raw),expected)
    def test_steam(self):
        self.assertEqual(steam_date({"coming_soon":False,"date":"May 9, 2016"}),"2016-05-09")
        self.assertEqual(steam_date({"coming_soon":False,"date":"9 May, 2016"}),"2016-05-09")
        for date in ["Coming soon","2026","Feb 30, 2020","Jan 1, 2099"]:
            self.assertIsNone(steam_date({"coming_soon":False,"date":date}))
        self.assertIsNone(steam_date({"coming_soon":True,"date":"May 9, 2016"}))
    def test_choice(self):
        row={"status":"rated","steam_appid":281990,"steam_release_appid":281990,"store_verified_at":"verified","steam_release_date":"2016-05-09"}
        for wiki,expected,source,conflict in [(None,"2016-05-09","steam",False),("1995-00-00","2016-05-09","steam",True),("2016-05-00","2016-05-09","steam",False),("2015-01-02","2015-01-02","wikidata",True),("2016-05-09","2016-05-09","wikidata",False)]:
            v=release_choice({"release_date":wiki},row)
            self.assertEqual((v["game_release_date"],v["game_release_source"],v["game_release_conflict"]),(expected,source,conflict))
        for change in [{"status":"mismatch"},{"steam_release_appid":999},{"store_verified_at":None}]:
            self.assertIsNone(release_choice(None,{**row,**change})["game_release_date"])
        self.assertEqual(release_choice({"release_date":"1995-00-00"},None)["game_release_precision"],"year")

if __name__=="__main__":unittest.main()
