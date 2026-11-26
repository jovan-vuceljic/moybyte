"""The live socket's device channel (#256; native/moy_net/moy_live.c's
header is the wire): a page's handle of a kind its board relays is a remote
row of the page's handle table, served by the board's.

The board twin is tests/test_live_link.py's (the web terminal's host
harness with the live socket) built with the kernel's handle table, its
event queues and a fake `lora` kind (tests/live_dev/fake_lora.c: a radio
that hears what it sends). The page is the browser's C: its link's queue
(moy_link_web.c), the remote rows (moy_dev_web.c) and the kernel's table
over them, loaded as a library, its socket a WebSocket client here, the
worker's job done by hand (test_live_link.Page).

What it holds: the probe names the kinds; a page's open, write, set, read,
get and the board's events crossing in order; a refusal answered to the
next call; one write in flight; the session's end closing the board's
handle so another page can take the radio; a dropped socket opening the
row again; the round trip of a call.
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import test_live_link as L  # noqa: E402
import test_moy_tty as T  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("cc") is None, reason="needs a C compiler")

KERNEL = os.path.join(T.NATIVE, "moy_kernel")
INPUT = os.path.join(T.NATIVE, "moy_input")
# The handle table and what it links on the host (the event queues, the
# leases and their buses' host twins).
TABLE = [os.path.join(KERNEL, n) for n in (
    "moy_dev.c", "moy_dev_kinds.c", "moy_lease.c", "moy_devbus.c", "moy_ledc.c", "moy_lock.c",
    "moy_evq.c", "moy_super.c", "moy_screen_slot.c", "moy_vmq.c")] + [
    os.path.join(T.SPINE, "moy_htab.c"), os.path.join(INPUT, "moy_input.c"),
    os.path.join(INPUT, "moy_hid.c")]
FAKE = os.path.join(os.path.dirname(__file__), "live_dev", "fake_lora.c")
SPEC = "lora:rssi,snr,port:joined,fcnt,busy"
P_LORA = 1 << 3
PID = 7
BUSY, BAD, ABSENT = -11, -7, -8


@pytest.fixture(scope="module")
def twin_exe(tmp_path_factory):
    out = tmp_path_factory.mktemp("live_dev")
    return T._build(out, extra=[os.path.join(T.NET, "moy_live.c"),
                                os.path.join(T.NET, "moy_live_dev.c"),
                                os.path.join(T.NET, "moy_link_host.c"), FAKE] + TABLE,
                    defines=("MOY_NET_LIVE=1", "MOY_NET_LINK=1", "MOY_TTY_LEASES=1",
                             "MOY_DEV_RELAYS=1"),
                    incs=(KERNEL, INPUT))


@pytest.fixture(scope="module")
def page_so(tmp_path_factory):
    out = tmp_path_factory.mktemp("page_dev")
    so = str(out / "page_dev.so")
    subprocess.run([shutil.which("cc"), "-shared", "-fPIC", "-O1", "-std=gnu99", "-w",
                    "-D_GNU_SOURCE", "-DMOY_NET_LINK=1", "-DMOY_NET_LIVE_PAGE=1"]
                   + ["-I" + d for d in (T.NET, KERNEL, INPUT, T.SPINE, T.STORE)]
                   + [os.path.join(T.NET, "moy_link_web.c"), os.path.join(T.NET, "moy_dev_web.c"),
                      os.path.join(KERNEL, "moy_log.c")] + TABLE + ["-o", so, "-lpthread"],
                   check=True)
    return so


class _Ev(ctypes.Structure):
    _fields_ = [("frm", ctypes.c_uint32), ("n", ctypes.c_uint32),
                ("app", ctypes.c_char * 48), ("name", ctypes.c_char * 24)]


def _page_lib(so, name, tmp):
    path = os.path.join(tmp, name + ".so")
    shutil.copy(so, path)
    d = ctypes.CDLL(path)
    U, I, Z, B = ctypes.c_uint32, ctypes.c_int32, ctypes.c_size_t, ctypes.c_char_p
    for fn, args, res in (
            ("moy_link_web_take", [B, Z], Z), ("moy_link_web_give", [B, Z], None),
            ("moy_link_web_open", [ctypes.c_int], None), ("moy_dev_web_kinds", [B, Z], None),
            ("moy_dev_open", [U, U, B, Z, B, Z], I), ("moy_dev_close", [U, I], I),
            ("moy_dev_read", [U, I, B, Z], I), ("moy_dev_write", [U, I, B, Z], I),
            ("moy_dev_set", [U, I, B, Z], I), ("moy_dev_get", [U, I, B, Z], I),
            ("moy_dev_xfer", [U, I, B, Z, B, Z], I),
            ("moy_evq_open", [U, B, B, U], ctypes.c_int),
            ("moy_evq_listen", [U, B, ctypes.c_bool], ctypes.c_int),
            ("moy_evq_step", [U], U),
            ("moy_evq_take", [U, ctypes.POINTER(_Ev), B, Z], ctypes.c_int)):
        f = getattr(d, fn)
        f.argtypes = args
        f.restype = res
    return d


class Cart:
    """A program on the page holding a handle, as a Lua service does through
    moybyte.dev_*: its process's queue listens on "lora"."""

    def __init__(self, page, pid=PID):
        self.page, self.lib, self.pid = page, page.lib, pid
        self.buf = ctypes.create_string_buffer(512)
        assert self.lib.moy_evq_open(pid, b"mesh", None, 0) == 0
        assert self.lib.moy_evq_listen(pid, b"lora", True) == 0

    def open(self, cfg=b"freq=868100000 sf=9"):
        return self.lib.moy_dev_open(self.pid, P_LORA, b"lora", 4, cfg, len(cfg))

    def write(self, h, data):
        return self.lib.moy_dev_write(self.pid, h, data, len(data))

    def set(self, h, cfg):
        return self.lib.moy_dev_set(self.pid, h, cfg, len(cfg))

    def get(self, h, what):
        return self.lib.moy_dev_get(self.pid, h, what, len(what))

    def read(self, h):
        n = self.lib.moy_dev_read(self.pid, h, self.buf, len(self.buf))
        return n if n < 0 else self.buf.raw[:n]

    def events(self):
        out = []
        ev, args = _Ev(), ctypes.create_string_buffer(128)
        self.lib.moy_evq_step(self.pid)
        while self.lib.moy_evq_take(self.pid, ctypes.byref(ev), args, 128) == 0:
            out.append((ev.name.decode(), json.loads(args.value.decode())))
        return out


