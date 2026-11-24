import { loadCatalogPayload, loadSearchIndexPayload, loadHealthPayload, loadSteamRatingsPayload, searchIndexMatchesCatalog } from './catalog-api.js?v=3';
import { createCardWindow } from './card-window.js';
import { normalized, createQueryScorer } from './search-score.js';
import { STORAGE_KEYS, readLibrary, writeLibrary } from './storage.js';
import { initWishlist, setWishlistCatalog, openWishlist, exportWishlist, importWishlist } from './wishlist.js?v=2';
import {
  displayTitle as identityDisplayTitle,
  editionTitle as identityEditionTitle,
  effectiveGenreLabels,
  gameReleaseYear,
} from './game-identity.js';
import {
  applyTranslations,
  currentLanguage,
  formatDateValue,
  formatNumber,
  gameCountLabel,
  initI18n,
  locale,
  t,
} from './i18n.js?v=2';

initI18n();

const PAGE_SIZE = 30;
const RECOMMENDATION_LIMIT = 12;
const HOME_LIMIT = 6;
const LOAD_COOLDOWN_MS = 250;
const SEARCH_DEBOUNCE_MS = 80;
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];

const els = {
  grid: $('#gameGrid'), template: $('#cardTemplate'), search: $('#searchInput'), suggestions: $('#searchSuggestions'), sort: $('#sortControl'),
  count: $('#visibleCount'), status: $('#catalogStatus'), empty: $('#emptyState'), favoritesToggle: $('#favoritesToggle'), activeState: $('#activeState'), catalogHeading: $('#catalogHeading'), catalogResults: $('#catalogResults'), steamSortHint: $('#steamSortHint'),
  dialog: $('#gameDialog'), dialogContent: $('#dialogContent'), tagFilter: $('#tagFilter'), tagList: $('#tagList'), tagSearch: $('#tagSearch'),
  clearTags: $('#clearTags'), selectedTagCount: $('#selectedTagCount'), selectedTagsBar: $('#selectedTagsBar'), tagResultCount: $('#tagResultCount'),
  tagPickerDialog: $('#tagPickerDialog'), openTagPicker: $('#openTagPicker'), closeTagPicker: $('#closeTagPicker'),
  scrollSentinel: $('#scrollSentinel'), infiniteStatus: $('#infiniteStatus'), yearFilter: $('#yearFilter'), releasePeriodFilter: $('#releasePeriodFilter'), sizeFilter: $('#sizeFilter'),
  newOnlyFilter: $('#newOnlyFilter'), detailsOnlyFilter: $('#detailsOnlyFilter'), mediaOnlyFilter: $('#mediaOnlyFilter'), resetFilters: $('#resetFilters'),
  mobileFiltersButton: $('#mobileFiltersButton'), filterSidebar: $('#filterSidebar'), filterOverlay: $('#filterOverlay'), closeFilters: $('#closeFilters'),
  exportLibrary: $('#exportLibrary'), importLibraryButton: $('#importLibraryButton'), importLibrary: $('#importLibrary'),
  favoritesCount: $('#favoritesCount'), backlogCount: $('#backlogCount'), completedCount: $('#completedCount'),
  recommendationSection: $('#recommendationSection'),
  recommendationGrid: $('#recommendationGrid'), recommendationMeta: $('#recommendationMeta'), healthBadge: $('#healthBadge'), healthPanel: $('#healthPanel'),
  healthTotal: $('#healthTotal'), healthDescriptions: $('#healthDescriptions'), healthGalleries: $('#healthGalleries'), healthGifs: $('#healthGifs'), healthMeta: $('#healthMeta')
};

let libraryStorageWarning=false;
function saveLibrary() {
  if(writeLibrary(state.library)){libraryStorageWarning=false;return;}
  if(!libraryStorageWarning){libraryStorageWarning=true;alert(t('wishlist.storageError'));}
}

const state = {
  games: [], byId:new Map(), filtered:[], visible:PAGE_SIZE, selectedTags:new Set(), tagCounts:new Map(), searchIndex:null, steamRatings:new Map(),
  library:readLibrary(), libraryFilter:'', quick:{ newOnly:false, detailsOnly:false, mediaOnly:false },
  dialogGameId:null, dialogScrollY:0, dialogOpener:null, loadingMore:false, lastLoadAt:0, renderGeneration:0, searchTimer:0, suggestionIndex:-1
};

function tokens(value='') { return normalized(value).split(' ').filter(Boolean); }
function searchGrams(token,size=3){const out=[];if(token.length<size)return out;for(let i=0;i<=token.length-size;i++){const gram=token.slice(i,i+size);if(!out.includes(gram))out.push(gram);}return out;}
function indexedTokenCandidates(token){
  const index=state.searchIndex;if(!index||token.length<2)return null;
  const prefixMax=Math.max(2,Number(index.prefix_max)||6),prefixKey=token.slice(0,Math.min(prefixMax,token.length));
  const candidates=new Set(index.prefixes?.[prefixKey]||[]);
  if(token.length>=4){const grams=searchGrams(token,Number(index.gram_size)||3),hits=new Map();for(const gram of grams)for(const ordinal of index.grams?.[gram]||[])hits.set(ordinal,(hits.get(ordinal)||0)+1);const threshold=Math.max(1,Math.ceil(grams.length*.4));for(const [ordinal,count] of hits)if(count>=threshold)candidates.add(ordinal);}
  return candidates;
}
function searchCandidateIndexes(rawQuery){
  if(!state.searchIndex)return null;const qTokens=tokens(rawQuery).filter(token=>token.length>=2);if(!qTokens.length)return null;let result=null;
  for(const token of qTokens){const candidates=indexedTokenCandidates(token);if(!candidates)continue;result=result===null?candidates:new Set([...result].filter(index=>candidates.has(index)));if(!result.size)break;}
  return result;
}
let poolCache=null;
function searchPool(rawQuery){
  const key=normalized(rawQuery);
  if(poolCache?.key===key&&poolCache.index===state.searchIndex&&poolCache.games===state.games)return poolCache.value;
  const indexes=searchCandidateIndexes(key);
  const value=!indexes||!indexes.size?state.games:[...indexes].map(index=>state.games[index]).filter(Boolean);
  poolCache={key,index:state.searchIndex,games:state.games,value};
  return value;
}
function getTags(game) {
  const value = game?.genres ?? game?.genre ?? [];
  return (Array.isArray(value) ? value : String(value || '').split(',')).map(v => String(v).trim()).filter(Boolean);
}
function effectiveTags(game) {
  return effectiveGenreLabels(game);
}
function cardDisplayTitle(game) {
  return String(game?.canonical_title || game?.title || '').trim();
}
function cardDisplayTags(game) {
  return effectiveGenreLabels(game);
}
function gameDate(game) { return game.__postTime ?? (Date.parse(game.post_date||'')||0); }
function releaseDate(game) { return game.__releaseTime ?? (Date.parse(game.game_release_date||'')||0); }
function formatDate(value) { return formatDateValue(value) || (currentLanguage()==='fr'?'Date inconnue':'Unknown date'); }
function isNew(game, days=14) { const t=gameDate(game); return Boolean(t && Date.now()-t < days*86400000); }
function startOfLocalWeek(time=Date.now()) {
  const date=new Date(time);
  const day=(date.getDay()+6)%7;
  date.setHours(0,0,0,0);
  date.setDate(date.getDate()-day);
  return date.getTime();
}
function releasePeriodMatches(game, period) {
  if(!period)return true;
  const t=releaseDate(game);
  if(!t)return false;
  const now=Date.now();
  const day=86400000;
  if(period==='7d')return t>=now-7*day && t<=now;
  if(period==='30d')return t>=now-30*day && t<=now;
  if(period==='90d')return t>=now-90*day && t<=now;
  if(period==='this-year')return new Date(t).getFullYear()===new Date(now).getFullYear();
  const thisWeek=startOfLocalWeek(now);
  if(period==='this-week')return t>=thisWeek && t<=now;
  if(period==='last-week')return t>=thisWeek-7*day && t<thisWeek;
  return true;
}
function ratingFor(game) {
  const row=state.steamRatings.get(game.id);
  return row && row.status==='rated' && Number(row.total_reviews)>0 ? row : null;
}
function steamQuality(game) {
  const row=ratingFor(game);
  if(!row)return -1;
  const n=Number(row.total_reviews), positive=Number(row.positive);
  return (positive+75)/(n+100)*100;
}
function steamHiddenScore(game) {
  const row=ratingFor(game);
  if(!row || row.total_reviews<25 || row.total_reviews>12000)return -1;
  const quality=steamQuality(game);
  if(quality<75)return -1;
  return quality-3.4*Math.log10(Math.max(1,row.total_reviews)/25);
}
function sizeMatches(game, bucket) {
  if (!bucket) return true;
  const mb = Number(game.size_mb);
  if (!Number.isFinite(mb) || mb <= 0) return false;
  if (bucket==='lt1') return mb < 1024;
  if (bucket==='1-10') return mb >= 1024 && mb < 10240;
  if (bucket==='10-50') return mb >= 10240 && mb < 51200;
  return mb >= 51200;
}

