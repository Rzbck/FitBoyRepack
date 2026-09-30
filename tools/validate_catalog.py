#!/usr/bin/env python3
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

P=Path('site/data/games.json')
data=json.loads(P.read_text(encoding='utf-8'))
assert isinstance(data,dict) and isinstance(data.get('games'),list),'games.json must contain {games: []}'
seen=set()
for i,g in enumerate(data['games']):
 assert isinstance(g,dict),f'game[{i}] is not an object'
 for key in ('id','title','source_url'): assert isinstance(g.get(key),str) and g[key].strip(),f'game[{i}] missing {key}'
 assert g['id'] not in seen,f'duplicate id: {g["id"]}'; seen.add(g['id'])
 u=urlparse(g['source_url']); assert u.scheme=='https' and u.netloc,f'invalid source_url: {g["source_url"]}'
 assert 'magnet:' not in json.dumps(g).lower(),f'magnet URI found in {g["id"]}'
 if g.get('post_date'): datetime.fromisoformat(g['post_date'].replace('Z','+00:00'))
 assert isinstance(g.get('genres',[]),list),f'genres must be list: {g["id"]}'
print(f'catalog OK: {len(data["games"])} games, {len(seen)} unique ids')
