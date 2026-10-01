import { loadGameDetail } from './catalog-api.js';

const dialog = document.querySelector('#gameDialog');
const dialogContent = document.querySelector('#dialogContent');
const warmed = new Map();
let openToken = 0;

function normalizedUrl(value = '') {
  try {
    const url = new URL(value, window.location.href);
    url.hash = '';
    return url.href.replace(/\/$/, '');
  } catch {
    return String(value || '').replace(/\/$/, '');
  }
}

function isHttps(value = '') {
  return /^https:\/\//i.test(String(value || ''));
}

function preloadImage(url) {
  if (!isHttps(url)) return Promise.resolve(false);
  const key = normalizedUrl(url);
  if (warmed.has(key)) return warmed.get(key);
  const promise = new Promise(resolve => {
    const image = new Image();
    image.decoding = 'async';
    image.referrerPolicy = 'no-referrer';
    image.onload = () => resolve(true);
    image.onerror = () => resolve(false);
    image.src = url;
  });
  warmed.set(key, promise);
  return promise;
}

function waitForPreview(img) {
  if (!img || img.complete) return Promise.resolve();
  return new Promise(resolve => {
    const done = () => resolve();
    img.addEventListener('load', done, { once:true });
    img.addEventListener('error', done, { once:true });
  });
}

function idle(callback) {
  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(callback, { timeout:1200 });
  } else {
    window.setTimeout(callback, 350);
  }
}

function waitForRenderedMedia(gameId, token) {
  return new Promise(resolve => {
    const find = () => {
      if (token !== openToken || !dialog?.open) return null;
      const layout = dialogContent?.querySelector(`.dialog-layout[data-game-id="${CSS.escape(String(gameId))}"]`);
      if (!layout) return null;
      const media = layout.querySelector('.media-item, .gameplay-preview-button');
      return media ? layout : null;
    };
    const immediate = find();
    if (immediate) return resolve(immediate);

    const observer = new MutationObserver(() => {
      const layout = find();
      if (!layout) return;
      observer.disconnect();
      resolve(layout);
    });
    observer.observe(dialogContent, { childList:true, subtree:true });
    window.setTimeout(() => {
      observer.disconnect();
      resolve(find());
    }, 2500);
  });
}

function mediaMap(game) {
  const map = new Map();
  for (const item of Array.isArray(game?.media) ? game.media : []) {
    if (!item?.url) continue;
    map.set(normalizedUrl(item.url), item);
  }
  return map;
}

function bindWarmup(target, fullUrl) {
  if (!target || !isHttps(fullUrl)) return;
  const warm = () => { preloadImage(fullUrl); };
  target.addEventListener('pointerenter', warm, { passive:true });
  target.addEventListener('focus', warm, { passive:true });
  target.addEventListener('touchstart', warm, { passive:true, once:true });
}

function usePreview(img, item) {
  if (!img || !item?.url) return false;
  const preview = item.preview_url;
  if (!isHttps(preview) || normalizedUrl(preview) === normalizedUrl(item.url)) return false;
  img.src = preview;
  img.loading = 'eager';
  img.decoding = 'async';
  img.referrerPolicy = 'no-referrer';
  img.dataset.previewSource = 'true';
  return true;
}

async function warmFullMedia(items, previewImages, token) {
  await Promise.allSettled(previewImages.map(waitForPreview));
  if (token !== openToken || !dialog?.open) return;
  idle(async () => {
    const queue = items
      .filter(item => isHttps(item?.url) && isHttps(item?.preview_url) && normalizedUrl(item.url) !== normalizedUrl(item.preview_url))
      .map(item => item.url);
    let cursor = 0;
    async function worker() {
      while (cursor < queue.length && token === openToken && dialog?.open) {
        const url = queue[cursor++];
        await preloadImage(url);
      }
    }
    await Promise.all([worker(), worker()]);
  });
}

async function applyPreviewSources(game, gameId, token) {
  const layout = await waitForRenderedMedia(gameId, token);
  if (!layout || token !== openToken) return;
  const byFull = mediaMap(game);
  const previewImages = [];

  layout.querySelectorAll('.media-item').forEach(anchor => {
    const item = byFull.get(normalizedUrl(anchor.href));
    if (!item) return;
    const img = anchor.querySelector('img');
    if (usePreview(img, item)) previewImages.push(img);
    bindWarmup(anchor, item.url);
  });

  const gifButton = layout.querySelector('.gameplay-preview-button');
  if (gifButton?.dataset.mediaUrl) {
    const item = byFull.get(normalizedUrl(gifButton.dataset.mediaUrl));
    const img = gifButton.querySelector('img');
    if (item && usePreview(img, item)) previewImages.push(img);
    if (item) bindWarmup(gifButton, item.url);
  }

  warmFullMedia(Array.isArray(game?.media) ? game.media : [], previewImages, token);
}

document.addEventListener('fitboy:game-open', async event => {
  const token = ++openToken;
  const { gameId, detailPath } = event.detail || {};
  if (!detailPath) return;
  try {
    const game = await loadGameDetail(detailPath);
    if (token !== openToken || !dialog?.open) return;
    applyPreviewSources(game, String(gameId || ''), token);
  } catch (error) {
    console.debug('Preview media optimization skipped', error);
  }
});

dialog?.addEventListener('close', () => { openToken += 1; });
