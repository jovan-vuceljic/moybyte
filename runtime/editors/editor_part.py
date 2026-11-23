"""The desk Editor's own panes as a placed `uitree` page, one page a pane
(docs/media/look_2026-10/EDITOR_LAYOUT.md's World, Art, Code and Sound
workspaces): the World's Actor (the picked actor's tag, the tags the scene
uses, Flip, Front, Back, its tile and place, and Remove; with nothing
picked, what to do), the Sheet (two pages of the sprite sheet at 2x, the
current sprite ringed), the Reference's Sprites (the Sheet over the call a
pick puts at the Code pane's caret, and Insert), Sounds (a row a sound,
its sketch and play tool, over `sfx(n)` and Insert), Map (the cart's map at
1x, a cell picked by a press or the arrows, over `mget(x, y)` and Insert)
and Log (the run's and the code's errors, each to its line), the Stamps
(the Sheet over the tag a stamp gives), the code the blocks make (read
only, numbered), a blocks cart's palette (the categories in two columns by
their colours, then the current one's blocks), and the Sound workspace's
Sounds list (the Song, then a row a sound) and Song (its verbs, then its
slots four a row).

`editor_parts.PartHost` is the host, which the handlers and the canvases
reach through `uitree_app.env()`: it writes the editor cores' state into
the page's (`sync`), draws the canvases and takes their presses and
arrows, and does what the handlers ask over the cores the handheld's tabs
edit (`SceneEditor`, `MusicEditor`, the blocks)."""
import uitree as ui
import uitree_app

# The palette's categories (the insert menu's, block_editor_ui._CAT_LABEL)
# in the pictures' order, read across two columns.
CATS = (("events", "When..."), ("control", "Control"), ("draw", "Draw"),
        ("input", "Buttons"), ("variables", "Variables"), ("lists", "Lists"),
        ("actors", "Sprite"), ("looks", "Looks"), ("operators", "Math"),
        ("sound", "Sound"), ("myblocks", "My Blocks"))

s = ui.state(
    part=ui.enum("actor", "sheet", "sprites", "stamps", "made", "palette", "sounds", "ref_sounds",
                 "song", "maps", "log", init="actor"),
    picked=False, tag="", tags=ui.model(key="k", k=""), tag_at=ui.row_of("tags"), many=False,
    flip=False, place="", stamp="thing", call="", made="", roomy=True,
    # the palette: the categories in two columns (where a name would not fit its half, a cycle
    # of them), the current one's blocks or why there are none
    blocks=False, cat="", cats_h=168, cats=ui.model(key="k", k="", label=""), cat_at=ui.row_of("cats"),
    cats_fold=False,
    items=ui.model(key="k", k=""), item=ui.row_of("items"), note="",
    # the sounds (the Sound workspace's list, the Reference's) and the song
    row_h=28, bank=False, snds=ui.model(key="k", k="", on=False), snd=ui.row_of("snds"), song_line="", del_ok=False, playing=False, many_songs=False,
    # the Reference's map and log
    has_map=False, errs=ui.model(key="k", k="", label=""), err=ui.row_of("errs"),
)


def sync(vals):
    """The host's values for the part it shows, where they moved: the
    part, then its own (`_SYNC`)."""
    part, got = vals
    if s.part != part:
        s.part = part
    _SYNC[part](got)


def _actor_sync(vals):
    """An actor picked, its tag, the scene's tags and the actor's among
    them ("" none), its flip and its place, and whether Front and Back have
    room for their words (else they are their icons)."""
    s.picked, s.tag, tags, at, s.flip, s.place, s.roomy = vals
    s.tags = [dict(k=t) for t in tags]
    s.many = bool(tags)
    if s.tag_at != at:
        s.tag_at = at


def _stamps_sync(vals):
    s.stamp = vals


def _sprites_sync(vals):
    s.call = vals


def _made_sync(vals):
    s.made = vals


def _palette_sync(vals):
    """A program opened, the current category, the categories' height
    and whether they fold into a cycle, a row's, the count of the
    category's blocks and the note standing in for them ("" none)."""
    s.blocks, s.cat, s.cats_h, s.cats_fold, s.row_h, items, s.note = vals
    if not s.cats:
        s.cats = [dict(k=k, label=label) for k, label in CATS]
    if s.cat_at != s.cat:
        s.cat_at = s.cat
    s.items = [dict(k=str(n)) for n in range(items)]


