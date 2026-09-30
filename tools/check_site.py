#!/usr/bin/env python3
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path('site')
html = (ROOT/'index.html').read_text(encoding='utf-8')
css = (ROOT/'assets/style.css').read_text(encoding='utf-8')
modal_css = (ROOT/'assets/modal-fix.css').read_text(encoding='utf-8')
js = (ROOT/'assets/app.js').read_text(encoding='utf-8')
sanitize_js = (ROOT/'assets/media-sanitize.js').read_text(encoding='utf-8')

class P(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=set(); self.scripts=[]; self.links=[]
    def handle_starttag(self, tag, attrs):
        data=dict(attrs)
        if 'id' in data: self.ids.add(data['id'])
        if tag=='script' and data.get('src'): self.scripts.append(data['src'])
        if tag=='link' and data.get('href'): self.links.append(data['href'])

p=P(); p.feed(html)
required={
    'gameGrid','cardTemplate','searchInput','sortControl','gameDialog','catalogStatus',
    'tagFilter','tagList','tagSearch','tagMode','clearTags','selectedTagCount',
    'recommendationSection','recommendationGrid','recommendationMeta'
}
missing=required-p.ids
assert not missing, f'missing required DOM ids: {sorted(missing)}'
assert './assets/app.js' in p.scripts
assert './assets/media-sanitize.js' in p.scripts
assert './assets/style.css' in p.links
assert './assets/modal-fix.css' in p.links
assert (ROOT/'data/games.json').exists()
for token in ('DATA_URL','renderRecommendations','appendMediaGallery','selectedTags'):
    assert token in js, f'missing frontend behavior: {token}'
for token in ('.game-grid','.tag-list','.recommendation-grid','.media-grid'):
    assert token in css, f'missing CSS contract: {token}'
for token in ('.game-dialog','#dialogContent','.dialog-info','.media-grid','90dvh'):
    assert token in modal_css, f'missing modal viewport contract: {token}'
for token in ('torrent-stats.info','MutationObserver','.media-item'):
    assert token in sanitize_js, f'missing legacy media sanitizer contract: {token}'
print('site smoke OK')
