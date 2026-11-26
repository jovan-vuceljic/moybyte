"""A match in a real browser: the page a Zero serves plays a console.

The board is real C: the web terminal's host harness built with the live
socket and its radio over a UDP air (tests/test_live_link.py's twin), and
serve.py --board serves the bundle in front of it. The console is
test_espnow_link's on the same air, in real time on a thread of its own: it
announces the cart, offers, and simulates each frame the match lets it. The
page opens the cart, its Player brings the board's radio up through the live
socket, and both sides simulate one match, a Lua cart's and a Python one's
(the page's Python computes as a board's: tests/test_web_lockstep_floats.py).

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_live_e2e.py
"""

import os
import hashlib
import random
import shutil
import sys
import threading
import time

import pytest

import web_e2e
from web_e2e import ROOT

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, str(ROOT / "tools"))

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")

CARTS = ("Brick Siege Lua", "Brick Siege")


@pytest.fixture(scope="module")
def live_exe(tmp_path_factory):
    web_e2e.require("term", "signin")
    import test_moy_tty as T
    out = tmp_path_factory.mktemp("live")
    return T._build(out, extra=[os.path.join(T.NET, "moy_live.c"),
                                os.path.join(T.NET, "moy_link_host.c")],
                    defines=("MOY_NET_LIVE=1", "MOY_NET_LINK=1"))


class Console:
    """A console on the air, playing `cart`: test_espnow_link's link, polled
    and advanced every 16 ms with random held buttons."""

    def __init__(self, air, cart):
        import test_espnow_link as E
        from runtime.run import players as P
        self.P = P
        radio, wlan = E._FakeRadio(air, bytes.fromhex("020000000003")), \
            E._FakeWlan(bytes.fromhex("020000000003"))
        radio.wlan = wlan
        self.link = P.EspNowLink(board="tdeck", name="Deck", radio=radio, wlan=wlan,
                                 launch=lambda ws, title: True)
        self.ws = E._Ws()
        self.cart = cart
        self.alive = True
        self.frames = 0
        self.stalls = 0
        self.t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        P, lk, ws = self.P, self.link, self.ws
        lk.start()
        lk.announce(self.cart, 1)
        rng = random.Random(5)
        while self.alive:
            lk.poll(ws)
            if ws.netplay is None and lk.peers:
                lk.offer(ws, self.cart)
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


@pytest.mark.parametrize("loader", [False, True], ids=["page", "loader"])
@pytest.mark.parametrize("cart", CARTS)
def test_a_page_a_zero_serves_plays_a_console(cart, loader, live_exe, tmp_path, monkeypatch):
    """`loader`: the board's root is the loader (an online console, the C3's),
    whose worker runs from the pack it fetched, not from the board's origin."""
    import gen_web_blob
    import test_live_link as L
    import test_moy_tty as T
    import test_web_term_e2e as W
    air = L.Air()
    monkeypatch.setenv("MOY_AIR", str(air.port))
    monkeypatch.setenv("MOY_AIR_MAC", "020000000001")
    root = W.tempfile.mkdtemp(prefix="moyl")
    page = None
    if loader:
        data, body = gen_web_blob.pack(gen_web_blob.collect(str(ROOT / "firmware" / "web_runner"
                                                                / "dist"))[0])
        page = (body.hex(), hashlib.sha256(data).hexdigest())
    host = T.Host(live_exe, W.pathlib.Path(root), page=page)
    store = host.tree / "sd" / "moybyte" / "carts"
    for src in sorted((ROOT / "system_carts").glob("*.moy")):
        shutil.copytree(src, store / src.name)
    server, base = W._serve(tmp_path, host.port, extra=["--loader"] if loader else [])
    console = Console(air, cart)
    console.t.start()
    st = ("window.__moyState().then(s => '%s ' + JSON.stringify({link: s.link, "
          "cart: s.cart, notice: s.notice, stats: s.link_stats, live: s.live && "
          "{opens: s.live.opens, drops: s.live.drops, up: s.live.up, down: s.live.down}}))")
    try:
        steps = [{"waitFor": "window.__moyState().then(s => s.cart === %r)" % cart,
                  "timeout": 30000},
                 {"js": st % "OPEN"},
                 {"waitFor": "window.__moyState().then(s => s.link && s.link[2])",
                  "timeout": 30000},
                 {"wait": 4000},
                 {"js": st % "PLAYED"}]
        query = ("?dev=1&desktop=1&linkcheck=1&cart=" + cart.replace(" ", "%20")
                 + W._qr_fragment(host))
        out, js = web_e2e.run(tmp_path, "live_match", query, steps, base,
                              tmp_path / "chrome", boot_ms=30000)
        played = W._tagged(js, "PLAYED")
        why = "\n%s\n-- console: frames %d stalls %d peers %s\n%s" % (
            js, console.frames, console.stalls, console.link.peers,
            W._sides(host, tmp_path, out))
        print("%s: page %s | console frames %d, stalled %d" % (
            cart, (played or {}).get("stats", {}).get("match"), console.frames, console.stalls))
        assert played and played["link"][2], "the match formed on the page" + why
        assert played["link"][3] > 60, "the page simulated the match" + why
        assert console.frames > 60, "the console simulated the match" + why
        assert played["stats"]["world_check"], "?linkcheck=1 armed the world check" + why
        assert played["stats"]["match"]["desync"] is None, "the checkpoints agreed" + why
    finally:
        console.end()
        server.terminate()
        host.end()
        air.close()
        shutil.rmtree(root, ignore_errors=True)


