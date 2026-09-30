const DATA_URL = './data/games.json';
const PAGE_SIZE = 30;
const RECOMMENDATION_LIMIT = 12;
const FAVORITES_KEY = 'fitboyrepack:favorites:v1';
const LOAD_COOLDOWN_MS = 250;

const $ = (selector) => document.querySelector(selector);
const els = {
  grid: $('#gameGrid'), template: $('#cardTemplate'), search: $('#searchInput'), sort: $('#sortControl'),
  count: $('#visibleCount'), status: $('#catalogStatus'), empty: $('#emptyState'),
  favoritesToggle: $('#favoritesToggle'), activeState: $('#activeState'), dialog: $('#gameDialog'),
  dialogContent: $('#dialogContent'), tagFilter: $('#tagFilter'), tagList: $('#tagList'), tagSearch: $('#tagSearch'),
  tagMode: $('#tagMode'), clearTags: $('#clearTags'), selectedTagCount: $('#selectedTagCount'), tagResultCount: $('#tagResultCount'),
  recommendationSection: $('#recommendationSection'), recommendationGrid: $('#recommendationGrid'),
  recommendationMeta: $('#recommendationMeta'), scrollSentinel: $('#scrollSentinel'), infiniteStatus: $('#infiniteStatus')
};

const state = {
  games: [], filtered: [], visible: PAGE_SIZE, favoritesOnly: false,
  favorites: readFavorites(), selectedTags: new Set(), tagCounts: new Map(),
  dialogGameId: null, dialogScrollY: 0, dialogOpener: null,
  loadingMore: false, lastLoadAt: 0
};

function readFavorites() {
  try { return new Set(JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]').map(String)); }
  catch { return new Set(); }
}
function saveFavorites() { localStorage.setItem(FAVORITES_KEY, JSON.stringify([...state.favorites])); }
function normalized(value = '') { return String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim(); }
function gameDate(game) { const time = Date.parse(game.post_date || ''); return Number.isFinite(time) ? time : 0; }
function formatDate(value) { const time = Date.parse(value || ''); return Number.isFinite(time) ? new Intl.DateTimeFormat('fr-FR', { day:'2-digit', month:'short', year:'numeric' }).format(time) : 'Date inconnue'; }
function isNew(game) { const time = gameDate(game); return Boolean(time && Date.now() - time < 14 * 86400000); }
function getTags(game) {
  const value = game.genres ?? game.genre ?? [];
  const raw = Array.isArray(value) ? value : String(value || '').split(',');
  return raw.map(item => String(item).trim()).filter(Boolean);
}
function getMedia(game) {
  if (!Array.isArray(game.media)) return [];
  return game.media.filter(item => item && typeof item.url === 'string' && item.url.startsWith('https://')).slice(0, 12);
}

function prepareGame(raw) {
  const game = { ...raw, id:String(raw.id) };
  const tags = getTags(game);
  game.__tagKeys = tags.map(normalized);
  game.__tagKeySet = new Set(game.__tagKeys);
  game.__searchText = normalized([game.title, game.repack_size, ...tags].join(' '));
  return game;
}

function buildTagIndex() {
  const canonical = new Map();
  const counts = new Map();
  for (const game of state.games) {
    const unique = new Set();
    for (const tag of getTags(game)) {
      const key = normalized(tag);
      if (!key || unique.has(key)) continue;
      unique.add(key);
      if (!canonical.has(key)) canonical.set(key, tag);
      counts.set(key, (counts.get(key) || 0) + 1);
    }
  }
  state.tagCounts = counts;
  const tags = [...canonical.entries()]
    .map(([key, label]) => ({ key, label, count: counts.get(key) || 0 }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'fr', { sensitivity:'base' }));

  const fragment = document.createDocumentFragment();
  for (const tag of tags) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'tag-chip'; button.dataset.tagKey = tag.key; button.dataset.tagLabel = tag.label;
    const label = document.createElement('span'); label.textContent = tag.label;
    const count = document.createElement('small'); count.textContent = tag.count.toLocaleString('fr-FR');
    button.append(label, count);
    button.addEventListener('click', () => {
      state.selectedTags.has(tag.key) ? state.selectedTags.delete(tag.key) : state.selectedTags.add(tag.key);
      updateTagUI(); applyFilters();
    });
    fragment.append(button);
  }
  els.tagList.replaceChildren(fragment);
  updateTagUI();
}

