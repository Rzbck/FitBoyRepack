import { loadGameDetail, loadTranslationsFrPayload } from './catalog-api.js';
import {
  displayTitle as identityDisplayTitle,
  editionTitle as identityEditionTitle,
  effectiveGenreLabels,
} from './game-identity.js';
import {
  applyTranslations,
  currentLanguage,
  formatDateValue,
  mediaCountLabel,
  t,
} from './i18n.js';
import { localizeGameProse } from './translations.js';

const dialog = document.querySelector('#gameDialog');
const dialogContent = document.querySelector('#dialogContent');

let lightboxItems = [];
let lightboxIndex = 0;
let detailRequestId = 0;
let currentSourceGame = null;
let currentSourceGameId = '';

function normalizedUrl(value = '') {
  try {
    const url = new URL(value, window.location.href);
    url.hash = '';
    return url.href.replace(/\/$/, '');
  } catch {
    return String(value || '').replace(/\/$/, '');
  }
}

function createPill(text) {
  const span = document.createElement('span');
  span.className = 'genre-pill';
  span.textContent = text;
  return span;
}

function formatDate(value) {
  return formatDateValue(value) || (currentLanguage()==='fr'?'Date inconnue':'Unknown date');
}

function verifiedMetadata(game) {
  const value = game?.verified_metadata;
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
}

function metadataList(value) {
  return Array.isArray(value)
    ? value.map(item => String(item || '').trim()).filter(Boolean)
    : [];
}

function safeHttpsUrl(value) {
  try {
    const url = new URL(String(value || ''));
    return url.protocol === 'https:' ? url : null;
  } catch {
    return null;
  }
}

function metadataSourceLabel(url) {
  const host = url.hostname.toLowerCase();
  if (host === 'www.wikidata.org') return 'Wikidata';
  if (host.endsWith('.wikipedia.org')) return 'Wikipedia';
  return host;
}

function cleanMetadataScalar(value) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text || /^Q\d+$/i.test(text)) return '';
  return text;
}

function cleanPlatformLabel(value) {
  const text = cleanMetadataScalar(value);
  if (!text) return '';
  const aliases = new Map([
    ['microsoft windows', 'Windows'],
    ['windows', 'Windows'],
    ['mac os', 'macOS'],
    ['macos', 'macOS'],
    ['mac', 'macOS'],
    ['xbox series x and series s', 'Xbox Series X/S'],
    ['xbox series x/s', 'Xbox Series X/S'],
    ['playstation 5', 'PlayStation 5'],
    ['playstation 4', 'PlayStation 4'],
    ['nintendo switch', 'Nintendo Switch'],
  ]);
  return aliases.get(text.toLowerCase()) || text;
}

function cleanMetadataList(value, cleaner = cleanMetadataScalar) {
  const out = [];
  const seen = new Set();
  for (const item of metadataList(value)) {
    const cleaned = cleaner(item);
    const key = cleaned.toLocaleLowerCase('fr');
    if (!cleaned || seen.has(key)) continue;
    seen.add(key);
    out.push(cleaned);
  }
  return out;
}

function appendIdentityFact(list, labelKey, value) {
  if (!value) return;
  const row = document.createElement('div');
  row.className = 'identity-fact';
  const term = document.createElement('dt');
  term.dataset.i18n = labelKey;
  term.textContent = t(labelKey);
  const description = document.createElement('dd');
  description.textContent = value;
  row.append(term, description);
  list.append(row);
}

