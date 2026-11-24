# Map (grep -n a name to jump there):
#   _zoom_word                    a zoom as the bar and the seg say it
#   fill                          the page's states from the layer's fields
#   build                         the page: tools, rail or desk row and panel, canvas, popovers
#   PaintAppLayout                the content rect and the drawing's view in it
#   PaintAppLayer                 the Paint app: the drawing, its tools and its pages
#   PaintAppLayer.handle_input    the keys: a popover's the page's, else the drawing's
#   PaintAppLayer._canvas_keys    the drawing's keys: the tools, the cursor, the verbs
#   PaintAppLayer.handle_pointer  a press on the drawing and its drag, else the page's
#   PaintAppLayer.draw            the frame: a stroke frame, else the page whole
#   PaintAppLayer.retained        the WM's word on a window draw's target (and `changed`)
#   -- Viewer and the draw half   paint_viewer's Viewer; paint_draw's PaintDraw, the first base
"""Paint: a `uitree` page round a drawing (the look's
docs/media/look_2026-10/APPS_RESTYLE.md, Paint). The page draws everything
but the drawing, which is its `view` canvas; a frame that changed nothing
but a mark repaints only the part of the view it changed (`paint_draw`'s
stroke frame).

The canvas, in the order a kid meets it:

  THE CANVAS   eight tools as toggles, the one in use current -- Pencil,
               Brush, Eraser, Fill, Shape (a line, a box or an oval, cycling
               on a repeat tap), Spray, Pick (a dropper whose drip is the
               colour under the cursor) and Move -- the drawing in its view,
               and the colours: on a handheld a rail of the colour in use,
               the page of sixteen that holds it, the brush (its dot the
               brush's own width) and More; on the desk all 64 and the
               sizes beside the drawing. The arrows move the ring cursor,
               Enter or `a` draws; Space held moves the drawing. On the
               handheld the bar carries undo, redo and the zoom (Z: 1x, 2x,
               4x, Fit); on the desk the window's tool row does, with the
               drawing's verbs.
  MORE         New drawing (N, the board's size: 1024 x 600 on a desk,
               320 x 240 on a handheld; the desk adds a game-size one), Open...
               (O: My Art), Use as wallpaper (W), Put in a game... (G, a
               320 x 240 drawing only), Put in a story... (T) and Show (V).
  A DESK'S DRAWING ON A HANDHELD  opens to look at (the bar's title, the
               zoom, More): Fit is a quarter, Z steps through a half, 1x and
               2x, the arrows pan and a sixteenth of the whole shows where
               the view is. Drawing on it answers with a toast.

Autosave (#108): a drawing persists on an idle debounce, a kid never saves;
the first save of a new drawing says its name in a toast.
"""

import ui_font as _ui_font
import uitree as ui
import uitree_app
from layout_base import bar_rows, content_of, ground_round, metric_class, window_foot, DESK
from artwork import PaintDocument, DESK_W, DESK_H, GAME_W, GAME_H, colour_name
from ticks import _ticks_ms, _ticks_diff
from drawing_pages import GamePage, StoryPage, shown, stories_here, dot as _dot


# The tools, in their order: (icon, key, word). Shape's icon is the shape in use.
TOOLS = (("pencil", "P", "Pencil"), ("paint", "B", "Brush"), ("eraser", "E", "Eraser"),
         ("bucket", "F", "Fill"), ("rect", "S", "Shape"), ("spray", "A", "Spray"),
         ("picker", "I", "Pick"), ("pan", "Space", "Move"))
PENCIL, BRUSH, ERASER, FILL, SHAPE, SPRAY, PICK, MOVE = range(8)
TOOL_IDS = ("pencil", "brush", "eraser", "fill", "shape", "spray", "pick", "move")
SHAPES = (("line", "Line"), ("rect", "Rect"), ("oval", "Oval"))
# A tool's key, typed: the tool (a repeat on the tool in use opens the brush).
_TOOL_KEYS = {ord("p"): PENCIL, ord("b"): BRUSH, ord("e"): ERASER, ord("f"): FILL,
              ord("s"): SHAPE, ord("a"): SPRAY, ord("i"): PICK}
# The verbs' keys, typed.
KEYS = {ord("c"): "colours", ord("m"): "more", ord("z"): "zoom", ord("n"): "new",
        ord("o"): "open", ord("w"): "wallpaper", ord("g"): "game", ord("v"): "show",
        ord("t"): "story", 0x1A: "undo", 0x19: "redo", 0x04: "dup"}
SPACE = 0x20
# The brush's widths: a desk drawing's and a game-size one's.
SIZES_DESK = (2, 4, 8, 16)
SIZES_GAME = (1, 2, 4)
# The zooms, as quarters of a pixel a drawing pixel takes: 1/4, 1/2, 1, 2, 4.
FIT = 0
ZOOM_EDIT = (4, 8, 16, FIT)              # Z on a drawing one draws on
ZOOM_VIEW = (FIT, 2, 4, 8)               # Z on a desk's drawing a handheld views
ZOOM_SEG = (FIT, 4, 8, 16)               # the desk's segments: Fit, 1x, 2x, 4x
TOAST_MS = 2000
AUTOSAVE_S = 2.5
RETRY_S = 30.0                           # a failing store retries slowly, not hot


