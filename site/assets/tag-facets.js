const DATA_URL = './data/games.json';
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
let updateQueued = false;

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

function compatibleCounts(pool, selected, requireAll) {
  const counts = new Map();

  if (requireAll) {
    let currentCount = 0;
    for (const game of pool) {
      if (!selected.every(tag => game.tagSet.has(tag))) continue;
      currentCount += 1;
      for (const tag of game.tagSet) counts.set(tag, (counts.get(tag) || 0) + 1);
    }
    return { counts, currentCount };
  }

  if (!selected.length) {
    for (const game of pool) {
      for (const tag of game.tagSet) counts.set(tag, (counts.get(tag) || 0) + 1);
    }
    return { counts, currentCount: pool.length };
  }

  let currentCount = 0;
  for (const game of pool) {
    const alreadyMatches = selected.some(tag => game.tagSet.has(tag));
    if (alreadyMatches) {
      currentCount += 1;
      continue;
    }
    for (const tag of game.tagSet) counts.set(tag, (counts.get(tag) || 0) + 1);
  }
  return { counts, currentCount };
}

function updateFacets() {
  updateQueued = false;
  if (!ready || !els.tagList.children.length) return;

  const selected = selectedTagKeys();
  const selectedSet = new Set(selected);
  const requireAll = els.tagMode.value === 'all';
  const pool = coreGames();
  const { counts, currentCount } = compatibleCounts(pool, selected, requireAll);
  const tagQuery = normalized(els.tagSearch.value);

  els.tagList.querySelectorAll('.tag-chip').forEach(button => {
    const key = button.dataset.tagKey;
    const active = selectedSet.has(key);
    const small = button.querySelector('small');
    let nextCount;

    if (active) {
      nextCount = currentCount;
      button.disabled = false;
      button.title = `Retirer le tag ${button.dataset.tagLabel}`;
      // Un tag déjà sélectionné reste toujours visible afin de pouvoir l'enlever.
      button.hidden = false;
    } else if (requireAll) {
      nextCount = counts.get(key) || 0;
      button.disabled = nextCount === 0;
      button.title = button.disabled
        ? `Aucun jeu supplémentaire ne correspond avec ${button.dataset.tagLabel}`
        : `Ajouter ${button.dataset.tagLabel} · ${nextCount} jeu${nextCount > 1 ? 'x' : ''}`;
    } else {
      const extra = counts.get(key) || 0;
      nextCount = selected.length ? currentCount + extra : extra;
      button.disabled = nextCount === 0;
      button.title = button.disabled
        ? `Aucun jeu ne correspond à ${button.dataset.tagLabel}`
        : `Ajouter ${button.dataset.tagLabel} · ${nextCount} jeu${nextCount > 1 ? 'x' : ''}`;
    }

    if (!active && tagQuery) button.hidden = !normalized(button.dataset.tagLabel).includes(tagQuery);
    if (small) small.textContent = nextCount.toLocaleString('fr-FR');
    button.setAttribute('aria-disabled', String(button.disabled));
  });
}

function scheduleUpdate() {
  if (updateQueued) return;
  updateQueued = true;
  queueMicrotask(updateFacets);
}

const observer = new MutationObserver(scheduleUpdate);
observer.observe(els.tagList, { childList:true, subtree:true, attributes:true, attributeFilter:['class'] });
observer.observe(els.favoritesToggle, { attributes:true, attributeFilter:['aria-pressed'] });

els.search.addEventListener('input', scheduleUpdate);
els.tagSearch.addEventListener('input', scheduleUpdate);
els.tagMode.addEventListener('change', scheduleUpdate);
els.clearTags.addEventListener('click', () => {
  // Réinitialisation complète du sous-système Tags : sélection, recherche et mode ET.
  if (els.tagMode.value !== 'all') {
    els.tagMode.value = 'all';
    els.tagMode.dispatchEvent(new Event('change', { bubbles:true }));
  }
  scheduleUpdate();
});

async function loadGames() {
  try {
    // Keep the facet index in sync with the same fresh catalog used by app.js.
    const response = await fetch(DATA_URL, { cache:'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const source = Array.isArray(payload) ? payload : payload.games || [];
    games = source.filter(game => game?.id && game?.title).map(game => {
      const tags = rawTags(game).map(normalized);
      return {
        id: String(game.id),
        tags,
        tagSet: new Set(tags),
        searchText: normalized([game.title, game.repack_size, ...rawTags(game)].join(' '))
      };
    });
    ready = true;
    scheduleUpdate();
  } catch (error) {
    console.error('Tag facets unavailable', error);
  }
}

loadGames();
