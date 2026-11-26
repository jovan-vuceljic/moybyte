"""The page's top bar is the console's rows, in a REAL browser.

The page keeps no bar of its own (firmware/web_runner/page_link.py): Full
screen and Add a file are the system menu's, Save to this
computer a cart's, Play on the console the open cart's where a console serves
the page, and Settings' Carts row says where the page keeps them. Each row is
chosen here as a person chooses it -- the system menu's key, its highlight
walked to the row, a real Enter -- on a static site and on a page a console
(serve.py's board twin) serves.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_page_rows_e2e.py
"""

import os
import pathlib
import shutil

import pytest

import web_e2e
from test_web_persist_e2e import _serve as _serve_board
from test_web_term_e2e import (PASSWORD, _asks, _board, _password, _prompt, _serve, _site,
                               _tagged, short, tty_exe)  # noqa: F401 -- fixtures

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")

ROOT = pathlib.Path(__file__).resolve().parent.parent
P8 = ROOT / "tests" / "fixtures" / "tiny_dash.p8"
LAPTOP = {"width": 1366, "height": 768, "dpr": 1, "mobile": False}
_PAGE = {"js": "window.__moyState().then(s => 'PAGE ' + JSON.stringify(s.page))"}
_PODS = ("window.__pods = [], (function (post) { WORKER.postMessage = function (m, t) { "
         "if (m && m.t === 'pod') window.__pods.push(m.cart); return post.call(WORKER, m, t); }; "
         "})(WORKER.postMessage), 'watched'")
_SAVES = "window.__saved = [], pzDownload = function (n, b) { window.__saved.push(n); }, 'caught'"


def _where(kind, tmp_path):
    """(the server, its base) for a static site or a page a console serves."""
    if kind == "site":
        web_e2e.require("site_shell")
        return _site(tmp_path)
    web_e2e.require("store")
    store = tmp_path / "store"
    store.mkdir()
    for cart in ("moybyte.star_catcher.moy", "moybyte.sakura.moy"):
        shutil.copytree(ROOT / "system_carts" / cart, store / cart)
    return _serve_board(web_e2e.free_port(), ("--carts", str(store)))


def _run(tmp_path, name, base, query, steps):
    return web_e2e.run(tmp_path, name, query, steps, base, tmp_path / "chrome",
                       device=LAPTOP, boot_ms=30000)


def test_full_screen_is_the_system_menu_s(tmp_path):
    """Full screen takes the page full screen, the row then reads Leave full
    screen, and that takes it out."""
    p, base = _where("site", tmp_path)
    try:
        def fs(tag):
            return {"js": "new Promise(ok => setTimeout(ok, 800)).then(() => window.__moyState())"
                          ".then(s => '%s ' + JSON.stringify([!!document.fullscreenElement, "
                          "s.page.fs]))" % tag}
        steps = ([{"wait": 2500}] + web_e2e.menu_pick("Full screen") + [fs("FS1")]
                 + web_e2e.menu_pick("Leave full screen") + [fs("FS2")])
        _out, js = _run(tmp_path, "full", base, "?dev=1", steps)
        assert _tagged(js, "FS1") == [True, True], js
        assert _tagged(js, "FS2") == [False, False], js
    finally:
        p.terminate()


@pytest.mark.parametrize("kind", ["site", "board"])
def test_add_from_this_computer_imports_the_file_chosen(tmp_path, kind):
    """Add a file opens the browser's file chooser; the PICO-8
    cart chosen imports, runs, and the console's card offers the Editor."""
    p, base = _where(kind, tmp_path)
    try:
        steps = ([{"wait": 2500}] + web_e2e.menu_pick("Add a file")
                 + [{"wait": 500}, {"choose": str(P8)}, {"wait": 6000},
                    {"js": "'IMPORTED ' + JSON.stringify(window.__moyImported || null)"},
                    {"js": "'CARD ' + JSON.stringify(window.__moyCard || null)"},
                    {"page": "imported"}])
        _out, js = _run(tmp_path, "add_" + kind, base, "?dev=1", steps)
        assert "CHOOSER opened" in js, js
        assert "imported local.tiny_dash.moy" in (_tagged(js, "IMPORTED") or ""), js
        assert (_tagged(js, "CARD") or {}).get("kind") == "offer", js
    finally:
        p.terminate()


