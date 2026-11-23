"""The placed layout's table, grid, label and rule (native/moy_uitree's
`place_at`, `draw_table`, `natural`): a table fills its stack and its
canvas child draws each row in view, told its row; a grid takes its w= and
h= at the top of its cell; a size="text" label is as wide as its text; a
rule is its line; a popover hung from a node narrower than it hangs under
that node, w= wide, inside the page; an empty fills its stack and drops its
disc where it would run past it."""
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


def _empty_at(top):
    """The page's room and the button's rect under a placed empty, the
    canvas over it `top` pixels tall."""
    import uitree_c
    import uitree_placed_empty as F
    F.TOP[0] = top
    seen = {}
    cls = F.layer(uitree_c.CEditorEngine)

    def opened(ws):
        seen["app"] = P.host(ws, cls)

    def probe(ws):
        e = seen["app"].engine
        return repr((e.rect, e.rect_of("head"), e.rect_of("go")))
    f = P.frames("p4_1024x600_fs2_windowed", P.Surface(opened, probe=probe), [])[0]
    return ast.literal_eval(f.state)


def test_a_placed_empty_fills_its_stack_and_drops_its_disc_where_it_would_run_past():
    """With room the empty's disc stands over its words; where the disc
    would push its button past the page, the disc goes and the button
    stays inside."""
    page, head, tall = _empty_at(1)
    _page, head2, short = _empty_at(150)
    bottom = page[1] + page[3]
    assert tall[1] + tall[3] <= bottom and short[1] + short[3] <= bottom, (page, tall, short)
    with_disc, without = tall[1] - (head[1] + head[3]), short[1] - (head2[1] + head2[3])
    assert with_disc - without >= 48, (with_disc, without)


def test_a_tables_canvas_is_handed_the_press_on_its_row(tmp_path):
    """A table's canvas child with pointer= takes a press on a row, handed
    that row (ev.row) in the row's coordinates, on any frame: the rows a
    frame did not draw again take it too."""
    import uitree_c
    import uitree_placed_parts as F
    from runtime import host_app
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    ws.pointer.visible = False
    app = P.host(ws, F.layer(uitree_c.CEditorEngine))
    drv = host_app.ConsoleDriver(ws)
    for _ in range(3):
        ws.mark_dirty()
        drv.frame(1 / 30)
    e = app.engine
    x, y, _w, _h = e.rect_of("rows")
    for row in (2, 2, 0):
        _tap(ws, drv, x + 20, y + row * 40 + 12)
    assert e.s.pressed == "down:2@12,up:2@12,down:2@12,up:2@12,down:0@12,up:0@12,", e.s.pressed


def _boxes(tmp_path, build, ids, placed=True, keys=()):
    """The toolkit's box of each focus id after the fixture's page opened
    full screen and `keys` were pressed: {id: (x, y, w, h)}."""
    import uitree_c
    import uitree_placed_rows as F
    from runtime import host_app
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    ws.pointer.visible = False
    cls = F.layer(getattr(F, build), uitree_c.CEditorEngine if placed else uitree_c.CEngine)
    app = P.host(ws, cls)
    drv = host_app.ConsoleDriver(ws)
    for k in (None,) * 3 + tuple(keys):
        if k is not None:
            drv.press(k)
        ws.mark_dirty()
        drv.frame(1 / 30)
    host = ws._app_hosts[cls.id]
    return app.engine, dict((i, host.box(i)) for i in ids)


def test_a_placed_rows_body_and_by_case_draw_their_rows(tmp_path):
    """A ui.row in a rows' body and in a by= case draws on a placed page:
    each row's button is a stop, one row under the other."""
    e, got = _boxes(tmp_path, "rows_page", ("a/go", "b/go", "c/go", "p/go", "r/go"))
    assert e.focus_key == "a/go", e.focus_key
    a, b, c, p, r = (got[k] for k in ("a/go", "b/go", "c/go", "p/go", "r/go"))
    assert a and b and c and a[1] < b[1] < c[1] and a[0] == b[0], got
    assert p and r and c[1] < p[1] < r[1], got


def test_groups_in_a_placed_row_stand_side_by_side(tmp_path):
    _e, got = _boxes(tmp_path, "groups_page", ("left", "right"))
    left, right = got["left"], got["right"]
    assert left[1] == right[1] and left[0] + left[2] <= right[0], got


def test_a_split_among_a_flowing_pages_rows_takes_its_cells_height(tmp_path):
    """A split between a flowing page's rows stands at the flow's place as
    tall as its tallest cell: the button after it is under the split's
    three rows, not over them."""
    _e, got = _boxes(tmp_path, "split_page", ("after",), placed=False)
    _e, one = _boxes(tmp_path, "rows_page", ("a/go", "b/go"))
    pitch = one["b/go"][1] - one["a/go"][1]
    assert got["after"][1] > 28 + 3 * pitch, (got, pitch)
