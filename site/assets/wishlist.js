import { formatNumber, t } from './i18n.js';
import { displayTitle, normalizeIdentity } from './game-identity.js';

const STORAGE_KEY = 'fitboyrepack:wishlist:v1';
const MAX_ITEMS = 150;
const MAX_TITLE_LENGTH = 140;
let items = readEntries();
let catalog = [];
let catalogReady = false;
let byId = new Map();
let byTitle = new Map();
let openGame = null;
let initialized = false;

function cleanTitle(value) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, MAX_TITLE_LENGTH);
}

function keyOf(value) {
  return normalizeIdentity(String(value || '').replace(/[™®©]/g, ''));
}

// Only strip known repack/edition suffixes, never arbitrary words:
// "Hollow Knight" must not match "Hollow Knight: Silksong".
function reliableRepackBase(value) {
  const raw = String(value || '').trim();
  const dash = /^(.*?)\s+[-–—]\s+(.+)$/.exec(raw);
  if (dash && /^(?:(?:gold|deluxe|ultimate|complete|standard|premium|digital|collector'?s|definitive|anniversary|special)\s+edition\b|(?:v(?:ersion)?[\s.]*\d|build\s*\d|update\s*\d)|(?:\d+\s+dlcs?\b))/i.test(dash[2])) {
    return dash[1];
  }
  const comma = /^(.*?),\s*(.+)$/.exec(raw);
  if (comma && /^(?:v(?:ersion)?[\s.]*\d|build\s*\d|\+\s*\d+\s*dlcs?)\b/i.test(comma[2])) {
    return comma[1];
  }
  return raw;
}

export function titleKeysForGame(game) {
  const keys = new Set();
  const canonical = keyOf(game?.canonical_title || '');
  if (canonical) keys.add(canonical);
  const raw = keyOf(game?.title || '');
  if (raw) keys.add(raw);
  const base = keyOf(reliableRepackBase(game?.title || ''));
  if (base) keys.add(base);
  return [...keys];
}

export function findWishlistGame(title, games) {
  const key = keyOf(title);
  if (!key) return null;
  const matching = (Array.isArray(games) ? games : []).filter(game => titleKeysForGame(game).includes(key));
  return matching.sort((a,b) => Date.parse(b.post_date||'')-Date.parse(a.post_date||''))[0] || null;
}

function safeEntry(row) {
  if (typeof row !== 'object' || !row || Array.isArray(row)) return null;
  if (typeof row.title !== 'string') return null;
  const title = cleanTitle(row.title);
  if (title.length < 2 || !keyOf(title)) return null;
  return {
    title,
    addedAt: typeof row.addedAt === 'string' ? row.addedAt.slice(0, 35) : new Date().toISOString(),
    matchedId: typeof row.matchedId === 'string' ? row.matchedId.slice(0, 180) : '',
    matchedAt: typeof row.matchedAt === 'string' ? row.matchedAt.slice(0, 35) : '',
  };
}
function sanitizeEntries(raw) {
  if (!Array.isArray(raw)) throw new Error('Invalid wishlist');
  if (raw.length > MAX_ITEMS) throw new Error('Wishlist too large');
  const seen = new Set();
  return raw.map(safeEntry).filter(row => {
    if (!row) return false;
    const key = keyOf(row.title);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
function readEntries() {
  try { return sanitizeEntries(JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')); }
  catch { return []; }
}
function save() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(items)); }
  catch { showFeedback(t('wishlist.storageError'), true); }
}
function showFeedback(message='', error=false) {
  const node = document.querySelector('#wishlistFeedback');
  if (!node) return;
  node.textContent = message;
  node.classList.toggle('is-error', !!error);
}
function buildTitleIndex() {
  byId = new Map(catalog.map(game => [String(game.id), game]));
  byTitle = new Map();
  for (const game of catalog) for (const key of titleKeysForGame(game)) {
    if (!byTitle.has(key)) byTitle.set(key, []);
    byTitle.get(key).push(game);
  }
  for (const array of byTitle.values()) array.sort((a,b) => {
    const aa = Date.parse(a.post_date || '') || 0, bb = Date.parse(b.post_date || '') || 0;
    return bb-aa;
  });
}
function foundGame(item) {
  const match = item.matchedId && byId.get(item.matchedId);
  return match || byTitle.get(keyOf(item.title))?.[0] || null;
}
function syncMatches() {
  if (!catalogReady) return;
  let changed = false;
  for (const row of items) {
    const matched = foundGame(row);
    if (matched && row.matchedId !== String(matched.id)) {
      row.matchedId = String(matched.id);
      row.matchedAt = new Date().toISOString();
      changed = true;
    }
  }
  if (changed) save();
}
function counts() {
  let available = 0;
  for (const item of items) if (catalogReady && foundGame(item)) available++;
  return {total:items.length,available,pending:items.length-available};
}

function rowNode(item) {
  const game = catalogReady ? foundGame(item) : null;
  const li = document.createElement('li'); li.className='wishlist-item';
  li.dataset.wishlistKey=keyOf(item.title);
  if (game) li.classList.add('is-available');
  const content = document.createElement('div'); content.className='wishlist-item-content';
  const title = document.createElement('strong'); title.className='wishlist-item-title'; title.textContent=item.title;
  const status = document.createElement('span'); status.className='wishlist-item-status';
  status.textContent=!catalogReady?t('wishlist.checking'):(game?t('wishlist.available'):t('wishlist.pending'));
  content.append(title,status);
  if (game && keyOf(displayTitle(game)) !== keyOf(item.title)) {
    const detail = document.createElement('small'); detail.className='wishlist-item-matched';
    detail.textContent=t('wishlist.matchedTo',{title:displayTitle(game)});
    content.append(detail);
  }
  const actions = document.createElement('div'); actions.className='wishlist-item-actions';
  if (game) {
    const view = document.createElement('button'); view.type='button'; view.className='wishlist-view';
    view.textContent=t('wishlist.view');
    view.addEventListener('click',()=>{
      document.querySelector('#wishlistDialog')?.close();
      openGame?.(game);
    });
    actions.append(view);
  }
  const remove=document.createElement('button');remove.type='button';remove.className='wishlist-remove';
  remove.textContent='×';remove.title=t('wishlist.remove');remove.setAttribute('aria-label',t('wishlist.removeNamed',{title:item.title}));
  remove.addEventListener('click',()=>{
    items=items.filter(record=>keyOf(record.title)!==keyOf(item.title));
    save();showFeedback('');renderWishlist();
  });
  actions.append(remove);
  li.append(content,actions);
  return li;
}

function renderWishlist() {
  const { total, available, pending } = counts();
  for (const label of document.querySelectorAll('[data-wishlist-count]')) label.textContent=formatNumber(total);
  const ready = document.querySelector('#wishlistReadyCount');
  if (ready) { ready.textContent=formatNumber(available);ready.hidden=!available; }
  const sidebarReady = document.querySelector('#wishlistSidebarReady');
  if (sidebarReady) {sidebarReady.hidden=!available;sidebarReady.textContent=formatNumber(available);}
  const meta = document.querySelector('#wishlistSummary');
  if (meta) meta.textContent=!catalogReady?t('wishlist.checking'):
    t('wishlist.summary',{pending:formatNumber(pending),available:formatNumber(available)});
  const list = document.querySelector('#wishlistList');
  if (!list) return;
  list.replaceChildren();
  const sorted=[...items].sort((a,b)=>{
    const diff=Number(Boolean(catalogReady&&foundGame(b)))-Number(Boolean(catalogReady&&foundGame(a)));
    return diff || String(b.addedAt).localeCompare(String(a.addedAt));
  });
  for (const item of sorted) list.append(rowNode(item));
  const empty = document.querySelector('#wishlistEmpty');
  if (empty) empty.hidden=items.length>0;
}

export function setWishlistCatalog(games) {
  catalog = Array.isArray(games) ? games : [];
  catalogReady = true;
  buildTitleIndex();
  syncMatches();
  renderWishlist();
}
export function exportWishlist() { return items.map(row=>({...row})); }
export function importWishlist(raw) {
  items=sanitizeEntries(raw);
  syncMatches();save();renderWishlist();
}
export function openWishlist(prefill='') {
  const dialog=document.querySelector('#wishlistDialog');
  if (!dialog) return;
  renderWishlist();
  const input=document.querySelector('#wishlistInput');
  if (input && prefill) input.value=cleanTitle(prefill);
  showFeedback('');
  if (!dialog.open) dialog.showModal();
  input?.focus();
  input?.select();
}

function addWishlist() {
  const input=document.querySelector('#wishlistInput');
  const title=cleanTitle(input?.value);
  if (!title || keyOf(title).length < 2) {
    showFeedback(t('wishlist.invalid'),true);return;
  }
  if (items.some(item=>keyOf(item.title)===keyOf(title))) {
    showFeedback(t('wishlist.duplicate'),true);return;
  }
  if (items.length>=MAX_ITEMS) {
    showFeedback(t('wishlist.maxItems'),true);return;
  }
  const row={title,addedAt:new Date().toISOString(),matchedId:'',matchedAt:''};
  items.push(row);
  syncMatches();save();renderWishlist();
  if (input) input.value='';
  showFeedback(t('wishlist.added'));
  input?.focus();
}

export function initWishlist({openGame:openGameCallback}={}) {
  if(initialized) return;
  initialized=true;
  openGame=openGameCallback;
  document.querySelectorAll('[data-open-wishlist]').forEach(button=>{
    button.addEventListener('click',()=>openWishlist());
  });
  const dialog=document.querySelector('#wishlistDialog');
  dialog?.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
  document.querySelector('#wishlistClose')?.addEventListener('click',()=>dialog?.close());
  document.querySelector('#wishlistForm')?.addEventListener('submit',event=>{event.preventDefault();addWishlist();});
  document.addEventListener('fitboy:language-change',renderWishlist);
  window.addEventListener('storage',event=>{
    if(event.key===STORAGE_KEY){items=readEntries();syncMatches();renderWishlist();}
  });
  renderWishlist();
}
