"""A board's device in a real browser: a cart on the page a Zero serves
opens the board's LoRa radio, sends, and hears the packet come back.

The board is real C: tests/test_live_dev.py's twin (the web terminal's host
harness with the live socket, the kernel's handle table and a fake `lora`
kind whose radio hears what it sends), with serve.py --board in front. The
cart is a Lua one written here: its first run asks, naming the radio, and
the test answers Open. It opens `lora` through moybyte.dev_open, writes "ping", and on the
radio's RX event reads the packet and answers "pong" with its RSSI, which
the board hears and pushes back too. The page's counts (`__moyState().devs`)
say each crossing happened.

    MOYBYTE_WEB_E2E=1 .venv/bin/python -m pytest tests/test_web_live_dev_e2e.py
"""

import json
import os
import shutil
import sys

import pytest

import web_e2e
from web_e2e import ROOT

sys.path.insert(0, os.path.dirname(__file__))

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOYBYTE_WEB_E2E"),
    reason="MOYBYTE_WEB_E2E not set (spawns headless Chrome)")

TITLE = "Relay Test"
# What it got, in pmem (the page's state carries the first cells): 0 the
# step it reached (1 opened, 2 sent, 3 heard its ping, 4 heard the pong),
# 1 why the open failed (moy_app's code, 0 none), 2 the RSSI it read.
MAIN = """
local CODES = { STALE = 1, FULL = 2, NOMEM = 3, DENIED = 4, IO = 6, BAD = 7, ABSENT = 8,
                BUSY = 11 }
local h, sent, answered = nil, false, false

function _init()
  moybyte.on("lora", function(_, ev)
    if ev ~= 1 or not h then return end
    while true do
      local p = moybyte.dev_read(h, 256)
      if not p or #p == 0 then return end
      if p == "ping" then
        pmem(0, 3)
        pmem(2, moybyte.dev_get(h, "rssi"))
        answered = "pong"
      elseif p == "pong" then
        pmem(0, 4)
      end
    end
  end)
  local why
  h, why = moybyte.dev_open("lora", "freq=868100000 sf=9 listen=1")
  if h then pmem(0, 1) else pmem(1, CODES[why] or 99) end
end

function _update()
  if not h then return end
  if not sent and moybyte.dev_write(h, "ping") then sent = true; pmem(0, 2) end
  if answered == "pong" and moybyte.dev_write(h, "pong") then answered = true end
end

function _draw()
  cls(1)
end
"""


def _cart(store):
    d = store / "relaytest.moy"
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({
        "format": "moy-1", "version": 1, "title": TITLE, "id": "relaytest",
        "runtime": "lua", "main": "main.lua", "canvas": "128x128",
        "moybyte": {"type": "app", "permissions": ["graphics", "input", "lora"],
                    "required": ["lora"]}}))
    (d / "main.lua").write_text(MAIN)


def test_a_cart_on_the_page_sends_and_hears_on_the_board_s_radio(tmp_path, monkeypatch):
    web_e2e.require("term", "signin")
    import test_live_dev as D
    import test_live_link as L
    import test_moy_tty as T
    import test_web_term_e2e as W
    (tmp_path / "twin").mkdir()
    exe = T._build(tmp_path / "twin", extra=[os.path.join(T.NET, "moy_live.c"),
                                             os.path.join(T.NET, "moy_live_dev.c"),
                                             os.path.join(T.NET, "moy_link_host.c"),
                                             D.FAKE] + D.TABLE,
                   defines=("MOY_NET_LIVE=1", "MOY_NET_LINK=1", "MOY_TTY_LEASES=1"),
                   incs=(D.KERNEL, D.INPUT))
    air = L.Air()
    monkeypatch.setenv("MOY_AIR", str(air.port))
    monkeypatch.setenv("MOY_AIR_MAC", "020000000001")
    root = W.tempfile.mkdtemp(prefix="moyd")
    host = T.Host(exe, W.pathlib.Path(root))
    store = host.tree / "sd" / "moybyte" / "carts"
    for src in sorted((ROOT / "system_carts").glob("*.moy")):
        shutil.copytree(src, store / src.name)
    _cart(store)
    server, base = W._serve(tmp_path, host.port)
    st = ("window.__moyState().then(s => '%s ' + JSON.stringify({cart: s.cart, devs: s.devs, "
          "pmem: s.pmem, card: s.card, error: s.cart_error}))")
    try:
        # its first run asks (it arrived as files): "Open Relay Test?", which
        # names the radio, No focused; Open records the consent and runs it
        steps = [{"waitFor": "window.__moyState().then(s => !!(s.card && /LoRa/.test("
                             "s.card.lines.join(' '))))", "timeout": 30000},
                 {"js": "cv.focus(), 'focused'"}, {"key": "ArrowRight"}, {"wait": 300},
                 {"key": "Enter"},
                 {"waitFor": "window.__moyState().then(s => s.cart === %r)" % TITLE,
                  "timeout": 30000},
                 {"waitFor": "window.__moyState().then(s => s.devs && s.devs.records >= 2)",
                  "timeout": 20000},
                 {"js": st % "HEARD"}]
        query = "?dev=1&desktop=1&cart=" + TITLE.replace(" ", "%20") + W._qr_fragment(host)
        out, js = web_e2e.run(tmp_path, "live_dev", query, steps, base, tmp_path / "chrome",
                              boot_ms=30000)
        heard = W._tagged(js, "HEARD")
        print("the page's device channel: %s, pmem %s" % (heard and heard["devs"],
                                                      heard and heard["pmem"][:3]))
        why = "\n%s\n%s\n-- the page from its boot:\n%s" % (js, W._sides(host, tmp_path, out),
                                                        out[:5000])
        assert heard and heard["devs"]["kinds"] == 1, "the probe named lora" + why
        d = heard["devs"]
        # ping and pong each went up, came back as a record, and woke the cart
        assert d["records"] >= 2 and d["events"] >= 4, why
        assert d["dropped"] == 0, why
        assert heard["pmem"][:3] == [4, 0, -57], "the cart read both packets" + why
    finally:
        server.terminate()
        host.end()
        air.close()
        shutil.rmtree(root, ignore_errors=True)
