import { loadCatalogPayload } from './catalog-api.js';

const PAGE_SIZE = 30;
const DISCOVERY_LIMIT = 12;
const FAVORITES_KEY = 'fitboyrepack:favorites:v1';
const LOAD_COOLDOWN_MS = 250;
const SEARCH_DEBOUNCE_MS = 80;
const TITLE_STOPWORDS = new Set(['the','a','an','of','and','or','in','on','for','with','to','edition','complete','deluxe','ultimate','remastered','remaster','game','pack']);

const $ = selector => document.querySelector(selector);
const els = {
  grid: $('#gameGrid'), template: $('#cardTemplate'), search: $('#searchInput'), suggestions: $('#searchSuggestions'), sort: $('#sortControl'),
  count: $('#visibleCount'), status: $('#catalogStatus'), empty: $('#emptyState'), favoritesToggle: $('#favoritesToggle'), activeState: $('#activeState'),
  dialog: $('#gameDialog'), dialogContent: $('#dialogContent'), tagFilter: $('#tagFilter'), tagList: $('#tagList'), tagSearch: $('#tagSearch'),
  tagMode: $('#tagMode'), clearTags: $('#clearTags'), selectedTagCount: $('#selectedTagCount'), tagResultCount: $('#tagResultCount'),
  yearFilter: $('#yearFilter'), sizeFilter: $('#sizeFilter'), newOnlyFilter: $('#newOnlyFilter'), mediaOnlyFilter: $('#mediaOnlyFilter'),
  descriptionOnlyFilter: $('#descriptionOnlyFilter'), resetFilters: $('#resetFilters'), filterSidebar: $('#filterSidebar'), filterDrawerToggle: $('#filterDrawerToggle'),
  filterDrawerClose: $('#filterDrawerClose'), recommendationSection: $('#recommendationSection'), recommendationGrid: $('#recommendationGrid'),
  recommendationMeta: $('#recommendationMeta'), newSection: $('#newSection'), newGrid: $('#newGrid'), newMeta: $('#newMeta'), recentSection: $('#recentSection'),
  recentGrid: $('#recentGrid'), recentMeta: $('#recentMeta'), favoritesSection: $('#favoritesSection'), favoritesGrid: $('#favoritesGrid'), favoritesMeta: $('#favoritesMeta'),
  scrollSentinel: $('#scrollSentinel'), infiniteStatus: $('#infiniteStatus')
};

const state = {
  games: [], filtered: [], visible: PAGE_SIZE, favoritesOnly: false,
  favorites: readFavorites(), selectedTags: new Set(), tagCounts: new Map(),
  dialogGameId: null, dialogScrollY: 0, dialogOpener: null,
  loadingMore: false, lastLoadAt: 0, suggestionIndex: -1
};

function readFavorites() {
  try { return new Set(JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]').map(String)); }
  catch { return new Set(); }
}

function saveFavorites() {
  localStorage.setItem(FAVORITES_KEY, JSON.stringify([...state.favorites]));
}

function normalized(value = '') {
  return String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

function gameDate(game) {
  const time = Date.parse(game.post_date || '');
  return Number.isFinite(time) ? time : 0;
}

function updatedDate(game) {
  const time = Date.parse(game.updated_at || game.post_date || '');
  return Number.isFinite(time) ? time : 0;
}

function gameYear(game) {
  const time = gameDate(game);
  return time ? new Date(time).getUTCFullYear() : 0;
}

function formatDate(value) {
  const time = Date.parse(value || '');
  return Number.isFinite(time)
    ? new Intl.DateTimeFormat('fr-FR', { day:'2-digit', month:'short', year:'numeric' }).format(time)
    : 'Date inconnue';
}

function isNew(game) {
  const time = gameDate(game);
  return Boolean(time && Date.now() - time < 14 * 86400000);
}

function getTags(game) {
  const value = game.genres ?? game.genre ?? [];
  const raw = Array.isArray(value) ? value : String(value || '').split(',');
  return raw.map(item => String(item).trim()).filter(Boolean);
}

function parseSizeGiB(value = '') {
  const text = String(value).replace(',', '.');
  const matches = [...text.matchAll(/(\d+(?:\.\d+)?)\s*(TB|TiB|GB|GiB|MB|MiB)/gi)];
  if (!matches.length) return null;
  const match = matches[matches.length - 1];
  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) return null;
  const unit = match[2].toLowerCase();
  if (unit.startsWith('t')) return amount * 1024;
  if (unit.startsWith('m')) return amount / 1024;
  return amount;
}

function titleTokens(title = '') {
  return normalized(title)
    .replace(/[^a-z0-9]+/g, ' ')
    .split(/\s+/)
    .filter(token => token.length > 2 && !TITLE_STOPWORDS.has(token));
}

function withinOneEdit(a, b) {
  if (a === b) return true;
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0; let j = 0; let edits = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i += 1; j += 1; continue; }
    edits += 1;
    if (edits > 1) return false;
    if (a.length > b.length) i += 1;
    else if (b.length > a.length) j += 1;
    else { i += 1; j += 1; }
  }
  if (i < a.length || j < b.length) edits += 1;
  return edits <= 1;
}

