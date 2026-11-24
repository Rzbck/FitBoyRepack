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
