"""Conservative release dates, preserving precision and conflicting sources."""
import re
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
