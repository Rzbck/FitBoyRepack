"""Conservative release dates, preserving precision and conflicting sources."""
import re
import json
from datetime import date, datetime, timezone
from calendar import month_abbr, month_name

MONTHS={name.lower():i for names in (month_abbr,month_name) for i,name in enumerate(names) if i}

def normalize_date(value):
    m=re.fullmatch(r"((?:19|20)\d{2})(?:-(\d{2})(?:-(\d{2}))?)?",str(value or "").strip())
    if not m:return None
    y,mo,d=m.groups()
    if not mo or mo=="00":return y if not d or d=="00" else None
    if not 1<=int(mo)<=12:return None
    if not d or d=="00":return y+"-"+mo
    try:return date(int(y),int(mo),int(d)).isoformat()
    except ValueError:return None

def steam_date(payload):
    if not isinstance(payload,dict) or payload.get("coming_soon") is not False:return None
    raw=str(payload.get("date") or "").strip()
    m=re.fullmatch(r"([A-Za-z]+) (\d{1,2}), (\d{4})",raw)
    if m:month,day,year=m.groups()
    else:
        m=re.fullmatch(r"(\d{1,2}) ([A-Za-z]+),? (\d{4})",raw)
        if not m:return None
        day,month,year=m.groups()
    mo=MONTHS.get(month.lower())
    if not mo:return None
    value=normalize_date(f"{year}-{mo:02d}-{int(day):02d}")
    return value if value and value<=datetime.now(timezone.utc).date().isoformat() else None

def release_choice(metadata,row):
    wiki=normalize_date((metadata or {}).get("release_date"))
    steam=None
    if isinstance(row,dict) and row.get("status") in {"rated","no_reviews","pending","unavailable"} and row.get("store_verified_at") and row.get("steam_appid") and row.get("steam_release_appid")==row.get("steam_appid"):
        candidate=normalize_date(row.get("steam_release_date"))
        if candidate and len(candidate)==10:steam=candidate
    # Exact original-release evidence is not silently replaced by Steam release.
    chosen=wiki if wiki and len(wiki)==10 else steam or wiki
    source="wikidata" if chosen and chosen==wiki else "steam" if chosen else None
    conflict=bool(wiki and steam and not steam.startswith(wiki))
    return {"game_release_date":chosen,"game_release_source":source,
            "game_release_precision":{4:"year",7:"month",10:"day"}.get(len(chosen or "")),
            "game_release_conflict":conflict,"steam_release_date":steam,
            "wikidata_release_date":wiki}

def load_release_seed(path):
    """A one-time, separately published collection; never modify the live cache."""
    if not path.exists():return {},None
    payload=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload,dict) or payload.get("seed_version")!=1 or not isinstance(payload.get("games"),dict) or not isinstance(payload.get("generated_at"),str):
        raise ValueError("invalid Steam release seed")
    return payload["games"],payload["generated_at"]

def apply_release_seed(rows,seed):
    """Import only into an existing verified identity with no date observation."""
    count=0
    for gid,entry in seed.items():
        row=rows.get(gid)
        if not isinstance(row,dict) or not isinstance(entry,dict):continue
        appid=row.get("steam_appid")
        if (row.get("status") not in {"rated","pending","no_reviews","unavailable"}
            or not row.get("store_verified_at") or row.get("steam_release_checked_at")
            or not isinstance(appid,int) or isinstance(appid,bool) or appid<=0
            or entry.get("steam_appid")!=appid or entry.get("steam_release_appid")!=appid
            or not row.get("steam_store_name") or row["steam_store_name"]!=entry.get("steam_store_name")):continue
        value=normalize_date(entry.get("steam_release_date"))
        checked=entry.get("steam_release_checked_at")
        if not value or len(value)!=10 or not isinstance(checked,str):continue
        try:
            stamp=datetime.fromisoformat(checked.replace("Z","+00:00"))
            if stamp.tzinfo is None or stamp>datetime.now(timezone.utc):continue
        except ValueError:continue
        if value>stamp.date().isoformat():continue
        row.update({"steam_release_date":value,"steam_release_appid":appid,"steam_release_checked_at":checked})
        row.pop("steam_release_retry_at",None)
        count+=1
    return count
