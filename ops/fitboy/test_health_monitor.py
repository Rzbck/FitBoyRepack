import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from health_monitor import service_health, workflow_health, queue_counts, write_report, notify

NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)
def run(age,conclusion="success",status="completed"):
    t=(NOW-timedelta(minutes=age)).isoformat()
    return {"created_at":t,"run_started_at":t,"status":status,"conclusion":conclusion,"event":"schedule"}

class MonitorTests(unittest.TestCase):
    def test_service(self):
        timer={"ActiveState":"active","UnitFileState":"enabled"}
        service={"ActiveState":"inactive","Result":"success","ExecMainExitTimestampMonotonic":"60000000"}
        self.assertEqual(service_health(timer,service,15,120000000)["issues"],[])
        self.assertIn("last_exit_stale",service_health(timer,service,15,1200000000)["issues"])
        self.assertIn("timer_inactive",service_health({},service,15,120000000)["issues"])
        self.assertIn("service_failed",service_health(timer,{**service,"Result":"exit-code"},15,120000000)["issues"])
    def test_workflow(self):
        status=workflow_health([run(1,"failure"),run(180)],NOW,120)
        self.assertEqual(status["issues"],["success_stale","latest_failed"])
        self.assertEqual(workflow_health([run(900)],NOW,None)["issues"],[])
        self.assertIn("success_stale",workflow_health([],NOW,30)["issues"])
    def test_persistent_alert_and_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"health").mkdir()
            report={"generated_at":NOW.isoformat(),"issues":["github/ci.yml/latest_failed"]}
            sent=[]
            def sender(title,items,priority):
                sent.append((title,items,priority));return True
            notify(root,report,"unused",sender)
            self.assertEqual(len(sent),0)
            notify(root,report,"unused",sender)
            self.assertEqual(len(sent),1)
            notify(root,report,"unused",sender)
            self.assertEqual(len(sent),1)
            notify(root,{**report,"issues":[]},"unused",sender)
            self.assertEqual(len(sent),2)
            self.assertEqual(sent[-1][2],3)
    def test_db_readonly_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); db=root/"test.db"
            c=sqlite3.connect(db)
            c.execute("CREATE TABLE jobs(status TEXT,active INTEGER)")
            c.executemany("INSERT INTO jobs VALUES(?,?)",[("done",1),("review",1),("done",0)])
            c.commit();c.close()
            before=db.read_bytes()
            self.assertEqual(queue_counts(db,"jobs"),{"done":1,"review":1})
            self.assertEqual(db.read_bytes(),before)
            report={"status":"ok","issues":[]}
            write_report(root,report);write_report(root,report)
            self.assertEqual(json.loads((root/"health/latest.json").read_text()),report)
            self.assertEqual(len((root/"health/history.jsonl").read_text().splitlines()),2)

if __name__=="__main__":unittest.main()