const queryScore=createQueryScorer();

function prepareGame(raw) {
  const game={...raw,id:String(raw.id)};
  const tags=effectiveTags(game);
  game.__tagLabels=tags;
  game.__tagKeys=tags.map(normalized);
  game.__tagKeySet=new Set(game.__tagKeys);
  const canonical=String(game.canonical_title||'').trim();
  const releaseYear=gameReleaseYear(game.game_release_date);
  const searchable=[
    game.title,
    canonical,
    game.repack_size,
    releaseYear,
    game.metadata_developer,
    game.metadata_publisher,
    ...(Array.isArray(game.metadata_platforms)?game.metadata_platforms:[]),
    ...tags,
  ];
  game.__titleNorm=normalized(canonical||game.title);
  game.__searchText=normalized(searchable.join(' '));
  game.__searchTokens=[...new Set(game.__searchText.split(' ').filter(Boolean))];
  game.__postTime=Date.parse(game.post_date||'')||0;
  game.__releaseTime=Date.parse(game.game_release_date||'')||0;
  game.__releaseYear=releaseYear;
  return game;
}

function nonTagMatches(game, query) {
  if (state.libraryFilter && !state.library[state.libraryFilter]?.has(game.id)) return false;
  if (els.yearFilter.value && game.__releaseYear!==els.yearFilter.value) return false;
  if (!releasePeriodMatches(game,els.releasePeriodFilter.value)) return false;
  if (!sizeMatches(game,els.sizeFilter.value)) return false;
  if (state.quick.newOnly && !isNew(game,30)) return false;
  if (state.quick.detailsOnly && !game.has_description) return false;
  if (state.quick.mediaOnly && !(game.media_count>0)) return false;
  if (query && !queryScore(game,query)) return false;
  return true;
}

function applyFilters() {
  const query=els.search.value.trim(); const selected=[...state.selectedTags]; const pool=query?searchPool(query):state.games;
  state.filtered=pool.filter(game=>nonTagMatches(game,query) && (!selected.length || selected.every(tag=>game.__tagKeySet.has(tag))));
  const sort=els.sort.value;
  const collator=sort.startsWith("name_")?new Intl.Collator(locale(),{sensitivity:"base"}):null;
  state.filtered.sort((a,b)=>{
    if(sort==='steam_best') return steamQuality(b)-steamQuality(a) || Number(ratingFor(b)?.total_reviews||0)-Number(ratingFor(a)?.total_reviews||0) || gameDate(b)-gameDate(a);
    if(sort==='steam_popular') return Number(ratingFor(b)?.total_reviews||0)-Number(ratingFor(a)?.total_reviews||0) || steamQuality(b)-steamQuality(a);
    if(sort==='steam_hidden') return steamHiddenScore(b)-steamHiddenScore(a) || gameDate(b)-gameDate(a);
    if (sort==='relevance' && query) return queryScore(b,query)-queryScore(a,query) || gameDate(b)-gameDate(a);
    if (sort==='release_desc') return releaseDate(b)-releaseDate(a) || gameDate(b)-gameDate(a);
    if (sort==='release_asc') return releaseDate(a)-releaseDate(b) || gameDate(a)-gameDate(b);
    if (sort==='date_asc') return gameDate(a)-gameDate(b);
    if (sort==='name_asc') return collator.compare(cardDisplayTitle(a),cardDisplayTitle(b));
    if (sort==='name_desc') return collator.compare(cardDisplayTitle(b),cardDisplayTitle(a));
    return gameDate(b)-gameDate(a);
  });
  state.renderGeneration++; state.lastLoadAt=-Infinity;
  state.visible=Math.min(PAGE_SIZE,state.filtered.length); state.loadingMore=false; els.infiniteStatus.hidden=true;
  renderCatalog(); updateTagFacets(state.filtered); renderSuggestions(); armInfiniteObserver();
}

function buildTagIndex() {
  const canonical=new Map(), counts=new Map();
  for (const game of state.games) for (const tag of game.__tagLabels) {
    const key=normalized(tag); if (!key) continue; if (!canonical.has(key)) canonical.set(key,tag);
    counts.set(key,(counts.get(key)||0)+1);
  }
  state.tagCounts=counts;
  const fragment=document.createDocumentFragment();
  [...canonical.entries()].map(([key,label])=>({key,label,count:counts.get(key)||0})).sort((a,b)=>b.count-a.count||a.label.localeCompare(b.label,locale(),{sensitivity:'base'})).forEach((tag,order)=>{
    const button=document.createElement('button'); button.type='button'; button.className='tag-chip'; button.dataset.tagKey=tag.key; button.dataset.tagLabel=tag.label; button.dataset.tagOrder=String(order);
    const label=document.createElement('span'); label.textContent=tag.label; const count=document.createElement('small'); count.textContent=formatNumber(tag.count); button.append(label,count);
    button.addEventListener('click',()=>{ state.selectedTags.has(tag.key)?state.selectedTags.delete(tag.key):state.selectedTags.add(tag.key); updateTagUI(); applyFilters(); });
    fragment.append(button);
  });
  els.tagList.replaceChildren(fragment); updateTagUI(); updateTagFacets();
}

