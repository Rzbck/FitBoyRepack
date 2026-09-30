#!/usr/bin/env python3
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
assert (ROOT/'data/games.json').exists()

for token in (
    'DATA_URL','renderRecommendations','appendMediaGallery','selectedTags',
    'lockCatalogScroll','unlockCatalogScroll','tagResultCount','__tagKeySet',
    'navigateDialog','dialogScrollY','pointerdown','IntersectionObserver','loadNextPage',
    'scheduleInfiniteCheck','armInfiniteObserver','grid.append','rootMargin','LOAD_COOLDOWN_MS',
    'infiniteObserver.unobserve','const PAGE_SIZE = 30;'
):
    assert token in js, f'missing frontend behavior: {token}'

load_block = js.split('function loadNextPage()', 1)[1].split('function scheduleInfiniteCheck()', 1)[0]
schedule_block = js.split('function scheduleInfiniteCheck()', 1)[1].split('const infiniteObserver', 1)[0]
assert 'scheduleInfiniteCheck(' not in load_block, 'loadNextPage must not recursively schedule another page'
assert 'loadNextPage(' not in schedule_block, 'resize/schedule hook must never trigger a page load directly'
assert "rootMargin:'900px 0px'" not in js, '900px prefetch margin is too aggressive for this catalog'

for token in ('compatibleCounts','button.disabled','selectedTagKeys',"cache:'no-cache'",'requestAnimationFrame','subtree:false'):
    assert token in facets_js, f'missing tag facet behavior: {token}'
assert 'queueMicrotask' not in facets_js, 'facet updates must not create a microtask feedback loop'
assert "childList:true, subtree:true" not in facets_js, 'facet observer must never watch its own counter mutations'

for token in ('openLightbox','preventDefault','renderCoverDetails','renderDescriptionTabs','renderGameplayPreview'):
    assert token in details_js, f'missing rich details behavior: {token}'
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
for token in ('.catalog-layout','.filter-sidebar','.sidebar-tag-list','position:sticky'):
    assert token in sidebar_css, f'missing sidebar filter contract: {token}'
for token in ('torrent-stats.info','MutationObserver','.media-item'):
    assert token in sanitize_js, f'missing legacy media sanitizer contract: {token}'
print('site smoke OK')
