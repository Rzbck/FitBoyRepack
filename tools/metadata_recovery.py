"""Bounded autonomous refresh of unresolved metadata only."""
from datetime import datetime, timedelta, timezone
from fast_metadata_bootstrap import cache_key

RECOVERY_VERSION = 1
RETRY_DAYS = 30
BATCH_LIMIT = 25

def schedule_reviews(conn, *, now=None, limit=BATCH_LIMIT):
    now = now or datetime.now(timezone.utc)
    if not 0 <= limit <= BATCH_LIMIT:
        raise ValueError("invalid recovery limit")
    conn.execute("""CREATE TABLE IF NOT EXISTS metadata_recovery_state (
        game_id TEXT NOT NULL, fingerprint TEXT NOT NULL, version INTEGER NOT NULL,
        attempted_at TEXT NOT NULL, PRIMARY KEY(game_id,fingerprint,version)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS metadata_recovery_llm_history (
        game_id TEXT NOT NULL, fingerprint TEXT NOT NULL, worker_version INTEGER NOT NULL,
        status TEXT NOT NULL, attempts INTEGER NOT NULL, candidate_id TEXT,
        confidence REAL, reason TEXT, last_error TEXT, attempted_at TEXT NOT NULL,
        archived_at TEXT NOT NULL
    )""")
    if conn.execute("SELECT 1 FROM jobs WHERE active=1 AND status IN ('pending','processing') LIMIT 1").fetchone():
        conn.commit()
        return 0
    stamp = now.isoformat()
    cutoff = (now-timedelta(days=RETRY_DAYS)).isoformat()
    rows = conn.execute("""
        SELECT j.game_id,j.title,j.fingerprint FROM jobs j
        LEFT JOIN metadata_recovery_state r ON r.game_id=j.game_id
          AND r.fingerprint=j.fingerprint AND r.version=?
        WHERE j.active=1 AND j.status='review'
          AND NOT EXISTS (SELECT 1 FROM results v WHERE v.game_id=j.game_id)
          AND (r.attempted_at IS NULL OR r.attempted_at<=?)
        ORDER BY CASE WHEN r.attempted_at IS NULL THEN 0 ELSE 1 END,
                 r.attempted_at,j.game_id LIMIT ?
    """,(RECOVERY_VERSION,cutoff,limit)).fetchall()
    has_llm = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='llm_review_state'").fetchone()
    for row in rows:
        game_id, title, fingerprint = row
        conn.execute("DELETE FROM metadata_cache WHERE search_title=?", (cache_key(title),))
        if has_llm:
            conn.execute("""INSERT INTO metadata_recovery_llm_history
                SELECT game_id,fingerprint,worker_version,status,attempts,candidate_id,
                       confidence,reason,last_error,attempted_at,?
                FROM llm_review_state WHERE game_id=? AND fingerprint=? AND status!='resolved'
            """,(stamp,game_id,fingerprint))
            conn.execute("DELETE FROM llm_review_state WHERE game_id=? AND fingerprint=? AND status!='resolved'",
                         (game_id,fingerprint))
        conn.execute("""INSERT INTO metadata_recovery_state VALUES(?,?,?,?)
            ON CONFLICT(game_id,fingerprint,version) DO UPDATE SET attempted_at=excluded.attempted_at
        """,(game_id,fingerprint,RECOVERY_VERSION,stamp))
        conn.execute("""UPDATE jobs SET status='pending',queued_at=?,updated_at=?,
            started_at=NULL,finished_at=NULL,last_error=NULL WHERE game_id=? AND status='review'
        """,(stamp,stamp,game_id))
    conn.commit()
    return len(rows)