function updateTagUI() {
  els.selectedTagCount.textContent=String(state.selectedTags.size); els.tagFilter.classList.toggle('active',state.selectedTags.size>0);
  els.tagList.querySelectorAll('.tag-chip').forEach(btn=>{ const active=state.selectedTags.has(btn.dataset.tagKey); btn.classList.toggle('active',active); btn.setAttribute('aria-pressed',String(active)); });
  const selected=[...state.selectedTags]; els.selectedTagsBar.hidden=!selected.length; els.selectedTagsBar.replaceChildren();
  for (const key of selected) {
    const source=els.tagList.querySelector(`[data-tag-key="${CSS.escape(key)}"]`); const chip=document.createElement('button'); chip.type='button'; chip.className='selected-filter-chip'; chip.textContent=`${source?.dataset.tagLabel||key} ×`;
    chip.addEventListener('click',()=>{ state.selectedTags.delete(key); updateTagUI(); applyFilters(); }); els.selectedTagsBar.append(chip);
  }
}

function tagMatchRank(label, query) {
  if (label===query) return 0;
  if (label.startsWith(query)) return 1;
  if (label.split(' ').some(word=>word.startsWith(query))) return 2;
  return 3;
}
function updateTagFacets(filtered=null) {
  if (!state.games.length) return;
  const query=els.search.value.trim(), selected=[...state.selectedTags], searchBase=query?searchPool(query):state.games;
  const pool=Array.isArray(filtered)?filtered:searchBase.filter(game=>nonTagMatches(game,query) && selected.every(tag=>game.__tagKeySet.has(tag)));
  const counts=new Map(); for (const game of pool) for (const tag of game.__tagKeySet) counts.set(tag,(counts.get(tag)||0)+1);
  const searchTag=normalized(els.tagSearch.value), buttons=[...els.tagList.querySelectorAll('.tag-chip')];
  const matchedKeys=new Set();
  let matched=0;
  for (const btn of buttons) {
    const key=btn.dataset.tagKey, active=state.selectedTags.has(key), next=active?pool.length:(counts.get(key)||0);
    const matchesSearch=!searchTag||normalized(btn.dataset.tagLabel).includes(searchTag);
    const visible=matchesSearch && (active || next>0);
    btn.hidden=!visible;
    btn.disabled=!active && !next;
    btn.querySelector('small').textContent=formatNumber(next);
    if (visible) {matched++;matchedKeys.add(key);}
  }
  buttons.sort((a,b)=>{
    if (searchTag) {
      const rank=tagMatchRank(normalized(a.dataset.tagLabel),searchTag)-tagMatchRank(normalized(b.dataset.tagLabel),searchTag);
      if (rank) return rank;
    }
    return Number(a.dataset.tagOrder)-Number(b.dataset.tagOrder);
  });
  els.tagList.append(...buttons);
  // Count each game only once when several matching genres share the same game.
  const matchedGames=searchTag?pool.filter(game=>game.__tagKeys.some(tag=>matchedKeys.has(tag))).length:state.filtered.length;
  els.tagResultCount.textContent=searchTag
    ?t(matched===1?'genre.matchingResults.one':'genre.matchingResults.other',{count:formatNumber(matched),games:gameCountLabel(matchedGames)})
    :gameCountLabel(state.filtered.length);
}

function pill(text){const el=document.createElement('span');el.className='genre-pill';el.textContent=text;return el;}
function setLibraryItem(list,id,on){ const set=state.library[list]; if(!set)return; on?set.add(id):set.delete(id); saveLibrary(); updateLibraryUI(); renderRecommendations(); if(list==="favorites")refreshFavoriteCards(id); document.dispatchEvent(new CustomEvent('fitboy:library-change',{detail:{gameId:id,library:snapshotLibrary()}})); }
function toggleFavorite(id){setLibraryItem('favorites',id,!state.library.favorites.has(id)); if(state.libraryFilter==='favorites') applyFilters();}
function refreshFavoriteCards(id){
  const active=state.library.favorites.has(id);
  for(const card of document.querySelectorAll('.game-card[data-game-id]')){
    if(card.dataset.gameId!==id)continue;
    const favorite=card.querySelector('.favorite-btn');if(!favorite)continue;
    favorite.classList.toggle('active',active);favorite.textContent=active?'\u2665':'\u2661';
    favorite.setAttribute('aria-label',t(active?'card.removeFavorite':'card.addFavorite'));
  }
}
function snapshotLibrary(){return Object.fromEntries(Object.entries(state.library).map(([k,v])=>[k,[...v]]));}

