# Map (grep -n a name to jump there):
#   ViewLayout     the page's measures: the view, the column beside it, the foot, the brushes
#   PageHost       a placed page's host: made at its first use, its sync, frame and pointer
#   ViewHost       a view tab's PageHost: its keys, the view's gestures, the brushes
#   checker        transparency's grey checker (the Sprite, Map, Scene and theme editors)
"""The host of a placed `uitree` page round a panned, zoomed view: the
Editor's World tab (`map_editor_ui.MapEditorUI`, its page `editor_map.py`)
and its Scene tab (`scene_editor_ui.SceneEditorUI`, `editor_scene.py`),
the handheld's tab and a desk Editor's pane alike.

`ViewLayout` measures the page: on the handheld the view from the content
rect's top left to the column beside it and the foot under both, the
brushes four by four at the largest scale the column holds and the lines
under them it has room for, a foot tool's pitch; in a desk pane the view
alone, over a status line where the tab has one.

`PageHost` hosts a placed page an Editor tab draws on the content rect
(a desk pane's part, `editor_parts.PartHost`, is one): made
at its first use, the tab's state handed to its `sync` hook where it moved
(`push`), its frame and its pointer. `ViewHost` is one round a view, with
its keys. The view's canvas hands the host a press, its drag
and its release (`press`, `drag`, `release`, in SYSTEM coords); a drag past
the tap's dead zone pans (`pan_drag`); the view's keys are the arrows
(`arrows`) and A, which steps the zoom. The brushes' canvas draws a page of
the sheet's sprites over the transparency checker, and its taps and arrows
pick the brush. A subclass answers the rest: its editor's state
(`_sync`), the camera (`pan`, `step`, `clamp_cam`, `cycle_zoom`), the
gestures and the brush (`brush`, `set_brush`)."""

from array import array

import ui_draw as _ui_draw
import uitree_app
import uitree_editor
from layout_base import (LayoutBase, BASE_W as _BASE_W, BASE_H as _BASE_H, pane as _in_pane,
                         metric_class as _metric_class, DESK as _DESK)

# A brush's pitch, the tile 20 inside it, and the brushes' pad round them,
# in the page's unit; the brushes a page shows, four rows of four.
CELL = 22
BRUSH_PAD = 6
BRUSHES = 16
# The handheld page's column beside the view, and a foot tool's cell, in
# the page's unit.
COL = 104
TOOL = 24
# A press dragged farther than this from where it went down pans the view
# (#37); a shorter press and release is a tap.
PAN_THRESH = 6


