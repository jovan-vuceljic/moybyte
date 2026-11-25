"""A Zero's Wi-Fi from the page it serves, in a REAL browser, against the
board twin (serve.py `--carts D --wifi W`: the board's own /wifi backend,
device/zero_wifi.py, over a fake radio that drops every request while it is
off the network the page reached it over).

One page, driven as a person drives it -- the system menu, Settings' Wi-Fi
row, the panel's keys, a typed password, the move's question -- through:

  * a network SAVED without a move (the question's Save), on the board's
    saved list and nowhere near its radio;
  * the same network FORGOTTEN, nothing dropped;
  * a move that FAILS (a wrong password): the board goes back, the page
    finds it again and says where the console is;
  * a move that WORKS: the page loses the board by design, waits out its
    windows and says where it went, with an Open to its .local address --
    an expected card, never the loss's.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_zero_wifi_e2e.py
"""

import json
import os
import pathlib
import shutil

import pytest

import web_e2e
from test_web_persist_e2e import _serve

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOME, RPT = "Home", "Home_RPT"
ENTER, RIGHT = "Enter", "ArrowRight"


def _panel(cond, timeout=15000):
    """A step that waits until the Wi-Fi panel's state `p` makes `cond` true."""
    return {"waitFor": "window.__moyState().then(s => { var p = s.wifi_panel; "
                       "return p && (%s); })" % cond, "timeout": timeout}


def _say(tag):
    return {"js": "window.__moyState().then(s => '%s ' + JSON.stringify("
                  "{p: s.wifi_panel, w: s.wifi, link: window.__moyLinkCard || null}))" % tag}


def _keys(*keys):
    out = []
    for k in keys:
        out += [{"key": k}, {"wait": 250}]
    return out


def _typed(text):
    """`text` into the focused field, pasted as the browser pastes: one step
    whose text a scrub of the output finds whole."""
    return [{"js": "send({type: 'paste', text: %s}), 'pasted'" % json.dumps(text)},
            {"wait": 400}]


def _focus(target=None, ssid=None):
    """Steps that walk the panel's focus with the arrow keys, as a hand
    does: to the stop `target` below the networks (down), or to the row of
    network `ssid` (up from below, down from above)."""
    walk = ("(function () { return new Promise(function (ok) { (function step(k) { "
            "window.__moyState().then(function (s) { var p = s.wifi_panel || {}, f = p.focus; "
            "var want = %s, i = (p.nets || []).indexOf(%s); "
            "if (want == null) want = 'net' + i + '/join'; "
            "if (f == want || k > 30) return ok('FOCUS ' + JSON.stringify([f, want])); "
            "var m = /^net(\\d+)/.exec(f || ''); "
            "var down = %s ? true : (f == null || (m && +m[1] < i)); "
            "var c = down ? 275 : 274; "
            "send({type: 'kd', code: c, mods: 0}); setTimeout(function () { "
            "send({type: 'ku', code: c, mods: 0}); setTimeout(function () { step(k + 1); }, 200); "
            "}, 120); }); })(0); }); })()"
            % (json.dumps(target), json.dumps(ssid), "true" if target else "false"))
    cond = ("p.focus == %s" % json.dumps(target) if target else
            "p.focus == 'net' + p.nets.indexOf(%s) + '/join'" % json.dumps(ssid))
    return [{"js": walk}, _panel(cond, 5000)]


def _move(ssid, password, choose, card="switch_save"):
    """Network `ssid` chosen, `password` typed where the panel asks for one
    (None: it is saved, and it does not), and the question it puts answered
    `choose` steps right of Cancel."""
    out = _focus(ssid=ssid) + _keys(ENTER)
    if password is not None:
        out += ([_panel("p.pick == %s" % json.dumps(ssid), 5000)] + _typed(password)
                + _keys(ENTER))
    return (out + [_panel("p.card && p.card[0] == %s" % json.dumps(card), 5000)]
            + _keys(*([RIGHT] * choose)) + _keys(ENTER))


