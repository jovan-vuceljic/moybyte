"""The browser console's glass follows the page, in a REAL browser.

The page sizes the console's canvas from its room (page_core.html's THE
GLASS): Auto takes the largest whole number of device pixels a canvas pixel
whose canvas still holds the desk's 1024x600, a smaller window the largest
whole N whose canvas holds the handheld's 320x240, a touch phone the phone
rule (240 tall in landscape), and Settings' UI size picks a percent of
the CSS pixel; a resize, a rotation or a new UI size moves the running
console live (`Workstation.resize_glass`), with no reload.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_glass_e2e.py
"""

import os
import pathlib

import pytest

import web_e2e
from test_web_term_e2e import (_SHELL, _board, _lines, _qr_fragment, _serve, _site, _tagged,
                               _typed, _until, short, tty_exe)  # noqa: F401 -- fixtures

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")

ROOT = pathlib.Path(__file__).resolve().parent.parent
LAPTOP = {"width": 1366, "height": 768, "dpr": 1, "mobile": False}
PHONE_L = {"width": 844, "height": 390, "dpr": 3, "mobile": True}
PHONE_P = {"width": 390, "height": 844, "dpr": 3, "mobile": True}
WIDE = {"width": 3440, "height": 1440, "dpr": 1, "mobile": False}


def _glass(tag):
    """The canvas, the UI size the page holds and the console's mode."""
    return {"js": "window.__moyState().then(s => '%s ' + JSON.stringify({w: W, h: H, "
                  "n: GLASS.n, zoom: GLASS.zoom, zooms: GLASS.zooms, desk: s.desk, "
                  "order: s.order, parked: s.parked, frames: s.frames}))" % tag}


def _moved(w=None, h=None, timeout=10000):
    test = []
    if w is not None:
        test.append("W === %d" % w)
    if h is not None:
        test.append("H === %d" % h)
    return {"waitFor": " && ".join(test), "timeout": timeout}


def _ui_size(pct):
    """Settings' UI size picked: what the page keeps and applies."""
    return {"js": "localStorage.setItem('moy.uisize', '%d'), glassCheck(), 'ui %d'" % (pct, pct)}


def _run(tmp_path, name, base, query, steps, device):
    return web_e2e.run(tmp_path, name, query, steps, base, tmp_path / "chrome",
                       device=device, boot_ms=30000)


def test_the_glass_follows_the_viewport_live(tmp_path):
    """A laptop boots the desk at 100%; turned into a phone in landscape the
    glass goes 240 tall in console mode, the Terminal's window parked and its
    session running; back on the laptop the desk returns with it, the lines
    typed before the turns still in the Terminal."""
    web_e2e.require("site_shell")
    p, base = _site(tmp_path)
    try:
        steps = ([{"note": "the Terminal on a laptop's desk"}, _until(_SHELL)]
                 + _typed("echo before") + [{"key": "Enter"}, {"wait": 500}, _glass("LAPTOP"),
                                            {"shot": "laptop"},
                                            {"viewport": PHONE_L}, _moved(h=240), {"wait": 800},
                                            _glass("PHONE"), {"shot": "phone_landscape"},
                                            {"viewport": PHONE_P}, _moved(320, 240), {"wait": 800},
                                            _glass("PORTRAIT"), {"shot": "phone_portrait"},
                                            {"viewport": LAPTOP}, _moved(1366), {"wait": 1200},
                                            _glass("BACK"), {"shot": "laptop_again"}]
                 + _typed("echo after") + [{"key": "Enter"}, {"wait": 600}, _lines("TERM")])
        _out, js = _run(tmp_path, "glass_live", base, "?dev=1&desktop=1&cart=Terminal", steps,
                        LAPTOP)
        lap = _tagged(js, "LAPTOP")
        assert (lap["w"], lap["n"], lap["desk"]) == (1366, 1, True), lap
        assert "terminal" in lap["order"], lap
        phone = _tagged(js, "PHONE")
        assert phone["h"] == 240 and phone["n"] == 0 and phone["desk"] is False, phone
        assert "terminal" in phone["parked"], phone
        assert (_tagged(js, "PORTRAIT")["w"], _tagged(js, "PORTRAIT")["h"]) == (320, 240), js
        back = _tagged(js, "BACK")
        assert back["desk"] is True and "terminal" in back["order"], back
        assert back["frames"] > lap["frames"], "the console never restarted"
        term = "\n".join(_tagged(js, "TERM"))
        assert "before" in term and "after" in term, term
    finally:
        p.terminate()


