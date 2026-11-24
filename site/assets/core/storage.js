// Keep all deployed keys and backup formats compatible with existing browsers.
export const STORAGE_KEYS=Object.freeze({
  library:'fitboyrepack:library:v2',
  legacyFavorites:'fitboyrepack:favorites:v1',
  wishlist:'fitboyrepack:wishlist:v1',
  language:'fitboyrepack:language:v1',
});
export function readText(key,fallback=null){
  try{return globalThis.localStorage.getItem(key)??fallback;}catch{return fallback;}
}
export function writeText(key,value){
  try{globalThis.localStorage.setItem(key,value);return true;}catch{return false;}
}
export function readJSON(key,fallback=null){
  try{return JSON.parse(readText(key))??fallback;}catch{return fallback;}
}
export function writeJSON(key,value){
  try{return writeText(key,JSON.stringify(value));}catch{return false;}
}
export function readLibrary(){
  const raw=readJSON(STORAGE_KEYS.library,{});
  const ids=value=>new Set(Array.isArray(value)?value.map(String):[]);
  return {
    // Once canonical favorites exist, never resurrect removed legacy entries.
    favorites:ids(Array.isArray(raw?.favorites)?raw.favorites:readJSON(STORAGE_KEYS.legacyFavorites,[])),
    backlog:ids(raw?.backlog),
    completed:ids(raw?.completed),
  };
}
export function writeLibrary(library){
  const payload=Object.fromEntries(['favorites','backlog','completed'].map(key=>[key,[...library[key]]]));
  if(!writeJSON(STORAGE_KEYS.library,payload))return false;
  // Mirror for old versions, but canonical data is authoritative.
  writeJSON(STORAGE_KEYS.legacyFavorites,payload.favorites);
  return true;
}
