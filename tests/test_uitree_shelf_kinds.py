"""The C engine's kinds and props a shelf of carts draws with (Get Carts'
design), each held on a page of its own from the Python front: a card's
badge= and tone=, a cards list's pad=, a group's look="card", the toast."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "uitree_fixtures")]

import uitree_parity as P  # noqa: E402

TDECK = "tdeck_320x240_fs1_dark"
DESK = "p4_1024x600_fs2_windowed"

HEAD = '''
import uitree as ui

s = ui.state(carts=ui.model(key="i", i="", name="", badge="", tone=""), on=False, n=0,
             text="Line one", toast="", kind="normal")


def opened():
    s.carts = [dict(i=str(i), name="Cart %d" % i, badge="", tone="") for i in range(4)]


def flip():
    s.on = not s.on


def tap(row):
    s.n = s.n + 1


ui.hook("opened", opened)
ui.action("flip", "Flip", flip, keys=("f",))
ui.action("tap", "Tap", tap, takes="row")
'''


def run(tmp_path, build, script=(), config=TDECK, boxes=(), name="shelf"):
    """The settled frames of a page whose module is HEAD and `build`'s source
    after each step of `script`; each frame's state the boxes of the stops
    `boxes` names, as the toolkit drew them."""
    import uitree_app
    import uitree_c
    import uitree_conf as C
    app_py = tmp_path / name / "app.py"
    app_py.parent.mkdir()
    app_py.write_text(HEAD + build)
    mod = C._module(str(app_py))
    cls = uitree_app.app_layer(name + "_c", name.title(), mod.build, engine=uitree_c.CEngine)
    seen = {}

    def opened(ws):
        seen["app"] = P.host(ws, cls)
        seen["ws"] = ws

    def probe(ws):
        from runtime import ui_draw
        ctx = ws._app_hosts[cls.id].ctx
        return [ui_draw._C.api_box(ctx, b) for b in boxes]
    frames = P.frames(config, P.Surface(opened, probe=probe), list(script))
    return frames, seen["app"]


def write(app, **kw):
    for k, v in kw.items():
        setattr(app.engine.s, k, v)


def test_a_cards_pad_spreads_as_many_columns_as_its_room_holds_at_that_gap(tmp_path):
    """pad=12 on the handheld's 64-pixel cards: three columns across 320
    pixels, the first 16 in, the fourth card under the first."""
    build = '''
def build():
    with ui.page("Shelf"):
        with ui.cards("carts", w=64, h=64, pad=12):
            ui.card("tap", label="{.name}")
'''
    ids = ["%d/tap" % i for i in range(4)]
    fs, _ = run(tmp_path, build, boxes=ids)
    b = fs[0].state
    assert all(b), b
    assert b[0][1] == b[1][1] == b[2][1] < b[3][1], b
    assert b[3][0] == b[0][0] and b[1][0] - b[0][0] == b[2][0] - b[1][0], b
    assert b[0][0] - 16 <= 8, b


def test_a_cards_badge_and_tone_draw_on_the_card(tmp_path):
    """badge= puts its icon on the card's picture, tone= recolours its sub
    line and veils a danger card's picture: each moves the card's pixels."""
    build = '''
def build():
    with ui.page("Shelf"):
        ui.button("mark")
        with ui.cards("carts", w=64, h=64):
            ui.card("tap", label="{.name}", sub="1 KB", badge="{.badge}", tone="{.tone}")


def mark():
    s.on = not s.on
    rows = [dict(i=r.i, name=r.name, badge="", tone="") for r in s.carts]
    rows[0]["badge"] = "check" if s.on else ""
    rows[1]["tone"] = "danger" if s.on else ""
    s.carts = rows


ui.action("mark", "Mark", mark)
'''
    fs, _ = run(tmp_path, build, ["k:a"])
    a, b = b"".join(P._rgb(fs[0])), b"".join(P._rgb(fs[1]))
    w = fs[0].w
    moved = {(i // 3) % w for i in range(0, len(a), 3) if a[i:i + 3] != b[i:i + 3]}
    assert moved, "neither badge nor tone drew"
    assert min(moved) < w // 3 and max(moved) > w // 3, sorted(moved)[:4]


def test_a_group_of_the_card_look_lays_its_rows_on_a_card(tmp_path):
    """look="card": the rows sit on a card of their own, drawn on the page's
    ground where the captionless group has none."""
    build = '''
def build():
    with ui.page("Shelf"):
        with ui.group("", look="{LOOK}"):
            ui.info("Licence", "MIT")
            ui.info("Size", "12 KB")
'''
    plain, _ = run(tmp_path, build.replace('look="{LOOK}"', ""), name="plain")
    card, _ = run(tmp_path, build.replace("{LOOK}", "card"), name="card")
    assert plain[0].buf != card[0].buf


def test_a_toast_draws_over_the_body_above_the_foot_and_takes_no_stop(tmp_path):
    """The toast's pill is drawn over the page's body while it is shown,
    the foot's button where it was and still the one stop."""
    build = '''
def build():
    with ui.page("Shelf"):
        ui.label("{text}")
        with ui.foot():
            ui.button("flip")
        ui.toast("Jet Teapot is on your shelf", icon="check", shown="on")
'''
    fs, app = run(tmp_path, build, ["k:a", "k:down", "k:a"], boxes=["flip"])
    assert fs[0].buf != fs[1].buf and fs[1].buf != fs[3].buf
    assert fs[0].state == fs[1].state == fs[2].state, [f.state for f in fs]
    assert app.engine.focus_key == "flip"


