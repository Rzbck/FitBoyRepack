"""Pull verified immutable snapshots to a separate Windows host via existing SSH."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import tarfile
import tempfile
import os

STAMP=re.compile(r"\d{8}T\d{6}Z")
FILES={"catalog_enrichment.sqlite3","translations.sqlite3","manifest.json"}

def verify(archive, stamp):
    with tarfile.open(archive,"r:*") as tar, tempfile.TemporaryDirectory() as temp:
        members={m.name.removeprefix("./"):m for m in tar.getmembers() if m.isfile()}
        expected={stamp+"/"+f for f in FILES}
        if set(members)!=expected or any(not m.isfile() and not m.isdir() for m in tar.getmembers()):
            raise ValueError("unexpected archive entries")
        manifest=json.load(tar.extractfile(members[stamp+"/manifest.json"]))
        if manifest["created_at"]!=stamp or set(manifest["databases"])!=FILES-{"manifest.json"}:
            raise ValueError("invalid manifest")
        for name,meta in manifest["databases"].items():
            target=Path(temp)/name
            with tar.extractfile(members[stamp+"/"+name]) as src,target.open("wb") as dst:
                while chunk:=src.read(1024*1024):dst.write(chunk)
            with target.open("rb") as f:
                if hashlib.file_digest(f,"sha256").hexdigest()!=meta["sha256"]:raise ValueError("checksum mismatch")
            if target.stat().st_size!=meta["size"]:raise ValueError("size mismatch")
            with closing(sqlite3.connect(target.as_uri()+"?mode=ro",uri=True)) as conn:
                if conn.execute("PRAGMA quick_check").fetchall()!=[("ok",)]:raise ValueError("SQLite integrity failure")
    return True

def pull(destination,ssh="ssh",host="rmm-vps"):
    destination.mkdir(parents=True,exist_ok=True)
    cmd=[ssh,"-o","BatchMode=yes","-o","ConnectTimeout=15",host]
    names=subprocess.check_output(cmd+["sudo -n -u fitboy ls -1 /var/lib/fitboy/backups"],text=True,timeout=30).splitlines()
    stamps=sorted(n.strip() for n in names if STAMP.fullmatch(n.strip()))
    if not stamps:raise RuntimeError("no completed backup")
    stamp=stamps[-1]
    target=destination/(stamp+".tar")
    if target.exists():
        verify(target,stamp)
    else:
        fd,tmp=tempfile.mkstemp(prefix=".fitboy-",suffix=".partial",dir=destination)
        try:
            with os.fdopen(fd,"wb") as handle:
                subprocess.run(cmd+[f"sudo -n -u fitboy tar -C /var/lib/fitboy/backups -cf - {stamp}"],stdout=handle,check=True,timeout=180)
                handle.flush();os.fsync(handle.fileno())
            verify(tmp,stamp)
            os.replace(tmp,target)
        finally:
            Path(tmp).unlink(missing_ok=True)
    receipt={"snapshot":stamp,"verified":True,"bytes":target.stat().st_size}
    print(json.dumps(receipt))
    # No automatic deletion of pre-existing external archives.
    return receipt

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--destination",type=Path,required=True);p.add_argument("--ssh",default="ssh");p.add_argument("--host",default="rmm-vps")
    a=p.parse_args();pull(a.destination,a.ssh,a.host)
