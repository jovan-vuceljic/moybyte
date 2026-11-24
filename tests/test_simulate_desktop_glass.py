"""`tools/simulate_desktop.py`'s glass: the console its arguments build, and
the frames it presents."""

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import simulate_desktop  # noqa: E402
from runtime import layout_base  # noqa: E402


def _ws(tmp_path, *argv):
    args = simulate_desktop.parse_args(list(argv) + ["--save-dir", str(tmp_path / "carts")])
    return simulate_desktop.build_workstation(args)


@pytest.mark.parametrize("size", ["1024x600", "1920x1080"])
def test_windowed_is_the_desk_at_the_p4s_density(tmp_path, size):
    ws = _ws(tmp_path, "--size", size, "--windowed")
    assert ws.metric_class == layout_base.DESK
    assert ws.wm.has_desk
    assert ws.chrome_floor == 1


def test_a_big_canvas_without_windows_is_the_handheld(tmp_path):
    ws = _ws(tmp_path, "--size", "960x600", "--font-scale", "2")
    assert ws.metric_class == layout_base.HANDHELD
    assert ws.look.font_scale == 2
    assert not getattr(ws.wm, "has_desk", False)