def _zoom_word(q):
    """A zoom in quarters as the bar and the seg say it."""
    if q == 1:
        return "¼" if _ui_font.print_symbols() else "1/4"
    if q == 2:
        return "½" if _ui_font.print_symbols() else "1/2"
    return "%d%s" % (q // 4, "×" if _ui_font.print_symbols() else "x")


# -- the page ---------------------------------------------------------------------
#
# Everything around the drawing is the page's: the tools, the rail or the
# desk's row and panel, the popovers, More, the toast. The drawing itself is
# the `view` canvas (`PaintDraw._view`), whose draw the stroke frame repeats
# alone where only a mark changed.

s = ui.state(
    mode=ui.enum("draw", "view", "show", init="draw"),    # the canvas, a desk's drawing viewed, Show
    draw=True,                  # ...the canvas
    tool=ui.enum(*TOOL_IDS, init="pencil"),
    shape_icon="rect",
    use_c=12,                   # the colour in use's tile
    rail_c=12,                  # ...the rail's sixteen, from rail_first
    rail_first=0,
    panel_c=12,                 # ...the desk panel's 64
    pop_c=12,                   # ...the colours popover's, from pop_first, pop_n of them
    pop_first=0,
    pop_n=64,
    cpage=ui.enum("p1", "p2", "p3", init="p1"),          # the colours' page under touch
    colour_word="",
    tool_word="Pencil",
    sizes=ui.model(key="id", id="", word=""),
    size_cur=ui.row_of("sizes"),
    shape_cur=ui.enum("line", "rect", "oval", init="rect"),
    fill_cur=ui.enum("outline", "filled", init="outline"),
    # the brush popover's own three, for the desk shows the panel's beside it
    pop_size=ui.row_of("sizes"),
    pop_shape=ui.enum("line", "rect", "oval", init="rect"),
    pop_fill=ui.enum("outline", "filled", init="outline"),
    zooms=ui.model(key="id", id="", word=""),
    zoom_cur=ui.row_of("zooms"),
    pop=ui.enum("none", "colours", "brush", "more", init="none"),
    touch=False,
    desk=False,
    pop_w=162,                  # the colours popover: its width, its cells' columns and side
    pop_cols=8,
    pop_side=18,
    pop_at="",                  # where the open popover hangs: "X Y W H" on the glass, "" its anchor
    look_h=0,                   # the viewed drawing's canvas, and its caption under it at Fit
    cap="",
    lead="",                    # the band's words before its keys
    can_undo=False,
    can_redo=False,
    viewing=False,              # a desk's drawing, looked at
    lends=False,                # the bar's row after its title: a handheld's drawing or view
    zoom_word="",               # ...its zoom
    copy_ok=False,              # a show-only picture: Copy to My Art
    game_ok=False,              # a 320 x 240 drawing: Put in a game
    story_ok=False,
    view=0,                     # moves where the view's drawing does outside a stroke frame
    toasting=False,
    toast="",
    toast_icon="check",
)
ui.app("Paint", icon="paint")
ui.labels("SHAPES", {"line": "Line", "rect": "Rect", "oval": "Oval"})
ui.labels("FILLS", {"outline": "Outline", "filled": "Filled"})
ui.labels("CPAGES", {"p1": "1-28", "p2": "29-56", "p3": "57-64"})


def _lay():
    """The app's Layer, which a handler's run owes a fill."""
    lay = uitree_app.env()
    lay.fill_owed = True
    return lay


# The states the row lent to the bar reads: a write moves the bar's zone.
_BAR_READS = ("lends", "viewing", "can_undo", "can_redo", "zoom_word")


def _set(lay, name, value):
    """State `name` written only where it moved."""
    if lay.shown.get(name) != value:
        lay.shown[name] = value
        setattr(s, name, value)
        if name in _BAR_READS:
            lay.zone_gen += 1


def _words(lay, name, rows):
    """Model `name`'s rows, (id, word) each, written where they moved."""
    if lay.shown.get(name) != rows:
        lay.shown[name] = rows
        setattr(s, name, [{"id": i, "word": w} for i, w in rows])


def fill(lay):
    """The page's states from the layer's fields."""
    d = lay._doc
    v = lay.viewer
    _set(lay, "mode", "show" if lay.page == "show" else "view" if v is not None else "draw")
    _set(lay, "viewing", v is not None)
    _set(lay, "draw", s.mode == "draw")
    t = lay.tool
    _set(lay, "tool", TOOL_IDS[t])
    _set(lay, "tool_word", TOOLS[t][2])
    _set(lay, "shape_icon", SHAPES[lay.shape][0])
    c = lay.color
    for name in ("use_c", "rail_c", "panel_c"):
        _set(lay, name, c)
    _set(lay, "rail_first", (c // 16) * 16)
    pop = lay.pop or "none"
    if pop == "colours" and lay.pop_was != "colours":
        if lay.layout.touch:
            _set(lay, "cpage", ("p1", "p2", "p3")[min(2, c // 28)])
        _set(lay, "pop_c", c)
    if pop == "none" and lay.pop_was not in (None, "none") and s.mode == "draw":
        ui.focus("view")            # back on the drawing, whose keys the arrows are
    lay.pop_was = pop
    if lay.layout.touch:
        first = ("p1", "p2", "p3").index(s.cpage) * 28
        _set(lay, "pop_first", first)
        _set(lay, "pop_n", min(28, 64 - first))
    _set(lay, "colour_word", colour_name(s.pop_c if pop == "colours" else c, _dot()))
    _set(lay, "pop", pop)
    touch = bool(lay.layout.touch)
    _set(lay, "touch", touch)
    _set(lay, "desk", bool(lay.layout.desk))
    _set(lay, "pop_w", 190 if lay.layout.desk else 260 if touch else 176)
    _set(lay, "pop_cols", 7 if touch else 8)
    _set(lay, "pop_side", 32 if touch else 18)
    _set(lay, "pop_at", lay._pop_at())
    h, cap = lay._look_h()
    _set(lay, "look_h", h)
    _set(lay, "cap", cap)
    _words(lay, "sizes", tuple((str(i), str(w)) for i, w in enumerate(lay.sizes())))
    for k in ("size_cur", "pop_size"):
        _set(lay, k, str(min(lay.size_i, len(lay.sizes()) - 1)))
    for k in ("shape_cur", "pop_shape"):
        _set(lay, k, SHAPES[lay.shape][0])
    for k in ("fill_cur", "pop_fill"):
        _set(lay, k, "filled" if lay.shape_fill else "outline")
    _words(lay, "zooms", tuple((str(i), _zoom_word(z) if z else "Fit") for i, z in enumerate(ZOOM_SEG)))
    _set(lay, "zoom_cur", str(ZOOM_SEG.index(lay.zoom) if lay.zoom in ZOOM_SEG else 0))
    _set(lay, "lends", not lay.layout.desk and lay.page is None)
    _set(lay, "zoom_word", _zoom_word(v.quarters()) if v is not None else
         _zoom_word(lay._quarters()) if d is not None else "")
    _set(lay, "can_undo", d is not None and v is None and bool(d.history))
    _set(lay, "can_redo", d is not None and v is None and bool(d.future))
    art = lay._art
    _set(lay, "copy_ok", v is None and not art.editable())
    _set(lay, "game_ok", v is None and d is not None and (d.W, d.H) == (GAME_W, GAME_H))
    _set(lay, "story_ok", v is not None or lay.layout.desk)
    _set(lay, "lead", lay._lead())
    _set(lay, "view", lay._view_n)
    toast = lay.toast
    _set(lay, "toasting", toast is not None)
    if toast is not None:
        _set(lay, "toast", toast[0])
        _set(lay, "toast_icon", toast[1])


def opened():
    lay = _lay()
    fill(lay)
    ui.focus("view" if s.mode == "draw" else "look" if s.mode == "view" else "show")


def _verb(verb):
    def press():
        _lay()._verb(verb)
    return press


def _tool(i):
    def press():
        _lay()._pick_tool(i)
    return press


def close_pop():
    lay = _lay()
    lay.pop = None
    lay._damage.all()


def use_moved():
    pass


def rail_moved():
    _lay()._take(s.rail_c)


def panel_moved():
    _lay()._take(s.panel_c)


def pop_moved():
    lay = _lay()
    lay.shown["pop_c"] = s.pop_c


def pop_picked():
    lay = _lay()
    lay._take(s.pop_c)
    lay.pop = None


def cpage_moved():
    lay = _lay()
    first = ("p1", "p2", "p3").index(s.cpage) * 28
    lay.shown["cpage"] = s.cpage
    _set(lay, "pop_c", first)


def _size(v):
    lay = _lay()
    lay.size_i = int(v)
    lay._damage.all()


def _shape(v):
    lay = _lay()
    lay.shape = ("line", "rect", "oval").index(v)
    lay._damage.all()


def _fill(v):
    lay = _lay()
    lay.shape_fill = v == "filled"
    lay._damage.all()


def zoom_moved():
    lay = _lay()
    lay._zoom_to(ZOOM_SEG[int(s.zoom_cur)])


def view_keys(i):
    """The canvas's keys while the drawing holds focus: the tools, the
    verbs, the cursor."""
    return uitree_app.env()._canvas_keys(i)


def draw_view(cv, x, y, w, h):
    lay = uitree_app.env()
    lay._draw_view(cv, x, y, w, h)


ui.hook("opened", opened)
for _i in range(8):
    ui.action("t_" + TOOL_IDS[_i], TOOLS[_i][2] + "\t" + TOOLS[_i][1], _tool(_i), icon=TOOLS[_i][0])
ui.action("undo", "Undo\tCtrl Z", _verb("undo"), icon="undo", hint="Undo", when="can_undo", off="grey")
ui.action("redo", "Redo\tCtrl Y", _verb("redo"), icon="redo", when="can_redo", off="grey")
ui.action("new", "New drawing\tN", _verb("new"), icon="new")
ui.action("new_game", "New game-size drawing (320x240)", _verb("new_game"), icon="new")
ui.action("open", "Open" + "...\tO", _verb("open"), icon="folder_open")
ui.action("copy", "Copy to My Art", _verb("copy"), icon="dup")
ui.action("wallpaper", "Wallpaper", _verb("wallpaper"), icon="wallpaper")
ui.action("game", "Put in a game...", _verb("game"), icon="export")
ui.action("story", "Put in a story", _verb("story"), icon="storybook")
ui.action("show", "Show", _verb("show"), icon="maximize")
ui.action("colours", "Colours", _verb("colours"), keys=("c",), hint="Colours", when="draw",
          off="hide")
ui.action("brush", "Brush", _verb("brush"), icon="brush")
ui.action("more", "More\tM", _verb("more"), icon="more", keys=("m",), hint="More")
ui.action("zoom", "Zoom", _verb("zoom"), keys=("z",), hint="Zoom")
ui.action("close_pop", "Close", close_pop)
ui.hook("use_moved", use_moved)
ui.hook("rail_moved", rail_moved)
ui.hook("panel_moved", panel_moved)
ui.hook("pop_moved", pop_moved)
ui.hook("pop_picked", pop_picked)
ui.hook("cpage_moved", cpage_moved)
ui.hook("size_moved", lambda: _size(s.size_cur))
ui.hook("shape_moved", lambda: _shape(s.shape_cur))
ui.hook("fill_moved", lambda: _fill(s.fill_cur))
ui.hook("pop_size_moved", lambda: _size(s.pop_size))
ui.hook("pop_shape_moved", lambda: _shape(s.pop_shape))
ui.hook("pop_fill_moved", lambda: _fill(s.pop_fill))
ui.hook("zoom_moved", zoom_moved)


def _tools(pitch, cols=1):
    with ui.grid(cols, 8 // cols, h=pitch, gap="0"):
        for i in range(8):
            ui.button("t_" + TOOL_IDS[i], icon="{shape_icon}" if i == SHAPE else TOOLS[i][0],
                      alone=True, kind="bar", marked="tool=" + TOOL_IDS[i])


def _view_canvas():
    ui.canvas("view", draw_view, keys=view_keys, reads=["view"], hint="Draw", mark=False)


def _rail():
    """A handheld's colours: the colour in use, its sixteen, the brush, More."""
    with ui.split("col", sizes=(27, 102, 26, 26, "1*"), gap="0", pad="0"):
        ui.cells("use_c", first="{use_c}", count=1, cols=1, side=24, edge=True, pick="colours")
        ui.cells("rail_c", first="{rail_first}", count=16, cols=2, side=12, edge=True,
                 on="rail_moved")
        ui.button("brush", alone=True, kind="bar", marked="pop=brush")
        ui.button("more", alone=True, kind="bar", marked="pop=more")
        ui.label("")


def _panel():
    """The desk's colours and the tool's sizes beside the drawing."""
    with ui.split("col", sizes=(20, 34, 206, 22, 32, 32, 32, "1*"), gap="0", pad="0"):
        ui.label("Colour", tone="dim", face="caption")
        with ui.split("row", sizes=(56, "1*"), gap="0", pad="0"):
            ui.cells("use_c", first="{use_c}", count=1, cols=1, side=28, pick="colours")
            ui.label("{colour_word}")
        ui.cells("panel_c", first=0, count=64, cols=8, side=25, gap=2, on="panel_moved")
        ui.label("{tool_word}", tone="dim", face="caption")
        ui.seg("Size", "size_cur", text="{.word}", on="size_moved")
        ui.seg("Shape", "shape_cur", labels="SHAPES", on="shape_moved", shown="tool=shape")
        ui.seg("Fill", "fill_cur", labels="FILLS", on="fill_moved", shown="tool=shape")
        ui.label("")


def _desk_row():
    with ui.split("row", sizes=(172, 180, "1*", 424), gap="s", pad="0"):
        with ui.row("row_verbs", pad=6, gap=8):
            ui.button("new", alone=True, kind="bar")
            ui.button("open", alone=True, kind="bar")
            ui.rule()
            ui.button("undo", alone=True, kind="bar")
            ui.button("redo", alone=True, kind="bar")
        ui.seg("", "zoom_cur", text="{.word}", on="zoom_moved")
        ui.label("")
        with ui.row("row_end", gap=8):
            ui.label("")
            ui.button("show")
            ui.button("wallpaper")
            ui.button("story")
            ui.button("more", alone=True, kind="bar", marked="pop=more")


def _draw_desk():
    with ui.split("col", sizes=(36, "1*"), gap="s", pad="s", rule=True, shown="draw && desk"):
        _desk_row()
        with ui.split("row", sizes=(44, "1*", 244), gap="s", pad="0"):
            _tools(44)
            _view_canvas()
            _panel()


def _draw_handheld():
    with ui.split("row", sizes=(26, "1*", 28), gap="s", pad="0", shown="draw && !desk && !touch"):
        _tools(23)
        _view_canvas()
        _rail()


def _draw_touch():
    """A handheld under a finger: the tools two by four, the colour in use
    and the brush side by side under them, More, and the drawing."""
    with ui.split("row", sizes=(64, "1*"), gap="s", pad="0", shown="draw && !desk && touch"):
        with ui.split("col", sizes=(128, 34, 34, "1*"), gap="s", pad="0"):
            _tools(32, 2)
            with ui.split("row", sizes=(32, 32), gap="0", pad="0"):
                ui.cells("use_c", first="{use_c}", count=1, cols=1, side=28, edge=True,
                         pick="colours")
                ui.button("brush", alone=True, kind="bar", marked="pop=brush")
            ui.button("more", alone=True, kind="bar", marked="pop=more")
            ui.label("")
        _view_canvas()


def _view():
    ui.canvas("look", draw_view, keys=view_keys, reads=["view"], mark=False,
              h="{look_h}", shown="mode=view")
    ui.label("{cap}", tone="dim", face="caption", align="center", shown="mode=view && cap")


def _show():
    ui.canvas("show", draw_view, keys=view_keys, reads=["view"], mark=False,
              h="{look_h}", shown="mode=show")


def _pops():
    with ui.popover("colours_pop", anchor="use_c", at="{pop_at}", shown="pop=colours", close="close_pop",
                    w="{pop_w}"):
        with ui.row("colours_head", pad=4):
            ui.label("Colour", face="title")
            ui.label("{colour_word}", tone="dim", face="caption", align="end")
        ui.cells("pop_c", first="{pop_first}", count="{pop_n}", cols="{pop_cols}",
                 side="{pop_side}", gap=2, edge=True, on="pop_moved", pick="pop_picked")
        ui.seg("", "cpage", labels="CPAGES", on="cpage_moved", shown="touch")
    with ui.popover("brush_pop", anchor="brush", at="{pop_at}", shown="pop=brush", close="close_pop", w=194):
        ui.label("{tool_word}", face="title")
        ui.seg("Size", "pop_size", text="{.word}", on="pop_size_moved")
        ui.seg("Shape", "pop_shape", labels="SHAPES", on="pop_shape_moved", shown="tool=shape")
        ui.seg("Fill", "pop_fill", labels="FILLS", on="pop_fill_moved", shown="tool=shape")
    with ui.popover("more_pop", anchor="more", at="{pop_at}", shown="pop=more", close="close_pop",
                    w="{@desk?300:182}"):
        with ui.menu(""):
            ui.item("new", label="New drawing\tN", shown="!viewing")
            ui.item("new_game", label="New game-size drawing (320x240)", shown="@desk && !viewing")
            ui.item("open", label="Open...\tO")
        with ui.menu(""):
            ui.item("copy", shown="copy_ok")
            ui.item("wallpaper", label="Use as wallpaper\tW")
            ui.item("game", label="Put in a game...\tG", shown="game_ok")
            ui.item("story", label="Put in a story...\tT", shown="story_ok")
            ui.item("show", label="Show\tV")


def build():
    with ui.page("", status="{lead}"):
        _draw_desk()
        _draw_handheld()
        _draw_touch()
        _view()
        _show()
        _pops()
        ui.toast("{toast}", icon="{toast_icon}", shown="toasting")
        with ui.tools("bar", lend="bar", shown="lends"):
            ui.button("undo", icon="undo", alone=True, shown="!viewing")
            ui.button("redo", icon="redo", alone=True, shown="!viewing")
            ui.button("zoom", label="{zoom_word}", icon="search")
            ui.button("more", icon="more", alone=True, shown="viewing")


class PaintAppLayout:
    """Paint's glass: the content rect, whether it is a desk's or a
    handheld's (under touch, `touch`), and `view`, the drawing's rect --
    where the page laid the `view` canvas out at its last draw, and before
    the first a rect of about its size, so a drawing opens centred."""

    MIN_W = 310
    MIN_H = 230

    def __init__(self, w, h, fs=1, windowed=False, cs=None, touch=False):
        self.w = int(w)
        self.h = int(h)
        self.fs = fs = max(1, int(fs))
        self.cs = max(fs, int(cs)) if cs else fs
        self.windowed = bool(windowed)
        self.desk = metric_class() == DESK
        self.touch = bool(touch) and not self.desk
        self.cx, self.cy, self.cw, self.ch = content_of(
            self.w, self.h, 0 if windowed else bar_rows(self.cs))
        cx, cy, cw, ch = self.cx, self.cy, self.cw, self.ch
        self.full = (cx, cy, cw, ch)
        self.page = (cx, cy, cw, ch)
        u = fs
        if self.desk:
            under = window_foot() if self.windowed else 0
            self.view = (cx + 68, cy + 62, cw - 68 - 264, ch - 62 - 44 + under)
            self.radius = 0
        elif self.touch:
            self.view = (cx + 68 * u, cy + 2 * u, cw - 72 * u, ch - 6 * u)
            self.radius = 6 * u
        else:
            self.view = (cx + 32 * u, cy + 3 * u, cw - 64 * u, ch - 28 * u)
            self.radius = 6 * u


def _grow(c, x0, y0, x1, y1):
    """Rect `c` [x0, y0, x1, y1) grown over another; an empty one adds
    nothing."""
    if x1 <= x0 or y1 <= y0:
        return
    if x0 < c[0]:
        c[0] = x0
    if y0 < c[1]:
        c[1] = y0
    if x1 > c[2]:
        c[2] = x1
    if y1 > c[3]:
        c[3] = y1


class _Damage:
    """Paint's damage role: `all` and `again` as the role's, each counted in
    `gen` and owing the page a fill; `mark` asks for a frame whose only
    change is a mark's -- the doc's pixels and a shape's outline -- which the
    stroke frame paints alone; `settle` asks, from a draw, for one more frame
    of the same page."""

    def __init__(self, role, lay):
        self._role = role
        self._lay = lay
        self.gen = 0

    def all(self):
        self.gen += 1
        self._lay.fill_owed = True
        self._role.all()

    def again(self):
        self.gen += 1
        self._lay.fill_owed = True
        self._role.again()

    def mark(self):
        self._role.all()

    def settle(self):
        self._role.again()


# The most physical buffers a canvas rotates through (the scroll's paint ring
# says the same of its own): a stroke frame needs that many paints of the
# same page behind it, and the ring keeps one more, the frame in hand.
_RING = 3


# Viewer and the draw half live in modules of their own (paint_viewer,
# paint_draw), which take this module's constants at their foot: imported
# here, after those are bound.
from paint_viewer import Viewer
from paint_draw import PaintDraw


class PaintAppLayer(PaintDraw, uitree_app.app_layer("artwork", "Paint", build)):
    """The Paint app: the page (`build`) round the drawing, the drawing's
    tools and colours, More's verbs, and a desk's drawing viewed on a
    handheld."""

    id = "artwork"
    TITLE = "Paint"
    LENDS_BAR = True
    # The WM's shown protocol (docs/surface_model_v1.md §14.3): `retained`
    # before a window draw, `changed` after it.
    HELD = True
    AUTOSAVE_S = AUTOSAVE_S
    RETRY_S = RETRY_S

    def __init__(self, ctx, names, service):
        """`ctx` carries the roles its declaration needs (its manifest's
        `needs`: its document model's, its copies' and My Art's door) under
        the prefs namespace `paint`, whose `paint_doc` and `paint_doc_kind`
        rows the artwork role's C rows read (native/moy_app's
        MOY_APP_ARTWORK_NS); `service` is its document model, the console's
        (`ArtworkService`, built over `ctx` at boot)."""
        uitree_app.App.__init__(self, ctx, names)
        self.engine.env = self
        self.shown = {}               # each state as last written (`_set`)
        self.fill_owed = True
        self.pop_was = None           # the popover the last fill saw open
        self._damage = _Damage(ctx.damage, self)
        self._nav = ctx.nav
        self._ui = ctx.ui
        self._art = self.service = service
        self._art.on_leave = self._leaving
        self.names = names
        cv = ctx.surface.canvas()
        self.layout = PaintAppLayout(cv.w, cv.h, self._surf.font_scale(),
                                  self._surf.windowed(), self._surf.chrome_scale())
        self._touch = None            # the input at open: None until the first frame
        # The document is built at the app's first use of it (`doc`), not at
        # the console's start: a session that never opens Paint pays nothing.
        self._doc = None
        self._starter_pending = self.layout.desk
        self.tool = PENCIL
        self.shape = 1                # SHAPES: a box until a repeat tap moves it on
        self.shape_fill = False
        self.color = names["blue"]
        self.size_i = 1
        self.zoom = 4                 # quarters, FIT the largest of 1x, 1/2, 1/4 that fits
        self.pan = [0, 0]             # the view's top left, in drawing pixels
        self.cur = [0, 0]             # the cursor, in drawing pixels
        self.mark = None              # where the last mark was made
        self.pop = None               # the popover open: colours | brush | more
        self.page = None              # a page over the canvas: game | story | show
        self.viewer = None            # a desk's drawing, looked at
        self.toast = None             # (text, icon, until ms, undo or None)
        self.game = None
        self.story = None
        self._stroke = None           # the last drawing pixel a stroke reached
        self._shape0 = None           # a shape's first corner, while it is dragged
        self._shape1 = None
        self._down = False            # the pointer pressed on the drawing
        self._panning = None          # (x, y) a Move drag last stood at
        self._held = 0                # frames an arrow has been held
        self._space = False
        self._drawing_key = False     # `a` held, drawing at the cursor
        self._rng = 0x5EED123
        self._unsaved = False
        self._idle = 0.0
        self._first_save = False      # the drawing has never been written
        self._opened = None           # the doc pointer the open drawing was opened at
        # The stroke frame (`_stroke_frame`): the paints behind it, each
        # [frame, epoch, x0, y0, x1, y1) the glass its marks changed; the
        # canvas they went to; the page's signature and its epoch; and last
        # frame's shape outline and pointer sprite, which a frame repaints
        # where they stood.
        self._ring = [[-1, -1, 0, 0, 0, 0] for _i in range(_RING + 1)]
        self._ring_cv = None
        self._sig = [None] * 20
        self._epoch = 0
        self._gen = -1
        self._chg = [0, 0, 0, 0]
        self._spec_l = [0] * 9
        self._src = [0, 0, 0, 0]
        self._hole = [0, 0, 0, 0, 0]
        self._own = [0, 0, 0, 0]
        self._clip_r = None
        self._pv = [0, 0, 0, 0]
        self._sp = [0, 0, 0, 0]
        self._sp_out = False
        self._cu = [0, 0, 0, 0]
        self._drip_c = 0
        # The window's word on the target of the next draw (`retained`):
        # [known, x0, y0, x1, y1), whether the WM said it, and whether the
        # draw before was one it said it of; and this draw's change, read by
        # `changed`.
        self._word = [0, 0, 0, 0, 0]
        self._held_on = False
        self._held_last = False
        self._moved = True
        self._said = False            # this draw's target is the one the WM said
        self._sf_ran = False          # the last draw weighed a stroke frame
        self._changed = False
        self._undo_seen = 0           # the undo and redo the page last showed
        self._drip_seen = -1          # the colour under the cursor the band last said
        self._view_n = 0              # the whole frames drawn: the view canvas's reads= state
        self._page_down = False       # a press the page took is held: its frames are whole

    # -- the document ------------------------------------------------------------

    @property
    def doc(self):
        d = self._doc
        if d is None:
            d = self._doc = PaintDocument(*self._board_size())
        return d

    @doc.setter
    def doc(self, d):
        old = self._doc
        self._doc = d
        if old is not None and old is not d:
            old.release()             # its bakes went back first (_return_bakes)

    def _pixels_for(self, w, h):
        """The document's own pixels at w x h, minted at that size where it
        is another: what the open drawing is read straight into."""
        d = self._doc
        if d is None or d.W != w or d.H != h:
            self.doc = d = PaintDocument(w, h)
        return d.pix

    def _board_size(self):
        """The drawings this board makes: a desk board's, else a handheld's."""
        return (DESK_W, DESK_H) if metric_class() == DESK else (GAME_W, GAME_H)

    def sizes(self):
        """The brush's widths for the open drawing's size."""
        d = self._doc
        if d is not None and (d.W > GAME_W or d.H > GAME_H):
            return SIZES_DESK
        return SIZES_GAME

    def size(self):
        s = self.sizes()
        return s[min(self.size_i, len(s) - 1)]

    def relayout(self, w, h, fs, cs=None):
        self.layout = PaintAppLayout(w, h, fs, self._surf.windowed(), cs, bool(self._touch))
        if self.viewer is not None:
            self.viewer.view = self.layout.view

    def open(self):
        art = self._art
        self._return_bakes()           # #186: load() may re-mint the document
        self._close_viewer()
        self._close_sent()
        self.pop = None
        self.page = None
        self.toast = None
        self._touch = None
        self.engine.open()
        peek = None if self.layout.desk else art.peek()
        if peek is not None and (peek[0] > GAME_W or peek[1] > GAME_H):
            # A desk's drawing on a handheld: to look at, never decoded whole.
            self.viewer = Viewer(art.doc_name(), peek[0], peek[1], peek[2], self.layout.view)
            self._opened = self._pointer()
            self._damage.all()
            return
        peek = None
        loaded = art.load(self._pixels_for)
        self._first_save = False
        if self.doc.load(loaded):
            if not art.editable():
                self._say(art.why_read_only(), "warn")
        elif not art.editable():
            # A picture that would not decode. It still opens HERE, saying so:
            # the blank canvas is not a new drawing and is never written back.
            self._say(art.why_read_only(), "warn")
        elif self._starter_pending:
            # The editable starter garden, built on the first Paint launch.
            self.doc = PaintDocument(*self._board_size(), seed=True)
            self._first_save = True
            self._mark_changed()
        else:
            if (self.doc.W, self.doc.H) != self._board_size():
                self.doc = PaintDocument(*self._board_size())
            self._first_save = True
        self._starter_pending = False
        self._unsaved = self._unsaved and art.editable()
        self.size_i = min(self.size_i, len(self.sizes()) - 1)
        self._open_view()
        self._opened = self._pointer()
        self._damage.all()

    def _pointer(self):
        """Where the doc pointer stands, as the count of its moves: what a
        frame compares, with no prefs read."""
        return self._art.moves

    def _open_view(self):
        """At 1x centred on the last mark on a handheld; the desk at Fit."""
        d = self.doc
        m = self._art_mark()
        self.cur = [m[0], m[1]] if m else [d.W // 2, d.H // 2]
        self.zoom = FIT if self.layout.desk else 4
        self._centre(self.cur)

    def _art_mark(self):
        got = self._art._prefs.get("mark")
        try:
            x, y = [int(v) for v in str(got).split(",")]
        except Exception:  # noqa: BLE001 -- no mark yet
            return None
        d = self.doc
        if 0 <= x < d.W and 0 <= y < d.H:
            return (x, y)
        return None

    def _close_viewer(self):
        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None

    def _return_bakes(self):
        """Hand this document's off-heap RGB565 bakes back (#186): the
        document is left (close) or replaced (a new drawing), and nothing is
        mid-draw there. The canvas nulls the bake as it frees, so the next
        frame rebuilds rather than reading returned RAM."""
        rel = getattr(self._surf.canvas(), "release_bakes", None)
        if rel is not None:
            rel(PaintDocument.OWNER)

    def close(self):
        """The app-API LEAVING hook: the drawing is saved where it changed,
        its bakes and a viewed drawing's screens go back. A document never
        built (Paint never opened) has nothing to write and lent no bake."""
        self._close_viewer()
        if self._sent() is not None:
            self._close_sent()
            self.page = None
        self.engine.close()
        if self._doc is None:
            return
        self._save()
        self._return_bakes()

    commit = close

    def _leaving(self):
        """The service is about to point at another picture: the open one
        is written first, while its name is still the pointer's."""
        if self._doc is not None and self.viewer is None and self._opened is not None:
            self._save()

    def has_page(self):
        return self.pop is not None or self.page is not None

    def back(self):
        """Back one level (B, Esc, the bar's chevron): a popover closes, a
        page goes back to the canvas. False on the canvas: the host leaves."""
        if self.pop is not None:
            self.pop = None
        elif self.page is not None:
            self._close_sent()
            self.page = None
            self._ui.reset()
        else:
            return False
        self._damage.all()
        return True

    def _sent(self):
        """The page a drawing is sent from that is open (Put in a game, Put
        in a story), else None."""
        return self.game if self.page == "game" else self.story if self.page == "story" else None

    def _close_sent(self):
        send = self._sent()
        if send is not None:
            send.close()
        self.game = self.story = None

    def doc_title(self):
        if self.viewer is not None:
            return shown(self.viewer.name)
        name = self._art.doc_name()
        return shown(name) if name else "New drawing"

    # -- saving -----------------------------------------------------------------

    def _mark_changed(self):
        self._unsaved = True
        self._idle = 0.0

    def _save(self):
        art = self._art
        if self.viewer is not None or not art.editable():
            return True                # show-only: there is nothing to write back
        if not self._unsaved and art.doc_name() is not None and not self._first_save:
            return True
        if not self._unsaved and self._first_save:
            return True                # a new drawing nobody marked: nothing lands
        d = self.doc
        if art.save(d.pix, d.W, d.H):
            self._opened = self._pointer()
            if self._first_save:
                self._say("Saved " + shown(art.doc_name()))
            self._first_save = False
            self._unsaved = False
            self._idle = 0.0
            if self.mark is not None:
                art._prefs.set("mark", "%d,%d" % self.mark)
            return True
        self._say(art.last_error or "Can't save", "warn", True)
        self._idle = self.AUTOSAVE_S - self.RETRY_S
        return False

    def _fresh_doc(self, w, h):
        """A new auto-named drawing: the open one keeps its file."""
        self._save()
        self._return_bakes()
        self._close_viewer()
        self._art.new_doc(w, h)
        self.doc = PaintDocument(w, h)
        self._unsaved = False
        self._first_save = True
        self.mark = None
        self.size_i = min(self.size_i, len(self.sizes()) - 1)
        self.cur = [w // 2, h // 2]
        self.zoom = FIT if self.layout.desk else 4
        self._centre(self.cur)
        self._opened = self._pointer()

    # -- toasts -------------------------------------------------------------------

    def _say(self, text, icon="check", danger=False, undo=None):
        if not text:
            return
        self.toast = (text, "warn" if danger else icon, _ticks_ms() + TOAST_MS, undo)
        self._damage.all()

    # -- the view ---------------------------------------------------------------

    def _quarters(self):
        """The zoom in quarters: Fit is the largest of 1x, 1/2 and 1/4 that
        shows the whole drawing."""
        if self.zoom != FIT:
            return self.zoom
        d = self.doc
        vw, vh = self.layout.view[2], self.layout.view[3]
        for q in (4, 2, 1):
            if d.W * q // 4 <= vw and d.H * q // 4 <= vh:
                return q
        return 1

    def _spec(self):
        """[x, y, w, h, sx, sy, sw, sh, q]: where the drawing's (sx, sy, sw,
        sh) part stands on the glass at q quarters a pixel. One list, filled
        afresh each call (a frame asks several times and keeps nothing)."""
        d = self.doc
        q = self._quarters()
        v = self.layout.view
        vx = v[0]
        vy = v[1]
        vw = v[2]
        vh = v[3]
        o = self._spec_l
        dw = d.W * q // 4
        dh = d.H * q // 4
        if dw <= vw:
            o[0] = vx + (vw - dw) // 2
            o[4] = 0
            o[6] = d.W
            o[2] = dw
            self.pan[0] = 0
        else:
            sw = vw * 4 // q
            self.pan[0] = max(0, min(self.pan[0], d.W - sw))
            o[0] = vx
            o[4] = self.pan[0]
            o[6] = sw
            o[2] = sw * q // 4
        if dh <= vh:
            o[1] = vy + (vh - dh) // 2
            o[5] = 0
            o[7] = d.H
            o[3] = dh
            self.pan[1] = 0
        else:
            sh = vh * 4 // q
            self.pan[1] = max(0, min(self.pan[1], d.H - sh))
            o[1] = vy
            o[5] = self.pan[1]
            o[7] = sh
            o[3] = sh * q // 4
        o[8] = q
        return o

    def _centre(self, p):
        q = self._quarters()
        vw, vh = self.layout.view[2], self.layout.view[3]
        self.pan[0] = p[0] - vw * 2 // q
        self.pan[1] = p[1] - vh * 2 // q

    def _follow(self):
        """Keep the cursor in the view, a sixteenth of it from the edge."""
        x, y, w, h, sx, sy, sw, sh, q = self._spec()
        mx, my = max(1, sw // 16), max(1, sh // 16)
        c = self.cur
        if c[0] < sx + mx:
            self.pan[0] = c[0] - mx
        elif c[0] >= sx + sw - mx:
            self.pan[0] = c[0] - sw + mx + 1
        if c[1] < sy + my:
            self.pan[1] = c[1] - my
        elif c[1] >= sy + sh - my:
            self.pan[1] = c[1] - sh + my + 1

    def _to_doc(self, px, py, clamp=False):
        x, y, w, h, sx, sy, sw, sh, q = self._spec()
        dx = sx + (px - x) * 4 // q
        dy = sy + (py - y) * 4 // q
        d = self.doc
        if clamp:
            return (max(0, min(d.W - 1, dx)), max(0, min(d.H - 1, dy)))
        if px < x or py < y or px >= x + w or py >= y + h:
            return None
        if dx < 0 or dy < 0 or dx >= d.W or dy >= d.H:
            return None
        return (dx, dy)

    def _to_glass(self, p):
        x, y, w, h, sx, sy, sw, sh, q = self._spec()
        return (x + (p[0] - sx) * q // 4, y + (p[1] - sy) * q // 4)

    def _zoom_to(self, z):
        mid = self._view_middle()
        self.zoom = z
        self._centre(mid)
        self._damage.all()

    def _view_middle(self):
        x, y, w, h, sx, sy, sw, sh, q = self._spec()
        return (sx + sw // 2, sy + sh // 2)

    def _step_zoom(self):
        if self.viewer is not None:
            self.viewer.step(ZOOM_VIEW)
            self._damage.all()
            return
        z = ZOOM_EDIT
        i = z.index(self.zoom) if self.zoom in z else len(z) - 1
        self._zoom_to(z[(i + 1) % len(z)])

    # -- input --------------------------------------------------------------------

    def ball_steps(self):
        """The trackball steps an open popover (colours, brush, more) and
        points at the drawing otherwise (InputPolicy.ball_steps)."""
        return self.pop is not None

    def handle_input(self, inp):
        k = getattr(inp, "typed", 0)
        typed = k != 0
        if self.toast is not None and (typed or inp.any_pressed()):
            if typed and k == 0x1A and self.toast[3] is not None:
                self.toast[3]()                 # Ctrl+Z on "Added as slide 6 ... Undo"
                self.toast = None
                self._say("Taken out again")
                return True
            self.toast = None
            self._damage.all()
        if self.page == "show":
            if typed or inp.any_pressed():
                self.page = None
                self._damage.all()
            return True
        if inp.pressed("b"):
            self.back()
            return True
        send = self._sent()
        if send is not None:
            return send.keys(inp)
        if self.pop is not None:
            return self.engine.keys(inp)
        return self._canvas_keys(inp)

    def _canvas_keys(self, inp):
        """The keys on the drawing (the view canvas's keys=): a tool, a verb,
        the arrows moving the cursor, `a` drawing at it, Space held moving the
        drawing."""
        k = getattr(inp, "typed", 0)
        typed = k != 0
        self._space = k == SPACE
        if typed and k != SPACE:
            lk = k + 32 if 65 <= k <= 90 else k
            if self._verb_key(lk):
                return True
        dx = (1 if inp.held("right") else 0) - (1 if inp.held("left") else 0)
        dy = (1 if inp.held("down") else 0) - (1 if inp.held("up") else 0)
        if dx or dy:
            self._held += 1
        else:
            self._held = 0
        step = dx or dy
        moved = step and (self._held == 1 or self._held > 8)
        if self.viewer is not None:
            if moved and self.viewer.zoom != FIT:
                self.viewer.nudge(dx, dy)
                self._damage.all()
            if inp.pressed("a"):
                self._say("From a desk: you can look, not draw")
            return True
        if moved:
            if self._space or self.tool == MOVE:
                q = self._quarters()
                n = max(1, 16 * 4 // q)
                self.pan[0] += dx * n
                self.pan[1] += dy * n
            else:
                n = 1 if self._held <= 24 else max(1, 4 * 4 // self._quarters())
                d = self.doc
                self.cur[0] = max(0, min(d.W - 1, self.cur[0] + dx * n))
                self.cur[1] = max(0, min(d.H - 1, self.cur[1] + dy * n))
                self._follow()
                if self._drawing_key:
                    self._drag((self.cur[0], self.cur[1]))
            if self._space or self.tool == MOVE:
                self._damage.all()
            else:
                self._damage.mark()
        down = inp.held("a") and not self._space
        if down and not self._drawing_key:
            self._drawing_key = True
            self._press((self.cur[0], self.cur[1]))
            self._damage.mark()
        elif not down and self._drawing_key:
            self._drawing_key = False
            self._release()
            self._damage.mark()
        return True

    def _verb_key(self, k):
        """A typed key on the canvas: a tool, a verb. Whether it was one."""
        if self.viewer is not None:
            verb = KEYS.get(k)
            if verb in ("zoom", "more", "open", "wallpaper", "show", "story"):
                self._verb(verb)
                return True
            if k in _TOOL_KEYS or verb in ("colours", "new", "game") or k == 0x0D:
                self._say("From a desk: you can look, not draw")
                return True
            return False
        t = _TOOL_KEYS.get(k)
        if t is not None:
            self._pick_tool(t, True)
            return True
        verb = KEYS.get(k)
        if verb is not None:
            self._verb(verb)
            return True
        return False

    def _pick_tool(self, t, keyed=False):
        """Tool `t` in use: a repeat on Shape moves its shape on, a repeat key
        on a tool with a brush opens the brush."""
        if t == self.tool and t == SHAPE:
            self.shape = (self.shape + 1) % len(SHAPES)
        elif t == self.tool and keyed and t in (PENCIL, BRUSH, ERASER, SPRAY):
            self._open("brush")
        self.tool = t
        self._damage.all()

    def _verb(self, verb):
        art = self._art
        if verb == "undo":
            if self.viewer is None and self.doc.undo():
                self._mark_changed()
        elif verb == "redo":
            if self.viewer is None and self.doc.redo():
                self._mark_changed()
        elif verb == "zoom":
            self._step_zoom()
        elif verb in ("colours", "brush", "more"):
            self._open(verb)
        elif verb == "new":
            self._fresh_doc(*self._board_size())
        elif verb == "new_game":
            self._fresh_doc(GAME_W, GAME_H)
        elif verb == "open":
            self._save()
            self._nav.open_app("myart")
        elif verb == "wallpaper":
            name = self._source_name()
            if name and self._save() and art.set_wallpaper(name):
                self._say(shown(name) + " is the wallpaper")
            elif name:
                self._say(art.last_error or "Can't use it", "warn", True)
        elif verb == "game":
            if self.viewer is None and (self.doc.W, self.doc.H) == (GAME_W, GAME_H) \
                    and self._save() and art.doc_name():
                self._ui.reset()
                self.game = GamePage(art.copies, self._nav, art.doc_name(), self._ui, self._damage)
                self.page = "game"
        elif verb == "story":
            name = self._source_name()
            if name and self._save() and stories_here():
                self._ui.reset()
                self.story = StoryPage(art.ctx.carts, art.ctx.files, name, self._ui, self._damage)
                self.page = "story"
        elif verb == "show":
            self._save()
            self.page = "show"
        elif verb == "copy":
            self._copy_to_my_art()
        elif verb == "dup":
            name = self._source_name()
            if name and self._save():
                got, err = art.ctx.files.duplicate("drawings", name)
                if err is None and got:
                    self._say("Duplicated as " + shown(got))
        self._damage.all()

    def _source_name(self):
        """The gallery drawing the verbs act on: the one open or viewed."""
        if self.viewer is not None:
            return self.viewer.name
        return self._art._open_drawing()

    def _copy_to_my_art(self):
        """A show-only picture's pixels as a new drawing of My Art's."""
        art = self._art
        d = self.doc
        name = art.new_doc(d.W, d.H)
        if name and art.save(d.pix, d.W, d.H):
            self._say("Copied to My Art as " + shown(name))
        else:
            self._say(art.last_error or "Can't copy it", "warn", True)

    def _open(self, which):
        self.pop = None if self.pop == which else which
        self._damage.all()

    def _take(self, c):
        """Colour `c` in use."""
        self.color = c
        self._damage.all()

    # -- the pointer ----------------------------------------------------------------

    def handle_pointer(self, px, py, click):
        if self.page == "show":
            if click:
                self.page = None
                self._damage.all()
            return True
        if self.toast is not None and click:
            if self.toast[3] is not None and self._toast_hit(px, py):
                self.toast[3]()
                self.toast = None
                self._damage.all()
                return True
        send = self._sent()
        if send is not None:
            return send.point(px, py, click)
        if self.pop is None and self.page is None and self.viewer is None and (
                self._down or click):
            # a press on the drawing, its drag and its release are the drawing's, wherever
            # the pointer goes, in the frame they come in: the stroke frame weighs them
            # (a canvas's pointer= runs after the frame's paint)
            down = bool(getattr(self._surf.pointer(), "down", False))
            if self._canvas_pointer(px, py, click, down or click):
                return True
        if click or self._page_down:
            # the page's press, drag and release: the frames that resolve them are whole
            # ones (the page draws its stops, a stroke frame does not)
            self._page_down = bool(getattr(self._surf.pointer(), "down", False))
            self._damage.all()
        return self.engine.point(px, py, click)

    def _canvas_pointer(self, px, py, click, down):
        if click:
            p = self._to_doc(px, py)
            if p is not None:
                self._down = True
                if self.tool == MOVE:
                    self._panning = (px, py)
                    self._damage.all()
                else:
                    self.cur = [p[0], p[1]]
                    self._press(p)
                    self._damage.mark()
                return True
            return False
        if not self._down:
            return False
        if self._panning is not None:
            q = self._quarters()
            self.pan[0] -= (px - self._panning[0]) * 4 // q
            self.pan[1] -= (py - self._panning[1]) * 4 // q
            self._panning = (px, py)
            self._damage.all()
        else:
            p = self._to_doc(px, py, True)
            self.cur[0] = p[0]
            self.cur[1] = p[1]
            self._drag(p)
            self._damage.mark()
        if not down:
            self._down = False
            self._panning = None
            self._release()
            self._damage.mark()
        return True

    def _toast_hit(self, px, py):
        """A tap on the toast's band, the foot of the view."""
        vx, vy, vw, vh = self.layout.view
        return vx <= px < vx + vw and vy + vh - 40 * self.layout.fs <= py < vy + vh

    # -- marks --------------------------------------------------------------------

    def _press(self, p):
        art = self._art
        if not art.editable():
            self._say(art.why_read_only() or "Only to look at", "warn")
            return
        d = self.doc
        t = self.tool
        if t == PICK:
            self.color = d.get(p[0], p[1])
            return
        if t == MOVE:
            return
        d.snapshot()
        if t == FILL:
            d.flood(p[0], p[1], self.color)
            d.finish()
            self.mark = p
            self._mark_changed()
            return
        if t == SHAPE:
            self._shape0 = p
            self._shape1 = p
            return
        self._stroke = p
        self._paint_at(p, p)

    def _paint_at(self, a, b):
        d = self.doc
        t = self.tool
        s = self.size()
        if t == SPRAY:
            self._rng = d.spray(b[0], b[1], self.color, s, self._rng)
        elif t == ERASER:
            d.line(a[0], a[1], b[0], b[1], PaintDocument.PAPER, s * 2, False)
        else:
            d.line(a[0], a[1], b[0], b[1], self.color, s, t == BRUSH)

    def _drag(self, p):
        if self._shape0 is not None:
            self._shape1 = p
            return
        if self._stroke is None or not self.doc.action_live:
            return
        self._paint_at(self._stroke, p)
        self._stroke = p

    def _release(self):
        d = self.doc
        if not d.action_live:
            self._stroke = self._shape0 = self._shape1 = None
            return
        a, b = self._shape0, self._shape1
        if a is not None and b is not None:
            s = self.size()
            if self.shape == 0:
                d.line(a[0], a[1], b[0], b[1], self.color, s, True)
            elif self.shape == 1:
                d.box(a, b, self.color, self.shape_fill, s)
            else:
                d.oval(a, b, self.color, self.shape_fill, s)
            self.mark = b
        else:
            self.mark = self._stroke
        d.finish()
        self._stroke = self._shape0 = self._shape1 = None
        self._mark_changed()

    # -- draw ---------------------------------------------------------------------

    # -- the WM's shown protocol (docs/surface_model_v1.md §14.3) ------------------

    def retained(self, known, x0, y0, x1, y1):
        """The window's word on the target of the draw that follows: when
        `known`, it holds the page as this layer's last draw left it but for
        [x0, y0, x1, y1)."""
        h = self._word
        h[0] = known
        h[1] = x0
        h[2] = y0
        h[3] = x1
        h[4] = y1
        self._held_on = True

    def changed(self):
        """What the last draw changed of the page, [x0, y0, x1, y1), or None
        when it was a whole frame."""
        return self._own if self._changed else None

    def draw(self, dt):
        # The window's word counts only when the draw before was one it said
        # it of too, and weighed a stroke frame: anything else may have drawn
        # the page since, or drawn one the page's signature never saw.
        said = self._held_on
        self._said = said and self._held_last and self._word[0] and self._sf_ran
        self._sf_ran = False
        self._held_on = False
        self._held_last = said
        self._changed = False
        cv = self._surf.canvas()
        if self._opened is not None and self._pointer() != self._opened \
                and (self._doc is None or not self._doc.action_live):
            # another app pointed Paint at a drawing (My Art's Open, Files'),
            # and the window came forward as it was: open that one (the
            # one open was written as the pointer moved, `on_leave`)
            self.open()
        if (self._unsaved and self.page is None and self._doc is not None
                and not self._doc.action_live):
            self._idle += dt
            if self._idle >= self.AUTOSAVE_S:
                self._save()
        if self.toast is not None:
            if _ticks_diff(_ticks_ms(), self.toast[2]) >= 0:
                self.toast = None
                self._damage.all()
            else:
                self._damage.settle()         # a frame to take it down at its time
        th = self._theme.colors()
        lay = self.layout
        d = self._doc
        if d is not None:
            u = (1 if d.history else 0) | (2 if d.future else 0)
            if u != self._undo_seen:
                # a mark made or taken back: the undo and redo the page shows move
                self._undo_seen = u
                self.fill_owed = True
            if self.tool == PICK:
                c = self._drip_colour()
                if c != self._drip_seen:
                    self._drip_seen = c       # the band says the colour under the cursor
                    self.fill_owed = True
        if self.fill_owed or self.engine.owes:
            self._damage.gen += 1         # the page moves: no stroke frame
        if (self.page is None and self.viewer is None and d is not None
                and self._stroke_frame(cv, th)):
            self._changed = True
            return
        send = self._sent()
        if send is not None:
            if self.shown.get("lends"):
                self.engine.run(fill, self, action="fill")    # the bar's row goes
                ui.commit(self.engine)
            self._name_bar()
            self._ui.begin(cv, th, lay.page, lay.desk, lay.windowed)
            self._send_page(cv, th, dt)
            self._ui.end()
            return
        # a whole frame: the view canvas draws again (its reads= state moves),
        # so it holds what the stroke frames after it repaint parts of
        self._view_n += 1
        self.fill_owed = False
        self.engine.run(fill, self, action="fill")
        ui.commit(self.engine)
        content = lay.full
        ground_round(cv, content, th["panel"])
        eng = self.engine
        eng.hosted(dt, cv, th, content, lay.desk)
        eng._ui.begin(cv, th, content, lay.desk, lay.windowed)
        if self._touch is None:
            self._touch = eng.input_now() == "touch"
            # the page this frame paints is the first a stroke frame may
            # follow: one more frame begins bringing every buffer to it
            self._damage.again()
            if self._touch != lay.touch and not lay.desk:
                self.relayout(lay.w, lay.h, lay.fs, lay.cs)
                lay = self.layout
                self.fill_owed = True
        self._name_bar()
        was = (self.pop, self.page)
        eng.paint(dt, cv, th, content, lay.desk)
        if (self.pop, self.page) != was:
            self._damage.again()
