"""Settings' Text size offers a size only where it is usable: the font scales
a glass offers are those whose room -- the panel over the render scale and
the font scale -- still holds the handheld's smallest layout, the T-Deck's
320x240 (`layout_base.font_scales`, read through `Appearance.font_scales`).
The rule reads the screen alone: its pixels and the scales the tier has. A
stored scale the glass does not offer is the largest it does; the row steps
through the offered sizes, and is hidden where there is one."""

import hashlib

import pytest

from runtime import host_app, layout_base
from pixel_goldens import rgb565_rows
from ws_helpers import build_ws

# (the panel, its declared diagonal, the sizes it offers): the golden boards'
# glasses (tests/test_shell_goldens.py CONFIGS) and the Guition P4's
GLASSES = (
    (None, None, (1,)),                     # the T-Deck: one canvas, text that does not scale
    ((480, 320), 3.5, (1,)),                # the Guition S3
    ((800, 480), None, (1, 2)),             # an 800x480 glass
    ((1024, 600), 7.0, (1, 2)),             # the Waveshare P4
    ((1280, 800), 10.1, (1, 2, 3)),         # the Guition P4
)


@pytest.fixture(autouse=True)
def _handheld_after():
    yield
    layout_base.place_class(layout_base.HANDHELD)


def _ws(tmp_path, size, diag, fs=1):
    return build_ws(tmp_path, sys_size=size, panel_diagonal_in=diag, font_scale=fs,
                    windowed=size is not None and diag is not None and diag >= 5)


def _glass(ws):
    drv = host_app.ConsoleDriver(ws)
    for _ in range(4):
        ws.mark_dirty()
        drv.frame(1 / 30)
    cv = ws.glass_canvas
    return hashlib.sha1(bytes(b for row in rgb565_rows(cv._buf, cv.w, cv.h) for b in row)).hexdigest()


def test_the_rule_reads_the_glass_alone():
    assert layout_base.font_scales(320, 240) == (1,)
    assert layout_base.font_scales(640, 480) == (1, 2)
    assert layout_base.font_scales(960, 720) == (1, 2, 3)
    assert layout_base.font_scales(959, 720) == (1, 2)
    assert layout_base.font_scales(1280, 800, render=2) == (1,)


@pytest.mark.parametrize("size, diag, offered", GLASSES)
def test_each_glass_offers_the_sizes_it_fits(tmp_path, size, diag, offered):
    ws = _ws(tmp_path, size, diag)
    assert ws.look.font_scales() == offered


@pytest.mark.parametrize("size, diag, offered", [g for g in GLASSES if len(g[2]) > 1])
def test_every_offered_size_changes_the_drawn_screen(tmp_path, size, diag, offered):
    """Each size the row offers draws a screen none of the others does: the
    row never offers one that leaves the screen as it was."""
    ws = _ws(tmp_path, size, diag)
    seen = {}
    for f in offered:
        ws.look.set_font_scale(f, persist=False)
        assert ws.look.font_scale == ws.look.effective_font_scale() == f
        seen.setdefault(_glass(ws), []).append(f)
    assert len(seen) == len(offered), seen


def test_a_stored_size_the_glass_does_not_fit_is_its_largest(tmp_path):
    """A scale stored on a bigger glass (the store moved, a panel swapped)
    boots as the largest this one offers, and stays stored for that glass."""
    big = _ws(tmp_path, (1280, 800), 10.1)
    big.look.set_font_scale(3)
    p4 = _ws(tmp_path, (1024, 600), 7.0)
    assert p4.look.font_scale == 2
    assert type(p4.wm).__name__ == "FullscreenStackWM"      # 512x300: no desk
    assert p4.system.get("font_scale") == 3
    tdeck = _ws(tmp_path, None, None)
    assert tdeck.look.font_scale == tdeck.look.effective_font_scale() == 1
    _glass(tdeck)


@pytest.mark.parametrize("size, diag, offered", [GLASSES[0], GLASSES[3]])
def test_the_text_size_row_offers_what_the_glass_does(tmp_path, size, diag, offered):
    """The row steps through the offered sizes alone, and is hidden where the
    glass offers one."""
    from runtime import settings_rows
    ws = _ws(tmp_path, size, diag)
    ws.open_settings()
    _glass(ws)
    s = settings_rows.s
    assert tuple(int(r.v) for r in s.sizes) == offered
    assert s.has_sizes == (len(offered) > 1)
    if len(offered) > 1:
        def pick():                     # the row's own step, as its cycle hands it
            s.font_scale = str(offered[-1])
            settings_rows.font_set()
        ws.settings_layer.rows.engine.run(pick, action="font_set")
        assert ws.look.font_scale == offered[-1]