function makeVoteThumb(down=false){
  const ns='http://www.w3.org/2000/svg';
  const svg=document.createElementNS(ns,'svg');
  svg.setAttribute('viewBox','0 0 24 24');
  svg.setAttribute('width','12');
  svg.setAttribute('height','12');
  svg.setAttribute('fill','none');
  svg.setAttribute('stroke','currentColor');
  svg.setAttribute('stroke-width','2');
  svg.setAttribute('stroke-linecap','round');
  svg.setAttribute('stroke-linejoin','round');
  svg.setAttribute('aria-hidden','true');
  svg.classList.add('steam-thumb-icon');
  if(down)svg.classList.add('is-down');
  const path1=document.createElementNS(ns,'path');
  path1.setAttribute('d','M7 10v12');
  const path2=document.createElementNS(ns,'path');
  path2.setAttribute('d','M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z');
  svg.append(path1,path2);
  return svg;
}
// Catalog: a single vote row; the opened game sheet retains its full breakdown.
function fillCompactSteamRating(target,rating){
  const percent=Math.max(0,Math.min(100,Number(rating.positive_percent)||0));
  const negative=100-percent;
  const line=document.createElement('div');line.className='steam-votes-inline';
  const vote=(down,value)=>{
    const item=document.createElement('span');
    item.className='steam-mini-vote '+(down?'negative':'positive');
    const number=document.createElement('span');
    number.textContent=`${formatNumber(Math.round(value))}%`;
    item.append(makeVoteThumb(down),number);
    return item;
  };
  const count=document.createElement('span');count.className='steam-mini-count';
  const abbreviated=new Intl.NumberFormat(locale(),{notation:'compact',maximumFractionDigits:1}).format(rating.total_reviews);
  // Only the number stays visible on the artwork; the accessible label has the full count.
  count.textContent=abbreviated;
  line.append(vote(false,percent),vote(true,negative),count);
  target.setAttribute('aria-label',t('rating.barLabel',{
    positive:formatNumber(Math.round(percent)),negative:formatNumber(Math.round(negative))
  })+' · '+t('rating.votes',{count:formatNumber(rating.total_reviews)}));
  target.title=t('rating.barLabel',{
    positive:formatNumber(Math.round(percent)),negative:formatNumber(Math.round(negative))
  })+' · '+t('rating.votes',{count:formatNumber(rating.total_reviews)});
  target.replaceChildren(line);
}
function fillSteamRating(target,rating){
  const percent=Math.max(0,Math.min(100,Number(rating.positive_percent)||0));
  const negative=100-percent;
  const heading=document.createElement('div');heading.className='steam-rating-heading';
  const source=document.createElement('span');source.textContent='Steam';
  const votes=document.createElement('span');votes.textContent=t('rating.votes',{count:formatNumber(rating.total_reviews)});
  heading.append(source,votes);
  const track=document.createElement('div');track.className='steam-rating-track';
  const positiveBar=document.createElement('span');positiveBar.className='steam-rating-positive';positiveBar.style.width=`${percent}%`;
  const negativeBar=document.createElement('span');negativeBar.className='steam-rating-negative';negativeBar.style.width=`${negative}%`;
  track.append(positiveBar,negativeBar);
  track.setAttribute('role','img');
  track.setAttribute('aria-label',t('rating.barLabel',{positive:formatNumber(Math.round(percent)),negative:formatNumber(Math.round(negative))}));
  const split=document.createElement('div');split.className='steam-rating-split';
  const positiveText=document.createElement('span');positiveText.textContent=t('rating.positivePercent',{percent:formatNumber(Math.round(percent))});
  const negativeText=document.createElement('span');negativeText.textContent=t('rating.negativePercent',{percent:formatNumber(Math.round(negative))});
  split.append(positiveText,negativeText);
  target.replaceChildren(heading,track,split);
}
function applyRatingLabel(card,game) {
  const target=card.querySelector('.cover-wrap > .steam-rating');if(!target)return;
  const rating=ratingFor(game);
  target.hidden=!rating;
  if(rating) fillCompactSteamRating(target,rating);
  else {target.replaceChildren();target.removeAttribute('aria-label');target.removeAttribute('title');}
}
function updateRatingLabels(){
  document.querySelectorAll('.game-card[data-game-id]').forEach(card=>{
    const game=state.byId.get(card.dataset.gameId);
    if(game)applyRatingLabel(card,game);
  });
}
function renderCard(game,compact=false){
  const card=els.template.content.firstElementChild.cloneNode(true), image=card.querySelector('.cover'), open=card.querySelector('.card-open'), favorite=card.querySelector('.favorite-btn');
  card.dataset.gameId=game.id;
  if(compact)card.classList.add('compact-card');
  applyTranslations(card);
  const displayTitle=cardDisplayTitle(game);
  card.querySelector('.card-title').textContent=displayTitle;
  const releaseNode=card.querySelector('.card-date');
  const verifiedRelease=Boolean(game.game_release_date && releaseDate(game));
  releaseNode.hidden=!verifiedRelease;
  releaseNode.textContent=verifiedRelease ? formatDate(game.game_release_date) : '';
  if(verifiedRelease){
    releaseNode.title=`${t('detail.releaseDate')}: ${formatDate(game.game_release_date)} · ${t('detail.published')}: ${formatDate(game.post_date)}`;
  }else releaseNode.removeAttribute('title');
  const sizeNode=card.querySelector('.card-size');
  sizeNode.textContent=game.repack_size!=='N/A'?(game.repack_size||''):'';
  card.querySelector('.card-meta').hidden=!verifiedRelease&&!sizeNode.textContent;
  applyRatingLabel(card,game);
  if(displayTitle && displayTitle!==game.title) card.title=game.title;
  if(game.image_url){
    image.fetchPriority='low'; image.src=game.image_url;
    image.alt=currentLanguage()==='fr'?`Illustration de ${displayTitle||game.title}`:`Cover art for ${displayTitle||game.title}`;
    image.addEventListener('error',()=>{image.style.display='none';},{once:true});
  }else image.style.display='none';
  card.querySelector('.new-badge').hidden=!isNew(game);
  const tagRow=card.querySelector('.genre-row'), tags=cardDisplayTags(game);
  tags.slice(0,2).forEach(tag=>tagRow.append(pill(tag)));
  if(tags.length>2) tagRow.title=tags.join(' · ');
  const active=state.library.favorites.has(game.id);
  favorite.classList.toggle('active',active); favorite.textContent=active?'♥':'♡';
  favorite.setAttribute('aria-label',t(active?'card.removeFavorite':'card.addFavorite'));
  favorite.addEventListener('click',e=>{e.stopPropagation();toggleFavorite(game.id);});
  open.addEventListener('click',()=>openDialog(game,{syncUrl:true}));
  return card;
}
function updateCatalogMeta(){
  const label=gameCountLabel(state.filtered.length);
  els.count.textContent=formatNumber(state.filtered.length);
  els.tagResultCount.textContent=label;
  els.empty.hidden=state.filtered.length!==0;
  const isEmptyFavorites=state.libraryFilter==='favorites' && state.library.favorites.size===0;
  els.empty.querySelector('strong').textContent=t(isEmptyFavorites?'library.emptyFavoritesTitle':'empty.title');
  els.empty.querySelector('span').textContent=t(isEmptyFavorites?'library.emptyFavoritesBody':'empty.body');
  els.empty.querySelector('.empty-wishlist-add')?.remove();
  const missingQuery=els.search.value.trim();
  if(state.filtered.length===0 && missingQuery.length>=2 && !state.libraryFilter){
    const add=document.createElement('button');
    add.type='button';add.className='empty-wishlist-add';add.textContent=t('wishlist.addThis');
    add.addEventListener('click',()=>openWishlist(missingQuery));
    els.empty.append(add);
  }
  const headingKey=state.libraryFilter==='favorites'?'library.myFavorites':state.libraryFilter==='backlog'?'library.backlog':state.libraryFilter==='completed'?'library.completed':'catalog.title';
  els.catalogHeading.textContent=t(headingKey);
  const steamSorting=els.sort.value.startsWith('steam_');
  els.steamSortHint.hidden=!steamSorting;
  if(steamSorting){
    const rated=state.filtered.filter(game=>ratingFor(game)).length;
    els.steamSortHint.textContent=t('rating.coverage',{rated:formatNumber(rated),total:formatNumber(state.filtered.length)});
  }
  const hasMore=state.visible<state.filtered.length;
  els.scrollSentinel.hidden=!hasMore;
  if(!hasMore)els.infiniteStatus.hidden=true;
  const active=[];
  if(els.search.value.trim())active.push(t('filter.searchPrefix',{value:els.search.value.trim()}));
  if(state.selectedTags.size)active.push(t(state.selectedTags.size===1?'filter.genreCount.one':'filter.genreCount.other',{count:state.selectedTags.size}));
  if(els.yearFilter.value)active.push(t('filter.releasePrefix',{value:els.yearFilter.value}));
  if(els.releasePeriodFilter.value)active.push(els.releasePeriodFilter.options[els.releasePeriodFilter.selectedIndex].text);
  if(els.sizeFilter.value)active.push(t('filter.sizePrefix',{value:els.sizeFilter.options[els.sizeFilter.selectedIndex].text}));
  if(state.quick.newOnly)active.push(t('filter.addedRecently'));
  if(state.quick.detailsOnly)active.push(t('filter.description'));
  if(state.quick.mediaOnly)active.push(t('filter.media'));
  if(state.libraryFilter)active.push(t(state.libraryFilter==='favorites'?'library.favorite':state.libraryFilter==='backlog'?'library.backlog':'library.completed'));
  els.activeState.hidden=!active.length;
  els.activeState.textContent=active.length?`${active.join(' • ')} • ${label}`:'';
  els.favoritesToggle.classList.toggle('active',state.libraryFilter==='favorites');
  els.favoritesToggle.setAttribute('aria-pressed',String(state.libraryFilter==='favorites'));
}
const cardWindow=createCardWindow(els.grid,renderCard,{protectedNode:()=>state.dialogOpener});
function renderCatalog({append=false,start=0}={}){
  if(!append)cardWindow.reset();
  cardWindow.append(state.filtered.slice(start,Math.min(state.visible,state.filtered.length)));
  updateCatalogMeta();
}
function loadNextPage(){
  if(state.loadingMore||state.visible>=state.filtered.length)return;
  const now=performance.now();
  if(now-state.lastLoadAt<LOAD_COOLDOWN_MS)return;
  state.loadingMore=true;state.lastLoadAt=now;
  const generation=state.renderGeneration,start=state.visible;
  infiniteObserver.unobserve(els.scrollSentinel);els.infiniteStatus.hidden=false;
  requestAnimationFrame(()=>{
    if(generation!==state.renderGeneration)return;
    state.visible=Math.min(state.visible+PAGE_SIZE,state.filtered.length);
    renderCatalog({append:true,start});els.infiniteStatus.hidden=true;
    setTimeout(()=>{if(generation!==state.renderGeneration)return;state.loadingMore=false;armInfiniteObserver();},LOAD_COOLDOWN_MS);
  });
}
const infiniteObserver=new IntersectionObserver(entries=>{if(entries.some(e=>e.target===els.scrollSentinel&&e.isIntersecting))loadNextPage();},{root:null,rootMargin:'350px 0px',threshold:.01});
function armInfiniteObserver(){infiniteObserver.unobserve(els.scrollSentinel);if(state.loadingMore||els.scrollSentinel.hidden)return;requestAnimationFrame(()=>{if(!state.loadingMore&&!els.scrollSentinel.hidden)infiniteObserver.observe(els.scrollSentinel);});}
infiniteObserver.observe(els.scrollSentinel);

