"""The desk Editor's own panes as a placed `uitree` page, one page a pane
(docs/media/look_2026-10/EDITOR_LAYOUT.md's World, Art and Code
workspaces): the World's Actor (the picked actor's tag, the tags the scene
uses, Flip, Front, Back, its tile and place, and Remove; with nothing
picked, what to do), the Sheet (two pages of the sprite sheet at 2x, the
current sprite ringed), the Reference's Sprites (the Sheet over the call a
pick puts at the Code pane's caret, and Insert), the Stamps (the Sheet
over the tag a stamp gives) and the code the blocks make (read only,
numbered).

`editor_parts.PartHost` is the host, which the handlers and the sheet's
canvas reach through `uitree_app.env()`: it writes the editor cores'
state into the page's (`sync`), draws the sheet and takes its presses and
arrows, and does what the handlers ask over the cores the handheld's tabs
edit (`SceneEditor`)."""
import uitree as ui
import uitree_app

s = ui.state(
    part=ui.enum("actor", "sheet", "sprites", "stamps", "made", init="actor"),
    picked=False, tag="", tags=ui.model(key="k", k=""), tag_at=ui.row_of("tags"), many=False,
    flip=False, place="", stamp="thing", call="", made="", roomy=True,
)


def sync(vals):
    """The host's values, where one moved: the part, an actor picked, its
    tag, the scene's tags and the actor's among them ("" none), its flip
    and its place, the stamp's tag, the Reference's call, the made code,
    and whether Front and Back have room for their words (else they are
    their icons)."""
    part, s.picked, s.tag, tags, at, s.flip, s.place, s.stamp, s.call, s.made, s.roomy = vals
    if s.part != part:
        s.part = part
    s.tags = [dict(k=t) for t in tags]
    s.many = bool(tags)
    if s.tag_at != at:
        s.tag_at = at


def home():
    """The sheet takes the keys where the pane shows it."""
    if s.part in ("sheet", "sprites", "stamps"):
        ui.focus("sheet")


def _act(verb, *args):
    uitree_app.env().act(verb, *args)


def tag_set():
    _act("tag", s.tag)


def tag_pick():
    _act("tag", s.tag_at)


def sheet_keys(i):
    return uitree_app.env().sheet_keys(i)


def sheet_press(ev):
    uitree_app.env().sheet_pointer(ev.kind, ev.x, ev.y)


def _draw_sheet(cv, x, y, w, h):
    uitree_app.env().draw_sheet(cv, x, y, w, h)


ui.hook("sync", sync, takes="arg")
ui.hook("home", home)
ui.hook("sheet_press", sheet_press, takes="pointer")
ui.action("tag_set", "Tag", tag_set)
ui.action("tag_pick", "Tag", tag_pick)
ui.action("flip_set", "Flip", lambda: _act("flip"))
ui.action("front", "Front", lambda: _act("front"))
ui.action("back", "Back", lambda: _act("back"))
ui.action("front_i", "Front", lambda: _act("front"), icon="to_front")
ui.action("back_i", "Back", lambda: _act("back"), icon="to_back")
ui.action("remove", "Remove", lambda: _act("remove"))
ui.action("remove_i", "Remove", lambda: _act("remove"), icon="trash")
ui.action("insert", "Insert", lambda: _act("insert"))


def _none():
    ui.empty("No actor picked", icon="scene", lines=["Tap one in the scene to change it"])


def _picked():
    with ui.row("tag_row", pad=10):
        ui.field("Tag", "tag", 16, commit=True, changed="tag_set", grow=True)
    with ui.row("tags_row", pad=10, shown="many"):
        ui.seg("Tags", "tag_at", text="{.k}", on="tag_pick")
    with ui.row("verbs", pad=10, gap=8):
        ui.toggle("Flip", "flip", on="flip_set")
        ui.button("front", shown="roomy")
        ui.button("back", shown="roomy")
        ui.button("front_i", icon="to_front", kind="bar", alone=True, w=36, shown="!roomy")
        ui.button("back_i", icon="to_back", kind="bar", alone=True, w=36, shown="!roomy")
    with ui.row("where", pad=10, gap=8):
        ui.label("{place}", tone="dim", size="text")
        ui.row("where_gap", grow=True)
        ui.button("remove", kind="danger", shown="roomy")
        ui.button("remove_i", icon="trash", kind="bar", alone=True, w=36, shown="!roomy")


def _actor():
    ui.switch("picked", {False: _none, True: _picked})


def _sheet():
    ui.canvas("sheet", _draw_sheet, keys=sheet_keys, pointer="sheet_press", mark=False)


def _sprites():
    _sheet()
    with ui.row("call_row", pad=10, gap=8):
        ui.label("{call}", tone="dim", size="text")
        ui.row("call_gap", grow=True)
        ui.button("insert")


def _stamps():
    _sheet()
    with ui.row("stamp_row", pad=10):
        ui.label("A stamp makes a {stamp}", tone="dim")


def _made():
    ui.text_view("made", syntax="python", gutter=True)


def part_page():
    with ui.page(""):
        ui.switch("part", {"actor": _actor, "sheet": _sheet, "sprites": _sprites, "stamps": _stamps,
                           "made": _made})


# The page only a desk opens: a board with no desk carries none compiled (tools/uitree_compile.py).
DESK_PAGES = (part_page,)
