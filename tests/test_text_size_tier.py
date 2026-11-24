"""A text size that crosses the desk's line moves the tier live
(`Workstation.place_tier`): Settings' Large on a 1024x600 desk draws its
next frame on the full-screen stack, the handheld's class, as a console
booted at Large draws it, and Normal brings the desk back, Settings in its
window, as a console booted at Normal has it. No frame draws the windowed
tier at a scale the desk does not fit.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from runtime import host_app, layout_base  # noqa: E402
from runtime.wm import FullscreenStackWM  # noqa: E402
from runtime.wm_windowed import WindowedWM  # noqa: E402
from ws_helpers import quiesce  # noqa: E402

DT = 1 / 30


def _boot(path, fs):
    ws = host_app.build_workstation(str(path / "carts"), sys_size=(1024, 600), panel_diagonal_in=7.0,
                                    font_scale=fs, windowed=True)
    ws.bar_layer.clock_text = lambda: "10:30"
    quiesce(ws)
    return ws, host_app.ConsoleDriver(ws)


def _frames(ws, drv, n=4):
    for _ in range(n):
        ws.mark_dirty()
        drv.frame(DT)


def _settings_at_its_text_size(path, fs):
    """A console booted at `fs`, Settings open on its Text size row."""
    ws, drv = _boot(path, fs)
    _frames(ws, drv)
    ws.open_settings()
    ws.settings_layer.focus_row("font_scale")
    _frames(ws, drv)
    return ws


def test_large_and_back_move_the_tier_live(tmp_path, monkeypatch):
    ws, drv = _boot(tmp_path / "live", 1)
    _frames(ws, drv)
    ws.open_settings()
    _frames(ws, drv)
    assert isinstance(ws.wm, WindowedWM) and ws.wm.mode == "desktop"

    windowed = []
    draw = WindowedWM.draw_stack
    monkeypatch.setattr(WindowedWM, "draw_stack",
                        lambda wm: windowed.append(wm.ws.look.font_scale) or draw(wm))
    ws.look.cycle_font_scale(1)                 # Settings' Text size: Large
    assert ws.look.font_scale == 2
    drawn = ws.frame_state.frames_drawn
    _frames(ws, drv)
    assert ws.frame_state.frames_drawn > drawn
    assert windowed == [], "a frame drew the windowed tier at Large"
    assert type(ws.wm) is FullscreenStackWM
    assert ws.metric_class == layout_base.HANDHELD == layout_base.metric_class()
    assert ws.wm.stack.kinds() == ["launcher", "settings"]
    booted = _settings_at_its_text_size(tmp_path / "large", 2)
    assert bytes(ws.sys_canvas._buf) == bytes(booted.sys_canvas._buf), \
        "Large live is not Large booted"

    ws.look.cycle_font_scale(-1)                # Normal
    _frames(ws, drv)
    assert isinstance(ws.wm, WindowedWM) and ws.wm.mode == "desktop"
    assert ws.metric_class == layout_base.DESK == layout_base.metric_class()
    assert list(ws.wm.windows) == ["settings"]
    assert windowed and set(windowed) == {1}, "the windowed tier drew at Normal alone"
    booted = _settings_at_its_text_size(tmp_path / "normal", 1)
    assert bytes(ws.sys_canvas._buf) == bytes(booted.sys_canvas._buf), \
        "Normal live is not Normal booted"


def test_a_size_the_desk_still_fits_keeps_the_windows(tmp_path):
    """On a 2048x1200 desk Large still holds the desk's 1024x600: the tier
    stays and the windows with it."""
    ws = host_app.build_workstation(str(tmp_path / "carts"), sys_size=(2048, 1200), panel_diagonal_in=7.0,
                                    font_scale=1, windowed=True)
    drv = host_app.ConsoleDriver(ws)
    ws.open_settings()
    _frames(ws, drv)
    wm = ws.wm
    ws.look.cycle_font_scale(1)
    _frames(ws, drv)
    assert ws.wm is wm and ws.wm.mode == "desktop" and "settings" in ws.wm.windows


def test_an_app_built_on_the_desk_follows_the_tier(tmp_path):
    """Storybook, built and open in a desk window, is closed by the swap to
    Large and opens again as the handheld's, saying where stories are made;
    back at Normal it opens as the desk's, its editor with it."""
    from runtime import storybook_app as SB
    ws, drv = _boot(tmp_path, 1)
    app = ws.app("storybook")
    ws.spine.open_app(app)
    _frames(ws, drv)
    assert app.desk and "storybook" in ws.wm.windows
    ws.open_settings()
    ws.look.cycle_font_scale(1)
    _frames(ws, drv)
    assert not ws.wm.stack.has("storybook") and not app.desk
    ws.spine.open_app(app)
    _frames(ws, drv)
    assert ws.wm.top_kind() == "storybook" and app.engine.band
    assert (SB.s.made_on, SB.s.made_how) == SB.MADE_SMALLER[:2]
    ws.look.cycle_font_scale(-1)
    _frames(ws, drv)
    ws.spine.open_app(app)
    _frames(ws, drv)
    assert app.desk and "storybook" in ws.wm.windows and app.ed is not None
