import { loadCatalogPayload } from './catalog-api.js';

const FAVORITES_KEY = 'fitboyrepack:favorites:v1';

const els = {
  search: document.querySelector('#searchInput'),
  tagSearch: document.querySelector('#tagSearch'),
  tagMode: document.querySelector('#tagMode'),
  tagList: document.querySelector('#tagList'),
  clearTags: document.querySelector('#clearTags'),
  favoritesToggle: document.querySelector('#favoritesToggle')
};

let games = [];
let ready = false;
let updateFrame = 0;

function normalized(value = '') {
  return String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

function rawTags(game) {
  const value = game?.genres ?? game?.genre ?? [];
  return (Array.isArray(value) ? value : String(value || '').split(','))
    .map(item => String(item).trim())
    .filter(Boolean);
}

function readFavorites() {
  try { return new Set(JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]').map(String)); }
  catch { return new Set(); }
}

function selectedTagKeys() {
  return [...els.tagList.querySelectorAll('.tag-chip.active')]
    .map(button => button.dataset.tagKey)
    .filter(Boolean);
}

function coreGames() {
  const query = normalized(els.search.value);
  const tagQuery = normalized(els.tagSearch.value);
  const favoritesOnly = els.favoritesToggle.getAttribute('aria-pressed') === 'true';
  const favorites = favoritesOnly ? readFavorites() : null;

  return games.filter(game => {
    if (favoritesOnly && !favorites.has(game.id)) return false;
    if (tagQuery && !game.tags.some(tag => tag.includes(tagQuery))) return false;
    if (query && !game.searchText.includes(query)) return false;
    return true;
  });
}

function compatibleCounts(pool, selected) {
  const counts = new Map();
  let currentCount = 0;
  for (const game of pool) {
    if (!selected.every(tag => game.tagSet.has(tag))) continue;
    currentCount += 1;
    for (const tag of game.tagSet) counts.set(tag, (counts.get(tag) || 0) + 1);
  }
  return { counts, currentCount };
}

function updateFacets() {
  if (!ready || !els.tagList.children.length) return;

  const selected = selectedTagKeys();
  const selectedSet = new Set(selected);
  const pool = coreGames();
  const { counts, currentCount } = compatibleCounts(pool, selected);
  const tagQuery = normalized(els.tagSearch.value);

  els.tagList.querySelectorAll('.tag-chip').forEach(button => {
    const key = button.dataset.tagKey;
    const active = selectedSet.has(key);
    const small = button.querySelector('small');
    const nextCount = active ? currentCount : (counts.get(key) || 0);

    button.disabled = !active && nextCount === 0;
    button.hidden = button.disabled || (!active && tagQuery && !normalized(button.dataset.tagLabel).includes(tagQuery));
    button.title = active
      ? `Retirer le tag ${button.dataset.tagLabel}`
      : `Ajouter ${button.dataset.tagLabel} · ${nextCount} jeu${nextCount > 1 ? 'x' : ''}`;

    const label = nextCount.toLocaleString('fr-FR');
    if (small && small.textContent !== label) small.textContent = label;
    button.setAttribute('aria-disabled', String(button.disabled));
  });
}

function scheduleUpdate() {
  if (!ready || updateFrame) return;
  updateFrame = requestAnimationFrame(() => {
    updateFrame = 0;
    updateFacets();
  });
}

const tagListObserver = new MutationObserver(scheduleUpdate);
tagListObserver.observe(els.tagList, { childList:true, subtree:false });

els.tagList.addEventListener('click', event => {
  if (event.target.closest('.tag-chip')) scheduleUpdate();
});
els.search.addEventListener('input', scheduleUpdate);
els.tagSearch.addEventListener('input', scheduleUpdate);
els.favoritesToggle.addEventListener('click', scheduleUpdate);
els.clearTags.addEventListener('click', scheduleUpdate);

async function loadGames() {
  try {
    const payload = await loadCatalogPayload();
    games = payload.games.filter(game => game?.id && game?.title).map(game => {
      const raw = rawTags(game);
      const tags = raw.map(normalized);
      return {
        id: String(game.id),
        tags,
        tagSet: new Set(tags),
        searchText: normalized([game.title, game.repack_size, ...raw].join(' '))
      };
    });
    ready = true;
    scheduleUpdate();
  } catch (error) {
    console.error('Tag facets unavailable', error);
  }
}

loadGames();