function prepareGame(raw) {
  const game = { ...raw, id:String(raw.id) };
  const tags = getTags(game);
  game.__tagKeys = tags.map(normalized);
  game.__tagKeySet = new Set(game.__tagKeys);
  game.__titleText = normalized(game.title);
  game.__titleTokens = titleTokens(game.title);
  game.__searchText = normalized([game.title, game.repack_size, ...tags].join(' '));
  game.__searchWords = game.__searchText.replace(/[^a-z0-9]+/g, ' ').split(/\s+/).filter(Boolean);
  game.__sizeGiB = parseSizeGiB(game.repack_size);
  game.__year = gameYear(game);
  return game;
}

function fuzzyTokenMatch(game, token) {
  if (game.__searchText.includes(token)) return true;
  if (token.length < 4) return false;
  return game.__searchWords.some(word => word.length > 2 && withinOneEdit(token, word));
}

function matchesSearch(game, rawQuery) {
  const query = normalized(rawQuery);
  if (!query) return true;
  if (game.__searchText.includes(query)) return true;
  const tokens = query.replace(/[^a-z0-9]+/g, ' ').split(/\s+/).filter(Boolean);
  return tokens.length > 0 && tokens.every(token => fuzzyTokenMatch(game, token));
}

function matchesSize(game, mode) {
  if (!mode) return true;
  const size = game.__sizeGiB;
  if (size === null) return false;
  if (mode === 'lt5') return size < 5;
  if (mode === '5-20') return size >= 5 && size < 20;
  if (mode === '20-50') return size >= 20 && size < 50;
  if (mode === '50-100') return size >= 50 && size < 100;
  if (mode === 'gte100') return size >= 100;
  return true;
}