def test_ui_size_moves_the_glass_and_offers_whole_device_pixels(tmp_path):
    """3440x1440 at a devicePixelRatio of 1: Auto is 200% (1720 wide, the
    desk), 100% and 200% move the glass live; a 1.5 screen offers 67%,
    133%, 200% and on, each a whole number of device pixels."""
    web_e2e.require("site_shell")
    p, base = _site(tmp_path)
    try:
        steps = [{"wait": 2500}, _glass("AUTO"), {"shot": "uw_auto"},
                 _ui_size(100), _moved(3440), {"wait": 800}, _glass("ONE"), {"shot": "uw_100"},
                 _ui_size(200), _moved(1720), {"wait": 800}, _glass("TWO"), {"shot": "uw_200"},
                 {"viewport": {"width": 1280, "height": 720, "dpr": 1.5, "mobile": False}},
                 _ui_size(0), {"wait": 1500}, _glass("DPR15")]
        _out, js = _run(tmp_path, "glass_size", base, "?dev=1", steps, WIDE)
        auto = _tagged(js, "AUTO")
        assert (auto["w"], auto["n"], auto["zoom"], auto["desk"]) == (1720, 2, 0, True), auto
        assert _tagged(js, "ONE")["w"] == 3440 and _tagged(js, "ONE")["n"] == 1, js
        assert _tagged(js, "TWO")["w"] == 1720, js
        d15 = _tagged(js, "DPR15")
        assert d15["zooms"].startswith("0,67,133,200") and d15["n"] == 1 and d15["w"] == 1920, d15
    finally:
        p.terminate()


_P8 = ROOT / "tests" / "fixtures" / "tiny_dash.p8"


@pytest.mark.parametrize("device", [PHONE_L, LAPTOP, WIDE], ids=["phone", "laptop", "wide"])
def test_a_game_in_console_mode_takes_a_whole_scale(tmp_path, device):
    """In console mode a 320x240 game and a PICO-8 cart take the largest whole
    scale that fits the glass, in a letterbox of the theme's desktop colour."""
    web_e2e.require("site_shell")
    p, base = _site(tmp_path)
    try:
        corner = ("(function(){var d=cx.getImageData(0,0,1,1).data;"
                  "return 'CORNER '+JSON.stringify([d[0],d[1],d[2]]);})()")
        steps = [{"wait": 2500}, {"js": "WORKER.postMessage({t:'open',"
                                        "cart:'moybyte.star_catcher.moy'}), 'open'"},
                 {"wait": 3000}, _glass("GAME"), {"js": corner}, {"shot": "star_catcher"},
                 {"file": str(_P8), "as": "__drop"},
                 {"js": "WORKER.postMessage({t:'import',name:'tiny_dash.p8',buf:window.__drop},"
                        "[window.__drop]), 'import'"},
                 {"note": "the import's card: Open (beside No) plays it"},
                 {"wait": 5000}, {"js": "cv.focus(), 'focused'"}, {"key": "ArrowRight"},
                 {"wait": 300}, {"key": "Enter"}, {"wait": 3000}, {"js": corner.replace("CORNER", "P8CORNER")},
                 {"shot": "pico8"}]
        _out, js = _run(tmp_path, "game", base, "?dev=1&console=1", steps, device)
        g = _tagged(js, "GAME")
        assert g["desk"] is False, g
        # A phone's glass is the game's own 320x240 (between the pads): it
        # fills it, and only the PICO-8 cart's 128x128 leaves a letterbox.
        tags = ("P8CORNER",) if (g["w"], g["h"]) == (320, 240) else ("CORNER", "P8CORNER")
        for tag in tags:
            assert _tagged(js, tag) != [0, 0, 0], (tag, js)
    finally:
        p.terminate()


def test_a_board_served_page_sizes_its_glass_too(tty_exe, tmp_path, short):  # noqa: F811
    """A page a board serves takes the same glass: a phone in landscape gets
    the 240-tall console."""
    host = _board(tty_exe, short)
    server, base = _serve(tmp_path, host.port)
    try:
        steps = [{"wait": 3000}, _glass("BOARD")]
        _out, js = _run(tmp_path, "board", base, "?dev=1" + _qr_fragment(host), steps, PHONE_L)
        b = _tagged(js, "BOARD")
        assert b["h"] == 240 and b["desk"] is False, b
    finally:
        server.terminate()
        host.end()



def _where(tag):
    return {"js": "window.__moyState().then(s => '%s ' + JSON.stringify({screen: s.screen, "
                  "desk: s.desk, order: s.order, edit: s.edit}))" % tag}


