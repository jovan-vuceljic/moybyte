# Map (grep -n a name to jump there):
#   _band_frame      the band frame: a drag, a fling, a step, a settle
#   _band_key        the band's keys: what it is drawn under, what its cards are of
#   _band_alone      whether the band is all a frame changes on the glass
#   _Keyed           an int that names a value a frame keys on
#   _statics_base    what the frame round the band is a function of
#   _ground_of       the home's ground's colour
#   _wall_ink        the text's ink over a wallpaper
#   held             the part buffers: which buffer holds a part, the face slots, the kept table's floor
"""The home's BAND FRAME (#113, #58/#66): the frame whose change is the
cards' band alone -- a drag, a fling, a step, a settle -- draws the band's
kept table of parts over the ground and leaves every other pixel of the
retained frame standing. ONE body for the home (`LauncherHomeLayer`) and the
home in a desk window (`HomeWindowLayer`), with the keys it trusts and the
small reads of the look both homes and their arrangements share (the
ground, the ink over a wallpaper, the dim, the cursor's stamp). A leaf: it
reads the layer and the grid it is handed and imports no home module.

The part buffers the bands draw through are here too: whether the buffer a
frame paints holds a part as a frame drew it (`held`, `held_last`,
`held_all`), the faces kept drawn in a layer's slots (`slots`, `slot`,
`slot_next`), and the kept table's floor (`table_floor`, `table_copy`), each
over the context the host began (`ui_draw.UI_TARGET`).
"""

from array import array

import moy_ui as _C
import ui_draw as _D
from chrome import _ticks_ms, _ticks_diff

_T = _D.UI_TARGET

_UNSET = -2147483648      # a look leaf the theme leaves silent



def _wall_ink(ws):
    """(white, black) where the home lies on a wallpaper -- a cart or a
    picture, pixels the theme does not know -- else None: its text is then
    white over a black shadow, as the desk's labels are
    (docs/history/look_2026-10.md steps 25 and 28)."""
    if ws.look.wallpaper_id is None:
        return None
    f = ws.look.live.fixed
    k = _WALL_INK[0]
    if k is None or k[0] != f[3] or k[1] != f[2]:
        k = _WALL_INK[0] = (f[3], f[2])
    return k


_WALL_INK = [None]      # the pair `_wall_ink` answered last: the same while it stands


def _overlaps_any(rects, others):
    """Whether any of `rects` meets any of `others` (x, y, w, h)."""
    for a in rects:
        for b in others:
            if (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                    and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]):
                return True
    return False


def _ground_of(ws):
    """The home's ground's colour: the look's `home_bg`, else the theme's
    `desktop` fill."""
    look = getattr(getattr(ws, "look", None), "live", None)
    c = _UNSET if look is None else look.look[0].get("home_bg", _UNSET)
    return ws.theme_colors["desktop"] if c == _UNSET else c


