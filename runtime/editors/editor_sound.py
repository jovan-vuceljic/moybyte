"""The desk Editor's Sound pane as a `uitree` page
(docs/media/look_2026-10/EDITOR_LAYOUT.md's Sound workspace): one sound of
the cart's bank as the wave brush (a swatch a wave, the step's own picked),
then a canvas of its pitch graph (16 steps a page over two octaves, the
selected step's note named), each step's wave under it and the volume
ladder, then the ops row (the step ops as icons, the octave and page
steppers). The rename popover hangs from the pane's header, and where no
Sounds list shows (800 x 480) the sounds menu does.

`SoundPane` (music_editor_ui.py) is the host, which the handlers and the
canvas's draw reach through `uitree_app.env()`: it writes the core's state
into the page's (`sync`), draws the graph and answers the pointer on it,
and does every verb over the `MusicEditor` core the handheld Music tab
edits, each its own undo step. The pane's header tools and its keys are the
desk's (`SoundPane.header`, `SoundPane.keys`)."""
import uitree as ui
import uitree_app
from audio import SFX_NAME_MAX

# The brush's order (EDITOR_LAYOUT.md's pictures), as wave ids
# (`audio.WAVE_*`): square, triangle, saw, pulse, organ, noise, phaser, tilted.
WAVES = (0, 1, 2, 4, 5, 3, 7, 6)
WAVE_WORDS = ("Square", "Triangle", "Saw", "Noise", "Pulse", "Organ", "Tilted", "Phaser")   # by id
# A wave's ink, a MOY64 index by wave id: on a light ground the deeper
# kin that holds 3:1 on white, on a dark one the colour itself; and the
# same as 0xRRGGBB, what the brush's swatches take (libmoy's MOY64).
WAVE_INK_DAY = (42, 3, 8, 5, 4, 45, 35, 13)
WAVE_INK_NIGHT = (12, 11, 8, 6, 9, 14, 10, 13)
WAVE_RGB_DAY = (0x2D8AE0, 0x008751, 0xFF004D, 0x5F574F, 0xAB5236, 0xE02DC4, 0x9E936A, 0x83769C)
WAVE_RGB_NIGHT = (0x29ADFF, 0x00E436, 0xFF004D, 0xC2C3C7, 0xFFA300, 0xFF77A8, 0xFFEC27, 0x83769C)

PAGE = 16                   # steps a page
SPAN = 24                   # semitones the graph shows: two octaves
LEVELS = 7                  # the ladder's lit levels; 0 is silence

# The ops row: (icon, its words, action), the delete a danger; then the
# octave's stepper and, where the sound runs past a page, the page's, the
# octave's only where the row holds both at STEPPER_W.
OPS = (("new", "Add a step", "add"), ("trash", "Delete the step", "del"),
       ("copy", "Copy the step", "copy"), ("paste", "Paste", "paste"),
       ("dup", "Duplicate the sound", "dup"), ("arrow_left", "Move earlier", "earlier"),
       ("arrow_right", "Move later", "later"), ("mute", "Rest", "rest"))
OP_W = 36                   # an op's button across
STEPPER_W = 96              # a stepper's room: its two chevrons and its value

s = ui.state(
    none=False,
    waves=ui.model(key="k", k="", rgb=0),
    brush=ui.row_of("waves"),
    word="", oct="", span="", paged=False, roomy=False,
    asking=ui.enum("none", "name", "menu", init="none"),
    f_name="", name_at="", name_w=300, menu_at="", menu_w=220,
    sounds=ui.model(key="k", k="", label="", icon=""),
)


def wave_ink(th, wv):
    t = WAVE_INK_DAY if th.get("surface_light", False) else WAVE_INK_NIGHT
    return t[wv & 7]


def row_label(me, k):
    """A sound's row: its number, and its name where it has one."""
    name = getattr(me.bank.sfx[k], "name", None)
    return "%d  %s" % (k, name) if name else "%d" % k


def sync(vals):
    """The host's values: (no bank, the brush's swatches, the wave
    picked, its word, the octave's word, the page's span, whether the
    sound runs past a page, whether the ops row holds both steppers)."""
    s.none, rows, brush, s.word, s.oct, s.span, s.paged, s.roomy = vals
    if s.waves != rows:
        s.waves = rows
    if s.brush != brush:
        s.brush = brush


def rename_open(arg):
    """The name popover, from the host: (the name, where it hangs, its width)."""
    s.f_name, s.name_at, s.name_w = arg
    s.asking = "name"
    ui.focus("f_name")


def menu_open(arg):
    """The sounds menu, from the host: (its rows, where it hangs, its width)."""
    s.sounds, s.menu_at, s.menu_w = arg
    s.asking = "menu"


def close():
    s.asking = "none"


def named():
    uitree_app.env().set_name(s.f_name)
    s.asking = "none"


def picked(row):
    s.asking = "none"
    uitree_app.env().pick_sound(int(row.k))


def brushed():
    uitree_app.env().set_brush(int(s.brush))


def graph(ev):
    uitree_app.env().graph_pointer(ev.kind, ev.x, ev.y)


def _do(op):
    uitree_app.env().act(op)


ui.hook("sync", sync, takes="arg")
ui.hook("rename_open", rename_open, takes="arg")
ui.hook("menu_open", menu_open, takes="arg")
ui.hook("brushed", brushed)
ui.hook("graph", graph, takes="pointer")
ui.action("close", "Close", close)
ui.action("named", "Name", named)
ui.action("pick", "Open", picked, takes="row")
ui.action("oct_down", "Lower", lambda: _do("oct-"))
ui.action("oct_up", "Higher", lambda: _do("oct+"))
ui.action("page_down", "Earlier steps", lambda: _do("page-"))
ui.action("page_up", "Later steps", lambda: _do("page+"))
for _i, _w, _op in OPS:
    ui.action(_op, _w, (lambda v: lambda: _do(v))(_op))


def _draw_graph(cv, x, y, w, h):
    uitree_app.env().draw_graph(cv, x, y, w, h)


def sound_page():
    with ui.page(""):
        ui.empty("No sound", icon="music", lines=["This cart has no sound bank"], shown="none")
        with ui.row("brush", pad=12, shown="!none"):
            ui.seg("Wave  {word}", "brush", text="{.rgb}", look="swatches", on="brushed")
        ui.canvas("graph", _draw_graph, pointer="graph", shown="!none")
        with ui.row("ops", pad=12, shown="!none"):
            for icon, _w, op in OPS:
                ui.button(op, icon=icon, alone=True, w=OP_W, kind="danger" if op == "del" else "normal")
            with ui.row("oct_step", pad=8, shown="!paged || roomy"):
                ui.stepper("{oct}", "oct_down", "oct_up", tone="dim", grow=True)
            with ui.row("page_step", pad=8, shown="paged"):
                ui.stepper("{span}", "page_down", "page_up", tone="dim", grow=True)
        with ui.popover("sound_name", at="{name_at}", w="{name_w}", close="close", shown="asking=name"):
            ui.field("Name", "f_name", max=SFX_NAME_MAX, on="named", hint="no name")
        with ui.popover("sound_menu", at="{menu_at}", w="{menu_w}", close="close", shown="asking=menu"):
            with ui.rows("sounds"):
                ui.link("pick", label="{.label}", icon="{.icon}")


DESK_PAGES = (sound_page,)
