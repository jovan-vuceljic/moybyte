"""The Editor's Art tab, the sprite editor, as a placed `uitree` page: the
handheld's tab and a desk Editor's Sprite pane alike
(docs/media/look_2026-10/EDITOR_LAYOUT.md's Art).

The handheld's: "Sprite N" with the sprite before and after (‹ n ›) and
its size, which opens the pickers; the grid, the palette's two columns and
the sprite map; the tool row (pen, fill, shape, select, stamp, more) with
load, save and to-Files and the status at the foot. The desk pane's (its
header the desk's): the tool row at its head, the grid and the palette,
‹ n › with the size and "64" (MOY64), the sprite's eight flags and the
sprite as the game draws it. Under an input with keys the band names the
operations' keys. The more menu (the operations, Clear a danger row apart;
a handheld folds the four shifts into a page of their own) and the pickers
(the size, and the sheet, whose tapped sprite becomes the sprite) are
popovers.

`PaintLayer` (paint_layer.py) is the host, which the handlers and the
canvases reach through `uitree_app.env()`: it writes the editor's state
into the page's (`sync`), measures the grid's span and the palette's side,
draws the grid, the map, the flags, the preview and the sheet, takes their
presses and their keys, and does what the handlers ask over its
`PaintEditor`."""
import uitree as ui
import uitree_app

s = ui.state(
    none=False, pane=False, tall=False, n="0", size="", status="",
    tool=ui.enum("pen", "fill", "shape", "select", "stamp", "other", init="pen"),
    shape_icon="oval", clip=False, mirrored=False,
    pop=ui.enum("none", "more", "pickers", init="none"), shifting=False,
    color=0, sized=ui.enum("1", "2", "3", init="1"),
    pad=6, mpad=2, gap=6, span=144, grid_w=152, grid_h=150, words=False, sw=11, pal_w=22, pal_h=88, pitch=24, flags_h=24, preview_h=34, sheet_h=64,
    more_w=150, pick_w=200,
    k_copy="", k_fliph="", k_flipv="", k_rot="", k_sleft="", k_sright="", k_sup="", k_sdown="",
    k_clear="",
)

ui.labels("SIZES", {"1": "1x1", "2": "2x2", "3": "3x3"})

# The tool row: (action, its word, icon); shape wears the shape in use.
TOOLS = (("pen", "Pen", "pencil"), ("fill", "Fill", "bucket"), ("shape", "Shape", "{shape_icon}"),
         ("select", "Select", "select"), ("stamp", "Stamp", "stamp"), ("more", "More", "more"))
# The more menu's operations, in its order: (action, its word, icon).
OPS = (("copy", "Copy", "copy"), ("fliph", "Flip across", "flip"), ("flipv", "Flip over", "flip_v"),
       ("rot", "Rotate", "rotate"), ("sleft", "Shift left", "arrow_left"),
       ("sright", "Shift right", "arrow_right"), ("sup", "Shift up", "arrow_up"),
       ("sdown", "Shift down", "arrow_down"))
SHIFTS = ("sleft", "sright", "sup", "sdown")


def sync(vals):
    """The host's values: (no sprite, the desk's pane, a pane tall enough
    for the preview, the sprite's number, its size's word, the status, the
    tool, the shape's icon, a clip to stamp, mirror on, the popover, the
    shifts' page, the colour, the size, and the host's measures: the rows'
    pad (the grid's row's, less the grid's margin) and gap, the grid's
    canvas's side (its span and a margin round it for the cursor), whether
    the foot's buttons wear their words, a palette cell's side and the palette's
    width and height, a tool's pitch, the flags' and the preview's heights,
    the sheet's, the more menu's width and the pickers', and the
    operations' keys). A canvas's height, a button's width and a cell's side
    are in the page's unit (the handheld's font scale), its pads and gap at
    1x (the engine scales them), the rest in pixels."""
    (s.none, s.pane, s.tall, s.n, s.size, s.status, tool, s.shape_icon, s.clip, s.mirrored, pop,
     s.shifting, color, sized, s.pad, s.mpad, s.gap, s.grid_w, s.grid_h, s.words, s.sw, s.pal_w, s.pal_h,
     s.pitch, s.flags_h, s.preview_h, s.sheet_h, s.more_w, s.pick_w, keys) = vals
    if s.tool != tool:
        s.tool = tool
    if s.pop != pop:
        s.pop = pop
    if s.color != color:
        s.color = color
    if s.sized != sized:
        s.sized = sized
    (s.k_copy, s.k_fliph, s.k_flipv, s.k_rot, s.k_sleft, s.k_sright, s.k_sup, s.k_sdown,
     s.k_clear) = keys