def test_an_end_foot_sets_its_buttons_at_their_natural_widths_at_its_end(tmp_path):
    """look="end" with a status label and two buttons: one line, the
    buttons side by side at their natural widths, the last at the foot's
    end, the label before them; a templated kind= draws its word."""
    build = '''
def build():
    with ui.page("Shelf"):
        ui.label("{text}")
        with ui.foot():
            ui.label("Doom · on your shelf", tone="dim")
            ui.button("tap2", icon="rotate")
            ui.button("flip", "{kind}")


def tap2():
    s.kind = "primary" if s.kind == "normal" else "normal"


ui.action("tap2", "Check", tap2)
'''
    for config in (TDECK, DESK):
        fs, app = run(tmp_path, build, ["k:a"], config=config, boxes=["tap2", "flip"],
                      name="foot_" + config[:4])
        (ax, ay, aw, ah), (bx, by, bw, bh) = fs[0].state
        w = fs[0].w
        assert ay == by and ah == bh, fs[0].state
        assert ax + aw < bx and aw < w // 3 and bw < w // 3, fs[0].state
        assert config == DESK or bx + bw > w * 3 // 4, fs[0].state
        assert app.engine.s._v["kind"] == "primary" and fs[0].buf != fs[1].buf


def test_a_row_on_a_flowing_page_sets_a_picture_beside_a_column_and_a_button_at_its_end(tmp_path):
    """ui.row outside a placed page: the picture with a column of a label and
    a button beside it, the row as tall as the picture; a row of a label and
    a button, the label taking what the button leaves; the page's next row
    under both."""
    build = '''
def build():
    with ui.page("Shelf"):
        with ui.row("head"):
            ui.picture(icon="game", side=64)
            with ui.group(""):
                ui.label("Doom", face="title")
                ui.button("tap2")
        with ui.row("caption", pad=16):
            ui.label("4 carts", tone="dim")
            ui.button("flip", icon="rotate")
        ui.label("{text}")


def tap2():
    s.n = s.n + 1


ui.action("tap2", "Info", tap2)
'''
    for config in (TDECK, DESK):
        fs, _ = run(tmp_path, build, config=config, boxes=["tap2", "flip"], name="row_" + config[:4])
        (ax, ay, aw, ah), (bx, by, bw, bh) = fs[0].state
        assert ax >= 64 and aw < fs[0].w // 2, fs[0].state          # beside the picture
        assert by >= ay + ah and by - ay >= 40, fs[0].state                   # under the picture's row
        assert bw < fs[0].w // 3 and bx > ax, fs[0].state                     # at the row's end


def test_a_row_of_buttons_alone_centres_them_at_their_natural_widths(tmp_path):
    build = '''
def build():
    with ui.page("Shelf"):
        ui.label("{text}")
        with ui.row("verbs"):
            ui.button("flip", icon="rotate")
'''
    fs, app = run(tmp_path, build, boxes=["flip"])
    x, y, w, h = fs[0].state[0]
    page = fs[0].w
    assert w < page // 2 and abs(x + w // 2 - page // 2) <= 8, fs[0].state


