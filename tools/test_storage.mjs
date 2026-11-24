import assert from 'node:assert/strict';
import {STORAGE_KEYS as K,readText,writeText,readJSON,writeJSON,readLibrary,writeLibrary} from '../site/assets/storage.js';
const data=new Map();let denied=false,blockedKey=null;
globalThis.localStorage={
 getItem:key=>{if(denied)throw Error('blocked');return data.get(key)??null;},
 setItem:(key,value)=>{if(denied||key===blockedKey)throw Error('blocked');data.set(key,value);}
};
assert.deepEqual([...readLibrary().favorites],[]);
writeJSON(K.legacyFavorites,['old',5]);
assert.deepEqual([...readLibrary().favorites],['old','5']);
const library=readLibrary();library.favorites.delete('old');library.backlog.add('later');library.completed.add('done');
assert.equal(writeLibrary(library),true);
writeJSON(K.legacyFavorites,['old','5']);
assert.deepEqual([...readLibrary().favorites],['5'],'canonical deletion must not resurrect old favorite');
assert.deepEqual([...readLibrary().backlog],['later']);assert.deepEqual([...readLibrary().completed],['done']);
blockedKey=K.legacyFavorites;library.favorites.clear();assert.equal(writeLibrary(library),true);
assert.equal(readLibrary().favorites.size,0);
blockedKey=K.library;library.favorites.add('new');assert.equal(writeLibrary(library),false);
assert.equal(readLibrary().favorites.size,0);
blockedKey=null;
assert.equal(writeJSON(K.wishlist,[{title:'Game'}]),true);assert.deepEqual(readJSON(K.wishlist),[{title:'Game'}]);
assert.equal(writeText(K.language,'fr'),true);assert.equal(readText(K.language),'fr');
data.set(K.library,'invalid');assert.deepEqual([...readLibrary().favorites],['old','5']);
denied=true;assert.equal(readText(K.language,'auto'),'auto');assert.equal(writeJSON(K.wishlist,[]),false);
assert.equal(readLibrary().favorites.size,0);
console.log('Storage: legacy migration, canonical deletion, all keys, invalid JSON and denied/quota writes OK');
