"""On a slow link the page says how its boot goes until the console's first
frame (page_core.html's loading card, the loader's line): the wasm's or
the pack's bytes as they arrive, then that the console starts. Both ways
a page boots: the page served whole (worker.js fetches the wasm) and a
board's loader (loader.html fetches the pack from its mirror), each in the
system Chrome through Playwright with the link throttled over CDP.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_load_progress_e2e.py
"""

import contextlib
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

import web_e2e
from web_e2e import RUNNER

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome on a throttled link)")

# What the page shows now: the loader's line before the page is written, the
# loading card while it stands, and "live" once the first frame took it down.
SAMPLE = """() => {
  if (!document.getElementById('cv')) { const s = document.getElementById('s');
    return ['loader', s ? s.textContent : '']; }
  const t = document.getElementById('ldt');
  return t ? ['page', t.textContent] : ['live', ''];
}"""

LINK = 400 * 1024           # bytes a second each way


@contextlib.contextmanager
def _serve(*extra):
    port = web_e2e.free_port()
    server = subprocess.Popen([sys.executable, "serve.py", str(port), "dist"] + list(extra),
                              cwd=RUNNER, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/", timeout=1).read(64)
                break
            except urllib.error.HTTPError:
                break
            except OSError:
                if server.poll() is not None:
                    pytest.fail("serve.py died on startup")
                time.sleep(0.1)
        yield base
    finally:
        server.terminate()
        server.wait(timeout=10)


def _watch(url):
    """Every change of what the page shows from `url` on a throttled link
    until the console's first frame: [(phase, words)]."""
    from playwright.sync_api import sync_playwright
    seen = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        try:
            ctx = browser.new_context(viewport={"width": 960, "height": 640})
            page = ctx.new_page()
            cdp = ctx.new_cdp_session(page)
            cdp.send("Network.enable")
            cdp.send("Network.emulateNetworkConditions", {
                "offline": False, "latency": 40,
                "downloadThroughput": LINK, "uploadThroughput": LINK})
            page.goto(url, wait_until="commit")
            end = time.time() + 120
            while time.time() < end:
                try:
                    got = tuple(page.evaluate(SAMPLE))
                except Exception:       # noqa: BLE001 -- a document being written
                    got = None
                if got and (not seen or seen[-1] != got):
                    seen.append(got)
                if got and got[0] == "live":
                    break
                time.sleep(0.05)
        finally:
            browser.close()
    return seen


def _mb(seen, phase):
    """The megabytes the loading words said in `phase`, in order."""
    out = []
    for ph, words in seen:
        m = re.match(r"Loading the console, ([\d.]+)( of ([\d.]+))? MB$", words)
        if ph == phase and m:
            out.append((float(m.group(1)), m.group(3)))
    return out


def test_the_page_says_its_download_and_its_start(tmp_path):
    web_e2e.require()
    with _serve() as base:
        seen = _watch(base + "/index.html?start=1")
    assert seen and seen[-1][0] == "live", seen
    got = _mb(seen, "page")
    assert len(got) >= 3 and [g[0] for g in got] == sorted(g[0] for g in got) \
        and got[-1][0] > got[0][0], ("the bytes did not count up", seen)
    assert ("page", "Starting the console") in seen, seen


def test_a_board_s_loader_says_the_pack_s_download_and_the_page_its_start(tmp_path):
    web_e2e.require("sync")
    store = tmp_path / "store"
    shutil.copytree(os.path.join(ROOT, "system_carts", "moybyte.star_catcher.moy"),
                    store / "moybyte.star_catcher.moy")
    web_e2e.warm_host_library()
    with _serve("--carts", str(store), "--loader") as base:
        seen = _watch(base + "/?start=1")
    assert seen and seen[-1][0] == "live", seen
    got = _mb(seen, "loader")
    assert len(got) >= 3 and got[-1][0] > got[0][0], ("the pack's bytes did not count up", seen)
    assert all(g[1] is not None for g in got), ("the pack's total went unsaid", got)
    assert ("page", "Starting the console") in seen, seen


def test_a_boot_whose_first_sign_in_meets_no_answer_asks_again(tmp_path):
    """A slow phone's first requests can meet a host still busy with its
    downloads: a sign-in that gets no answer at all is asked again, the
    card saying the boot's stage, and the console starts; it never says
    the console does not answer while the boot can still go on."""
    web_e2e.require()
    from playwright.sync_api import sync_playwright
    failed = []
    with _serve() as base, sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844})

            def drop(route):
                if len(failed) < 2:
                    failed.append(route.request.url)
                    route.abort("connectionreset")
                else:
                    route.continue_()
            ctx.route("**/auth", drop)
            page = ctx.new_page()
            page.goto(base + "/index.html?start=1", wait_until="commit")
            seen, end = [], time.time() + 60
            while time.time() < end:
                try:
                    got = tuple(page.evaluate(SAMPLE))
                except Exception:       # noqa: BLE001
                    got = None
                if got and (not seen or seen[-1] != got):
                    seen.append(got)
                if got and got[0] == "live":
                    break
                time.sleep(0.05)
        finally:
            browser.close()
    assert len(failed) == 2, ("the sign-in was not asked again", failed, seen)
    assert seen and seen[-1][0] == "live", seen
    assert ("page", "Loading your carts") in seen, seen
    assert not [s for s in seen if "does not answer" in s[1]], seen


def test_the_loading_card_stands_on_the_console_s_screen(tmp_path):
    """In a phone's portrait the pads lie under the console's screen, and
    the card stands on the screen's middle, not the page's."""
    web_e2e.require()
    from playwright.sync_api import sync_playwright
    with _serve() as base, sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        try:
            for vp in ({"width": 390, "height": 844}, {"width": 844, "height": 390},
                       {"width": 1280, "height": 800}):
                ctx = browser.new_context(viewport=vp, has_touch=vp["width"] < 1000,
                                          is_mobile=vp["width"] < 1000)
                page = ctx.new_page()
                cdp = ctx.new_cdp_session(page)
                cdp.send("Network.enable")
                cdp.send("Network.emulateNetworkConditions", {
                    "offline": False, "latency": 40,
                    "downloadThroughput": LINK, "uploadThroughput": LINK})
                page.goto(base + "/index.html", wait_until="commit")
                page.wait_for_selector("#ld", timeout=20000)
                page.wait_for_timeout(500)
                at = page.evaluate("""() => {
                  const a = document.getElementById('ld').getBoundingClientRect(),
                        b = document.getElementById('cv').getBoundingClientRect();
                  return [a.left + a.width / 2, a.top + a.height / 2,
                          b.left + b.width / 2, b.top + b.height / 2, b.height];
                }""")
                ctx.close()
                assert abs(at[0] - at[2]) <= 2 and abs(at[1] - at[3]) <= 2 and at[4] > 0, (vp, at)
        finally:
            browser.close()