function makeIdentityFacts(game) {
  const metadata = verifiedMetadata(game);
  if (!metadata) return null;

  const facts = document.createElement('section');
  facts.className = 'cover-identity-facts';

  const list = document.createElement('dl');
  list.className = 'identity-fact-list';

  appendIdentityFact(list, 'detail.developer', cleanMetadataScalar(metadata.developer));
  appendIdentityFact(list, 'detail.publisher', cleanMetadataScalar(metadata.publisher));

  const platforms = cleanMetadataList(metadata.platforms, cleanPlatformLabel);
  appendIdentityFact(list, 'detail.platforms', platforms.slice(0, 5).join(' · '));

  if (list.childElementCount) facts.append(list);

  const sources = metadataList(metadata.evidence_urls)
    .map(safeHttpsUrl)
    .filter(Boolean)
    .slice(0, 2);
  if (sources.length) {
    const sourceLine = document.createElement('div');
    sourceLine.className = 'identity-evidence';
    const prefix = document.createElement('span');
    prefix.dataset.i18n = 'detail.verified';
    prefix.textContent = t('detail.verified');
    sourceLine.append(prefix);
    sources.forEach(url => {
      const link = document.createElement('a');
      link.href = url.href;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = `${metadataSourceLabel(url)} ↗`;
      sourceLine.append(link);
    });
    facts.append(sourceLine);
  }

  return facts;
}

function currentLayout(gameId = '') {
  const layout = dialogContent.querySelector('.dialog-layout');
  if (!layout) return null;
  if (gameId && layout.dataset.gameId !== String(gameId)) return null;
  return layout;
}

function renderCoverDetails(layout, game) {
  const cover = layout.querySelector('.dialog-cover');
  const info = layout.querySelector('.dialog-info');
  if (!cover || !info) return;

  layout.classList.add('rich-details');
  layout.classList.remove('dialog-loading');

  const coverImg = cover.querySelector(':scope > img');
  if (coverImg) {
    const visibleTitle = cover.querySelector('.cover-game-title')?.textContent?.trim()
      || identityDisplayTitle(game)
      || game.title;
    coverImg.alt = `Jaquette de ${visibleTitle}`;
    coverImg.loading = 'eager';
  }

  // The lightweight catalog already contains the identity fields required for
  // the first paint (canonical title, release date and merged genres). Keep
  // that exact DOM node when lazy details arrive so the user never sees a
  // second title/tag version replace the first one.
  const existing = cover.querySelector('.cover-details');
  if (existing) {
    existing.classList.remove('cover-details-initial');
    layout.dataset.identityStable = 'true';

    if (!existing.querySelector('.cover-identity-facts')) {
      const identityFacts = makeIdentityFacts(game);
      if (identityFacts) existing.append(identityFacts);
    }
    return;
  }

  // Defensive fallback for a malformed/legacy shell. It uses the exact same
  // shared identity rules as app.js, including merged metadata + legacy genres.
  const card = document.createElement('div');
  card.className = 'cover-details';

  const metadata = verifiedMetadata(game);
  const meta = document.createElement('div');
  meta.className = 'cover-details-meta';

  const published = document.createElement('span');
  const publishedLabel = document.createElement('small');
  publishedLabel.dataset.i18n = 'detail.published';
  publishedLabel.textContent = t('detail.published');
  const publishedValue = document.createElement('strong');
  publishedValue.dataset.i18nDate = game.post_date || '';
  publishedValue.textContent = formatDate(game.post_date);
  published.append(publishedLabel, publishedValue);
  meta.append(published);

  if (metadata?.release_date) {
    const release = document.createElement('span');
    const releaseLabel = document.createElement('small');
    releaseLabel.dataset.i18n = 'detail.releaseDate';
    releaseLabel.textContent = t('detail.releaseDate');
    const releaseValue = document.createElement('strong');
    releaseValue.dataset.i18nDate = metadata.release_date;
    releaseValue.textContent = formatDate(metadata.release_date);
    release.append(releaseLabel, releaseValue);
    meta.append(release);
  }

  if (game.repack_size && game.repack_size !== 'N/A') {
    const size = document.createElement('span');
    const sizeLabel = document.createElement('small');
    sizeLabel.dataset.i18n = 'detail.repackSize';
    sizeLabel.textContent = t('detail.repackSize');
    const sizeValue = document.createElement('strong');
    sizeValue.textContent = game.repack_size;
    size.append(sizeLabel, sizeValue);
    meta.append(size);
  }
  card.append(meta);

  const tags = effectiveGenreLabels(game);
  if (tags.length) {
    const tagBox = document.createElement('div');
    tagBox.className = 'cover-tags';
    tags.forEach(tag => tagBox.append(createPill(tag)));
    card.append(tagBox);
  }

  const h2 = document.createElement('h2');
  h2.className = 'cover-game-title';
  h2.textContent = identityDisplayTitle(game) || game.title;
  card.append(h2);

  const edition = identityEditionTitle(game);
  if (edition) {
    const version = document.createElement('p');
    version.className = 'cover-game-version cover-edition-title';
    version.textContent = edition;
    card.append(version);
  }

  const identityFacts = makeIdentityFacts(game);
  if (identityFacts) card.append(identityFacts);

  cover.append(card);
  layout.dataset.identityStable = 'fallback';
  info.querySelector(':scope > h2')?.classList.add('details-moved');
  info.querySelector(':scope > .dialog-meta')?.classList.add('details-moved');
  info.querySelector(':scope > .dialog-genres')?.classList.add('details-moved');
}

