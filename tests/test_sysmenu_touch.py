"""The system menu under a finger (shell_cards.SystemMenuUI, sysmenu_ui's
page): a drag past the slop scrolls its rows and chooses none, and a tap
that does not move chooses the row under it. A phone's browser and a touch
board lay it out on a handheld, where its rows run past the glass."""

import pytest

from ws_helpers import build_ws, make_drv


def _menu(tmp_path, size):
    ws = build_ws(tmp_path, sys_size=size)
    ws.home.go_home()
    drv = make_drv(ws)
    drv.frame(1 / 30)
    ws.toggle_sysmenu()
    for _ in range(3):
        drv.frame(1 / 30)
    return ws, drv


def _frames(drv, n=4):
    for _ in range(n):
        drv.frame(1 / 30)


# the handheld (a phone's browser, the T-Deck), whose menu runs past the
# glass, and the Guition S3's 480x320, where it fits
@pytest.mark.parametrize("size, runs_on", [((320, 240), True), ((480, 320), False)])
def test_a_drag_scrolls_the_menu_and_chooses_nothing(tmp_path, size, runs_on):
    ws, drv = _menu(tmp_path, size)
    host = ws.menu_ui.host
    card = ws.menu_ui.look_card()
    last = [it[4] for it in ws.sysmenu.items if it[0] == "item"][-1]
    was = host.box(last)
    assert was is not None and (was[1] + was[3] > card[1] + card[3]) == runs_on, (was, card)
    x, y = card[0] + card[2] // 2, card[1] + card[3] - 24
    drv.touch(x, y)
    drv.frame(1 / 30)
    for i in range(1, 11):
        drv.touch_drag(x, y - 8 * i)
        drv.frame(1 / 30)
    drv.touch_up()
    _frames(drv, 30)
    assert ws.sysmenu.open, "the drag chose a row"
    now = host.box(last)
    assert (now[1] < was[1]) == runs_on, ("the rows scrolled as they could", was, now)


@pytest.mark.parametrize("size", [(320, 240), (480, 320)])
def test_a_tap_that_does_not_move_chooses_its_row(tmp_path, size):
    ws, drv = _menu(tmp_path, size)
    box = ws.menu_ui.host.box("Tasks")
    assert box is not None
    drv.touch(box[0] + box[2] // 2, box[1] + box[3] // 2)
    drv.frame(1 / 30)
    drv.touch_up()
    _frames(drv)
    assert not ws.sysmenu.open
    assert ws.wm.top_is(ws.tasks_layer.id)
