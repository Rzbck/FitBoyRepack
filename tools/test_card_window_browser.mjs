// Real wall-clock Chromium test over its private DevTools pipe.
import {spawn} from 'node:child_process';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {setTimeout as sleep} from 'node:timers/promises';
import assert from 'node:assert/strict';

const [chrome,url]=process.argv.slice(2);
assert.ok(chrome&&url,'usage: node test_card_window_browser.mjs CHROME URL');
const profile=await mkdtemp(join(tmpdir(),'fitboy-chrome-'));
let browser, sessionId, seq=0, stderr='', incoming='';
const pending=new Map();
function call(method,params={},session=null){
  const id=++seq;
  return new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>{pending.delete(id);reject(new Error(method+' timed out'));},15000);
    pending.set(id,{resolve,reject,timeout});
    browser.stdio[3].write(JSON.stringify({id,method,params,...(session?{sessionId:session}:{})})+'\0');
  });
}
try {
  browser=spawn(chrome,['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage',
    '--remote-debugging-pipe','--user-data-dir='+profile,'--window-size=1000,800','about:blank'],
    {stdio:['ignore','ignore','pipe','pipe','pipe']});
  browser.stderr.on('data',data=>{stderr=(stderr+data.toString()).slice(-4000);});
  browser.stdio[3].on('error',()=>{});
  browser.stdio[4].setEncoding('utf8');
  browser.stdio[4].on('data',chunk=>{
    incoming+=chunk;
    const parts=incoming.split('\0');incoming=parts.pop();
    for(const part of parts){
      if(!part)continue;
      const message=JSON.parse(part),item=pending.get(message.id);
      if(!item)continue;
      clearTimeout(item.timeout);pending.delete(message.id);
      if(message.error)item.reject(new Error(message.error.message));else item.resolve(message.result);
    }
  });
  await call('Browser.getVersion');
  const targets=await call('Target.getTargets');
  const targetId=targets.targetInfos.find(t=>t.type==='page')?.targetId;
  assert.ok(targetId,'DevTools page missing');
  sessionId=(await call('Target.attachToTarget',{targetId,flatten:true})).sessionId;
  const page=(method,params={})=>call(method,params,sessionId);
  for(const viewport of [{width:1000,height:800},{width:390,height:844}]){
    await page('Emulation.setDeviceMetricsOverride',{...viewport,deviceScaleFactor:1,mobile:false});
    const target=new URL(url);target.searchParams.set('viewport',String(viewport.width));
    await page('Page.bringToFront');
    await page('Page.navigate',{url:target.href});
    let result='pending';
    for(let i=0;i<150;i++){
      await sleep(100);
      const response=await page('Runtime.evaluate',{expression:"({href:location.href,result:document.querySelector('#result')?.textContent})",returnByValue:true});
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
  if(browser&&browser.exitCode===null){browser.kill();await Promise.race([new Promise(resolve=>browser.once('exit',resolve)),sleep(2000)]);}
  await rm(profile,{recursive:true,force:true,maxRetries:5,retryDelay:200}).catch(()=>{});
}
