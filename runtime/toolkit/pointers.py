"""The pointer's families (native/moy_ui/icons/pointer/pointer_art.py), drawn
the same way on every tier.

A family is one font file a size (`ptr-<family>-<size>.fnt`,
tools/make_icons.py): shape s's layers -- the outline, the fill, the
accent -- are the glyphs at byte FIRST + 3 s and the two after it, each with
its pen at the shape's hotspot, drawn by `moy_ui.icon_mask` in its family's
colour. A smooth family's soft shadow is its outline glyph again, drawn
translucent in its ink a pixel per 16 px down and right (none at 16 px or
on a text beam).

The family a theme wears is its look's `pointer` where it names one, else
its icon set's (`iconsets.spec`: a pixel set's the pixel family, a smooth
set's its own, the shell's own sheet the pixel family); Appearance's
Pointer row picks another (`Appearance.pointer_family`). Normal draws 16 px
a step of the chrome scale, Large the next size up (`size`).

  theme_family(look) -> family          the theme's own
  size(family, scale, large) -> px      the size a scale draws
  draw(cv, family, shape, x, y, px)     the shape's hotspot at (x, y)
  box(family, shape, x, y, px)          what it covers there, (x, y, w, h)
  image(cv, family, shape, px)          its pixels as RGBA, for a page's CSS cursor
  Under                                 what lies under the pointer, put back

A pointer's edges and shadow blend into what is under them, so a pointer
drawn again over its own last stamp would darken it frame by frame. The
console keeps what was under it (`Under`) and puts that back wherever the
buffer still holds the stamp before it draws the pointer again.
"""

import fontset as _fontset
import iconsets as _iconsets
import ui_draw as _ui_draw

FAMILIES = ("pixel", "moy", "coast", "luna", "blocks")
NAMES = ("Pixel", "Moy", "Coast", "Luna", "Blocks")
# Ids a saved pick may still name, and the family each became (2026-11-26).
RENAMED = {"default": "moy", "playful": "blocks"}
SHAPES = ("arrow", "hand", "text", "ew", "ns", "nwse", "nesw", "move", "busy")
SIZES = (16, 32, 48)
FIRST = 0x21
_LAYERS = 3
_AT = {k: _LAYERS * i for i, k in enumerate(SHAPES)}
# Each family's outline, fill and accent (the nearest MOY64 each draws in),
# and its shadow's ink and alpha (0..256; 0: none).
COLOURS = {
    "pixel": ("#000000", "#fff1e8", "#000000", "#000000", 0),
    "moy": ("#000000", "#fff1e8", "#000000", "#000000", 48),
    "coast": ("#1d2b53", "#fff1e8", "#2de0e0", "#1d2b53", 68),
    "luna": ("#000000", "#fff1e8", "#b7a1e6", "#000000", 80),
    "blocks": ("#1d2b53", "#ffec27", "#fff1e8", "#1d2b53", 68),
}
# The family a smooth icon set without one of its own wears.
_SET_DEFAULT = "moy"

_IDX = {}                     # family -> (outline, fill, accent, alpha), indices
_FONT = [None, 0, None]       # the one file loaded: (family, size), its font id, its bytes
_HAVE = {}                    # (family, size) -> the image carries it


def theme_family(look):
    """The family a live look (`chrome.Live.look`) wears: its `pointer`,
    else its icon set's."""
    texts = look[4] if len(look) > 4 else ()
    k = look[0].get("pointer", 0)
    name = texts[k - 1] if 0 < k <= len(texts) else None
    if name in FAMILIES:
        return name
    sp = _iconsets.spec(look)
    if sp is None or sp[0] == "pixel":
        return "pixel"
    return sp[1] if sp[1] in FAMILIES else _SET_DEFAULT


def carried(family, px):
    """Whether this image holds `family` at `px`."""
    key = (family, px)
    got = _HAVE.get(key)
    if got is None:
        got = _HAVE[key] = _fontset.icon_file("ptr-%s-%d.fnt" % key) is not None
    return got


def size(family, scale, large=False):
    """The size `family` draws at chrome scale `scale`: the largest the image
    holds within 16 px a scale step (Large: twice that on a 1x screen, half
    again above it), else the smallest it holds; 0 where it holds none."""
    want = 16 * max(1, scale)
    if large:
        want = want * 2 if want == 16 else want * 3 // 2
    best = 0
    for px in SIZES:
        if carried(family, px) and (px <= want or not best):
            best = px
    return best