def _sounds_sync(vals):
    """A bank, a row's height, the rows (key, current), the current one's
    key (where the keys rest), and the call a pick inserts."""
    s.bank, s.row_h, rows, cur, s.call = vals
    s.snds = [dict(k=k, on=on) for k, on in rows]
    if cur and s.snd != cur:
        s.snd = cur


def _song_sync(vals):
    """A bank, the song's line, whether a slot can go, a song plays,
    whether the cart has more than one song, and whether the line has room
    beside the tools (else it is a row over them)."""
    s.bank, s.song_line, s.del_ok, s.playing, s.many_songs, s.roomy = vals


def _maps_sync(vals):
    s.has_map, s.call = vals


def _log_sync(vals):
    s.errs = [dict(k=str(n), label=t) for n, t in enumerate(vals)]


_SYNC = {"actor": _actor_sync, "sheet": lambda v: None, "sprites": _sprites_sync,
         "stamps": _stamps_sync, "made": _made_sync, "palette": _palette_sync,
         "sounds": _sounds_sync, "ref_sounds": _sounds_sync, "song": _song_sync,
         "maps": _maps_sync, "log": _log_sync}


def home():
    """The canvas a pane shows takes the keys."""
    if s.part in ("sheet", "sprites", "stamps"):
        ui.focus("sheet")
    elif s.part == "maps":
        ui.focus("map")
    elif s.part == "song":
        ui.focus("slots")
    elif s.part == "palette":
        ui.focus("cat_at" if s.cats_fold else "cats")


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


def snd_moved(row):
    """The keys moved onto a sounds row: it is picked."""
    _act("sound", row.k)


def snd_keys(i, row):
    """Enter on a sounds row picks it."""
    if i.pressed("a"):
        _act("sound", row.k)
        return True
    return False


def _draw_snd(cv, x, y, w, h, row):
    uitree_app.env().draw_snd(cv, x, y, w, h, row.k)


def snd_press(ev):
    if ev.row is not None:
        uitree_app.env().snd_pointer(ev.kind, ev.x, ev.y, ev.row.k)


def _draw_item(cv, x, y, w, h, row):
    uitree_app.env().draw_item(cv, x, y, w, h, row.k)


def item_keys(i, row):
    """Enter on a block puts it at the Blocks pane's cursor."""
    if i.pressed("a"):
        _act("block", row.k)
        return True
    return False


def item_press(ev):
    if ev.kind == "up" and ev.row is not None:
        _act("block", ev.row.k)


def _draw_cats(cv, x, y, w, h):
    uitree_app.env().draw_cats(cv, x, y, w, h)


def cats_keys(i):
    return uitree_app.env().cats_keys(i)


def cats_press(ev):
    uitree_app.env().cats_pointer(ev.kind, ev.x, ev.y)


def _err(row):
    if row is not None:
        _act("goto", int(row.k))


def _draw_slots(cv, x, y, w, h):
    uitree_app.env().draw_slots(cv, x, y, w, h, ui.text_size("0", getattr(cv, "font_scale", 1))[1])


def slots_keys(i):
    return uitree_app.env().slots_keys(i)


def slots_press(ev):
    uitree_app.env().slots_pointer(ev.kind, ev.x, ev.y)


def _draw_map(cv, x, y, w, h):
    uitree_app.env().draw_map(cv, x, y, w, h)


def map_keys(i):
    return uitree_app.env().map_keys(i)


def map_press(ev):
    uitree_app.env().map_pointer(ev.kind, ev.x, ev.y)


ui.hook("sync", sync, takes="arg")
ui.hook("home", home)
ui.hook("sheet_press", sheet_press, takes="pointer")
ui.hook("slots_press", slots_press, takes="pointer")
ui.hook("map_press", map_press, takes="pointer")
ui.hook("snd_press", snd_press, takes="pointer")
ui.hook("snd_moved", snd_moved, takes="row")
ui.hook("cats_press", cats_press, takes="pointer")
ui.hook("item_press", item_press, takes="pointer")
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
ui.action("cat_set", "Category", lambda: _act("cat", s.cat_at))
ui.action("goto", "Go to", _err, takes="row")
# the Song's line, left to right as it stands
SONG_TOOLS = (("song_prev", "Previous song", "back", "song-"), ("song_next", "Next song", "forward", "song+"),
              ("slot_prev", "Previous sound", "back", "slot-"), ("slot_next", "Next sound", "forward", "slot+"),
              ("slot_add", "Add slot", "new", "add"), ("slot_del", "Delete slot", "del", "del"))
