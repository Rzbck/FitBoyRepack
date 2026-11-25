import assert from 'node:assert/strict';
import {mediaCandidates,showMedia} from '../site/assets/catalog/media-fallback.js';
const url='https://s01.riotpixels.net/data/c1/8a/c18a557f-be60-4e6d-aad9-8d2c81598546.jpg';
const preview=url+'.240p.jpg';
assert.deepEqual(mediaCandidates({url,preview,kind:'image'}),[url,url+'.1080p.jpg',url+'.720p.jpg',url+'.480p.jpg',preview]);
assert.deepEqual(mediaCandidates({url,preview,kind:'gif'}),[url,preview]);
assert.deepEqual(mediaCandidates({url:'https://example.com/a.jpg',preview:'https://example.com/b.jpg'}),['https://example.com/a.jpg','https://example.com/b.jpg']);
assert.deepEqual(mediaCandidates({url:'javascript:alert(1)',preview:'https://example.com/b.jpg'}),['https://example.com/b.jpg']);
assert.deepEqual(mediaCandidates({url,preview:url}),[url]);
class Img {
  constructor(){this.events={};this.isConnected=true;}
  addEventListener(n,f){this.events[n]=f;}
  replaceWith(x){this.isConnected=false;stage.img=x;}
}
const stage={img:new Img(),querySelector:()=>stage.img,prepend:x=>stage.img=x};
globalThis.document={createElement:()=>new Img()};
const caption={dataset:{}};
const labels={media:'image',original:'original',fallback:'fallback',unavailable:'unavailable'};
showMedia(stage,{url,preview},caption,labels);
const first=stage.img;
assert.equal(first.src,url);
first.events.error();
assert.equal(stage.img.src,url+'.1080p.jpg');
stage.img.events.load();
assert.equal(caption.dataset.mediaStatus,'fallback');
const stale=stage.img;
showMedia(stage,{url:'https://example.com/new.jpg'},caption,labels);
stale.events.error();
assert.equal(stage.img.src,'https://example.com/new.jpg');
stage.img.events.error();
assert.equal(caption.dataset.mediaStatus,'unavailable');
assert.equal(stage.img.hidden,true);
console.log('Media resolution fallback, stale navigation and unavailable state OK');
