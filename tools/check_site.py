#!/usr/bin/env python3
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import unicodedata

ROOT=Path('site')
html=(ROOT/'index.html').read_text(encoding='utf-8')
app=(ROOT/'assets/app.js').read_text(encoding='utf-8')
api=(ROOT/'assets/catalog-api.js').read_text(encoding='utf-8')
details=(ROOT/'assets/details.js').read_text(encoding='utf-8')
identity=(ROOT/'assets/game-identity.js').read_text(encoding='utf-8')
v2css=(ROOT/'assets/catalog-v2.css').read_text(encoding='utf-8')
focuscss=(ROOT/'assets/catalog-focus-v3.css').read_text(encoding='utf-8')

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
'recommendationSection','recommendationGrid','recommendationMeta','scrollSentinel','infiniteStatus','yearFilter','releasePeriodFilter','sizeFilter',
'newOnlyFilter','detailsOnlyFilter','mediaOnlyFilter','resetFilters','mobileFiltersButton','filterOverlay','closeFilters',
'tagPickerDialog','openTagPicker','closeTagPicker',
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
assert (ROOT/'data/search-index.json').exists(), 'static search index missing'
assert (ROOT/'data/health.json').exists(), 'health payload missing'

catalog=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))
search=json.loads((ROOT/'data/search-index.json').read_text(encoding='utf-8'))
health=json.loads((ROOT/'data/health.json').read_text(encoding='utf-8'))
assert health['total_games'] >= health['with_description'] >= 0
assert health['total_games'] >= health['with_gallery'] >= 0
assert health['total_games'] >= health.get('metadata_verified', 0) >= 0
assert health.get('expected_versions', {}).get('metadata') == 1
assert all('metadata_ready' in game and 'canonical_title' in game and 'metadata_genres' in game for game in catalog['games'])
assert search['search_index_version'] == 1
assert search['count'] == catalog['count'] == len(catalog['games'])
assert search['prefix_min'] == 2 and search['prefix_max'] >= search['prefix_min']
assert search['gram_size'] == 3
assert isinstance(search['prefixes'], dict) and search['prefixes']
assert isinstance(search['grams'], dict) and search['grams']

def norm(value):
    text=unicodedata.normalize('NFD',str(value or ''))
    text=''.join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',text)).strip()

for ordinal,game in enumerate(catalog['games']):
    title_tokens=norm(game.get('title')).split()
    assert title_tokens, f'empty normalized title at ordinal {ordinal}'
    token=title_tokens[0]
    if len(token)>=search['prefix_min']:
        key=token[:min(search['prefix_max'],len(token))]
        assert ordinal in search['prefixes'].get(key,[]), f'missing prefix posting for {game["id"]}'
    if len(token)>=search['gram_size']:
        gram=token[:search['gram_size']]
        assert ordinal in search['grams'].get(gram,[]), f'missing gram posting for {game["id"]}'

for token in ('queryScore','boundedDistance','searchCandidateIndexes','searchPool','renderSuggestions','yearFilter','releasePeriodFilter','releasePeriodMatches','releaseDate','effectiveTags','sizeFilter','detailsOnly','mediaOnly','selectedTagsBar','tagPickerDialog','openTagPicker','LIBRARY_KEY','exportLibrary','importLibrary','recommendationScores','titleAffinityTokens','renderHighlights','loadSearchIndexPayload','loadHealthPayload','IntersectionObserver','loadNextPage','openHashGame','fitboy:game-open','cardDisplayTitle','cardDisplayTags','identityDisplayTitle','buildInitialCoverIdentity','buildDetailLoadingShell','cover-details-initial','detail-loading-shell','dialog-loading'):
    assert token in app, f'missing V2 behavior: {token}'
for token in ('catalog.json','search-index.json','health.json','loadSearchIndexPayload','loadHealthPayload','loadGameDetail'):
    assert token in api, f'missing API behavior: {token}'
for token in ('openLightbox','renderDescriptionTabs','renderGameplayPreview','loadGameDetail','makeIdentityFacts','identityStable','cleanPlatformLabel','verifiedMetadata','Sortie du jeu','Données vérifiées'):
    assert token in details, f'missing detail behavior: {token}'
for token in ('displayTitle','editionTitle','effectiveGenreLabels','cleanGenreLabel','titleParts'):
    assert token in identity, f'missing shared identity behavior: {token}'
for token in ('.search-suggestions','.quick-filter-panel','.library-panel','.home-card-row','.dialog-actions','.filter-sidebar.mobile-open','.health-grid'):
    assert token in v2css, f'missing V2 CSS contract: {token}'
for token in ('.compact-tag-filter','.tag-picker-dialog','.tag-picker-list','.release-period-field','max-height:none'):
    assert token in focuscss, f'missing compact filter CSS contract: {token}'
assert "title.textContent=game.title;info.append(title)" not in app.replace(" ", ""), 'legacy dialog title flash returned'
assert 'Chargement de la fiche détaillée…' in app, 'accessible loading status missing'
assert 'magnet:?' not in app.lower() and 'torrent_links' not in app.lower()
print('site V2 smoke OK')
