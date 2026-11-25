"""Pinned Playwright Chromium; retry launch only, never retry assertions."""
import argparse
import sys
import time
from playwright.sync_api import sync_playwright, Error

def launch(driver):
    for attempt in range(3):
        try:
            return driver.chromium.launch(headless=True,timeout=30000)
        except Error:
            if attempt==2: raise
            print("Chromium launch failed; retrying infrastructure startup",file=sys.stderr)
            time.sleep(2*(attempt+1))

def check_media_fallback(page):
    url="https://s01.riotpixels.net/data/c1/8a/c18a557f-be60-4e6d-aad9-8d2c81598546.jpg"
    seen=[]
    def handle(route):
        seen.append(route.request.url)
        if route.request.url==url+".1080p.jpg":
            route.fulfill(status=200,content_type="image/svg+xml",body='<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"><rect width="1920" height="1080" fill="red"/></svg>')
        else:
            route.fulfill(status=404,body="not found")
    page.route("https://s01.riotpixels.net/**",handle)
    page.evaluate("""async url=>{
      const {showMedia}=await import('/assets/catalog/media-fallback.js');
      const stage=document.createElement('figure');
      stage.id='media-fallback-ci';
      stage.innerHTML='<img alt=""><figcaption></figcaption>';
      document.body.append(stage);
      showMedia(stage,{url,preview:url+'.240p.jpg',kind:'image'},stage.querySelector('figcaption'),
         {media:'image',original:'original',fallback:'fallback',unavailable:'unavailable'});
    }""",url)
    page.wait_for_function("document.querySelector('#media-fallback-ci figcaption').dataset.mediaStatus==='fallback'")
    assert page.locator('#media-fallback-ci img').evaluate('(img)=>img.naturalWidth')==1920
    assert seen==[url,url+".1080p.jpg"],seen
    print("Real browser media fallback OK")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--language",choices=["en","fr"])
    parser.add_argument("--card-window",action="store_true")
    args=parser.parse_args()
    with sync_playwright() as driver:
        browser=launch(driver)
        try:
            if args.card_window:
                for width,height in [(1000,800),(390,844)]:
                    context=browser.new_context(viewport={"width":width,"height":height})
                    page=context.new_page()
                    page.goto(args.url,wait_until="domcontentloaded",timeout=30000)
                    page.locator("#result").filter(has_not_text="pending").wait_for(timeout=20000)
                    result=page.locator("#result").inner_text()
                    assert result=="CARD WINDOW BROWSER OK",f"{width}px: {result}"
                    print(f"Card window Chromium {width}px: OK")
                    if width==1000:check_media_fallback(page)
                    context.close()
            else:
                context=browser.new_context(viewport={"width":1200,"height":900})
                if args.language:
                    context.add_init_script("localStorage.setItem('fitboyrepack:language:v1', "+repr(args.language)+")")
                page=context.new_page()
                page.route("**/*",lambda route:route.abort() if route.request.resource_type=="image" or not route.request.url.startswith("http://127.0.0.1:4173/") else route.continue_())
                page.goto(args.url,wait_until="domcontentloaded",timeout=30000)
                page.wait_for_function("document.querySelectorAll('#gameGrid .game-card').length >= 20",timeout=20000)
                if "#game=" in args.url:
                    page.wait_for_function("document.querySelector('#gameDialog')?.open && document.querySelector('.dialog-layout.rich-details:not(.dialog-loading)') && !document.querySelector('.detail-loading-shell')",timeout=20000)
                if args.language:page.wait_for_function("(lang)=>document.documentElement.dataset.language===lang",arg=args.language,timeout=10000)
                print(page.content())
        finally:
            browser.close()

if __name__=="__main__":main()
