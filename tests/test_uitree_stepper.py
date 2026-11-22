"""`ui.stepper` on the C engine (native/moy_uitree's draw of a stepper over
native/moy_ui's moy_ui_api_stepper): a value between two chevrons whose
taps, and left and right while it is focused, fire its prev= and next=, a
chevron greyed and inert while its action is off; in a placed row a grow=
stepper fills, its chevrons at the cell's ends."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))

import uitree_parity as P  # noqa: E402


def _live(tmp_path, placed):
    import uitree_c
    import uitree_stepper as F
    from runtime import host_app
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    ws.pointer.visible = False
    app = P.host(ws, F.layer(uitree_c.CEditorEngine if placed else uitree_c.CEngine, placed))
    drv = host_app.ConsoleDriver(ws)
    _settle(ws, drv)
    return ws, drv, app.engine


def _settle(ws, drv):
    for _ in range(3):
        ws.mark_dirty()
        drv.frame(1 / 30)


def _tap(ws, drv, x, y):
    drv.click(x, y)
    _settle(ws, drv)


def test_a_tap_steps_the_half_it_lands_in_and_a_greyed_end_takes_none(tmp_path):
    ws, drv, e = _live(tmp_path, True)
    x, y, w, h = e.rect_of("head")
    sx, sy, sw, sh = e.rect_of("stepper#1")
    assert sw > w // 2, "a grow= stepper fills its row"
    _tap(ws, drv, sx + 4, sy + sh // 2)
    assert e.s.log == "", "the back chevron is off at the first value"
    for _ in range(3):
        _tap(ws, drv, sx + sw - 4, sy + sh // 2)
    assert (e.s.log, e.s.n) == (">>", 2), "the forward chevron stops at the last value"
    _tap(ws, drv, sx + 4, sy + sh // 2)
    assert (e.s.log, e.s.word) == (">><", "2 / 3")


def test_left_and_right_step_it_while_it_is_focused(tmp_path):
    ws, drv, e = _live(tmp_path, False)
    for k in ("right", "right", "right", "left"):
        drv.press(k)
        _settle(ws, drv)
    assert (e.s.log, e.s.n) == (">><", 1)

