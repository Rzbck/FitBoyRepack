#!/usr/bin/env python3
import json
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path('site')
html = (ROOT/'index.html').read_text(encoding='utf-8')
css = (ROOT/'assets/style.css').read_text(encoding='utf-8')
modal_css = (ROOT/'assets/modal-fix.css').read_text(encoding='utf-8')
ux_css = (ROOT/'assets/ux-fixes.css').read_text(encoding='utf-8')
compact_css = (ROOT/'assets/compact-header.css').read_text(encoding='utf-8')
performance_css = (ROOT/'assets/performance.css').read_text(encoding='utf-8')
sidebar_css = (ROOT/'assets/filter-sidebar.css').read_text(encoding='utf-8')
js = (ROOT/'assets/app.js').read_text(encoding='utf-8')
facets_js = (ROOT/'assets/tag-facets.js').read_text(encoding='utf-8')
details_js = (ROOT/'assets/details.js').read_text(encoding='utf-8')
catalog_api_js = (ROOT/'assets/catalog-api.js').read_text(encoding='utf-8')
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
    'gameGrid','cardTemplate','searchInput','sortControl','gameDialog','catalogStatus','visibleCount',
    'tagFilter','tagList','tagSearch','tagMode','clearTags','selectedTagCount','tagResultCount','filterSidebar',
    'recommendationSection','recommendationGrid','recommendationMeta','scrollSentinel','infiniteStatus'
}
missing=required-p.ids
assert not missing, f'missing required DOM ids: {sorted(missing)}'
assert 'Les derniers jeux, vite et proprement.' not in html
assert 'Afficher plus' not in html
assert 'Au moins un (OU)' not in html, 'tag filtering must expose one strict additive mode only'
assert 'id="tagMode" hidden' in html, 'internal strict tag mode must stay hidden from the UI'
assert './assets/app.js' in p.scripts
assert './assets/tag-facets.js' in p.scripts
assert './assets/details.js' in p.scripts
assert './assets/media-sanitize.js' in p.scripts
assert './assets/style.css' in p.links
assert './assets/modal-fix.css' in p.links
assert './assets/ux-fixes.css' in p.links
assert './assets/compact-header.css' in p.links
assert './assets/performance.css' in p.links
assert './assets/filter-sidebar.css' in p.links

source_path = ROOT/'data/games.json'
catalog_path = ROOT/'data/catalog.json'
detail_dir = ROOT/'data/games'
assert source_path.exists(), 'source games.json missing'
assert catalog_path.exists(), 'lightweight catalog.json must be generated before site checks'
assert detail_dir.is_dir(), 'per-game detail directory missing'
source_payload = json.loads(source_path.read_text(encoding='utf-8'))
catalog_payload = json.loads(catalog_path.read_text(encoding='utf-8'))
assert catalog_payload.get('count') == len(catalog_payload.get('games', []))
assert len(catalog_payload['games']) == len(source_payload['games']), 'light catalog must contain every source game'
assert catalog_path.stat().st_size < source_path.stat().st_size, 'light catalog must be smaller than rich source payload'
assert catalog_payload['games'], 'light catalog cannot be empty'
first = catalog_payload['games'][0]
assert first.get('detail_path', '').startswith('data/games/')
first_detail = ROOT / first['detail_path']
assert first_detail.exists(), f'missing lazy detail payload: {first_detail}'
assert json.loads(first_detail.read_text(encoding='utf-8')).get('id') == first.get('id')

for token in (
    'loadCatalogPayload','renderRecommendations','selectedTags',
    'lockCatalogScroll','unlockCatalogScroll','tagResultCount','__tagKeySet',
    'navigateDialog','dialogScrollY','pointerdown','IntersectionObserver','loadNextPage',
    'scheduleInfiniteCheck','armInfiniteObserver','grid.append','rootMargin','LOAD_COOLDOWN_MS',
    'infiniteObserver.unobserve','const PAGE_SIZE = 30;','syncGameHash','gameHashId',
    'fitboy:game-open','detail_path'
):
    assert token in js, f'missing frontend behavior: {token}'
assert 'data/games.json' not in js, 'main frontend must never fetch the rich monolith'

load_block = js.split('function loadNextPage()', 1)[1].split('function scheduleInfiniteCheck()', 1)[0]
schedule_block = js.split('function scheduleInfiniteCheck()', 1)[1].split('const infiniteObserver', 1)[0]
assert 'scheduleInfiniteCheck(' not in load_block, 'loadNextPage must not recursively schedule another page'
assert 'loadNextPage(' not in schedule_block, 'resize/schedule hook must never trigger a page load directly'
assert "rootMargin:'900px 0px'" not in js, '900px prefetch margin is too aggressive for this catalog'

for token in ('compatibleCounts','button.disabled','selectedTagKeys','loadCatalogPayload','requestAnimationFrame','subtree:false'):
    assert token in facets_js, f'missing tag facet behavior: {token}'
assert 'data/games.json' not in facets_js, 'tag facets must reuse the lightweight catalog'
assert 'queueMicrotask' not in facets_js, 'facet updates must not create a microtask feedback loop'
assert "childList:true, subtree:true" not in facets_js, 'facet observer must never watch its own counter mutations'

for token in ('openLightbox','preventDefault','renderCoverDetails','renderDescriptionTabs','renderGameplayPreview','renderMediaGallery','loadGameDetail','fitboy:game-open'):
    assert token in details_js, f'missing lazy rich details behavior: {token}'
assert 'data/games.json' not in details_js, 'details frontend must lazy-load one game, not the monolith'
for token in ('CATALOG_URL','catalog.json','loadCatalogPayload','loadGameDetail','DETAIL_CACHE_LIMIT'):
    assert token in catalog_api_js, f'missing catalog API behavior: {token}'

for token in ('.game-grid','.tag-list','.recommendation-grid','.media-grid'):
    assert token in css, f'missing CSS contract: {token}'
for token in ('.game-dialog','#dialogContent','.dialog-info','.media-grid','90dvh','.media-lightbox','.cover-details','.detail-tabs'):
    assert token in modal_css, f'missing modal viewport/details contract: {token}'
for token in ('.dialog-scroll-locked','.tag-result-summary','overflow:hidden','.tag-chip:disabled','.tag-chip.active::after'):
    assert token in ux_css, f'missing modal/filter UX contract: {token}'
for token in ('.compact-topbar','.header-toolbar','.scroll-sentinel','.header-count'):
    assert token in compact_css, f'missing compact header/infinite-scroll CSS contract: {token}'
for token in ('content-visibility: auto','contain-intrinsic-size'):
    assert token in performance_css, f'missing offscreen rendering optimization: {token}'
for token in ('.catalog-layout','.filter-sidebar','.sidebar-tag-list','position:sticky','flex-wrap:wrap','width:min(1900px,calc(100% - 20px))','.sidebar-tag-list .tag-chip:disabled','display:none'):
    assert token in sidebar_css, f'missing compact strict sidebar filter contract: {token}'
for token in ('torrent-stats.info','MutationObserver','.media-item'):
    assert token in sanitize_js, f'missing legacy media sanitizer contract: {token}'
print(f"site smoke OK: {catalog_payload['count']} lightweight entries + lazy details")