@pytest.mark.parametrize("kind", ["site", "board"])
def test_a_cart_s_menu_saves_it_and_a_served_page_plays_it_on_the_console(tmp_path, kind):
    """The home's selected card: Download downloads its .moy; on
    a page a console serves, Play on the console asks that console to play
    it, and only there. Settings' Carts row says where the page keeps them."""
    p, base = _where(kind, tmp_path)
    try:
        steps = ([{"wait": 3000}, {"js": _SAVES}, {"js": _PODS}, _PAGE]
                 + web_e2e.menu_pick("Download") + [{"wait": 1500},
                 {"js": "'SAVED ' + JSON.stringify(window.__saved)"}])
        if kind == "board":
            steps += web_e2e.menu_pick("Play on the console") + [
                {"wait": 1500}, {"js": "'PODS ' + JSON.stringify(window.__pods)"}]
        steps += [{"js": "'CARTS ' + JSON.stringify(window.__moyCarts || [])"}]
        _out, js = _run(tmp_path, "cart_" + kind, base, "?handheld=1&dev=1", steps)
        page = _tagged(js, "PAGE")
        assert page["kept"] == ("In this browser" if kind == "site" else "On the console"), page
        assert page["served"] is (kind == "board"), page
        menu = [j for j in js if isinstance(j, str) and j.startswith("MENU ")][0]
        assert ("Play on the console" in menu) is (kind == "board"), menu
        saved = _tagged(js, "SAVED")
        assert len(saved) == 1 and saved[0].endswith(".moy.zip"), js
        assert saved[0][:-4] in _tagged(js, "CARTS"), js
        if kind == "board":
            assert _tagged(js, "PODS") == [saved[0][:-4]], js
    finally:
        p.terminate()


# An iPhone's Safari: its user agent, and no element full screen.
IPHONE = {"width": 390, "height": 844, "dpr": 3, "mobile": True}
IPHONE_L = {"width": 844, "height": 390, "dpr": 3, "mobile": True}
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1")
NO_FS = ("delete Element.prototype.requestFullscreen;"
         "delete Element.prototype.webkitRequestFullscreen;")
# ...opened from its Home Screen.
AS_APP = NO_FS + "Object.defineProperty(Navigator.prototype, 'standalone', {get: () => true});"
_CARD = {"js": "window.__moyState().then(s => 'CARD ' + JSON.stringify(s.card))"}
_HOME = "Add to Home Screen"


def _iphone(tmp_path, name, base, query, steps, init=NO_FS, device=IPHONE):
    return web_e2e.run(tmp_path, name, query, steps, base, tmp_path / name, device=device,
                       boot_ms=30000, ua=IPHONE_UA, init=init)


def test_an_iphone_s_menu_says_how_to_get_full_screen(tmp_path):
    """Where the browser has no full screen the system menu offers Add to
    Home Screen, whose card has the steps; the home-screen app offers none."""
    p, base = _where("site", tmp_path)
    try:
        _out, js = _iphone(tmp_path, "safari", base, "?dev=1",
                           [{"wait": 2500}, _PAGE] + web_e2e.menu_pick(_HOME)
                           + [{"wait": 600}, _CARD, {"page": "card"}])
        page, card = _tagged(js, "PAGE"), _tagged(js, "CARD")
        assert page["canfs"] is False and page["app"] is False, page
        assert card["title"] == "Full screen", card
        assert "2. Choose Add to Home Screen." in card["lines"], card
        _out, js = _iphone(tmp_path, "app", base, "?dev=1",
                           [{"wait": 2500}, _PAGE] + web_e2e.menu_pick(_HOME, enter=False),
                           init=AS_APP)
        assert _tagged(js, "PAGE")["app"] is True, js
        menu = _tagged(js, "MENU")
        assert _HOME not in menu and "Full screen" not in menu, menu
    finally:
        p.terminate()


_RECTS = ("(function(){var o={};['cv','joy','bb','ba','kb','bh'].forEach(function(id){"
          "var r=document.getElementById(id).getBoundingClientRect();"
          "if(r.width&&r.height)o[id]=[r.left,r.top,r.right,r.bottom];});"
          "o.vw=innerWidth;o.vh=innerHeight;return '%s '+JSON.stringify(o);})()")
_INSETS = ("document.documentElement.style.cssText += '--sa-t:%dpx;--sa-r:%dpx;--sa-b:%dpx;"
           "--sa-l:%dpx', dispatchEvent(new Event('resize')), 'insets'")


@pytest.mark.parametrize("device,insets", [(IPHONE, (59, 0, 34, 0)), (IPHONE_L, (0, 59, 21, 59))],
                         ids=["portrait", "landscape"])
