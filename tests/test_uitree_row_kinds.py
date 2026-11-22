"""A list's rows on the C engine beyond a toggle and a slider
(tests/uitree_fixtures/uitree_row_kinds.py): a seg bound to a row's int
field, a canvas handed its row, a dialog that on the T-Deck lets the band's
keys be its buttons, and the items a host adds to the band."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))

from runtime import ui_draw  # noqa: E402
from runtime import host_app  # noqa: E402
from ws_helpers import build_ws  # noqa: E402


class _Damage:
    def all(self):
        pass


class _Keys:
    """One frame's input: `name` pressed."""
    typed = 0

    def __init__(self, name):
        self.name = name

    def pressed(self, n):
        return n == self.name

    def steps(self, n):
        return 1 if n == self.name else 0

    def held(self, n):
        return False


@pytest.fixture(params=["built", "compiled"])
def page(tmp_path, request, monkeypatch):
    """The fixture's page, built, or loaded from the blob its compile made
    (a board's: the front end's functions found again by name)."""
    import uitree_app
    import uitree_aot
    if request.param == "compiled":
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import uitree_compile as UC
        monkeypatch.setattr(uitree_aot, "BLOBS", UC.compile_modules(["uitree_row_kinds"]).pages)
    import uitree_row_kinds as F        # the module the compile left imported
    ws = build_ws(tmp_path)
    host = ui_draw.AppHost()
    pg = uitree_app.hosted_page(F.page, host, _Damage())
    pg.open()
    assert pg._loaded == (request.param == "compiled")
    pg._bind()
    pg.run_action(pg.actions["fill"], ([{"id": "a", "shape": "seg", "k": 1, "words": "one\ntwo\nthree"},
                                        {"id": "b", "shape": "pic", "k": 0, "words": ""},
                                        {"id": "c", "shape": "pic", "k": 0, "words": ""}],), "host")
    was = ui_draw.input_kind(), ui_draw.hint_kind()

    def paint():
        cv, th = ws.sys_canvas, ws.theme_colors
        rect = (0, 0, cv.w, cv.h)
        for _ in range(2):
            host.begin(cv, th, rect, False)
            pg.paint(0.0, cv, th, rect, False)
    pg.test_paint, pg.test_ws, pg.test_host, pg.test_F = paint, ws, host, F
    paint()
    yield pg
    ui_draw.input_kind(was[0])
    ui_draw.hint_kind(was[1])


def test_a_seg_bound_to_a_row_field_steps_it_and_hands_its_row(page):
    F = page.test_F
    assert page.stop_kinds()["a/k"] == "cycle"
    assert page.focus_key == "a/k"
    page.keys(_Keys("right"))
    page.test_paint()
    assert F.s.rows[0].k == 2 and F.s.log == "a=2"
    page.keys(_Keys("right"))           # past its last item: back to its first
    page.test_paint()
    assert F.s.rows[0].k == 0 and F.s.log == "a=0"


def test_a_canvas_in_a_list_is_handed_its_row(page):
    F = page.test_F
    F.DRAWN[:] = []
    page.test_paint()
    assert {d[0] for d in F.DRAWN} == {"b", "c"} and all(d[2] == 30 for d in F.DRAWN)
    for _ in range(2):
        page.keys(_Keys("down"))
        page.test_paint()
    assert page.focus_key == "c/pic"
    F.KEYS[:] = []
    page.keys(_Keys("right"))
    assert F.KEYS == ["c"]
    assert page.hints()[:2] == ("confirm", "Take")
    x, y, w, h = page._x.rect("b/pic")
    assert page._x.rect("c/pic")[1] > y
    page.point(x + 4, y + 7, True)
    page.test_paint()                   # the frame runs what the press queued
    assert F.s.log == "up b 7", F.s.log       # a press and its release, each handed row b


def _dialog_pixels(page, kind):
    ui_draw.input_kind(kind)
    ui_draw.hint_kind("keys")
    page.test_paint()
    cv = page.test_ws.sys_canvas
    return bytes(cv._buf)[: cv.w * 2 * (cv.h - 40)]


def test_a_keys_dialog_draws_no_buttons_on_the_t_deck_and_names_its_fields(page):
    F = page.test_F
    page._bind()
    page.run_action(page.actions["ask"], (), "host")
    keys, tdeck = _dialog_pixels(page, "keys"), _dialog_pixels(page, "tdeck")
    assert keys != tdeck                # the buttons' row is gone on the T-Deck
    h = page.hints()
    assert h[:2] == ("scroll", "Field"), h
    assert "cancel" in h                # in a field the key that never types


def test_a_host_adds_items_to_the_band_before_back(page):
    page.band_extra(("F6", "Next pane"))
    page.test_paint()
    h = page.hints()
    assert h[-4:-2] == ("F6", "Next pane"), h