function populateYears() {
  const years = [...new Set(state.games.map(game => game.__year).filter(Boolean))].sort((a, b) => b - a);
  const fragment = document.createDocumentFragment();
  for (const year of years) {
    const option = document.createElement('option');
    option.value = String(year);
    option.textContent = String(year);
    fragment.append(option);
  }
  els.yearFilter.append(fragment);
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
    .map(([key, label]) => ({ key, label, count:counts.get(key) || 0 }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'fr', { sensitivity:'base' }));

  const fragment = document.createDocumentFragment();
  for (const tag of tags) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'tag-chip';
    button.dataset.tagKey = tag.key;
    button.dataset.tagLabel = tag.label;
    const label = document.createElement('span'); label.textContent = tag.label;
    const count = document.createElement('small'); count.textContent = tag.count.toLocaleString('fr-FR');
    button.append(label, count);
    button.addEventListener('click', () => {
      state.selectedTags.has(tag.key) ? state.selectedTags.delete(tag.key) : state.selectedTags.add(tag.key);
      updateTagUI();
      applyFilters();
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
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
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
  const query = els.search.value;
  const tagQuery = normalized(els.tagSearch.value);
  const selected = [...state.selectedTags];
  const sort = els.sort.value;
  const year = Number(els.yearFilter.value || 0);
  const sizeMode = els.sizeFilter.value;

  state.filtered = state.games.filter(game => {
    if (state.favoritesOnly && !state.favorites.has(game.id)) return false;
    if (selected.length && !selected.every(tag => game.__tagKeySet.has(tag))) return false;
    if (tagQuery && !game.__tagKeys.some(tag => tag.includes(tagQuery))) return false;
    if (!matchesSearch(game, query)) return false;
    if (year && game.__year !== year) return false;
    if (!matchesSize(game, sizeMode)) return false;
    if (els.newOnlyFilter.checked && !isNew(game)) return false;
    if (els.mediaOnlyFilter.checked && !(Number(game.media_count) > 0)) return false;
    if (els.descriptionOnlyFilter.checked && !game.has_description) return false;
    return true;
  });

  state.filtered.sort((a, b) => {
    if (sort === 'updated_desc') return updatedDate(b) - updatedDate(a) || gameDate(b) - gameDate(a);
    if (sort === 'date_asc') return gameDate(a) - gameDate(b);
    if (sort === 'name_asc') return a.title.localeCompare(b.title, 'fr', { sensitivity:'base' });
    if (sort === 'name_desc') return b.title.localeCompare(a.title, 'fr', { sensitivity:'base' });
    return gameDate(b) - gameDate(a);
  });

  state.visible = Math.min(PAGE_SIZE, state.filtered.length);
  state.loadingMore = false;
  renderCatalog();
  armInfiniteObserver();
  renderSearchSuggestions();
}

function pill(text) {
  const el = document.createElement('span');
  el.className = 'genre-pill';
  el.textContent = text;
  return el;
}

function toggleFavorite(gameId) {
  state.favorites.has(gameId) ? state.favorites.delete(gameId) : state.favorites.add(gameId);
  saveFavorites();
  if (state.favoritesOnly) applyFilters(); else renderCatalog();
  renderDiscovery();
  document.dispatchEvent(new CustomEvent('fitboy:profile-change', { detail:{ source:'favorites' } }));
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
  favorite.classList.toggle('active', active);
  favorite.textContent = active ? '♥' : '♡';
  favorite.setAttribute('aria-label', active ? 'Retirer des favoris' : 'Ajouter aux favoris');
  favorite.addEventListener('click', event => { event.stopPropagation(); toggleFavorite(game.id); });
  open.addEventListener('click', () => openDialog(game, { syncUrl:true }));
  return card;
}

function updateCatalogMeta() {
  const resultLabel = `${state.filtered.length.toLocaleString('fr-FR')} jeu${state.filtered.length > 1 ? 'x' : ''}`;
  els.count.textContent = state.filtered.length.toLocaleString('fr-FR');
  els.tagResultCount.textContent = resultLabel;
  els.empty.hidden = state.filtered.length !== 0;

  const hasMore = state.visible < state.filtered.length;
  els.scrollSentinel.hidden = !hasMore;
  if (!hasMore) els.infiniteStatus.hidden = true;

  const active = [];
  if (els.search.value.trim()) active.push(`recherche « ${els.search.value.trim()} »`);
  if (els.tagSearch.value.trim()) active.push(`tag « ${els.tagSearch.value.trim()} »`);
  if (state.selectedTags.size) active.push(`${state.selectedTags.size} tag${state.selectedTags.size > 1 ? 's' : ''}`);
  if (els.yearFilter.value) active.push(`année ${els.yearFilter.value}`);
  if (els.sizeFilter.value) active.push(`taille ${els.sizeFilter.options[els.sizeFilter.selectedIndex]?.textContent || ''}`);
  if (els.newOnlyFilter.checked) active.push('nouveautés');
  if (els.mediaOnlyFilter.checked) active.push('avec médias');
  if (els.descriptionOnlyFilter.checked) active.push('avec description');
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

function titleProfile(favorites) {
  const profile = new Map();
  for (const game of favorites) {
    for (const token of new Set(game.__titleTokens)) profile.set(token, (profile.get(token) || 0) + 1);
  }
  return profile;
}

function recommendationScores() {
  const favorites = state.games.filter(game => state.favorites.has(game.id));
  if (!favorites.length) return [];

  const tagProfile = new Map();
  for (const game of favorites) {
    for (const tag of new Set(game.__tagKeys)) tagProfile.set(tag, (tagProfile.get(tag) || 0) + 1);
  }
  const nameProfile = titleProfile(favorites);
  const favoriteYears = favorites.map(game => game.__year).filter(Boolean);
  const averageYear = favoriteYears.length ? favoriteYears.reduce((sum, year) => sum + year, 0) / favoriteYears.length : 0;
  const total = Math.max(1, state.games.length);
  const now = Date.now();
  const scored = [];

  for (const game of state.games) {
    if (state.favorites.has(game.id)) continue;
    const tags = new Set(game.__tagKeys);
    let score = 0; let shared = 0;
    for (const tag of tags) {
      const interest = tagProfile.get(tag) || 0;
      if (!interest) continue;
      const frequency = state.tagCounts.get(tag) || 1;
      const rarity = Math.log((total + 1) / (frequency + 1)) + 1;
      score += interest * rarity;
      shared += 1;
    }

    let sharedTitle = 0;
    for (const token of new Set(game.__titleTokens)) {
      const weight = nameProfile.get(token) || 0;
      if (!weight) continue;
      sharedTitle += 1;
      score += weight * 0.85;
    }

    if (!shared && !sharedTitle) continue;
    if (averageYear && game.__year) {
      const distance = Math.abs(game.__year - averageYear);
      score += Math.max(0, 0.55 - distance * 0.07);
    }
    const ageDays = Math.max(0, (now - gameDate(game)) / 86400000);
    score += Math.max(0, 1 - ageDays / 730) * 0.35;
    score /= Math.sqrt(Math.max(1, tags.size));
    scored.push({ game, score, shared:shared + sharedTitle });
  }

  return scored.sort((a, b) => b.score - a.score || b.shared - a.shared || gameDate(b.game) - gameDate(a.game));
}

function renderDiscoverySection(section, grid, items, meta, text) {
  if (!items.length) {
    section.hidden = true;
    grid.replaceChildren();
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const game of items.slice(0, DISCOVERY_LIMIT)) fragment.append(renderCard(game, true));
  grid.replaceChildren(fragment);
  if (meta) meta.textContent = text;
  section.hidden = false;
}

function renderDiscovery() {
  const newest = state.games.filter(isNew).sort((a, b) => gameDate(b) - gameDate(a));
  renderDiscoverySection(els.newSection, els.newGrid, newest, els.newMeta, `${newest.length} sortie${newest.length > 1 ? 's' : ''} sur les 14 derniers jours.`);

  const recentlyUpdated = state.games
    .filter(game => game.details_ready || Number(game.media_count) > 0)
    .slice()
    .sort((a, b) => updatedDate(b) - updatedDate(a) || gameDate(b) - gameDate(a));
  renderDiscoverySection(els.recentSection, els.recentGrid, recentlyUpdated, els.recentMeta, 'Fiches enrichies le plus récemment par les robots.');

  const favoriteGames = state.games.filter(game => state.favorites.has(game.id)).sort((a, b) => gameDate(b) - gameDate(a));
  renderDiscoverySection(els.favoritesSection, els.favoritesGrid, favoriteGames, els.favoritesMeta, `${favoriteGames.length} favori${favoriteGames.length > 1 ? 's' : ''} stocké${favoriteGames.length > 1 ? 's' : ''} localement.`);

  const recommendations = recommendationScores().map(item => item.game);
  renderDiscoverySection(
    els.recommendationSection,
    els.recommendationGrid,
    recommendations,
    els.recommendationMeta,
    favoriteGames.length ? `Tags, rareté, titres proches, époque et fraîcheur calculés localement à partir de ${favoriteGames.length} favori${favoriteGames.length > 1 ? 's' : ''}.` : ''
  );
}

function suggestionScore(game, query) {
  const q = normalized(query);
  if (!q) return 0;
  if (game.__titleText === q) return 120;
  if (game.__titleText.startsWith(q)) return 100;
  if (game.__titleText.includes(q)) return 80;
  if (game.__tagKeys.some(tag => tag === q)) return 70;
  if (game.__tagKeys.some(tag => tag.includes(q))) return 55;
  const tokens = q.split(/\s+/).filter(Boolean);
  if (tokens.every(token => fuzzyTokenMatch(game, token))) return 35;
  return 0;
}

function searchSuggestionGames() {
  const query = els.search.value.trim();
  if (normalized(query).length < 2) return [];
  return state.games
    .map(game => ({ game, score:suggestionScore(game, query) }))
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score || gameDate(b.game) - gameDate(a.game))
    .slice(0, 7)
    .map(item => item.game);
}

function renderSearchSuggestions() {
  const games = searchSuggestionGames();
  state.suggestionIndex = -1;
  if (!games.length || document.activeElement !== els.search) {
    els.suggestions.hidden = true;
    els.suggestions.replaceChildren();
    return;
  }

  const fragment = document.createDocumentFragment();
  games.forEach((game, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'search-suggestion';
    button.dataset.index = String(index);
    button.setAttribute('role', 'option');
    const title = document.createElement('strong'); title.textContent = game.title;
    const meta = document.createElement('span');
    meta.textContent = [game.__year || '', getTags(game).slice(0, 2).join(' · ')].filter(Boolean).join(' · ');
    button.append(title, meta);
    button.addEventListener('mousedown', event => event.preventDefault());
    button.addEventListener('click', () => {
      els.suggestions.hidden = true;
      openDialog(game, { syncUrl:true });
    });
    fragment.append(button);
  });
  els.suggestions.replaceChildren(fragment);
  els.suggestions.hidden = false;
}

function moveSuggestion(delta) {
  const buttons = [...els.suggestions.querySelectorAll('.search-suggestion')];
  if (!buttons.length || els.suggestions.hidden) return false;
  state.suggestionIndex = (state.suggestionIndex + delta + buttons.length) % buttons.length;
  buttons.forEach((button, index) => button.classList.toggle('active', index === state.suggestionIndex));
  buttons[state.suggestionIndex].scrollIntoView({ block:'nearest' });
  return true;
}

function activateSuggestion() {
  if (state.suggestionIndex < 0) return false;
  const button = els.suggestions.querySelector(`.search-suggestion[data-index="${state.suggestionIndex}"]`);
  if (!button) return false;
  button.click();
  return true;
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

function gameHashId() {
  if (!window.location.hash.startsWith('#')) return '';
  return new URLSearchParams(window.location.hash.slice(1)).get('game') || '';
}

function syncGameHash(gameId) {
  const hash = `#game=${encodeURIComponent(gameId)}`;
  if (window.location.hash === hash) return;
  history.replaceState(history.state, '', `${window.location.pathname}${window.location.search}${hash}`);
}

function clearGameHash() {
  if (!gameHashId()) return;
  history.replaceState(history.state, '', `${window.location.pathname}${window.location.search}`);
}

function copyCurrentGameLink(button) {
  const url = window.location.href;
  const done = () => {
    const before = button.textContent;
    button.textContent = 'Lien copié';
    window.setTimeout(() => { button.textContent = before; }, 1300);
  };
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(url).then(done).catch(() => window.prompt('Copier le lien', url));
  else window.prompt('Copier le lien', url);
}

function openDialog(game, { syncUrl = true } = {}) {
  const firstOpen = !els.dialog.open;
  if (firstOpen) {
    state.dialogOpener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    lockCatalogScroll();
  }
  state.dialogGameId = game.id;
  if (syncUrl) syncGameHash(game.id);

  const layout = document.createElement('div');
  layout.className = 'dialog-layout';
  layout.dataset.gameId = game.id;
  layout.dataset.detailPath = game.detail_path || '';

  const cover = document.createElement('div'); cover.className = 'dialog-cover';
  if (game.image_url) {
    const img = document.createElement('img');
    img.src = game.image_url;
    img.alt = '';
    img.referrerPolicy = 'no-referrer';
    img.addEventListener('error', () => img.remove(), { once:true });
    cover.append(img);
  }

  const info = document.createElement('div'); info.className = 'dialog-info';
  const title = document.createElement('h2'); title.textContent = game.title; info.append(title);
  const meta = document.createElement('div'); meta.className = 'dialog-meta';
  const date = document.createElement('span'); date.textContent = formatDate(game.post_date); meta.append(date);
  if (game.repack_size && game.repack_size !== 'N/A') {
    const size = document.createElement('span'); size.textContent = `Taille : ${game.repack_size}`; meta.append(size);
  }
  info.append(meta);

  const nav = document.createElement('div'); nav.className = 'dialog-nav';
  const previous = document.createElement('button'); previous.type = 'button'; previous.className = 'ghost-btn'; previous.textContent = '← Précédent'; previous.addEventListener('click', () => navigateDialog(-1));
  const share = document.createElement('button'); share.type = 'button'; share.className = 'ghost-btn'; share.textContent = 'Partager'; share.addEventListener('click', () => copyCurrentGameLink(share));
  const next = document.createElement('button'); next.type = 'button'; next.className = 'ghost-btn'; next.textContent = 'Suivant →'; next.addEventListener('click', () => navigateDialog(1));
  nav.append(previous, share, next);
  info.append(nav);

  const tags = getTags(game);
  if (tags.length) {
    const box = document.createElement('div'); box.className = 'dialog-genres';
    tags.forEach(tag => box.append(pill(tag)));
    info.append(box);
  }

  const source = game.source_url || game.post_url || '';
  if (source) {
    const link = document.createElement('a');
    link.className = 'source-link';
    link.href = source;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Voir la page source ↗';
    info.append(link);
  }

  if (game.detail_path) {
    const loading = document.createElement('p');
    loading.className = 'dialog-note detail-loading';
    loading.dataset.detailStatus = 'loading';
    loading.textContent = 'Chargement de la fiche détaillée…';
    info.append(loading);
  }

  const note = document.createElement('p');
  note.className = 'dialog-note';
  note.textContent = 'FitBoyRepack indexe les métadonnées et médias publics utiles au catalogue puis renvoie vers la page source.';
  info.append(note);

  layout.append(cover, info);
  els.dialogContent.replaceChildren(layout);
  if (firstOpen) els.dialog.showModal();
  document.dispatchEvent(new CustomEvent('fitboy:game-open', { detail:{ gameId:game.id, detailPath:game.detail_path || '', game } }));
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
  openDialog(state.filtered[next], { syncUrl:true });
}

function restoreCatalogPosition() {
  const opener = state.dialogOpener;
  state.dialogGameId = null;
  state.dialogOpener = null;
  clearGameHash();
  unlockCatalogScroll();
  requestAnimationFrame(() => {
    if (opener?.isConnected) {
      try { opener.focus({ preventScroll:true }); } catch { /* noop */ }
    }
  });
}

function openGameFromHash() {
  if (!state.games.length) return;
  const gameId = gameHashId();
  if (!gameId) {
    if (els.dialog.open) els.dialog.close();
    return;
  }
  const game = state.games.find(item => item.id === gameId);
  if (game) openDialog(game, { syncUrl:false });
}

function setDrawer(open) {
  els.filterSidebar.classList.toggle('drawer-open', open);
  document.body.classList.toggle('filter-drawer-open', open);
  els.filterDrawerToggle.setAttribute('aria-expanded', String(open));
}

function resetFilters() {
  els.search.value = '';
  els.tagSearch.value = '';
  els.yearFilter.value = '';
  els.sizeFilter.value = '';
  els.newOnlyFilter.checked = false;
  els.mediaOnlyFilter.checked = false;
  els.descriptionOnlyFilter.checked = false;
  state.selectedTags.clear();
  state.favoritesOnly = false;
  updateTagUI();
  filterVisibleTags();
  els.suggestions.hidden = true;
}

async function loadCatalog() {
  try {
    const payload = await loadCatalogPayload();
    state.games = payload.games.filter(game => game?.id && game?.title).map(prepareGame);
    const generated = payload.generated_at;
    els.status.textContent = generated
      ? `Mis à jour ${new Intl.DateTimeFormat('fr-FR', { dateStyle:'medium', timeStyle:'short' }).format(new Date(generated))}`
      : `${state.games.length.toLocaleString('fr-FR')} jeux`;
    populateYears();
    buildTagIndex();
    applyFilters();
    renderDiscovery();
    openGameFromHash();
    document.dispatchEvent(new CustomEvent('fitboy:catalog-ready', { detail:{ count:state.games.length } }));
  } catch (error) {
    console.error(error);
    els.status.textContent = 'Catalogue indisponible';
    els.empty.hidden = false;
    els.empty.querySelector('strong').textContent = 'Impossible de charger le catalogue';
    els.empty.querySelector('span').textContent = 'Le robot de données doit être relancé.';
  }
}

let searchTimer;
els.search.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    applyFilters();
    renderSearchSuggestions();
  }, SEARCH_DEBOUNCE_MS);
});
els.search.addEventListener('focus', renderSearchSuggestions);
els.search.addEventListener('blur', () => window.setTimeout(() => { els.suggestions.hidden = true; }, 120));
els.search.addEventListener('keydown', event => {
  if (event.key === 'ArrowDown' && moveSuggestion(1)) { event.preventDefault(); return; }
  if (event.key === 'ArrowUp' && moveSuggestion(-1)) { event.preventDefault(); return; }
  if (event.key === 'Enter' && activateSuggestion()) { event.preventDefault(); return; }
  if (event.key === 'Escape') els.suggestions.hidden = true;
});
els.tagSearch.addEventListener('input', filterVisibleTags);
els.tagMode.addEventListener('change', applyFilters);
els.clearTags.addEventListener('click', () => {
  state.selectedTags.clear();
  els.tagSearch.value = '';
  updateTagUI();
  filterVisibleTags();
});
els.yearFilter.addEventListener('change', applyFilters);
els.sizeFilter.addEventListener('change', applyFilters);
els.newOnlyFilter.addEventListener('change', applyFilters);
els.mediaOnlyFilter.addEventListener('change', applyFilters);
els.descriptionOnlyFilter.addEventListener('change', applyFilters);
els.resetFilters.addEventListener('click', resetFilters);
els.sort.addEventListener('change', applyFilters);
els.favoritesToggle.addEventListener('click', () => { state.favoritesOnly = !state.favoritesOnly; applyFilters(); });
els.filterDrawerToggle.addEventListener('click', () => setDrawer(!els.filterSidebar.classList.contains('drawer-open')));
els.filterDrawerClose.addEventListener('click', () => setDrawer(false));
els.dialog.addEventListener('click', event => { if (event.target === els.dialog || event.target.closest('[data-close-dialog]')) els.dialog.close(); });
els.dialog.addEventListener('close', restoreCatalogPosition);