def _dim_of(ws):
    """The theme's neighbour dimming (`dim_neighbours`, Moy Night's): the
    colour the carousel's neighbours are dimmed toward -- the home's ground
    (`_ground_of`) -- and its alpha (0..255), or None."""
    look = getattr(getattr(ws, "look", None), "live", None)
    if look is None:
        return None
    pct = look.look[0].get("dim_neighbours", 0)
    if not pct or pct < 0:
        return None
    return (_ground_of(ws), (pct * 255 + 50) // 100)


def _cursor_stamp(ws):
    """The pointer's footprint on the system canvas this frame
    (`Workstation.pointer_box`), or None when it isn't drawn -- recorded with
    each shelf paint (#113) so a blitted frame can repaint the stale stamp the
    shift dragged along."""
    return ws.pointer_box()


def _statics_base(ws, cv, grid):
    """What BOTH grid layers' static chrome is a pure function of: the canvas,
    the font scale, the look (`look_gen`), the grid rect (#113:
    set_layout no longer invalidates the ring eagerly, since the windowed tier
    re-applies layouts several times per frame, so this key is what makes a
    paint recorded under a different layout unmatchable) and the item count.
    The home shelf folds its own extras on top."""
    return (cv.w, cv.h, ws.layout.fs, ws.look.look_gen,
            grid.band_rect(), len(grid.items))


def _band_alone(ws, dt, kind, calm=False):
    """Whether this frame leaves the home's band its own on the glass but
    for the cursor (the paint ring's stamp): the home on top in console
    mode, nothing animating, no overlay, splash or owed LOADING pill over
    it (its own band page moving on its own changes nothing outside the
    band). `calm`: the caller found it on top with nothing animating."""
    wm = ws.wm
    if not calm:
        if ws.animating(dt, False):
            return False
        top = getattr(wm, "top_kind", None)
        if top is not None and top() != kind:
            return False
    if getattr(wm, "cache_sig", 0) != 0 or getattr(wm, "mode", "console") != "console":
        return False
    return not (ws.deferred and ws.toast_owed())


class _Keyed:
    """An int that names a value a frame keys what it draws on (a kept
    table's `o.keep`, a part `held` names): the same while the value
    compares equal to the one before, another once it does not."""

    def __init__(self):
        self.v = None
        self.n = 0

    def of(self, v):
        if v != self.v:
            self.v = v
            self.n = (self.n + 1) & 0x3fffffff
        return self.n

    def of3(self, a, b, c):
        """`of((a, b, c))`, the tuple made only where one of them moved."""
        v = self.v
        if v is None or v[0] != a or v[1] != b or v[2] != c:
            self.v = (a, b, c)
            self.n = (self.n + 1) & 0x3fffffff
        return self.n


def _band_key(layer, cv, dt, grid, vouch, calm=False):
    """The band's keys (`band_pass`'s `key`): what the frame round the band
    is drawn under (the statics, `_statics_key`) and what the band table's
    every card is a function of beside its row (`o.keep`: the statics, the
    cover gen and the arrangement's own, `band_key`) -- both -1, this
    frame's paint keeping nothing, where the home `vouch`es for its buffers
    and the band is not its alone on the glass (`_band_alone`)."""
    ws = layer.ws
    k = layer._keys
    gen = ws.covers.gen
    if gen != layer._keyed_gen:
        layer._keyed_gen = gen
    if vouch and not _band_alone(ws, dt, layer.id, calm):
        k[0] = k[1] = -1
        return k
    k[0] = layer._sk.of(layer._statics_key(cv))
    k[1] = layer._bk.of3(k[0], gen, grid.band_key())
    return k


def _band_frame(layer, cv, dt, grid, kind, fill, strip, timed=False, steps=False):
    """The home layers' band frame (#113, #58/#66), ONE body for the home and
    the home window: a frame whose change is the cards' band draws the band
    alone -- its kept table of parts (`repaint_band`: the engine draws what
    the buffer this frame paints lacks of it, over the ground `fill(cv,
    rect)` puts back) -- and the bar strip, where that buffer holds the
    band and the frame round it under this frame's key (`held`).

    Without `steps` only a drag or a fling takes the path (the home window,
    the desk's carousel, whose selection lies outside the band); with it any
    frame does -- a key, a repeat or a trackball step, a settle -- and the
    parts outside the band a selection changes (the hint strip, the icons'
    caption band) are drawn again where the buffer holds another
    selection's (`_beside`).

    `strip` is the bar strip's kind; `timed` records the home diag's
    `ws.pf_home` split under perf_capture. Returns False when the frame
    must be painted in full."""
    ws = layer.ws
    moving = grid.dragging or grid.flinging
    if not (moving or steps):
        return False
    if getattr(cv, "RETAINED_FRAMES", 0) < 1:
        return False
    # Anything animating over the surface (toast/confetti/splash/live
    # wallpaper) moves pixels outside the band -> full frames; the band's
    # own page moving (the handheld's carousel) is this frame's.
    if ws.animating(dt, False):
        return False
    top = getattr(ws.wm, "top_kind", None)
    if top is not None and top() != kind:
        return False
    bx, by, bw, bh = grid.band_rect()
    stamp = _cursor_stamp(ws)
    if stamp is not None:
        # The composited cursor must land fully inside the redrawn band,
        # or its previous stamp would ghost on the untouched chrome.
        sx, sy, sw, sh = stamp
        if not (bx <= sx and sx + sw <= bx + bw and by <= sy and sy + sh <= by + bh):
            return False
    _t0 = _ticks_ms() if timed and getattr(ws, "perf_capture", False) else None
    end = grid.repaint_band(cv, ws.covers.sheet_icon, fill,
                            _band_key(layer, cv, dt, grid, steps, True), stamp,
                            layer._beside if steps else None, True)
    if end is None:
        return False
    # The rects drawn are the frame's damage (read before a landing's note
    # empties the floor); the bar strip carries its own word.
    a = 0
    for r in grid.floor:
        ws.wm.hand_content_damage(cv, r[0], r[1], r[2], r[3])
        a += r[2] * r[3]
    for r in grid.copied:
        ws.wm.hand_content_damage(cv, r[0], r[1], r[2], r[3])
        a += r[2] * r[3]
    for r in grid.shifted:
        ws.wm.hand_content_damage(cv, r[0], r[1], r[2], r[3])
        a += r[2] * r[3]
    whole = 2 * a > bw * bh             # (more than a step's cells: a scroll's, a jump's)
    if not moving:
        # (a moving frame notes no cover landing: the next frame scrolls
        # the band and draws it whatever its key)
        whole = layer._band_landed(cv, dt, steps) or whole
    _t1 = _ticks_ms() if _t0 is not None else None
    ws.bar_layer.draw_status_strip(strip)
    if steps:
        for r in layer._beside_drew:
            ws.wm.hand_content_damage(cv, r[0], r[1], r[2], r[3])
    if _t0 is not None:
        ws.pf_home = (0, _ticks_diff(_t1, _t0), _ticks_diff(_ticks_ms(), _t1))
    if steps and not moving:
        layer._band_settle(end, whole)
    return True


# -- the part buffers ------------------------------------------------------------

def held(id, key):
    """Whether the buffer this frame paints holds part `id` of the page as
    a frame drew it under `key` (an int); names `id` under `key` for this
    frame, whose pass draws the part where it answers False."""
    return _C.api_held(_T[0], id, key)


def held_last(id, key):
    """Whether the buffer the last frame painted holds part `id` as that
    frame named it under `key`: for a part copied out of that buffer.
    Names nothing."""
    return _C.api_held_last(_T[0], id, key)


def held_all():
    """Whether every buffer the canvas presents holds every part this frame
    named (`held`) as it names it. False where the canvas keeps nothing."""
    return _C.api_held_all(_T[0])


SLOT_MINT = 0x10000                     # `slot`'s answer: draw the face into the slot first


def slots(cap, key):
    """Keep the parts' faces drawn in `cap` square slots of a layer the app
    owns, under `key` (another key or `cap` forgets every face). Answers the
    slots kept (at most 128)."""
    return _C.api_slots(_T[0], cap, key)


def slot(name, gen=0, mint=False):
    """The slot holding the face `name` and `gen` name, to stamp; else with
    `mint` the slot to draw it into | `SLOT_MINT`; else -1, the part drawn
    as it is."""
    return _C.api_slot(_T[0], name, gen, mint)


def slot_next():
    """The next part whose face an idle frame draws (handed to `slot` with
    `mint`); -1 after the last."""
    return _C.api_slot_next(_T[0])


_TF = array("i", [0] * 4)               # table_floor's and table_copy's answer


def table_floor(r):
    """The kept table's next floor rect this frame draws, written into `r`
    (four words), 1, for the ground to go back there before its parts draw;
    after the last, 0 where every buffer holds the table as this frame
    draws it, -1 where one lags, -2 where they hold it but for what was
    drawn over it."""
    a = _TF
    v = _C.api_table_floor(_T[0], a)
    if v > 0:
        r[0] = a[0]
        r[1] = a[1]
        r[2] = a[2]
        r[3] = a[3]
    return v


def table_copy(r, back=False):
    """Before `table_floor`: the next rect of the floor the buffer the last
    frame painted holds as this frame draws it, written into `r`, 1, to copy
    out of that buffer (the canvas's `copy_last`); 0 after the last. `back`
    gives the rect answered last back to the floor and answers 0."""
    a = _TF
    v = _C.api_table_copy(_T[0], a, back)
    if v > 0:
        r[0] = a[0]
        r[1] = a[1]
        r[2] = a[2]
        r[3] = a[3]
    return v
