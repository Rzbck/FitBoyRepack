import { loadGameDetail } from './catalog-api.js';

const dialog = document.querySelector('#gameDialog');
const dialogContent = document.querySelector('#dialogContent');

let lightboxItems = [];
let lightboxIndex = 0;
let detailRequestId = 0;

function normalizedUrl(value = '') {
  try {
    const url = new URL(value, window.location.href);
    url.hash = '';
    return url.href.replace(/\/$/, '');
  } catch {
    return String(value || '').replace(/\/$/, '');
  }
}

function titleParts(title = '') {
  const parts = String(title).split(/\s+[–—]\s+/, 2);
  return { name: parts[0]?.trim() || title, version: parts[1]?.trim() || '' };
}

function createPill(text) {
  const span = document.createElement('span');
  span.className = 'genre-pill';
  span.textContent = text;
  return span;
}

function getTags(game) {
  const value = game?.genres ?? game?.genre ?? [];
  return (Array.isArray(value) ? value : String(value || '').split(','))
    .map(item => String(item).trim())
    .filter(Boolean);
}

function formatDate(value) {
  const time = Date.parse(value || '');
  return Number.isFinite(time)
    ? new Intl.DateTimeFormat('fr-FR', { day:'2-digit', month:'short', year:'numeric' }).format(time)
    : 'Date inconnue';
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

function cleanGenreLabel(value) {
  const cleaned = cleanMetadataScalar(value)
    .replace(/\s+video game$/i, '')
    .replace(/\s+computer game$/i, '')
    .replace(/\s+game$/i, '')
    .trim();
  if (!cleaned) return '';

  const aliases = new Map([
    ['grand strategy wargame', 'Grand Strategy'],
    ['role-playing', 'RPG'],
    ['role-playing video', 'RPG'],
    ['real-time strategy', 'Real-Time Strategy'],
    ['turn-based strategy', 'Turn-Based Strategy'],
    ['first-person shooter', 'First-Person Shooter'],
    ['third-person shooter', 'Third-Person Shooter'],
  ]);
  const alias = aliases.get(cleaned.toLowerCase());
  if (alias) return alias;

  return cleaned.replace(/(^|[-\s])\p{L}/gu, match => match.toLocaleUpperCase('fr'));
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

function appendIdentityFact(list, label, value) {
  if (!value) return;
  const row = document.createElement('div');
  row.className = 'identity-fact';
  const term = document.createElement('dt');
  term.textContent = label;
  const description = document.createElement('dd');
  description.textContent = value;
  row.append(term, description);
  list.append(row);
}

function editionLabel(sourceTitle, canonicalTitle) {
  const source = cleanMetadataScalar(sourceTitle);
  const canonical = cleanMetadataScalar(canonicalTitle);
  if (!source || !canonical) return '';
  if (source.localeCompare(canonical, undefined, { sensitivity:'accent' }) === 0) return '';

  const sourceLower = source.toLocaleLowerCase('fr');
  const canonicalLower = canonical.toLocaleLowerCase('fr');
  if (sourceLower.startsWith(canonicalLower)) {
    return source.slice(canonical.length).replace(/^[\s:–—-]+/, '').trim();
  }
  return source;
}

function makeIdentityFacts(game) {
  const metadata = verifiedMetadata(game);
  if (!metadata) return null;

  const facts = document.createElement('section');
  facts.className = 'cover-identity-facts';

  const list = document.createElement('dl');
  list.className = 'identity-fact-list';

  appendIdentityFact(list, 'Développeur', cleanMetadataScalar(metadata.developer));
  appendIdentityFact(list, 'Éditeur', cleanMetadataScalar(metadata.publisher));

  const platforms = cleanMetadataList(metadata.platforms, cleanPlatformLabel);
  appendIdentityFact(list, 'Plateformes', platforms.slice(0, 5).join(' · '));

  if (list.childElementCount) facts.append(list);

  const sources = metadataList(metadata.evidence_urls)
    .map(safeHttpsUrl)
    .filter(Boolean)
    .slice(0, 2);
  if (sources.length) {
    const sourceLine = document.createElement('div');
    sourceLine.className = 'identity-evidence';
    const prefix = document.createElement('span');
    prefix.textContent = 'Données vérifiées';
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

  const initial = cover.querySelector('.cover-details-initial');
  if (initial) initial.remove();
  else if (cover.querySelector('.cover-details')) return;

  layout.classList.add('rich-details');
  layout.classList.remove('dialog-loading');
  const coverImg = cover.querySelector(':scope > img');
  if (coverImg) {
    coverImg.alt = `Jaquette de ${game.title}`;
    coverImg.loading = 'eager';
  }

  const card = document.createElement('div');
  card.className = 'cover-details';

  const metadata = verifiedMetadata(game);
  const meta = document.createElement('div');
  meta.className = 'cover-details-meta';

  const published = document.createElement('span');
  published.innerHTML = `<small>Publié</small><strong>${formatDate(game.post_date)}</strong>`;
  meta.append(published);

  if (metadata?.release_date) {
    const release = document.createElement('span');
    release.innerHTML = `<small>Sortie du jeu</small><strong>${formatDate(metadata.release_date)}</strong>`;
    meta.append(release);
  }

  if (game.repack_size && game.repack_size !== 'N/A') {
    const size = document.createElement('span');
    size.innerHTML = `<small>Taille repack</small><strong>${game.repack_size}</strong>`;
    meta.append(size);
  }
  card.append(meta);

  const enrichedGenres = metadata ? cleanMetadataList(metadata.genres, cleanGenreLabel) : [];
  const tags = enrichedGenres.length ? enrichedGenres : getTags(game);
  if (tags.length) {
    const tagBox = document.createElement('div');
    tagBox.className = 'cover-tags';
    tags.slice(0, 4).forEach(tag => tagBox.append(createPill(tag)));
    card.append(tagBox);
  }

  const parts = titleParts(game.title);
  const canonical = cleanMetadataScalar(metadata?.canonical_title);
  const primaryTitle = canonical || parts.name;

  const h2 = document.createElement('h2');
  h2.className = 'cover-game-title';
  h2.textContent = primaryTitle;
  card.append(h2);

  const edition = canonical ? editionLabel(game.title, canonical) : parts.version;
  if (edition) {
    const version = document.createElement('p');
    version.className = 'cover-game-version cover-edition-title';
    version.textContent = edition;
    card.append(version);
  }

  const identityFacts = makeIdentityFacts(game);
  if (identityFacts) card.append(identityFacts);

  cover.append(card);
  info.querySelector(':scope > h2')?.classList.add('details-moved');
  info.querySelector(':scope > .dialog-meta')?.classList.add('details-moved');
  info.querySelector(':scope > .dialog-genres')?.classList.add('details-moved');
}

function makeTextPanel(title, text) {
  if (!text) return null;
  const panel = document.createElement('section');
  panel.className = 'detail-text-panel';
  const heading = document.createElement('h3');
  heading.textContent = title;
  const body = document.createElement('p');
  body.textContent = text;
  panel.append(heading, body);
  return panel;
}

function makeListPanel(title, items) {
  if (!Array.isArray(items) || !items.length) return null;
  const panel = document.createElement('section');
  panel.className = 'detail-text-panel';
  const heading = document.createElement('h3');
  heading.textContent = title;
  const list = document.createElement('ul');
  items.forEach(item => {
    const li = document.createElement('li');
    li.textContent = item;
    list.append(li);
  });
  panel.append(heading, list);
  return panel;
}

function renderDescriptionTabs(info, game) {
  if (info.querySelector('.detail-tabs')) return;
  const details = game.details || {};
  const panels = [
    ['Description', makeTextPanel('Description', details.description)],
    ['Game Features', makeListPanel('Game Features', details.game_features)],
    ['Repack Features', makeListPanel('Repack Features', details.repack_features)],
  ].filter(([, panel]) => panel);
  if (!panels.length) return;

  const section = document.createElement('section');
  section.className = 'detail-tabs';
  const nav = document.createElement('div');
  nav.className = 'detail-tab-nav';
  const body = document.createElement('div');
  body.className = 'detail-tab-body';

  panels.forEach(([label, panel], index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'detail-tab-btn';
    button.textContent = label;
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
  title.textContent = 'Images & GIFs';
  const count = document.createElement('span');
  count.textContent = `${media.length} média${media.length > 1 ? 's' : ''}`;
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
    img.alt = `Capture de ${game.title}`;
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
  h3.textContent = 'Gameplay Preview';
  const hint = document.createElement('span');
  hint.textContent = 'GIF';
  heading.append(h3, hint);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'gameplay-preview-button';
  button.dataset.mediaUrl = gif.url;
  const img = document.createElement('img');
  img.src = gif.preview_url || gif.url;
  img.alt = `Gameplay de ${game.title}`;
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
  if (count) count.textContent = `${remaining} image${remaining > 1 ? 's' : ''}`;
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
      <button type="button" class="media-lightbox-close" aria-label="Fermer l’image">×</button>
    </div>
    <button type="button" class="media-lightbox-nav media-lightbox-prev" aria-label="Image précédente">‹</button>
    <figure class="media-lightbox-stage"><img alt=""><figcaption></figcaption></figure>
    <button type="button" class="media-lightbox-nav media-lightbox-next" aria-label="Image suivante">›</button>`;
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
  img.alt = item.alt || 'Média du jeu';
  box.querySelector('.media-lightbox-count').textContent = `${lightboxIndex + 1} / ${lightboxItems.length}`;
  box.querySelector('figcaption').textContent = item.kind === 'gif' ? 'GIF gameplay' : 'Capture du jeu';
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

function enhanceDialog(game, gameId) {
  const layout = currentLayout(gameId);
  const info = layout?.querySelector('.dialog-info');
  if (!layout || !info || layout.dataset.enhanced === 'true') return;

  if (!hasRenderableDetails(game)) {
    layout.classList.remove('dialog-loading');
    info.querySelector('.detail-loading-shell')?.remove();
    const status = info.querySelector('[data-detail-status]');
    status?.classList.remove('sr-only');
    setDetailStatus(
      info,
      'Aucun détail enrichi disponible pour cette fiche pour le moment.',
      'empty',
    );
    return;
  }

  layout.dataset.enhanced = 'true';
  info.querySelector('.detail-loading-shell')?.remove();
  info.querySelector('[data-detail-status]')?.remove();
  renderCoverDetails(layout, game);
  renderDescriptionTabs(info, game);
  renderMediaGallery(info, game);
  renderGameplayPreview(info, game);
}

async function loadDetailsForOpenGame(gameId, detailPath) {
  const requestId = ++detailRequestId;
  if (!detailPath) {
    const layout = currentLayout(gameId);
    const info = layout?.querySelector('.dialog-info');
    layout?.classList.remove('dialog-loading');
    info?.querySelector('.detail-loading-shell')?.remove();
    const status = info?.querySelector('[data-detail-status]');
    status?.classList.remove('sr-only');
    setDetailStatus(info, 'Fiche détaillée indisponible pour cette entrée.', 'missing');
    return;
  }

  try {
    const game = await loadGameDetail(detailPath);
    if (requestId !== detailRequestId || !dialog.open || !currentLayout(gameId)) return;
    enhanceDialog(game, gameId);
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
      status.textContent = 'La fiche détaillée est momentanément indisponible.';
    }
  }
}

document.addEventListener('fitboy:game-open', event => {
  const { gameId, detailPath } = event.detail || {};
  loadDetailsForOpenGame(String(gameId || ''), detailPath || '');
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