class ViewLayout(LayoutBase):
    """The page's geometry, from the SYSTEM canvas size (w, h) and font
    scale. On the handheld (`verbs`) the view runs from the content rect's
    top left to the page's column and its foot (a rule and a row); in a
    desk Editor's pane (`pane`) it fills the pane, over a status line where
    `STATUS` says the tab has one. The view's rect as the page placed it
    last is what the host reads (`ViewHost.view_at`); `view_*` are its
    measure before that. `ZOOMS` are the tab's zoom rungs."""

    ZOOMS = ()
    STATUS = False

    def __init__(self, w=_BASE_W, h=_BASE_H, font_scale=1, chrome_scale=None):
        LayoutBase.__init__(self, w, h, font_scale, chrome_scale=chrome_scale)
        fs = self.fs
        cx, cy, cw, ch = self.cx, self.cy, self.cw, self.ch
        self.zooms = self.ZOOMS
        self.pan_thresh = PAN_THRESH * fs
        self.desk = desk = _metric_class() == _DESK
        self.pane = _in_pane()
        self.verbs = not self.pane
        # the page's unit: a canvas's h= and a button's w= are multiplied by it
        self.unit = u = 1 if desk else fs
        row = 48 if desk else 22 * fs
        self.view_x0, self.view_y0 = cx, cy
        if self.pane:
            self.view_w = cw
            self.view_h = ch - (max(20, _ui_draw.font("ui")[2] + 2) * fs if self.STATUS else 0)
        else:
            self.view_w = max(0, cw - COL * u)
            self.view_h = max(0, ch - row - (1 if desk else fs))
        # a foot tool's pitch in the page's unit: a desk's touch target (32 px at
        # least), else narrower where the foot would not hold the whole row
        self.pitch = 36 if desk else TOOL if cw >= 320 * u else TOOL - 4
        # the column: the brushes at the largest scale `bk` (up to the unit) that
        # leaves a row for their pager, then as many lines (`lines`, three at
        # most) as its height holds
        need = 2 * BRUSH_PAD + 4 * CELL - 2
        room = self.view_h - row
        self.bk = bk = max(1, min(u, room // need))
        self.brushes_h = (need * bk + u - 1) // u
        self.lines = max(0, min(3, (room - self.brushes_h * u) // row))


# The ring a canvas draws round what it picked (the brushes', the desk Sheet's).
cursor = _ui_draw.cursor
# What the desk's own canvases draw in the theme (editor_parts.py): a label in
# the UI face, the current mark under a row, a button's plate, a glyph.
label = _ui_draw.label
ALIGN_RIGHT = _ui_draw.ALIGN_RIGHT
current = _ui_draw.current
plate = _ui_draw.button
glyph = _ui_draw.glyph
hint_kind = _ui_draw.hint_kind


def ui_line():
    """The UI face's ascent at scale 1."""
    return _ui_draw.font("ui")[3]


def ui_face_line():
    """The UI face's line, its leading included, at scale 1."""
    return _ui_draw.font("ui")[2]


def text_w(text, fs=1):
    """The pixels `text` takes in the UI face at scale `fs`."""
    return _ui_draw.text_width(text, fs, "ui")


class _Damage:
    def __init__(self, ws):
        self.ws = ws

    def all(self):
        self.ws.mark_dirty()


def went_up(page):
    """Whether the last frame's up press on placed page `page` found no
    stop above its focus (the engine's `edge`): the keys went past its top."""
    return page is not None and bool(page.edge() & uitree_app.EDGE_UP)


class PageHost:
    """A placed page an Editor tab draws on the content rect, hosted over
    `ws`: `tab` the tab it is (a desk pane the keys are not in shows no
    focus), `build` its page. The subclass hands the page its state
    (`_sync`, through `push`) and has a `layout` with the content rect,
    `desk` and `pane`."""

    BAND = False                       # the page's band names its keys

    def __init__(self, ws, names, tab, build):
        self.ws = ws
        self._NAMES = names            # injected, not imported back from console.py (a cycle)
        self.tab = tab
        self._build = build
        self.page = None               # the page's engine, made at its first use
        self._host = _ui_draw.AppHost("editor_" + tab, self)
        self._shown = None             # the values handed to the page's sync last
        self._rect = None              # the content rect, as a tuple drawn with
        self._due = None               # a hook the next draw runs (the keys' new stop)

    # -- the page ------------------------------------------------------------

    def _page(self):
        """The page's engine, made and opened at its first use, the view
        holding the keys."""
        if self.page is None:
            pg = self.page = uitree_editor.page(self._build, self._host, _Damage(self.ws))
            pg.env = self                   # what its handlers reach (`uitree_app.env()`)
            pg.bare = True                  # its ground is the host's
            pg.band = self.BAND
            ws = self.ws                    # a canvas holds its press while the pointer is down
            pg.pointer_down = lambda: bool(ws.pointer.down)
            pg.open(hook="none")
            self._sync()
            self.run("home")
        return self.page

    def run(self, name, *args):
        """Run the page's action or hook `name` now."""
        pg = self._page()
        pg._bind()
        pg.run_action(pg.actions[name], args, "host")

    def pointer(self):
        """The pointer, where the page's host reads whether it is held."""
        return self.ws.pointer

    def rect_of(self, key):
        """Where the last frame placed the page's node `key`, in SYSTEM
        coords (None before it drew)."""
        return None if self.page is None else self.page.rect_of(key)

    def push(self, vals):
        """The page's `sync` hook handed `vals` where they moved."""
        if vals != self._shown:
            self._shown = vals
            self.run("sync", vals)

    def draw(self, dt):
        """The tab: the page on the content rect (the handheld's tab, a
        desk pane's view)."""
        ws = self.ws
        lay = self.layout
        r = self._rect
        if r is None or r[0] != lay.cx or r[1] != lay.cy or r[2] != lay.cw or r[3] != lay.ch:
            r = self._rect = (lay.cx, lay.cy, lay.cw, lay.ch)
        cv = ws.sys_canvas
        th = ws.theme_colors
        pg = self._page()
        cv.rect(r[0], r[1], r[2], r[3], th["surface"])
        d = ws.editor_desk if lay.pane else None
        # a desk's pane the keys are not in shows no focus
        away = d is not None and d.tab_of(d.focused()[0]) != self.tab
        self._host.begin(cv, th, r, lay.desk, False, away)
        self._sync()
        due = self._due
        if due is not None:
            self._due = None
            self.run(due)
        pg.paint(dt, cv, th, r, lay.desk)
        self._host.end()
        if not self._host.still():
            ws.request_frame()

    def at_top(self):
        """The page's keys went past its top, no popover open: an up goes
        on to the bar (InputRouter._bar_keys)."""
        return not self.popover() and went_up(self.page)

    def popover(self):
        """Whether a popover of the page's is open."""
        return False

    def handle_pointer(self, px, py, click):
        """A pointer sample for the page; what a canvas's press does lands
        with the input, where a desk's frame sees what it changed."""
        pg = self._page()
        pg.point(px, py, click)
        q = pg.q
        if q:
            pg.q = []
            pg._bind()
            for act, args, src in q:
                pg.run_action(act, args, src)

class ViewHost(PageHost):
    """A view tab's page host (`PageHost`): `layout` its `ViewLayout`
    class."""

    def __init__(self, ws, names, tab, build, layout):
        PageHost.__init__(self, ws, names, tab, build)
        self._layout = layout
        self._view_r = None            # the view's rect as the page placed it last
        self.brush_page = 0            # the first sprite on the brushes' page
        self._press = None             # the view's press (px, py); None outside one
        self._panning = False          # the press's drag crossed the dead zone: it pans
        self._drag = None              # where the pan's drag is consumed to
        self._pan_acc = [0, 0]         # a middle drag's pixels not yet a step
        sc = ws.sys_canvas
        self.layout = layout(sc.w, sc.h, getattr(sc, "font_scale", 1))

    def relayout(self, w, h, fs, cs=None):
        """Rebuild the responsive geometry (#39): ws.relayout's fan-out on a
        font-scale change, and EditorApp.set_tab's on every entry into the
        tab (#216); the camera clamped to the reflowed view."""
        self.layout = self._layout(w, h, fs, chrome_scale=cs)
        self._view_r = None
        self.clamp_cam()

    def handle_input(self, i):
        """The frame's keys: the page's (the view's and the brushes' their
        canvases'); B closes an open popover, else leaves the tab."""
        if self.popover():
            if i.pressed("b"):
                self.close_pop()
            else:
                self._page().keys(i)
            return
        self._page().keys(i)          # (the page's damage marks what the keys moved)
        self.ws.home.leave_or_home(self.ws.spine.exit)

    def at_top(self):
        """The view holding the keys at its top (`view_top`), or the page's
        keys past its top, no popover open: an up goes on to the bar
        (InputRouter._bar_keys)."""
        return (self.page is not None and not self.popover()
                and (self.page._focus_key() == "view" and self.view_top()
                     or went_up(self.page)))

    # -- the view --------------------------------------------------------------

    def view_at(self, x, y, w, h):
        """The view's canvas placed at (x, y, w, h): its rect, and the
        camera clamped to it where it moved."""
        r = self._view_r
        if r is None or r[0] != x or r[1] != y or r[2] != w or r[3] != h:
            self._view_r = (x, y, w, h)
            self.clamp_cam()

    def view_pointer(self, kind, x, y):
        """A press on the view, its drag and its release, in its coordinates."""
        r = self._view_r
        if r is None:
            return
        px, py = x + r[0], y + r[1]
        if kind == "down":
            self._press = (px, py)
            self._panning = False
            self._drag = None
            self.press(px, py)
        elif kind == "drag":
            if self._press is not None:
                self.drag(px, py)
        else:
            self.release(px, py)
            self._press = None
            self._panning = False
            self._drag = None
        self.ws.mark_dirty()

    def pan_drag(self, px, py, step):
        """The press dragged to (px, py): past the tap's dead zone it pans
        the camera a unit every `step` pixels, the content following the
        finger. Whether this sample crossed the dead zone."""
        press = self._press
        crossed = False
        if not self._panning:
            t = self.layout.pan_thresh
            if abs(px - press[0]) < t and abs(py - press[1]) < t:
                return False
            self._panning = crossed = True
            self._drag = press
        last = self._drag
        dx = _ui_draw.drag_steps(last[0] - px, step)
        dy = _ui_draw.drag_steps(last[1] - py, step)
        if dx or dy:
            self.pan(dx, dy)
            # the anchor moves by the whole steps taken; a slow drag keeps its remainder
            self._drag = (last[0] - dx * step, last[1] - dy * step)
        return crossed

    def drag_pan(self, dx, dy):
        """The view dragged `dx`, `dy` pixels (a middle drag, the wheel
        across): the camera the other way, a step at a time."""
        step = self.step()
        acc = self._pan_acc
        acc[0] -= dx
        acc[1] -= dy
        sx, sy = int(acc[0] / step), int(acc[1] / step)
        if sx or sy:
            acc[0] -= sx * step
            acc[1] -= sy * step
            self.pan(sx, sy)

    def view_keys(self, i):
        """The view's keys while it holds focus: the arrows (`arrows`), A
        steps the zoom. An arrow it does not take is the page's, which
        moves focus on."""
        if not self.ready():
            return False
        dx = i.steps("right") - i.steps("left")
        dy = i.steps("down") - i.steps("up")
        took = bool((dx or dy) and self.arrows(dx, dy))
        if i.pressed("a"):
            self.cycle_zoom()
            took = True
        if took:
            self.ws.mark_dirty()
        return took

    # -- the brushes -----------------------------------------------------------

    def brush_ids(self):
        """The sprites on the brushes' page (clamped to the sheet)."""
        sheet = self.ws.run.project.sheet
        if sheet is None:
            return []
        start = self.brush_page
        return list(range(start, min(start + BRUSHES, sheet.count)))

    def pager(self):
        """The brushes' pages: (on the first, on the last, "n / m")."""
        sheet = self.ws.run.project.sheet
        pages = max(1, (sheet.count + BRUSHES - 1) // BRUSHES) if sheet is not None else 1
        cur = self.brush_page // BRUSHES
        return cur == 0, cur + 1 >= pages, "%d / %d" % (cur + 1, pages)

    def page_step(self, d):
        """The brushes' page before (`d` -1) or after (1)."""
        sheet = self.ws.run.project.sheet
        last = max(0, (sheet.count - 1) // BRUSHES * BRUSHES) if sheet is not None else 0
        self.brush_page = max(0, min(last, self.brush_page + d * BRUSHES))

    def _brush_at(self, x, y):
        """The brush (its place on the page) at (x, y) in the brushes'
        canvas, -1 none."""
        u = self.layout.bk
        x -= BRUSH_PAD * u
        y -= BRUSH_PAD * u
        c = CELL * u
        if x < 0 or y < 0 or x >= 4 * c or y >= 4 * c:
            return -1
        k = y // c * 4 + x // c
        return k if k < len(self.brush_ids()) else -1

    def _pick_brush(self, k):
        ids = self.brush_ids()
        if self.ready() and 0 <= k < len(ids):
            self.set_brush(ids[k])
            self.ws.mark_dirty()

    def brush_tap(self, x, y):
        """A tap on the brushes, in their coordinates: the brush under it."""
        self._pick_brush(self._brush_at(x, y))

    def brush_keys(self, i):
        """The brushes' keys while they hold focus: the arrows move the
        brush along the page's four rows of four. An arrow past their edge
        is the page's."""
        ids = self.brush_ids()
        if not self.ready() or not ids:
            return False
        dx = i.steps("right") - i.steps("left")
        dy = i.steps("down") - i.steps("up")
        if not (dx or dy):
            return False
        n = self.brush()
        k = ids.index(n) if n in ids else -1
        if k < 0:
            self._pick_brush(0)
            return True
        x, y = k % 4 + dx, k // 4 + dy
        if not (0 <= x < 4 and 0 <= y < 4 and y * 4 + x < len(ids)):
            return False
        self._pick_brush(y * 4 + x)
        return True

    def draw_brushes(self, cv, x, y, w, h):
        """The brushes: the page's sixteen sprites on the grey checker four
        by four, the brush's ringed by the cursor."""
        ws = self.ws
        sheet = ws.run.project.sheet
        if sheet is None or not self.ready():
            return
        u = self.layout.bk
        c = CELL * u
        s = c - 2 * u
        x0, y0 = x + BRUSH_PAD * u, y + BRUSH_PAD * u
        ids = self.brush_ids()
        dark, light = ws.look.live.fixed[:2]
        d = 2 * sheet.TILE * u
        for k in range(len(ids)):
            tx = x0 + (k % 4) * c
            ty = y0 + (k // 4) * c
            checker(cv, tx, ty, s, s, 4 * u, dark, light)
            if 0 <= ids[k] < sheet.count:
                ox, oy = sheet.tile_origin(ids[k])
                cv.sspr(sheet, ox, oy, sheet.TILE, sheet.TILE,
                        tx + (s - d) // 2, ty + (s - d) // 2, d, d, -1)
        n = self.brush()
        if n in ids:
            k = ids.index(n)
            _ui_draw.cursor(cv, (x0 + (k % 4) * c, y0 + (k // 4) * c, s, s))

    # -- the subclass's ----------------------------------------------------------

    def close_pop(self):
        """The open popover closed."""

    def view_top(self):
        """Whether an up in the view would go past its top."""
        return False


# -- transparency's checker ----------------------------------------------------

_CHECKERS = {}                   # (w, h, s) packed in one int -> the dark squares


# The bytes one array of `bands` may hold. A board's heap finds a free run
# that long anywhere; one array for a whole checker or lattice (20 KB for the
# Sprite tab's sheet) found none on a T-Deck's fragmented heap, and the
# collection that allocation set off cost the frame 140-150 ms.
CHUNK = 2048


def bands(template, n, step):
    """`n` copies of the packed quads `template` (x, y, w, h, colour), the
    k-th moved down by k * `step`, in order, as a list of arrays of at most
    CHUNK bytes (whole copies each, one `fill_rects` an array): each copy a
    slice store and its y fields."""
    L = len(template)
    per = max(1, CHUNK // (2 * L)) if L else 1
    out = []
    k = 0
    while k < n:
        m = min(per, n - k)
        a = array("h", bytes(2 * L * m))
        i = 0
        for _ in range(m):
            a[i:i + L] = template
            if k:
                dy = k * step
                for j in range(i + 1, i + L, 5):
                    a[j] += dy
            i += L
            k += 1
        out.append(a)
    return out


def _checker_quads(w, h, s):
    """The dark squares of a w x h checker in squares of `s`, the first
    row's first square light, band by band (`bands`' arrays): the two bands'
    squares alternate, and the last band is cut to the height left."""
    s2 = 2 * s
    pair = []
    for k in (0, 1):
        for xx in range(s - k * s, w, s2):
            pair += (xx, k * s, s if xx + s <= w else w - xx, s, 0)
    first = 5 * len(range(s, w, s2))                # the first band's length
    second = len(pair) - first
    nb = (h + s - 1) // s
    out = bands(array("h", pair), (nb + 1) // 2, s2)
    odd = nb & 1
    tail = out[-1]
    if odd and second:
        tail = out[-1] = tail[:len(tail) - second]   # the last pair's second band
    last = (nb - 1) * s
    if h - last < s:
        n = len(tail)
        for j in range(n - (first if odd else second) + 3, n, 5):
            tail[j] = h - last
    return out


def checker(cv, x, y, w, h, s, dark, light):
    """Transparency's grey checker over (x, y, w, h) in squares of `s`, the
    first row's first square light (the Sprite tab's grid and swatch, the
    Map's and the Scene's brushes): the light ground, then the dark squares
    in a `fill_rects` an array of quads kept per size."""
    cv.rect(x, y, w, h, light)
    if w <= 0 or h <= 0 or s <= 0:
        return
    for q in checker_quads(w, h, s):
        cv.fill_rects(q, -1, x, y, dark)


def checker_quads(w, h, s):
    """The dark squares of a w x h checker in squares of `s` from (0, 0), as
    `fill_rects` arrays, kept per size: what `checker` draws over its light
    ground."""
    key = (w & 0xFFF) | ((h & 0xFFF) << 12) | ((s & 0x3F) << 24)
    quads = _CHECKERS.get(key)
    if quads is None:
        if len(_CHECKERS) >= 32:
            _CHECKERS.clear()
        quads = _CHECKERS[key] = _checker_quads(w, h, s)
    return quads
