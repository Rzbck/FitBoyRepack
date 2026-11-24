// Real wall-clock Chromium test; virtual time can skip compositor intersections.
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {setTimeout as sleep} from 'node:timers/promises';
import assert from 'node:assert/strict';

const [chrome,url]=process.argv.slice(2);
assert.ok(chrome&&url,'usage: node test_card_window_browser.mjs CHROME URL');
const profile=await mkdtemp(join(tmpdir(),'fitboy-chrome-'));
let browser, socket;
const pending=new Map();
let seq=0, stderr='';
function call(method,params={}){
  const id=++seq;
  return new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>{pending.delete(id);reject(new Error(method+' timed out'));},5000);
    pending.set(id,{resolve,reject,timeout});
    socket.send(JSON.stringify({id,method,params}));
  });
}
try {
  browser=spawn(chrome,['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage',
    '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',
    '--user-data-dir='+profile,'--window-size=1000,800','about:blank'],
    {stdio:['ignore','ignore','pipe']});
  browser.stderr.on('data',data=>{stderr=(stderr+data.toString()).slice(-4000);});
  let port;
  for(let i=0;i<100;i++){
    if(browser.exitCode!==null)throw new Error('Chrome exited: '+browser.exitCode);
    try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{}
    await sleep(100);
  }
  assert.ok(port,'DevTools port missing');
  const pages=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  const page=pages.find(p=>p.type==='page');
  assert.ok(page?.webSocketDebuggerUrl,'DevTools page missing');
  socket=new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>reject(new Error('DevTools connection timed out')),5000);
    socket.addEventListener('open',()=>{clearTimeout(timeout);resolve();},{once:true});
    socket.addEventListener('error',()=>{clearTimeout(timeout);reject(new Error('DevTools connection failed'));},{once:true});
  });
  socket.addEventListener('message',event=>{
    const message=JSON.parse(event.data);
    const item=pending.get(message.id);
    if(!item)return;
    clearTimeout(item.timeout);pending.delete(message.id);
    if(message.error)item.reject(new Error(message.error.message));else item.resolve(message.result);
  });
  for(const viewport of [{width:1000,height:800},{width:390,height:844}]){
    await call('Emulation.setDeviceMetricsOverride',{...viewport,deviceScaleFactor:1,mobile:false});
    const target=new URL(url);target.searchParams.set('viewport',String(viewport.width));
    await call('Page.bringToFront');
    await call('Page.navigate',{url:target.href});
    let result='pending';
    for(let i=0;i<150;i++){
      await sleep(100);
      const response=await call('Runtime.evaluate',{expression:"({href:location.href,result:document.querySelector('#result')?.textContent})",returnByValue:true});
      const data=response.result.value;
      if(data?.href===target.href&&data.result&&data.result!=='pending'){result=data.result;break;}
    }
    assert.equal(result,'CARD WINDOW BROWSER OK',viewport.width+'px: '+result);
    console.log('Card window Chromium '+viewport.width+'px: OK');
  }
} catch(error) {
  console.error(stderr);
  throw error;
} finally {
  for(const item of pending.values()){clearTimeout(item.timeout);item.reject(new Error('browser closed'));}
  socket?.close();
  if(browser&&browser.exitCode===null){browser.kill();await Promise.race([new Promise(resolve=>browser.once('exit',resolve)),sleep(2000)]);}
  await rm(profile,{recursive:true,force:true,maxRetries:5,retryDelay:200}).catch(()=>{});
}