document.addEventListener('pointerdown', event => {
  if (window.innerWidth > 900 || !els.filterSidebar.classList.contains('drawer-open')) return;
  if (els.filterSidebar.contains(event.target) || els.filterDrawerToggle.contains(event.target)) return;
  setDrawer(false);
});

document.addEventListener('fitboy:profile-change', event => {
  if (event.detail?.source === 'favorites') return;
  state.favorites = readFavorites();
  applyFilters();
  renderDiscovery();
});

document.addEventListener('keydown', event => {
  const activeTag = document.activeElement?.tagName;
  const typing = activeTag === 'INPUT' || activeTag === 'TEXTAREA' || activeTag === 'SELECT';

  if (els.dialog.open && !typing && !isMediaLightboxOpen()) {
    if (event.key === 'ArrowLeft') { event.preventDefault(); navigateDialog(-1); return; }
    if (event.key === 'ArrowRight') { event.preventDefault(); navigateDialog(1); return; }
  }

  if (event.key === '/' && !typing) { event.preventDefault(); els.search.focus(); }
  if (event.key === 'Escape' && els.filterSidebar.classList.contains('drawer-open')) setDrawer(false);
});

window.addEventListener('resize', () => {
  scheduleInfiniteCheck();
  if (window.innerWidth > 900) setDrawer(false);
}, { passive:true });
window.addEventListener('hashchange', openGameFromHash);
infiniteObserver.observe(els.scrollSentinel);
loadCatalog();
