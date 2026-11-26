"""The live socket's radio link (native/moy_net/moy_live.c, #256): a page a
Zero serves plays a console's match on its board's radio.

The board twins are the web terminal's host harness (tests/test_moy_tty.py's
tty_main) built with the live socket and the host's radio
(native/moy_net/moy_link_host.c), whose ESP-NOW is a UDP air this file runs.
Each page is the browser's half: its link (native/moy_net/moy_link_web.c,
the C the wasm builds, loaded once a page) under `players.EspNowLink` and the
match's C, and its socket a WebSocket client here, sealed as the worker
seals it (tests/seal_client.py, slot 1) on one twin and open on the other.
A console on the same air is test_espnow_link's fake radio.

What it holds: the probe and the handshake; two pages playing one lockstep
match through two boards to the same inputs on every frame; a page and a
console doing the same; a lost input stalling both sides, never guessed;
a dropped socket reconnecting and the match carrying on; the socket's
echo, and a channel the board does not serve passed over.
"""
import base64
import ctypes
import json
import os
import random
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import types

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import seal_client  # noqa: E402
import test_espnow_link as E  # noqa: E402
import test_moy_tty as T  # noqa: E402
from runtime import players as P  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("cc") is None, reason="needs a C compiler")

BCAST = b"\xff" * 6
MAC_A, MAC_B, MAC_C = bytes.fromhex("020000000001"), bytes.fromhex("020000000002"), \
    bytes.fromhex("020000000003")
CART = "Brick Siege"


@pytest.fixture(scope="module")
def twin_exe(tmp_path_factory):
    out = tmp_path_factory.mktemp("live")
    return T._build(out, extra=[os.path.join(T.NET, "moy_live.c"),
                                os.path.join(T.NET, "moy_link_host.c")],
                    defines=("MOY_NET_LIVE=1", "MOY_NET_LINK=1"))


@pytest.fixture(scope="module")
def page_so(tmp_path_factory):
    """The page's link as a library, one copy a page (its state is static)."""
    out = tmp_path_factory.mktemp("page")
    so = str(out / "link_web.so")
    subprocess.run([shutil.which("cc"), "-shared", "-fPIC", "-O1", "-std=gnu99",
                    "-DMOY_NET_LINK=1", "-DMOY_NET_LIVE_PAGE=1", "-I" + T.NET,
                    os.path.join(T.NET, "moy_link_web.c"), "-o", so], check=True)
    return so


def _page_lib(so, name, tmp):
    path = os.path.join(tmp, name + ".so")
    shutil.copy(so, path)
    d = ctypes.CDLL(path)
    U32, Z, I, B = ctypes.c_uint32, ctypes.c_size_t, ctypes.c_int, ctypes.c_char_p
    for fn, args, res in (("moy_link_start", [U32], I), ("moy_link_stop", [], None),
                          ("moy_link_rate", [I], I), ("moy_link_channel", [I], I),
                          ("moy_link_add_peer", [B], I), ("moy_link_mac", [B], None),
                          ("moy_link_frame_max", [], U32), ("moy_link_send", [B, B, Z], I),
                          ("moy_link_recv", [B, B, U32], I),
                          ("moy_link_web_take", [B, Z], Z), ("moy_link_web_give", [B, Z], None),
                          ("moy_link_web_open", [I], None)):
        f = getattr(d, fn)
        f.argtypes = args
        f.restype = res
    return d


# -- the air ------------------------------------------------------------------

