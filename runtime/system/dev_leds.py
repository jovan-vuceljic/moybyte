"""`moybyte.leds`: the `leds` device API's face (docs/moy_cart_api.md, the
Moybyte-side device APIs) over its driver (native/moy_leds/moy_leds.h, the
module moy_leds): a board's RGB LEDs -- the CoreS3's Faces Bottom3 bar. Needs
the `leds` permission; one process holds them at a time. A colour is
0xRRGGBB.

  count() -> n          the LEDs this console has (0: none, and no face)
  set(i, rgb)           LED i's colour, shown at once
  fill(rgb)             every LED's
  brightness(level)     0..255 over every colour, 255 at the first take
  show(rgb_list)        a frame: a colour an LED from the first, the rest dark
  open() / close()      take them now (OSError EBUSY while another process
                        holds them) / let them go, dark; every verb above
                        takes them first
  holder()              the pid holding them, 0 for none

The holder's end (exit, crash, kill, a run's end) lets them go, dark, through
`moybyte.ENDS`. The host has LEDs only under its stand-in (`moy_leds.sim`)."""

try:
    import moy_leds as _N
except ImportError:  # host, or an image without the driver
    _N = None
if _N is None:
    try:
        from runtime import moy_leds as _N
    except ImportError:
        _N = None

import devices as _D


def _p():
    return _D.need("leds")


def count():
    return _N.count() if _N is not None else 0


def open():  # noqa: A001 -- the verb's name
    _D.check(_N.open(_p()))
    return count()


def close():
    _N.close(_D.pid())


def set(i, rgb):  # noqa: A001 -- the verb's name
    _D.check(_N.set(_p(), int(i), int(rgb) & 0xFFFFFF))


def fill(rgb):
    _D.check(_N.fill(_p(), int(rgb) & 0xFFFFFF))


def brightness(level):
    _D.check(_N.bright(_p(), int(level)))


def show(colours):
    buf = bytearray(3 * len(colours))
    for k, c in enumerate(colours):
        buf[3 * k] = (c >> 16) & 0xFF
        buf[3 * k + 1] = (c >> 8) & 0xFF
        buf[3 * k + 2] = c & 0xFF
    _D.check(_N.write(_p(), buf))


def holder():
    return _N.owner() if _N is not None else 0


def present():
    return count() > 0


def sweep(pid):
    return _N.sweep(pid) if _N is not None else 0
