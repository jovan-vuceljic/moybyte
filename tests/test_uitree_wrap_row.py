"""`ui.row(wrap=True)` on the C engine (tests/uitree_fixtures/uitree_wrap_row.py):
its children from the row's start at their natural widths, gap= apart, the
one that does not fit starting a line under them; a group as wide as its
widest child, never a share of the row."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))

from runtime import ui_draw  # noqa: E402
from ws_helpers import build_ws  # noqa: E402


class _Damage:
    def all(self):
        pass


@pytest.fixture(params=["built", "compiled"])
def paint(tmp_path, request, monkeypatch):
    """Paint the fixture's page into a rect `w` wide on the desk; its
    buttons' boxes."""
    import uitree_app
    import uitree_aot
    if request.param == "compiled":
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import uitree_compile as UC
        monkeypatch.setattr(uitree_aot, "BLOBS", UC.compile_modules(["uitree_wrap_row"]).pages)
    import uitree_wrap_row as F
    ws = build_ws(tmp_path)
    host = ui_draw.AppHost()
    pg = uitree_app.hosted_page(F.page, host, _Damage())
    pg.open()
    assert pg._loaded == (request.param == "compiled")

    def at(w):
        cv, th = ws.sys_canvas, ws.theme_colors
        rect = (10, 20, w, 300)
        for _ in range(2):
            host.begin(cv, th, rect, True, elsewhere=True)
            pg.paint(0.0, cv, th, rect, True)
        return [host.box("press/%d" % k) for k in range(4)]
    return at


def test_the_buttons_pack_from_the_rows_start_gap_apart(paint):
    boxes = paint(900)
    assert len({b[1] for b in boxes}) == 1, boxes
    x0 = boxes[0][0]
    assert x0 < 10 + 40, "from the row's start, not centred: %r" % (boxes,)
    for a, b in zip(boxes, boxes[1:]):
        assert b[0] - (a[0] + a[2]) == 14, boxes


def test_a_button_that_does_not_fit_starts_a_line_under_them(paint):
    wide = paint(900)
    w = wide[2][0] + wide[2][2] - wide[0][0] + 20       # room for three
    boxes = paint(w)
    assert boxes[0][1] == boxes[1][1] == boxes[2][1] < boxes[3][1], boxes
    assert boxes[3][0] == boxes[0][0], "the new line starts at the row's start"
    assert boxes[3][1] >= boxes[0][1] + boxes[0][3] + 14, "the lines gap= apart"