class Air:
    """ESP-NOW for the twins (UDP, moy_link_host.c's datagrams) and the
    consoles (test_espnow_link's fake radios): every frame to every station
    but its sender, a unicast to its address alone. `cut` drops what the
    stations it names send; `deaf` drops everything."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.twins = {}
        self.radios = {}
        self.cut = set()
        self.deaf = False
        self.sent = 0
        self.lock = threading.Lock()
        self.alive = True
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def _run(self):
        self.sock.settimeout(0.05)
        while self.alive:
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            if data[:3] == b"REG":
                with self.lock:
                    self.twins[data[3:9]] = addr
            elif data[:3] == b"BYE":
                with self.lock:
                    self.twins.pop(data[3:9], None)
            elif len(data) >= 12:
                self.carry(data[:6], data[6:12], data[12:])

    def carry(self, src, dst, payload):
        with self.lock:
            self.sent += 1
            if self.deaf or src in self.cut:
                return
            for mac, addr in self.twins.items():
                if mac != src and dst in (BCAST, mac):
                    self.sock.sendto(src + payload, addr)
            for mac, r in self.radios.items():
                if mac != src and dst in (BCAST, mac):
                    r.inbox.append((src, payload))

    def close(self):
        self.alive = False
        self.sock.close()


@pytest.fixture
def air():
    a = Air()
    yield a
    a.close()


# -- a board twin and its page -------------------------------------------------

def _twin(exe, tmp_path, monkeypatch, air, mac, sealed, **kw):
    monkeypatch.setenv("MOY_AIR", str(air.port))
    monkeypatch.setenv("MOY_AIR_MAC", mac.hex())
    return live_host(T.Host(exe, tmp_path, sealed=sealed, **kw))


def live_host(h):
    """A twin whose page talks to it on its live socket alone: `h.page` the
    signed-in page's client once a Page signed in (its requests ride the
    host's open Page, `h.sock`), `h.probe()` the open GET /live."""
    h.page = None
    h.sock = None
    h.ask = lambda method, target, body=b"": h.sock.ask(method, target, body)
    h.probe = lambda: json.loads(seal_client.split(h.send("GET", "/live"))[2])
    return h


def board_id(host):
    """A board's id, from a hello on a socket signing in: a board with the
    live socket answers no sign-in over HTTP."""
    shim = live_host(types.SimpleNamespace(port=host.port, send=host.send))
    page = Page(shim, None, True).open(bare=True)
    try:
        return seal_client.Browser(shim.ask).hello()["id"]
    finally:
        page.drop()