function updateTagUI() {
  els.selectedTagCount.textContent = String(state.selectedTags.size);
  els.tagFilter.classList.toggle('active', state.selectedTags.size > 0);
  els.tagList.querySelectorAll('.tag-chip').forEach(button => {
    const active = state.selectedTags.has(button.dataset.tagKey);
    button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
  });
}

function filterVisibleTags() {
  const query = normalized(els.tagSearch.value);
  els.tagList.querySelectorAll('.tag-chip').forEach(button => {
    button.hidden = Boolean(query && !normalized(button.dataset.tagLabel).includes(query));
  });
  applyFilters();
}

function applyFilters() {
  const query = normalized(els.search.value);
  const tagQuery = normalized(els.tagSearch.value);
  const selected = [...state.selectedTags];
  const requireAll = els.tagMode.value === 'all';
  const sort = els.sort.value;

  state.filtered = state.games.filter(game => {
    if (state.favoritesOnly && !state.favorites.has(game.id)) return false;

    if (selected.length) {
      const match = requireAll
        ? selected.every(tag => game.__tagKeySet.has(tag))
        : selected.some(tag => game.__tagKeySet.has(tag));
      if (!match) return false;
    }

    if (tagQuery && !game.__tagKeys.some(tag => tag.includes(tagQuery))) return false;
    if (query && !game.__searchText.includes(query)) return false;
    return true;
  });

  state.filtered.sort((a, b) => {
    if (sort === 'date_asc') return gameDate(a) - gameDate(b);
    if (sort === 'name_asc') return a.title.localeCompare(b.title, 'fr', { sensitivity:'base' });
    if (sort === 'name_desc') return b.title.localeCompare(a.title, 'fr', { sensitivity:'base' });
    return gameDate(b) - gameDate(a);
  });

  state.visible = Math.min(PAGE_SIZE, state.filtered.length);
  state.loadingMore = false;
  renderCatalog();
  armInfiniteObserver();
}

function pill(text) { const el = document.createElement('span'); el.className = 'genre-pill'; el.textContent = text; return el; }

function toggleFavorite(gameId) {
  state.favorites.has(gameId) ? state.favorites.delete(gameId) : state.favorites.add(gameId);
  saveFavorites();
  if (state.favoritesOnly) applyFilters(); else renderCatalog();
  renderRecommendations();
}

function renderCard(game, compact = false) {
  const card = els.template.content.firstElementChild.cloneNode(true);
  const image = card.querySelector('.cover');
  const open = card.querySelector('.card-open');
  const favorite = card.querySelector('.favorite-btn');
  card.dataset.gameId = game.id;
  if (compact) card.classList.add('compact-card');
  card.querySelector('.card-title').textContent = game.title;
  card.querySelector('.card-date').textContent = formatDate(game.post_date);
  card.querySelector('.card-size').textContent = game.repack_size !== 'N/A' ? (game.repack_size || '') : '';
  if (game.image_url) {
    image.fetchPriority = 'low';
    image.src = game.image_url;
    image.alt = `Illustration de ${game.title}`;
    image.addEventListener('error', () => { image.style.display = 'none'; }, { once:true });
  } else image.style.display = 'none';
  card.querySelector('.new-badge').hidden = !isNew(game);
  for (const tag of getTags(game).slice(0, 3)) card.querySelector('.genre-row').append(pill(tag));
  const active = state.favorites.has(game.id);
  favorite.classList.toggle('active', active); favorite.textContent = active ? '♥' : '♡';
  favorite.setAttribute('aria-label', active ? 'Retirer des favoris' : 'Ajouter aux favoris');
  favorite.addEventListener('click', event => { event.stopPropagation(); toggleFavorite(game.id); });
  open.addEventListener('click', () => openDialog(game));
  return card;
}