def home():
    """The grid takes the keys."""
    ui.focus("grid")


def menu(row):
    """An open menu's row `row` (its text) takes focus."""
    ui.focus(row)


def colored():
    uitree_app.env().set_color(s.color)


def sized():
    uitree_app.env().set_size(int(s.sized))


def _do(verb):
    uitree_app.env().act(verb)


def grid(ev):
    uitree_app.env().grid_pointer(ev.kind, ev.x, ev.y)


def map_tap(ev):
    if ev.kind == "down":
        uitree_app.env().map_pick(ev.x, ev.y)


def flags_tap(ev):
    if ev.kind == "down":
        uitree_app.env().flag_tap(ev.x)


def sheet_tap(ev):
    uitree_app.env().sheet_pointer(ev.kind, ev.x, ev.y)


ui.hook("sync", sync, takes="arg")
ui.hook("home", home)
ui.hook("menu", menu, takes="arg")
ui.hook("colored", colored)
ui.hook("resized", sized)
ui.hook("grid", grid, takes="pointer")
ui.hook("map_tap", map_tap, takes="pointer")
ui.hook("flags_tap", flags_tap, takes="pointer")
ui.hook("sheet_tap", sheet_tap, takes="pointer")
for _a, _w, _i in TOOLS:
    if _a == "stamp":
        ui.action(_a, _w, (lambda v: lambda: _do(v))(_a), when="clip", off="grey")
    elif _a != "shape":
        ui.action(_a, _w, (lambda v: lambda: _do(v))(_a), icon=_i)
    else:
        ui.action(_a, _w, (lambda v: lambda: _do(v))(_a))
for _a, _w, _i in OPS:
    ui.action(_a, _w, (lambda v: lambda: _do(v))(_a), icon=_i)
ui.action("shifts", "Shift", lambda: _do("shifts"), icon="arrow_right")
ui.action("mirror", "Mirror", lambda: _do("mirror"), icon="mirror")
ui.action("clear", "Clear", lambda: _do("clear"), icon="del")
ui.action("prev", "Previous", lambda: _do("prev"))
ui.action("next", "Next", lambda: _do("next"))
ui.action("pickers", "Size", lambda: _do("pickers"))
ui.action("load", "Load", lambda: _do("load"), icon="folder_open")
ui.action("save", "Save", lambda: _do("save"), icon="save")
ui.action("files", "To Files", lambda: _do("files"), icon="export")
ui.action("close_pop", "Close", lambda: _do("close"), hint="Close")


def grid_keys(i):
    return uitree_app.env().grid_keys(i)


def flags_keys(i):
    return uitree_app.env().flags_keys(i)


def _draw_grid(cv, x, y, w, h):
    uitree_app.env().draw_grid(cv, x, y, w, h)


def _draw_map(cv, x, y, w, h):
    uitree_app.env().draw_map(cv, x, y, w, h)


def _draw_flags(cv, x, y, w, h):
    uitree_app.env().draw_flags(cv, x, y, w, h)


def _draw_preview(cv, x, y, w, h):
    uitree_app.env().draw_preview(cv, x, y, w, h)


def _draw_sheet(cv, x, y, w, h):
    uitree_app.env().draw_sheet(cv, x, y, w, h)


def _tools():
    ui.button("pen", kind="bar", alone=True, w="{pitch}", marked="tool=pen")
    ui.button("fill", kind="bar", alone=True, w="{pitch}", marked="tool=fill")
    ui.button("shape", icon="{shape_icon}", kind="bar", alone=True, w="{pitch}", marked="tool=shape")
    ui.button("select", kind="bar", alone=True, w="{pitch}", marked="tool=select")
    ui.button("stamp", icon="stamp", kind="bar", alone=True, w="{pitch}", marked="tool=stamp")
    ui.button("more", kind="bar", alone=True, w="{pitch}", marked="pop=more")