def test_a_progress_in_a_split_cell_draws_its_label_over_its_bar(tmp_path):
    """In a split's cell as on the page, the progress takes the tall form (its
    label and percent on a line, its bar under them, as tall as two rows),
    not a value row's one line."""
    build = '''
def build():
    with ui.page("Shelf"):
        with ui.split("row", sizes=("1*", 274)):
            ui.label("shelf")
            with ui.group(""):
                ui.button("tap2")
                ui.progress("n", max=4, label="Downloading")
                ui.button("flip")


def tap2():
    s.n = s.n + 1


ui.action("tap2", "Info", tap2)
'''
    fs, _ = run(tmp_path, build, boxes=["tap2", "flip"], config=DESK)
    (ax, ay, aw, ah), (bx, by, bw, bh) = fs[0].state
    assert by - (ay + ah) >= 40, fs[0].state


def test_an_empty_breaks_a_long_line_at_word_breaks(tmp_path):
    """A line wider than the page breaks into lines of its column: the
    control under it stands lower than under a short line."""
    build = '''
def build():
    with ui.page("Shelf"):
        with ui.empty("Not installed", lines=["{LINE}"]):
            ui.button("flip")
'''
    long_ = "The download stopped before it finished: the network went away while it was coming."
    short, _ = run(tmp_path, build.replace("{LINE}", "Nothing changed."), boxes=["flip"], name="short")
    wrapped, _ = run(tmp_path, build.replace("{LINE}", long_), boxes=["flip"], name="long")
    assert wrapped[0].state[0][1] > short[0].state[0][1], (short[0].state, wrapped[0].state)


def test_a_split_draws_its_rule_and_a_split_in_a_cell_lays_out_in_that_cell(tmp_path):
    """rule=True draws a rule between the cells; a split inside a group cell
    takes that cell's room, not the page's."""
    build = '''
def build():
    with ui.page("Shelf"):
        with ui.split("row", sizes=("1*", "1*"), RULE):
            with ui.group(""):
                ui.label("left")
            with ui.group(""):
                with ui.split("row", sizes=("1*", "1*")):
                    with ui.group(""):
                        ui.button("tap2")
                    with ui.group(""):
                        ui.button("flip")


def tap2():
    s.n = s.n + 1


ui.action("tap2", "Info", tap2)
'''
    plain, _ = run(tmp_path, build.replace(", RULE", ""), boxes=["tap2", "flip"], name="plain")
    ruled, _ = run(tmp_path, build.replace("RULE", "rule=True"), boxes=["tap2", "flip"], name="ruled")
    assert plain[0].buf != ruled[0].buf
    (ax, _, _, _), (bx, _, _, _) = ruled[0].state
    w = ruled[0].w
    assert ax >= w // 2 - 8 and bx > ax, ruled[0].state


def test_a_text_view_of_the_well_look_lays_its_prose_on_a_well(tmp_path):
    build = '''
def build():
    with ui.page("Shelf"):
        ui.text_view("text", face="ui", wrap="word"LOOK)
'''
    plain, _ = run(tmp_path, build.replace("LOOK", ""), name="plain")
    well, _ = run(tmp_path, build.replace("LOOK", ', look="well"'), name="well")
    assert plain[0].buf != well[0].buf


LUA_SHELF = '''ui.app("Shelf", { icon = "getcarts" })
local s = ui.state {
  carts = ui.model { key = "i", i = "", name = "", badge = "" }, on = false, text = "Line one",
}
ui.action("tap", "Open", function(row) s.on = not s.on end, { takes = "row" })
ui.action("flip", "Check", function() s.on = not s.on end)
ui.hook("opened", function()
  s.carts:set({ { i = "a", name = "Doom", badge = "check" }, { i = "b", name = "Jet", badge = "" } })
end)
ui.page("p", function()
  ui.row("caption", { pad = 16 }, function()
    ui.label("2 carts", { tone = "dim" })
    ui.button("flip", { icon = "rotate" })
  end)
  ui.split({ dir = "row", sizes = { "1*", "1*" }, rule = true }, function()
    ui.cards("carts", { w = 64, h = 64, pad = 12 }, function()
      ui.card("tap", { label = "{.name}", badge = "{.badge}" })
    end)
    ui.group("", { look = "card" }, function() ui.text_view("text", { face = "ui", look = "well" }) end)
  end)
  ui.foot(function()
    ui.label("Doom", { tone = "dim" })
    ui.button("flip", { kind = "{on?primary:normal}" })
  end)
  ui.toast("Doom is on your shelf", { icon = "check", shown = "on" })
end)
'''


