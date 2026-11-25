const CATALOG_URL = './data/catalog.json';
const SEARCH_INDEX_URL = './data/search-index.json';
const HEALTH_URL = './data/health.json';
const STEAM_RATINGS_URL = './data/steam-ratings.json';
const DETAIL_CACHE_LIMIT = 24;

let catalogPromise = null;
let searchIndexPromise = null;
let healthPromise = null;
let steamRatingsPromise = null;
const detailCache = new Map();
const detailPending = new Map();

function fetchJson(url, label) {
  return fetch(url, { cache:'no-cache' }).then(async response => {
    if (!response.ok) throw new Error(`${label} HTTP ${response.status}`);
    return response.json();
  });
}

export function loadCatalogPayload() {
  if (!catalogPromise) {
    catalogPromise = fetchJson(CATALOG_URL, 'Catalog').then(payload => {
      if (!payload || !Array.isArray(payload.games)) throw new Error('Invalid lightweight catalog payload');
      return payload;
    }).catch(error => { catalogPromise = null; throw error; });
  }
  return catalogPromise;
}

export function loadSearchIndexPayload() {
  if (!searchIndexPromise) {
    searchIndexPromise = fetchJson(SEARCH_INDEX_URL, 'Search index').then(payload => {
      if (!payload || typeof payload.count !== 'number' || !payload.prefixes || !payload.grams) {
        throw new Error('Invalid static search index payload');
      }
      return payload;
    }).catch(error => { searchIndexPromise = null; throw error; });
  }
  return searchIndexPromise;
}

export function loadHealthPayload() {
  if (!healthPromise) {
    healthPromise = fetchJson(HEALTH_URL, 'Health').then(payload => {
      if (!payload || typeof payload.total_games !== 'number') throw new Error('Invalid health payload');
      return payload;
    }).catch(error => { healthPromise = null; throw error; });
  }
  return healthPromise;
}

export function loadSteamRatingsPayload() {
  if (!steamRatingsPromise) {
    steamRatingsPromise = fetchJson(STEAM_RATINGS_URL, 'Steam ratings').then(payload => {
      if (!payload || payload.rating_version !== 1 || !payload.games || typeof payload.games !== 'object') {
        throw new Error('Invalid Steam ratings payload');
      }
      return payload;
    }).catch(error => { steamRatingsPromise = null; throw error; });
  }
  return steamRatingsPromise;
}

export function detailUrl(detailPath) {
  if (!detailPath) return null;
  return new URL(detailPath, document.baseURI).href;
}

export function loadGameDetail(detailPath) {
  const url = detailUrl(detailPath);
  if (!url) return Promise.reject(new Error('Missing game detail path'));
  if (detailCache.has(url)) {
    const value = detailCache.get(url);
    detailCache.delete(url);
    detailCache.set(url, value);
    return Promise.resolve(value);
  }
  if (detailPending.has(url)) return detailPending.get(url);
  const promise = fetchJson(url, 'Game detail').then(game => {
    if (!game || !game.id || !game.title) throw new Error('Invalid game detail payload');
    detailCache.set(url, game);
    while (detailCache.size > DETAIL_CACHE_LIMIT) detailCache.delete(detailCache.keys().next().value);
    return game;
  }).finally(() => {
    if (detailPending.get(url) === promise) detailPending.delete(url);
  });
  detailPending.set(url, promise);
  return promise;
}

export function searchIndexMatchesCatalog(index, catalog) {
  return index.count === catalog.count
    && index.generated_at === catalog.generated_at
    && index.metadata_generated_at === catalog.metadata_generated_at
    && index.steam_generated_at === catalog.steam_generated_at
    && index.steam_release_seed_generated_at === catalog.steam_release_seed_generated_at;
}
