"""The browser draws what the boards draw: each of its two arrangements lays
out on the metric class of the board whose arrangement it is, and its image
carries the faces and the icon sets those boards freeze, so a theme's fonts
and its icon set resolve in the wasm as they do on the glass.

The handheld 320x240 is the T-Deck's (no glass declared, the handheld's
class); the 1024x600 desk is the Waveshare P4's (its 7-inch glass, the desk's
class: `layout_base.desk_diagonal_in`, the P4's glass at the P4's density). `tools/make_font.py module` writes each
image's `fonts_data` from its board.toml (`font_tier`, else `tier`); the
module the browser freezes is held here against each board's, and
`iconsets.carried` -- what the bar, the Editor's ladder and the C parts draw
from -- is evaluated under each image's module for every seed theme in both
variants.

Under MOYBYTE_WEB_E2E the real wasm console (dist/, booted in node) is held
to the host's workstation built in each board's arrangement -- the shell the
goldens pin -- frame for frame: the home, the desk, the Editor's Config tab,
Settings, Files and Appearance under the seed themes, pixel for pixel; the
console page awards achievements as a board does (the one-cart player keeps
none); and its pages run on the C engine from the compiled pages it carries. tests/test_editor_ladder_icons.py and tests/test_web_fonts.py
run the wasm too.
"""

import ast
import glob
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest

from runtime import fontset, iconsets, layout_base
from ws_helpers import build_ws, fresh_icon_caches

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import board_config, make_font  # noqa: E402

FW = ROOT / "firmware"
WEB = FW / "web_runner"
TDECK = FW / "lilygo_t_deck_plus_mainline"
P4 = FW / "esp32_p4_wifi6_touch_lcd_7b"
# Every board that freezes a font set: the console boards, the browser aside.
CONSOLES = sorted(Path(p).parent for p in glob.glob(str(FW / "*" / "build.sh"))
                  if "make_font.py\" module" in Path(p).read_text()
                  and Path(p).parent != WEB)
SEEDS = sorted(Path(p).stem for p in glob.glob(str(ROOT / "native" / "moy_ui" / "themes" / "*.json")))
VARIANTS = ("dark", "light")
# The browser's arrangements: (the board whose arrangement it is, whether
# web_boot declares a glass for it, the font tier of its class).
ARRANGEMENTS = {"handheld": (TDECK, False, "handheld"),
                "desk": (P4, True, "desktop")}


def _image(board):
    """The `fonts_data` board `board`'s image freezes, as a module."""
    ns = types.ModuleType("fonts_data")
    src = make_font.render_module(make_font.board_fonts(str(board)))
    exec(compile(src, "fonts_data", "exec"), ns.__dict__)
    return ns


def _tiers(board):
    t = make_font.board_fonts(str(board))
    return (t,) if isinstance(t, str) else t


def _web_glass(w=1024, h=600):
    """The diagonal web_boot declares for a `w` x `h` desk."""
    return layout_base.desk_diagonal_in(w, h)


def test_the_console_boards_are_found():
    names = sorted(b.name for b in CONSOLES)
    assert names == ["elecrow_crowpanel_p4_10_1", "esp32_p4_wifi6_touch_lcd_7b",
                     "guition_jc3248w535", "guition_jc8012p4a1c",
                     "lilygo_t_deck_plus_mainline", "m5stack_cores3_se"], names


@pytest.mark.parametrize("arrangement", sorted(ARRANGEMENTS))
def test_each_arrangement_lays_out_on_its_boards_class(arrangement):
    board, const, tier = ARRANGEMENTS[arrangement]
    declared = board_config.load(board).get("panel", {}).get("diagonal_in")
    glass = _web_glass() if const else None
    assert glass == declared, (arrangement, glass, declared)
    cls = layout_base.class_of(glass)
    assert cls == layout_base.class_of(declared)
    assert (cls == layout_base.DESK) == (tier == "desktop")
    assert _tiers(board) == (tier,)
    assert tier in _tiers(WEB), "the browser's image lacks the %s faces" % tier


def _glass_in():
    """web_boot.glass_in, executed over the host's layout_base."""
    tree = ast.parse((WEB / "web_boot.py").read_text())
    fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "glass_in"]
    ns = {"layout_base": layout_base}
    exec(compile(ast.Module(body=fn, type_ignores=[]), "web_boot", "exec"), ns)
    return ns["glass_in"]


