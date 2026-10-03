import { loadCatalogPayload, loadSearchIndexPayload, loadHealthPayload } from './catalog-api.js';
import {
  displayTitle as identityDisplayTitle,
  editionTitle as identityEditionTitle,
  effectiveGenreLabels,
} from './game-identity.js';

const PAGE_SIZE = 30;
const RECOMMENDATION_LIMIT = 12;
const HOME_LIMIT = 10;
const LEGACY_FAVORITES_KEY = 'fitboyrepack:favorites:v1';
const LIBRARY_KEY = 'fitboyrepack:library:v2';
const LOAD_COOLDOWN_MS = 250;
const SEARCH_DEBOUNCE_MS = 80;
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];

const els = {
  grid: $('#gameGrid'), template: $('#cardTemplate'), search: $('#searchInput'), suggestions: $('#searchSuggestions'), sort: $('#sortControl'),
  count: $('#visibleCount'), status: $('#catalogStatus'), empty: $('#emptyState'), favoritesToggle: $('#favoritesToggle'), activeState: $('#activeState'),
  dialog: $('#gameDialog'), dialogContent: $('#dialogContent'), tagFilter: $('#tagFilter'), tagList: $('#tagList'), tagSearch: $('#tagSearch'),
  clearTags: $('#clearTags'), selectedTagCount: $('#selectedTagCount'), selectedTagsBar: $('#selectedTagsBar'), tagResultCount: $('#tagResultCount'),
  tagPickerDialog: $('#tagPickerDialog'), openTagPicker: $('#openTagPicker'), closeTagPicker: $('#closeTagPicker'),
  scrollSentinel: $('#scrollSentinel'), infiniteStatus: $('#infiniteStatus'), yearFilter: $('#yearFilter'), releasePeriodFilter: $('#releasePeriodFilter'), sizeFilter: $('#sizeFilter'),
  newOnlyFilter: $('#newOnlyFilter'), detailsOnlyFilter: $('#detailsOnlyFilter'), mediaOnlyFilter: $('#mediaOnlyFilter'), resetFilters: $('#resetFilters'),
  mobileFiltersButton: $('#mobileFiltersButton'), filterSidebar: $('#filterSidebar'), filterOverlay: $('#filterOverlay'), closeFilters: $('#closeFilters'),
  exportLibrary: $('#exportLibrary'), importLibraryButton: $('#importLibraryButton'), importLibrary: $('#importLibrary'),
  favoritesCount: $('#favoritesCount'), backlogCount: $('#backlogCount'), completedCount: $('#completedCount'),
  newSection: $('#newSection'), newGrid: $('#newGrid'), updatedSection: $('#updatedSection'), updatedGrid: $('#updatedGrid'),
  librarySection: $('#librarySection'), libraryGrid: $('#libraryGrid'), recommendationSection: $('#recommendationSection'),
  recommendationGrid: $('#recommendationGrid'), recommendationMeta: $('#recommendationMeta'), healthBadge: $('#healthBadge'), healthPanel: $('#healthPanel'),
  healthTotal: $('#healthTotal'), healthDescriptions: $('#healthDescriptions'), healthGalleries: $('#healthGalleries'), healthGifs: $('#healthGifs'), healthMeta: $('#healthMeta')
};

function emptyLibrary() { return { favorites:new Set(), backlog:new Set(), completed:new Set() }; }
function readLibrary() {
  const out = emptyLibrary();
  try {
    const parsed = JSON.parse(localStorage.getItem(LIBRARY_KEY) || '{}');
    for (const key of Object.keys(out)) out[key] = new Set(Array.isArray(parsed[key]) ? parsed[key].map(String) : []);
  } catch { /* keep empty */ }
  try {
    for (const id of JSON.parse(localStorage.getItem(LEGACY_FAVORITES_KEY) || '[]')) out.favorites.add(String(id));
  } catch { /* noop */ }
  return out;
}
function saveLibrary() {
  const payload = Object.fromEntries(Object.entries(state.library).map(([key, set]) => [key, [...set]]));
  localStorage.setItem(LIBRARY_KEY, JSON.stringify(payload));
  localStorage.setItem(LEGACY_FAVORITES_KEY, JSON.stringify([...state.library.favorites]));
}

