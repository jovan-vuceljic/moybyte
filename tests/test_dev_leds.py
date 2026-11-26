"""The `leds` device API (runtime/system/dev_leds.py over
native/moy_leds/moy_leds.h): a board's RGB LEDs, one holder at a time, the
frame the board is handed (GRB, scaled by the brightness), the permission,
the bar going dark when its holder lets go or ends, the row's absence on a
console without LEDs, and the same API by handle (moy_dev's `leds` kind)."""

import errno

import pytest

from runtime import app_perms as P
from runtime import devices, moybyte
from runtime import moy_leds as N
from runtime import moy_log as L

BAR = 10


@pytest.fixture(autouse=True)
def bar():
    devices.grants = devices.console = None     # a console an earlier test built
    N.reset()
    N.sim(BAR)
    yield
    if N.owner():
        moybyte.end(N.owner())
    devices.grants = None
    N.sim(0)
    N.reset()


def _as(pid, fn):
    was = L.current()
    L.current(pid)
    try:
        return fn()
    finally:
        L.current(was)


def _errno(fn):
    with pytest.raises(OSError) as e:
        fn()
    return e.value.errno


def _shown():
    buf = bytearray(3 * BAR)
    n = N.shown(buf)
    return [tuple(buf[i:i + 3]) for i in range(0, n, 3)]


def test_the_holder_lights_the_bar_and_the_board_gets_grb():
    pid = L.spawn("t.leds")
    assert moybyte.leds.count() == BAR
    _as(pid, lambda: moybyte.leds.fill(0x102030))
    assert N.owner() == pid and moybyte.leds.holder() == pid
    assert _shown() == [(0x20, 0x10, 0x30)] * BAR
    _as(pid, lambda: moybyte.leds.set(2, 0xFF0000))
    assert _shown()[2] == (0, 0xFF, 0)
    _as(pid, lambda: moybyte.leds.brightness(0))
    assert _shown() == [(0, 0, 0)] * BAR
    _as(pid, lambda: moybyte.leds.brightness(255))
    _as(pid, lambda: moybyte.leds.show([0x0000FF, 0x00FF00]))
    assert _shown()[:3] == [(0, 0, 0xFF), (0xFF, 0, 0), (0, 0, 0)]
    assert _errno(lambda: _as(pid, lambda: moybyte.leds.set(BAR, 1))) == errno.EINVAL


def test_one_process_holds_them_and_its_end_turns_them_dark():
    a, b = L.spawn("t.a"), L.spawn("t.b")
    _as(a, lambda: moybyte.leds.fill(0xFFFFFF))
    assert _errno(lambda: _as(b, lambda: moybyte.leds.fill(0xFF0000))) == errno.EBUSY
    assert _errno(lambda: _as(b, moybyte.leds.open)) == errno.EBUSY
    moybyte.end(a)                              # exit, crash or kill
    assert N.owner() == 0
    assert _shown() == [(0, 0, 0)] * BAR
    _as(b, lambda: moybyte.leds.fill(0xFF0000))
    assert N.owner() == b


def test_a_close_lets_them_go_dark():
    pid = L.spawn("t.leds")
    _as(pid, lambda: moybyte.leds.fill(0x00FF00))
    _as(pid, moybyte.leds.close)
    assert N.owner() == 0 and _shown() == [(0, 0, 0)] * BAR


def test_the_leds_need_the_permission():
    pid = L.spawn("t.leds")
    devices.grants = lambda p: ("pins",) if p == pid else None
    assert _errno(lambda: _as(pid, moybyte.leds.open)) == errno.EPERM
    devices.grants = lambda p: ("leds",) if p == pid else None
    assert _as(pid, moybyte.leds.open) == BAR


def test_the_row_and_its_absence_without_leds():
    assert P.line("leds") == "Light the console's LEDs"
    cart = {"id": "t.l", "runtime": "python", "permissions": ["leds"], "required": ["leds"]}

    class Ws:
        wifi = net = gpio = None
    assert "leds" in P.services(Ws())
    assert P.check(cart, None, P.services(Ws()))[0] == ["leds"]
    N.sim(0)
    assert moybyte.leds is None
    assert "leds" not in P.services(Ws())
    assert P.check(cart, None, P.services(Ws()))[2] is not None
    assert N.open(5) == -errno.ENODEV