for _a, _w, _i, _op in SONG_TOOLS:
    ui.action(_a, _w, (lambda v: lambda: _act("song", v))(_op), icon=_i,
              when="del_ok" if _op == "del" else None, off="grey" if _op == "del" else None)
ui.action("song_play", "Play", lambda: _act("song", "play"), icon="run")


def _none():
    ui.empty("No actor picked", icon="scene", lines=["Tap one in the scene to change it"])


def _picked():
    with ui.row("tag_row", pad=10):
        ui.field("Tag", "tag", 16, commit=True, changed="tag_set", grow=True)
    with ui.row("tags_head", pad=10, shown="many && !roomy"):
        ui.label("Tags")
        ui.row("tags_gap", grow=True)
    with ui.row("tags_row", pad=10, shown="many"):
        ui.seg("{roomy?Tags:}", "tag_at", text="{.k}", on="tag_pick")
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


def _palette():
    ui.empty("No blocks", icon="blocks", lines=["This cart's blocks did not open"], shown="!blocks")
    ui.canvas("cats", _draw_cats, h="{cats_h}", keys=cats_keys, pointer="cats_press", mark=False,
              shown="blocks && !cats_fold", hint="Open")
    with ui.row("cats_row", pad=6, shown="blocks && cats_fold"):
        ui.seg("", "cat_at", text="{.label}", look="cycle", on="cat_set")
    ui.rule(shown="blocks")
    with ui.row("note_row", pad=10, shown="blocks && note"):
        ui.label("{note}", tone="dim", wrap="word", lines=4)
    with ui.scroll("items_view", shown="blocks && !note"):
        with ui.rows("items", cur="item"):
            ui.canvas("item", _draw_item, h="{row_h}", keys=item_keys, pointer="item_press", mark=False,
                      hint="Add")


def _sounds():
    ui.empty("No sounds", icon="music", lines=["This cart has no sound bank"], shown="!bank")
    with ui.scroll("snds_view", shown="bank"):
        with ui.rows("snds", cur="snd", changed="snd_moved"):
            ui.canvas("snd", _draw_snd, h="{row_h}", keys=snd_keys, pointer="snd_press", mark=False,
                      hint="Pick")


def _ref_sounds():
    _sounds()
    with ui.row("snd_call", pad=10, gap=8, shown="bank"):
        ui.label("{call}", tone="dim", size="text")
        ui.row("snd_call_gap", grow=True)
        ui.button("insert")


def _song():
    with ui.row("song_line_row", pad=10, shown="bank && !roomy"):
        ui.label("{song_line}", tone="dim", size="text")
    with ui.row("song_head", pad=10, gap=0, shown="bank"):
        ui.label("{song_line}", tone="dim", size="text", shown="roomy")
        ui.row("song_gap", grow=True)
        for a, _w, icon, op in SONG_TOOLS:
            ui.button(a, icon=icon, kind="bar", alone=True, w=32,
                      shown="many_songs" if op in ("song-", "song+") else None)
        ui.button("song_play", icon="run", kind="bar", alone=True, w=32, marked="playing")
    ui.canvas("slots", _draw_slots, keys=slots_keys, pointer="slots_press", mark=False, shown="bank",
              hint="Edit")


def _maps():
    ui.empty("No map", icon="map", lines=["This cart has no map yet"], shown="!has_map")
    ui.canvas("map", _draw_map, keys=map_keys, pointer="map_press", mark=False, shown="has_map")
    with ui.row("map_call", pad=10, gap=8, shown="has_map"):
        ui.label("{call}", tone="dim", size="text")
        ui.row("map_call_gap", grow=True)
        ui.button("insert")


def _log():
    ui.empty("Nothing logged", icon="doc", lines=["Your game's errors show here, with their line"],
             shown="!errs")
    with ui.scroll("errs_view", shown="errs"):
        with ui.rows("errs", cur="err"):
            ui.link("goto", label="{.label}")


def part_page():
    with ui.page(""):
        ui.switch("part", {"actor": _actor, "sheet": _sheet, "sprites": _sprites, "stamps": _stamps,
                           "made": _made, "palette": _palette, "sounds": _sounds,
                           "ref_sounds": _ref_sounds, "song": _song, "maps": _maps, "log": _log})


# The page only a desk opens: a board with no desk carries none compiled (tools/uitree_compile.py).
DESK_PAGES = (part_page,)