function makeTextPanel(titleKey, text) {
  if (!text) return null;
  const panel = document.createElement('section');
  panel.className = 'detail-text-panel';
  const heading = document.createElement('h3');
  heading.dataset.i18n = titleKey;
  heading.textContent = t(titleKey);
  const body = document.createElement('p');
  body.textContent = text;
  panel.append(heading, body);
  return panel;
}

function makeListPanel(titleKey, items) {
  if (!Array.isArray(items) || !items.length) return null;
  const panel = document.createElement('section');
  panel.className = 'detail-text-panel';
  const heading = document.createElement('h3');
  heading.dataset.i18n = titleKey;
  heading.textContent = t(titleKey);
  const list = document.createElement('ul');
  items.forEach(item => {
    const li = document.createElement('li');
    li.textContent = item;
    list.append(li);
  });
  panel.append(heading, list);
  return panel;
}

function renderDescriptionTabs(info, game, { replace = false } = {}) {
  const existing = info.querySelector('.detail-tabs');
  if (existing && !replace) return;
  existing?.remove();
  const details = game.details || {};
  const panels = [
    ['detail.description', makeTextPanel('detail.description', details.description)],
    ['detail.gameFeatures', makeListPanel('detail.gameFeatures', details.game_features)],
    ['detail.repackFeatures', makeListPanel('detail.repackFeatures', details.repack_features)],
  ].filter(([, panel]) => panel);
  if (!panels.length) return;

  const section = document.createElement('section');
  section.className = 'detail-tabs';
  const nav = document.createElement('div');
  nav.className = 'detail-tab-nav';
  const body = document.createElement('div');
  body.className = 'detail-tab-body';

  panels.forEach(([labelKey, panel], index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'detail-tab-btn';
    button.dataset.i18n = labelKey;
    button.textContent = t(labelKey);
    button.setAttribute('aria-pressed', index === 0 ? 'true' : 'false');
    panel.hidden = index !== 0;
    button.addEventListener('click', () => {
      nav.querySelectorAll('.detail-tab-btn').forEach(btn => btn.setAttribute('aria-pressed', 'false'));
      body.querySelectorAll('.detail-text-panel').forEach(item => { item.hidden = true; });
      button.setAttribute('aria-pressed', 'true');
      panel.hidden = false;
    });
    nav.append(button);
    body.append(panel);
  });

  section.append(nav, body);
  info.prepend(section);
}
function validMedia(game) {
  if (!Array.isArray(game.media)) return [];
  return game.media
    .filter(item => item && typeof item.url === 'string' && item.url.startsWith('https://') && ['image', 'gif'].includes(item.type))
    .slice(0, 12);
}

function hasRenderableDetails(game) {
  const details = game?.details || {};
  const hasText = Boolean(String(details.description || '').trim());
  const hasGameFeatures = Array.isArray(details.game_features) && details.game_features.some(item => String(item || '').trim());
  const hasRepackFeatures = Array.isArray(details.repack_features) && details.repack_features.some(item => String(item || '').trim());
  return Boolean(verifiedMetadata(game)) || hasText || hasGameFeatures || hasRepackFeatures || validMedia(game).length > 0;
}

function setDetailStatus(info, text, state = 'empty') {
  const status = info?.querySelector('[data-detail-status]');
  if (!status) return;
  status.dataset.detailStatus = state;
  status.textContent = text;
}

