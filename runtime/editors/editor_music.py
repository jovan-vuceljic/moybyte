"""The handheld Editor's Music tab as a `uitree` page
(docs/media/look_2026-10/EDITOR_LAYOUT.md's `music` pictures): Sound and
Song as tabs, the sound or the song being edited between its chevrons (a
sound by its number and its name, moy-spec's optional `name`), its speed,
whose popover holds a slider, the steps (a song's slots) as a table whose
canvas draws each row -- its number, its step (or its slot's sound) and a
step's volume meter -- the edit pad, and the foot's Hear, Loop and the step
count.

`MusicEditorUI` (music_editor_ui.py) is the host, which the handlers and
the rows' draw reach through `uitree_app.env()`: it writes the core's
state into the page's (`sync`), draws the table's rows (`draw_row`) and
does what the handlers ask over the core (`MusicEditor`), every edit its
undo step. The keys are the host's (up and down the cursor, left and right
its value, A hears it) but while the popover is open."""
import uitree as ui
import uitree_app

s = ui.state(
    none=False, song=False, view=ui.enum("sound", "song", init="sound"),
    name="", speed=1, pad_w=124, pop=False, playing=False, looping=False, count="",
    steps=ui.model(key="k", k="", a="", b="", c="", lit=0),
    at=ui.row_of("steps"),
)

ui.labels("VIEWS", {"sound": "Sound", "song": "Song"})

# The pad, two to a row: (action, its word, icon, the view it shows in, its kind).
PAD = (
    ("lower", "{song?Sfx:Note}", "{song?back:arrow_down}", "", "normal"),
    ("higher", "{song?Sfx:Note}", "{song?forward:arrow_up}", "", "normal"),
    ("wave", "Wave", "rotate", "!song", "normal"),
    ("vol", "Vol", "volume", "!song", "normal"),
    ("rest", "Rest", "mute", "!song", "normal"),
    ("add", "Add", "new", "", "normal"),
    ("dup", "Dup", "dup", "", "normal"),
    ("del", "Del", "del", "", "danger"),
    ("copy", "Copy", "copy", "", "normal"),
    ("paste", "Paste", "paste", "", "normal"),
    ("up", "Up", "to_front", "", "normal"),
    ("down", "Down", "to_back", "", "normal"),
)


def sync(vals):
    """The host's values: (no bank, the song view, the name, the speed,
    the preview playing, the loop, the count, the rows, the cursor's row,
    the pad's width in pixels)."""
    (s.none, s.song, s.name, s.speed, s.playing, s.looping, s.count, rows, at, s.pad_w) = vals
    v = "song" if s.song else "sound"
    if s.view != v:
        s.view = v
    if s.steps != rows:
        s.steps = rows
    if s.at != at:
        s.at = at


def closed():
    """The popover let go (B, a tap outside it)."""
    s.pop = False


def _do(verb):
    uitree_app.env().act(verb)


def view():
    uitree_app.env().set_view(s.view == "song")


def picked(row):
    uitree_app.env().pick(row.k)


def set_speed():
    uitree_app.env().set_speed(s.speed)


def speed():
    s.pop = not s.pop
    if s.pop:
        ui.focus("speed_value")


ui.hook("sync", sync, takes="arg")
ui.hook("view_moved", view)
ui.hook("picked", picked, takes="row")
ui.hook("set_speed", set_speed)
ui.action("pop_close", "Close", closed)
ui.action("speed_open", "Speed", speed)
ui.action("prev", "Previous", lambda: _do("prev"))
ui.action("next", "Next", lambda: _do("next"))
ui.action("hear", "Hear", lambda: _do("hear"))
ui.action("loop", "Loop", lambda: _do("loop"))
for _a, _w, _i, _sh, _k in PAD:
    ui.action(_a, _a[:1].upper() + _a[1:], (lambda v: lambda: _do(v))(_a))


def _draw_row(cv, x, y, w, h, row):
    uitree_app.env().draw_row(cv, int(row.k), x, y, w, h)


def music_page():
    with ui.page(""):
        ui.empty("No sounds", icon="music", lines=["This cart has no sound bank"], shown="none")
        with ui.row("head", pad=4, gap=6, shown="!none"):
            ui.tabs("view", "VIEWS", on="view_moved")
            ui.stepper("{name}", "prev", "next")
            ui.button("speed_open", label="Speed {speed}", kind="bar", marked="pop")
        with ui.row("body", grow=True, shown="!none"):
            with ui.table("steps", cur="at", row=17, changed="picked"):
                ui.canvas("step", _draw_row)
            with ui.grid(2, 6, w="{pad_w}", h=152, gap="s"):
                for a, word, icon, shown, kind in PAD:
                    if shown:
                        ui.button(a, label=word, icon=icon, kind=kind, shown=shown)
                    else:
                        ui.button(a, label=word, icon=icon, kind=kind)
        ui.rule(shown="!none")
        with ui.row("foot", pad=4, shown="!none"):
            ui.button("hear", label="{playing?Stop:Hear}", icon="{playing?close:music}", marked="playing")
            ui.button("loop", label="Loop", icon="loop", marked="looping")
            ui.label("{count}", tone="dim", align="end")
        with ui.popover("speed_pop", anchor="speed_open", w=180, close="pop_close", shown="pop"):
            ui.slider("Speed", "speed", 1, 30, on="set_speed", focus="pop")
