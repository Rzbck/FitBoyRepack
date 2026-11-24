import assert from 'node:assert/strict';
import {createCardWindow} from '../site/assets/card-window.js';
let observer;
globalThis.IntersectionObserver=class {
 constructor(callback){this.callback=callback;this.nodes=new Set();observer=this;}
 observe(node){this.nodes.add(node);}
 unobserve(node){this.nodes.delete(node);}
 disconnect(){this.nodes.clear();}
 emit(nodes,intersecting){this.callback(nodes.map(target=>({target,isIntersecting:intersecting})));}
};
class Node {
 constructor(){this.children=[];this.parentNode=null;this.className='';this.style={setProperty(){},removeProperty(){}};this.events={};}
 get classList(){return {contains:x=>this.className.split(' ').includes(x)};}
 append(...nodes){for(const n of nodes){if(n.fragment)this.append(...n.children);else{n.parentNode=this;this.children.push(n);}}}
 replaceChildren(){for(const n of this.children)n.parentNode=null;this.children=[];}
 replaceWith(n){const p=this.parentNode;p.children[p.children.indexOf(this)]=n;n.parentNode=p;this.parentNode=null;}
 contains(n){return this===n;}
 getBoundingClientRect(){return {width:180,height:320};}
 setAttribute(){}
 addEventListener(type,fn){this.events[type]=fn;}
 querySelector(){return {focus(){},addEventListener(){}};}
}
globalThis.document={activeElement:null,createElement:()=>new Node(),createDocumentFragment:()=>Object.assign(new Node(),{fragment:true})};
const grid=new Node(), render=game=>Object.assign(new Node(),{className:'game-card',id:game.id});
let protectedCard;
const window=createCardWindow(grid,render,{limit:120,protectedNode:()=>protectedCard});
window.append(Array.from({length:240},(_,id)=>({id,title:'Game '+id})));
protectedCard=grid.children[0];
observer.emit(grid.children.slice(0,200),false);
assert.equal(grid.children.length,240);
assert.equal(grid.children.filter(n=>n.className==='game-card').length,120);
assert.equal(grid.children[0],protectedCard);
const slot=grid.children[1];
assert.equal(slot.className,'card-slot');
assert.equal(slot.type,'button');
observer.emit([slot],true);
assert.equal(grid.children[1].id,1);
const another=grid.children.find(n=>n.className==='card-slot');
const index=grid.children.indexOf(another);
another.events.focus();
assert.equal(grid.children[index].id,index);
window.reset();
assert.equal(grid.children.length,0);
assert.equal(observer.nodes.size,0);
window.append([{id:999,title:'New filter'}]);
observer.emit([slot],true);
assert.equal(grid.children[0].id,999);
console.log('Card window: 240 ordered slots, bounded live cards, focus, restoration, reset OK');