function renderMediaGallery(info, game) {
  if (info.querySelector('.dialog-media')) return;
  const media = validMedia(game);
  if (!media.length) return;

  const section = document.createElement('section');
  section.className = 'dialog-media';
  const heading = document.createElement('div');
  heading.className = 'dialog-subheading';
  const title = document.createElement('h3');
  title.dataset.i18n = 'detail.imagesGifs';
  title.textContent = t('detail.imagesGifs');
  const count = document.createElement('span');
  count.textContent = mediaCountLabel(media.length);
  heading.append(title, count);

  const grid = document.createElement('div');
  grid.className = 'media-grid';
  for (const item of media) {
    const link = document.createElement('a');
    link.className = 'media-item';
    link.href = item.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';

    const img = document.createElement('img');
    img.src = item.preview_url || item.url;
    img.alt = currentLanguage()==='fr'?`Capture de ${game.title}`:`Screenshot of ${game.title}`;
    img.loading = 'lazy';
    img.decoding = 'async';
    img.referrerPolicy = 'no-referrer';
    img.addEventListener('error', () => link.remove(), { once:true });
    link.append(img);

    if (item.type === 'gif') {
      const badge = document.createElement('span');
      badge.className = 'media-kind';
      badge.textContent = 'GIF';
      link.append(badge);
    }
    grid.append(link);
  }
  section.append(heading, grid);

  const sourceLink = info.querySelector('.source-link');
  if (sourceLink) info.insertBefore(section, sourceLink);
  else info.append(section);
}

function renderGameplayPreview(info, game) {
  if (info.querySelector('.gameplay-preview')) return;
  const gif = validMedia(game).find(item => item.type === 'gif');
  if (!gif) return;

  const section = document.createElement('section');
  section.className = 'gameplay-preview';
  const heading = document.createElement('div');
  heading.className = 'dialog-subheading';
  const h3 = document.createElement('h3');
  h3.dataset.i18n = 'detail.gameplay';
  h3.textContent = t('detail.gameplay');
  const hint = document.createElement('span');
  hint.textContent = 'GIF';
  heading.append(h3, hint);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'gameplay-preview-button';
  button.dataset.mediaUrl = gif.url;
  const img = document.createElement('img');
  img.src = gif.preview_url || gif.url;
  img.alt = currentLanguage()==='fr'?`Gameplay de ${game.title}`:`Gameplay from ${game.title}`;
  img.loading = 'lazy';
  img.decoding = 'async';
  img.referrerPolicy = 'no-referrer';
  button.append(img);
  section.append(heading, button);

  const gallery = info.querySelector('.dialog-media');
  if (gallery) info.insertBefore(section, gallery);
  else info.append(section);

  info.querySelectorAll('.media-item').forEach(item => {
    if (normalizedUrl(item.href) === normalizedUrl(gif.url)) item.remove();
  });
  const count = info.querySelector('.dialog-media .dialog-subheading span');
  const remaining = info.querySelectorAll('.dialog-media .media-item').length;
  if (count) count.textContent = mediaCountLabel(remaining);
}

function ensureLightbox() {
  let box = dialog.querySelector('.media-lightbox');
  if (box) return box;

  box = document.createElement('div');
  box.className = 'media-lightbox';
  box.hidden = true;
  box.innerHTML = `
    <div class="media-lightbox-toolbar">
      <span class="media-lightbox-count"></span>
      <button type="button" class="media-lightbox-close" aria-label="${t('detail.closeImage')}" data-i18n-aria-label="detail.closeImage">×</button>
    </div>
    <button type="button" class="media-lightbox-nav media-lightbox-prev" aria-label="${t('detail.prevImage')}" data-i18n-aria-label="detail.prevImage">‹</button>
    <figure class="media-lightbox-stage"><img alt=""><figcaption></figcaption></figure>
    <button type="button" class="media-lightbox-nav media-lightbox-next" aria-label="${t('detail.nextImage')}" data-i18n-aria-label="detail.nextImage">›</button>`;
  applyTranslations(box);
  dialog.append(box);

  box.querySelector('.media-lightbox-close').addEventListener('click', closeLightbox);
  box.querySelector('.media-lightbox-prev').addEventListener('click', () => stepLightbox(-1));
  box.querySelector('.media-lightbox-next').addEventListener('click', () => stepLightbox(1));
  box.addEventListener('click', event => { if (event.target === box) closeLightbox(); });
  return box;
}

