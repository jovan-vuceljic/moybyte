"""The live socket's pins (#256; native/moy_net/moy_live.c's THE PINS): a
board that serves its pins to its page (/gpio) relays them on its device
channel too, so a cart's pin write leaves when the frame that made it ends
and a watched pin's change is pushed, not polled.

The board twin is tests/test_live_link.py's, built with the device channel
and the /gpio route's stand-in pins (moy_net_host.c; tty_main's
MOY_TTY_PINS, `pin` and `level`) and no kind of the handle table, as the C3
Zero builds it. The page is its socket and the pin verbs' queue
(firmware/web_runner/gpio_link.py), the worker's job done by hand.
"""
import os
import shutil
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import test_live_link as L  # noqa: E402
import test_moy_tty as T  # noqa: E402

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "firmware", "web_runner"))
from gpio_link import GpioLink, PINS_ROW  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("cc") is None, reason="needs a C compiler")

PINS = (1, 2, 21)
KERNEL = os.path.join(T.NATIVE, "moy_kernel")
ROW = bytes([PINS_ROW])
BAD = -7


@pytest.fixture(scope="module")
def twin_exe(tmp_path_factory):
    out = tmp_path_factory.mktemp("live_pins")
    return T._build(out, extra=[os.path.join(T.NET, "moy_live.c"),
                                os.path.join(T.NET, "moy_live_dev.c"),
                                os.path.join(T.NET, "moy_link_host.c")],
                    defines=("MOY_NET_LIVE=1", "MOY_NET_LINK=1", "MOY_NET_GPIO_ROUTE=1"),
                    incs=(KERNEL,))


class _Lib:
    """The page's link library where only the device channel matters: what
    the board sends on it is kept, and the link queues nothing."""

    def __init__(self):
        self.got = []

    def moy_link_web_give(self, pl, n):
        self.got.append(bytes(pl[:n]))

    def moy_link_web_take(self, out, cap):
        return 0

    def moy_link_web_open(self, on):
        pass


@pytest.fixture
def board(twin_exe, tmp_path, monkeypatch):
    air = L.Air()
    monkeypatch.setenv("MOY_TTY_PINS", ",".join(str(p) for p in PINS))
    h = L._twin(twin_exe, tmp_path, monkeypatch, air, L.MAC_A, sealed=True)
    yield h
    h.end()
    air.close()


def _page(board):
    return L.Page(board, _Lib(), True).open()


def _pins(page, timeout=3.0, want=None):
    """The pins row's messages the board sent, waiting for one where `want`."""
    end = time.monotonic() + timeout
    while True:
        page.pump()
        got = [m for m in page.lib.got if m[:1] == b"d" and m[2:3] == ROW]
        if not want or any(want(m) for m in got) or time.monotonic() > end:
            return got
        time.sleep(0.01)


def _level(board, n):
    board.say("level %d" % n)
    line = board.wait_line("LEVEL %d " % n, after=len(board.log()))
    _tag, _n, lv, mode = line.split()
    return int(lv), int(mode)


def _g(m):
    return [int.from_bytes(m[i:i + 4], "little", signed=True) for i in range(3, len(m), 4)]


def test_the_probe_names_the_pins(board):
    d = board.probe()
    assert d.get("kinds") == "pins", d


def test_a_write_drives_the_pin_as_it_arrives(board):
    p = _page(board)
    p.send(b"dO" + ROW + b"\x04pins")
    assert _pins(p, want=lambda m: m[1:2] == b"A")[0] == b"dA" + ROW + b"O" + bytes(4)
    p.send(b"dW" + ROW + bytes([2, 1, 21, 1]))
    end = time.monotonic() + 3
    while _level(board, 2) != (1, 2) and time.monotonic() < end:
        time.sleep(0.02)
    assert _level(board, 2) == (1, 2) and _level(board, 21) == (1, 2)
    p.send(b"dW" + ROW + bytes([2, 0]))
    end = time.monotonic() + 3
    while _level(board, 2) != (0, 2) and time.monotonic() < end:
        time.sleep(0.02)
    assert _level(board, 2) == (0, 2)


def test_a_watched_pin_is_pushed_when_it_changes(board):
    p = _page(board)
    p.send(b"dO" + ROW + b"\x04pins")
    p.send(b"dS" + ROW + bytes([1, 2]))
    first = _pins(p, want=lambda m: m[1:2] == b"G")
    assert _g([m for m in first if m[1:2] == b"G"][0]) == [1, 1], "inputs read their pull-up"
    p.lib.got.clear()
    p.send(b"dW" + ROW + bytes([2, 0]))
    got = _pins(p, want=lambda m: m[1:2] == b"G")
    assert [_g(m) for m in got if m[1:2] == b"G"] == [[1, 0]], "the write's own change"
    p.lib.got.clear()
    board.say("pin 1 0")
    got = _pins(p, want=lambda m: m[1:2] == b"G")
    assert [_g(m) for m in got if m[1:2] == b"G"] == [[0, 0]], "a change from outside"
    p.lib.got.clear()
    time.sleep(0.3)
    assert [m for m in _pins(p, timeout=0) if m[1:2] == b"G"] == [], "no change, no push"


