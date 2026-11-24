"""An app cart's window draws at the shell's font scale: the canvas a window
lends a run carries no scale of its own, so the run's face (`ui_face`) takes
the shell's, as the run's layout does (`Player._layout_args`)."""

import os

import pytest

from runtime import host_app, layout_base

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _handheld_after():
    yield
    layout_base.place_class(layout_base.HANDHELD)


def _ws(tmp_path, size, fs):
    return host_app.build_workstation(str(tmp_path / "carts"), sys_size=size, font_scale=fs,
                                      windowed=True, panel_diagonal_in=7.0)


def test_an_app_cart_s_window_draws_at_the_shell_s_font_scale(tmp_path):
    """A Lua app's window lends it a canvas of its own, which carries no
    scale: the run's face takes the shell's font scale, as its layout does
    (`Player._layout_args`), so its text grows with everything around it."""
    import shutil
    from runtime.host import lora_sim
    from runtime.player_face import _FACE_FS_SHIFT
    from ws_helpers import open_cart
    mesh = os.path.join(ROOT, "tests", "fixtures", "apps", "moymesh.moy")
    ws = _ws(tmp_path, (2048, 1200), 2)           # a glass that holds the desk at 2
    assert type(ws.wm).__name__ == "WindowedWM"
    ws.home.open_desk()
    shutil.copytree(mesh, os.path.join(str(ws.carts_root), "moymesh.moy"))
    ws.carts.rescan()
    lora_sim.install()
    try:
        open_cart(ws, "Moy Mesh")
        run = ws.run
        assert run.app_window_canvas and getattr(run.canvas, "font_scale", 1) == 1
        assert run.player.face.ui_face() >> _FACE_FS_SHIFT == 2
    finally:
        lora_sim.remove()
