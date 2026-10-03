const CATALOG_URL = './data/catalog.json';
const SEARCH_INDEX_URL = './data/search-index.json';
const HEALTH_URL = './data/health.json';
const TRANSLATIONS_FR_URL = './data/translations-fr.json';
const DETAIL_CACHE_LIMIT = 24;

let catalogPromise = null;
let searchIndexPromise = null;
let healthPromise = null;
let translationsFrPromise = null;
const detailCache = new Map();

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

export function loadTranslationsFrPayload() {
  if (!translationsFrPromise) {
    translationsFrPromise = fetchJson(TRANSLATIONS_FR_URL, 'French translations').then(payload => {
      if (
        !payload
        || payload.translation_version !== 1
        || payload.language !== 'fr'
        || !payload.games
        || typeof payload.games !== 'object'
      ) {
        throw new Error('Invalid French translation payload');
      }
      return payload;
    }).catch(error => { translationsFrPromise = null; throw error; });
  }
  return translationsFrPromise;
}

export function detailUrl(detailPath) {
  if (!detailPath) return null;
  return new URL(detailPath, document.baseURI).href;
}

export function loadGameDetail(detailPath) {
  const url = detailUrl(detailPath);
  if (!url) return Promise.reject(new Error('Missing game detail path'));
  if (detailCache.has(url)) return detailCache.get(url);
  const promise = fetchJson(url, 'Game detail').then(game => {
    if (!game || !game.id || !game.title) throw new Error('Invalid game detail payload');
    return game;
  }).catch(error => { detailCache.delete(url); throw error; });
  detailCache.set(url, promise);
  while (detailCache.size > DETAIL_CACHE_LIMIT) detailCache.delete(detailCache.keys().next().value);
  return promise;
}