class Page:
    """A page's socket and link, the worker's job done by hand: what the
    link queued goes up, what the board sends goes into the link. On a
    sealed twin its first socket signs in on itself (the QR's token, as
    the worker's sign-in), and a later one resumes the session; its
    requests (`ask`) are the worker's request channel."""

    def __init__(self, host, lib, sealed):
        self.host, self.lib, self.sealed = host, lib, sealed
        self.on = False                 # its frames sealed
        self.id = 0                     # its last request's
        self.frames = []                # (kind, plaintext length) of each answer frame
        self.c = None
        self.buf = b""
        self.closed = None
        self.echoes = []
        self.terms = []                 # the terminal channel's messages, 't' and all
        self.hints = []                 # the hints' letters, a message each
        self.answers = []               # the requests' messages, 'r' and all
        self.out = ctypes.create_string_buffer(16384)

    def open(self, proto="moy.live", signin=None, bare=False, via=None):
        """The socket: sealed under the host's session where it has one,
        else signed in on itself by `signin` (a Browser's pairing, called
        with it; the QR's token by default), or left in the clear and not
        signed in (`bare`). `via`: from 127.0.0.1 as the secure door
        connects, the browser it names that address (moy_net.h, THE DOOR'S
        BROWSERS)."""
        path = "/live"
        self.on = False
        resume = self.sealed and self.host.page is not None and signin is None and not bare
        if resume:
            path, _b, seq = self.host.page.seal("GET", "/live")
            seal_client.lib().moy_sw_ws(1, seq)
        if via is None:
            c = socket.create_connection(("127.0.0.1", self.host.port), timeout=5)
        else:
            c = socket.socket()
            c.settimeout(5)
            c.bind(("127.0.0.1", 0))
            at = len(self.host.log())
            self.host.say("via %d %s" % (c.getsockname()[1], via))
            self.host.wait_line("VIA %d" % c.getsockname()[1], at)
            c.connect(("127.0.0.1", self.host.port))
        key = base64.b64encode(os.urandom(16)).decode()
        c.sendall(("GET %s HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n"
                   "Sec-WebSocket-Protocol: %s\r\n\r\n" % (path, key, proto)).encode())
        data = b""
        while b"\r\n\r\n" not in data:
            k = c.recv(4096)
            assert k, data
            data += k
        head, _, self.buf = data.partition(b"\r\n\r\n")
        self.head = head.decode()
        assert self.head.startswith("HTTP/1.1 101"), self.head
        c.setblocking(False)
        self.c = c
        self.closed = None
        self.piece = self.host.probe().get("req", 0)
        self.host.sock = self
        self.on = resume
        if self.sealed and not resume and not bare:
            self.sign_in(signin or (lambda b: b.pair_token(self.host.token())))
        if self.lib is not None:
            self.lib.moy_link_web_open(1)
        return self

    def sign_in(self, how):
        """The sign-in on the socket, then its last frame in the clear and
        the seal (moy_live.c, THE SIGN-IN)."""
        b = seal_client.Browser(self.host.ask)
        how(b)
        self.send(b"cS")
        seal_client.lib().moy_sw_ws(1, 0)
        self.on = True
        self.host.page = b
        return b

    def ask(self, method, target, body=b""):
        """One request on the socket (moy_live.c, THE REQUESTS): its answer
        as the raw HTTP a client reads."""
        self.id += 1
        req = method.encode() + b" " + target.encode() + b"\n" + body
        first = self.piece - 8
        self.send(b"rQ" + struct.pack("<HI", self.id, len(req)) + req[:first])
        for at in range(first, len(req), self.piece - 4):
            self.send(b"rB" + struct.pack("<H", self.id) + req[at:at + self.piece - 4])
        status, ctype, body = self.answer()
        return b"HTTP/1.1 %d -\r\nContent-Type: %s\r\n\r\n" % (status, ctype) + body

    def answer(self, timeout=10.0):
        """(status, Content-Type, body) of request self.id, once its 'Z' or
        its 'W' came; each frame's (kind, plaintext length) kept in
        self.frames."""
        status, ctype, body = None, b"", b""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.pump()
            got, self.answers = self.answers, []
            for m in got:
                kind, mid = m[1:2], struct.unpack("<H", m[2:4])[0]
                assert mid == self.id, (mid, self.id)
                self.frames.append((kind, len(m)))
                at = 4
                if kind in (b"A", b"W"):
                    assert status is None, "a second head"
                    status, at = struct.unpack("<H", m[4:6])[0], 7 + m[6]
                    ctype = m[7:at]
                else:
                    assert kind in (b"D", b"Z"), kind
                    assert status is not None, "a body before its head"
                body += m[at:]
                if kind in (b"Z", b"W"):
                    return status, ctype, body
            if self.closed:
                raise AssertionError("the socket closed: %r" % (self.closed,))
            time.sleep(0.005)
        raise AssertionError("no answer to request %d" % self.id)

    def drop(self):
        self.c.close()
        self.c = None
        if self.lib is not None:
            self.lib.moy_link_web_open(0)

    def send(self, pl, op=2):
        if self.on:
            n = seal_client.lib().moy_sw_ws_up(1, seal_client.put(pl))
            assert n > 0
            pl = seal_client.got(n)
        mask = os.urandom(4)
        n = len(pl)
        head = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126
                                     else bytes([0x80 | 126]) + struct.pack(">H", n))
        self.c.sendall(head + mask + bytes(b ^ mask[i & 3] for i, b in enumerate(pl)))

    def _frames(self):
        while True:
            if len(self.buf) < 2:
                return
            op, n, at = self.buf[0] & 15, self.buf[1] & 127, 2
            if n == 126:
                if len(self.buf) < 4:
                    return
                n, at = struct.unpack(">H", self.buf[2:4])[0], 4
            if len(self.buf) < at + n:
                return
            pl, self.buf = self.buf[at:at + n], self.buf[at + n:]
            yield op, pl

    def pump(self):
        if self.c is None:
            return
        while True:
            try:
                k = self.c.recv(65536)
            except BlockingIOError:
                break
            if not k:
                self.closed = self.closed or (0, "eof")
                break
            self.buf += k
        for op, pl in self._frames():
            if op == 8:
                self.closed = (struct.unpack(">H", pl[:2])[0], pl[2:].decode())
                continue
            if op != 2:
                continue
            if self.on:
                n = seal_client.lib().moy_sw_ws_down(1, seal_client.put(pl))
                assert n >= 0, "a frame down that does not open"
                pl = seal_client.got(n)
            if pl[:1] in (b"n", b"d", b"m"):
                if self.lib is not None:
                    self.lib.moy_link_web_give(pl, len(pl))
            elif pl[:2] == b"cE":
                self.echoes.append(pl[2:])
            elif pl[:1] == b"t":
                self.terms.append(pl)
            elif pl[:2] == b"cH":
                self.hints.append(pl[2:])
            elif pl[:1] == b"r":
                self.answers.append(pl)
        if self.lib is None:
            return
        n = self.lib.moy_link_web_take(self.out, len(self.out))
        raw = self.out.raw[:n]
        at = 0
        while at + 2 <= len(raw):
            m = raw[at] | raw[at + 1] << 8
            self.send(raw[at + 2:at + 2 + m])
            at += 2 + m


