"""The Editor's Map tab, the tilemap editor, as a placed `uitree` page: the
handheld's tab and a desk Editor's Map pane alike
(docs/media/look_2026-10/EDITOR_LAYOUT.md's `map` pictures).

The handheld's: the view (the map at its zoom) from the content rect's top
left; beside it the brushes a page at a time (‹ 1 / 4 ›), the brush's tile,
the cell last touched and that a hold picks, or while Select is the tool,
Copy, Cut and Paste; under both the tools (pen, box, fill, select, erase),
the brush's size, the zoom and Resize, whose popover grows and shrinks the
map. The desk pane's (its header and its tools the desk's): the view over a
status line.

`MapEditorUI` (map_editor_ui.py) is the host, which the handlers and the
canvases reach through `uitree_app.env()`: it writes the editor's state into
the page's (`sync`), draws the view and the brushes, takes their presses (in
the view a tap paints, a drag pans and a still hold picks the cell's tile; a
tap on a brush picks it) and their keys (the arrows pan the view and move
along the brushes, A steps the zoom and picks a brush), and does what the
handlers ask over its `MapEditor`."""
import uitree as ui
import uitree_app

s = ui.state(
    none=False, pane=False, selecting=False,
    tool=ui.enum("pen", "box", "fill", "select", "erase", init="pen"),
    pop=ui.enum("none", "resize", init="none"),
    sel=False, clip=False, first=True, last=True,
    bpage="1 / 1", tile="Sky", cell="Tap to paint", size_word="1x1", zoom_word="1x", dims="", status="",
    view_w=216, brushes_h=96, tile_on=True, cell_on=True, hold_on=True, pitch=24, pad=6, resize_w=160,
)

# The foot's tools: (action, its word, icon).
TOOLS = (("pen", "Pen", "pencil"), ("box", "Box", "rect"), ("fill", "Fill", "bucket"),
         ("select", "Select", "select"), ("erase", "Erase", "eraser"))


def sync(vals):
    """The host's values: (no map, the desk's pane, the tool, the popover,
    a selection, a clip to paste, the brushes' first page and their last,
    the page's words, the brush's tile, the cell last touched, the brush's
    size, the zoom, the map's size, the pane's status line, and the host's
    measures: the view's width (pixels), the brushes' height (the page's
    unit), the lines under them the column holds, a tool's pitch (the
    page's unit), the column's pad (at 1x) and the popover's width (pixels))."""
    (s.none, s.pane, tool, pop, s.sel, s.clip, s.first, s.last, s.bpage, s.tile, s.cell, s.size_word,
     s.zoom_word, s.dims, s.status, s.view_w, s.brushes_h, lines, s.pitch, s.pad, s.resize_w) = vals
    s.tile_on, s.cell_on, s.hold_on = lines > 0, lines > 1, lines > 2
    if s.tool != tool:
        s.tool = tool
    if s.pop != pop:
        s.pop = pop
    selecting = tool == "select"
    if s.selecting != selecting:
        s.selecting = selecting


def home():
    """The view takes the keys."""
    ui.focus("view")


def popped():
    """The resize popover's first step takes the keys."""
    ui.focus("wider")


def _do(verb):
    uitree_app.env().act(verb)


def view_press(ev):
    uitree_app.env().view_pointer(ev.kind, ev.x, ev.y)


def brush_press(ev):
    if ev.kind == "down":
        uitree_app.env().brush_tap(ev.x, ev.y)


ui.hook("sync", sync, takes="arg")
ui.hook("home", home)
ui.hook("popped", popped)
ui.hook("view_press", view_press, takes="pointer")
ui.hook("brush_press", brush_press, takes="pointer")
for _a, _w, _i in TOOLS:
    ui.action(_a, _w, (lambda v: lambda: _do(v))(_a), icon=_i)