def _until(pages, cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for p in pages:
            p.pump()
        got = cond()
        if got:
            return got
        time.sleep(0.002)
    raise AssertionError("timed out")


def _live(board):
    """The board's last LIVE line (tty_main's: moy_live_stats), as a dict."""
    lines = [ln for ln in board.log().splitlines() if ln.startswith("LIVE ")]
    return dict(kv.split("=") for kv in lines[-1].split()[1:]) if lines else {}


def _ended(page):
    """Whether the board closed `page`'s socket, its bytes read and dropped."""
    try:
        while True:
            k = page.c.recv(65536)
            if not k:
                return True
    except BlockingIOError:
        return False
    except OSError:
        return True


@pytest.fixture
def board(twin_exe, tmp_path, monkeypatch, air):
    h = L._twin(twin_exe, tmp_path, monkeypatch, air, L.MAC_A, sealed=True)
    yield h
    h.end()


@pytest.fixture
def air():
    a = L.Air()
    yield a
    a.close()


def _page(board, page_so, tmp_path, name="p"):
    lib = _page_lib(page_so, name, str(tmp_path))
    lib.moy_dev_web_kinds(SPEC.encode(), len(SPEC))
    return L.Page(board, lib, True)


def test_the_probe_names_the_kinds_the_board_relays(board):
    status, d = board.page.json("GET", "/live")
    assert status == 200 and d["kinds"] == SPEC and d["link"] == 1


def test_a_page_sends_and_hears_its_board_s_radio(board, page_so, tmp_path):
    page = _page(board, page_so, tmp_path).open()
    cart = Cart(page)
    h = cart.open()
    assert h > 0
    assert cart.write(h, b"hello mesh") == 10
    # one write in flight a handle, as the device's own BUSY
    assert cart.write(h, b"again") == BUSY
    got = _until([page], lambda: [e for e in cart.events() if e[1][0] == 1] or None)
    assert got == [("lora", [1, 1])]
    assert cart.read(h) == b"hello mesh"
    assert (cart.get(h, b"rssi"), cart.get(h, b"snr"), cart.get(h, b"port")) == (-57, 26, 0)
    # the state gets the board read after the event: the transmission done
    assert cart.get(h, b"busy") == 0 and cart.get(h, b"fcnt") == 1
    assert cart.get(h, b"freq") == BAD
    assert cart.read(h) == b""
    assert cart.write(h, b"again") == 5
    _until([page], lambda: cart.read(h) == b"again")
    _until([], lambda: _live(board).get("dev_writes") == "2")
    assert _live(board)["devs"] == "1"


def test_a_refusal_is_answered_to_the_next_call(board, page_so, tmp_path):
    page = _page(board, page_so, tmp_path).open()
    cart = Cart(page)
    h = cart.open()
    assert cart.set(h, b"fail=1") == 0
    _until([page], lambda: page.lib.moy_dev_set(PID, h, b"sf=7", 4) == BAD)
    assert cart.set(h, b"sf=7") == 0
    xo = ctypes.create_string_buffer(8)
    assert page.lib.moy_dev_xfer(PID, h, b"x", 1, xo, 8) == BAD


def test_a_kind_the_board_lacks_stays_absent(board, page_so, tmp_path):
    lib = _page_lib(page_so, "none", str(tmp_path))
    page = L.Page(board, lib, True).open()
    cart = Cart(page)
    assert cart.open() == ABSENT


def test_the_session_s_end_lets_the_radio_go(board, page_so, tmp_path):
    a = _page(board, page_so, tmp_path, "a").open()
    ca = Cart(a)
    h = ca.open()
    assert ca.write(h, b"x") == 1
    _until([a], lambda: ca.read(h) == b"x")
    # a second page takes the socket over (moy_wa_take: the newer page has
    # it): the first's session ends, and with it its process's radio
    b = _page(board, page_so, tmp_path, "b")
    b.host.page = b.host.browser()
    b.open()
    # (the seal client keeps one slot's keys, b's now: a's bytes are read raw)
    _until([], lambda: _ended(a))
    # the upgrade that took the socket found a's bridge still serving, and
    # was closed busy, as a page's first try is: the page tries again
    b.drop()
    b.open()
    cb = Cart(b)
    hb = cb.open()
    assert cb.write(hb, b"mine") == 4
    _until([b], lambda: cb.read(hb) == b"mine")


def test_a_dropped_socket_opens_the_row_again(board, page_so, tmp_path):
    page = _page(board, page_so, tmp_path).open()
    cart = Cart(page)
    h = cart.open()
    assert cart.set(h, b"sf=10") == 0
    assert cart.write(h, b"one") == 3
    _until([page], lambda: cart.read(h) == b"one")
    page.drop()
    assert cart.write(h, b"lost") == BUSY        # no socket: the board is not there
    # the board's session ends with it, and its handle with the session
    _until([], lambda: _live(board).get("live") == "0" and _live(board).get("devs") == "0")
    page.open()
    assert cart.write(h, b"two") == 3
    _until([page], lambda: cart.read(h) == b"two")


def test_a_call_s_round_trip(board, page_so, tmp_path):
    """A call's answer back at the page: a set the board refuses, timed to
    the first later set that answers the refusal. Printed (the on-glass
    number is the PR's report) and bounded loosely."""
    page = _page(board, page_so, tmp_path).open()
    cart = Cart(page)
    h = cart.open()
    times = []
    for _ in range(20):
        t = time.monotonic()
        assert cart.set(h, b"fail=1") == 0
        _until([page], lambda: cart.set(h, b"sf=7") == BAD)
        times.append((time.monotonic() - t) * 1000)
    times.sort()
    print("round trip ms: min %.1f median %.1f max %.1f" % (times[0], times[10], times[-1]))
    assert times[10] < 200


# -- the page's console ---------------------------------------------------------

def test_a_relayed_kind_is_the_consoles_for_handles_and_not_for_faces(monkeypatch):
    """The console a page is has the device its board relays (an install
    check and the shelves find it), for the programs that hold handles: a
    Lua, wasm or ELF one. A Python program holds a face, which the page has
    not, so it lacks the device there."""
    from runtime import app_perms
    import devices
    monkeypatch.setattr(devices, "RELAYED", ())
    lua = {"runtime": "lua", "permissions": ["lora"], "required": ["lora"]}
    py = {"runtime": "python", "permissions": ["lora"], "required": ["lora"]}
    have = ()
    assert app_perms.lacking(lua, have) == "lora"
    monkeypatch.setattr(devices, "RELAYED", ("lora",))
    have = devices.apis()
    assert "lora" in have
    assert app_perms.lacking(lua, have) is None
    assert app_perms.lacking(py, have) == "lora"


def test_a_board_builds_the_channel_for_exactly_the_kinds_with_a_relay_list():
    """moy_dev_kinds.h's MOY_DEV_RELAYS names the MOY_API_ define of each kind
    whose KINDS row has a relay list, and only those: a board whose class
    rows name none of them (the C3 Zero) links none of the kinds (its pins are
    the channel's other half, MOY_DEV_PINS)."""
    import re
    kinds = open(os.path.join(KERNEL, "moy_dev_kinds.c")).read()
    listed = set(re.findall(r'\{\s*"(\w+)",[^{}]*,\s*"[^"]*"\s*\}', kinds))
    head = open(os.path.join(KERNEL, "moy_dev_kinds.h")).read()
    block = head[head.index("#ifndef MOY_DEV_RELAYS"):head.index("#define MOY_DEV_RELAYS")]
    named = {m.lower() for m in re.findall(r"defined\(MOY_API_(\w+)\)", block)}
    assert listed and listed == named, (listed, named)