def test_the_live_socket_comes_back_after_the_board_restarts(live_exe, tmp_path, monkeypatch):
    """The board resets under an open page: its sessions are gone, so it
    refuses the page's reopened socket with a 401 the browser cannot read.
    The page asks the same route over HTTP, signs in again with the key it
    paired, and its socket opens again, the page never loaded again."""
    import test_live_link as L
    import test_moy_tty as T
    import test_web_term_e2e as W
    air = L.Air()
    monkeypatch.setenv("MOY_AIR", str(air.port))
    monkeypatch.setenv("MOY_AIR_MAC", "020000000001")
    root = W.tempfile.mkdtemp(prefix="moyl")
    host = T.Host(live_exe, W.pathlib.Path(root))
    store = host.tree / "sd" / "moybyte" / "carts"
    for src in sorted((ROOT / "system_carts").glob("*.moy")):
        shutil.copytree(src, store / src.name)
    server, base = W._serve(tmp_path, host.port)
    restarted = []

    def reset():
        host.wait_line("LIVE sessions=1", timeout=120.0)
        time.sleep(2.0)
        host.restart()
        restarted.append(time.monotonic())

    t = threading.Thread(target=reset, daemon=True)
    t.start()
    st = ("window.__moyState().then(s => '%s ' + JSON.stringify({stay: window.__stay || 0, "
          "opens: s.live && s.live.opens, drops: s.live && s.live.drops}))")
    try:
        steps = [{"waitFor": "window.__moyState().then(s => s.live && s.live.opens >= 1)",
                  "timeout": 60000},
                 {"js": "(window.__stay = 1, 1)"}, {"js": st % "BEFORE"},
                 {"waitFor": "window.__moyState().then(s => s.live && s.live.opens >= 2)",
                  "timeout": 90000},
                 {"js": st % "AFTER"}]
        query = "?dev=1&desktop=1" + W._qr_fragment(host)
        out, js = web_e2e.run(tmp_path, "live_restart", query, steps, base,
                              tmp_path / "chrome", boot_ms=30000)
        t.join(5)
        before, after = W._tagged(js, "BEFORE"), W._tagged(js, "AFTER")
        why = "\n%s\n%s" % (js, W._sides(host, tmp_path, out))
        assert restarted, "the board never restarted" + why
        assert before and before["opens"] == 1, why
        assert after and after["opens"] >= 2 and after["drops"] >= 1, why
        assert after["stay"] == 1, "the page loaded again" + why
    finally:
        server.terminate()
        host.end()
        air.close()
        shutil.rmtree(root, ignore_errors=True)


