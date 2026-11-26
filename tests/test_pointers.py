"""The pointer's families (runtime/toolkit/pointers.py over
native/moy_ui/icons/pointer/pointer_art.py's art, built by
tools/make_icons.py): every family draws every shape at every size its
hotspot on the shape, a tier carries every family at its sizes, a theme
wears its own family unless Appearance picks one, and the console draws the
pick where the pointer stands."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "native" / "moy_ui" / "icons" / "pointer"))

import make_icons  # noqa: E402
import pointer_art  # noqa: E402
from runtime import host_app, pointers, ui_draw  # noqa: E402
from ws_helpers import build_ws  # noqa: E402

DT = 1 / 30
META = json.loads((ROOT / "native" / "moy_ui" / "icons" / "set.json").read_text())


def test_the_runtime_and_the_art_name_the_same_families_shapes_and_layers():
    assert pointers.FAMILIES == pointer_art.FAMILIES
    assert pointers.SHAPES == pointer_art.SHAPES
    assert len(pointer_art.LAYERS) == 3
    assert META["pointers"]["families"] == list(pointers.FAMILIES)
    assert META["pointers"]["shapes"] == list(pointers.SHAPES)
    assert tuple(sorted({s for t in make_icons.POINTER_SIZES.values() for s in t})) == \
        pointers.SIZES


@pytest.mark.parametrize("family", pointer_art.FAMILIES)
def test_every_shape_has_its_hotspot_on_it_at_every_size(family):
    """The hotspot is a pixel the shape covers, at every size: where a press
    lands is what the pointer shows. Busy's is its middle, which a ring
    leaves open."""
    for shape in pointer_art.SHAPES:
        for px in pointers.SIZES:
            hx, hy, w, h, layers = pointer_art.render(family, shape, px)
            a = layers["line"]
            if shape != "busy":
                assert a[hy * w + hx] > 96, (shape, px)
                continue
            xs = [x for x in range(w) if any(a[y * w + x] > 96 for y in range(h))]
            ys = [y for y in range(h) if any(a[y * w + x] > 96 for x in range(w))]
            near = px // 8 + 1
            assert abs(xs[0] + xs[-1] - 2 * hx) <= near and abs(ys[0] + ys[-1] - 2 * hy) <= near


@pytest.mark.parametrize("family", pointer_art.FAMILIES)
def test_an_arrow_and_a_hand_point_with_the_apex_of_their_outline(family):
    """The hotspot is the outline's apex, a pixel the outline covers whole,
    with the fill starting within 2 px below it (3 at 48 px, under a 2 px
    keyline): an arrow's has no outline above it, a hand's at most the 2
    rows a thick keyline puts over it."""
    for shape in ("arrow", "hand"):
        for px in pointers.SIZES:
            hx, hy, w, h, layers = pointer_art.render(family, shape, px)
            a, f = layers["line"], layers["fill"]
            assert a[hy * w + hx] >= 250, (shape, px, a[hy * w + hx])
            top = hy if shape == "arrow" else hy - 2
            assert not any(a[y * w + x] for y in range(max(0, top)) for x in range(w)), (shape, px)
            if family == "pixel" and px > 16:
                continue                # its 16 px art, cells grown whole
            first = min(y for y in range(h) for x in range(w) if f[y * w + x] >= 128)
            assert first - hy <= max(2, px // 16), (shape, px, first - hy)


@pytest.mark.parametrize("tier", sorted(make_icons.POINTER_SIZES))
def test_a_tier_carries_every_family_at_its_sizes(tier):
    lines = "\n".join(make_icons.module_lines(tier))
    for family in pointers.FAMILIES:
        for px in make_icons.POINTER_SIZES[tier]:
            assert "'ptr-%s-%d.fnt'" % (family, px) in lines


def test_a_glyph_drawn_at_the_hotspot_puts_the_hotspot_there(tmp_path):
    """The file's pen is the hotspot: the shape drawn at (x, y) inks (x, y),
    and its box holds it."""
    ws = build_ws(tmp_path)
    cv = ws.sys_canvas
    for family in pointers.FAMILIES:
        for shape in pointers.SHAPES:
            cv.cls(5)
            before = bytes(cv._buf)
            assert pointers.draw(cv, family, shape, 100, 80, 16)
            at = (80 * cv.w + 100) * 2
            assert bytes(cv._buf)[at:at + 2] != before[at:at + 2], (family, shape)
            x, y, w, h = pointers.box(family, shape, 100, 80, 16)
            assert x <= 100 < x + w and y <= 80 < y + h


def test_the_size_follows_the_chrome_scale_and_large():
    assert pointers.size("moy", 1) == 16
    assert pointers.size("moy", 1, True) == 32
    assert pointers.size("moy", 2) == 32
    assert pointers.size("moy", 2, True) == 48
    assert pointers.size("moy", 4) == 48     # the largest the image holds


@pytest.mark.parametrize("theme,family", [("moy", "moy"), ("blocks", "blocks"),
                                          ("contrast", "moy")])
def test_a_seed_theme_wears_its_own_family(tmp_path, theme, family):
    ws = build_ws(tmp_path)
    ws.look.set_theme(theme, persist=False)
    assert ws.look.pointer_family() == family
    assert ws.look.choices()["own_pointer"] == family


def test_a_pick_outranks_the_theme_and_draws_where_the_pointer_stands(tmp_path):
    ws = build_ws(tmp_path)
    ws.look.set_theme("blocks", persist=False)
    ws.look.set_pointer("luna")
    d = host_app.ConsoleDriver(ws)
    d.hover(160, 120)
    d.frame(DT)
    ws.pointer.visible = True
    d.frame(DT)
    assert ws.look.pointer_at(1) == ("luna", 16)
    assert ws.pointer_box() == pointers.box("luna", ws.pointer_shape() or "arrow", 160, 120, 16)
    ws.look.set_pointer("nonesuch")
    assert ws.look.pointer_pick == "" and ws.look.pointer_at(1) == ("blocks", 16)


@pytest.mark.parametrize("old,new", [("default", "moy"), ("playful", "blocks")])
def test_a_saved_pick_of_a_renamed_family_reads_as_its_new_name(tmp_path, old, new):
    """Moy and Blocks were Default and Playful until 2026-11-26: a pick saved
    under the old id wears the family it became."""
    ws = build_ws(tmp_path)
    ws.system.set("pointer", old)
    ws.look.set_pointer(ws.system.get("pointer", ""), persist=False)
    assert ws.look.pointer_pick == new


def test_a_font_reset_under_the_pointer_loads_its_file_again(tmp_path):
    ws = build_ws(tmp_path)
    assert pointers.draw(ws.sys_canvas, "coast", "hand", 50, 50, 16)
    ui_draw.font_reset()
    assert pointers.draw(ws.sys_canvas, "coast", "hand", 50, 50, 16)


def test_the_page_wears_the_familys_own_pixels(tmp_path):
    """The browser's pointer is the page's CSS cursor, drawn from the
    family's pixels (web_boot._cursor_images): the shape at 1x and at the
    high density, straight RGBA, opaque where the shape is whole, clear
    beyond it, the hotspot on it, made once a family and shape."""
    import binascii
    for p in ("firmware/web_runner", "device"):
        if str(ROOT / p) not in sys.path:
            sys.path.insert(0, str(ROOT / p))
    web_boot = pytest.importorskip("web_boot")
    build_ws(tmp_path)                          # the faces and the binding up
    key, ratio, imgs = web_boot._cursor_images("blocks", False, "hand")
    assert key == "blocks/0/hand" and ratio == 2
    for (w, h, hx, hy, b64), px in zip(imgs, (16, 32)):
        rgba = binascii.a2b_base64(b64)
        assert len(rgba) == w * h * 4
        bx, by, bw, bh = pointers.box("blocks", "hand", 0, 0, px)
        assert (w, h, hx, hy) == (bw, bh, -bx, -by)
        assert rgba[4 * (hy * w + hx) + 3] > 200          # the fingertip, opaque
        assert rgba[3] == 0                                # the box's corner, clear
    assert web_boot._cursor_images("blocks", False, "hand")[0] is key
    assert web_boot._cursor_images("pixel", True, "arrow")[1] == 1.5


@pytest.mark.parametrize("desk", [False, True])
def test_a_still_pointer_over_partial_frames_keeps_its_pixels(tmp_path, desk):
    """Its blended edges and shadow are drawn over what was under them, never
    over its own last stamp (`pointers.Under`): frames that paint around a
    still pointer leave the picture under it as it was."""
    from ws_helpers import build_desktop_ws
    ws = build_desktop_ws(tmp_path, panel_diagonal_in=7) if desk else build_ws(tmp_path)
    d = host_app.ConsoleDriver(ws)
    for _ in range(3):
        d.frame(DT)
    d.hover(150, 150)
    d.frame(DT)
    ws.pointer.visible = True
    cv, x, y = ws.sys_canvas, 150, 150

    def around():
        b = bytes(cv._buf)
        return [b[((y + j) * cv.w + x - 4) * 2:((y + j) * cv.w + x + 40) * 2]
                for j in range(-4, 48)]
    for _ in range(2):                          # (the page's hover and its shape, settled)
        ws.mark_dirty()
        d.frame(DT)
        d.frame(DT)
    first = around()
    for i in range(9):
        if i % 3 == 0:
            ws.mark_dirty()
        d.frame(DT)
        assert around() == first, i


def test_a_load_and_a_window_drag_wear_their_shapes(tmp_path):
    """The frame that shows the LOADING pill wears busy (the load runs after
    it), and a window in a drag wears move."""
    from ws_helpers import build_desktop_ws
    ws = build_desktop_ws(tmp_path, panel_diagonal_in=7)
    d = host_app.ConsoleDriver(ws)
    d.hover(300, 300)
    d.frame(DT)
    assert ws.pointer_shape() != "busy"
    ws.deferred.append((lambda: None, True, False))
    assert ws.pointer_shape() == "busy"
    ws.deferred.clear()
    ws.wm._drag = ("files", 0, 0)
    assert ws.pointer_shape() == "move"
