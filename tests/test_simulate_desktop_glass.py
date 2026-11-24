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


def _desk_frame(tmp_path):
    from runtime import host_app
    ws = _ws(tmp_path, "--size", "1024x600", "--windowed")
    driver = host_app.ConsoleDriver(ws)
    for _ in range(10):
        driver.frame(1 / 30)
    ws.open_settings()
    for _ in range(10):
        driver.frame(1 / 30)
    return ws.glass_canvas


def _expand(indexed):
    indices, colours = indexed
    return b"".join(colours[i] for i in indices)


def test_the_indexed_readout_is_to_rgb888s_pixels(tmp_path):
    cv = _desk_frame(tmp_path)
    first = cv.to_indexed()
    assert first is not None
    assert _expand(first) == cv.to_rgb888()
    # Words the map has not met yet join it, and the pixels stay to_rgb888's.
    mv = memoryview(cv._buf).cast("H")
    for i, word in enumerate((0x1234, 0x0841, 0xF81F)):
        mv[i * 7] = word
    assert _expand(cv.to_indexed()) == cv.to_rgb888()


def test_a_surrogate_pair_of_words_reads_as_two_pixels(tmp_path):
    cv = _desk_frame(tmp_path)
    mv = memoryview(cv._buf).cast("H")
    mv[0], mv[1] = 0xD800, 0xDC00          # one character, decoded as UTF-16
    assert _expand(cv.to_indexed()) == cv.to_rgb888()


def test_more_words_than_a_palette_holds_read_through_to_rgb888(tmp_path):
    cv = _desk_frame(tmp_path)
    mv = memoryview(cv._buf).cast("H")
    for i in range(300):
        mv[i] = 0x0100 + i
    assert cv.to_indexed() is None


def test_the_window_shows_to_rgb888s_pixels(tmp_path, monkeypatch):
    pygame = pytest.importorskip("pygame")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    cv = _desk_frame(tmp_path)
    pygame.display.init()
    try:
        screen = pygame.display.set_mode((cv.w, cv.h))
        simulate_desktop.present(screen, cv, 1)
        assert pygame.image.tobytes(screen, "RGB") == cv.to_rgb888()
    finally:
        pygame.display.quit()
