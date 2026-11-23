"""The Editor's Scene tab, the placement editor, as a placed `uitree` page:
the handheld's tab and a desk Editor's Scene pane alike
(docs/media/look_2026-10/EDITOR_LAYOUT.md's `scene` pictures).

The handheld's: the world (the view) from the content rect's top left;
beside it the picked actor -- its tag and sprite, its place, then Tag,
Flip, Front, Back and Remove -- or, under the stamp tool, the sprites a
page at a time (‹ 1 / 4 ›) and the tag a stamp gives, or with nothing
picked what a tap does; under both the pick and stamp tools, Snap, the
zoom and the scene's name. A tag is typed in a popover's field. The desk
pane's (its tools the pane header's, the actor and the stamps panes of
their own): the view alone.

`SceneEditorUI` (scene_editor_ui.py) is the host, which the handlers and
the canvases reach through `uitree_app.env()`: it writes the editor's
state into the page's (`sync`), draws the view, the actor's sprite and the
stamps, takes their presses (in the view a tap picks an actor, a drag
moves it or pans, and under the stamp tool a tap on empty world places
one; a tap on a stamp picks it) and their keys (the arrows nudge the
picked actor or pan, A steps the zoom; the arrows move along the stamps),
and does what the handlers ask over its `SceneEditor`."""
import uitree as ui
import uitree_app

s = ui.state(
    none=False, pane=False,
    tool=ui.enum("pick", "stamp", init="pick"),
    side=ui.enum("nothing", "actor", "stamps", init="nothing"),
    pop=ui.enum("none", "tag", "stamp", init="none"),
    snap_on=False, tag_word="", place="", spage="1 / 1", first=True, last=True, stamp_word="thing",
    zoom_word="1x", name="", tag_text="", stamp_text="",
    view_w=216, stamps_h=96, stag_on=True, hint_on=True, roomy=True, pitch=24, pad=6, pop_w=150,
)


def sync(vals):
    """The host's values: (no scene, the desk's pane, the tool, what the
    column shows, the popover, snap on, the picked actor's tag and place,
    the stamps' first page and their last and the pager's words, the
    stamp's tag, the zoom's word, the scene's name, and the host's
    measures: the view's width (pixels), the stamps' height (the page's
    unit), the lines under them the column holds, a tool's pitch (the
    page's unit), the column's pad and the popover's width (pixels))."""
    (s.none, s.pane, tool, side, pop, s.snap_on, s.tag_word, s.place, s.first, s.last, s.spage, s.stamp_word,
     s.zoom_word, s.name, s.view_w, s.stamps_h, lines, s.roomy, s.pitch, s.pad, s.pop_w) = vals
    s.stag_on, s.hint_on = lines > 0, lines > 1
    if s.tool != tool:
        s.tool = tool
    if s.side != side:
        s.side = side
    if s.pop != pop:
        s.pop = pop


def home():
    """The view takes the keys."""
    ui.focus("view")


def typing(text):
    """The open popover's field holds `text` and the keys."""
    if s.pop == "tag":
        s.tag_text = text
        ui.focus("tag_text")
    else:
        s.stamp_text = text
        ui.focus("stamp_text")


def _do(verb):
    uitree_app.env().act(verb)


def view_press(ev):
    uitree_app.env().view_pointer(ev.kind, ev.x, ev.y)


def stamp_press(ev):
    if ev.kind == "down":
        uitree_app.env().brush_tap(ev.x, ev.y)


def tag_ok():
    uitree_app.env().tagged(s.tag_text)


def stamp_ok():
    uitree_app.env().tagged(s.stamp_text)


ui.hook("sync", sync, takes="arg")
ui.hook("home", home)
ui.hook("typing", typing, takes="arg")
ui.hook("view_press", view_press, takes="pointer")
ui.hook("stamp_press", stamp_press, takes="pointer")
ui.action("pick", "Pick", lambda: _do("pick"), icon="pointer")
ui.action("stamp", "Stamp", lambda: _do("stamp"), icon="stamp")
ui.action("snap", "Snap", lambda: _do("snap"), icon="grid")
ui.action("zoom", "Zoom", lambda: _do("zoom"), icon="search")
ui.action("tag", "Tag", lambda: _do("tag"), icon="notes")
ui.action("flip", "Flip", lambda: _do("flip"), icon="flip")
ui.action("front", "Front", lambda: _do("front"), icon="arrow_up")
ui.action("back", "Back", lambda: _do("back"), icon="arrow_down")
ui.action("remove", "Remove", lambda: _do("remove"), icon="del")
ui.action("stamp_tag", "Stamp tag", lambda: _do("stamp_tag"))
ui.action("sprev", "Previous stamps", lambda: _do("sprev"), when="!first", off="grey")
ui.action("snext", "Next stamps", lambda: _do("snext"), when="!last", off="grey")
ui.action("tag_ok", "Use", tag_ok)
ui.action("stamp_ok", "Use", stamp_ok)
ui.action("close_pop", "Close", lambda: _do("close"), hint="Close")


