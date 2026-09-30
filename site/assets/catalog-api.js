const CATALOG_URL = './data/catalog.json';
const DETAIL_CACHE_LIMIT = 24;

let catalogPromise = null;
const detailCache = new Map();

export function loadCatalogPayload() {
  if (!catalogPromise) {
    catalogPromise = fetch(CATALOG_URL, { cache:'no-cache' }).then(async response => {
      if (!response.ok) throw new Error(`Catalog HTTP ${response.status}`);
      const payload = await response.json();
      if (!payload || !Array.isArray(payload.games)) throw new Error('Invalid lightweight catalog payload');
      return payload;
    }).catch(error => {
      catalogPromise = null;
      throw error;
    });
  }
  return catalogPromise;
}

export function detailUrl(detailPath) {
  if (!detailPath) return null;
  return new URL(detailPath, document.baseURI).href;
}

export function loadGameDetail(detailPath) {
  const url = detailUrl(detailPath);
  if (!url) return Promise.reject(new Error('Missing game detail path'));
  if (detailCache.has(url)) return detailCache.get(url);

  const promise = fetch(url, { cache:'no-cache' }).then(async response => {
    if (!response.ok) throw new Error(`Game detail HTTP ${response.status}`);
    const game = await response.json();
    if (!game || !game.id || !game.title) throw new Error('Invalid game detail payload');
    return game;
  }).catch(error => {
    detailCache.delete(url);
    throw error;
  });

  detailCache.set(url, promise);
  while (detailCache.size > DETAIL_CACHE_LIMIT) {
    const oldest = detailCache.keys().next().value;
    detailCache.delete(oldest);
  }
  return promise;
}