def test_the_home_screen_app_keeps_out_of_the_notch_and_the_home_bar(tmp_path, device, insets):
    """Opened from the Home Screen the page runs under the notch and the
    home bar (viewport-fit=cover): the canvas and every control stay inside
    the safe area."""
    p, base = _where("site", tmp_path)
    try:
        t, r, b, left = insets
        _out, js = _iphone(tmp_path, "app", base, "?dev=1",
                           [{"wait": 2500}, {"js": _INSETS % insets}, {"wait": 800},
                            {"js": _RECTS % "RECTS"}, {"page": "safe"}],
                           init=AS_APP, device=device)
        rects = _tagged(js, "RECTS")
        vw, vh = rects.pop("vw"), rects.pop("vh")
        for name, (x0, y0, x1, y1) in rects.items():
            assert x0 >= left - 0.5 and y0 >= t - 0.5, (name, rects)
            assert x1 <= vw - r + 0.5 and y1 <= vh - b + 0.5, (name, rects)
        assert {"cv", "joy", "ba", "bb"} <= set(rects), rects
    finally:
        p.terminate()


_GUARDS = ("(function(){var o={};['cv','joy','ba','bb','ctl'].forEach(function(id){"
           "var c=getComputedStyle(document.getElementById(id));"
           "o[id]=[c.touchAction,c.userSelect||c.webkitUserSelect,c.webkitTouchCallout||'none'];});"
           "o.html=getComputedStyle(document.documentElement).touchAction;"
           "function tap(el){var t=new Touch({identifier:1,target:el,clientX:1,clientY:1});"
           "var e=new TouchEvent('touchend',{bubbles:true,cancelable:true,touches:[],"
           "changedTouches:[t]});el.dispatchEvent(e);return e.defaultPrevented;}"
           "var a=document.getElementById('ba');o.first=tap(a);o.second=tap(a);"
           "var s=new Event('selectstart',{bubbles:true,cancelable:true});"
           "document.getElementById('joy').dispatchEvent(s);o.select=s.defaultPrevented;"
           "var g=new Event('gesturestart',{bubbles:true,cancelable:true});"
           "document.dispatchEvent(g);o.pinch=g.defaultPrevented;"
           "return 'GUARDS '+JSON.stringify(o);})()")


def test_the_controls_never_zoom_or_select(tmp_path):
    """A double tap on A or B never zooms the page, a long press on the
    stick or the canvas selects nothing, and a pinch is refused: the play
    surfaces take every touch."""
    p, base = _where("site", tmp_path)
    try:
        _out, js = _iphone(tmp_path, "guards", base, "?dev=1",
                           [{"wait": 2500}, {"js": _GUARDS}])
        g = _tagged(js, "GUARDS")
        for el in ("cv", "joy", "ba", "bb", "ctl"):
            assert g[el][0] == "none" and g[el][1] == "none", (el, g)
        assert g["html"] == "pan-x pan-y", g
        assert g["first"] is False and g["second"] is True, "the second tap of a double tap"
        assert g["select"] is True and g["pinch"] is True, g
    finally:
        p.terminate()


def test_the_home_screen_app_pairs_with_its_board_and_reaches_the_home(tty_exe, tmp_path,
                                                                        short):  # noqa: F811
    """iOS gives the home-screen app storage of its own, so its first launch
    pairs again: its card asks for the password (a scanned code would open
    Safari), and once paired the app reaches the home."""
    host = _board(tty_exe, short, password=PASSWORD)
    server, base = _serve(tmp_path, host.port)
    try:
        steps = [_asks("p => p.shown === 'flex'"), _prompt("ASK"),
                 {"js": "'TEXT ' + JSON.stringify(document.getElementById('pinp').textContent)"},
                 _password(PASSWORD), _asks("p => p.shown === 'none' && p.keys === 1"),
                 {"waitFor": "window.__moyState && window.__moyState().then(s => "
                             "s.screen === 'launcher')", "timeout": 30000},
                 {"js": "window.__moyState().then(s => 'HOME ' + JSON.stringify("
                        "{screen: s.screen, desk: s.desk, page: s.page}))"},
                 {"page": "paired"}]
        _out, js = _iphone(tmp_path, "app", base, "?dev=1", steps, init=AS_APP)
        assert "opens Safari, not this app" in _tagged(js, "TEXT"), js
        home = _tagged(js, "HOME")
        assert home["screen"] == "launcher" and home["desk"] is False, home
        assert home["page"]["app"] is True and home["page"]["served"] is True, home
    finally:
        server.terminate()
        host.end()