_HERO_DESK = "?desktop=1&start=1&edit=moybyte.star_catcher.moy&tab=code&play=1&only=desk"


@pytest.mark.parametrize("device", [PHONE_P, WIDE], ids=["phone", "desktop"])
def test_a_visit_lands_on_the_home_in_console_mode(tmp_path, device):
    """In console mode (a phone) a visit lands on the home: a fresh one, one
    after the Editor was open, and the site hero's Desktop start, which on a
    desk opens the Editor as a window with its game playing."""
    web_e2e.require("site_shell")
    p, base = _site(tmp_path)
    try:
        first = [{"wait": 3000}, _where("FIRST"),
                 {"js": "WORKER.postMessage({t:'edit',cart:'moybyte.star_catcher.moy',"
                        "tab:'code'}), 'edit'"},
                 {"wait": 3000}, _where("EDITING"), {"wait": 1500}]
        _out, js = _run(tmp_path, "first", base, "", first, device)
        fresh, editing = _tagged(js, "FIRST"), _tagged(js, "EDITING")
        _out, js = _run(tmp_path, "again", base, "", [{"wait": 3000}, _where("AGAIN")], device)
        again = _tagged(js, "AGAIN")
        _out, js = _run(tmp_path, "hero", base, _HERO_DESK,
                        [{"wait": 4000}, _where("HERO"), {"shot": "hero"}], device)
        hero = _tagged(js, "HERO")
        assert editing["edit"].get("tab") == "code", editing
        if device is PHONE_P:
            for st in (fresh, again, hero):
                assert st["desk"] is False and st["screen"] == "launcher", (fresh, again, hero)
        else:
            assert fresh["desk"] is True and again["desk"] is True, (fresh, again)
            assert hero["desk"] is True and "menu" in hero["order"], hero
            assert hero["edit"].get("tab") == "code", hero
    finally:
        p.terminate()


_RECTS = ("(function(){var o={};['cv','joy','bb','ba','kb','bh'].forEach(function(id){"
          "var e=document.getElementById(id),r=e.getBoundingClientRect();"
          "if(r.width&&r.height&&getComputedStyle(e).visibility!=='hidden')"
          "o[id]=[r.left,r.top,r.right,r.bottom];});"
          "o.vw=innerWidth;o.vh=innerHeight;"
          "return 'RECTS '+JSON.stringify(o);})()")


def _apart(a, b):
    return a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


@pytest.mark.parametrize("device", [PHONE_L, PHONE_P], ids=["landscape", "portrait"])
def test_a_phone_s_controls_overlap_nothing(tmp_path, device):
    """On a touch phone no two controls overlap and none overlaps the canvas;
    held sideways the page shows no rows above the canvas, which takes the
    full height, centred, with the stick and A/B in its side margins."""
    web_e2e.require("site_shell")
    p, base = _site(tmp_path)
    try:
        steps = [{"wait": 3000}, {"js": _RECTS}, {"page": "home"},
                 {"js": "WORKER.postMessage({t:'open',cart:'moybyte.star_catcher.moy'}), 'open'"},
                 {"wait": 3000}, {"js": _RECTS.replace("RECTS", "GAME")}, {"page": "game"}]
        _out, js = _run(tmp_path, "pads", base, "?dev=1", steps, device)
        for tag in ("RECTS", "GAME"):
            r = _tagged(js, tag)
            ids = [k for k in ("cv", "joy", "bb", "ba", "kb", "bh") if k in r]
            assert set(ids) >= {"cv", "kb", "bh"}, r
            for i, a in enumerate(ids):
                x0, y0, x1, y1 = r[a]
                assert x0 >= 0 and y0 >= 0 and x1 <= r["vw"] + 0.5 and y1 <= r["vh"] + 0.5, (a, r)
                for b in ids[i + 1:]:
                    assert _apart(r[a], r[b]), (a, b, r)
            if device is PHONE_L:
                assert {"joy", "bb", "ba"} <= set(ids), r
                cv = r["cv"]
                assert cv[1] <= 0.5 and cv[3] >= r["vh"] - 0.5, r
                assert abs(cv[0] - (r["vw"] - cv[2])) <= 1, r
                assert r["joy"][2] <= cv[0] and r["ba"][0] >= cv[2], r
    finally:
        p.terminate()


