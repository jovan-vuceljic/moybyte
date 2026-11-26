"""The handheld Editor's canvas tabs driven with a pad's buttons alone (the
d-pad, A and B), as on the T-Deck's glass: no part of a tab is a dead end.

Up past the top of a tab's page walks onto the bar (its page's engine edge,
`PaintLayer.at_top` and `PageHost.at_top`), B leaves the Editor as on every
tab, and the Sprites tab's header walks its parts: the sprite before, the
sprite after and Size, each its own stop.
"""

import pytest

from runtime import host_app, ui_draw
from test_v04_userland import select_first_game


@pytest.fixture
def editor(tmp_path):
    was = ui_draw.input_kind()
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    drv = host_app.ConsoleDriver(ws)
    ws.use_inputs((("local", "tdeck"),))
    select_first_game(ws)
    _frames(drv)
    ws.open_workspace(ws.launcher.selected())
    ws.text.open_menu()
    _frames(drv)
    yield ws, drv
    ui_draw.input_kind(was)


def _frames(drv, n=3):
    for _ in range(n):
        drv.frame(1 / 30)


def _press(drv, name, times=1):
    for _ in range(times):
        drv.press(name)
        _frames(drv)


def _tab(ws, drv, tab):
    ws.editor_app.set_tab(tab)
    _frames(drv)


HEAD = ("prev", "next", "pickers")


def _to_head(drv, pg):
    """Up from the grid, through the palette's rows, onto the header."""
    for _ in range(12):
        if pg.focus_key in HEAD:
            return
        _press(drv, "up")
    raise AssertionError(pg.focus_key)


def _bar_cell(ws):
    """The bar's focused cell, None while the keys are on the page."""
    return ws.bar_layer.focus


def test_the_sprites_header_walks_its_parts_and_up_reaches_the_bar(editor):
    ws, drv = editor
    _tab(ws, drv, "paint")
    pg = ws.layer_of("paint").page
    assert pg.focus_key == "grid"
    _to_head(drv, pg)
    assert pg.focus_key == "prev"
    _press(drv, "right")
    assert pg.focus_key == "next"
    n = ws.paint.n
    _press(drv, "a")
    assert ws.paint.n == n + 1
    _press(drv, "right")
    assert pg.focus_key == "pickers"
    _press(drv, "left", 2)
    assert pg.focus_key == "prev"
    _press(drv, "a")
    assert ws.paint.n == n
    _press(drv, "up")
    assert _bar_cell(ws) is not None
    assert ws.bar_layer.focus_where == "menu"
    _press(drv, "down")
    assert _bar_cell(ws) is None and pg.focus_key == "prev"


def test_b_leaves_the_sprites_tab_and_first_closes_its_popover(editor):
    ws, drv = editor
    _tab(ws, drv, "paint")
    pg = ws.layer_of("paint").page
    _to_head(drv, pg)
    _press(drv, "right", 2)
    assert pg.focus_key == "pickers"
    _press(drv, "a")
    assert ws.layer_of("paint")._pop == "pickers"
    _press(drv, "b")
    assert not ws.layer_of("paint")._pop
    ws.layer_of("paint")._open_more()      # (a gamepad's Y, which the host has not)
    _frames(drv)
    assert ws.layer_of("paint")._pop == "more"
    _press(drv, "b")
    assert not ws.layer_of("paint")._pop
    assert ws.wm.top_kind() == "menu"
    _press(drv, "b")
    assert ws.wm.top_kind() == "launcher"


def test_up_from_the_maps_brushes_reaches_the_bar(editor):
    ws, drv = editor
    _tab(ws, drv, "map")
    pg = ws.map_ui.page
    for _ in range(80):
        if pg.focus_key == "brushes":
            break
        _press(drv, "right")
    assert pg.focus_key == "brushes"
    _press(drv, "up", 4)
    assert _bar_cell(ws) is not None
    _press(drv, "down")
    _press(drv, "b")
    assert ws.wm.top_kind() == "launcher"
