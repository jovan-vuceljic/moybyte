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
from test_web_term_e2e import _site, _tagged

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
