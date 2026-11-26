"""The passive passes -- a window's strip and the notices, pages drawn with
no input and no focus -- begin on one toolkit context
(`ui_draw.passive_frame`): each draws what it draws on a context of its
own, and a page that needs a stop, a focus or kept state across frames
holds its own."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_wm_windowed import _moy_desk  # noqa: E402
from ws_helpers import no_unlock_banner  # noqa: E402

import ui_draw  # noqa: E402

FRAMES = 12


def _desk_frames(tmp_path, own, monkeypatch):
    """The desk's glass over `FRAMES` frames with Calc's window and a
    notice up; `own`: each passive pass on a fresh context of its own."""
    if own:
        def fresh(cv, th, rect, desk):
            return ui_draw.ui_frame(ui_draw.ui_context(), cv, th, rect=rect, desk=desk,
                                    elsewhere=True)
        monkeypatch.setattr(ui_draw, "passive_frame", fresh)
    ws = no_unlock_banner(_moy_desk(tmp_path))     # (a badge's banner shines with the clock)
    ws.spine.open_app(ws.app("calc"))
    ws.notices.notice("Saved", "to My Art")
    out = []
    for _ in range(FRAMES):
        ws.frame(1 / 30)
        out.append(bytes(ws.sys_canvas._buf))
    return out


def test_a_passive_pass_draws_on_the_shared_context_what_it_draws_on_its_own(
        tmp_path, monkeypatch):
    shared = _desk_frames(tmp_path / "shared", False, monkeypatch)
    own = _desk_frames(tmp_path / "own", True, monkeypatch)
    assert shared == own


def test_no_pass_gives_the_passive_context_input_or_focus(tmp_path, monkeypatch):
    """Every begin on the passive context takes no input with the keys
    elsewhere, and no host walks focus onto it."""
    seen = []
    frame, focus = ui_draw.ui_frame, ui_draw.focus_on

    def spy_frame(ctx, cv, th, rect=None, inp=None, **kw):
        if ctx is ui_draw._PASSIVE[0]:
            seen.append((inp, kw.get("elsewhere")))
        return frame(ctx, cv, th, rect=rect, inp=inp, **kw)

    def spy_focus(ctx, id):
        assert ctx is not ui_draw._PASSIVE[0], id
        return focus(ctx, id)

    monkeypatch.setattr(ui_draw, "ui_frame", spy_frame)
    monkeypatch.setattr(ui_draw, "focus_on", spy_focus)
    _desk_frames(tmp_path, False, monkeypatch)
    assert seen and set(seen) == {(None, True)}, seen