def _forget(ssid):
    """Network `ssid` chosen, then Forget."""
    return _focus(ssid=ssid) + _focus("forget") + _keys(ENTER)


def test_the_boards_wifi_is_managed_from_its_page(tmp_path):
    web_e2e.require("store")
    store = tmp_path / "store"
    store.mkdir()
    for cart in ("moybyte.star_catcher.moy", "moybyte.sakura.moy"):
        shutil.copytree(ROOT / "system_carts" / cart, store / cart)
    saved = tmp_path / "wifi.json"
    saved.write_text(json.dumps({"networks": [{"ssid": HOME, "password": "homepw"}]}))
    radio = tmp_path / "radio.json"
    radio.write_text(json.dumps({
        "on": HOME, "join_ms": 3000, "back_ms": 3000, "delay": 0.8,
        "nets": [{"ssid": HOME, "password": "homepw", "rssi": -50},
                 {"ssid": RPT, "password": "rptpw", "rssi": -70}]}))
    p, base = _serve(web_e2e.free_port(), ("--carts", str(store), "--wifi", str(radio)))
    try:
        steps = ([{"wait": 2500},
                  {"waitFor": "window.__moyState().then(s => s.wifi && s.wifi[0])",
                   "timeout": 10000}, _say("BOOT")]
                 + web_e2e.menu_pick("Settings")
                 + [{"wait": 800}] + _keys(ENTER)
                 + [_panel("p.nets.length == 2 && p.focus == 'rescan'"), _say("OPEN")]
                 # SAVE: a new network's question offers Save, which moves nothing
                 + _move(RPT, "rptpw", 1)
                 + [_panel("p.known.indexOf(%s) >= 0 && !p.card" % json.dumps(RPT)),
                    {"wait": 1500}, _say("SAVED")]
                 # FORGET: the saved network picked, then Forget
                 + _forget(RPT)
                 + [_panel("p.known.length == 1"), {"wait": 1500}, _say("FORGOT")]
                 # A MOVE THAT FAILS: back on Home, and the page says so
                 + _move(RPT, "wrong", 2)
                 + [_panel("p.card && p.card[0] == 'tell'", 20000), _say("FAILED")]
                 + _keys(ENTER) + [_panel("!p.card", 5000)]
                 # A MOVE THAT WORKS: the page loses the board and says where it went
                 + _move(RPT, "rptpw", 2)
                 + [{"waitFor": "window.__moyLinkCard && window.__moyLinkCard.go",
                     "timeout": 30000}, {"wait": 500}, _say("MOVED")])
        out, js = web_e2e.run(tmp_path, "zero_wifi", "?dev=1&handheld=1", steps, base,
                              tmp_path / "chrome", boot_ms=30000)
    finally:
        p.terminate()
        p.wait(timeout=10)
    said = {}
    for j in js:
        tag, _, doc = str(j).partition(" ")
        if doc[:1] in ("{", "["):
            said[tag] = json.loads(doc)
    assert said["BOOT"]["w"][:2] == [True, HOME], said["BOOT"]
    assert said["OPEN"]["p"]["nets"] == [HOME, RPT]
    assert said["SAVED"]["p"]["known"] == [HOME, RPT], said["SAVED"]
    assert said["FORGOT"]["p"]["known"] == [HOME], said["FORGOT"]
    assert said["FAILED"]["p"]["card"] == ["tell", "Still on %s" % HOME], said["FAILED"]
    assert said["FAILED"]["w"][:2] == [True, HOME]
    moved = said["MOVED"]["link"]
    assert moved["head"] == "the console moved to %s" % RPT, moved
    assert moved["bad"] is False and "moybyte-twin.local" in moved["go"], moved
    assert said["MOVED"]["p"]["card"][0] == "open", said["MOVED"]
    assert said["MOVED"]["w"][:2] == [True, "moved to %s" % RPT], said["MOVED"]
    # The board: the moved-to network saved first, its password never on the page.
    nets = json.loads(saved.read_text())["networks"]
    assert [n["ssid"] for n in nets] == [RPT, HOME]
    assert "rptpw" not in out and "homepw" not in out
