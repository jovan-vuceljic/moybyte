"""The Editor's theme mode's Sprites tab as a placed `uitree` page: the
handheld's tab and a desk's Sprites pane alike (theme_editor.py's module
doc has the mode).

The open slot at its zoom (a canvas) with the tools under it (pencil,
bucket, line, rect, select); beside it the sheet (a canvas: the slots,
a pixel tile's dot, the legend; on the desk each named under its tile),
and on the handheld the sheet's pages where it is paged (‹ 1 / 3 ›), the
open slot as the shell draws it with its name, its state and the
palette. The desk pane's: the palette and the slot at 1x and 2x under the
tools, and the state as its status line.

`SpritesLayer` (theme_editor.py) is the host, which the handlers and the
canvases reach through `uitree_app.env()`: it writes the open theme's
state into the page's (`sync`), draws the slot, the sheet and the
previews, takes their presses (the slot paints, the sheet opens a slot)
and their keys (the arrows move the cursor or along the sheet, A paints),
and does what the handlers ask over the `ThemeDoc`."""
import uitree as ui
import uitree_app

s = ui.state(
    pane=False, paged=False, named_on=True, state_on=True, name="", status="", spage="1 / 1", first=True, last=True,
    tool=ui.enum("pencil", "bucket", "line", "rect", "select", init="pencil"),
    color=0, grid_w=160, grid_h=160, sheet_h=96, pitch=24, sw=11, prev_w=18, prev_h=18, pad=4,
)

# The tools under the slot: (action, its word, icon).
TOOLS = (("pencil", "Pencil", "pencil"), ("bucket", "Fill", "bucket"), ("line", "Line", "line"),
         ("rect", "Rect", "rect"), ("select", "Select", "select"))


def sync(vals):
    """The host's values: (the desk's pane, the sheet paged, the slot's
    name's line shown and its state's, the slot's name, its state, the pager's words, its first page and its last, the
    tool, the colour, and the host's measures: the slot's canvas's width
    and height and the sheet's height and a tool's pitch (the page's unit), a
    palette cell's side, the preview's width and height (the page's unit)
    and the rows' pad (at 1x))."""
    (s.pane, s.paged, s.named_on, s.state_on, s.name, s.status, s.spage, s.first, s.last, tool, color, s.grid_w, s.grid_h, s.sheet_h,
     s.pitch, s.sw, s.prev_w, s.prev_h, s.pad) = vals
    if s.tool != tool:
        s.tool = tool
    if s.color != color:
        s.color = color


def home():
    """The slot takes the keys."""
    ui.focus("grid")


def colored():
    uitree_app.env().set_color(s.color)


def _do(verb):
    uitree_app.env().act(verb)


def grid_press(ev):
    uitree_app.env().grid_pointer(ev.kind, ev.x, ev.y)


def sheet_press(ev):
    if ev.kind == "down":
        uitree_app.env().sheet_tap(ev.x, ev.y)


ui.hook("sync", sync, takes="arg")
ui.hook("home", home)
ui.hook("colored", colored)
ui.hook("grid_press", grid_press, takes="pointer")
ui.hook("sheet_press", sheet_press, takes="pointer")
for _a, _w, _i in TOOLS:
    ui.action(_a, _w, (lambda v: lambda: _do(v))(_a), icon=_i)
ui.action("sprev", "Previous icons", lambda: _do("sprev"), when="!first", off="grey")
ui.action("snext", "Next icons", lambda: _do("snext"), when="!last", off="grey")


def grid_keys(i):
    return uitree_app.env().grid_keys(i)


def sheet_keys(i):
    return uitree_app.env().sheet_keys(i)


def _draw_grid(cv, x, y, w, h):
    uitree_app.env().draw_grid(cv, x, y, w, h)


def _draw_sheet(cv, x, y, w, h):
    uitree_app.env().draw_sheet(cv, x, y, w, h)


def _draw_preview(cv, x, y, w, h):
    uitree_app.env().draw_preview(cv, x, y, w, h)


def _hand():
    ui.canvas("sheet", _draw_sheet, h="{sheet_h}", keys=sheet_keys, pointer="sheet_press", mark=False)
    with ui.row("pager", pad="{pad}", shown="paged"):
        ui.stepper("{spage}", "sprev", "snext", grow=True)
    with ui.row("named", pad="{pad}", gap=6, shown="named_on"):
        ui.canvas("slot_icon", _draw_preview, w="{prev_w}", h="{prev_h}")
        ui.label("{name}", face="title")
    with ui.row("state", pad="{pad}", shown="state_on"):
        ui.label("{status}", tone="dim")
    with ui.row("swatches", pad="{pad}"):
        ui.cells("color", first=0, count=16, cols=8, side="{sw}", on="colored")


def _desk():
    ui.canvas("dsheet", _draw_sheet, keys=sheet_keys, pointer="sheet_press", mark=False)


def theme_page():
    with ui.page(""):
        with ui.row("main", grow=True, gap=0):
            ui.canvas("grid", _draw_grid, w="{grid_w}", h="{grid_h}", keys=grid_keys, pointer="grid_press", mark=False,
                      hint="Paint")
            ui.switch("pane", {False: _hand, True: _desk})
        ui.rule()
        with ui.row("tools", pad="{pad}", gap=2):
            ui.button("pencil", kind="bar", alone=True, w="{pitch}", marked="tool=pencil")
            ui.button("bucket", kind="bar", alone=True, w="{pitch}", marked="tool=bucket")
            ui.button("line", kind="bar", alone=True, w="{pitch}", marked="tool=line")
            ui.button("rect", kind="bar", alone=True, w="{pitch}", marked="tool=rect")
            ui.button("select", kind="bar", alone=True, w="{pitch}", marked="tool=select")
        with ui.row("dpal", pad="{pad}", gap=12, shown="pane"):
            ui.cells("color", first=0, count=16, cols=8, side="{sw}", on="colored")
            ui.canvas("preview", _draw_preview, w="{prev_w}", h="{prev_h}")
            ui.label("1x · 2x", tone="dim")
        ui.status("{status}", shown="pane")
