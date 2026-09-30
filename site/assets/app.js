const DATA_URL = './data/games.json';
const PAGE_SIZE = 60;
const RECOMMENDATION_LIMIT = 12;
const FAVORITES_KEY = 'fitboyrepack:favorites:v1';

const $ = (selector) => document.querySelector(selector);
const els = {
  grid: $('#gameGrid'), template: $('#cardTemplate'), search: $('#searchInput'), sort: $('#sortControl'),
  count: $('#visibleCount'), status: $('#catalogStatus'), loadMore: $('#loadMore'), empty: $('#emptyState'),
  favoritesToggle: $('#favoritesToggle'), activeState: $('#activeState'), dialog: $('#gameDialog'),
  dialogContent: $('#dialogContent'), tagFilter: $('#tagFilter'), tagList: $('#tagList'), tagSearch: $('#tagSearch'),
  tagMode: $('#tagMode'), clearTags: $('#clearTags'), selectedTagCount: $('#selectedTagCount'),
  recommendationSection: $('#recommendationSection'), recommendationGrid: $('#recommendationGrid'),
  recommendationMeta: $('#recommendationMeta')
};

const state = {
  games: [], filtered: [], visible: PAGE_SIZE, favoritesOnly: false,
  favorites: readFavorites(), selectedTags: new Set(), tagCounts: new Map()
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
}

function applyFilters() {
  const query = normalized(els.search.value);
  const selected = [...state.selectedTags];
  const requireAll = els.tagMode.value === 'all';
  const sort = els.sort.value;

  state.filtered = state.games.filter(game => {
    if (state.favoritesOnly && !state.favorites.has(game.id)) return false;
    const tags = getTags(game); const tagKeys = new Set(tags.map(normalized));
    if (selected.length) {
      const match = requireAll ? selected.every(tag => tagKeys.has(tag)) : selected.some(tag => tagKeys.has(tag));
      if (!match) return false;
    }
    if (!query) return true;
    return normalized([game.title, game.repack_size, ...tags].join(' ')).includes(query);
  });

  state.filtered.sort((a, b) => {
    if (sort === 'date_asc') return gameDate(a) - gameDate(b);
    if (sort === 'name_asc') return a.title.localeCompare(b.title, 'fr', { sensitivity:'base' });
    if (sort === 'name_desc') return b.title.localeCompare(a.title, 'fr', { sensitivity:'base' });
    return gameDate(b) - gameDate(a);
  });
  state.visible = PAGE_SIZE;
  renderCatalog();
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
  const image = card.querySelector('.cover'); const open = card.querySelector('.card-open'); const favorite = card.querySelector('.favorite-btn');
  card.dataset.gameId = game.id; if (compact) card.classList.add('compact-card');
  card.querySelector('.card-title').textContent = game.title;
  card.querySelector('.card-date').textContent = formatDate(game.post_date);
  card.querySelector('.card-size').textContent = game.repack_size !== 'N/A' ? (game.repack_size || '') : '';
  if (game.image_url) {
    image.src = game.image_url; image.alt = `Illustration de ${game.title}`;
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

function renderCatalog() {
  const shown = state.filtered.slice(0, state.visible); const fragment = document.createDocumentFragment();
  for (const game of shown) fragment.append(renderCard(game));
  els.grid.replaceChildren(fragment);
  els.count.textContent = state.filtered.length.toLocaleString('fr-FR');
  els.empty.hidden = state.filtered.length !== 0;
  els.loadMore.hidden = state.visible >= state.filtered.length;

  const active = [];
  if (els.search.value.trim()) active.push(`recherche « ${els.search.value.trim()} »`);
  if (state.selectedTags.size) active.push(`${state.selectedTags.size} tag${state.selectedTags.size > 1 ? 's' : ''} (${els.tagMode.value === 'all' ? 'tous' : 'au moins un'})`);
  if (state.favoritesOnly) active.push('favoris');
  els.activeState.hidden = active.length === 0;
  els.activeState.textContent = active.length ? `Filtres actifs : ${active.join(' • ')}` : '';
  els.favoritesToggle.classList.toggle('active', state.favoritesOnly);
  els.favoritesToggle.setAttribute('aria-pressed', String(state.favoritesOnly));
  els.favoritesToggle.textContent = state.favoritesOnly ? '♥ Favoris' : '♡ Favoris';
}

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

function openDialog(game) {
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

  layout.append(cover, info); els.dialogContent.replaceChildren(layout); els.dialog.showModal();
}

async function loadCatalog() {
  try {
    const response = await fetch(DATA_URL, { cache:'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.games = (Array.isArray(payload) ? payload : payload.games || []).filter(game => game?.id && game?.title).map(game => ({ ...game, id:String(game.id) }));
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
els.clearTags.addEventListener('click', () => { state.selectedTags.clear(); updateTagUI(); applyFilters(); });
els.sort.addEventListener('change', applyFilters);
els.loadMore.addEventListener('click', () => { state.visible += PAGE_SIZE; renderCatalog(); });
els.favoritesToggle.addEventListener('click', () => { state.favoritesOnly = !state.favoritesOnly; applyFilters(); });
els.dialog.addEventListener('click', event => { if (event.target === els.dialog || event.target.closest('[data-close-dialog]')) els.dialog.close(); });
document.addEventListener('keydown', event => {
  if (event.key === '/' && document.activeElement?.tagName !== 'INPUT') { event.preventDefault(); els.search.focus(); }
  if (event.key === 'Escape' && els.tagFilter.open) els.tagFilter.open = false;
});
loadCatalog();