class PageRadio:
    """The page's link as `EspNowLink`'s radio (players._RadioIo calls it)."""

    def __init__(self, lib):
        self.lib = lib
        self.mac6 = ctypes.create_string_buffer(6)
        self.data = ctypes.create_string_buffer(1470)

    def config(self, **kw):
        if "rate" in kw:
            self.lib.moy_link_rate(int(kw["rate"]))

    def active(self, on=None):
        if on is True:
            err = self.lib.moy_link_start(0)
            if err:
                raise OSError(err)
        elif on is False:
            self.lib.moy_link_stop()
        return True

    def add_peer(self, mac):
        self.lib.moy_link_add_peer(bytes(mac))

    def send(self, mac, payload, sync=False):
        return self.lib.moy_link_send(bytes(mac), bytes(payload), len(payload)) == 0

    def irecv(self, timeout=0):
        n = self.lib.moy_link_recv(self.mac6, self.data, 1470)
        if n < 0:
            return (None, None)
        return (self.mac6.raw, self.data.raw[:n])


class PageWlan:
    def __init__(self, lib):
        self.lib = lib

    def active(self, on=None):
        return True

    def isconnected(self):
        return True

    def config(self, *a, **kw):
        if kw or not a:
            return None
        if a[0] == "mac":
            b = ctypes.create_string_buffer(6)
            self.lib.moy_link_mac(b)
            return b.raw
        if a[0] == "channel":
            return abs(self.lib.moy_link_channel(0))
        return 0


def _settle(pages, ms=15):
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        for p in pages:
            p.pump()
        time.sleep(0.002)


def _page_link(page, clock, name):
    for _ in range(200):
        page.pump()
        if page.lib.moy_link_channel(0) != 0:
            break
        time.sleep(0.005)
    lk = P.EspNowLink(board="web", name=name, ticks_ms=clock, radio=PageRadio(page.lib),
                      wlan=PageWlan(page.lib), launch=lambda ws, title: True)
    assert lk.start(), lk.error
    return lk


def _console(air, clock):
    radio, wlan = E._FakeRadio(air, MAC_C), E._FakeWlan(MAC_C)
    radio.wlan = wlan
    lk = P.EspNowLink(board="tdeck", name="Deck", ticks_ms=clock, radio=radio, wlan=wlan,
                      launch=lambda ws, title: True)
    lk.start()
    return lk


def _meet(sides, pages, clock):
    """Every side on the cart until each hears the others, then the first
    offers and the match forms on both."""
    for lk, _ws in sides:
        lk.announce(CART, 0)
    for _ in range(100):
        clock.advance(300)
        for lk, ws in sides:
            lk.poll(ws)
        _settle(pages)
        if all(len(lk.peers) for lk, _ws in sides):
            break
    assert all(len(lk.peers) for lk, _ws in sides), "the sides hear each other"
    for lk, _ws in sides:
        lk.state = 1
    (la, wa), (lb, wb) = sides
    la.offer(wa, CART)
    for _ in range(200):
        _settle(pages, 5)
        clock.advance(5)
        la.poll(wa)
        lb.poll(wb)
        if wa.netplay is not None and wb.netplay is not None:
            break
    assert wa.netplay is not None and wb.netplay is not None, "the match formed"