function titleAffinityTokens(title){const stop=new Set(['the','a','an','of','and','edition','deluxe','complete','ultimate','remastered','remake','goty','version','v','build','update','dlc']);return tokens(title).filter(t=>t.length>2&&!stop.has(t)&&!/^[0-9]+$/.test(t));}
function recommendationScores(){
  const sourceWeights={favorites:3,backlog:2,completed:.35},profile=new Map(),titleProfile=new Map(),sourceIds=new Set();
  for(const [list,weight] of Object.entries(sourceWeights))for(const id of state.library[list]){const game=state.byId.get(id);if(!game)continue;sourceIds.add(id);for(const tag of new Set(game.__tagKeys))profile.set(tag,(profile.get(tag)||0)+weight);for(const token of titleAffinityTokens(game.title))titleProfile.set(token,(titleProfile.get(token)||0)+weight);}
  if(!sourceIds.size)return[];const total=Math.max(1,state.games.length),now=Date.now(),scored=[];
  for(const game of state.games){if(sourceIds.has(game.id)||state.library.completed.has(game.id))continue;let score=0,shared=0;for(const tag of new Set(game.__tagKeys)){const interest=profile.get(tag)||0;if(!interest)continue;const rarity=Math.log((total+1)/((state.tagCounts.get(tag)||1)+1))+1;score+=interest*rarity;shared++;}for(const token of titleAffinityTokens(game.title))score+=(titleProfile.get(token)||0)*1.35;const ageDays=Math.max(0,(now-gameDate(game))/86400000);score+=Math.max(0,1-ageDays/730)*.45+(game.has_description?.12:0)+(game.media_count?.08:0);if(score>0)scored.push({game,score,shared});}
  return scored.sort((a,b)=>b.score-a.score||b.shared-a.shared||gameDate(b.game)-gameDate(a.game));
}
function renderRow(grid,games){const f=document.createDocumentFragment();for(const game of games.slice(0,HOME_LIMIT))f.append(renderCard(game,true));grid.replaceChildren(f);}
function renderRecommendations(){
  const enabled=state.libraryFilter==='favorites' && state.library.favorites.size>0;
  const picks=enabled?recommendationScores().slice(0,RECOMMENDATION_LIMIT):[];
  const visible=picks.length>0;
  els.recommendationSection.hidden=!visible;
  els.catalogResults.classList.toggle('with-suggestions',visible);
  if(!visible){els.recommendationGrid.replaceChildren();return;}
  renderRow(els.recommendationGrid,picks.map(x=>x.game));
  els.recommendationMeta.textContent=t('library.recommendationHint');
}
function renderSuggestions(){
  const q=els.search.value.trim(); if(q.length<2){els.suggestions.hidden=true;els.suggestions.replaceChildren();state.suggestionIndex=-1;return;}
  const picks=searchPool(q).map(game=>({game,score:queryScore(game,q)})).filter(x=>x.score>0).sort((a,b)=>b.score-a.score||gameDate(b.game)-gameDate(a.game)).slice(0,8); if(!picks.length){els.suggestions.hidden=true;return;}
  const f=document.createDocumentFragment();picks.forEach(({game},i)=>{const b=document.createElement('button');b.type='button';b.className='search-suggestion';b.setAttribute('role','option');b.dataset.index=String(i);b.innerHTML=`<span></span><small></small>`;b.querySelector('span').textContent=cardDisplayTitle(game);b.querySelector('small').textContent=[game.__releaseYear,...game.__tagLabels.slice(0,2)].filter(Boolean).join(' • ');b.addEventListener('click',()=>{els.suggestions.hidden=true;openDialog(game,{syncUrl:true});});f.append(b);});els.suggestions.replaceChildren(f);els.suggestions.hidden=false;state.suggestionIndex=-1;
}
function stepSuggestion(delta){const items=$$('.search-suggestion');if(!items.length)return;state.suggestionIndex=(state.suggestionIndex+delta+items.length)%items.length;items.forEach((b,i)=>b.classList.toggle('active',i===state.suggestionIndex));items[state.suggestionIndex].scrollIntoView({block:'nearest'});}

