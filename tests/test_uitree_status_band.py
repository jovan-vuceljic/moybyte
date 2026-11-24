"""A row's hidden status keeps the row's cells through a rows frame.

A row with a `ui.status(shown=...)` cell that is not shown still has a
status line's height and its band (`row_cells`). The band is the row's
ground, drawn before its cells; a frame that draws rows alone (the text view
above it changing, the floor of `moy_ui_api_shift_plan`) leaves the cells'
pixels as the last frame drew them, so a band painted over them without going
through that floor (`moy_ui_api_status_band`) wiped Notes' tools row on the
first rows frame, on the handheld and on the desk. Notes' tools row is that
row (`status` shown while a save or run was refused); each frame of a typing
session on two consoles, one as it ships and one drawing every frame whole,
is held to the same bytes.
"""

import pytest

from test_notes_rows import Pair, audit, clock  # noqa: F401 -- fixtures the pair runs under


def _type(p):
    p.keys("down", 2)
    p.typed("hello there")
    p.keys("up", 1)
    p.settle()


def _tools_row_drawn(p):
    """The tools row's buttons are on the glass: the strip they stand in is
    not one flat colour."""
    c = p.a.sys_canvas
    w = c.w
    x, top, cw, h = 0, 0, w, c.h
    if p.desk:                      # the cart's window
        win = p.a.wm.windows["desktop"]
        x, top, cw, h = win.x, win.y, win.w, win.h
    buf = bytes(c._buf)
    cols = set()
    for y in range(top + h - 30, top + h - 4):
        cols.update(buf[(y * w + x) * 2:(y * w + x + cw // 2) * 2:2])
    return len(cols) > 2


@pytest.mark.parametrize("desk", (False, True))
def test_a_rows_frame_leaves_the_tools_row_under_a_hidden_status(tmp_path, desk):
    p = Pair(tmp_path, 1, desk=desk)
    assert p.a.run.player.ns["s"].status == "", "the status cell is the hidden one"
    _type(p)
    assert "rows" in p.kinds, "the session drew rows frames: %r" % p.kinds
    assert _tools_row_drawn(p), "the tools row is on the glass after the rows frames"


@pytest.mark.parametrize("desk,look", ((False, {}), (True, {}), (True, {"font_scale": 1, "panel_diagonal_in": 7.0})))
def test_a_hints_band_that_goes_leaves_no_pixel_behind(tmp_path, desk, look):
    """A placed page's hints band takes its foot only while the focus has
    hints, and the page's rows move with it: Notes' vault row says New note,
    Rename and Move to Trash, the open note's text editor says nothing. The
    page's gen counts the band, so the frame the band goes draws whole and the
    keys it showed are not left under the tools that moved down."""
    p = Pair(tmp_path, 1, desk=desk, **look)
    assert bytes(p.a.sys_canvas._buf) == bytes(p.b.sys_canvas._buf), "the open note, drawn as it ships"