const state = {
  games: [], byId:new Map(), filtered:[], visible:PAGE_SIZE, selectedTags:new Set(), tagCounts:new Map(), searchIndex:null,
  library:readLibrary(), libraryFilter:'', quick:{ newOnly:false, detailsOnly:false, mediaOnly:false },
  dialogGameId:null, dialogScrollY:0, dialogOpener:null, loadingMore:false, lastLoadAt:0, searchTimer:0, suggestionIndex:-1
};

function normalized(value='') {
  return String(value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').replace(/\s+/g,' ').trim();
}
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
function searchPool(rawQuery){const indexes=searchCandidateIndexes(rawQuery);if(!indexes||!indexes.size)return state.games;return [...indexes].map(index=>state.games[index]).filter(Boolean);}
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
function gameDate(game) { const t=Date.parse(game.post_date||''); return Number.isFinite(t)?t:0; }
function releaseDate(game) { const t=Date.parse(game.game_release_date||''); return Number.isFinite(t)?t:0; }
function formatDate(value) { const t=Date.parse(value||''); return Number.isFinite(t)?new Intl.DateTimeFormat('fr-FR',{day:'2-digit',month:'short',year:'numeric'}).format(t):'Date inconnue'; }
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
function sizeMatches(game, bucket) {
  if (!bucket) return true;
  const mb = Number(game.size_mb);
  if (!Number.isFinite(mb) || mb <= 0) return false;
  if (bucket==='lt1') return mb < 1024;
  if (bucket==='1-10') return mb >= 1024 && mb < 10240;
  if (bucket==='10-50') return mb >= 10240 && mb < 51200;
  return mb >= 51200;
}

function boundedDistance(a,b,max) {
  if (Math.abs(a.length-b.length)>max) return max+1;
  let prev=Array.from({length:b.length+1},(_,i)=>i);
  for (let i=1;i<=a.length;i++) {
    const cur=[i]; let rowMin=i;
    for (let j=1;j<=b.length;j++) {
      const val=Math.min(cur[j-1]+1,prev[j]+1,prev[j-1]+(a[i-1]===b[j-1]?0:1));
      cur[j]=val; rowMin=Math.min(rowMin,val);
    }
    if (rowMin>max) return max+1;
    prev=cur;
  }
  return prev[b.length];
}

function queryScore(game, rawQuery) {
  const query=normalized(rawQuery);
  if (!query) return 1;
  if (game.__titleNorm===query) return 500;
  if (game.__titleNorm.startsWith(query)) return 420-query.length*.01;
  if (game.__titleNorm.includes(query)) return 360-query.length*.01;
  if (game.__searchText.includes(query)) return 300;
  const qTokens=query.split(' ');
  let total=0;
  for (const q of qTokens) {
    let best=0;
    for (const candidate of game.__searchTokens) {
      if (candidate===q) { best=90; break; }
      if (candidate.startsWith(q)) best=Math.max(best,75);
      else if (candidate.includes(q)) best=Math.max(best,58);
      else if (q.length>=4 && Math.abs(candidate.length-q.length)<=2) {
        const max=q.length<=5?1:2;
        const d=boundedDistance(q,candidate,max);
        if (d<=max) best=Math.max(best,48-d*8);
      }
    }
    if (!best) return 0;
    total+=best;
  }
  return total;
}

function prepareGame(raw) {
  const game={...raw,id:String(raw.id)};
  const tags=effectiveTags(game);
  game.__tagLabels=tags;
  game.__tagKeys=tags.map(normalized);
  game.__tagKeySet=new Set(game.__tagKeys);
  const canonical=String(game.canonical_title||'').trim();
  const releaseYear=/^(20\d{2})/.exec(String(game.game_release_date||''))?.[1]||'';
  const searchable=[game.title,canonical,game.repack_size,releaseYear,...tags];
  game.__titleNorm=normalized(canonical||game.title);
  game.__searchText=normalized(searchable.join(' '));
  game.__searchTokens=[...new Set(tokens(searchable.join(' ')))];
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
  state.filtered.sort((a,b)=>{
    if (sort==='relevance' && query) return queryScore(b,query)-queryScore(a,query) || gameDate(b)-gameDate(a);
    if (sort==='release_desc') return releaseDate(b)-releaseDate(a) || gameDate(b)-gameDate(a);
    if (sort==='release_asc') return releaseDate(a)-releaseDate(b) || gameDate(a)-gameDate(b);
    if (sort==='date_asc') return gameDate(a)-gameDate(b);
    if (sort==='name_asc') return cardDisplayTitle(a).localeCompare(cardDisplayTitle(b),'fr',{sensitivity:'base'});
    if (sort==='name_desc') return cardDisplayTitle(b).localeCompare(cardDisplayTitle(a),'fr',{sensitivity:'base'});
    return gameDate(b)-gameDate(a);
  });
  state.visible=Math.min(PAGE_SIZE,state.filtered.length); state.loadingMore=false;
  renderCatalog(); updateTagFacets(); renderSuggestions(); armInfiniteObserver();
}

function buildTagIndex() {
  const canonical=new Map(), counts=new Map();
  for (const game of state.games) for (const tag of game.__tagLabels) {
    const key=normalized(tag); if (!key) continue; if (!canonical.has(key)) canonical.set(key,tag);
    counts.set(key,(counts.get(key)||0)+1);
  }
  state.tagCounts=counts;
  const fragment=document.createDocumentFragment();
  [...canonical.entries()].map(([key,label])=>({key,label,count:counts.get(key)||0})).sort((a,b)=>b.count-a.count||a.label.localeCompare(b.label,'fr')).forEach(tag=>{
    const button=document.createElement('button'); button.type='button'; button.className='tag-chip'; button.dataset.tagKey=tag.key; button.dataset.tagLabel=tag.label;
    const label=document.createElement('span'); label.textContent=tag.label; const count=document.createElement('small'); count.textContent=tag.count.toLocaleString('fr-FR'); button.append(label,count);
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

function updateTagFacets() {
  if (!state.games.length) return;
  const query=els.search.value.trim(), selected=[...state.selectedTags], searchBase=query?searchPool(query):state.games;
  const pool=searchBase.filter(game=>nonTagMatches(game,query) && selected.every(tag=>game.__tagKeySet.has(tag)));
  const counts=new Map(); for (const game of pool) for (const tag of game.__tagKeySet) counts.set(tag,(counts.get(tag)||0)+1);
  const searchTag=normalized(els.tagSearch.value);
  els.tagList.querySelectorAll('.tag-chip').forEach(btn=>{
    const key=btn.dataset.tagKey, active=state.selectedTags.has(key), next=active?pool.length:(counts.get(key)||0), visibleBySearch=active||!searchTag||normalized(btn.dataset.tagLabel).includes(searchTag);
    btn.hidden=!active && (!next || !visibleBySearch); btn.disabled=!active && !next; btn.querySelector('small').textContent=next.toLocaleString('fr-FR');
  });
  els.tagResultCount.textContent=`${state.filtered.length.toLocaleString('fr-FR')} jeu${state.filtered.length>1?'x':''}`;
}

function pill(text){const el=document.createElement('span');el.className='genre-pill';el.textContent=text;return el;}
function setLibraryItem(list,id,on){ const set=state.library[list]; if(!set)return; on?set.add(id):set.delete(id); saveLibrary(); updateLibraryUI(); renderHighlights(); renderRecommendations(); document.dispatchEvent(new CustomEvent('fitboy:library-change',{detail:{gameId:id,library:snapshotLibrary()}})); }
function toggleFavorite(id){setLibraryItem('favorites',id,!state.library.favorites.has(id)); if(state.libraryFilter==='favorites') applyFilters(); else renderCatalog();}
function snapshotLibrary(){return Object.fromEntries(Object.entries(state.library).map(([k,v])=>[k,[...v]]));}

function renderCard(game,compact=false){
  const card=els.template.content.firstElementChild.cloneNode(true), image=card.querySelector('.cover'), open=card.querySelector('.card-open'), favorite=card.querySelector('.favorite-btn'); card.dataset.gameId=game.id; if(compact)card.classList.add('compact-card');
  const displayTitle=cardDisplayTitle(game);
  card.querySelector('.card-title').textContent=displayTitle; card.querySelector('.card-date').textContent=formatDate(game.post_date); card.querySelector('.card-size').textContent=game.repack_size!=='N/A'?(game.repack_size||''):'';
  if(displayTitle && displayTitle!==game.title) card.title=game.title;
  if(game.image_url){image.fetchPriority='low';image.src=game.image_url;image.alt=`Illustration de ${displayTitle||game.title}`;image.addEventListener('error',()=>{image.style.display='none';},{once:true});}else image.style.display='none';
  card.querySelector('.new-badge').hidden=!isNew(game);
  const tagRow=card.querySelector('.genre-row'), tags=cardDisplayTags(game);
  tags.slice(0,2).forEach(tag=>tagRow.append(pill(tag)));
  if(tags.length>2) tagRow.title=tags.join(' · ');
  const active=state.library.favorites.has(game.id); favorite.classList.toggle('active',active); favorite.textContent=active?'♥':'♡'; favorite.setAttribute('aria-label',active?'Retirer des favoris':'Ajouter aux favoris'); favorite.addEventListener('click',e=>{e.stopPropagation();toggleFavorite(game.id);});
  open.addEventListener('click',()=>openDialog(game,{syncUrl:true})); return card;
}

function updateCatalogMeta(){
  const label=`${state.filtered.length.toLocaleString('fr-FR')} jeu${state.filtered.length>1?'x':''}`; els.count.textContent=state.filtered.length.toLocaleString('fr-FR'); els.tagResultCount.textContent=label; els.empty.hidden=state.filtered.length!==0;
  const hasMore=state.visible<state.filtered.length; els.scrollSentinel.hidden=!hasMore; if(!hasMore)els.infiniteStatus.hidden=true;
  const active=[]; if(els.search.value.trim())active.push(`Recherche : ${els.search.value.trim()}`); if(state.selectedTags.size)active.push(`${state.selectedTags.size} genre${state.selectedTags.size>1?'s':''}`); if(els.yearFilter.value)active.push(`Sortie ${els.yearFilter.value}`); if(els.releasePeriodFilter.value)active.push(els.releasePeriodFilter.options[els.releasePeriodFilter.selectedIndex].text); if(els.sizeFilter.value)active.push(`Taille ${els.sizeFilter.options[els.sizeFilter.selectedIndex].text}`); if(state.quick.newOnly)active.push('Ajoutés récemment'); if(state.quick.detailsOnly)active.push('Description'); if(state.quick.mediaOnly)active.push('Médias'); if(state.libraryFilter)active.push($('.library-filter[aria-pressed="true"]')?.textContent.trim()||state.libraryFilter);
  els.activeState.hidden=!active.length; els.activeState.textContent=active.length?`${active.join(' • ')} • ${label}`:'';
  els.favoritesToggle.classList.toggle('active',state.libraryFilter==='favorites'); els.favoritesToggle.setAttribute('aria-pressed',String(state.libraryFilter==='favorites'));
}
function renderCatalog({append=false,start=0}={}){const end=Math.min(state.visible,state.filtered.length),fragment=document.createDocumentFragment();for(let i=start;i<end;i++)fragment.append(renderCard(state.filtered[i]));append?els.grid.append(fragment):els.grid.replaceChildren(fragment);updateCatalogMeta();}

function loadNextPage(){if(state.loadingMore||state.visible>=state.filtered.length)return;const now=performance.now();if(now-state.lastLoadAt<LOAD_COOLDOWN_MS)return;state.loadingMore=true;state.lastLoadAt=now;infiniteObserver.unobserve(els.scrollSentinel);els.infiniteStatus.hidden=false;const start=state.visible;requestAnimationFrame(()=>{state.visible=Math.min(state.visible+PAGE_SIZE,state.filtered.length);renderCatalog({append:true,start});els.infiniteStatus.hidden=true;setTimeout(()=>{state.loadingMore=false;armInfiniteObserver();},LOAD_COOLDOWN_MS);});}
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
function renderRecommendations(){const picks=recommendationScores().slice(0,RECOMMENDATION_LIMIT);els.recommendationSection.hidden=!picks.length;if(!picks.length){els.recommendationGrid.replaceChildren();return;}renderRow(els.recommendationGrid,picks.map(x=>x.game));const n=state.library.favorites.size+state.library.backlog.size;els.recommendationMeta.textContent=`Profil local basé sur ${n} choix, tags rares, fraîcheur et proximité des titres.`;}
function renderHighlights(){const newest=[...state.games].sort((a,b)=>gameDate(b)-gameDate(a)).filter(g=>isNew(g,30));els.newSection.hidden=!newest.length;if(newest.length)renderRow(els.newGrid,newest);const updated=[...state.games].filter(g=>g.detail_updated_at).sort((a,b)=>Date.parse(b.detail_updated_at)-Date.parse(a.detail_updated_at));els.updatedSection.hidden=!updated.length;if(updated.length)renderRow(els.updatedGrid,updated);const backlog=[...state.library.backlog].map(id=>state.byId.get(id)).filter(Boolean);els.librarySection.hidden=!backlog.length;if(backlog.length)renderRow(els.libraryGrid,backlog);}

function renderSuggestions(){
  const q=els.search.value.trim(); if(q.length<2){els.suggestions.hidden=true;els.suggestions.replaceChildren();state.suggestionIndex=-1;return;}
  const picks=searchPool(q).map(game=>({game,score:queryScore(game,q)})).filter(x=>x.score>0).sort((a,b)=>b.score-a.score||gameDate(b.game)-gameDate(a.game)).slice(0,8); if(!picks.length){els.suggestions.hidden=true;return;}
  const f=document.createDocumentFragment();picks.forEach(({game},i)=>{const b=document.createElement('button');b.type='button';b.className='search-suggestion';b.setAttribute('role','option');b.dataset.index=String(i);b.innerHTML=`<span></span><small></small>`;b.querySelector('span').textContent=cardDisplayTitle(game);b.querySelector('small').textContent=[game.__releaseYear,...game.__tagLabels.slice(0,2)].filter(Boolean).join(' • ');b.addEventListener('click',()=>{els.suggestions.hidden=true;openDialog(game,{syncUrl:true});});f.append(b);});els.suggestions.replaceChildren(f);els.suggestions.hidden=false;state.suggestionIndex=-1;
}
function stepSuggestion(delta){const items=$$('.search-suggestion');if(!items.length)return;state.suggestionIndex=(state.suggestionIndex+delta+items.length)%items.length;items.forEach((b,i)=>b.classList.toggle('active',i===state.suggestionIndex));items[state.suggestionIndex].scrollIntoView({block:'nearest'});}

function updateLibraryUI(){els.favoritesCount.textContent=state.library.favorites.size;els.backlogCount.textContent=state.library.backlog.size;els.completedCount.textContent=state.library.completed.size;$$('.library-filter').forEach(b=>{const active=b.dataset.library===state.libraryFilter;b.setAttribute('aria-pressed',String(active));b.classList.toggle('active',active);});}
function setLibraryFilter(list){state.libraryFilter=state.libraryFilter===list?'':list;updateLibraryUI();applyFilters();closeMobileFilters();}
function exportLibrary(){const blob=new Blob([JSON.stringify({version:2,exported_at:new Date().toISOString(),...snapshotLibrary()},null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='fitboyrepack-library.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
async function importLibrary(file){try{const data=JSON.parse(await file.text());for(const key of ['favorites','backlog','completed'])if(Array.isArray(data[key]))state.library[key]=new Set(data[key].map(String));saveLibrary();updateLibraryUI();renderHighlights();renderRecommendations();applyFilters();}catch(error){console.error(error);alert('Fichier de bibliothèque invalide.');}finally{els.importLibrary.value='';}}

function toggleQuick(key,button){state.quick[key]=!state.quick[key];button.setAttribute('aria-pressed',String(state.quick[key]));button.classList.toggle('active',state.quick[key]);applyFilters();}
function resetFilters(){els.search.value='';els.tagSearch.value='';els.yearFilter.value='';els.releasePeriodFilter.value='';els.sizeFilter.value='';state.selectedTags.clear();state.libraryFilter='';for(const key of Object.keys(state.quick))state.quick[key]=false;for(const b of [els.newOnlyFilter,els.detailsOnlyFilter,els.mediaOnlyFilter]){b.setAttribute('aria-pressed','false');b.classList.remove('active');}updateTagUI();updateLibraryUI();applyFilters();}
function populateYears(){const years=[...new Set(state.games.map(g=>g.__releaseYear).filter(y=>/^20\d\d$/.test(y)))].sort((a,b)=>b-a);for(const year of years){const o=document.createElement('option');o.value=year;o.textContent=year;els.yearFilter.append(o);}}

function openTagPicker(){if(!els.tagPickerDialog.open)els.tagPickerDialog.showModal();requestAnimationFrame(()=>els.tagSearch.focus());}
function closeTagPicker(){if(els.tagPickerDialog.open)els.tagPickerDialog.close();}
function openMobileFilters(){els.filterSidebar.classList.add('mobile-open');els.filterOverlay.hidden=false;els.mobileFiltersButton.setAttribute('aria-expanded','true');}
function closeMobileFilters(){els.filterSidebar.classList.remove('mobile-open');els.filterOverlay.hidden=true;els.mobileFiltersButton.setAttribute('aria-expanded','false');}

function lockCatalogScroll(){state.dialogScrollY=window.scrollY;const gap=Math.max(0,window.innerWidth-document.documentElement.clientWidth);document.documentElement.classList.add('dialog-scroll-locked');document.body.classList.add('dialog-scroll-locked');Object.assign(document.body.style,{position:'fixed',top:`-${state.dialogScrollY}px`,left:'0',right:'0',width:'100%'});if(gap)document.body.style.paddingRight=`${gap}px`;}
function unlockCatalogScroll(){const top=state.dialogScrollY;document.documentElement.classList.remove('dialog-scroll-locked');document.body.classList.remove('dialog-scroll-locked');for(const p of ['position','top','left','right','width','paddingRight'])document.body.style[p]='';window.scrollTo({top,left:0,behavior:'auto'});}
function gameHashId(){return window.location.hash.startsWith('#')?(new URLSearchParams(window.location.hash.slice(1)).get('game')||''):'';}
function syncGameHash(id){const hash=`#game=${encodeURIComponent(id)}`;if(window.location.hash!==hash)history.replaceState(history.state,'',`${window.location.pathname}${window.location.search}${hash}`);}
function clearGameHash(){if(gameHashId())history.replaceState(history.state,'',`${window.location.pathname}${window.location.search}`);}

function collectionButton(label,list,gameId){const b=document.createElement('button');b.type='button';b.className='dialog-action';const refresh=()=>{const on=state.library[list].has(gameId);b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on));b.textContent=`${on?'✓ ':''}${label}`;};refresh();b.addEventListener('click',()=>{setLibraryItem(list,gameId,!state.library[list].has(gameId));refresh();if(list==='favorites')renderCatalog();});return b;}

function appendInitialIdentityFact(meta,label,value){
  if(!value)return;
  const box=document.createElement('span');
  const small=document.createElement('small');
  small.textContent=label;
  const strong=document.createElement('strong');
  strong.textContent=value;
  box.append(small,strong);
  meta.append(box);
}

function buildInitialCoverIdentity(cover,game){
  const card=document.createElement('div');
  card.className='cover-details cover-details-initial';

  const meta=document.createElement('div');
  meta.className='cover-details-meta';
  appendInitialIdentityFact(meta,'Publié',formatDate(game.post_date));
  if(game.game_release_date)appendInitialIdentityFact(meta,'Sortie du jeu',formatDate(game.game_release_date));
  if(game.repack_size&&game.repack_size!=='N/A')appendInitialIdentityFact(meta,'Taille repack',game.repack_size);
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

  cover.append(card);
}

function buildDetailLoadingShell(){
  const shell=document.createElement('div');
  shell.className='detail-loading-shell';
  shell.setAttribute('aria-busy','true');
  shell.setAttribute('aria-label','Chargement de la fiche');
  for(const cls of ['detail-loading-tabs','detail-loading-copy','detail-loading-media']){
    const block=document.createElement('div');
    block.className=cls;
    shell.append(block);
  }
  return shell;
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
    img.alt=`Jaquette de ${identityDisplayTitle(game)||game.title}`;
    img.loading='eager';
    img.referrerPolicy='no-referrer';
    img.addEventListener('error',()=>img.remove(),{once:true});
    cover.append(img);
  }

  buildInitialCoverIdentity(cover,game);

  const actions=document.createElement('div');
  actions.className='dialog-actions';
  actions.append(
    collectionButton('Favori','favorites',game.id),
    collectionButton('À jouer','backlog',game.id),
    collectionButton('Terminé','completed',game.id),
  );

  const share=document.createElement('button');
  share.type='button';
  share.className='dialog-action';
  share.textContent='Partager';
  share.addEventListener('click',async()=>{
    const url=`${location.origin}${location.pathname}#game=${encodeURIComponent(game.id)}`;
    try{
      await navigator.clipboard.writeText(url);
      share.textContent='Lien copié ✓';
      setTimeout(()=>share.textContent='Partager',1500);
    }catch{
      prompt('Copier ce lien :',url);
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
    link.textContent='Voir la page source ↗';
    cover.append(link);
  }

  const info=document.createElement('div');
  info.className='dialog-info';
  info.append(buildDetailLoadingShell());

  const detailStatus=document.createElement('p');
  detailStatus.className='dialog-note sr-only';
  detailStatus.dataset.detailStatus='loading';
  detailStatus.textContent=(game.details_ready||game.metadata_ready)?'Chargement de la fiche détaillée…':'Fiche détaillée en cours d’enrichissement.';
  info.append(detailStatus);

  layout.append(cover,info);
  els.dialogContent.replaceChildren(layout);
  if(first)els.dialog.showModal();
  if(syncUrl)syncGameHash(game.id);

  document.dispatchEvent(new CustomEvent('fitboy:game-open',{
    detail:{gameId:game.id,detailPath:game.detail_path||''}
  }));
}
function isLightboxOpen(){const box=els.dialog.querySelector('.media-lightbox');return Boolean(box&&!box.hidden);}
function navigateDialog(delta){if(!els.dialog.open||isLightboxOpen()||state.filtered.length<2)return;const current=state.filtered.findIndex(g=>g.id===state.dialogGameId);if(current<0)return;openDialog(state.filtered[(current+delta+state.filtered.length)%state.filtered.length],{syncUrl:true});}
function restoreCatalogPosition(){const opener=state.dialogOpener;state.dialogGameId=null;state.dialogOpener=null;clearGameHash();unlockCatalogScroll();requestAnimationFrame(()=>{try{if(opener?.isConnected)opener.focus({preventScroll:true});}catch{}});}
function openHashGame(){const id=gameHashId();if(!id)return;const game=state.byId.get(id);if(game)openDialog(game,{syncUrl:false});}

function renderHealth(health){els.healthPanel.hidden=false;els.healthBadge.hidden=false;els.healthBadge.textContent=`${health.coverage?.details||0}% fiches`;els.healthTotal.textContent=health.total_games.toLocaleString('fr-FR');els.healthDescriptions.textContent=health.with_description.toLocaleString('fr-FR');els.healthGalleries.textContent=health.with_gallery.toLocaleString('fr-FR');els.healthGifs.textContent=health.with_gif.toLocaleString('fr-FR');const when=health.generated_at?new Intl.DateTimeFormat('fr-FR',{dateStyle:'short',timeStyle:'short'}).format(new Date(health.generated_at)):'';els.healthMeta.textContent=`${health.enrichment_pending.toLocaleString('fr-FR')} fiches restent à enrichir${when?` • synchro ${when}`:''}.`;}

async function loadCatalog(){try{const payload=await loadCatalogPayload();state.games=payload.games.filter(g=>g?.id&&g?.title).map(prepareGame);state.byId=new Map(state.games.map(g=>[g.id,g]));const generated=payload.generated_at;els.status.textContent=generated?`Mis à jour ${new Intl.DateTimeFormat('fr-FR',{dateStyle:'medium',timeStyle:'short'}).format(new Date(generated))}`:`${state.games.length.toLocaleString('fr-FR')} jeux`;populateYears();buildTagIndex();updateLibraryUI();applyFilters();renderHighlights();renderRecommendations();openHashGame();loadSearchIndexPayload().then(index=>{if(index.count!==state.games.length)throw new Error(`Search index count ${index.count} != catalog ${state.games.length}`);state.searchIndex=index;if(els.search.value.trim())applyFilters();}).catch(e=>console.warn('Search index unavailable, using full scan',e));loadHealthPayload().then(renderHealth).catch(e=>console.warn('Health unavailable',e));}catch(error){console.error(error);els.status.textContent='Catalogue indisponible';els.empty.hidden=false;els.empty.querySelector('strong').textContent='Impossible de charger le catalogue';}}

els.search.addEventListener('input',()=>{clearTimeout(state.searchTimer);state.searchTimer=setTimeout(applyFilters,SEARCH_DEBOUNCE_MS);});
els.search.addEventListener('keydown',event=>{if(!els.suggestions.hidden&&(event.key==='ArrowDown'||event.key==='ArrowUp')){event.preventDefault();stepSuggestion(event.key==='ArrowDown'?1:-1);return;}if(event.key==='Enter'&&state.suggestionIndex>=0){event.preventDefault();$$('.search-suggestion')[state.suggestionIndex]?.click();}});
els.search.addEventListener('blur',()=>setTimeout(()=>{els.suggestions.hidden=true;},150));
els.tagSearch.addEventListener('input',updateTagFacets);els.clearTags.addEventListener('click',()=>{state.selectedTags.clear();els.tagSearch.value='';updateTagUI();applyFilters();});els.sort.addEventListener('change',applyFilters);els.yearFilter.addEventListener('change',applyFilters);els.releasePeriodFilter.addEventListener('change',applyFilters);els.sizeFilter.addEventListener('change',applyFilters);
els.newOnlyFilter.addEventListener('click',()=>toggleQuick('newOnly',els.newOnlyFilter));els.detailsOnlyFilter.addEventListener('click',()=>toggleQuick('detailsOnly',els.detailsOnlyFilter));els.mediaOnlyFilter.addEventListener('click',()=>toggleQuick('mediaOnly',els.mediaOnlyFilter));els.resetFilters.addEventListener('click',resetFilters);
$$('.library-filter').forEach(b=>b.addEventListener('click',()=>setLibraryFilter(b.dataset.library)));els.favoritesToggle.addEventListener('click',()=>setLibraryFilter('favorites'));els.exportLibrary.addEventListener('click',exportLibrary);els.importLibraryButton.addEventListener('click',()=>els.importLibrary.click());els.importLibrary.addEventListener('change',()=>{if(els.importLibrary.files[0])importLibrary(els.importLibrary.files[0]);});
els.openTagPicker.addEventListener('click',openTagPicker);els.closeTagPicker.addEventListener('click',closeTagPicker);els.tagPickerDialog.addEventListener('click',event=>{if(event.target===els.tagPickerDialog)closeTagPicker();});
els.mobileFiltersButton.addEventListener('click',openMobileFilters);els.closeFilters.addEventListener('click',closeMobileFilters);els.filterOverlay.addEventListener('click',closeMobileFilters);
els.dialog.addEventListener('click',e=>{if(e.target===els.dialog||e.target.closest('[data-close-dialog]'))els.dialog.close();});els.dialog.addEventListener('close',restoreCatalogPosition);
window.addEventListener('hashchange',()=>{const id=gameHashId();if(!id&&els.dialog.open)els.dialog.close();else if(id&&state.byId.has(id)&&id!==state.dialogGameId)openDialog(state.byId.get(id),{syncUrl:false});});
document.addEventListener('keydown',event=>{const typing=['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName);if(els.dialog.open&&!typing&&!isLightboxOpen()){if(event.key==='ArrowLeft'){event.preventDefault();navigateDialog(-1);return;}if(event.key==='ArrowRight'){event.preventDefault();navigateDialog(1);return;}}if(event.key==='/'&&!typing){event.preventDefault();els.search.focus();}if(event.key==='Escape'){if(els.tagPickerDialog.open)closeTagPicker();else closeMobileFilters();}});
window.addEventListener('resize',armInfiniteObserver,{passive:true});
loadCatalog();