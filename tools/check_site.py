#!/usr/bin/env python3
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import unicodedata

ROOT=Path('site')
html=(ROOT/'index.html').read_text(encoding='utf-8')
app=(ROOT/'assets/app.js').read_text(encoding='utf-8')
api=(ROOT/'assets/core/catalog-api.js').read_text(encoding='utf-8')
details=(ROOT/'assets/details.js').read_text(encoding='utf-8')
identity=(ROOT/'assets/catalog/game-identity.js').read_text(encoding='utf-8')
i18n=(ROOT/'assets/core/i18n.js').read_text(encoding='utf-8')
translations=(ROOT/'assets/catalog/translations.js').read_text(encoding='utf-8')
v2css=(ROOT/'assets/catalog.css').read_text(encoding='utf-8')
focuscss=(ROOT/'assets/catalog.css').read_text(encoding='utf-8')

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
'exportLibrary','importLibraryButton','importLibrary',
'healthBadge','healthPanel','healthTotal','healthDescriptions','healthGalleries','healthGifs','healthMeta','languageSwitcher'
}
missing=required-p.ids
assert not missing, f'missing required DOM ids: {sorted(missing)}'
assert 'discoveryShell' not in p.ids, 'Discover panel must no longer appear in the catalog'
assert "state.libraryFilter==='favorites'" in app, 'recommendations must stay inside Favorites'
assert 'catalogResults' in p.ids and 'catalogHeading' in p.ids, 'compact Favorites layout is missing'
assert 'steam_best' in html and 'steam_hidden' in html, 'Steam sort options are missing'
assert './assets/catalog.css?v=1' in p.links, 'Favorites layout CSS is missing'
ratings=json.loads((ROOT/'data/steam-ratings.json').read_text(encoding='utf-8'))
assert ratings.get('rating_version')==1 and isinstance(ratings.get('games'),dict)
for game_id, row in ratings['games'].items():
    assert isinstance(game_id,str) and isinstance(row,dict)
    assert row.get('status') in ('rated','no_reviews','pending','no_match','unavailable','mismatch'), f'invalid Steam status for {game_id}'
    if row.get('status')=='mismatch':
        assert not row.get('steam_appid'), f'invalid Steam ID must not remain attached to {game_id}'
        assert 'positive_percent' not in row, f'invalid Steam score must not be displayed for {game_id}'
    if row.get('status')=='rated':
        assert row.get('total_reviews',0)>0 and 0<=row.get('positive_percent',-1)<=100
assert './assets/app.js?v=7' in p.scripts and './assets/details.js?v=6' in p.scripts and './assets/media-sanitize.js' in p.scripts
assert './assets/tag-facets.js' not in p.scripts, 'facets are now integrated in the main filtered state'
assert './assets/catalog.css?v=1' in p.links
assert './assets/base.css?v=2' in p.links and './assets/game-sheet.css?v=1' in p.links
assert (ROOT/'data/games.json').exists()
assert (ROOT/'data/catalog.json').exists(), 'run tools/build_site_data.py before smoke test'
assert (ROOT/'data/search-index.json').exists(), 'static search index missing'
assert (ROOT/'data/health.json').exists(), 'health payload missing'
assert (ROOT/'data/translations-fr.json').exists(), 'French translation snapshot missing'

catalog=json.loads((ROOT/'data/catalog.json').read_text(encoding='utf-8'))
search=json.loads((ROOT/'data/search-index.json').read_text(encoding='utf-8'))
health=json.loads((ROOT/'data/health.json').read_text(encoding='utf-8'))
translations_fr=json.loads((ROOT/'data/translations-fr.json').read_text(encoding='utf-8'))
assert health['total_games'] >= health['with_description'] >= 0
assert health['total_games'] >= health['with_gallery'] >= 0
assert health['total_games'] >= health.get('metadata_verified', 0) >= 0
assert health.get('expected_versions', {}).get('metadata') == 1
assert all(
    'metadata_ready' in game
    and 'canonical_title' in game
    and 'metadata_genres' in game
    and 'metadata_developer' in game
    and 'metadata_publisher' in game
    and 'metadata_platforms' in game
    and 'metadata_evidence_urls' in game
    for game in catalog['games']
)
assert search['search_index_version'] == 1
assert search['count'] == catalog['count'] == len(catalog['games'])
# Arrival date remains in the catalog for "Recently added" and game details;
# the displayed card date / year instead belong to the actual game release.
for release_game in catalog['games']:
    assert 'post_date' in release_game and release_game['post_date'], 'arrival timestamp lost'
    assert 'game_release_date' in release_game, 'release-date field missing'
    date = release_game.get('game_release_date') or ''
    expected_year = int(date[:4]) if re.match(r'^(?:19|20)[0-9]{2}(?=$|[-T ])', date) else None
    assert release_game.get('year') == expected_year, f'wrong release year for {release_game["id"]}'