function updateLibraryUI(){els.favoritesCount.textContent=state.library.favorites.size;els.backlogCount.textContent=state.library.backlog.size;els.completedCount.textContent=state.library.completed.size;$$('.library-filter').forEach(b=>{const active=b.dataset.library===state.libraryFilter;b.setAttribute('aria-pressed',String(active));b.classList.toggle('active',active);});}
function setLibraryFilter(list){state.libraryFilter=state.libraryFilter===list?'':list;updateLibraryUI();applyFilters();renderRecommendations();closeMobileFilters();}
function exportLibrary(){const blob=new Blob([JSON.stringify({version:3,exported_at:new Date().toISOString(),...snapshotLibrary(),wishlist:exportWishlist()},null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='fitboyrepack-library.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
async function importLibrary(file){try{const data=JSON.parse(await file.text());if(Object.hasOwn(data,'wishlist'))importWishlist(data.wishlist);for(const key of ['favorites','backlog','completed'])if(Array.isArray(data[key]))state.library[key]=new Set(data[key].map(String));saveLibrary();updateLibraryUI();renderRecommendations();applyFilters();}catch(error){console.error(error);alert(t('library.invalidFile'));}finally{els.importLibrary.value='';}}

function toggleQuick(key,button){state.quick[key]=!state.quick[key];button.setAttribute('aria-pressed',String(state.quick[key]));button.classList.toggle('active',state.quick[key]);applyFilters();}
function resetFilters(){els.search.value='';els.tagSearch.value='';els.yearFilter.value='';els.releasePeriodFilter.value='';els.sizeFilter.value='';state.selectedTags.clear();state.libraryFilter='';for(const key of Object.keys(state.quick))state.quick[key]=false;for(const b of [els.newOnlyFilter,els.detailsOnlyFilter,els.mediaOnlyFilter]){b.setAttribute('aria-pressed','false');b.classList.remove('active');}updateTagUI();updateLibraryUI();applyFilters();renderRecommendations();}
function populateYears(){const years=[...new Set(state.games.map(g=>g.__releaseYear).filter(Boolean))].sort((a,b)=>b-a);for(const year of years){const o=document.createElement('option');o.value=year;o.textContent=year;els.yearFilter.append(o);}}

function openTagPicker(){if(!els.tagPickerDialog.open)els.tagPickerDialog.showModal();requestAnimationFrame(()=>els.tagSearch.focus());}
function closeTagPicker(){if(els.tagPickerDialog.open)els.tagPickerDialog.close();}
function openMobileFilters(){els.filterSidebar.classList.add('mobile-open');els.filterOverlay.hidden=false;els.mobileFiltersButton.setAttribute('aria-expanded','true');}
function closeMobileFilters(){els.filterSidebar.classList.remove('mobile-open');els.filterOverlay.hidden=true;els.mobileFiltersButton.setAttribute('aria-expanded','false');}

function lockCatalogScroll(){state.dialogScrollY=window.scrollY;const gap=Math.max(0,window.innerWidth-document.documentElement.clientWidth);document.documentElement.classList.add('dialog-scroll-locked');document.body.classList.add('dialog-scroll-locked');Object.assign(document.body.style,{position:'fixed',top:`-${state.dialogScrollY}px`,left:'0',right:'0',width:'100%'});if(gap)document.body.style.paddingRight=`${gap}px`;}
function unlockCatalogScroll(){const top=state.dialogScrollY;document.documentElement.classList.remove('dialog-scroll-locked');document.body.classList.remove('dialog-scroll-locked');for(const p of ['position','top','left','right','width','paddingRight'])document.body.style[p]='';window.scrollTo({top,left:0,behavior:'auto'});}
function gameHashId(){return window.location.hash.startsWith('#')?(new URLSearchParams(window.location.hash.slice(1)).get('game')||''):'';}
function syncGameHash(id){const hash=`#game=${encodeURIComponent(id)}`;if(window.location.hash!==hash)history.replaceState(history.state,'',`${window.location.pathname}${window.location.search}${hash}`);}
function clearGameHash(){if(gameHashId())history.replaceState(history.state,'',`${window.location.pathname}${window.location.search}`);}

function refreshCollectionButton(button,list,gameId,labelKey){
  const on=state.library[list].has(gameId);
  button.classList.toggle('active',on);
  button.setAttribute('aria-pressed',String(on));
  button.textContent=(on?'\u2713 ':'')+t(labelKey);
}
function refreshDialogCollections(){
  if(!els.dialog.open||!state.dialogGameId)return;
  for(const button of els.dialog.querySelectorAll('[data-collection-list]')){
    refreshCollectionButton(button,button.dataset.collectionList,state.dialogGameId,button.dataset.collectionLabel);
  }
}
function collectionButton(labelKey,list,gameId,actionType){
  const b=document.createElement('button');b.type='button';b.className='dialog-action';
  b.dataset.actionType=actionType;b.dataset.collectionList=list;b.dataset.collectionLabel=labelKey;
  const refresh=()=>refreshCollectionButton(b,list,gameId,labelKey);
  refresh();b.addEventListener('click',()=>{setLibraryItem(list,gameId,!state.library[list].has(gameId));refresh();if(state.libraryFilter===list)applyFilters();});
  return b;
}

function appendInitialIdentityFact(meta,labelKey,value,{dateValue=''}={}){
  if(!value)return;
  const box=document.createElement('span');
  const small=document.createElement('small');
  small.dataset.i18n=labelKey;
  small.textContent=t(labelKey);
  const strong=document.createElement('strong');
  strong.textContent=value;
  if(dateValue)strong.dataset.i18nDate=dateValue;
  box.append(small,strong);
  meta.append(box);
}

function cleanInitialMetadataScalar(value){
  const text=String(value||'').replace(/\s+/g,' ').trim();
  return text && !/^Q\d+$/i.test(text) ? text : '';
}

function cleanInitialPlatformLabel(value){
  const text=cleanInitialMetadataScalar(value);
  if(!text)return '';
  const aliases=new Map([
    ['microsoft windows','Windows'],
    ['windows','Windows'],
    ['mac os','macOS'],
    ['macos','macOS'],
    ['mac','macOS'],
    ['xbox series x and series s','Xbox Series X/S'],
    ['xbox series x/s','Xbox Series X/S'],
    ['playstation 5','PlayStation 5'],
    ['playstation 4','PlayStation 4'],
    ['nintendo switch','Nintendo Switch'],
  ]);
  return aliases.get(text.toLowerCase())||text;
}

function cleanInitialList(value,cleaner=cleanInitialMetadataScalar){
  const out=[];
  const seen=new Set();
  for(const item of Array.isArray(value)?value:[]){
    const cleaned=cleaner(item);
    const key=normalized(cleaned);
    if(!cleaned||!key||seen.has(key))continue;
    seen.add(key);
    out.push(cleaned);
  }
  return out;
}

function safeInitialHttpsUrl(value){
  try{
    const url=new URL(String(value||''));
    return url.protocol==='https:'?url:null;
  }catch{return null;}
}

function initialMetadataSourceLabel(url){
  const host=url.hostname.toLowerCase();
  if(host==='www.wikidata.org')return 'Wikidata';
  if(host.endsWith('.wikipedia.org'))return 'Wikipedia';
  return host;
}

function buildInitialVerifiedIdentity(game){
  if(!game?.metadata_ready)return null;
  const developer=cleanInitialMetadataScalar(game.metadata_developer);
  const publisher=cleanInitialMetadataScalar(game.metadata_publisher);
  const platforms=cleanInitialList(game.metadata_platforms,cleanInitialPlatformLabel).slice(0,5);
  const sources=(Array.isArray(game.metadata_evidence_urls)?game.metadata_evidence_urls:[])
    .map(safeInitialHttpsUrl).filter(Boolean).slice(0,2);
  if(!developer&&!publisher&&!platforms.length&&!sources.length)return null;

  const facts=document.createElement('section');
  facts.className='cover-identity-facts';
  facts.dataset.initialVerified='true';

  const list=document.createElement('dl');
  list.className='identity-fact-list';

  const appendFact=(labelKey,value)=>{
    if(!value)return;
    const row=document.createElement('div');
    row.className='identity-fact';
    const term=document.createElement('dt');
    term.dataset.i18n=labelKey;
    term.textContent=t(labelKey);
    const description=document.createElement('dd');
    description.textContent=value;
    row.append(term,description);
    list.append(row);
  };

  appendFact('detail.developer',developer);
  appendFact('detail.publisher',publisher);
  appendFact('detail.platforms',platforms.join(' · '));
  if(list.childElementCount)facts.append(list);

  if(sources.length){
    const sourceLine=document.createElement('div');
    sourceLine.className='identity-evidence';
    const prefix=document.createElement('span');
    prefix.dataset.i18n='detail.verified';
    prefix.textContent=t('detail.verified');
    sourceLine.append(prefix);
    for(const url of sources){
      const link=document.createElement('a');
      link.href=url.href;
      link.target='_blank';
      link.rel='noopener noreferrer';
      link.textContent=`${initialMetadataSourceLabel(url)} ↗`;
      sourceLine.append(link);
    }
    facts.append(sourceLine);
  }

  return facts;
}

function buildInitialCoverIdentity(cover,game){
  const card=document.createElement('div');
  card.className='cover-details cover-details-initial';

  const meta=document.createElement('div');
  meta.className='cover-details-meta';
  appendInitialIdentityFact(meta,'detail.published',formatDate(game.post_date),{dateValue:game.post_date});
  if(game.game_release_date)appendInitialIdentityFact(meta,'detail.releaseDate',formatDate(game.game_release_date),{dateValue:game.game_release_date});
  if(game.repack_size&&game.repack_size!=='N/A')appendInitialIdentityFact(meta,'detail.repackSize',game.repack_size);
  card.append(meta);

  const tags=cardDisplayTags(game);
  if(tags.length){
    const tagBox=document.createElement('div');
    tagBox.className='cover-tags';
    tags.forEach(tag=>tagBox.append(pill(tag)));
    card.append(tagBox);
  }

  const title=document.createElement('h2');
  title.className='cover-game-title';
  title.textContent=identityDisplayTitle(game)||game.title;
  card.append(title);

  const edition=identityEditionTitle(game);
  if(edition){
    const subtitle=document.createElement('p');
    subtitle.className='cover-game-version cover-edition-title';
    subtitle.textContent=edition;
    card.append(subtitle);
  }

  const verifiedIdentity=buildInitialVerifiedIdentity(game);
  if(verifiedIdentity)card.append(verifiedIdentity);

  cover.append(card);
}

function buildDetailLoadingShell(){
  const shell=document.createElement('div');
  shell.className='detail-loading-shell';
  shell.setAttribute('aria-busy','true');
  shell.setAttribute('aria-label',t('detail.loadingAria'));
  for(const cls of ['detail-loading-tabs','detail-loading-copy','detail-loading-media']){
    const block=document.createElement('div');
    block.className=cls;
    shell.append(block);
  }
  return shell;
}

function syncDialogSteamRating(game){
  const layout=els.dialogContent.querySelector('.dialog-layout');
  if(!layout || layout.dataset.gameId!==game.id)return;
  const rating=ratingFor(game);
  layout.steamRating=rating;
  const card=layout.querySelector('.cover-details');
  if(!card)return;
  let summary=card.querySelector('.dialog-steam-rating');
  if(!rating){summary?.remove();}
  else{
    if(!summary){
      summary=document.createElement('div');
      summary.className='dialog-steam-rating';
      const facts=card.querySelector('.cover-identity-facts');
      if(facts)card.insertBefore(summary,facts);
      else card.append(summary);
    }
    summary.classList.add('steam-rating');
    fillSteamRating(summary,rating);
  }

}

function openDialog(game,{syncUrl=true}={}){
  const first=!els.dialog.open;
  if(first){
    state.dialogOpener=document.activeElement instanceof HTMLElement?document.activeElement:null;
    lockCatalogScroll();
  }
  state.dialogGameId=game.id;

  const layout=document.createElement('div');
  layout.className='dialog-layout rich-details dialog-loading';
  layout.dataset.gameId=game.id;
  layout.dataset.detailPath=game.detail_path||'';

  const cover=document.createElement('div');
  cover.className='dialog-cover';

  if(game.image_url){
    const img=document.createElement('img');
    img.src=game.image_url;
    img.alt=currentLanguage()==='fr'?`Jaquette de ${identityDisplayTitle(game)||game.title}`:`Cover of ${identityDisplayTitle(game)||game.title}`;
    img.loading='eager';
    img.referrerPolicy='no-referrer';
    img.addEventListener('error',()=>img.remove(),{once:true});
    cover.append(img);
  }

  buildInitialCoverIdentity(cover,game);

  const actions=document.createElement('div');
  actions.className='dialog-actions';
  actions.append(
    collectionButton('detail.favorite','favorites',game.id,'favorite'),
    collectionButton('detail.backlog','backlog',game.id,'backlog'),
    collectionButton('detail.completed','completed',game.id,'completed'),
  );

  const share=document.createElement('button');
  share.type='button';
  share.className='dialog-action';
  share.dataset.actionType='share';
  share.textContent=t('detail.share');
  share.addEventListener('click',async()=>{
    const url=`${location.origin}${location.pathname}#game=${encodeURIComponent(game.id)}`;
    try{
      await navigator.clipboard.writeText(url);
      share.dataset.copied='true';
      share.textContent=t('detail.shareCopied');
      setTimeout(()=>{share.dataset.copied='false';share.textContent=t('detail.share');},1500);
    }catch{
      prompt(t('detail.copyPrompt'),url);
    }
  });
  actions.append(share);
  cover.append(actions);

  const source=game.source_url||'';
  if(source){
    const link=document.createElement('a');
    link.className='source-link';
    link.href=source;
    link.target='_blank';
    link.rel='noopener noreferrer';
    link.dataset.i18n='detail.source';
    link.textContent=t('detail.source');
    cover.append(link);
  }

  const info=document.createElement('div');
  info.className='dialog-info';
  info.append(buildDetailLoadingShell());

  const detailStatus=document.createElement('p');
  detailStatus.className='dialog-note sr-only';
  detailStatus.dataset.detailStatus='loading';
  detailStatus.textContent=(game.details_ready||game.metadata_ready)?t('detail.loading'):t('detail.enriching');
  info.append(detailStatus);

  layout.append(cover,info);
  els.dialogContent.replaceChildren(layout);
  syncDialogSteamRating(game);
  if(first)els.dialog.showModal();
  if(syncUrl)syncGameHash(game.id);

  document.dispatchEvent(new CustomEvent('fitboy:game-open',{
    detail:{gameId:game.id,detailPath:game.detail_path||''}
  }));
}
function isLightboxOpen(){const box=els.dialog.querySelector('.media-lightbox');return Boolean(box&&!box.hidden);}
function navigateDialog(delta){if(!els.dialog.open||isLightboxOpen()||state.filtered.length<2)return;const current=state.filtered.findIndex(g=>g.id===state.dialogGameId);if(current<0)return;openDialog(state.filtered[(current+delta+state.filtered.length)%state.filtered.length],{syncUrl:true});}
function restoreCatalogPosition(){const opener=state.dialogOpener;state.dialogGameId=null;state.dialogOpener=null;clearGameHash();unlockCatalogScroll();requestAnimationFrame(()=>{try{if(opener?.isConnected)opener.focus({preventScroll:true});cardWindow.prune();}catch{}});}
function openHashGame(){const id=gameHashId();if(!id)return;const game=state.byId.get(id);if(game)openDialog(game,{syncUrl:false});}

function renderHealth(health){
  els.healthPanel.hidden=false;
  els.healthBadge.hidden=false;
  els.healthBadge.textContent=`${health.coverage?.details||0}% ${currentLanguage()==='fr'?'fiches':'details'}`;
  els.healthTotal.textContent=formatNumber(health.total_games);
  els.healthDescriptions.textContent=formatNumber(health.with_description);
  els.healthGalleries.textContent=formatNumber(health.with_gallery);
  els.healthGifs.textContent=formatNumber(health.with_gif);
  const when=health.generated_at?formatDateValue(health.generated_at,{dateStyle:'short',timeStyle:'short'}):'';
  const sync=when?t('health.sync',{value:when}):'';
  els.healthMeta.textContent=t('health.remaining',{count:formatNumber(health.enrichment_pending),sync});
}

let lastCatalogPayload=null;
let lastHealthPayload=null;
function showCatalogTimestamp(generated){
  if(!generated){
    els.status.textContent=gameCountLabel(state.games.length);
    els.status.removeAttribute('title');
    return;
  }
  els.status.textContent=t('catalog.updatedCompact',{value:formatDateValue(generated,{
    day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false
  })});
  els.status.title=t('catalog.updated',{value:formatDateValue(generated,{
    dateStyle:'full',timeStyle:'short'
  })});
}
async function loadCatalog(){
  try{
    const payload=await loadCatalogPayload();
    lastCatalogPayload=payload;
    state.games=payload.games.filter(g=>g?.id&&g?.title).map(prepareGame);
    state.byId=new Map(state.games.map(g=>[g.id,g]));
    setWishlistCatalog(state.games);
    showCatalogTimestamp(payload.generated_at);
    populateYears();
    buildTagIndex();
    updateLibraryUI();
    applyFilters();
    
    renderRecommendations();
    openHashGame();
    loadSearchIndexPayload().then(index=>{
      if(!searchIndexMatchesCatalog(index,payload)||index.count!==state.games.length)throw new Error(`Search index count ${index.count} != catalog ${state.games.length}`);
      state.searchIndex=index;
      if(els.search.value.trim())applyFilters();
    }).catch(e=>console.warn('Search index unavailable, using full scan',e));
    loadHealthPayload().then(health=>{lastHealthPayload=health;renderHealth(health);}).catch(e=>console.warn('Health unavailable',e));
    loadSteamRatingsPayload().then(payload=>{
      state.steamRatings=new Map(Object.entries(payload.games));
      if(els.dialog.open){
        const game=state.byId.get(state.dialogGameId);
        if(game)syncDialogSteamRating(game);
      }
      if(els.sort.value.startsWith('steam_'))applyFilters();
      else updateRatingLabels();
      renderRecommendations();
    }).catch(error=>console.warn('Steam ratings unavailable, keeping classic catalog sorting',error));
  }catch(error){
    console.error(error);
    els.status.textContent=t('catalog.unavailable');
    els.empty.hidden=false;
    els.empty.querySelector('strong').textContent=t('catalog.loadFailed');
  }
}

document.addEventListener('fitboy:language-change',()=>{
  applyTranslations(document);
  if(lastCatalogPayload?.generated_at){
    showCatalogTimestamp(lastCatalogPayload.generated_at);
  }
  if(lastHealthPayload)renderHealth(lastHealthPayload);
  buildTagIndex();
  applyFilters();
  if(els.dialog.open){
    const game=state.byId.get(state.dialogGameId);
    if(game)syncDialogSteamRating(game);
    refreshDialogCollections();
  }
  renderRecommendations();
});

els.search.addEventListener('input',()=>{clearTimeout(state.searchTimer);state.searchTimer=setTimeout(applyFilters,SEARCH_DEBOUNCE_MS);});
els.search.addEventListener('keydown',event=>{if(!els.suggestions.hidden&&(event.key==='ArrowDown'||event.key==='ArrowUp')){event.preventDefault();stepSuggestion(event.key==='ArrowDown'?1:-1);return;}if(event.key==='Enter'&&state.suggestionIndex>=0){event.preventDefault();$$('.search-suggestion')[state.suggestionIndex]?.click();}});
els.search.addEventListener('blur',()=>setTimeout(()=>{els.suggestions.hidden=true;},150));
els.tagSearch.addEventListener('input',updateTagFacets);els.clearTags.addEventListener('click',()=>{state.selectedTags.clear();els.tagSearch.value='';updateTagUI();applyFilters();});els.sort.addEventListener('change',applyFilters);els.yearFilter.addEventListener('change',applyFilters);els.releasePeriodFilter.addEventListener('change',applyFilters);els.sizeFilter.addEventListener('change',applyFilters);
els.newOnlyFilter.addEventListener('click',()=>toggleQuick('newOnly',els.newOnlyFilter));els.detailsOnlyFilter.addEventListener('click',()=>toggleQuick('detailsOnly',els.detailsOnlyFilter));els.mediaOnlyFilter.addEventListener('click',()=>toggleQuick('mediaOnly',els.mediaOnlyFilter));els.resetFilters.addEventListener('click',resetFilters);
document.querySelectorAll('.library-filter[data-library]').forEach(b=>b.addEventListener('click',()=>setLibraryFilter(b.dataset.library)));els.favoritesToggle.addEventListener('click',()=>setLibraryFilter('favorites'));els.exportLibrary.addEventListener('click',exportLibrary);els.importLibraryButton.addEventListener('click',()=>els.importLibrary.click());els.importLibrary.addEventListener('change',()=>{if(els.importLibrary.files[0])importLibrary(els.importLibrary.files[0]);});
els.openTagPicker.addEventListener('click',openTagPicker);els.closeTagPicker.addEventListener('click',closeTagPicker);els.tagPickerDialog.addEventListener('click',event=>{if(event.target===els.tagPickerDialog)closeTagPicker();});
els.mobileFiltersButton.addEventListener('click',openMobileFilters);els.closeFilters.addEventListener('click',closeMobileFilters);els.filterOverlay.addEventListener('click',closeMobileFilters);
els.dialog.addEventListener('click',e=>{if(e.target===els.dialog||e.target.closest('[data-close-dialog]'))els.dialog.close();});els.dialog.addEventListener('close',restoreCatalogPosition);
window.addEventListener('hashchange',()=>{const id=gameHashId();if(!id&&els.dialog.open)els.dialog.close();else if(id&&state.byId.has(id)&&id!==state.dialogGameId)openDialog(state.byId.get(id),{syncUrl:false});});
document.addEventListener('keydown',event=>{const typing=['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName);if(els.dialog.open&&!typing&&!isLightboxOpen()){if(event.key==='ArrowLeft'){event.preventDefault();navigateDialog(-1);return;}if(event.key==='ArrowRight'){event.preventDefault();navigateDialog(1);return;}}if(event.key==='/'&&!typing){event.preventDefault();els.search.focus();}if(event.key==='Escape'){if(els.tagPickerDialog.open)closeTagPicker();else closeMobileFilters();}});
window.addEventListener('resize',armInfiniteObserver,{passive:true});
window.addEventListener('storage',event=>{
  if(event.key!==STORAGE_KEYS.library && event.key!==STORAGE_KEYS.legacyFavorites && event.key!==null)return;
  const next=readLibrary(),previous=state.library;
  const changed=Object.keys(next).filter(key=>next[key].size!==previous[key].size||[...next[key]].some(id=>!previous[key].has(id)));
  if(!changed.length)return;
  state.library=next;
  updateLibraryUI();refreshDialogCollections();
  if(changed.includes(state.libraryFilter))applyFilters();
  else if(changed.includes('favorites')){
    for(const id of new Set([...previous.favorites,...next.favorites])){
      if(previous.favorites.has(id)!==next.favorites.has(id))refreshFavoriteCards(id);
    }
  }
  renderRecommendations();
});
initWishlist({openGame:game=>{closeMobileFilters();openDialog(game,{syncUrl:true});}});
document.querySelector('#wishlistLibraryButton')?.addEventListener('click',closeMobileFilters);
loadCatalog();