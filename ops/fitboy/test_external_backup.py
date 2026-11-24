import hashlib,json,sqlite3,tarfile,tempfile,unittest
from pathlib import Path
from pull_external_backup import verify

class BackupTests(unittest.TestCase):
    def test_valid_and_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);stamp="20261124T120000Z";folder=root/stamp;folder.mkdir()
            manifest={"created_at":stamp,"databases":{}}
            for name in ["catalog_enrichment.sqlite3","translations.sqlite3"]:
                path=folder/name
                c=sqlite3.connect(path);c.execute("create table t(x)");c.commit();c.close()
                manifest["databases"][name]={"size":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
            (folder/"manifest.json").write_text(json.dumps(manifest))
            archive=root/"backup.tar"
            with tarfile.open(archive,"w") as t:t.add(folder,arcname=stamp)
            self.assertTrue(verify(archive,stamp))
            (folder/"translations.sqlite3").write_bytes(b"bad")
            with tarfile.open(archive,"w") as t:t.add(folder,arcname=stamp)
            with self.assertRaises(ValueError):verify(archive,stamp)
if __name__=="__main__":unittest.main()