@pytest.mark.parametrize("device", [IPHONE_L, IPHONE], ids=["landscape", "portrait"])
def test_the_menu_pad_keeps_out_of_the_browser_s_top_corners(tmp_path, device):
    """An iPhone's browser lays its own chrome over the page's top corners
    (full screen's Close, at the top right): the burger and the keyboard
    summon sit at the bottom of the side margins in landscape, clear of the
    top 64 pixels, and every control and the canvas stay apart."""
    p, base = _where("site", tmp_path)
    try:
        _out, js = _iphone(tmp_path, "pads", base, "?dev=1",
                           [{"wait": 2500}, {"js": _RECTS % "RECTS"}, {"page": "pads"}],
                           init=AS_APP, device=device)
        rects = _tagged(js, "RECTS")
        vw, vh = rects.pop("vw"), rects.pop("vh")
        bh = rects["bh"]
        assert bh[1] >= 64 and bh[3] <= vh, rects
        if device is IPHONE_L:
            assert bh[0] >= vw / 2 and bh[1] >= vh / 2, ("the bottom right", rects)
            assert rects["kb"][2] <= vw / 2 and rects["kb"][1] >= vh / 2, ("the bottom left", rects)
            for name in ("joy", "ba", "bb"):
                assert rects[name][1] >= 48, (name, "under the top corners' band", rects)
        names = sorted(rects)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                ra, rb = rects[a], rects[b]
                apart = ra[2] <= rb[0] or rb[2] <= ra[0] or ra[3] <= rb[1] or rb[3] <= ra[1]
                assert apart, (a, b, rects)
    finally:
        p.terminate()


_FS_RECTS = ("new Promise(ok => setTimeout(ok, 1200)).then(() => window.__moyState()).then(s => {"
             "var o = {}; ['cv','joy','bb','ba','kb','bh'].forEach(function (id) {"
             "var r = document.getElementById(id).getBoundingClientRect();"
             "if (r.width && r.height) o[id] = [r.left, r.top, r.right, r.bottom]; });"
             "o.fs = !!(document.fullscreenElement || document.webkitFullscreenElement);"
             "o.page = s.page.fs; o.mark = document.documentElement.classList.contains('iosfs');"
             "return '%s ' + JSON.stringify(o); })")
# An iPhone's browser with webkit's full screen alone.
WEBKIT_FS = ("delete Element.prototype.requestFullscreen;"
             "delete Document.prototype.exitFullscreen;")


@pytest.mark.parametrize("init", ["", WEBKIT_FS], ids=["unprefixed", "webkit"])
def test_an_iphone_s_full_screen_keeps_clear_of_its_strip(tmp_path, init):
    """Where an iPhone's browser has full screen, prefixed or not, the menu
    offers it beside Add to Home Screen (the true full screen, with no
    browser bars); full screen, the page keeps the top 50 pixels clear for
    the browser's exit strip and its Close, and leaving it gives them
    back."""
    p, base = _where("site", tmp_path)
    try:
        steps = ([{"wait": 2500}] + web_e2e.menu_pick("Full screen") + [{"js": _FS_RECTS % "IN"}]
                 + web_e2e.menu_pick("Leave full screen") + [{"js": _FS_RECTS % "OUT"}])
        _out, js = _iphone(tmp_path, "fs", base, "?dev=1", steps, init=init or None,
                           device=IPHONE_L)
        menu = _tagged(js, "MENU")
        assert "Full screen" in menu and _HOME in menu, menu
        inside, out = _tagged(js, "IN"), _tagged(js, "OUT")
        assert inside["fs"] and inside["page"] and inside["mark"], inside
        for name in ("cv", "joy", "ba", "bb", "kb", "bh"):
            if name in inside:
                assert inside[name][1] >= 50 - 0.5, (name, inside)
        assert not out["fs"] and not out["mark"] and out["cv"][1] < 50, out
    finally:
        p.terminate()


def test_an_iphone_s_home_screen_app_offers_neither_full_screen(tmp_path):
    """Opened from the Home Screen the page is full screen already: its menu
    offers neither Full screen nor Add to Home Screen."""
    p, base = _where("site", tmp_path)
    try:
        _out, js = _iphone(tmp_path, "app", base, "?dev=1",
                           [{"wait": 2500}] + web_e2e.menu_pick(_HOME, enter=False),
                           init=AS_APP.replace(NO_FS, ""), device=IPHONE_L)
        menu = _tagged(js, "MENU")
        assert "Full screen" not in menu and _HOME not in menu, menu
    finally:
        p.terminate()