function updateCatalogMeta() {
  const resultLabel = `${state.filtered.length.toLocaleString('fr-FR')} jeu${state.filtered.length > 1 ? 'x' : ''}`;
  els.count.textContent = state.filtered.length.toLocaleString('fr-FR');
  if (els.tagResultCount) els.tagResultCount.textContent = resultLabel;
  els.empty.hidden = state.filtered.length !== 0;

  const hasMore = state.visible < state.filtered.length;
  els.scrollSentinel.hidden = !hasMore;
  if (!hasMore) els.infiniteStatus.hidden = true;

  const active = [];
  if (els.search.value.trim()) active.push(`recherche « ${els.search.value.trim()} »`);
  if (els.tagSearch.value.trim()) active.push(`tag recherché « ${els.tagSearch.value.trim()} »`);
  if (state.selectedTags.size) active.push(`${state.selectedTags.size} tag${state.selectedTags.size > 1 ? 's' : ''} (${els.tagMode.value === 'all' ? 'tous' : 'au moins un'})`);
  if (state.favoritesOnly) active.push('favoris');
  els.activeState.hidden = active.length === 0;
  els.activeState.textContent = active.length ? `Filtres actifs : ${active.join(' • ')} • ${resultLabel}` : '';
  els.favoritesToggle.classList.toggle('active', state.favoritesOnly);
  els.favoritesToggle.setAttribute('aria-pressed', String(state.favoritesOnly));
  els.favoritesToggle.textContent = state.favoritesOnly ? '♥ Favoris' : '♡ Favoris';
}

function renderCatalog({ append = false, start = 0 } = {}) {
  const end = Math.min(state.visible, state.filtered.length);
  const fragment = document.createDocumentFragment();
  for (let index = start; index < end; index += 1) fragment.append(renderCard(state.filtered[index]));
  if (append) els.grid.append(fragment);
  else els.grid.replaceChildren(fragment);
  updateCatalogMeta();
}

function loadNextPage() {
  if (state.loadingMore || state.visible >= state.filtered.length) return;
  const now = performance.now();
  if (now - state.lastLoadAt < LOAD_COOLDOWN_MS) return;

  state.loadingMore = true;
  state.lastLoadAt = now;
  infiniteObserver.unobserve(els.scrollSentinel);
  els.infiniteStatus.hidden = false;
  const start = state.visible;

  requestAnimationFrame(() => {
    state.visible = Math.min(state.visible + PAGE_SIZE, state.filtered.length);
    renderCatalog({ append:true, start });
    els.infiniteStatus.hidden = true;

    window.setTimeout(() => {
      state.loadingMore = false;
      armInfiniteObserver();
    }, LOAD_COOLDOWN_MS);
  });
}

function scheduleInfiniteCheck() {
  // Kept as a compatibility hook for resize/tests. It never loads a page itself.
  // The previous implementation called loadNextPage recursively here and could
  // cascade dozens of renders while the sentinel remained near the viewport.
  armInfiniteObserver();
}

const infiniteObserver = new IntersectionObserver(entries => {
  const entry = entries.find(item => item.target === els.scrollSentinel);
  if (entry?.isIntersecting) loadNextPage();
}, { root:null, rootMargin:'350px 0px', threshold:0.01 });

function armInfiniteObserver() {
  infiniteObserver.unobserve(els.scrollSentinel);
  if (state.loadingMore || els.scrollSentinel.hidden) return;
  requestAnimationFrame(() => {
    if (!state.loadingMore && !els.scrollSentinel.hidden) infiniteObserver.observe(els.scrollSentinel);
  });
}

infiniteObserver.observe(els.scrollSentinel);

function recommendationScores() {
  const favorites = state.games.filter(game => state.favorites.has(game.id));
  if (!favorites.length) return [];

  const profile = new Map();
  for (const game of favorites) {
    for (const tag of new Set(getTags(game).map(normalized))) profile.set(tag, (profile.get(tag) || 0) + 1);
  }
  const total = Math.max(1, state.games.length);
  const now = Date.now();
  const scored = [];
  for (const game of state.games) {
    if (state.favorites.has(game.id)) continue;
    const tags = new Set(getTags(game).map(normalized));
    let score = 0; let shared = 0;
    for (const tag of tags) {
      const interest = profile.get(tag) || 0;
      if (!interest) continue;
      const frequency = state.tagCounts.get(tag) || 1;
      const rarity = Math.log((total + 1) / (frequency + 1)) + 1;
      score += interest * rarity; shared += 1;
    }
    if (!shared) continue;
    const ageDays = Math.max(0, (now - gameDate(game)) / 86400000);
    const freshness = Math.max(0, 1 - ageDays / 730) * 0.35;
    score = score / Math.sqrt(Math.max(1, tags.size)) + freshness;
    scored.push({ game, score, shared });
  }
  return scored.sort((a, b) => b.score - a.score || b.shared - a.shared || gameDate(b.game) - gameDate(a.game));
}

