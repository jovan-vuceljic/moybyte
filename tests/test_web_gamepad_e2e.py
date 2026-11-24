"""A gamepad held at the browser drives the hosted console, in a real
browser (#254): the page polls the Gamepad API once a frame
(firmware/web_runner/page_tail.js), and here a stand-in for
`navigator.getGamepads` holds one standard-mapping pad whose buttons the
steps press. With the pad's buttons alone: the pad's focus and keys show
the moment it connects, the d-pad moves the home's selection, R steps the
tabs and L steps back, A opens an app and B leaves it, A plays a game and
Start's pause card quits it; the pad leaving gives the keyboard back, and
coming back takes over again. On the desk the pad's focus is on the tiles,
A on Play opens the console-mode home and B comes back, and Start opens
and closes the system menu. The mapping and the console's half are
tests/test_web_gamepad.py's.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_gamepad_e2e.py

One Chrome boot a test.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

import pytest

import web_e2e
from web_e2e import RUNNER

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")

# The stand-in pad: the standard mapping's 17 buttons and 4 axes, absent
# until `__pad.connected`; `__padTap(i)` holds button i for a few frames.
PAD = """
window.__pad = {id: "stand-in", index: 0, connected: false, mapping: "standard",
  timestamp: 0, axes: [0, 0, 0, 0],
  buttons: Array.from({length: 17}, () => ({pressed: false, touched: false, value: 0}))};
Object.defineProperty(Navigator.prototype, "getGamepads", {configurable: true,
  value: function () { return [window.__pad.connected ? window.__pad : null, null, null, null]; }});
