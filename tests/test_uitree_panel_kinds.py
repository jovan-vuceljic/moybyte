"""The C engine's kinds and props a style panel and a slide sorter draw
with (Storybook's editor), each held on a page of its own from the Python
front: a card's label_icon=, a group's look="rules" (a row among its rows
ruled too), a popover hung under its button on the desk, a swatches row
whose label takes its right pad before it is cut, a bar item's narrower
icon-alone width."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "uitree_fixtures")]

import uitree_parity as P  # noqa: E402
from test_uitree_shelf_kinds import DESK, run  # noqa: E402


def _reds(f):
    """The x of every red pixel (#FF004D's, as RGB565 keeps it) in frame f."""
    px = b"".join(P._rgb(f))
    return {(i // 3) % f.w for i in range(0, len(px), 3)
            if px[i] > 200 and px[i + 1] < 40 and 40 < px[i + 2] < 110}


def test_a_cards_label_icon_stands_before_its_label_under_the_picture(tmp_path):
    """label_icon= draws its icon in the label's band, the two centred as
    one: the band's pixels move, the picture's do not."""
    build = '''
def build():
    with ui.page("Shelf"):
        with ui.cards("carts", w=64, h=64):
            ui.card("tap", label="{.name}", label_icon=ICON)
'''
    plain, _ = run(tmp_path, build.replace("ICON", '""'), name="lead_off", boxes=["0/tap"])
    lead, _ = run(tmp_path, build.replace("ICON", '"check"'), name="lead_on")
    a, b = b"".join(P._rgb(plain[0])), b"".join(P._rgb(lead[0]))
    w = plain[0].w
    rows = {(i // 3) // w for i in range(0, len(a), 3) if a[i:i + 3] != b[i:i + 3]}
    x, y, cw, ch = plain[0].state[0]
    assert rows, "label_icon= drew nothing"
    assert min(rows) >= y + 64, (sorted(rows)[:3], y)


def test_a_group_of_the_rules_look_rules_its_rows_apart_a_flow_row_among_them(tmp_path):
    """look="rules": a captionless group whose rows a rule parts, as a
    captioned group's are; a row of kids (ui.row) is one of its rows."""
    build = '''
def build():
    with ui.page("Shelf"):
        with ui.group("", look="{LOOK}"):
            with ui.row("r", gap=0):
                ui.label("Colour")
                ui.button("flip", icon="forward", alone=True, kind="bar")
            ui.info("Size", "12 KB")
            ui.info("Kind", "Cart")
'''
    plain, _ = run(tmp_path, build.replace('look="{LOOK}"', ""), config=DESK, name="plain")
    ruled, _ = run(tmp_path, build.replace("{LOOK}", "rules"), config=DESK, name="ruled")
    a, b = b"".join(P._rgb(plain[0])), b"".join(P._rgb(ruled[0]))
    w = plain[0].w
    lines = {}
    for i in range(0, len(a), 3):
        if a[i:i + 3] != b[i:i + 3]:
            lines.setdefault((i // 3) // w, set()).add((i // 3) % w)
    # two rules: under the row of kids and under the first info row, each a long line
    long_ = [y for y, xs in lines.items() if len(xs) > w // 4]
    assert len(long_) >= 2, {y: len(xs) for y, xs in lines.items()}


def test_on_the_desk_a_buttons_popover_hangs_under_it(tmp_path):
    """anchor= a button: on the desk its popover's top stands under the
    button and its left edge at the button's, not centred on the page."""
    build = '''
def build():
    with ui.page("Shelf"):
        with ui.row("tools", gap=8):
            ui.button("flip")
            ui.label("")
        with ui.popover("pop", anchor="flip", shown="!on", close="flip", w=200):
            with ui.menu(""):
                ui.item("tap0", label="One")


def tap0():
    pass


ui.action("tap0", "Tap", tap0)
'''
    fs, _ = run(tmp_path, build, config=DESK, boxes=["flip", "One"])
    btn, item = fs[0].state
    assert btn and item, fs[0].state
    assert item[1] >= btn[1] + btn[3], (btn, item)
    assert abs(item[0] - btn[0]) < 40, (btn, item)


def test_a_swatches_rows_cut_label_takes_its_right_pad_where_that_makes_it_whole(tmp_path):
    """A swatches row whose dots would cut its label moves them into its
    right pad where that makes the label whole, else shrinks them until it
    is: across labels a letter longer each, the dots stand where a short
    label's do, then (one label at least) further right, the longest's
    leftmost further right still."""
    build = '''
def build():
    with ui.page("Shelf"):
        with ui.group("", look="rules"):
            ui.seg(LABEL, "kind", text="{.rgb}", look="swatches")
'''
    head = '''
s2 = ui.state(swatches=ui.model(key="id", id="", rgb=""), kind=ui.row_of("swatches"))


def fill():
    s2.swatches = [dict(id=str(i), rgb=c) for i, c in enumerate(("0xFF004D", "0x00E436", "0x29ADFF",
                                                                  "0x000000") * 2)]


ui.hook("opened", fill)
'''
    def left(label, name):
        fs, _ = run(tmp_path, head + build.replace("LABEL", repr(label)), name=name)
        reds = _reds(fs[0])
        assert reds, "no swatch drew"
        return min(reds)
    rest = left("Bg", "sw_bg")
    xs = [left("Background " + "m" * n, "sw_%d" % n) for n in range(0, 12)]
    assert all(x >= rest for x in xs), (rest, xs)
    moved = [i for i, x in enumerate(xs) if x > rest]
    assert moved, (rest, xs)
    assert xs[-1] > xs[moved[0]], (rest, xs)


def test_a_bar_items_icon_alone_is_narrower_than_a_buttons(tmp_path):
    """kind="bar" alone: 28 desk pixels across, a button's 36."""
    build = '''
def build():
    with ui.page("Shelf"):
        with ui.row("tools", gap=8):
            ui.button("flip", icon="forward", alone=True, kind="bar")
            ui.button("tap1", icon="back", alone=True)
            ui.label("")


def tap1():
    pass


ui.action("tap1", "Tap", tap1)
'''
    fs, _ = run(tmp_path, build, config=DESK, boxes=["flip", "tap1"])
    bar, btn = fs[0].state
    assert bar[2] < btn[2], (bar, btn)