function renderRecommendations() {
  const favoriteCount = state.games.reduce((count, game) => count + Number(state.favorites.has(game.id)), 0);
  if (!favoriteCount) {
    els.recommendationSection.hidden = true; els.recommendationGrid.replaceChildren(); return;
  }
  const picks = recommendationScores().slice(0, RECOMMENDATION_LIMIT);
  if (!picks.length) {
    els.recommendationSection.hidden = true; els.recommendationGrid.replaceChildren(); return;
  }
  const fragment = document.createDocumentFragment();
  for (const item of picks) fragment.append(renderCard(item.game, true));
  els.recommendationGrid.replaceChildren(fragment);
  els.recommendationMeta.textContent = `Basé sur ${favoriteCount} favori${favoriteCount > 1 ? 's' : ''} et les tags que tu préfères. Rien n'est envoyé à un serveur.`;
  els.recommendationSection.hidden = false;
}

function appendMediaGallery(info, game) {
  const media = getMedia(game);
  if (!media.length) return;
  const section = document.createElement('section'); section.className = 'dialog-media';
  const heading = document.createElement('div'); heading.className = 'dialog-subheading';
  const title = document.createElement('h3'); title.textContent = 'Images & GIFs';
  const count = document.createElement('span'); count.textContent = `${media.length} média${media.length > 1 ? 's' : ''}`;
  heading.append(title, count); section.append(heading);
  const grid = document.createElement('div'); grid.className = 'media-grid';
  for (const item of media) {
    const link = document.createElement('a'); link.className = 'media-item'; link.href = item.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
    const img = document.createElement('img'); img.src = item.url; img.alt = `Capture de ${game.title}`; img.loading = 'lazy'; img.decoding = 'async'; img.referrerPolicy = 'no-referrer';
    img.addEventListener('error', () => link.remove(), { once:true }); link.append(img);
    if (item.type === 'gif') { const badge = document.createElement('span'); badge.className = 'media-kind'; badge.textContent = 'GIF'; link.append(badge); }
    grid.append(link);
  }
  section.append(grid); info.append(section);
}

function lockCatalogScroll() {
  state.dialogScrollY = window.scrollY;
  const scrollbarGap = Math.max(0, window.innerWidth - document.documentElement.clientWidth);
  document.documentElement.classList.add('dialog-scroll-locked');
  document.body.classList.add('dialog-scroll-locked');
  document.body.style.position = 'fixed';
  document.body.style.top = `-${state.dialogScrollY}px`;
  document.body.style.left = '0';
  document.body.style.right = '0';
  document.body.style.width = '100%';
  if (scrollbarGap) document.body.style.paddingRight = `${scrollbarGap}px`;
}

function unlockCatalogScroll() {
  const top = state.dialogScrollY;
  document.documentElement.classList.remove('dialog-scroll-locked');
  document.body.classList.remove('dialog-scroll-locked');
  document.body.style.position = '';
  document.body.style.top = '';
  document.body.style.left = '';
  document.body.style.right = '';
  document.body.style.width = '';
  document.body.style.paddingRight = '';
  window.scrollTo({ top, left:0, behavior:'auto' });
}

function openDialog(game) {
  const firstOpen = !els.dialog.open;
  if (firstOpen) {
    state.dialogOpener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    lockCatalogScroll();
  }
  state.dialogGameId = game.id;

  const layout = document.createElement('div'); layout.className = 'dialog-layout';
  const cover = document.createElement('div'); cover.className = 'dialog-cover';
  if (game.image_url) {
    const img = document.createElement('img'); img.src = game.image_url; img.alt = ''; img.referrerPolicy = 'no-referrer';
    img.addEventListener('error', () => img.remove(), { once:true }); cover.append(img);
  }

  const info = document.createElement('div'); info.className = 'dialog-info';
  const title = document.createElement('h2'); title.textContent = game.title; info.append(title);
  const meta = document.createElement('div'); meta.className = 'dialog-meta';
  const date = document.createElement('span'); date.textContent = formatDate(game.post_date); meta.append(date);
  if (game.repack_size && game.repack_size !== 'N/A') { const size = document.createElement('span'); size.textContent = `Taille : ${game.repack_size}`; meta.append(size); }
  info.append(meta);

  const tags = getTags(game);
  if (tags.length) { const box = document.createElement('div'); box.className = 'dialog-genres'; tags.forEach(tag => box.append(pill(tag))); info.append(box); }

  const source = game.source_url || game.post_url || '';
  if (source) { const link = document.createElement('a'); link.className = 'source-link'; link.href = source; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = 'Voir la page source ↗'; info.append(link); }
  appendMediaGallery(info, game);
  const note = document.createElement('p'); note.className = 'dialog-note'; note.textContent = 'FitBoyRepack indexe les métadonnées et médias publics utiles au catalogue puis renvoie vers la page source.'; info.append(note);

  layout.append(cover, info);
  els.dialogContent.replaceChildren(layout);
  if (firstOpen) els.dialog.showModal();
}