def test_the_lua_front_makes_the_same_kinds_and_props(tmp_path):
    """A Lua page of a row, a split's rule, a cards list's pad= and its
    cards' badge=, a card group, a well, an end foot with a templated kind
    and a toast: built, lowered and drawn on the C engine; Check shows the
    toast."""
    import test_uitree_lua as L
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    L._cart(carts, "Shelf", LUA_SHELF)
    ws, drv, frame, open_cart = L._console(carts)
    open_cart(ws, "Shelf")
    for _ in range(4):
        frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    before = bytes(drv.rgb888())
    drv.press("a")
    for _ in range(4):
        frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    assert bytes(drv.rgb888()) != before


def test_a_rule_in_a_row_divides_its_neighbours_and_is_never_its_filler(tmp_path):
    """A rule in a flowing row is a line down the row between its
    neighbours, its own width: the label after it stays the filler, so the
    button beside the rule keeps its place."""
    build = '''
def build():
    with ui.page("Shelf"):
        with ui.row("tools"):
            ui.button("tap2")
            RULE
            ui.button("flip")
            ui.label("")


def tap2():
    s.n = s.n + 1


ui.action("tap2", "Info", tap2)
'''
    for config in (TDECK, DESK):
        plain, _ = run(tmp_path, build.replace("RULE", "pass"), config=config, boxes=["flip"],
                       name="plain_" + config[:4])
        ruled, _ = run(tmp_path, build.replace("RULE", "ui.rule()"), config=config, boxes=["flip"],
                       name="ruled_" + config[:4])
        assert plain[0].buf != ruled[0].buf
        moved = ruled[0].state[0][0] - plain[0].state[0][0]
        assert 0 < moved <= 16, (plain[0].state, ruled[0].state)


def test_a_cards_current_marks_its_row(tmp_path):
    """current= on a cards list marks the card whose key the state holds."""
    global HEAD
    build = '''
def build():
    with ui.page("Shelf"):
        with ui.cards("carts", CURRENT w=48, h=48):
            ui.card("tap", label="{.name}")
'''
    was = HEAD
    HEAD = HEAD.replace('text="Line one"', 'text="2"')
    try:
        plain, _ = run(tmp_path, build.replace("CURRENT", ""), name="cur_off")
        marked, _ = run(tmp_path, build.replace("CURRENT", 'current="text",'), name="cur_on")
    finally:
        HEAD = was
    assert plain[0].buf != marked[0].buf


def test_a_split_in_a_switchs_case_is_laid_out_above_the_band(tmp_path):
    """A page whose split stands in a switch's case is laid out in cells as
    one whose split is the page's own: the band is cut from its room."""
    build = '''
def build():
    with ui.page("Shelf"):
        OPEN
            with ui.split("col", sizes=("1*", 40)):
                ui.label("{text}")
                ui.button("tap2")


def body():
    pass


def tap2():
    s.n = s.n + 1


ui.action("tap2", "Info", tap2)
'''
    own, _ = run(tmp_path, build.replace("OPEN", "if True:"), config=DESK, boxes=["tap2"],
                 name="own")
    case = build.replace("OPEN", "ui.switch(\"on\", {\"_\": cased})\n        if False:") + '''

def cased():
    with ui.split("col", sizes=("1*", 40)):
        ui.label("{text}")
        ui.button("tap2")
'''
    cased, _ = run(tmp_path, case, config=DESK, boxes=["tap2"], name="cased")
    assert cased[0].state == own[0].state, (own[0].state, cased[0].state)


def test_a_links_swatch_draws_a_chip_of_its_colour_before_its_value(tmp_path):
    """swatch="#RRGGBB" on a link: a chip of that colour before its value;
    an empty one draws none."""
    build = '''
def build():
    with ui.page("Shelf"):
        ui.link("flip", "Red", SWATCH)
'''
    plain, _ = run(tmp_path, build.replace("SWATCH", 'swatch=""'), config=DESK, name="chip_off")
    chip, _ = run(tmp_path, build.replace("SWATCH", 'swatch="#FF004D"'), config=DESK,
                  name="chip_on")
    assert plain[0].buf != chip[0].buf