def test_the_terminal_of_a_page_a_zero_serves_rides_the_live_socket(
        live_exe, tmp_path, monkeypatch):
    """A board with the live socket serves its page's shell on it
    (native/moy_tty/moy_tty_live.c): the Terminal's keys and the shell's
    bytes cross the one socket the page holds, its exit says the status,
    and after the board restarts under it the socket comes back and Enter
    opens a new face on it."""
    import test_live_link as L
    import test_web_term_e2e as W
    air = L.Air()
    monkeypatch.setenv("MOY_AIR", str(air.port))
    monkeypatch.setenv("MOY_AIR_MAC", "020000000001")
    root = W.tempfile.mkdtemp(prefix="moyl")
    host = W._board(live_exe, W.pathlib.Path(root))
    server, base = W._serve(tmp_path, host.port)
    restarted = []

    def reset():
        """The board restarts once the page's second face is up."""
        end = time.monotonic() + 180
        while time.monotonic() < end:
            try:
                st = host.stats()
            except (IndexError, ValueError, OSError):
                st = {}
            if st.get("sessions") == "2" and st.get("live") == "1":
                time.sleep(1.0)
                host.restart()
                restarted.append(time.monotonic())
                return
            time.sleep(0.1)

    t = threading.Thread(target=reset, daemon=True)
    t.start()
    live = ("window.__moyState().then(s => '%s ' + JSON.stringify({opens: s.live && s.live.opens, "
            "drops: s.live && s.live.drops}))")
    try:
        steps = ([W._until(W._SHELL), W._lines("OPEN"), {"js": live % "LIVE1"}]
                 + W._typed("echo zero-$((6*7))") + [{"key": "Enter"}, W._says("zero-42"),
                                                     W._lines("ECHO")]
                 + W._typed("exit 5") + [{"key": "Enter"}, W._says("[the shell exited 5]"),
                                         W._lines("EXIT"), {"key": "Enter"},
                                         W._until(W._SHELL),
                                         W._until("ln => ln.includes('was lost')", 90000), W._lines("LOST"),
                                         {"waitFor": "window.__moyState().then(s => "
                                          "s.live && s.live.opens >= 2)", "timeout": 90000},
                                         {"key": "Enter"}, W._until(W._SHELL, 60000)]
                 + W._typed("echo back-$((6*7))") + [{"key": "Enter"}, W._says("back-42"),
                                                     W._lines("BACK"), {"js": live % "LIVE2"}])
        out, js = W._play(tmp_path, "term_live", base, steps, after=W._qr_fragment(host))
        t.join(5)
        why = "\n%s\n%s" % (js, W._sides(host, tmp_path, out))
        assert "zero-42" in "\n".join(W._tagged(js, "ECHO")), why
        assert "[the shell exited 5]" in "\n".join(W._tagged(js, "EXIT")), why
        assert W._tagged(js, "LIVE1")["opens"] == 1, why
        assert restarted, "the board never restarted" + why
        assert "back-42" in "\n".join(W._tagged(js, "BACK")), why
        assert W._tagged(js, "LIVE2")["opens"] >= 2, why
    finally:
        server.terminate()
        host.end()
        air.close()
        shutil.rmtree(root, ignore_errors=True)


def test_a_store_change_another_page_made_reaches_the_page_at_once(
        live_exe, tmp_path, monkeypatch):
    """The board says on the live socket that its store changed under the
    page (native/moy_net/moy_live.c, THE HINTS: another page's sync here),
    and the page pulls it at once: the new cart is on its shelf. The page's
    requests ride the socket (THE REQUESTS): its boot's pulls, and the pull
    the hint asks for."""
    import test_live_hints as H
    import test_live_link as L
    import test_web_term_e2e as W
    air = L.Air()
    monkeypatch.setenv("MOY_AIR", str(air.port))
    monkeypatch.setenv("MOY_AIR_MAC", "020000000001")
    root = W.tempfile.mkdtemp(prefix="moyl")
    host = W._board(live_exe, W.pathlib.Path(root))
    server, base = W._serve(tmp_path, host.port)
    synced = []

    def other():
        """Another page syncs a new cart once this one's socket is up."""
        host.wait_line("LIVE sessions=1", timeout=120.0)
        time.sleep(3.0)
        H._other_syncs(host, H._batch("pushed.moy/main.lua",
                                      "function _draw() cls(3) end\n"))
        synced.append(time.monotonic())

    t = threading.Thread(target=other, daemon=True)
    t.start()
    st = ("window.__moyState().then(s => '%s ' + JSON.stringify({hints: s.hints, "
          "opens: s.live && s.live.opens, reqs: s.live && s.live.reqs}))")
    try:
        steps = [{"waitFor": "window.__moyState().then(s => s.live && s.live.opens >= 1)",
                  "timeout": 60000},
                 {"js": st % "BEFORE"},
                 {"waitFor": "window.__moyState().then(s => s.hints && s.hints.pulls >= 1)",
                  "timeout": 60000},
                 {"js": st % "AFTER"},
                 {"js": "(pzAsk(), 1)"},
                 {"waitFor": "Promise.resolve((window.__moyCarts || []).some("
                             "n => n.startsWith('pushed')))", "timeout": 10000},
                 {"js": "'CARTS ' + JSON.stringify(window.__moyCarts)"}]
        query = "?dev=1&desktop=1" + W._qr_fragment(host)
        out, js = web_e2e.run(tmp_path, "live_store", query, steps, base,
                              tmp_path / "chrome", boot_ms=30000)
        t.join(5)
        why = "\n%s\n%s" % (js, W._sides(host, tmp_path, out))
        before, after = W._tagged(js, "BEFORE"), W._tagged(js, "AFTER")
        assert synced, "the other page never synced" + why
        assert before["hints"]["pulls"] == 0, why
        assert after["hints"]["s"] >= 1 and after["hints"]["pulls"] >= 1, why
        assert before["reqs"] >= 3 and after["reqs"] > before["reqs"], why
        assert any(n.startswith("pushed") for n in W._tagged(js, "CARTS")), why
    finally:
        server.terminate()
        host.end()
        air.close()
        shutil.rmtree(root, ignore_errors=True)