assert 'releaseNode.textContent=verifiedRelease' in app
assert 'releaseNode.hidden=!verifiedRelease' in app, 'unknown release date must be completely hidden'
assert "releaseNode.textContent=verifiedRelease ? formatDate(game.game_release_date) : ''" in app
assert 'cover-wrap > .steam-rating' in app, 'Steam badges must attach to the cover'
assert '<div class="steam-rating steam-cover-badge" hidden></div></div><div class="card-body">' in html
assert '<div class="steam-rating" hidden></div><div class="genre-row">' not in html, 'body Steam rating must not remain'

assert search['prefix_min'] == 2 and search['prefix_max'] >= search['prefix_min']
assert search['gram_size'] == 3
assert isinstance(search['prefixes'], dict) and search['prefixes']
assert isinstance(search['grams'], dict) and search['grams']
assert translations_fr.get('translation_version') == 1
assert translations_fr.get('language') == 'fr'
assert isinstance(translations_fr.get('games'), dict)
assert translations_fr.get('count') == len(translations_fr['games'])
assert 'translations-fr.json' not in api and 'loadTranslationsFrPayload' not in details
from build_site_data import verified_translation_entry
translation_games=translation_fields=0
for item in catalog['games']:
    payload=json.loads((ROOT/item['detail_path']).read_text(encoding='utf-8'))
    assert 'translations_fr' not in item
    expected,count=verified_translation_entry(payload.get('details') or {},translations_fr['games'].get(str(item['id'])))
    assert payload.get('translations_fr',{})==expected, item['id']
    translation_games+=bool(count)
    translation_fields+=count
assert translation_games==health['translation_games']
assert translation_fields==health['translation_fields']

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

for token in ('queryScore','createQueryScorer','searchCandidateIndexes','searchPool','renderSuggestions','yearFilter','releasePeriodFilter','releasePeriodMatches','releaseDate','effectiveTags','sizeFilter','detailsOnly','mediaOnly','selectedTagsBar','tagPickerDialog','openTagPicker','readLibrary','exportLibrary','importLibrary','recommendationScores','titleAffinityTokens','loadSearchIndexPayload','loadHealthPayload','IntersectionObserver','loadNextPage','openHashGame','fitboy:game-open','fitboy:language-change','cardDisplayTitle','cardDisplayTags','identityDisplayTitle'  ,'initI18n','metadata_developer','metadata_publisher','buildInitialVerifiedIdentity','buildInitialCoverIdentity','buildDetailLoadingShell','cover-details-initial','detail-loading-shell','dialog-loading'):
    assert token in app, f'missing V2 behavior: {token}'
for token in ('catalog.json','search-index.json','health.json','loadSearchIndexPayload','loadHealthPayload','loadGameDetail'):
    assert token in api, f'missing API behavior: {token}'
for token in ('openLightbox','renderDescriptionTabs','renderGameplayPreview','loadGameDetail','localizeGameProse','makeIdentityFacts','identityStable','cleanPlatformLabel','verifiedMetadata','detail.releaseDate','detail.verified'):
    assert token in details, f'missing detail behavior: {token}'
for token in ('displayTitle','editionTitle','effectiveGenreLabels','cleanGenreLabel','titleParts'):
    assert token in identity, f'missing shared identity behavior: {token}'
for token in ('STORAGE_KEYS.language','navigator.languages','data-i18n','languageSwitcher','setLanguageMode'):
    assert token in i18n or token in html, f'missing i18n behavior: {token}'
for token in ('localizeGameProse','source_sha256','crypto.subtle'):
    assert token in translations, f'missing translation client behavior: {token}'
for token in ('.search-suggestions','.quick-filter-panel','.library-panel','.home-card-row','.dialog-actions','.filter-sidebar.mobile-open','.health-grid'):
    assert token in v2css, f'missing V2 CSS contract: {token}'
for token in ('.compact-tag-filter','.tag-picker-dialog','.tag-picker-list','.release-period-field','max-height:none'):
    assert token in focuscss, f'missing compact filter CSS contract: {token}'
assert "title.textContent=game.title;info.append(title)" not in app.replace(" ", ""), 'legacy dialog title flash returned'
assert "t('detail.loading')" in app, 'accessible localized loading status missing'
assert 'magnet:?' not in app.lower() and 'torrent_links' not in app.lower()
print('site V2 smoke OK')
