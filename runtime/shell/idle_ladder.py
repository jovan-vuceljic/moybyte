"""The idle ladder's console half (native/moy_kernel/moy_idle.h; the owner's
answers 1 and 7 in docs/history/kernel_survival_2026-10.md section 13): the
Settings rows that set its rungs, and the screensaver its SAVER rung shows.

The ladder itself is the kernel's (native/moy_kernel/moy_idle.c): it decides
when the screen dims, when the saver comes and when the light goes off, it
swallows the touch that wakes the screen, and it moves the kernel epoch so the
console repaints what the saver covered. What lives here is what only the
console can do:

  IdleLadder  the rows' values -- seconds of no input, OFF a value -- stepped
              from Settings, persisted in the system store and handed to the
              kernel (`moy_loop.idle`). A rung the board's light cannot show
              (DIM on a binary backlight) has no row. Settings' Brightness
              is the light the ladder's full rung means (`moy_loop.light_top`),
              applied at boot and on a change.
  Saver       what the screen shows on the SAVER rung: a cover cycle where
              the console is fullscreen (the S3s), the desk's wallpaper cart
              where there is a desk (the P4s). Never over a running cart:
              the game keeps the glass, and the ladder still dims and blanks.
"""

import ui_draw as _ui_draw
from chrome import _ticks_ms, _ticks_diff

DIM, SAVER, BLANK = 1, 2, 3

# The values a rung steps through, in seconds; 0 is OFF.
STEPS = (0, 30, 60, 120, 300, 600, 1800)

# (system key, rung, label, default). The blank rung's default is the board's
# (its POWER_SAVE_MS); the others ship OFF.
ROWS = (
    ("idle_dim", DIM, "DIM AFTER", 0),
    ("idle_saver", SAVER, "SAVER AFTER", 0),
    ("idle_blank", BLANK, "SCREEN OFF AFTER", 300),
)


