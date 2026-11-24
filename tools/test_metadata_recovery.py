from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from ai_catalog_bootstrap import connect_db,initialize_queue
from fast_metadata_bootstrap import ensure_cache,store_cache,cached_evidence
from fitboy.metadata.metadata_recovery import schedule_reviews

def main():
    with TemporaryDirectory() as tmp:
        c=connect_db(Path(tmp)/"queue.sqlite")
        games=[{"id":str(i),"title":"Game "+str(i),"source_url":"https://example.invalid/"+str(i)} for i in range(31)]
        initialize_queue(c,games); ensure_cache(c)
        c.execute("UPDATE jobs SET status='review'")
        c.execute("UPDATE jobs SET status='done' WHERE game_id='0'")
        for g in games: store_cache(c,g["title"],[])
        c.execute("""CREATE TABLE llm_review_state (
          game_id TEXT,fingerprint TEXT,worker_version INTEGER,status TEXT,attempts INTEGER,
          candidate_id TEXT,confidence REAL,reason TEXT,last_error TEXT,attempted_at TEXT
        )""")
        c.execute("""INSERT INTO llm_review_state SELECT game_id,fingerprint,1,'ineligible',1,
          NULL,NULL,'no evidence',NULL,'2026-10-01' FROM jobs WHERE game_id='1'""")
        c.commit()
        now=datetime(2026,11,24,tzinfo=timezone.utc)
        assert schedule_reviews(c,now=now)==25
        assert schedule_reviews(c,now=now)==0
        assert c.execute("SELECT count(*) FROM metadata_recovery_llm_history WHERE game_id='1'").fetchone()[0]==1
        assert c.execute("SELECT count(*) FROM llm_review_state WHERE game_id='1'").fetchone()[0]==0
        assert cached_evidence(c,"Game 1") is None
        assert cached_evidence(c,"Game 0")==[]
        assert c.execute("SELECT status FROM jobs WHERE game_id='0'").fetchone()[0]=="done"
        c.execute("UPDATE jobs SET status='review' WHERE status='pending'"); c.commit()
        assert schedule_reviews(c,now=now)==5
        c.execute("UPDATE jobs SET status='review' WHERE status='pending'"); c.commit()
        assert schedule_reviews(c,now=now+timedelta(days=29))==0
        assert schedule_reviews(c,now=now+timedelta(days=30))==25
        assert c.execute("SELECT count(*) FROM metadata_recovery_state").fetchone()[0]==30
        c.close()
    print("metadata recovery bounded retry OK")
if __name__=="__main__": main()
