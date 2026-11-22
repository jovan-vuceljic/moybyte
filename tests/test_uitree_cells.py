"""`ui.cells` on the C engine (native/moy_uitree's UIT_CELLS over the
toolkit's moy_ui_api_cells): a palette's colours as square cells, a stop
bound to an int -- the arrows move the current cell a cell at a time,
on= hears each move, Enter and a tap fire pick=, and a tap moves the
current cell to the one under it first."""
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
                 pick="on_pick")
'''


def run(tmp_path, script):
    import uitree_app
    import uitree_c
    import uitree_conf as C
    app_py = tmp_path / "cells" / "app.py"
    app_py.parent.mkdir()
    app_py.write_text(APP)
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
