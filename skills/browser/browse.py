#!/usr/bin/env python3
"""
Browser tool for Friday — navigate, screenshot, click, type, extract text.
Uses Playwright with Chromium. Screenshots go to /tmp for Friday to read.

Usage:
    browse.py goto <url>                    — Navigate and screenshot
    browse.py screenshot                    — Screenshot current page
    browse.py click <selector>              — Click an element
    browse.py click_text <visible_text>     — Click element by visible text
    browse.py type <selector> <text>        — Type into an input
    browse.py select <selector> <value>     — Select dropdown option
    browse.py scroll <direction>            — Scroll up/down
    browse.py extract                       — Extract all visible text
    browse.py links                         — List all links on page
    browse.py eval <js>                     — Run arbitrary JS, return result
    browse.py close                         — Close browser session

Session persists via state file between calls.
"""

import sys
import json
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

STATE_FILE = Path("/tmp/friday_browser_state.json")
SCREENSHOT_PATH = "/tmp/friday_browser_screenshot.png"
VIEWPORT = {"width": 1280, "height": 900}
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def save_state(url, cookies=None, local_storage=None):
    state = {"url": url, "cookies": cookies or [], "ts": time.time()}
    if local_storage:
        state["local_storage"] = local_storage
    STATE_FILE.write_text(json.dumps(state))


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return None


def make_browser(pw):
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        viewport=VIEWPORT,
        user_agent=USER_AGENT,
        locale="en-US",
        java_script_enabled=True,
    )
    # Block heavy media to speed things up
    context.route("**/*.{mp4,webm,ogg,mp3,wav,flac}", lambda route: route.abort())
    page = context.new_page()
    return browser, context, page


def screenshot(page, path=SCREENSHOT_PATH):
    page.screenshot(path=path, full_page=False)
    print(f"Screenshot saved: {path}")


def cmd_goto(pw, url):
    browser, context, page = make_browser(pw)
    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
    except PWTimeout:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
    page.wait_for_timeout(1000)  # let JS settle
    screenshot(page)
    print(f"Title: {page.title()}")
    print(f"URL: {page.url}")
    save_state(page.url, context.cookies())
    browser.close()


def with_page(pw, fn):
    """Restore session and run fn(page), then cleanup."""
    state = load_state()
    if not state:
        print("ERROR: No browser session. Run 'goto <url>' first.")
        sys.exit(1)
    browser, context, page = make_browser(pw)
    if state.get("cookies"):
        context.add_cookies(state["cookies"])
    try:
        page.goto(state["url"], wait_until="networkidle", timeout=30000)
    except PWTimeout:
        page.goto(state["url"], wait_until="domcontentloaded", timeout=15000)
    page.wait_for_timeout(500)
    result = fn(page)
    save_state(page.url, context.cookies())
    browser.close()
    return result


def cmd_screenshot(pw):
    with_page(pw, lambda p: screenshot(p))


def cmd_click(pw, selector):
    def do(page):
        page.click(selector, timeout=5000)
        page.wait_for_timeout(1000)
        screenshot(page)
        print(f"Clicked: {selector}")
    with_page(pw, do)


def cmd_click_text(pw, text):
    def do(page):
        loc = page.get_by_text(text, exact=False).first
        loc.click(timeout=5000)
        page.wait_for_timeout(1000)
        screenshot(page)
        print(f"Clicked text: {text}")
    with_page(pw, do)


def cmd_type(pw, selector, text):
    def do(page):
        page.fill(selector, text, timeout=5000)
        page.wait_for_timeout(500)
        screenshot(page)
        print(f"Typed into {selector}: {text}")
    with_page(pw, do)


def cmd_select(pw, selector, value):
    def do(page):
        page.select_option(selector, value, timeout=5000)
        page.wait_for_timeout(500)
        screenshot(page)
        print(f"Selected {value} in {selector}")
    with_page(pw, do)


def cmd_scroll(pw, direction="down"):
    def do(page):
        delta = 600 if direction == "down" else -600
        page.mouse.wheel(0, delta)
        page.wait_for_timeout(500)
        screenshot(page)
        print(f"Scrolled {direction}")
    with_page(pw, do)


def cmd_extract(pw):
    def do(page):
        text = page.inner_text("body")
        # Trim to reasonable length
        if len(text) > 15000:
            text = text[:15000] + "\n... (truncated)"
        print(text)
    with_page(pw, do)


def cmd_links(pw):
    def do(page):
        links = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({text: e.innerText.trim().slice(0,80), href: e.href})).filter(l => l.text)"
        )
        for l in links[:100]:
            print(f"  [{l['text']}] → {l['href']}")
        if len(links) > 100:
            print(f"  ... and {len(links)-100} more")
    with_page(pw, do)


def cmd_eval(pw, js):
    def do(page):
        result = page.evaluate(js)
        print(json.dumps(result, indent=2, default=str))
    with_page(pw, do)


def cmd_close():
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    if os.path.exists(SCREENSHOT_PATH):
        os.unlink(SCREENSHOT_PATH)
    print("Session closed.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "close":
        cmd_close()
        return

    with sync_playwright() as pw:
        if cmd == "goto" and len(sys.argv) >= 3:
            cmd_goto(pw, sys.argv[2])
        elif cmd == "screenshot":
            cmd_screenshot(pw)
        elif cmd == "click" and len(sys.argv) >= 3:
            cmd_click(pw, sys.argv[2])
        elif cmd == "click_text" and len(sys.argv) >= 3:
            cmd_click_text(pw, " ".join(sys.argv[2:]))
        elif cmd == "type" and len(sys.argv) >= 4:
            cmd_type(pw, sys.argv[2], " ".join(sys.argv[3:]))
        elif cmd == "select" and len(sys.argv) >= 4:
            cmd_select(pw, sys.argv[2], sys.argv[3])
        elif cmd == "scroll":
            direction = sys.argv[2] if len(sys.argv) >= 3 else "down"
            cmd_scroll(pw, direction)
        elif cmd == "extract":
            cmd_extract(pw)
        elif cmd == "links":
            cmd_links(pw)
        elif cmd == "eval" and len(sys.argv) >= 3:
            cmd_eval(pw, " ".join(sys.argv[2:]))
        else:
            print(f"Unknown command or missing args: {' '.join(sys.argv[1:])}")
            print(__doc__)
            sys.exit(1)


if __name__ == "__main__":
    main()