const padWait = (ms) => new Promise((ok) => setTimeout(ok, ms));
window.__padTap = async function (i) {
  const b = window.__pad.buttons[i];
  b.pressed = true; b.value = 1; await padWait(160);
  b.pressed = false; b.value = 0; await padWait(260);
};
"""

# Standard-mapping indices.
A, B, L, R, START, UP, DOWN, LEFT, RIGHT = 0, 1, 4, 5, 9, 12, 13, 14, 15


@pytest.fixture
def base():
    web_e2e.require()
    port = web_e2e.free_port()
    p = subprocess.Popen([sys.executable, "serve.py", str(port), "dist"], cwd=RUNNER,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = "http://127.0.0.1:%d" % port
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(url + "/index.html", timeout=1).read(64)
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("serve.py never answered")
        yield url
    finally:
        p.terminate()
        p.wait(timeout=10)


def _probe(tag):
    return {"js": "window.__moyState().then(s => '%s ' + JSON.stringify("
                  "{input: s.input, stack: s.stack, cart: s.cart, screen: s.screen,"
                  " order: s.order, sysmenu: s.edit.sysmenu}))" % tag}


def _tap(i, settle=300):
    return [{"js": "window.__padTap(%d).then(() => 'tap %d')" % (i, i)}, {"wait": settle}]


def _tap_until(i, cond, most=8):
    """Tap button `i` until `cond` (a JS expression over the state `s`)
    holds, at most `most` times."""
    return {"js": "(async () => { let n = 0; for (; n < %d; n++) {"
                  " const s = await window.__moyState(); if (%s) break;"
                  " await window.__padTap(%d); await new Promise(ok => setTimeout(ok, 300)); }"
                  " return 'taps ' + n; })()" % (most, cond, i)}


def _tagged(js):
    out = {}
    for j in js:
        if isinstance(j, str) and " " in j and j.split(" ", 1)[0].isupper():
            tag, body = j.split(" ", 1)
            out[tag] = json.loads(body)
    return out


def _run(tmp_path, base, name, query, steps):
    out, js = web_e2e.run(tmp_path, name, query, [{"init": PAD}] + steps, base,
                          tmp_path / ("chrome_" + name), boot_ms=30000)
    return out[-3000:], _tagged(js)


def _connect(tag, on=True):
    return [{"js": "window.__pad.connected = %s; 'pad'" % ("true" if on else "false")},
            {"wait": 500}, _probe(tag)]


def test_a_gamepad_alone_drives_the_handheld(tmp_path, base):
    """The 320x240 console: the home, an app, a game and its pause card."""
    tail, got = _run(tmp_path, base, "pad_handheld", "?dev=1&handheld=1", [
        {"note": "the console up", "wait": 5000},
        _probe("START"),
        *_connect("CONNECTED"),
        *_tap(RIGHT, 1200), _probe("MOVED"),
        {"shot": "pad_focus"},
        _tap_until(R, "s.input.home_tab === 'apps'"), _probe("APPS"),
        *_tap(A, 2500), _probe("APP"),
        _tap_until(B, "s.stack.length === 1"), _probe("APP_LEFT"),
        _tap_until(L, "s.input.home_tab === 'games'"),
        *_tap(A, 3000), _probe("PLAYING"),
        *_tap(START, 800), _probe("PAUSED"),
        _tap_until(DOWN, "s.input.pause_sel === 'Quit'"), _probe("ON_QUIT"),
        *_tap(A, 1500), _probe("QUIT"),
        *_connect("GONE", False),
        *_connect("BACK"),
    ])
    assert got["START"]["input"]["kind"] == "keys", tail
    assert "gamepad" not in got["START"]["input"]["sources"], tail

    con = got["CONNECTED"]["input"]
    assert "gamepad" in con["sources"], tail
    assert con["kind"] == con["hints"] == "pad", "the pad's focus and keys show at once"

    moved = got["MOVED"]["input"]
    assert moved["home_sel"] == con["home_sel"] + 1, got["MOVED"]
    assert moved["kind"] == "pad"

    assert got["APPS"]["input"]["home_tab"] == "apps", "R stepped no tab: %s" % got["APPS"]
    assert len(got["APP"]["stack"]) > 1, "A opened no app: %s" % got["APP"]
    assert got["APP_LEFT"]["stack"] == ["launcher"], "B left no app: %s" % got["APP_LEFT"]

    play = got["PLAYING"]
    assert play["stack"][-1] == "desktop" and play["cart"], "A played no game: %s" % play
    assert got["PAUSED"]["input"]["pause"], "Start opened no pause card"
    assert got["ON_QUIT"]["input"]["pause_sel"] == "Quit", got["ON_QUIT"]
    assert got["QUIT"]["stack"] == ["launcher"], "Quit did not come home: %s" % got["QUIT"]
    assert got["QUIT"]["input"]["pause"] is None

    gone = got["GONE"]["input"]
    assert "gamepad" not in gone["sources"] and gone["kind"] == "keys", gone
    back = got["BACK"]["input"]
    assert "gamepad" in back["sources"] and back["kind"] == "pad", back


def test_a_gamepad_alone_drives_the_desk(tmp_path, base):
    """The 1024x600 desk: the focus on its tiles, A on Play opening the
    console-mode home and B coming back to the desk, and Start's system
    menu."""
    tail, got = _run(tmp_path, base, "pad_desk", "?dev=1", [
        {"note": "the console up", "wait": 5000},
        *_connect("CONNECTED"),
        *_tap(DOWN, 800), _probe("MOVED"),
        {"shot": "pad_desk_focus"},
        *_tap(UP, 800),
        *_tap(A, 2500), _probe("OPENED"),
        *_tap(B, 1200), _probe("CLOSED"),
        *_tap(START, 800), _probe("MENU"),
        *_tap(START, 800), _probe("MENU_SHUT"),
    ])
    con = got["CONNECTED"]
    assert con["screen"] == "desk" and con["input"]["kind"] == "pad", tail
    assert got["MOVED"]["input"]["desk_focus"] == "tiles", "no focus on the desk's tiles"
    assert got["OPENED"]["stack"] == ["launcher"], "A on Play opened no home: %s" % got
    assert got["CLOSED"]["stack"] == con["stack"], "B came back to no desk: %s" % got["CLOSED"]
    assert got["MENU"]["sysmenu"], "Start opened no system menu"
    assert not got["MENU_SHUT"]["sysmenu"], "Start did not close it"