function updateLightbox() {
  const box = ensureLightbox();
  const item = lightboxItems[lightboxIndex];
  if (!item) return closeLightbox();
  const img = box.querySelector('.media-lightbox-stage img');
  img.src = item.url;
  img.alt = item.alt || t('detail.gameMedia');
  box.querySelector('.media-lightbox-count').textContent = `${lightboxIndex + 1} / ${lightboxItems.length}`;
  box.querySelector('figcaption').textContent = item.kind === 'gif' ? 'GIF gameplay' : t('detail.gameCapture');
  const hasMany = lightboxItems.length > 1;
  box.querySelector('.media-lightbox-prev').hidden = !hasMany;
  box.querySelector('.media-lightbox-next').hidden = !hasMany;
}

function openLightbox(items, index) {
  lightboxItems = items;
  lightboxIndex = Math.max(0, Math.min(index, items.length - 1));
  const box = ensureLightbox();
  box.hidden = false;
  dialog.classList.add('lightbox-open');
  updateLightbox();
}

function closeLightbox() {
  const box = dialog.querySelector('.media-lightbox');
  if (box) box.hidden = true;
  dialog.classList.remove('lightbox-open');
}

function stepLightbox(delta) {
  if (!lightboxItems.length) return;
  lightboxIndex = (lightboxIndex + delta + lightboxItems.length) % lightboxItems.length;
  updateLightbox();
}

function currentMediaItems() {
  const result = [];
  dialogContent.querySelectorAll('.media-item').forEach(item => {
    const img = item.querySelector('img');
    if (!item.href) return;
    result.push({ url:item.href, alt:img?.alt || '', kind:item.querySelector('.media-kind') ? 'gif' : 'image' });
  });
  const preview = dialogContent.querySelector('.gameplay-preview-button');
  if (preview?.dataset.mediaUrl) {
    result.unshift({ url:preview.dataset.mediaUrl, alt:preview.querySelector('img')?.alt || '', kind:'gif' });
  }
  return result;
}

async function localizedGameForCurrentLanguage(game, payload = null) {
  if (currentLanguage() !== 'fr') return game;
  try {
    const translations = payload || await loadTranslationsFrPayload();
    return await localizeGameProse(game, translations, 'fr');
  } catch (error) {
    console.debug('French translations unavailable; using English source', error);
    return game;
  }
}

function refreshLocalizedChrome(info) {
  const gallery = info?.querySelector('.dialog-media');
  const galleryTitle = gallery?.querySelector('.dialog-subheading h3');
  if (galleryTitle) galleryTitle.textContent = t('detail.gallery');
  const count = gallery?.querySelector('.dialog-subheading span');
  const mediaCount = gallery?.querySelectorAll('.media-item').length || 0;
  if (count && mediaCount >= 0) count.textContent = mediaCountLabel(mediaCount);
  applyTranslations(info || document);
  if (!dialog.querySelector('.media-lightbox')?.hidden) updateLightbox();
}
function enhanceDialog(game, gameId, { refresh = false } = {}) {
  const layout = currentLayout(gameId);
  const info = layout?.querySelector('.dialog-info');
  if (!layout || !info) return;

  if (layout.dataset.enhanced === 'true' && refresh) {
    renderDescriptionTabs(info, game, { replace:true });
    refreshLocalizedChrome(info);
    applyTranslations(layout);
    return;
  }
  if (layout.dataset.enhanced === 'true') return;

  if (!hasRenderableDetails(game)) {
    layout.classList.remove('dialog-loading');
    info.querySelector('.detail-loading-shell')?.remove();
    const status = info.querySelector('[data-detail-status]');
    status?.classList.remove('sr-only');
    setDetailStatus(info, t('detail.noDetails'), 'empty');
    return;
  }

  layout.dataset.enhanced = 'true';
  info.querySelector('.detail-loading-shell')?.remove();
  info.querySelector('[data-detail-status]')?.remove();
  renderCoverDetails(layout, game);
  renderDescriptionTabs(info, game);
  renderMediaGallery(info, game);
  renderGameplayPreview(info, game);
  refreshLocalizedChrome(info);
  applyTranslations(layout);
}

