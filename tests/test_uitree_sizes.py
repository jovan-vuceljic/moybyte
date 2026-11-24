"""What a flowing page's sizes do on the C engine (tests/uitree_fixtures/uitree_sizes.py):
a label's scale= and w=, a button's look="hero", a group's gap=, a row in a group's
column, and a grow= row that stands what follows it at the page's foot."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))

from runtime import ui_draw  # noqa: E402
from ws_helpers import build_ws  # noqa: E402

RECT = (10, 20, 900, 400)


class _Damage:
    def all(self):
        pass


@pytest.fixture(params=["built", "compiled"])
def boxes(tmp_path, request, monkeypatch):
    """Paint one of the fixture's pages into RECT on the desk; its buttons' boxes."""
    import uitree_app
    import uitree_aot
    if request.param == "compiled":
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import uitree_compile as UC
        monkeypatch.setattr(uitree_aot, "BLOBS", UC.compile_modules(["uitree_sizes"]).pages)
    import uitree_sizes as F
    ws = build_ws(tmp_path)

    def at(name, n):
        host = ui_draw.AppHost()
        pg = uitree_app.hosted_page(getattr(F, name), host, _Damage())
        pg.bare = True                   # on its ground, no band: as the desk home's pane
        pg.band = False
        pg.open()
        assert pg._loaded == (request.param == "compiled")
        cv, th = ws.sys_canvas, ws.theme_colors
        for _ in range(2):
            host.begin(cv, th, RECT, True, elsewhere=True)
            pg.paint(0.0, cv, th, RECT, True)
        return [host.box("press/%d" % k) for k in range(n)]
    return at


def test_a_labels_scale_draws_its_face_that_many_times_as_tall(boxes):
    two, three = boxes("page_s2", 1)[0], boxes("page_s3", 1)[0]
    assert three[1] - two[1] == ui_draw.font("title")[2], "a line of the face a scale on: %r %r" % (two, three)


def test_a_labels_w_keeps_its_text_that_wide(boxes):
    wide, narrow = boxes("page_wide", 1)[0], boxes("page_narrow", 1)[0]
    assert narrow[1] > wide[1], "a narrower measure takes more lines: %r %r" % (wide, narrow)


def test_a_large_button_is_half_again_as_tall_and_roomier(boxes):
    plain, large, normal = boxes("page_foot", 3)
    assert large[3] == plain[3] * 3 // 2, (plain, large)
    assert large[2] >= 112 and large[2] > normal[2], (large, normal)


def test_a_grow_row_stands_what_follows_it_at_the_pages_foot(boxes):
    plain, large, _n = boxes("page_foot", 3)
    # the last row counts the gap a row leaves after it (2 px), as every row of the page
    # does: with it the rows end at the page's foot, so the page fits and never scrolls
    assert large[1] + large[3] + 2 == RECT[1] + RECT[3], large
    assert large[1] - (plain[1] + plain[3]) == 20, "the group's gap= between its children"
