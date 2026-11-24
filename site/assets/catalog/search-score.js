export function normalized(value='') {
  return String(value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').replace(/\s+/g,' ').trim();
}
export function boundedDistance(a,b,max) {
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

function scoreNormalized(game, query, qTokens) {
  if (!query) return 1;
  if (game.__titleNorm===query) return 500;
  if (game.__titleNorm.startsWith(query)) return 420-query.length*.01;
  if (game.__titleNorm.includes(query)) return 360-query.length*.01;
  if (game.__searchText.includes(query)) return 300;
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


// Only the active normalized query is retained; scores are tied to game objects.
export function createQueryScorer() {
  let raw, query='', parts=[], scores=new WeakMap();
  return (game, rawQuery) => {
    if(rawQuery!==raw){
      raw=rawQuery;
      const next=normalized(rawQuery);
      if(next!==query){query=next;parts=query.split(' ');scores=new WeakMap();}
    }
    if(!query)return 1;
    if(scores.has(game))return scores.get(game);
    const score=scoreNormalized(game,query,parts);
    scores.set(game,score);
    return score;
  };
}
