import assert from 'node:assert/strict';
import { findWishlistGame, titleKeysForGame } from '../site/assets/wishlist.js';

const games=[
  { id:'anno-117',title:'Anno 117: Pax Romana - Gold Edition, v3.0 + 6 DLCs',canonical_title:'Anno 117 : Pax Romana',post_date:'2026-11-23' },
  { id:'silksong',title:'Hollow Knight: Silksong',canonical_title:'Hollow Knight: Silksong',post_date:'2026-11-23' },
  { id:'resident5',title:'Resident Evil 5',post_date:'2024-01-01' },
  { id:'resident4',title:'Resident Evil 4 - Gold Edition',post_date:'2026-11-21' },
  { id:'spiritold',title:'Spirit City: Lofi Sessions – v1.0.0 + DLC',post_date:'2026-08-01' },
  { id:'spiritnew',title:'Spirit City: Lofi Sessions – v2.1.0 + DLC',post_date:'2026-11-23' },
];
assert.equal(findWishlistGame('Anno 117: Pax Romana',games)?.id,'anno-117','verified canonical punctuation');
assert.equal(findWishlistGame('Resident Evil 4',games)?.id,'resident4','edition suffix');
assert.equal(findWishlistGame('Hollow Knight: Silksong',games)?.id,'silksong','full sequel name');
assert.equal(findWishlistGame('Spirit City: Lofi Sessions',games)?.id,'spiritnew','prefer latest repack version');
assert.equal(findWishlistGame('Resident Evil 6',games),null,'do not match different sequel');
assert.equal(findWishlistGame('Hollow Knight',games),null,'do not match sequel prefix');
assert.equal(findWishlistGame('Resident Evil',games),null,'do not match part of title');
assert.equal(findWishlistGame('Anno 117',games),null,'do not match generic prefix');
assert.equal(findWishlistGame('Spirit City',games),null,'do not match partial name');
assert.equal(findWishlistGame('Resident Evil 4 Remastered',games),null,'do not assume remaster');
assert.ok(titleKeysForGame(games[0]).includes('anno 117 pax romana'));

const edgeCases=[
  ['   ANNO   117 :  PAX  ROMANA   ', 'anno-117'],
  ['anno 117 pax romana', 'anno-117'],
  ['  Resident    Evil 4   ', 'resident4'],
  ['RÉSIDENT ÉVIL 4', 'resident4'],
  ['SpIrIt  CITY : LOFI  SeSSionS', 'spiritnew'],
  ['HOLLOW KNIGHT - SILKSONG', 'silksong'],
];
for(const [query,expected] of edgeCases){
  assert.equal(findWishlistGame(query,games)?.id,expected,'normalized match: '+query);
}
assert.equal(findWishlistGame('Resident Evil 40',games),null,'numbers must not be dropped');
assert.equal(findWishlistGame('Hollow Knight Silksong 2',games),null,'no broad fuzzy matches');
assert.equal(findWishlistGame('Anno 117: Pax',games),null,'no incomplete prefix matches');
console.log('Wishlist case/accents/whitespace/punctuation: 9 checks OK');

console.log('Wishlist matching: 11 baseline checks OK');
