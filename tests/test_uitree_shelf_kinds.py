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
