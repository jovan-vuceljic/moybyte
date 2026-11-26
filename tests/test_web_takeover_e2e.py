"""Two browsers on one Zero, in real Chromes: the newer page takes the board.

The board is real C: the web terminal's host harness built with the live
socket (tests/test_web_live_e2e.py's), its sign-in on, with the console's
password; serve.py --board serves the bundle in front of it. The first page
pairs by the password and opens its live socket. The second pairs too (a
wrong password first, which says so) and its live socket opens: the first
page's closes 4001 "taken" (moy_webauth.c's moy_wa_take) and it shows the
card that says another browser signed in, with one button. Taking it back
is that click, and the second page is told in turn; neither page ever takes
the board back by itself.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_takeover_e2e.py
"""

import os
import shutil
import sys
import threading
import time

import pytest

import web_e2e

sys.path.insert(0, os.path.dirname(__file__))

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")

PASSWORD = "correct horse"
CARD = ("({shown: getComputedStyle(document.getElementById('pin')).display, "
        "head: document.getElementById('pinh').textContent, "
        "said: document.getElementById('pinp').textContent, "
        "button: document.getElementById('pinb').textContent, "
        "typing: getComputedStyle(document.getElementById('pinf')).display})")
LIVE = "window.__moyState().then(s => s.live && s.live.opens >= %d)"


def _card(tag):
    return {"js": "window.__moyState().then(s => '%s ' + JSON.stringify(Object.assign(%s, "
                  "{opens: s.live && s.live.opens, drops: s.live && s.live.drops})))"
                  % (tag, CARD)}


def _taken(timeout):
    return {"waitFor": "(%s).head === 'disconnected'" % CARD, "timeout": timeout}


def _shut():
    return {"waitFor": "(%s).shown === 'none'" % CARD, "timeout": 30000}


@pytest.fixture(scope="module")
def live_exe(tmp_path_factory):
    web_e2e.require("term", "signin")
    import test_moy_tty as T
    out = tmp_path_factory.mktemp("live")
    return T._build(out, extra=[os.path.join(T.NET, "moy_live.c"),
                                os.path.join(T.NET, "moy_link_host.c")],
                    defines=("MOY_NET_LIVE=1", "MOY_NET_LINK=1"))


def test_the_newer_page_takes_the_board_and_the_first_takes_it_back_by_a_click(
        live_exe, tmp_path, monkeypatch):
    import test_live_link as L
    import test_web_term_e2e as W
    air = L.Air()
    monkeypatch.setenv("MOY_AIR", str(air.port))
    monkeypatch.setenv("MOY_AIR_MAC", "020000000001")
    root = W.tempfile.mkdtemp(prefix="moyt")
    host = W._board(live_exe, W.pathlib.Path(root), password=PASSWORD)
    server, base = W._serve(tmp_path, host.port)
    query = "?dev=1&desktop=1"
    got = {}

    def first():
        steps = [W._asks("p => p.shown === 'flex'"), W._password(PASSWORD),
                 {"waitFor": LIVE % 1, "timeout": 30000}, _card("A_LIVE"),
                 _taken(120000), _card("A_TAKEN"),
                 {"wait": 3000}, _card("A_STILL"),
                 {"js": "(document.getElementById('pinb').click(), 'clicked')"},
                 _shut(), {"waitFor": LIVE % 2, "timeout": 30000}, _card("A_BACK")]
        got["a"] = web_e2e.run(tmp_path, "first", query, steps, base, tmp_path / "pa",
                               boot_ms=30000)

    t = threading.Thread(target=first)
    t.start()
    try:
        time.sleep(20)
        steps = [W._asks("p => p.shown === 'flex'"), W._password("wrong horse"),
                 W._asks("p => p.said.includes('did not work')"), W._password(PASSWORD),
                 {"waitFor": LIVE % 1, "timeout": 30000}, _card("B_LIVE"),
                 _taken(120000), _card("B_TAKEN"), {"wait": 3000}, _card("B_STILL")]
        out, js = web_e2e.run(tmp_path, "second", query, steps, base, tmp_path / "pb",
                              boot_ms=30000)
        t.join(timeout=300)
        out_a, js_a = got["a"]
        why = "\n" + "\n".join(map(str, js_a + js)) + W._sides(host, tmp_path, out + out_a)
        a_live, a_taken = W._tagged(js_a, "A_LIVE"), W._tagged(js_a, "A_TAKEN")
        a_still, a_back = W._tagged(js_a, "A_STILL"), W._tagged(js_a, "A_BACK")
        b_live, b_taken = W._tagged(js, "B_LIVE"), W._tagged(js, "B_TAKEN")
        b_still = W._tagged(js, "B_STILL")
        assert a_live and a_live["shown"] == "none", "the first page signed in" + why
        assert b_live and b_live["shown"] == "none", "the second page signed in" + why
        assert a_taken["said"].startswith("Another browser signed in to this console"), why
        assert a_taken["button"] == "take it back" and a_taken["typing"] == "none", why
        assert a_still["opens"] == a_taken["opens"] == 1 and a_still["shown"] == "flex", (
            "the taken page asked for nothing by itself" + why)
        assert a_back["opens"] >= 2 and a_back["shown"] == "none", "the click took it back" + why
        assert b_taken["head"] == "disconnected", "the second page was told in turn" + why
        assert b_still["opens"] == b_taken["opens"] and b_still["shown"] == "flex", (
            "...and asked for nothing by itself" + why)
    finally:
        t.join(timeout=5)
        server.terminate()
        host.end()
        air.close()
        shutil.rmtree(root, ignore_errors=True)