ui.action("copy", "Copy", lambda: _do("copy"), icon="copy", when="sel", off="grey")
ui.action("cut", "Cut", lambda: _do("cut"), icon="cut", when="sel", off="grey")
ui.action("paste", "Paste", lambda: _do("paste"), icon="paste", when="clip", off="grey")
ui.action("bprev", "Previous brushes", lambda: _do("bprev"), when="!first", off="grey")
ui.action("bnext", "Next brushes", lambda: _do("bnext"), when="!last", off="grey")
ui.action("size", "Brush size", lambda: _do("size"), icon="brush")
ui.action("zoom", "Zoom", lambda: _do("zoom"), icon="search")
ui.action("resize", "Resize", lambda: _do("resize"), icon="resize")
ui.action("wider", "Wider", lambda: _do("wider"))
ui.action("narrower", "Narrower", lambda: _do("narrower"))
ui.action("taller", "Taller", lambda: _do("taller"))
ui.action("shorter", "Shorter", lambda: _do("shorter"))
ui.action("close_pop", "Close", lambda: _do("close"), hint="Close")


def view_keys(i):
    return uitree_app.env().view_keys(i)


def brush_keys(i):
    return uitree_app.env().brush_keys(i)


def _draw_view(cv, x, y, w, h):
    uitree_app.env().draw_view(cv, x, y, w, h)


def _draw_brushes(cv, x, y, w, h):
    uitree_app.env().draw_brushes(cv, x, y, w, h)


def _brushes():
    ui.canvas("brushes", _draw_brushes, h="{brushes_h}", keys=brush_keys, pointer="brush_press",
              mark=False)
    with ui.row("pager", pad="{pad}"):
        ui.stepper("{bpage}", "bprev", "bnext", grow=True)
    with ui.row("tile_row", pad="{pad}", shown="tile_on"):
        ui.label("{tile}")
    with ui.row("cell_row", pad="{pad}", shown="cell_on"):
        ui.label("{cell}", tone="dim")
    with ui.row("hold_row", pad="{pad}", shown="hold_on"):
        ui.label("Hold: pick", tone="dim")


def _region():
    with ui.row("copy_row", pad="{pad}"):
        ui.button("copy", grow=True)
    with ui.row("cut_row", pad="{pad}"):
        ui.button("cut", grow=True)
    with ui.row("paste_row", pad="{pad}"):
        ui.button("paste", grow=True)


def map_page():
    with ui.page(""):
        ui.empty("No map", icon="map", lines=["This cart has no sprites to paint with"], shown="none")
        with ui.row("main", grow=True, gap=0, shown="!none"):
            ui.canvas("view", _draw_view, w="{view_w}", keys=view_keys, pointer="view_press", mark=False)
            ui.switch("selecting", {False: _brushes, True: _region}, shown="!pane")
        ui.status("{status}", shown="!none && pane")
        ui.rule(shown="!none && !pane")
        with ui.row("foot", pad=2, gap=0, shown="!none && !pane"):
            ui.button("pen", kind="bar", alone=True, w="{pitch}", marked="tool=pen")
            ui.button("box", kind="bar", alone=True, w="{pitch}", marked="tool=box")
            ui.button("fill", kind="bar", alone=True, w="{pitch}", marked="tool=fill")
            ui.button("select", kind="bar", alone=True, w="{pitch}", marked="tool=select")
            ui.button("erase", kind="bar", alone=True, w="{pitch}", marked="tool=erase")
            ui.rule()
            with ui.row("chips", gap=4):
                ui.button("size", label="{size_word}")
                ui.button("zoom", label="{zoom_word}")
            with ui.row("rest"):
                pass
            ui.button("resize", kind="bar", alone=True, w="{pitch}", marked="pop=resize")
        with ui.popover("resize_pop", anchor="resize", w="{resize_w}", close="close_pop",
                        shown="pop=resize"):
            ui.info("Size", "{dims}")
            ui.button("wider")
            ui.button("narrower")
            ui.button("taller")
            ui.button("shorter")