function isMediaLightboxOpen() {
  const box = els.dialog.querySelector('.media-lightbox');
  return Boolean(box && !box.hidden);
}

function navigateDialog(delta) {
  if (!els.dialog.open || isMediaLightboxOpen() || state.filtered.length < 2) return;
  const current = state.filtered.findIndex(game => game.id === state.dialogGameId);
  if (current < 0) return;
  const next = (current + delta + state.filtered.length) % state.filtered.length;
  openDialog(state.filtered[next]);
}

function restoreCatalogPosition() {
  const opener = state.dialogOpener;
  state.dialogGameId = null;
  state.dialogOpener = null;
  unlockCatalogScroll();
  requestAnimationFrame(() => {
    if (opener?.isConnected) {
      try { opener.focus({ preventScroll:true }); } catch { /* noop */ }
    }
  });
}

async function loadCatalog() {
  try {
    const response = await fetch(DATA_URL, { cache:'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const source = Array.isArray(payload) ? payload : payload.games || [];
    state.games = source.filter(game => game?.id && game?.title).map(prepareGame);
    const generated = Array.isArray(payload) ? null : payload.generated_at;
    els.status.textContent = generated ? `Mis à jour ${new Intl.DateTimeFormat('fr-FR', { dateStyle:'medium', timeStyle:'short' }).format(new Date(generated))}` : `${state.games.length.toLocaleString('fr-FR')} jeux`;
    buildTagIndex(); applyFilters(); renderRecommendations();
  } catch (error) {
    console.error(error); els.status.textContent = 'Catalogue indisponible'; els.empty.hidden = false;
    els.empty.querySelector('strong').textContent = 'Impossible de charger le catalogue';
    els.empty.querySelector('span').textContent = 'Le robot de données doit être relancé.';
  }
}

let searchTimer;
els.search.addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(applyFilters, 100); });
els.tagSearch.addEventListener('input', filterVisibleTags);
els.tagMode.addEventListener('change', applyFilters);
els.clearTags.addEventListener('click', () => {
  state.selectedTags.clear();
  els.tagSearch.value = '';
  filterVisibleTags();
  updateTagUI();
});
els.sort.addEventListener('change', applyFilters);
els.favoritesToggle.addEventListener('click', () => { state.favoritesOnly = !state.favoritesOnly; applyFilters(); });
els.dialog.addEventListener('click', event => { if (event.target === els.dialog || event.target.closest('[data-close-dialog]')) els.dialog.close(); });
els.dialog.addEventListener('close', restoreCatalogPosition);

document.addEventListener('pointerdown', event => {
  if (els.tagFilter.open && !els.tagFilter.contains(event.target)) els.tagFilter.open = false;
});

document.addEventListener('keydown', event => {
  const activeTag = document.activeElement?.tagName;
  const typing = activeTag === 'INPUT' || activeTag === 'TEXTAREA' || activeTag === 'SELECT';

  if (els.dialog.open && !typing && !isMediaLightboxOpen()) {
    if (event.key === 'ArrowLeft') { event.preventDefault(); navigateDialog(-1); return; }
    if (event.key === 'ArrowRight') { event.preventDefault(); navigateDialog(1); return; }
  }

  if (event.key === '/' && !typing) { event.preventDefault(); els.search.focus(); }
  if (event.key === 'Escape' && els.tagFilter.open) els.tagFilter.open = false;
});

window.addEventListener('resize', scheduleInfiniteCheck, { passive:true });
loadCatalog();
