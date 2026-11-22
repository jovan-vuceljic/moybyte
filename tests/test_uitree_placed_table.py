"""The placed layout's table, grid, label and rule (native/moy_uitree's
`place_at`, `draw_table`, `natural`): a table fills its stack and its
canvas child draws each row in view, told its row; a grid takes its w= and
h= at the top of its cell; a size="text" label is as wide as its text; a
rule is its line; a popover hung from a node narrower than it hangs under
that node, w= wide, inside the page."""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))

import uitree_parity as P  # noqa: E402

KEYS = ("head", "open_pop", "body", "rows", "bump_a", "bump_d", "foot", "pop")


def _run(config, script):
    import uitree_c
    import uitree_placed_table as F
    seen = {}
    cls = F.layer(uitree_c.CEditorEngine)

    def opened(ws):
        seen["app"] = P.host(ws, cls)

    def probe(ws):
        e = seen["app"].engine
        return "%s|%s|%r" % (e.s.chosen, e.s.pop, [(k, e.rect_of(k)) for k in KEYS])
    del F.DRAWN[:]
    return P.frames(config, P.Surface(opened, probe=probe), script), F.DRAWN


def _rects(f):
    return dict(ast.literal_eval(f.state.split("|", 2)[2]))


def test_a_tables_canvas_draws_each_row_told_its_row_beside_a_grid_of_its_size():
    frames, drawn = _run("tdeck_320x240_fs1_dark", [])
    r = _rects(frames[0])
    rows, body, a, d = r["rows"], r["body"], r["bump_a"], r["bump_d"]
    assert rows[3] == body[3] - 4 and rows[3] > 3 * 17, r      # the table fills its cell of the body
    assert d[0] + d[2] - a[0] <= 100 and d[1] + d[3] - a[1] <= 48, r    # the grid's w= and h=
    assert a[1] == rows[1], r                                    # at its cell's top
    assert r["open_pop"][0] < 80, r                              # after a label as wide as its text
    got = sorted(set((i, h) for i, _y, h in drawn))
    assert got == [(0, 17), (1, 17), (2, 17), (3, 17)], drawn
    ys = sorted(set((i, y) for i, y, _h in drawn))
    assert [y - ys[0][1] for _i, y in ys] == [0, 17, 34, 51], ys


def _live(tmp_path):
    """A workstation with the fixture open, its driver and its engine."""
    import uitree_c
    import uitree_placed_table as F
    from runtime import host_app
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    ws.pointer.visible = False
    app = P.host(ws, F.layer(uitree_c.CEditorEngine))
    drv = host_app.ConsoleDriver(ws)
    for _ in range(3):
        ws.mark_dirty()
        drv.frame(1 / 30)
    return ws, drv, app.engine


def _tap(ws, drv, x, y):
    drv.click(x, y)
    for _ in range(3):
        ws.mark_dirty()
        drv.frame(1 / 30)


def test_a_tap_on_a_row_moves_the_tables_current_row(tmp_path):
    ws, drv, e = _live(tmp_path)
    x, y, _w, _h = e.rect_of("rows")
    _tap(ws, drv, x + 20, y + 2 * 17 + 8)
    assert e.s.chosen == "2"


def test_a_popover_hangs_under_the_narrow_node_it_names_inside_the_page(tmp_path):
    ws, drv, e = _live(tmp_path)
    b = e.rect_of("open_pop")
    _tap(ws, drv, b[0] + b[2] // 2, b[1] + b[3] // 2)
    assert e.s.pop
    host = ws._app_hosts[[k for k in ws._app_hosts if k.startswith("placed_table")][0]]
    card = host.box("pop")
    assert card is not None, "the popover drew no card"
    assert card[1] >= b[1] + b[3] and card[2] >= 170, (card, b)
    assert card[0] + card[2] <= ws.sys_canvas.w, card
