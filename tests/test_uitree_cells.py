"""`ui.cells` on the C engine (native/moy_uitree's UIT_CELLS over the
toolkit's moy_ui_api_cells): a palette's colours as square cells, a stop
bound to an int -- the arrows move the current cell a cell at a time,
on= hears each move, Enter and a tap fire pick=, and a tap moves the
current cell to the one under it first; clear= shows its colour as the
grey checker under a white stroke."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "uitree_fixtures")]

import uitree_parity as P  # noqa: E402

TDECK = "tdeck_320x240_fs1_dark"

APP = '''
import uitree as ui

s = ui.state(c=12, moves=0, picks=0)


def on_move():
    s.moves = s.moves + 1


def on_pick():
    s.picks = s.picks + 1


ui.hook("on_move", on_move)
ui.action("on_pick", "Use", on_pick)


def build():
    with ui.page("Cells"):
        ui.cells("c", first=0, count=64, cols=8, side=18, gap=2, edge=True, on="on_move",
                 pick="on_pick"%s)
'''


def run(tmp_path, script, clear=""):
    import uitree_app
    import uitree_c
    import uitree_conf as C
    app_py = tmp_path / "cells" / "app.py"
    app_py.parent.mkdir(parents=True)
    app_py.write_text(APP % clear)
    mod = C._module(str(app_py))
    cls = uitree_app.app_layer("cells_c", "Cells", mod.build, engine=uitree_c.CEngine)
    seen = {}

    def opened(ws):
        seen["app"] = P.host(ws, cls)

    def probe(ws):
        s = seen["app"].engine.s
        return (s.c, s.moves, s.picks)

    return P.frames(TDECK, P.Surface(opened, probe=probe), list(script))


def test_the_arrows_move_the_current_cell_and_enter_picks_it(tmp_path):
    fs = run(tmp_path, ["k:right", "k:down", "k:left", "k:a"])
    states = [f.state for f in fs]
    assert states[0] == (12, 0, 0), states
    assert states[1][:2] == (13, 1), states             # a cell right
    assert states[2][:2] == (21, 2), states             # a row down: eight on
    assert states[3][:2] == (20, 3), states
    assert states[4] == (20, 3, 1), states              # Enter: picked, not moved
    assert fs[0].buf != fs[1].buf                       # the current mark moved


def test_the_edges_hold_the_current_cell(tmp_path):
    fs = run(tmp_path, ["k:right"] * 5)
    assert [f.state[0] for f in fs] == [12, 13, 14, 15, 15, 15]


def test_a_clear_colour_shows_the_checker_under_a_white_stroke(tmp_path):
    """clear=0: colour 0's cell is transparency's grey checker, dark and
    light (chrome.FIXED's, the colours the C draws it in), under a white
    stroke; without it the cell is colour 0's black."""
    import chrome

    def count(buf, rgb):
        w = ((rgb >> 8) & 0xf800) | ((rgb >> 5) & 0x07e0) | ((rgb >> 3) & 0x1f)
        hi, lo = w >> 8, w & 0xff
        return sum(1 for i in range(0, len(buf), 2) if buf[i] == hi and buf[i + 1] == lo)

    plain = run(tmp_path / "plain", [])[-1].buf
    clear = run(tmp_path / "clear", [], clear=", clear=0")[-1].buf
    dark, light, _black, white = [v & 0xffffff for v in chrome.FIXED]
    side = 16                                       # side= less gap= on the T-Deck's scale
    for rgb in (dark, light):
        assert count(clear, rgb) - count(plain, rgb) >= side * side // 4, hex(rgb)
    assert count(clear, white) - count(plain, white) >= side - 2


COLUMN = '''
import uitree as ui

s = ui.state(c=0, n=0)


def go():
    s.n = s.n + 1


for k in ("one", "two", "three", "four"):
    ui.action(k, k.title(), go)


def build():
    with ui.page("Cells"):
        with ui.split("col", sizes=(20, 216, 32, 32, 32, 32, "1*"), gap=0, pad=0):
            ui.label("Colour")
            ui.cells("c", first=0, count=64, cols=8, side=25, gap=2)
            for k in ("one", "two", "three", "four"):
                ui.button(k)
            ui.label("")
'''


def column(tmp_path, script):
    import ui_draw
    import uitree_app
    import uitree_c
    import uitree_conf as C
    app_py = tmp_path / "column" / "app.py"
    app_py.parent.mkdir()
    app_py.write_text(COLUMN)
    mod = C._module(str(app_py))
    cls = uitree_app.app_layer("column_c", "Column", mod.build, engine=uitree_c.CEngine)
    seen = {}

    def opened(ws):
        seen["app"] = P.host(ws, cls)

    def probe(ws):
        e = seen["app"].engine
        ctx, lib = ui_draw.UI_TARGET[0], ui_draw._C
        four, cells = lib.api_hit_box(ctx, "four"), lib.api_hit_box(ctx, "c")
        return (e.focus_key, four is not None and four == lib.api_box(ctx, "four"), cells)

    return P.frames(TDECK, P.Surface(opened, probe=probe), list(script))


def test_a_column_its_palette_cannot_fit_scrolls_and_the_keys_bring_its_foot_in(tmp_path):
    """A column split whose palette, at a third of its side, still leaves its
    cells past the room scrolls: its last button lies past the view at
    first (pressed nowhere: its hit box is cut to the view) and the keys
    walk down to it, scrolling it whole into view; the palette keeps its
    rows."""
    fs = column(tmp_path, ["k:down"] * 12)
    first, last = fs[0].state, fs[-1].state
    assert not first[1], first                  # the foot past the view at rest
    assert last[0] == "four" and last[1], last  # the keys bring it in whole
    assert first[2][3] >= 8 * 9, first          # eight rows of at least 9 px
