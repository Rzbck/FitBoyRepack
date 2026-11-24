// Lightweight offscreen slots retain the responsive grid geometry and order.
export function createCardWindow(grid, render, {limit=120, protectedNode=()=>null}={}) {
  const live = new Set();
  const near = new WeakMap();
  const games = new WeakMap();
  let count=0;
  const observer = typeof IntersectionObserver === 'function'
    ? new IntersectionObserver(entries => {
        for (const entry of entries) {
          const node=entry.target;
          if (node.parentNode!==grid) continue;
          near.set(node,entry.isIntersecting);
          if (entry.isIntersecting && node.classList.contains('card-slot')) restore(node);
        }
        prune();
      }, {rootMargin:'1200px 0px'})
    : null;

  function restore(slot, focus=false) {
    if (slot.parentNode!==grid) return;
    focus=focus||document.activeElement===slot;
    const game=games.get(slot);
    if (!game) return;
    const card=render(game);
    games.set(card,game);
    near.set(card,true);
    observer?.unobserve(slot);
    slot.replaceWith(card);
    live.add(card);
    observer?.observe(card);
    if(focus){
      // Keep the restored card renderable while transferring keyboard focus.
      card.style.contentVisibility='visible';
      const control=card.querySelector('.card-open');
      const transfer=()=>control?.focus({preventScroll:true});
      control?.addEventListener('blur',()=>card.style.removeProperty('content-visibility'),{once:true});
      transfer();
      if(document.activeElement!==control&&typeof requestAnimationFrame==='function'){
        requestAnimationFrame(()=>{if(card.isConnected)transfer();});
      }
    }
  }

  function prune() {
    if (!observer || count<=limit || live.size<=limit) return;
    const protectedElement=protectedNode();
    for (const card of live) {
      if(live.size<=limit) break;
      if (near.get(card)!==false || card.contains(document.activeElement)
          || (protectedElement && card.contains(protectedElement))) continue;
      // Measure real geometry rather than the CSS intrinsic placeholder.
      card.style.contentVisibility="visible";
      const rect=card.getBoundingClientRect();
      card.style.removeProperty("content-visibility");
      if(rect.width<=0 || rect.height<=0) continue;
      const game=games.get(card);
      const slot=document.createElement('button');
      slot.type='button';
      slot.className='card-slot';
      slot.tabIndex=0;
      slot.setAttribute('aria-label',game.title);
      slot.style.setProperty('--slot-body',Math.max(0,rect.height-rect.width*4/3)+'px');
      games.set(slot,game);
      slot.addEventListener('focus',()=>restore(slot,true),{once:true});
      slot.addEventListener('click',()=>restore(slot,true),{once:true});
      observer.unobserve(card);
      card.replaceWith(slot);
      live.delete(card);
      observer.observe(slot);
    }
  }
  return {
    reset() { observer?.disconnect(); live.clear(); count=0; grid.replaceChildren(); },
    append(items) {
      const fragment=document.createDocumentFragment();
      const nodes=[];
      for(const game of items) {
        const card=render(game);
        games.set(card,game);
        live.add(card);
        nodes.push(card);
        fragment.append(card);
        count++;
      }
      grid.append(fragment);
      for(const node of nodes) observer?.observe(node);
      prune();
    },
    prune,
  };
}
