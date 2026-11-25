// Keep fallback URLs tied to the same screenshot, never to unrelated media.
export function mediaCandidates(item) {
  const out=[];
  const add=value=>{
    try {
      const u=new URL(value);
      if(u.protocol==='https:'&&!u.username&&!u.password&&!out.includes(u.href))out.push(u.href);
    }catch{}
  };
  add(item.url);
  if(item.kind!=='gif'){
    try{
      const full=new URL(item.url), preview=new URL(item.preview);
      // Known RiotPixels derivative family, confirmed against real images.
      if(/^s\d+\.riotpixels\.net$/i.test(full.hostname)&&full.origin===preview.origin&&
          /^\/data\/[0-9a-f]{2}\/[0-9a-f]{2}\/[0-9a-f-]{36}\.jpg$/i.test(full.pathname)&&
          preview.pathname===full.pathname+'.240p.jpg'){
        for(const size of [1080,720,480]){
          const derivative=new URL(full.href);
          derivative.pathname=full.pathname+'.'+size+'p.jpg';
          add(derivative.href);
        }
      }
    }catch{}
  }
  add(item.preview);
  return out;
}

// A fresh image per attempt prevents late errors from a previous slide.
export function showMedia(stage,item,caption,labels) {
  const candidates=mediaCandidates(item);
  let active=null;
  function next(){
    if(active&&!active.isConnected)return;
    const previous=active||stage.querySelector('img');
    const img=document.createElement('img');
    img.alt=item.alt||labels.media;
    img.referrerPolicy='no-referrer';
    img.decoding='async';
    const url=candidates.shift();
    if(!url){
      img.hidden=true;
      caption.textContent=labels.unavailable;
      caption.dataset.mediaStatus='unavailable';
    }else{
      img.addEventListener('error',next,{once:true});
      img.addEventListener('load',()=>{
        if(!img.isConnected)return;
        caption.dataset.mediaStatus=url===item.url?'full':'fallback';
        caption.textContent=url===item.url?labels.original:labels.fallback;
      },{once:true});
    }
    active=img;
    if(previous)previous.replaceWith(img);else stage.prepend(img);
    if(url)img.src=url;
  }
  caption.textContent=labels.original;
  caption.dataset.mediaStatus='loading';
  next();
}