def _colours(family):
    got = _IDX.get(family)
    if got is None:
        c = COLOURS[family]
        got = _IDX[family] = tuple(
            _ui_draw._C.theme_rgb(0x1000000 | int(v[1:], 16))[2] for v in c[:4]) + (c[4],)
    return got


def _shadow(family, shape, px):
    """How far down and right `shape`'s shadow falls at `px`: a pixel per 16
    px, none at 16 px (its 1-bit art), on a text beam, or in a family
    without one."""
    if px <= 16 or shape == "text" or not COLOURS[family][4]:
        return 0
    return px // 16


def _font(family, px):
    """The font id of `family` at `px`, loaded in place of the one before;
    0 where the image holds none or no slot is free."""
    f = _FONT
    if f[0] is not None and f[0][0] == family and f[0][1] == px and f[1]:
        return f[1]
    if f[1]:
        _ui_draw.font_free(f[1])
    src = _fontset.icon_file("ptr-%s-%d.fnt" % (family, px))
    fid = 0
    if src is not None:
        rc, got = _ui_draw.font_load(src)
        fid = got if rc == 0 and got is not None else 0
    f[0], f[1], f[2] = (family, px), fid, src if fid else None
    return fid


def draw(cv, family, shape, x, y, px):
    """Pointer `shape` of `family` at `px`, its hotspot at (x, y). False
    where the image holds no such file (nothing drawn). A font the loader
    refuses (its slots freed under it: `ui_draw.font_reset`) is loaded
    again."""
    fid = _font(family, px) if px else 0
    if not fid:
        return False
    try:
        _layers(cv, fid, family, shape, x, y, px)
    except ValueError:
        _FONT[1] = 0
        fid = _font(family, px)
        if not fid:
            return False
        _layers(cv, fid, family, shape, x, y, px)
    return True


def _layers(cv, fid, family, shape, x, y, px):
    line, fill, accent, ink, alpha = _colours(family)
    C = _ui_draw._C
    b = FIRST + _AT[shape]
    d = _shadow(family, shape, px)
    if d:
        C.icon_mask(cv, fid, b, x + d, y + d, ink, alpha)
    C.icon_mask(cv, fid, b, x, y, line)
    C.icon_mask(cv, fid, b + 1, x, y, fill)
    C.icon_mask(cv, fid, b + 2, x, y, accent)


def box(family, shape, x, y, px, out=None):
    """(x, y, w, h) that `shape` covers with its hotspot at (x, y), its
    shadow included, written into list `out` where given (then answered);
    None where it draws nothing."""
    if not _font(family, px):
        return None
    src = _FONT[2]
    r = 16 + 256 + 8 * src[16 + FIRST + _AT[shape]]     # the outline glyph's record
    w, h = src[r + 3], src[r + 4]
    if not w:
        return None
    x0 = src[r + 5] - 256 if src[r + 5] > 127 else src[r + 5]
    up = src[r + 6] - 256 if src[r + 6] > 127 else src[r + 6]
    d = _shadow(family, shape, px)
    if out is None:
        return (x + x0, y - up, w + d, h + d)
    out[0], out[1], out[2], out[3] = x + x0, y - up, w + d, h + d
    return out


