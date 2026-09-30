#!/usr/bin/env python3
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path('site'); html=(ROOT/'index.html').read_text(encoding='utf-8'); css=(ROOT/'assets/style.css').read_text(encoding='utf-8'); js=(ROOT/'assets/app.js').read_text(encoding='utf-8')
class P(HTMLParser):
 def __init__(self): super().__init__(); self.ids=set(); self.scripts=[]; self.links=[]
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  if 'id' in d:self.ids.add(d['id'])
  if tag=='script' and d.get('src'):self.scripts.append(d['src'])
  if tag=='link' and d.get('href'):self.links.append(d['href'])
p=P(); p.feed(html)
required={'gameGrid','cardTemplate','searchInput','genreFilter','sortControl','gameDialog','catalogStatus'}
missing=required-p.ids; assert not missing,f'missing required DOM ids: {sorted(missing)}'
assert './assets/app.js' in p.scripts and './assets/style.css' in p.links
assert (ROOT/'data/games.json').exists(); assert 'DATA_URL' in js and '.game-grid' in css
print('site smoke OK')
