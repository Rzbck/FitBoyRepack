#!/usr/bin/env python3
from html.parser import HTMLParser
from pathlib import Path
import json

ROOT=Path('site')
html=(ROOT/'index.html').read_text(encoding='utf-8')
app=(ROOT/'assets/app.js').read_text(encoding='utf-8')
api=(ROOT/'assets/catalog-api.js').read_text(encoding='utf-8')
details=(ROOT/'assets/details.js').read_text(encoding='utf-8')
v2css=(ROOT/'assets/catalog-v2.css').read_text(encoding='utf-8')

class P(HTMLParser):
    def __init__(self): super().__init__(); self.ids=set(); self.scripts=[]; self.links=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if d.get('id'): self.ids.add(d['id'])
        if tag=='script' and d.get('src'): self.scripts.append(d['src'])
        if tag=='link' and d.get('href'): self.links.append(d['href'])
p=P();p.feed(html)
required={
'gameGrid','cardTemplate','searchInput','searchSuggestions','sortControl','gameDialog','catalogStatus','visibleCount',
'tagFilter','tagList','tagSearch','clearTags','selectedTagCount','selectedTagsBar','tagResultCount','filterSidebar',
'recommendationSection','recommendationGrid','recommendationMeta','scrollSentinel','infiniteStatus','yearFilter','sizeFilter',
'newOnlyFilter','detailsOnlyFilter','mediaOnlyFilter','resetFilters','mobileFiltersButton','filterOverlay','closeFilters',
'exportLibrary','importLibraryButton','importLibrary','newSection','newGrid','updatedSection','updatedGrid','librarySection','libraryGrid',
'healthBadge','healthPanel','healthTotal','healthDescriptions','healthGalleries','healthGifs','healthMeta'
}
missing=required-p.ids
assert not missing, f'missing required DOM ids: {sorted(missing)}'
assert './assets/app.js' in p.scripts and './assets/details.js' in p.scripts and './assets/media-sanitize.js' in p.scripts
assert './assets/tag-facets.js' not in p.scripts, 'facets are now integrated in the main filtered state'
assert './assets/catalog-v2.css' in p.links
assert (ROOT/'data/games.json').exists()
assert (ROOT/'data/catalog.json').exists(), 'run tools/build_site_data.py before smoke test'
assert (ROOT/'data/health.json').exists(), 'health payload missing'
health=json.loads((ROOT/'data/health.json').read_text(encoding='utf-8'))
assert health['total_games'] >= health['with_description'] >= 0
assert health['total_games'] >= health['with_gallery'] >= 0

for token in ('queryScore','boundedDistance','renderSuggestions','yearFilter','sizeFilter','detailsOnly','mediaOnly','selectedTagsBar','LIBRARY_KEY','exportLibrary','importLibrary','recommendationScores','titleAffinityTokens','renderHighlights','loadHealthPayload','IntersectionObserver','loadNextPage','openHashGame','fitboy:game-open'):
    assert token in app, f'missing V2 behavior: {token}'
for token in ('catalog.json','health.json','loadHealthPayload','loadGameDetail'):
    assert token in api, f'missing API behavior: {token}'
for token in ('openLightbox','renderDescriptionTabs','renderGameplayPreview','loadGameDetail'):
    assert token in details, f'missing detail behavior: {token}'
for token in ('.search-suggestions','.quick-filter-panel','.library-panel','.home-card-row','.dialog-actions','.filter-sidebar.mobile-open','.health-grid'):
    assert token in v2css, f'missing V2 CSS contract: {token}'
assert 'magnet:?' not in app.lower() and 'torrent_links' not in app.lower()
print('site V2 smoke OK')