def test_the_desk_arrangement_declares_its_glass_to_the_workstation():
    src = (WEB / "web_boot.py").read_text()
    assert "panel_diagonal_in=glass_in(width, height)" in src
    assert "ws.resize_glass(int(w), int(h), glass_in(int(w), int(h)))" in src
    assert src.count("panel_diagonal_in=") == 1, "only the desk declares a glass"


@pytest.mark.parametrize("wh", [(320, 240), (345, 280), (450, 300), (569, 240), (1023, 600),
                                (1100, 599)])
def test_a_page_glass_without_the_desk_s_room_is_the_handheld_s(wh):
    """A phone's or a small window's glass declares none, as the T-Deck: the
    handheld's class at chrome scale 1, never the desk's density lifting its
    16-pixel icons to 2 (the owner's 690x560 window, 2026-11-25)."""
    from runtime import chrome
    d = _glass_in()(*wh)
    assert d is None
    assert layout_base.class_of(d, *wh) == layout_base.HANDHELD
    assert chrome.chrome_scale_floor(wh[0], wh[1], d) == 1


@pytest.mark.parametrize("wh", [(1024, 600), (1100, 650), (1375, 812), (1920, 1080)])
def test_a_page_glass_with_the_desk_s_room_is_the_p4_s(wh):
    d = _glass_in()(*wh)
    assert d == layout_base.desk_diagonal_in(*wh)
    assert layout_base.class_of(d, *wh) == layout_base.DESK


def test_the_desk_keeps_the_p4s_density_at_any_size():
    """1024x600 is the P4's own 7 inches; a bigger page is a bigger panel at
    the same density, so its chrome is not lifted the way a 7-inch 1920x1080
    panel's would be."""
    from runtime import chrome
    assert layout_base.desk_diagonal_in(1024, 600) == 7.0
    for w, h in ((1024, 600), (1280, 800), (1920, 1080), (2560, 1440)):
        assert chrome.chrome_scale_floor(w, h, layout_base.desk_diagonal_in(w, h)) == 1, (w, h)


def test_the_browser_carries_what_its_boards_freeze():
    web = _image(WEB)
    faces, icons = set(), set()
    for board in CONSOLES:
        if not set(_tiers(board)) <= set(_tiers(WEB)):
            continue
        img = _image(board)
        assert set(img.FACES) <= set(web.FACES), board.name
        for name, data in img.ICONS.items():
            assert web.ICONS.get(name) == data, (board.name, name)
        faces |= set(img.FACES)
        icons |= set(img.ICONS)
    assert sorted(web.FACES) == sorted(faces), "the browser carries a face no board does"
    assert sorted(web.ICONS) == sorted(icons), "the browser carries an icon file no board does"
    assert "system_icons.moygfx" in web.ICONS


@pytest.fixture(scope="module")
def theme_specs(tmp_path_factory):
    """{(theme, variant): the icon set its look names}, uncarried."""
    ws = build_ws(tmp_path_factory.mktemp("parity"))
    out = {}
    for name in SEEDS:
        for variant in VARIANTS:
            ws.look.set_theme(name, persist=False, variant=variant)
            out[(name, variant)] = iconsets.spec(ws.look.live.look)
    return out


def _carried(monkeypatch, board, specs):
    monkeypatch.setattr(fontset, "_data", _image(board))
    fresh_icon_caches(monkeypatch)
    return {k: iconsets.carried(s) for k, s in specs.items()}


@pytest.mark.parametrize("arrangement", sorted(ARRANGEMENTS))
def test_every_seed_theme_draws_its_boards_icon_set_in_the_browser(
        monkeypatch, theme_specs, arrangement):
    assert SEEDS == ["blocks", "contrast", "moy"], SEEDS    # a new seed joins this net
    assert theme_specs[("moy", "dark")] == ("smooth", "default", None)
    board = ARRANGEMENTS[arrangement][0]
    on_glass = _carried(monkeypatch, board, theme_specs)
    web = _carried(monkeypatch, WEB, theme_specs)
    assert web == on_glass
    assert web[("moy", "dark")] == ("smooth", "default", None)