def _steps():
    # the sprite before and after, each its own stop: left and right walk
    # them and the row's other parts, A steps
    ui.button("prev", icon="back", kind="bar", alone=True)
    ui.label("{n}", size="text", align="center")
    ui.button("next", icon="forward", kind="bar", alone=True)


def sprite_page():
    with ui.page(""):
        ui.empty("No sprites", icon="art", lines=["This cart has no sprite sheet"], shown="none")
        with ui.row("head", pad="{pad}", gap="{gap}", shown="!none && !pane"):
            ui.label("Sprite {n}", tone="dim")
            _steps()
            ui.button("pickers", label="Size {size}", kind="bar", marked="pop=pickers")
        with ui.row("tools", pad="{pad}", gap=0, shown="!none && pane"):
            _tools()
        with ui.row("main", pad="{mpad}", gap="{gap}", shown="!none"):
            ui.canvas("grid", _draw_grid, w="{grid_w}", h="{grid_h}", keys=grid_keys, pointer="grid",
                      mark=False)
            with ui.grid(1, 1, w="{pal_w}", h="{pal_h}", gap=0, pad=0):
                ui.cells("color", first=0, count=16, cols=2, side="{sw}", clear=0, on="colored")
            ui.canvas("map", _draw_map, pointer="map_tap", shown="!pane")
        with ui.row("nav", pad="{pad}", gap="{gap}", shown="!none && pane"):
            _steps()
            ui.button("pickers", label="{size}", kind="bar", marked="pop=pickers")
            ui.label("64", align="end")
        ui.canvas("flags", _draw_flags, h="{flags_h}", keys=flags_keys, pointer="flags_tap",
                  mark=False, shown="!none && pane")
        ui.canvas("preview", _draw_preview, h="{preview_h}", shown="!none && pane && tall")
        with ui.row("rest", grow=True, shown="!none && !pane"):
            pass
        with ui.row("foot", pad="{pad}", gap=2, shown="!none && !pane"):
            _tools()
            with ui.row("worded", gap="{gap}", shown="words"):
                for a in ("load", "save", "files"):
                    ui.button(a)
            with ui.row("icons", gap=2, shown="!words"):
                for a, icon in (("load", "folder_open"), ("save", "save"), ("files", "export")):
                    ui.button(a, icon=icon, alone=True)
            ui.label("{status}", tone="dim")
        with ui.popover("more_pop", anchor="more", w="{more_w}", close="close_pop", shown="pop=more"):
            with ui.menu("", shown="!shifting"):
                ui.item("copy", label="Copy{k_copy}")
                ui.item("fliph", label="Flip across{k_fliph}")
                ui.item("flipv", label="Flip over{k_flipv}")
                ui.item("rot", label="Rotate{k_rot}")
                ui.item("shifts", shown="!@desk")
                ui.item("sleft", label="Shift left{k_sleft}", shown="@desk")
                ui.item("sright", label="Shift right{k_sright}", shown="@desk")
                ui.item("sup", label="Shift up{k_sup}", shown="@desk")
                ui.item("sdown", label="Shift down{k_sdown}", shown="@desk")
                ui.item("mirror", label="{mirrored?Turn off mirror:Turn on mirror}")
            with ui.menu("", shown="!shifting"):
                ui.item("clear", label="Clear{k_clear}", kind="danger")
            with ui.menu("", shown="shifting"):
                ui.item("sleft", label="Shift left{k_sleft}")
                ui.item("sright", label="Shift right{k_sright}")
                ui.item("sup", label="Shift up{k_sup}")
                ui.item("sdown", label="Shift down{k_sdown}")
        with ui.popover("pick_pop", anchor="pickers", w="{pick_w}", close="close_pop",
                        shown="pop=pickers"):
            ui.seg("Size", "sized", labels="SIZES", on="resized")
            ui.canvas("sheet", _draw_sheet, h="{sheet_h}", pointer="sheet_tap")
