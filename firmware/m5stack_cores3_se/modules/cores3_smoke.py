"""CoreS3 SE bring-up smokes -- self-terminating, one question each, driven from
moybyte_shell.MODE or by hand:

    import cores3_smoke; cores3_smoke.pad()

`panel()`: do the rails, the ILI9342C and the banded flush come up (colour bars
over a checker, drawn in C). `touch()`: does the FT6336U report where the
finger is. `pad()`: does the Faces Gamepad3 answer and which buttons it holds.
"""

import time

import moy_cores3
import moy_glass
import moy_lcd


def panel(frames=6):
    """The panel up and a test pattern painted in C (`moy_lcd.bars`), the light
    on after the first frames are out. Expect 8 colour bars over a checker,
    the right way up; `moy_lcd.set_madctl(0x08 | 0x40)` and kin turn it over
    the REPL without a rebuild (MX 0x40, MY 0x80, MV 0x20, BGR 0x08)."""
    print("Moybyte panel: init")
    comp = moy_glass.BandedCompositor(moy_lcd, nfbs=2)
    w, h = comp.size()
    print("Moybyte panel: %dx%d madctl=0x%02x" % (w, h, moy_lcd.madctl()))
    for i in range(moy_lcd.nfbs()):
        moy_lcd.bars(i)
    for _ in range(moy_lcd.nfbs()):
        comp.flush()
    comp.sync()
    comp.set_backlight(True)
    print("Moybyte panel: light code=%d" % moy_cores3.light())
    for _ in range(frames):
        comp.flush()
        time.sleep_ms(120)
    comp.sync()
    n, us = comp.stats()
    print("Moybyte panel: flushes=%d last=%dus" % (n, us))
    print("Moybyte panel smoke done -> REPL")


def touch(secs=20):
    """The FT6336U's points for `secs`, mapped onto 320x240."""
    import moy_input
    t = moy_input.touch(320, 240)
    print("Moybyte touch: available=%s" % (t is not None and t.available))
    end = time.ticks_add(time.ticks_ms(), secs * 1000)
    last = None
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        moy_input.kick()
        p = t.poll()
        if p != last:
            print("touch", p)
            last = p
        time.sleep_ms(20)
    print("Moybyte touch smoke done -> REPL")


def pad(secs=20):
    """The Gamepad3's byte (active low: bit 0 up .. 7 Start) for `secs`."""
    import moy_input
    g = moy_input.gamepad()
    print("Moybyte pad: available=%s gate=%s"
          % (g is not None and g.available, g is not None and g.gate))
    end = time.ticks_add(time.ticks_ms(), secs * 1000)
    last = None
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        moy_input.kick()
        time.sleep_ms(20)
        if g is not None and g.raw != last:
            last = g.raw
            print("pad raw=0x%02x" % last)
    print("Moybyte pad smoke done -> REPL")