@pytest.mark.skipif(not os.environ.get("MOYBYTE_WEB_E2E"),
                    reason="MOYBYTE_WEB_E2E not set (boots the built wasm console)")
def test_the_browser_console_awards_achievements_as_a_board_does():
    from web_e2e import require
    require()
    if not (WEB / "dist" / "micropython.mjs").exists():
        pytest.skip("no built firmware/web_runner/dist")
    py = ("import json, web_boot\n"
          "_n0 = _ws.ach.count()\n"
          "web_boot.open_cart('Star Catcher')\n")
    report = ("print('ACH ' + json.dumps({'before': _n0, 'after': _ws.ach.count(),"
              " 'toast': _ws.ach.toast is not None}))\n")
    steps = [{"frames": 30}, {"py": py}, {"frames": 10}, {"py": report}]
    with tempfile.TemporaryDirectory() as tmp:
        scenario = Path(tmp) / "ach.json"
        scenario.write_text(json.dumps({"size": [320, 240], "windowed": False, "steps": steps}))
        r = subprocess.run(["node", "pageshot.mjs", str(scenario), str(Path(tmp) / "shots")],
                           cwd=WEB, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and "Traceback" not in r.stdout, r.stdout[-3000:] + r.stderr[-500:]
    line = [ln for ln in r.stdout.splitlines() if "ACH " in ln]
    assert line, r.stdout[-3000:]
    got = json.loads(line[0].split("ACH ", 1)[1])
    assert got["after"] > got["before"], got     # First Steps, as on a board


@pytest.mark.skipif(not os.environ.get("MOYBYTE_WEB_E2E"),
                    reason="MOYBYTE_WEB_E2E not set (boots the built wasm console)")
def test_the_browser_console_draws_its_pages_on_the_c_engine_from_compiled_pages():
    """The wasm carries native/moy_uitree and the console's compiled pages
    (firmware/web_runner/build.sh), so its pages run on the C engine as on a
    board, loaded from the compiled pages."""
    from web_e2e import require
    require()
    if not (WEB / "dist" / "micropython.mjs").exists():
        pytest.skip("no built firmware/web_runner/dist")
    report = ("import json, sys, uitree_aot\n"
              "print('UIT ' + json.dumps({'c': 'uitree_c' in sys.modules, 'pages': len(uitree_aot.BLOBS)}))\n")
    steps = [{"frames": 30}, {"py": "_ws.open_settings()\n"}, {"frames": 10}, {"py": report}]
    with tempfile.TemporaryDirectory() as tmp:
        scenario = Path(tmp) / "uit.json"
        scenario.write_text(json.dumps({"size": [320, 240], "windowed": False, "steps": steps}))
        r = subprocess.run(["node", "pageshot.mjs", str(scenario), str(Path(tmp) / "shots")],
                           cwd=WEB, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and "Traceback" not in r.stdout, r.stdout[-3000:] + r.stderr[-500:]
    line = [ln for ln in r.stdout.splitlines() if "UIT " in ln]
    assert line, r.stdout[-3000:]
    got = json.loads(line[0].split("UIT ", 1)[1])
    assert got["c"] and got["pages"] > 0, got


# -- the frames themselves -----------------------------------------------------
#
# Each scene runs on the host's workstation in the board's arrangement and in
# the real wasm console, and the two framebuffers are compared pixel for
# pixel. The clock reads a fixed time in both (the host's zone is not node's),
# the pointer is hidden (the page boots it hidden; the host draws the
# cursor), achievements stay quiet (a toast's slide is timed by the clock),
# Settings' About names no facts (the host names the board it stands in
# for, the browser none: rows below the fold the page's thumb measures), and
# the host has the browser's radio and light, none (its FakeWifi and a
# board's light would draw a Wi-Fi glyph and rows the browser does not).
_STEADY = ("_ws.bar_layer.clock_text = lambda: '12:00'\n"
           "_ws.settings_layer._read_about = lambda: ()\n"
           "_ws.pointer.visible = False\n"
           "_ws.ach.mute = True\n"
           "_ws.ach.toast = None\n"
           "_ws.wifi = None\n"
           "_ws.panel_light = False\n"
           "_ws.look.set_theme(%r, persist=False, variant=%r)\n")
_EDITOR = ("_ws.open_in_editor([c for c in _ws.carts.all if c.get('title') == 'Star Catcher'][0])\n"
           "_ws.text.set_menu_view('cards')\n")
_APP = "_ws.spine.open_app(_ws.app(%r))\n"
# (arrangement, scene, theme, variant, what the scene does after the setup)
SCENES = [("handheld", "home", "moy", "dark", ""),
          ("handheld", "editor_config", "moy", "dark", _EDITOR),
          ("handheld", "settings", "moy", "light", "_ws.open_settings()\n"),
          ("handheld", "files", "contrast", "dark", _APP % "files"),
          ("handheld", "home", "blocks", "light", ""),
          ("desk", "desk", "moy", "dark", ""),
          ("desk", "editor_config", "moy", "light", _EDITOR),
          ("desk", "appearance", "moy", "dark", _APP % "appearance"),
          ("desk", "desk", "contrast", "light", ""),
          ("desk", "settings", "blocks", "dark", "_ws.open_settings()\n")]
SIZES = {"handheld": (320, 240), "desk": (1024, 600)}


def _host_frame(tmp_path, arrangement, src):
    from runtime import host_app
    from ws_helpers import device_frames, ship_shelf
    w, h = SIZES[arrangement]
    glass = _web_glass(w, h) if arrangement == "desk" else None
    ws = host_app.build_workstation(str(tmp_path / "carts"), sys_size=(w, h),
                                    windowed=arrangement == "desk",
                                    panel_diagonal_in=glass)
    ship_shelf(ws, "web")                  # the browser bundle's shelf
    device_frames(ws, 30)
    exec(src, {"_ws": ws})
    ws.mark_dirty()
    device_frames(ws, 20)
    cv = ws.glass if ws.glass is not None else ws.run.canvas
    assert (cv.w, cv.h) == (w, h)
    stride = getattr(cv, "_stride", 0) or cv.w
    buf = bytes(cv._buf)
    return [buf[2 * (y * stride + x)] << 8 | buf[2 * (y * stride + x) + 1]
            for y in range(h) for x in range(w)]


def _web_frame(tmp_path, arrangement, src):
    w, h = SIZES[arrangement]
    steps = [{"frames": 30}, {"py": src + "_ws.mark_dirty()\n"}, {"frames": 20},
             {"shot": "frame"}]
    tmp_path.mkdir(parents=True, exist_ok=True)
    scenario = tmp_path / "scene.json"
    scenario.write_text(json.dumps({"size": [w, h], "windowed": arrangement == "desk",
                                    "steps": steps}))
    r = subprocess.run(["node", "pageshot.mjs", str(scenario), str(tmp_path / "shots")],
                       cwd=WEB, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and "Traceback" not in r.stdout, r.stdout[-3000:] + r.stderr[-500:]
    from PIL import Image
    img = Image.open(tmp_path / "shots" / "frame.png").convert("RGB")
    assert img.size == (w, h)
    return [(p[0] >> 3) << 11 | (p[1] >> 2) << 5 | (p[2] >> 3) for p in img.getdata()]


@pytest.mark.skipif(not os.environ.get("MOYBYTE_WEB_E2E"),
                    reason="MOYBYTE_WEB_E2E not set (boots the built wasm console)")
@pytest.mark.parametrize("arrangement,scene,theme,variant,src", SCENES,
                         ids=["%s-%s-%s-%s" % sc[:4] for sc in SCENES])
def test_the_browser_draws_the_boards_frame(tmp_path, arrangement, scene, theme, variant, src):
    from web_e2e import require
    require()
    pytest.importorskip("PIL")
    if not (WEB / "dist" / "micropython.mjs").exists():
        pytest.skip("no built firmware/web_runner/dist")
    full = _STEADY % (theme, variant) + src
    host = _host_frame(tmp_path / "host", arrangement, full)
    web = _web_frame(tmp_path / "web", arrangement, full)
    w = SIZES[arrangement][0]
    diff = [(i % w, i // w) for i, (a, b) in enumerate(zip(host, web)) if a != b]
    box = None
    if diff:
        xs = [p[0] for p in diff]
        ys = [p[1] for p in diff]
        box = (min(xs), min(ys), max(xs), max(ys))
    assert not diff, "%d pixels differ from the host's %s %s frame, in %s" % (
        len(diff), arrangement, scene, box)
