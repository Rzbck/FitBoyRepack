#!/usr/bin/env python3
"""Fixed-target GitHub heartbeat. No repository checkout or shell execution."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

BASE="https://api.github.com/repos/Rzbck/FitBoyRepack/actions/workflows/catalog-orchestrator.yml"
HISTORY=BASE+"/runs?branch=main&per_page=20"
DISPATCH=BASE+"/dispatches"
COOLDOWN=300
ERROR_COOLDOWN=900

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def api(url, token, payload=None):
    if url not in (HISTORY,DISPATCH):raise ValueError("unexpected endpoint")
    request=Request(url,data=None if payload is None else json.dumps(payload).encode(),
                    headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
                             "Content-Type":"application/json","X-GitHub-Api-Version":"2022-11-28",
                             "User-Agent":"FitBoyRepack-VPS-Guard/1"},
                    method="GET" if payload is None else "POST")
    with build_opener(NoRedirect()).open(request,timeout=15) as response:
        if payload is not None:
            if response.status not in (200,204):raise RuntimeError("dispatch not acknowledged")
            return None
        return json.load(response)["workflow_runs"]

def decision(runs, now, state):
    if not isinstance(runs,list):raise ValueError("invalid workflow history")
    if now<float(state.get("next_attempt",0)):return "cooldown"
    for run in runs:
        if run["status"]!="completed":return "active"
        created=datetime.fromisoformat(run["created_at"].replace("Z","+00:00")).timestamp()
        if now-created<COOLDOWN:return "recent"
    return "dispatch"

def save(path, state):
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--dry-run",action="store_true")
    args=parser.parse_args()
    credential=Path(os.environ["CREDENTIALS_DIRECTORY"])/"github-token"
    token=credential.read_text(encoding="utf-8").strip()
    if not token.startswith("github_pat_") or any(c.isspace() for c in token):
        raise SystemExit("Invalid fine-grained credential format")
    path=Path(os.environ["STATE_DIRECTORY"])/"dispatch.json"
    state=json.loads(path.read_text()) if path.exists() else {}
    now=time.time()
    if not args.dry_run and now<float(state.get("next_attempt",0)):
        print("Dispatch guard: cooldown",flush=True)
        # Keep a previous API failure visible to systemd during backoff.
        if state.get("result") in {"pending","error"}:raise SystemExit(1)
        return
    try:
        runs=api(HISTORY,token)
        action=decision(runs,now,state)
        print("Dispatch guard: "+action,flush=True)
        if args.dry_run or action!="dispatch":return
        # Persist before POST: an ambiguous network timeout must not cause a burst.
        save(path,{"next_attempt":now+ERROR_COOLDOWN,"last_attempt":now,"result":"pending"})
        api(DISPATCH,token,{"ref":"main","inputs":{"dry_run":"false"}})
        save(path,{"next_attempt":now+COOLDOWN,"last_attempt":now,"result":"accepted"})
        print("Dispatch guard: accepted",flush=True)
    except (HTTPError,URLError,OSError,ValueError,KeyError,RuntimeError) as exc:
        if not args.dry_run:
            save(path,{"next_attempt":now+ERROR_COOLDOWN,"last_attempt":now,"result":"error"})
        # Never emit HTTP response bodies, request headers or credentials.
        print("Dispatch guard: failed",type(exc).__name__,getattr(exc,"code",""),flush=True)
        raise SystemExit(1)

if __name__=="__main__":main()
