"""The placed layout's swatches, square icons, menus and canvases under a
popover (native/moy_uitree's `draw` of a seg, `row_cells`, `menu_rows`;
`uitree_c.CEditorPage.point`): a seg of look="swatches" draws a colour dot
a row, each row's word its colour, and a tap on one writes its key; an
icon button of its own w= in a placed row stands square, centred down the
row; a popover's list of links is a menu whose rows carry their link's
icon; and a canvas under a shown popover takes no press."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))

import uitree_parity as P  # noqa: E402


def _live(tmp_path):
    import uitree_c
    import uitree_placed_swatches as F
    from runtime import host_app
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    ws.pointer.visible = False
    app = P.host(ws, F.layer(uitree_c.CEditorEngine))
    drv = host_app.ConsoleDriver(ws)
    _settle(ws, drv)
    return ws, drv, app.engine, ws._app_hosts["placed_swatches"]


def _settle(ws, drv):
    for _ in range(3):
        ws.mark_dirty()
        drv.frame(1 / 30)


def _tap(ws, drv, x, y):
    drv.click(x, y)
    _settle(ws, drv)


def _pixels(ws, r):
    cv = ws.wm.root_canvas if hasattr(ws.wm, "root_canvas") else ws.sys_canvas
    b = bytes(cv._buf)
    return [b[2 * (y * cv.w + x):2 * (y * cv.w + x) + 2] for y in range(r[1], r[1] + r[3])
            for x in range(r[0], r[0] + r[2])]


def test_a_swatches_seg_draws_a_dot_a_row_and_a_tap_writes_its_key(tmp_path):
    ws, drv, e, host = _live(tmp_path)
    x, y, w, h = e.rect_of("brush")
    assert e.s.dot == "red"
    # the dots stand at the row's end, the last row's nearest it: walk in from the end
    seen, was = [], e.s.dot
    for k in range(60):
        _tap(ws, drv, x + w - 6 - 3 * k, y + h // 2)
        if e.s.dot != was:
            was = e.s.dot
            seen.append(was)
        if len(seen) == 3:
            break
    assert seen == ["blue", "green", "red"], seen


def test_an_icon_of_its_own_width_stands_square_centred_down_its_row(tmp_path):
    ws, drv, e, host = _live(tmp_path)
    row = e.rect_of("ops")
    for k in ("one", "two"):
        bx, by, bw, bh = e.rect_of(k)
        assert bw == bh == 14, (k, e.rect_of(k))
        assert by - row[1] == row[1] + row[3] - (by + bh), (row, e.rect_of(k))
    assert e.rect_of("open_pop")[3] == row[3], "a bar item keeps the row's height"


def test_a_popovers_links_are_a_menu_whose_rows_carry_their_icons(tmp_path):
    ws, drv, e, host = _live(tmp_path)
    b = e.rect_of("open_pop")
    _tap(ws, drv, b[0] + b[2] // 2, b[1] + b[3] // 2)
    assert e.s.pop
    a = host.box("Alpha")
    assert a is not None, "the menu drew no Alpha row"
    assert len(set(_pixels(ws, (a[0] + 2, a[1] + 2, 16, a[3] - 4)))) > 1, "the row's icon drew nothing"
    _tap(ws, drv, a[0] + a[2] // 2, a[1] + a[3] // 2)
    assert e.s.took == "a" and not e.s.pop


def test_a_canvas_under_a_shown_popover_takes_no_press(tmp_path):
    ws, drv, e, host = _live(tmp_path)
    x, y, w, h = e.rect_of("area")
    _tap(ws, drv, x + w // 2, y + h // 2)
    assert e.s.presses == 1
    b = e.rect_of("open_pop")
    _tap(ws, drv, b[0] + b[2] // 2, b[1] + b[3] // 2)
    a = host.box("Beta")
    assert e.s.pop and a is not None
    assert y <= a[1] < y + h, "the menu hangs over the canvas"
    _tap(ws, drv, a[0] + a[2] // 2, a[1] + a[3] // 2)
    assert e.s.presses == 1 and e.s.took == "b"
