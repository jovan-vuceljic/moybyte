"""The sprite pickers' frames: the pickers are the Art page's popover
(runtime/editors/editor_sprite.py), the size seg over the sheet, a canvas
whose tapped sprite becomes the sprite. On the handheld's full screen the
engine draws the page's frames; inside the desk's Sprite pane the desk
draws the pane alone (its own frames) while the pickers are up.

Each case runs one session on two consoles: one as it ships, its root
presenting one, two or three buffers in turn, and one that draws every
frame whole; every presented picture of the first is held to the second's
bytes, and on the desk the share of its frames that drew the pane alone is
held above a floor (a mechanism that quietly never engages fails)."""

from array import array

import pytest

from runtime import host_app, ui_draw
from runtime import moy_input as mi
from ws_helpers import no_unlock_banner, quiesce

DT = 1 / 30
_NOW = [100000]


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """One clock for both consoles, a frame's worth a frame."""
    import sys
    from runtime import ticks  # noqa: F401 -- loaded, then patched
    for mod in list(sys.modules.values()):
        f = getattr(mod, "__file__", None) or ""
        if "/runtime/" in f.replace("\\", "/") and hasattr(mod, "_ticks_ms"):
            monkeypatch.setattr(mod, "_ticks_ms", lambda: _NOW[0])
    # Pair._drive swaps the toolkit's per-console state between its two
    # consoles, the painted frame's count among it: the test leaves it as it
    # found it, or the next test's console counts its frames from the second
    # console's count, into the frames a record of this test's names
    # (`drew_within`'s, keyed by that count)
    was = (ui_draw._KEYS_HOST[0], list(ui_draw._PAINT), ui_draw._PF[:], ui_draw._EDGE[0],
           ui_draw._WITHIN[:])
    yield
    ui_draw._KEYS_HOST[0] = was[0]
    ui_draw._PAINT[:] = was[1]
    ui_draw._PF[:] = was[2]
    ui_draw._EDGE[0] = was[3]
    ui_draw._WITHIN[:] = was[4]