def image(cv, family, shape, px):
    """(w, h, hx, hy, rgba): `shape` of `family` at `px` as straight RGBA
    bytes and its hotspot, drawn on scratch canvas `cv` (at least the
    shape's box) over black and again over white, its alpha the difference:
    the same pixels the console draws, for a page whose pointer is the
    browser's (firmware/web_runner/web_boot.py)."""
    b = box(family, shape, 0, 0, px)
    if b is None:
        return None
    w, h = min(b[2], cv.w), min(b[3], cv.h)
    k = g = span = None
    for ci in (0, 7):
        cv.cls(ci)
        ground = _rgb_rows(cv, 1, 1)
        draw(cv, family, shape, -b[0], -b[1], px)
        if ci:
            g, span = _rgb_rows(cv, w, h), sum(ground) - span
        else:
            k, span = _rgb_rows(cv, w, h), sum(ground)
    out = bytearray(w * h * 4)
    for i in range(w * h):
        r0, g0, b0 = k[3 * i], k[3 * i + 1], k[3 * i + 2]
        diff = (g[3 * i] - r0) + (g[3 * i + 1] - g0) + (g[3 * i + 2] - b0)
        a = 255 - diff * 255 // span
        a = 0 if a < 0 else 255 if a > 255 else a
        if a:
            j = 4 * i
            out[j] = min(255, r0 * 255 // a)
            out[j + 1] = min(255, g0 * 255 // a)
            out[j + 2] = min(255, b0 * 255 // a)
            out[j + 3] = a
    return w, h, -b[0], -b[1], bytes(out)


def _rgb_rows(cv, w, h):
    """RGB888 of the canvas's top-left w x h, read from its RGB565 buffer."""
    buf = cv._buf
    hi = 0 if getattr(cv, "swapped565", True) else 1
    out = bytearray(w * h * 3)
    for y in range(h):
        o = y * cv.w * 2
        for x in range(w):
            v = buf[o + hi] << 8 | buf[o + 1 - hi]
            o += 2
            j = 3 * (y * w + x)
            out[j] = (v >> 11 & 31) * 255 // 31
            out[j + 1] = (v >> 5 & 63) * 255 // 63
            out[j + 2] = (v & 31) * 255 // 31
    return out


class Under:
    """What lies under the pointer in each buffer it was drawn into: before
    it draws, `put_back` restores its last stamp in the canvas's buffer
    wherever the buffer still holds it (`moy_gfx.restore_under`: a pixel
    painted since stays); `keep` takes what is under the box it draws in
    next, and `drawn` the stamp once it is drawn. A buffer a canvas swaps
    to keeps its own (the boards' two and three retained frames). Nothing
    is made a frame but the first copies at a size."""

    SLOTS = 4                       # the buffers remembered, the oldest dropped

    def __init__(self):
        self._slots = []            # [buf, x, y, w, h, saved, drawn]
        self.box = [0, 0, 0, 0]     # `box`'s answer, written in place

    def _slot(self, buf):
        for s in self._slots:
            if s[0] is buf:
                return s
        s = [buf, 0, 0, 0, 0, None, None]
        if len(self._slots) >= self.SLOTS:
            self._slots.pop(0)
        self._slots.append(s)
        return s

    def put_back(self, cv):
        """The canvas's buffer as it was before the pointer was drawn into it
        last, where nothing painted since."""
        gfx = getattr(cv, "_gfx", None)
        if gfx is None:
            return
        s = self._slot(cv._buf)
        if s[3]:
            gfx.restore_under(s[0], cv._stride, s[1], s[2], s[3], s[4], s[5], s[6])
            s[3] = 0

    def keep(self, cv, x, y, w, h):
        """Take what lies under (x, y, w, h) of the canvas's buffer, clipped
        to it, before the pointer draws there."""
        gfx = getattr(cv, "_gfx", None)
        if gfx is None:
            return
        buf, st = cv._buf, cv._stride
        rows = len(buf) // (2 * st)
        if x < 0:
            w += x
            x = 0
        if y < 0:
            h += y
            y = 0
        w = min(w, st - x)
        h = min(h, rows - y)
        s = self._slot(buf)
        if w <= 0 or h <= 0:
            s[3] = 0
            return
        n = 2 * w * h
        if s[5] is None or len(s[5]) < n:
            s[5] = bytearray(n)
            s[6] = bytearray(n)
        gfx.copy_block(s[5], w, buf, st, 0, 0, x, y, w, h)
        s[1], s[2], s[3], s[4] = x, y, w, h

    def drawn(self, cv):
        """Take the stamp just drawn over what `keep` took."""
        gfx = getattr(cv, "_gfx", None)
        if gfx is None:
            return
        s = self._slot(cv._buf)
        if s[3]:
            gfx.copy_block(s[6], s[3], s[0], cv._stride, 0, 0, s[1], s[2], s[3], s[4])


def reset():
    """Forget the loaded file (the font slots outlive a VM)."""
    if _FONT[1]:
        _ui_draw.font_free(_FONT[1])
    _FONT[0], _FONT[1], _FONT[2] = None, 0, None
    _HAVE.clear()