def test_a_pin_off_the_allowlist_is_refused_and_named(board):
    p = _page(board)
    p.send(b"dO" + ROW + b"\x04pins")
    p.send(b"dW" + ROW + bytes([3, 1, 2, 1]))
    got = _pins(p, want=lambda m: m[1:2] == b"A" and m[3:4] == b"W")
    refused = [m for m in got if m[1:2] == b"A" and m[3:4] == b"W"]
    assert refused == [b"dA" + ROW + b"W" + BAD.to_bytes(4, "little", signed=True) + b"\x03"]
    end = time.monotonic() + 3
    while _level(board, 2) != (1, 2) and time.monotonic() < end:
        time.sleep(0.02)
    assert _level(board, 2) == (1, 2), "its neighbour still driven"


def test_the_socket_s_end_leaves_the_pins_to_the_batches(board):
    """The socket's pins are /gpio's (moy_gpio_op): a page whose socket
    drops reads in a batch on its next socket what it drove on the last."""
    p = _page(board)
    p.send(b"dO" + ROW + b"\x04pins")
    p.send(b"dW" + ROW + bytes([21, 1]))
    end = time.monotonic() + 3
    while _level(board, 21) != (1, 2) and time.monotonic() < end:
        time.sleep(0.02)
    p.drop()
    _page(board)
    status, d = board.page.json("POST", "/gpio", {"v": 1, "ops": [{"p": 21, "mode": "read"}]})
    assert status == 200 and d["reads"] == {"21": 1}, d


def test_the_pin_verbs_ride_the_socket_and_fall_back_to_the_batches(board):
    """gpio_link.py end to end: a write leaves as the frame's 'W', a read
    subscribes the pin ('S') and answers the board's push; a refusal is said
    once; a closed socket hands the writes back to the batches."""
    p = _page(board)
    said = []
    g = GpioLink(PINS, log=said.append)

    def frame():
        for pl in g.take_live():
            p.send(pl)
        p.pump()
        for m in p.lib.got:
            g.live_in(m)
        p.lib.got.clear()

    g.live_open(True)
    assert g.read(2) is None
    assert g.write(21, 1)
    frame()
    assert g.take_json() == "", "no batch while the socket carries the pins"
    end = time.monotonic() + 3
    while g.read(2) is None and time.monotonic() < end:
        frame()
        time.sleep(0.01)
    assert g.read(2) == 1
    g.write(2, 0)
    end = time.monotonic() + 3
    while g.read(2) != 0 and time.monotonic() < end:
        frame()
        time.sleep(0.01)
    assert g.read(2) == 0, "the write's level comes back pushed"
    assert len(g.rt) == 1 and g.rt[0] >= 0, "...timed from the write (the meter)"
    assert _level(board, 21) == (1, 2)
    g.live_in(b"dA" + ROW + b"W" + BAD.to_bytes(4, "little", signed=True) + b"\x03")
    g.live_in(b"dA" + ROW + b"W" + BAD.to_bytes(4, "little", signed=True) + b"\x03")
    assert said == ["gpio: pin 3: not on this board's allowlist"]
    g.live_open(False)
    g.write(1, 1)
    assert '"p": 1' in g.take_json(), "the batches take over"


def test_a_reopened_socket_says_again_what_the_page_drove_and_watches():
    g = GpioLink(PINS, log=lambda s: None)
    g.live_open(True)
    g.write(2, 1)
    g.read(21)
    assert g.take_live() == [b"dO" + ROW + b"\x04pins", b"dW" + ROW + bytes([2, 1]),
                             b"dS" + ROW + bytes([21])]
    assert g.take_live() == []
    g.live_open(False)
    g.live_open(True)
    assert g.take_live() == [b"dO" + ROW + b"\x04pins", b"dW" + ROW + bytes([2, 1]),
                             b"dS" + ROW + bytes([21])]


def test_a_board_without_the_pins_on_its_socket_keeps_the_batches():
    said = []
    g = GpioLink(PINS, log=said.append)
    g.live_open(True)
    g.take_live()
    g.live_in(b"dA" + ROW + b"O" + (-8).to_bytes(4, "little", signed=True))
    assert not g.live and said
    g.write(2, 1)
    assert '"p": 2' in g.take_json()