def _tick(sides, pages, clock, rng, log):
    """One loop frame on every side, its held buttons random; each frame a
    side simulates goes into `log[i]` with the two masks it applied."""
    for i, (lk, ws) in enumerate(sides):
        ws.input.down = {b for b in ("left", "right", "a", "b") if rng.random() < 0.3}
        lk.poll(ws)
        np = ws.netplay
        if np is None:
            continue
        f = np.frame
        np.advance(P.mask_of(ws.input, P.CART_BUTTONS))
        if np.frame != f:
            r = ws.input.players
            log[i].append((np.frame, P.mask_of(r, P.CART_BUTTONS, 0),
                           P.mask_of(r, P.CART_BUTTONS, 1)))
    clock.advance(34)
    _settle(pages, 3)


def _play(sides, pages, clock, frames, rng, log, timeout=20.0):
    """Ticks until each side has simulated `frames` more."""
    start = [ws.netplay.frame for _lk, ws in sides]
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        _tick(sides, pages, clock, rng, log)
        if all(ws.netplay is not None and ws.netplay.frame - s >= frames
               for (lk, ws), s in zip(sides, start)):
            return
    raise AssertionError("the match stopped at %r" % [ws.netplay.frame for _l, ws in sides])


def _same(log):
    a, b = log
    n = min(len(a), len(b))
    assert n > 0 and a[:n] == b[:n], "the two sides applied different inputs"


@pytest.fixture
def two_pages(twin_exe, page_so, tmp_path, monkeypatch, air):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ha = _twin(twin_exe, tmp_path / "a", monkeypatch, air, MAC_A, sealed=True)
    hb = _twin(twin_exe, tmp_path / "b", monkeypatch, air, MAC_B, sealed=False)
    pa = Page(ha, _page_lib(page_so, "a", str(tmp_path)), True).open()
    pb = Page(hb, _page_lib(page_so, "b", str(tmp_path)), False).open()
    yield ha, hb, pa, pb, air
    ha.end()
    hb.end()


# -- the socket ----------------------------------------------------------------

def test_the_probe_says_the_board_relays_its_radio_and_its_address(two_pages):
    ha, hb, pa, pb, air = two_pages
    assert ha.probe() == {"live": 1, "link": 1, "mac": MAC_A.hex(), "term": 1, "hints": 1,
                          "req": 4096 - 8 - 16}
    assert "Sec-WebSocket-Protocol: moy.live" in pa.head


def test_the_socket_says_the_board_s_address_and_echoes(two_pages):
    ha, hb, pa, pb, air = two_pages
    _settle([pa])
    mac = ctypes.create_string_buffer(6)
    pa.lib.moy_link_mac(mac)
    assert mac.raw == MAC_A, "the page's address on the air is its board's"
    assert pa.lib.moy_link_channel(0) == -1, "pinned: a Zero never tunes"
    pa.send(b"zq-a channel this board does not serve")
    pa.send(b"ce" + b"12345678")
    for _ in range(100):
        pa.pump()
        if pa.echoes:
            break
        time.sleep(0.005)
    assert pa.echoes == [b"12345678"] and pa.closed is None


# -- a match --------------------------------------------------------------------

def test_two_pages_play_one_match_through_two_boards(two_pages):
    ha, hb, pa, pb, air = two_pages
    clock = E._Clock()
    la, lb = _page_link(pa, clock, "A"), _page_link(pb, clock, "B")
    sides = [(la, E._Ws()), (lb, E._Ws())]
    _meet(sides, [pa, pb], clock)
    log = ([], [])
    _play(sides, [pa, pb], clock, 120, random.Random(7), log)
    _same(log)
    for _lk, ws in sides:
        assert ws.netplay.desync < 0, "the checkpoints agree"
    assert "radio=1" in ha.wait_line("LIVE ") or "radio=1" in ha.log()