def view_keys(i):
    return uitree_app.env().view_keys(i)


def stamp_keys(i):
    return uitree_app.env().brush_keys(i)


def _draw_view(cv, x, y, w, h):
    uitree_app.env().draw_view(cv, x, y, w, h)


def _draw_sprite(cv, x, y, w, h):
    uitree_app.env().draw_sprite(cv, x, y, w, h)


def _draw_stamps(cv, x, y, w, h):
    uitree_app.env().draw_brushes(cv, x, y, w, h)


def _nothing():
    with ui.row("none_row", pad="{pad}"):
        ui.label("Nothing picked", wrap="word", lines=2)
    with ui.row("none_help", pad="{pad}"):
        ui.label("Tap an actor to change it, or take the stamp to place one", tone="dim",
                 wrap="word", lines=4)


def _actor():
    with ui.row("who", pad="{pad}"):
        ui.label("{tag_word}", face="title")
        ui.canvas("sprite", _draw_sprite, w=26, h=26, mark=False)
    with ui.row("where", pad="{pad}"):
        ui.label("{place}", tone="dim")
    ui.rule()
    with ui.menu("", shown="roomy"):
        ui.item("tag")
        ui.item("flip")
        ui.item("front")
        ui.item("back")
        ui.item("remove", mkind="danger")
    with ui.row("verbs", pad="{pad}", wrap=True, shown="!roomy"):
        ui.button("tag", kind="bar", alone=True, w="{pitch}")
        ui.button("flip", kind="bar", alone=True, w="{pitch}")
        ui.button("front", kind="bar", alone=True, w="{pitch}")
        ui.button("back", kind="bar", alone=True, w="{pitch}")
        ui.button("remove", kind="bar", alone=True, w="{pitch}")


def _stamps():
    ui.canvas("stamps", _draw_stamps, h="{stamps_h}", keys=stamp_keys, pointer="stamp_press",
              mark=False)
    with ui.row("pager", pad="{pad}"):
        ui.stepper("{spage}", "sprev", "snext", grow=True)
    with ui.row("stag_row", pad="{pad}", shown="stag_on"):
        ui.label("Tag", tone="dim")
        ui.button("stamp_tag", label="{stamp_word}", grow=True)
    with ui.row("place_row", pad="{pad}", shown="hint_on"):
        ui.label("Tap to place", tone="dim")


def scene_page():
    with ui.page(""):
        ui.empty("No scene", icon="scene", lines=["This cart has no sprites to place"], shown="none")
        with ui.row("main", grow=True, gap=0, shown="!none"):
            ui.canvas("view", _draw_view, w="{view_w}", keys=view_keys, pointer="view_press", mark=False)
            ui.switch("side", {"nothing": _nothing, "actor": _actor, "stamps": _stamps},
                      shown="!pane")
        ui.rule(shown="!none && !pane")
        with ui.row("foot", pad=2, gap=0, shown="!none && !pane"):
            ui.button("pick", kind="bar", alone=True, w="{pitch}", marked="tool=pick")
            ui.button("stamp", kind="bar", alone=True, w="{pitch}", marked="tool=stamp")
            ui.rule()
            with ui.row("chips", gap=4):
                ui.button("snap", marked="snap_on")
                ui.button("zoom", label="{zoom_word}")
            with ui.row("rest"):
                pass
            ui.label("{name}", tone="dim", align="end")
        with ui.popover("tag_pop", anchor="where", w="{pop_w}", close="close_pop", shown="pop=tag"):
            ui.field("Tag", "tag_text", max=16, on="tag_ok", hint="coin")
        with ui.popover("stamp_pop", anchor="stamp_tag", w="{pop_w}", close="close_pop",
                        shown="pop=stamp"):
            ui.field("Tag", "stamp_text", max=16, on="stamp_ok", hint="coin")
