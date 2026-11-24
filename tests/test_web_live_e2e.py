"""A match in a real browser: the page a Zero serves plays a console.

The board is real C: the web terminal's host harness built with the live
socket and its radio over a UDP air (tests/test_live_link.py's twin), and
serve.py --board serves the bundle in front of it. The console is
test_espnow_link's on the same air, in real time on a thread of its own: it
announces the cart, offers, and simulates each frame the match lets it. The
page opens the cart, its Player brings the board's radio up through the live
socket, and both sides simulate one match.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_live_e2e.py
"""

import os
import random
import shutil
import sys
import threading
import time

import pytest

import web_e2e
from web_e2e import ROOT

sys.path.insert(0, os.path.dirname(__file__))

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")

CART = "Brick Siege Lua"


@pytest.fixture(scope="module")
def live_exe(tmp_path_factory):
    web_e2e.require("term", "signin")
    import test_moy_tty as T
    out = tmp_path_factory.mktemp("live")
    return T._build(out, extra=[os.path.join(T.NET, "moy_live.c"),
                                os.path.join(T.NET, "moy_link_host.c")],
                    defines=("MOY_NET_LIVE=1", "MOY_NET_LINK=1"))


class Console:
    """A console on the air, playing CART: test_espnow_link's link, polled
    and advanced every 16 ms with random held buttons."""

    def __init__(self, air):
        import test_espnow_link as E
        from runtime.run import players as P
        self.P = P
        radio, wlan = E._FakeRadio(air, bytes.fromhex("020000000003")), \
            E._FakeWlan(bytes.fromhex("020000000003"))
        radio.wlan = wlan
        self.link = P.EspNowLink(board="tdeck", name="Deck", radio=radio, wlan=wlan,
                                 launch=lambda ws, title: True)
        self.ws = E._Ws()
        self.alive = True
        self.frames = 0
        self.stalls = 0
        self.t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        P, lk, ws = self.P, self.link, self.ws
        lk.start()
        lk.announce(CART, 1)
        rng = random.Random(5)
        while self.alive:
            lk.poll(ws)
            if ws.netplay is None and lk.peers:
                lk.offer(ws, CART)
            np = ws.netplay
            if np is not None:
                ws.input.down = {b for b in ("left", "right", "a") if rng.random() < 0.3}
                f = np.frame
                np.advance(P.mask_of(ws.input, P.CART_BUTTONS))
                if np.frame == f:
                    self.stalls += 1
                self.frames = np.frame
            time.sleep(0.016)

    def end(self):
        self.alive = False
        self.t.join(2)


def test_a_page_a_zero_serves_plays_a_console(live_exe, tmp_path, monkeypatch):
    import test_live_link as L
    import test_moy_tty as T
    import test_web_term_e2e as W
    air = L.Air()
    monkeypatch.setenv("MOY_AIR", str(air.port))
    monkeypatch.setenv("MOY_AIR_MAC", "020000000001")
    root = W.tempfile.mkdtemp(prefix="moyl")
    host = T.Host(live_exe, W.pathlib.Path(root))
    store = host.tree / "sd" / "moybyte" / "carts"
    for cart in sorted((ROOT / "system_carts").glob("*.moy")):
        shutil.copytree(cart, store / cart.name)
    server, base = W._serve(tmp_path, host.port)
    console = Console(air)
    console.t.start()
    st = ("window.__moyState().then(s => '%s ' + JSON.stringify({link: s.link, "
          "cart: s.cart, notice: s.notice, live: s.live && {opens: s.live.opens, "
          "drops: s.live.drops, up: s.live.up, down: s.live.down}}))")
    try:
        steps = [{"waitFor": "window.__moyState().then(s => s.cart === %r)" % CART,
                  "timeout": 30000},
                 {"js": st % "OPEN"},
                 {"waitFor": "window.__moyState().then(s => s.link && s.link[2])",
                  "timeout": 30000},
                 {"wait": 4000},
                 {"js": st % "PLAYED"}]
        query = "?dev=1&desktop=1&cart=" + CART.replace(" ", "%20") + W._qr_fragment(host)
        out, js = web_e2e.run(tmp_path, "live_match", query, steps, base,
                              tmp_path / "chrome", boot_ms=30000)
        played = W._tagged(js, "PLAYED")
        why = "\n%s\n-- console: frames %d stalls %d peers %s\n%s" % (
            js, console.frames, console.stalls, console.link.peers,
            W._sides(host, tmp_path, out))
        assert played and played["link"][2], "the match formed on the page" + why
        assert played["link"][3] > 60, "the page simulated the match" + why
        assert console.frames > 60, "the console simulated the match" + why
    finally:
        console.end()
        server.terminate()
        host.end()
        air.close()
        shutil.rmtree(root, ignore_errors=True)