# The in-between windows of a desktop, where a whole-N handheld and the desk
# meet: (width, height, dpr), the N and the glass the page takes, and its
# class. Below the desk's room in CSS pixels, the largest N whose canvas
# still holds 320x240; at or past it, the desk.
_BETWEEN = [((700, 560, 1), 2, (350, 280), "handheld"),
            ((900, 600, 1), 2, (450, 300), "handheld"),
            ((1100, 650, 1), 1, (1100, 650), "desk"),
            ((1300, 700, 1), 1, (1300, 700), "desk"),
            ((700, 560, 1.25), 2, (437, 350), "handheld"),
            ((900, 600, 1.25), 3, (375, 250), "handheld"),
            ((1100, 650, 1.25), 1, (1375, 812), "desk"),
            ((1300, 700, 1.25), 1, (1625, 875), "desk")]

_COVER = ("Promise.resolve(window.__moyState()).then(function(s){"
          "var b=cv.getBoundingClientRect();return '%s '+JSON.stringify({l:b.left,t:b.top,"
          "w:b.width,h:b.height,iw:innerWidth,ih:innerHeight,dpr:devicePixelRatio,n:GLASS.n,"
          "W:W,H:H,desk:s.desk,glass:s.glass});})")


@pytest.mark.parametrize("size,n,glass,cls", _BETWEEN,
                         ids=["%dx%d@%s" % s for s, _n, _g, _c in _BETWEEN])
def test_a_desktop_window_between_the_handheld_and_the_desk(tmp_path, size, n, glass, cls):
    """A pointer's window below the desk's room is the handheld at the
    largest whole N whose canvas holds 320x240: the T-Deck's class at chrome
    scale 1, its bar N device pixels a glass pixel, the home the floor (no
    back chevron); at or past the room, the desk, whose console mode keeps
    the way back to it. Either way the canvas covers the viewport to under N
    device pixels, and Brick Siege, paused in console mode, sits at a whole
    scale in the theme's letterbox."""
    web_e2e.require("site_shell")
    w, h, dpr = size
    device = {"width": w, "height": h, "dpr": dpr, "mobile": False}
    corner = ("(function(){var d=cx.getImageData(0,H-1,1,1).data;"
              "return 'CORNER '+JSON.stringify([d[0],d[1],d[2]]);})()")
    p, base = _site(tmp_path)
    try:
        steps = [{"wait": 3500}, {"js": _COVER % "HOME"}, {"page": "home"},
                 {"js": "WORKER.postMessage({t:'open',cart:'moybyte.brick_siege.moy'}), 'open'"},
                 {"wait": 3000}, {"js": "cv.focus(), 'focused'"}, {"key": "Escape"},
                 {"wait": 1200}, {"js": _COVER % "PAUSED"}, {"js": corner}, {"page": "paused"}]
        _out, js = _run(tmp_path, "between", base, "?dev=1&console=1", steps, device)
        home, paused = _tagged(js, "HOME"), _tagged(js, "PAUSED")
        for st in (home, paused):
            assert (st["n"], (st["W"], st["H"])) == (n, glass), st
            # The canvas covers the viewport: what whole N leaves is under N
            # device pixels (and a CSS pixel of rounding) at the edges.
            slack = n / dpr + 1
            assert st["l"] >= 0 and st["t"] >= 0, st
            assert 0 <= st["iw"] - st["w"] <= slack and 0 <= st["ih"] - st["h"] <= slack, st
            g = st["glass"]
            assert g["cls"] == cls, st
            assert st["desk"] is False, st
            if cls == "handheld":
                assert g["cs"] == 1 and g["bar"] < 32, st
            else:
                assert g["bar"] >= 32, st
            assert abs(st["h"] * g["bar"] / st["H"] - g["bar"] * n / dpr) < 1, st
        g = home["glass"]
        if cls == "handheld":
            assert g["depth"] == g["floor"], ("the held home is the floor", home)
        else:
            assert g["depth"] > g["floor"], ("console mode keeps the desk beneath", home)
        assert _tagged(js, "CORNER") != [0, 0, 0] or glass == (320, 240), js
    finally:
        p.terminate()


@pytest.mark.parametrize("device", [PHONE_P, PHONE_L], ids=["portrait", "landscape"])
def test_a_phone_lays_out_the_handheld(tmp_path, device):
    """A touch phone's glass is the T-Deck's class at chrome scale 1, and its
    home is the floor: no back chevron, nothing beneath it."""
    web_e2e.require("site_shell")
    p, base = _site(tmp_path)
    try:
        _out, js = _run(tmp_path, "phone", base, "?dev=1",
                        [{"wait": 3500}, {"js": _COVER % "HOME"}, {"page": "home"}], device)
        st = _tagged(js, "HOME")
        g = st["glass"]
        assert st["desk"] is False and g["cls"] == "handheld" and g["cs"] == 1, st
        assert g["depth"] == g["floor"], st
    finally:
        p.terminate()