async function loadDetailsForOpenGame(gameId, detailPath, { refresh = false } = {}) {
  const requestId = ++detailRequestId;
  if (!detailPath) {
    const layout = currentLayout(gameId);
    const info = layout?.querySelector('.dialog-info');
    layout?.classList.remove('dialog-loading');
    info?.querySelector('.detail-loading-shell')?.remove();
    const status = info?.querySelector('[data-detail-status]');
    status?.classList.remove('sr-only');
    setDetailStatus(info, t('detail.missing'), 'missing');
    return;
  }

  try {
    const translationPromise = currentLanguage() === 'fr'
      ? loadTranslationsFrPayload().catch(error => {
          console.debug('French translation snapshot unavailable; using English source', error);
          return null;
        })
      : Promise.resolve(null);
    const [sourceGame, translationPayload] = await Promise.all([
      loadGameDetail(detailPath),
      translationPromise,
    ]);
    if (requestId !== detailRequestId || !dialog.open || !currentLayout(gameId)) return;
    currentSourceGame = sourceGame;
    currentSourceGameId = String(gameId);
    const game = translationPayload
      ? await localizedGameForCurrentLanguage(sourceGame, translationPayload)
      : sourceGame;
    if (requestId !== detailRequestId || !dialog.open || !currentLayout(gameId)) return;
    enhanceDialog(game, gameId, { refresh });
  } catch (error) {
    if (requestId !== detailRequestId || !currentLayout(gameId)) return;
    console.error('Game details unavailable', error);
    const layout = currentLayout(gameId);
    const info = layout?.querySelector('.dialog-info');
    layout?.classList.remove('dialog-loading');
    info?.querySelector('.detail-loading-shell')?.remove();
    const status = info?.querySelector('[data-detail-status]');
    if (status) {
      status.classList.remove('sr-only');
      status.dataset.detailStatus = 'error';
      status.textContent = t('detail.error');
    }
  }
}

document.addEventListener('fitboy:game-open', event => {
  const { gameId, detailPath } = event.detail || {};
  loadDetailsForOpenGame(String(gameId || ''), detailPath || '');
});

document.addEventListener('fitboy:language-change', () => {
  applyTranslations(document);
  const layout = currentLayout();
  if (!dialog.open || !layout) return;
  const gameId = String(layout.dataset.gameId || currentSourceGameId || '');
  const detailPath = layout.dataset.detailPath || '';
  loadDetailsForOpenGame(gameId, detailPath, { refresh:true });
});

dialog.addEventListener('click', event => {
  const preview = event.target.closest('.gameplay-preview-button');
  if (preview) {
    const items = currentMediaItems();
    const index = items.findIndex(item => normalizedUrl(item.url) === normalizedUrl(preview.dataset.mediaUrl));
    openLightbox(items, Math.max(0, index));
    return;
  }

  const media = event.target.closest('.media-item');
  if (!media) return;
  event.preventDefault();
  event.stopPropagation();
  const items = currentMediaItems();
  const index = items.findIndex(item => normalizedUrl(item.url) === normalizedUrl(media.href));
  openLightbox(items, Math.max(0, index));
}, true);

dialog.addEventListener('cancel', event => {
  const box = dialog.querySelector('.media-lightbox');
  if (box && !box.hidden) {
    event.preventDefault();
    closeLightbox();
  }
});

document.addEventListener('keydown', event => {
  const box = dialog.querySelector('.media-lightbox');
  if (!box || box.hidden) return;
  if (event.key === 'ArrowLeft') { event.preventDefault(); stepLightbox(-1); }
  if (event.key === 'ArrowRight') { event.preventDefault(); stepLightbox(1); }
});

dialog.addEventListener('close', () => {
  detailRequestId += 1;
  closeLightbox();
});