def test_a_page_plays_a_console(twin_exe, page_so, tmp_path, monkeypatch, air):
    ha = _twin(twin_exe, tmp_path, monkeypatch, air, MAC_A, sealed=True)
    try:
        pa = Page(ha, _page_lib(page_so, "a", str(tmp_path)), True).open()
        clock = E._Clock()
        la, lc = _page_link(pa, clock, "A"), _console(air, clock)
        sides = [(la, E._Ws()), (lc, E._Ws())]
        _meet(sides, [pa], clock)
        log = ([], [])
        _play(sides, [pa], clock, 120, random.Random(11), log)
        _same(log)
    finally:
        ha.end()


def test_a_lost_input_stalls_both_sides_and_nothing_is_guessed(two_pages):
    ha, hb, pa, pb, air = two_pages
    clock = E._Clock()
    la, lb = _page_link(pa, clock, "A"), _page_link(pb, clock, "B")
    sides = [(la, E._Ws()), (lb, E._Ws())]
    _meet(sides, [pa, pb], clock)
    log = ([], [])
    _play(sides, [pa, pb], clock, 30, random.Random(3), log)
    held = [ws.netplay.frame for _lk, ws in sides]
    air.cut.add(MAC_B)                # B's board is heard by nobody
    rng = random.Random(9)
    for _ in range(60):
        _tick(sides, [pa, pb], clock, rng, log)
    a_at, b_at = (ws.netplay.frame for _lk, ws in sides)
    assert a_at <= held[0] + P.REDUNDANCY + 4, "A waits for B's input"
    assert a_at <= b_at + 4 and b_at <= a_at + 4, "neither runs ahead"
    air.cut.clear()
    _play(sides, [pa, pb], clock, 30, random.Random(4), log)
    _same(log)
    for _lk, ws in sides:
        assert ws.netplay.desync < 0


def test_a_dropped_socket_reconnects_and_the_match_carries_on(two_pages):
    ha, hb, pa, pb, air = two_pages
    clock = E._Clock()
    la, lb = _page_link(pa, clock, "A"), _page_link(pb, clock, "B")
    sides = [(la, E._Ws()), (lb, E._Ws())]
    _meet(sides, [pa, pb], clock)
    log = ([], [])
    _play(sides, [pa, pb], clock, 30, random.Random(5), log)
    pa.drop()
    assert not PageRadio(pa.lib).send(BCAST, b"x"), "a closed socket refuses a send"
    for _ in range(100):
        if any("live=0 radio=0" in ln for ln in ha.log().splitlines() if ln.startswith("LIVE")):
            break
        time.sleep(0.02)
    assert any("live=0 radio=0" in ln for ln in ha.log().splitlines() if ln.startswith("LIVE")), \
        "the board's radio went down with the socket"
    rng = random.Random(10)
    for _ in range(20):
        _tick(sides, [pb], clock, rng, log)
    pa.open()                            # the worker's reopen: a new sealed upgrade
    _play(sides, [pa, pb], clock, 60, random.Random(6), log)
    _same(log)
    for _lk, ws in sides:
        assert ws.netplay.desync < 0
    assert "sessions=2" in [ln for ln in ha.log().splitlines() if ln.startswith("LIVE")][-1]



def test_a_link_held_before_the_socket_opens_brings_the_radio_up_when_it_does(
        twin_exe, page_so, tmp_path, monkeypatch, air):
    """The page's cart starts from its address at boot, before the worker's
    socket is open: the hold is kept and said when the socket opens."""
    ha = _twin(twin_exe, tmp_path, monkeypatch, air, MAC_A, sealed=True)
    try:
        lib = _page_lib(page_so, "early", str(tmp_path))
        assert lib.moy_link_start(0) == 0, "a hold with no socket yet is taken"
        assert not PageRadio(lib).send(BCAST, b"x"), "and a send before it opens refused"
        page = Page(ha, lib, True).open()
        for _ in range(200):
            page.pump()
            if any("radio=1" in ln for ln in ha.log().splitlines() if ln.startswith("LIVE")):
                break
            time.sleep(0.01)
        assert any("radio=1" in ln for ln in ha.log().splitlines() if ln.startswith("LIVE")), \
            "the board's radio came up when the socket opened"
    finally:
        ha.end()
