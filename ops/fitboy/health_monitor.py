#!/usr/bin/env python3
"""Read-only health collection for FitBoyRepack; no worker dispatch or credentials."""
from __future__ import annotations
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
from urllib.request import Request, urlopen

SERVICES = {
    "metadata-autodrain": 45, "review-llm": 90, "metadata-publish": 150,
    "translation-autodrain": 45, "translation-publish": 420,
    "fitboy-backup": 1800,
}
WORKFLOWS = {
    "catalog-orchestrator.yml": 30, "feed-watch.yml": 40,
    "steam-ratings.yml": 120, "update-catalog.yml": 120,
    "enrich-media.yml": 45, "backfill-catalog.yml": 2880,
    "pages.yml": None,
}
REPO = "Rzbck/FitBoyRepack"

def props(unit):
    out = subprocess.check_output(["systemctl","show",unit,
        "-p","ActiveState","-p","UnitFileState","-p","Result",
        "-p","ExecMainStartTimestampMonotonic","-p","ExecMainExitTimestampMonotonic"],
        text=True,timeout=5)
    return dict(line.split("=",1) for line in out.splitlines() if "=" in line)

def age_minutes(value, mono):
    try:
        stamp=int(value)
        return round(max(0,mono-stamp)/60_000_000,1) if stamp>0 else None
    except (TypeError,ValueError):
        return None

def service_health(timer, service, limit, mono):
    active=service.get("ActiveState")
    running=active in {"active","activating","reloading"}
    age=age_minutes(service.get("ExecMainExitTimestampMonotonic"),mono)
    started=age_minutes(service.get("ExecMainStartTimestampMonotonic"),mono)
    issues=[]
    if timer.get("ActiveState")!="active": issues.append("timer_inactive")
    if timer.get("UnitFileState") not in {"enabled","enabled-runtime"}: issues.append("timer_not_enabled")
    if service.get("Result") not in {"success",None,""} or active=="failed": issues.append("service_failed")
    if running and started is not None and started>limit: issues.append("running_too_long")
    if not running and age is not None and age>limit: issues.append("last_exit_stale")
    if not running and age is None: issues.append("no_exit_this_boot")
    return {"state":active,"result":service.get("Result"),"timer":timer.get("ActiveState"),
            "last_exit_age_minutes":age,"running_age_minutes":started if running else None,"issues":issues}

def queue_counts(path, table):
    if table not in {"jobs","translation_jobs"}: raise ValueError("unexpected table")
    with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=3)) as conn:
        conn.execute("PRAGMA query_only=ON")
        return dict(conn.execute(f"SELECT status,COUNT(*) FROM {table} WHERE active=1 GROUP BY status"))

def backup_age(root, now):
    manifests=[p for p in (root/"backups").glob("*/manifest.json") if p.is_file()]
    if not manifests:return None
    return round((now.timestamp()-max(p.stat().st_mtime for p in manifests))/60,1)

def workflow_health(runs, now, limit):
    successes=[r for r in runs if r.get("status")=="completed" and r.get("conclusion")=="success"]
    last=max((datetime.fromisoformat((r.get("run_started_at") or r["created_at"]).replace("Z","+00:00")) for r in successes),default=None)
    age=round((now-last).total_seconds()/60,1) if last else None
    latest=max(runs,key=lambda r:r["created_at"],default={})
    issues=[]
    if age is None or (limit is not None and age>limit):issues.append("success_stale")
    if latest.get("status")=="completed" and latest.get("conclusion") not in {"success","skipped","cancelled"}:issues.append("latest_failed")
    return {"last_success_age_minutes":age,"latest_status":latest.get("status"),
            "latest_conclusion":latest.get("conclusion"),"latest_event":latest.get("event"),
            "issues":issues}

def github_runs(workflow):
    url=f"https://api.github.com/repos/{REPO}/actions/workflows/{workflow}/runs?branch=main&per_page=15"
    req=Request(url,headers={"User-Agent":"FitBoyRepack-health/1","Accept":"application/vnd.github+json"})
    with urlopen(req,timeout=6) as response:
        payload=json.load(response)
    return payload["workflow_runs"]

def collect(root, *, github=True, now=None):
    now=now or datetime.now(timezone.utc)
    mono=time.clock_gettime(time.CLOCK_MONOTONIC)*1_000_000
    result={"generated_at":now.isoformat(),"services":{},"queues":{},"github":{},"issues":[]}
    def record(section,name,fn):
        try: value=fn()
        except Exception as exc:
            value={"issues":["check_unavailable"],"error_type":type(exc).__name__}
        result[section][name]=value
        result["issues"].extend(f"{section}/{name}/{issue}" for issue in value.get("issues",[]))
    for name,limit in SERVICES.items():
        record("services",name,lambda:service_health(props(name+".timer"),props(name+".service"),limit,mono))
    record("services","llama-server",lambda:{"state":props("llama-server.service").get("ActiveState"),"issues":[] if props("llama-server.service").get("ActiveState")=="active" else ["llm_inactive"]})
    for name,path,table in [
        ("metadata",root/"ai/catalog_enrichment.sqlite3","jobs"),
        ("translation",root/"translation/translations.sqlite3","translation_jobs"),
    ]:
        def queue():
            counts=queue_counts(path,table)
            issues=["failed_jobs"] if counts.get("failed",0) or counts.get("error",0) else []
            return {"counts":counts,"issues":issues}
        record("queues",name,queue)
    disk=shutil.disk_usage(root)
    result["disk"]={"used_percent":round(disk.used/disk.total*100,1),"free_bytes":disk.free}
    if result["disk"]["used_percent"]>=85:result["issues"].append("disk/high_usage")
    result["backup_age_minutes"]=backup_age(root,now)
    if result["backup_age_minutes"] is None or result["backup_age_minutes"]>1800:result["issues"].append("backup/stale")
    # A valid recent backup is stronger evidence than no exit since reboot.
    if result["backup_age_minutes"] is not None and result["backup_age_minutes"]<=1800:
        result["issues"]=[i for i in result["issues"] if i!="services/fitboy-backup/no_exit_this_boot"]
        result["services"]["fitboy-backup"]["issues"]=[i for i in result["services"]["fitboy-backup"].get("issues",[]) if i!="no_exit_this_boot"]
    if github:
        for name,limit in WORKFLOWS.items():
            record("github",name,lambda:workflow_health(github_runs(name),now,limit))
    result["status"]="warning" if result["issues"] else "ok"
    return result

def write_report(root, report):
    target=root/"health"
    target.mkdir(mode=0o700,exist_ok=True)
    tmp=target/"latest.tmp"
    tmp.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,target/"latest.json")
    # Bounded 7 days of 15 minute observations, no secrets or source text.
    history=target/"history.jsonl"
    rows=history.read_text(encoding="utf-8").splitlines()[-671:] if history.exists() else []
    rows.append(json.dumps(report,separators=(",",":")))
    tmp=target/"history.tmp"
    tmp.write_text("\n".join(rows)+"\n",encoding="utf-8")
    os.replace(tmp,history)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path("/var/lib/fitboy"))
    parser.add_argument("--offline",action="store_true")
    args=parser.parse_args()
    report=collect(args.root,github=not args.offline)
    write_report(args.root,report)
    print(json.dumps({"status":report["status"],"issues":report["issues"]},sort_keys=True),flush=True)

if __name__=="__main__":main()