def label(secs):
    """A rung's value as the row shows it: OFF, 30S, 5M."""
    if not secs:
        return "OFF"
    if secs % 60 == 0:
        return "%dM" % (secs // 60)
    return "%dS" % secs


class IdleLadder:
    """The rungs as Settings rows, over the kernel's ladder (`loop`, the
    module `moy_loop`)."""

    def __init__(self, ws, loop, blank_default=300):
        self.ws = ws
        self.loop = loop
        self.defaults = {"idle_blank": blank_default}
        self.can_dim = bool(loop.idle_can_dim())
        for key, rung, _label, default in ROWS:
            secs = self.defaults.get(key, default)
            try:
                v = ws.system.get(key, secs)
                secs = int(v) if v is not None else secs
            except (TypeError, ValueError):
                pass
            loop.idle(rung, secs)
        self.brightness()

    def brightness(self, level=None):
        """Settings' Brightness `level` (the stored one when None) on the
        panel, an even step of its light a level, the highest full and the
        lowest still lit: the kernel's light top now, or None where the
        board's light cannot dim."""
        v, lo, hi = self.ws.settings_layer.level("brightness")
        if level is not None:
            v = max(lo, min(hi, int(level)))
        return self.loop.light_top(255 * (v - lo + 1) // (hi - lo + 1))

    def rows(self):
        """The Settings rows this board's light can show."""
        return tuple((key, text, "idle") for key, rung, text, _d in ROWS
                     if rung != DIM or self.can_dim)

    def rungs(self):
        """Every rung's value as the kernel holds it, by ROWS' rung index:
        one read for all of them."""
        return self.loop.idle()

    def value(self, key):
        for k, rung, _t, _d in ROWS:
            if k == key:
                return self.loop.idle()[rung]
        return 0

    def label(self, key):
        return label(self.value(key))

    def steps(self):
        """The values a rung takes, in seconds (0 is OFF)."""
        return STEPS

    def step(self, key, d):
        """The next value up (d > 0) or down, persisted and live."""
        cur = self.value(key)
        i = 0
        while i < len(STEPS) and STEPS[i] < cur:
            i += 1
        i = max(0, min(len(STEPS) - 1, i + (1 if d > 0 else -1)))
        return self.set(key, STEPS[i])

    def sleep(self):
        """The BLANK rung now (the system menu's Sleep): the light goes off
        until the next input, which the ladder swallows as it wakes."""
        self.loop.power(False)

    def wake(self):
        """The ladder back to AWAKE now (an alarm, moybyte.at): the light
        comes on as an input would bring it. True when it was below AWAKE."""
        was = self.loop.idle_state()
        self.loop.power(True)
        return was != 0

    def set(self, key, secs):
        """Rung `key` at `secs`, persisted and live."""
        for k, rung, _t, _d in ROWS:
            if k == key:
                self.loop.idle(rung, secs)
                self.ws.system.set(key, secs)
        self.ws.mark_dirty()
        return secs


# The saver's inks, the same in every theme: MOY64's black ground, white ink,
# light grey dim and dark blue's frame.
_GROUND, _INK, _DIM, _FRAME = 0, 7, 6, 1
_ART_GAP = 8                    # the saver's room under the cover, over its title, in units


class Saver:
    """The SAVER rung's screen. `frame(dt)` paints the system canvas and
    answers True on a frame that drew (the console flushes it), False on one
    that shows what is already there."""

    PERIOD_MS = 6000

    def __init__(self, ws):
        self.ws = ws
        self.wallpaper = bool(getattr(ws.wm, "has_desk", False))
        self._i = -1
        self._next = None
        self._cart = None               # the cart whose cover shows
        self._th = None                 # the saver's inks over the theme's roles, made once

    def frame(self, dt):
        ws = self.ws
        if self.wallpaper:
            ws.wallpaper.draw(dt)       # the desk's wallpaper cart, the whole glass
            return True
        now = _ticks_ms()
        if self._next is not None and _ticks_diff(self._next, now) > 0:
            return False
        self._next = now + self.PERIOD_MS
        carts = [c for c in ws.carts.all if c.get("type") == "game"] or ws.carts.all
        cv = ws.sys_canvas or ws.run.canvas
        cv.cls(0)
        if carts:
            self._i = (self._i + 1) % len(carts)
            self._cover(cv, carts[self._i])
        return True

    def _cover(self, cv, cart):
        """The saver in every theme (docs/history/look_2026-10.md step 33): on
        black, the cart's cover at its largest whole scale, its title in the
        title face under it, the clock small in the corner: `overlay_ui.saver`
        in the saver's inks. A cart with no cover is its title alone."""
        import console_notices as _cn
        import overlay_ui
        ws = self.ws
        n = ws.notices
        img = ws.covers.cover_for(cart)
        fs = getattr(cv, "font_scale", 1) or 1
        self._cart = cart
        side = 0
        block = _ui_draw.font("title")[2] * fs + 12 * fs  # the title's row
        if img is not None:
            room = cv.h - 30 * fs - block - _ART_GAP * fs
            s = max(1, min((cv.w - 32 * fs) // img.w, room // img.h))
            side = img.w * s // fs
            block += img.h * s + _ART_GAP * fs
        n.put_overlay(_cn.SAVER, "title", str(cart.get("title") or "?"))
        n.put_overlay(_cn.SAVER, "time", ws.bar_layer.clock_text())
        n.put_overlay(_cn.SAVER, "covered", img is not None)
        n.put_overlay(_cn.SAVER, "side", side + _ART_GAP if side else 0)
        th = self._th
        if th is None:
            th = self._th = dict(ws.theme_colors)
            for role in ("ground", "surface", "panel", "chrome"):
                th[role] = _GROUND
            for role in ("ink", "value", "chrome_ink"):
                th[role] = _INK
            for role in ("ink_dim", "chrome_ink_dim"):
                th[role] = _DIM
            th["line"] = _FRAME
        overlay_ui.COVER[0] = self._art
        # (the clock 10 units in from the corner; the page's foot where the
        # cover and its title stand centred on the glass)
        m = 10 * fs
        n.paint_overlay(_cn.SAVER, cv, n.room(_cn.SAVER, m, m // 2, cv.w - 2 * m,
                                              min(cv.h, (cv.h + block) // 2) - m // 2), th)

    def _art(self, cv, x, y, w, h):
        """The cover's canvas, the page's width: the cart's cover centred
        across it at its whole scale in a 1 px frame, `_ART_GAP` under it."""
        img = self.ws.covers.cover_for(self._cart) if self._cart is not None else None
        if img is None:
            return
        fs = getattr(cv, "font_scale", 1) or 1
        s = max(1, (h - _ART_GAP * fs) // img.h)
        sw, sh = img.w * s, img.h * s
        x += (w - sw) // 2
        cv.blit565(img.pix, img.w, img.h, x, y, s)
        cv.rectb(x - fs, y - fs, sw + 2 * fs, sh + 2 * fs, _FRAME)