def _fill(sheet):
    """Every pixel of the sheet a colour, none clear: a sheet that shows
    where it is drawn (a clear sheet would hide a draw past the card)."""
    pix = sheet.pix
    w = sheet.w
    for i in range(len(pix)):
        pix[i] = 1 + (i % w // 3 + i // w // 5) % 15
    sheet.gen += 1


def _console(path, desk, ships):
    if desk:
        ws = host_app.build_workstation(str(path / "carts"), sys_size=(1024, 600),
                                        panel_diagonal_in=7.0, font_scale=1, windowed=True)
    else:
        ws = host_app.build_workstation(str(path / "carts"))
    ws.bar_layer.clock_text = lambda: "10:30"
    no_unlock_banner(ws)
    quiesce(ws)
    if desk:
        ws.home.open_desk()
    ws.open_in_editor(next(c for c in ws.carts.all if c.get("title") == "Star Catcher"))
    drv = host_app.ConsoleDriver(ws)
    for _ in range(3):
        drv.frame(DT)
    ws.took = [False]
    if desk:
        ws.editor_desk.switch("art")
        rows = ws.editor_desk._split_frame

        def own(dt, o, rows=rows, took=ws.took):
            took[0] = drew = ships and rows(dt, o)
            return drew
        ws.editor_desk._split_frame = own
    elif not ships:
        ws.wm.CONTENT_RING = False
    ws.editor_app.set_tab("paint")
    ws.pointer.visible = False
    _fill(ws.paint.sheet)
    ws.paint.n = 37
    for _ in range(3):
        drv.frame(DT)
    ws.paint_layer._open_pickers()
    return ws, drv


class Pair:
    def __init__(self, tmp_path, desk, bufs, settle=True):
        self.desk = desk
        self.a, self.da = _console(tmp_path / "a", desk, True)
        self.b, self.db = _console(tmp_path / "b", desk, False)
        self.bufs = bufs
        self._state = {}
        root = self._root(self.a)
        root.RETAINED_FRAMES = bufs
        self.held = [bytes(root._buf)]
        self.alone = []
        if not settle:
            return
        for _ in range(6):
            self.frame(check=False)
        for _ in range(3):
            self.frame()
        del self.alone[:]

    def _root(self, ws):
        return ws.wm.root_canvas if self.desk else ws.sys_canvas

    def _drive(self, ws, drv):
        """One loop pass of `ws` with the toolkit's per-console state its
        own, as on a board with one console."""
        st = self._state.setdefault(id(ws), [None, [-1, False, None] + [-1] * (
            len(ui_draw._PAINT) - 3), False, ui_draw._PF[:], [-1, 0, 0, 0, 0]])
        ui_draw._KEYS_HOST[0] = st[0]
        ui_draw._PAINT[:] = st[1]
        ui_draw._PF[:] = st[3]
        ui_draw._EDGE[0] = st[2]
        ui_draw._WITHIN[:] = array("i", st[4])
        try:
            ws.mark_dirty()
            drv.frame(DT)
        finally:
            st[0] = ui_draw._KEYS_HOST[0]
            st[1] = list(ui_draw._PAINT)
            st[3] = ui_draw._PF[:]
            st[2] = ui_draw._EDGE[0]
            st[4] = list(ui_draw._WITHIN)

    def frame(self, check=True):
        _NOW[0] += 33
        a, b = self.a, self.b
        n = a.frame_state.frames_drawn
        a.took[0] = False
        self._drive(a, self.da)
        self._drive(b, self.db)
        if a.frame_state.frames_drawn == n:
            return
        root = self._root(a)
        shot = bytes(root._buf)
        if check:
            want = bytes(self._root(b)._buf)
            if shot != want:
                w = root.w
                px = [i // 2 for i in range(0, len(shot), 2) if shot[i:i + 2] != want[i:i + 2]]
                xs = [q % w for q in px]
                ys = [q // w for q in px]
                raise AssertionError("frame %d (%d buffers) differs from a whole draw in "
                                     "x %d-%d, y %d-%d" % (a.frame_state.frames_drawn, self.bufs, min(xs),
                                                           max(xs), min(ys), max(ys)))
        self.alone.append(a.took[0])
        self.held.append(shot)
        if self.bufs > 1:
            root._comp.last = shot
            root._buf[:] = (self.held[-self.bufs] if len(self.held) > self.bufs
                            else self.held[0])
        del self.held[:-self.bufs]

    def both(self, verb, *args):
        getattr(self.da, verb)(*args)
        getattr(self.db, verb)(*args)

    def key(self, code, n=1, held=1):
        for _ in range(n):
            self.both("key_down", code)
            for _ in range(held):
                self.frame()
            self.both("key_up", code)
            self.frame()
            self.frame()

    def drag(self, x, y0, dy, steps=6, rest=4):
        self.both("touch", x, y0)
        self.frame()
        for i in range(1, steps + 1):
            self.both("touch_drag", x, y0 + dy * i // steps)
            self.frame()
        self.both("touch_up")
        for _ in range(rest):
            self.frame()

    def body(self):
        """The pickers' sheet on the glass."""
        x0, y0, x1, y1 = self.a.paint_layer.sheet_shown
        x, y = x0, y0
        if self.desk:
            own = self.a.editor_desk._own_pane()
            assert own is not None and own[0] == "paint"
            content = self.a.wm.windows["menu"].content_rect()
            x += own[4][0] + content[0]
            y += own[4][1] + content[1]
        return x, y, x1 - x0, y1 - y0

    def share(self):
        return sum(self.alone) / max(1, len(self.alone))


def _session(p):
    p.key(mi.KEY_RIGHT, 2)
    p.key(mi.KEY_LEFT, 1, held=20)
    p.key(mi.KEY_DOWN, 4)
    p.key(mi.KEY_UP, 2)
    p.key(mi.KEY_DOWN, 1, held=20)


@pytest.mark.parametrize("bufs", (1, 2, 3))
@pytest.mark.parametrize("desk", (False, True), ids=("handheld", "desk"))
def test_the_pickers_frames_draw_as_a_whole_draw_does(tmp_path, desk, bufs):
    p = Pair(tmp_path, desk, bufs)
    _session(p)
    assert p.a.paint_layer._pop == "pickers"
    if desk:
        assert p.share() > 0.6, p.alone


@pytest.mark.parametrize("desk", (False, True), ids=("handheld", "desk"))
def test_a_size_picked_and_a_sprite_tapped_draw_the_page_again(tmp_path, desk):
    """The size seg changes the page under the pickers and a tapped sprite
    closes them: each draws what a whole draw does."""
    p = Pair(tmp_path, desk, 2)
    p.key(mi.KEY_RIGHT)
    assert p.a.paint.size == p.b.paint.size != 1
    x, y, w, h = p.body()
    p.both("touch", x + w // 2, y + h // 2)
    p.frame()
    p.both("touch_up")
    for _ in range(4):
        p.frame()
    assert not p.a.paint_layer._pop
    assert p.a.paint.n == p.b.paint.n != 37


@pytest.mark.parametrize("desk", (False, True), ids=("handheld", "desk"))
def test_the_sheet_draws_inside_the_pickers_card(tmp_path, desk):
    """The sheet's canvas lies inside the pickers' card, and its blit
    inside its canvas."""
    p = Pair(tmp_path, desk, 2)
    pl = p.a.paint_layer
    x0, y0, x1, y1 = pl.sheet_shown
    cx, cy, cw, ch = pl._host.box("pick_pop")
    assert cx <= x0 < x1 <= cx + cw and cy <= y0 < y1 <= cy + ch, (pl.sheet_shown, (cx, cy, cw, ch))


def test_a_sheet_taller_than_the_room_scrolls_under_a_drag(tmp_path):
    """The handheld's pickers show the rows of a tall sheet that fit; a
    drag up the sheet shows the rows below, and a tap there picks the
    sprite it shows, every frame as a whole draw does."""
    p = Pair(tmp_path, False, 2)
    pl = p.a.paint_layer
    sheet = p.a.paint.sheet
    fit = pl._sheet_fit
    assert fit < sheet.rows, "the sheet fits the handheld's room"
    x, y, w, h = p.body()
    first = pl._sheet_first
    tile = sheet.TILE * pl._sheet_geom(sheet)[0]
    p.drag(x + w // 2, y + h - 4, -(h - 8))
    assert pl._sheet_first > first and pl._pop == "pickers"
    m = 2 * pl.layout.fs
    p.both("touch", x + m + tile // 2, y + m + tile // 2)
    p.frame()
    p.both("touch_up")
    for _ in range(4):
        p.frame()
    assert p.a.paint.n == pl._sheet_first * sheet.cols == p.b.paint.n
    assert not pl._pop
