"""The console APP API (docs/app_api_v1.md): register_app wires a cartridge
identity to a responsive system process -- launcher dispatch, router kind,
window minimums, text mode, relayout fan-out -- and Calc is the reference app
built only on the public seams (ui toolkit + the registry)."""

from pathlib import Path

import pytest

from runtime.layers import AppLayer
from runtime.app_decls import APPS

ROOT = Path(__file__).resolve().parent.parent


from ws_helpers import build_ws as _build_ws, select_on_home, use_theme
from tools.board_config import runtime_file
from ws_helpers import settle_badges  # noqa: E402


def _ws(tmp_path, **kw):
    """A workstation on the `night` fixture (tests/fixtures/themes/) in its
    dark mode, a palette theme with no look (the default's, flat) whose
    layout places the bar's context X its tool apps exit by; a test of a
    look sets its theme."""
    ws = _build_ws(tmp_path, **kw)
    use_theme(ws, "night", "dark")
    return ws


def _select(ws, title):
    it = select_on_home(ws, title)
    if it is not None:
        return it
    raise AssertionError(title + " not on the launcher")


# -- the registry --------------------------------------------------------------

def test_builtin_apps_are_registered(tmp_path):
    ws = _ws(tmp_path)
    kinds = [app.id for app in ws.app_layers]
    assert kinds == ["artwork", "myart", "appearance", "storybook",
                     "files", "calc", "getcarts", "jukebox", "terminal"]
    for kind in kinds:
        assert ws.layer_of(kind) is None                   # nothing to route to until it is built
        app = ws.app(kind)
        assert ws.layer_of(kind) is app                    # router wired, built at its first ask
    assert ws.spine.app_min_size("artwork") == (310, 230)       # registered minimum
    assert ws.spine.app_min_size("calc") == (170, 190)          # its manifest's min_size


def test_register_app_dispatches_a_custom_app(tmp_path):
    """A third-party app: one register_app call makes a launcher tap open it."""
    ws = _ws(tmp_path)

    class Demo(AppLayer):
        id = "demo"
        domain = "system"
        TITLE = "BATTLE DEMO"
        opened = 0

        def is_app(self, cart):
            return bool(cart) and cart.get("title") == "Brick Siege"

        def open(self):
            self.opened += 1

        def draw(self, dt):
            pass

        def handle_input(self, i):
            return True

        def handle_pointer(self, px, py, click):
            return True

    demo = Demo(ws)
    ws.spine.register_app(demo, min_size=(200, 100))
    assert ws._content_layers["demo"] is demo
    assert ws.spine.app_min_size("demo") == (200, 100)
    assert ws.spine.app_title("demo") == "BATTLE DEMO"
    _select(ws, "Brick Siege")
    ws.home.launch_selected()
    assert demo.opened == 1
    assert ws.screen == "demo"                            # back-stack kind


def test_late_app_metadata_reaches_windowed_wm(tmp_path):
    """TITLE and layout minimums are registry metadata, not WM id ladders."""
    ws = _ws(tmp_path, sys_size=(1024, 600), windowed=True)

    class DemoLayout:
        MIN_W = 210
        MIN_H = 130

    class Demo(AppLayer):
        id = "story_editor"
        domain = "system"
        TITLE = "Story Editor"

        def __init__(self):
            self.layout = DemoLayout()

    demo = Demo()
    ws.spine.register_app(demo)
    assert ws.spine.app_min_size(demo.id) == (210, 130)
    assert ws.wm.root_ctx.app_layouts[demo.id] is demo.layout
    win = type("Win", (), {"kind": demo.id})()
    assert ws.wm._win_title(win) == "Story Editor"


def test_a_ui_tree_apps_min_is_its_window_floor(tmp_path):
    """`ui.app(min=)` is the floor the console registers a ui tree app with."""
    ws = _ws(tmp_path, sys_size=(1024, 600), windowed=True)
    assert ws.spine.app_min_size("appearance") == (310, 230)
    assert ws.spine.app_min_size("jukebox") == (300, 220)


def test_files_types_only_while_its_rename_field_shows(tmp_path):
    """Files' rows are no text surface (the T-Deck's W A S D step them);
    its Rename dialog's field is, while it shows."""
    ws = _ws(tmp_path)
    _select(ws, "Files")
    ws.home.launch_selected()
    assert ws.screen == "files"
    assert not ws.input.text_mode
    ws.app("files").dialog = "rename"
    ws.frame(1 / 30)                  # the dialog draws, its field focused
    ws.frame(1 / 30)
    ws.input_policy.sync()            # and the input policy reads it
    assert ws.input.text_mode
    ws.app("files").dialog = None
    ws.frame(1 / 30)
    ws.input_policy.sync()
    assert not ws.input.text_mode


# -- Calc, the reference app ----------------------------------------------------

def test_calc_opens_from_its_identity_cart(tmp_path):
    ws = _ws(tmp_path)
    _select(ws, "Calc")
    ws.home.launch_selected()
    assert ws.screen == "calc"
    ws.frame(1 / 30)                                      # draws without error
    # Exit returns home (the tool-bar context X path uses ws.spine.exit).
    ws.spine.exit()
    assert ws.screen == "launcher"


class _Key:
    """One frame's input as an app's handler reads it: button `name`
    pressed, `typed` the key typed."""

    def __init__(self, name=None, typed=0):
        self.name = name
        self.last_key = self.typed = typed

    def steps(self, n):
        return int(bool(self.pressed(n)))

    def pressed(self, n):
        return n == self.name


def _calc(tmp_path, **kw):
    ws = _ws(tmp_path, **kw)
    _select(ws, "Calc")
    ws.home.launch_selected()
    calc = ws._content_layers["calc"]
    ws.frame(1 / 30)
    return ws, calc


def _settle_calc(ws, calc, n=3):
    for _ in range(n):
        calc.handle_input(_Key())
        ws.frame(1 / 30)


def _st(calc, name):
    return calc.engine.s._v[name]


def _key_rect(calc, key):
    return calc.engine._ui.box("dot" if key == "." else "key/" + key)


def _tap(ws, calc, key):
    """A tap on `key`: the press frame, then the release that activates it."""
    x, y, w, h = _key_rect(calc, key)
    calc.handle_pointer(x + w // 2, y + h // 2, True)
    ws.frame(1 / 30)
    _settle_calc(ws, calc)


def test_calc_math_via_taps(tmp_path):
    """7 x 8 = 56 through taps on the keys the page drew: the engine
    resolves the tap to the stop it went down on."""
    ws, calc = _calc(tmp_path)
    for k in ("7", "*", "8", "="):
        _tap(ws, calc, k)
    assert _st(calc, "entry") == "56"
    _tap(ws, calc, "C")
    assert _st(calc, "entry") == "0" and _st(calc, "op") == ""
    # Division by zero stays kid-friendly.
    for k in ("9", "/", "0", "="):
        _tap(ws, calc, k)
    assert _st(calc, "entry") == "OOPS"
    # % is the remainder, the backspace key drops the last digit.
    for k in ("C", "1", "7", "%", "5", "="):
        _tap(ws, calc, k)
    assert _st(calc, "entry") == "2"
    for k in ("1", "2", "3", "<"):
        _tap(ws, calc, k)
    assert _st(calc, "entry") == "12"                  # a digit after a sum starts afresh
    # Calc counts in whole numbers: the point key is drawn and is no stop.
    assert _key_rect(calc, ".") is None


def test_calc_arrows_move_focus_and_enter_presses(tmp_path):
    """Focus opens on 5; the arrows move it key to key and `a` presses the
    focused key; the keyboard types digits and operators."""
    ws, calc = _calc(tmp_path)
    for name in ("a", "right", "a", "down", "a"):
        calc.handle_input(_Key(name))
        ws.frame(1 / 30)
        _settle_calc(ws, calc, 1)
    assert _st(calc, "entry") == "563"
    for ch in "*2=":
        calc.handle_input(_Key(typed=ord(ch)))
        ws.frame(1 / 30)
    assert _st(calc, "entry") == "1126"
    calc.handle_input(_Key(typed=8))
    ws.frame(1 / 30)
    assert _st(calc, "entry") == "112"
    # A tap owes its release and rest frames, and then Calc paints nothing.
    _quiesce_frame(ws)
    _tap(ws, calc, "4")
    before = ws.frame_state.frames_drawn
    _settle_calc(ws, calc, 8)
    assert ws.frame_state.frames_drawn == before


def test_calc_keeps_a_tape(tmp_path):
    """Each sum lands on the tape, its newest at the foot; the operand
    banked shows over the result; a fresh open starts it empty."""
    ws, calc = _calc(tmp_path)
    for expr in ("48+72=", "120-36=", "84/7=", "12*7="):
        for ch in expr:
            calc.handle_input(_Key(typed=ord(ch)))
            ws.frame(1 / 30)
    assert [r._f["line"] for r in _st(calc, "tape")] == [
        "48 + 72 = 120", "120 - 36 = 84", "84 / 7 = 12", "12 * 7 = 84"]
    assert _st(calc, "result") == "84" and _st(calc, "expr") == ""
    for ch in "5-":
        calc.handle_input(_Key(typed=ord(ch)))
        ws.frame(1 / 30)
    assert _st(calc, "expr") == "5 −" and len(_st(calc, "tape")) == 4
    for _ in range(6):
        for ch in "1+1=":
            calc.handle_input(_Key(typed=ord(ch)))
            ws.frame(1 / 30)
    assert len(_st(calc, "tape")) == 8                   # the tape keeps its last eight
    calc.open()
    ws.frame(1 / 30)
    assert len(_st(calc, "tape")) == 0 and _st(calc, "entry") == "0"


def test_calc_tags_its_keys_by_kind():
    """Calc's one per-key decision (DESIGN.md, "Button kinds"): = the one
    primary, C danger, the operators tonal, the rest normal."""
    from runtime.calc_app import KEYS, kind_of
    kinds = dict((k, kind_of(k)) for k in KEYS)
    assert kinds["="] == "primary" and kinds["C"] == "danger"
    assert {kinds[k] for k in "+-*/%"} == {"tonal"}
    assert {kinds[k] for k in "0123456789.<"} == {"normal"}


def test_calc_reflows_and_declares_minimum(tmp_path):
    """The keys beside the display on a wide page, under it in a tall
    window; they grow with the page and stay inside it, the 0 two keys
    wide."""
    ws, calc = _calc(tmp_path)
    assert ws.spine.app_min_size("calc") == (170, 190)
    zero, equals, five = (_key_rect(calc, k) for k in "0=5")
    assert zero[2] > equals[2] * 2
    assert five[0] > ws.sys_canvas.w // 3                # beside the display
    ws2, calc2 = _calc(tmp_path / "desk", sys_size=(1024, 600))
    big = _key_rect(calc2, "5")
    assert big[2] > five[2]
    for k in "C<%/789*456-123+0=":
        x, y, w, h = _key_rect(calc2, k)
        assert x >= 0 and y >= 0 and x + w <= 1024 and y + h <= 600


def test_calc_is_app_rejects_lookalikes():
    from runtime.app_slot import AppSlot
    is_app = AppSlot(next(d for d in APPS if d["id"] == "calc")).is_app
    assert not is_app(None)
    assert not is_app({"title": "Calc", "permissions": ("graphics",), "path": "/x/moybyte.calc.moy"})
    assert not is_app({"title": "My Calc", "permissions": ("calc",), "path": "/x/moybyte.calc.moy"})
    assert is_app({"title": "Calc", "permissions": ("calc",), "path": "/carts/moybyte.calc.moy"})

# -- the bar contract is a HOST GUARANTEE (ui_refactor_2026-08 Phase 2) --------
#
# The router draws a registered app's strip ("app") and routes its band, so
# these are BEHAVIOURAL assertions, not a call-site count: a stub app that knows
# nothing about the bar must still show the strip and still exit on its
# context-X, and so must all seven shipped apps, through the same assertion --
# on the 320x240 handheld, whose system canvas IS the game canvas, and on the
# Guition S3's 480x320, whose system canvas is its own (the strip once went to
# the hidden game canvas there and left the app's bar band empty).

import hashlib

_DT = 1.0 / 30.0
_MAX_FRAMES = 6
_SHIPPED_APPS = ("artwork", "myart", "appearance", "storybook",
                 "files", "calc", "getcarts", "jukebox")


class _NakedApp(AppLayer):
    """An app written by someone who never read the bar paragraph: no strip
    draw, no bar-tap route, no layout of its own (so the host also has to
    supply the band height). It paints one flat colour, so any pixel the
    router adds is the bar and nothing else."""

    id = "naked"
    domain = "system"
    TITLE = "NAKED"

    def __init__(self):
        self.taps = []

    def is_app(self, cart):
        return False                   # opened explicitly, never claimed

    def open(self):
        pass

    def relayout(self, w, h, fs):
        pass

    def draw(self, dt):
        pass                           # filled by the harness below

    def handle_input(self, i):
        return True

    def handle_pointer(self, px, py, click):
        self.taps.append((px, py, click))
        return True


def _quiesce_frame(ws):
    """Everything transient or clock-driven off the frame (the shell-golden
    recipe): two renders taken a moment apart must differ only by the bar."""
    if ws.pointer is not None:
        ws.pointer.visible = False
    settle_badges(ws)
    ws.toast_until = 0
    ws._egg_until = 0
    ws._confetti_until = 0
    ws.show_achievements = False
    ws.show_fps = False
    ws.perf_hud = False
    ws.perf_capture = False
    ws.sysmenu.open = False
    ws.about = False
    ws.notice_up = None
    ws._notice_until = 0
    ws.bar_layer.clock_text = lambda: "00:00"


_SENTINEL = b"\x5a"      # a colour no surface paints, to prove nothing drew


def _settle(ws):
    """Wipe the canvas to a sentinel, then draw until two consecutive frames
    are byte-identical; return that frame.

    The wipe is load-bearing. Not every surface repaints the bar band -- the
    Appearance app leaves those rows alone -- so without it the STALE strip
    from the previous render survives into the muted one and the comparison
    silently reads as agreement. (It did, on exactly that app.)"""
    buf = ws.sys_canvas._buf
    buf[:] = _SENTINEL * len(buf)
    wm = ws.wm
    if getattr(wm, "has_desk", False):
        # The wipe is behind the WM's back: what it retains in this buffer
        # (the desk, the windows' stamps and chrome) is gone with it.
        wm._desk_streak = 0
        wm._win_sig = None
    # ...and so is what a content's context vouches its last frame left there
    # (a verbs page's next frame would move those pixels, docs/surface_model_v1.md
    # §14.7): its next frame draws whole
    for app in ws.app_layers:
        host = getattr(getattr(app, "_inst", app), "_ui", None) or getattr(getattr(app, "engine", None), "_ui", None)
        if host is not None and hasattr(host, "whole"):
            host.whole()
    prev = None
    for _ in range(_MAX_FRAMES):
        _quiesce_frame(ws)
        ws.mark_dirty()
        ws.frame(_DT)
        cur = bytes(ws.sys_canvas._buf)
        if cur == prev:
            return cur
        prev = cur
    raise AssertionError("surface never settled in %d frames" % _MAX_FRAMES)


def _mute_app_strip(ws):
    """Suppress ONLY the registered app's strip, leaving the other strip kinds
    alone -- the desk, launcher, picker, editor-menu, Settings and tool-cart
    bars must keep drawing, so a pixel difference here names the app bar and
    nothing else."""
    orig = ws.bar_layer.draw_status_strip

    def muted(where):
        if where == "app":
            return
        return orig(where)

    ws.bar_layer.draw_status_strip = muted


def _band(ws, frame):
    """The bar band's rows and everything below it, as two hashes."""
    stride = ws.sys_canvas.w * 2
    rows = ws.bar_layer._bar_h("app")
    top = frame[:stride * rows]
    rest = frame[stride * rows:]
    return hashlib.sha256(top).hexdigest(), hashlib.sha256(rest).hexdigest()


def _open_app_kind(ws, kind):
    if kind == "naked":
        app = _NakedApp()
        names = ws._NAMES if hasattr(ws, "_NAMES") else None
        colour = 7 if names is None else 7
        app.draw = lambda dt, cv=ws.sys_canvas, c=colour: cv.cls(c)
        ws.spine.register_app(app)
        ws.spine.open_app(app, cart=ws.carts.all[0])
        return app
    app = ws.app(kind)
    assert ws.spine.open_app(app), kind + " has no identity cart"
    return app


_SIZES = {"handheld": {}, "guition_s3": {"sys_size": (480, 320),
                                         "panel_diagonal_in": 3.5}}


@pytest.mark.parametrize("size", sorted(_SIZES))
@pytest.mark.parametrize("kind", _SHIPPED_APPS + ("naked",))
def test_host_draws_the_app_bar_without_the_app_asking(tmp_path, kind, size):
    """The strip's PIXELS appear over a registered app on the fullscreen tier,
    including over an app whose draw() never mentions a bar."""
    ws = _ws(tmp_path, **_SIZES[size])
    _open_app_kind(ws, kind)
    assert ws.screen == kind
    assert not ws.windowed_chrome
    with_bar = _settle(ws)
    _mute_app_strip(ws)
    without_bar = _settle(ws)
    top_a, rest_a = _band(ws, with_bar)
    top_b, rest_b = _band(ws, without_bar)
    assert top_a != top_b, kind + ": nothing drew in the bar band"
    assert rest_a == rest_b, kind + ": the bar leaked outside its band"


@pytest.mark.parametrize("size", sorted(_SIZES))
@pytest.mark.parametrize("kind", _SHIPPED_APPS + ("naked",))
def test_host_routes_the_context_x_and_the_app_exits(tmp_path, kind, size):
    """A tap on the context-X exits, and the app never sees the tap -- the bar
    is routed BEFORE handle_pointer, not after it."""
    ws = _ws(tmp_path, **_SIZES[size])
    app = _open_app_kind(ws, kind)
    assert ws.screen == kind
    x, y, w, h = ws.layout.context_x_btn
    ws.pointer.place(x + w // 2, y + h // 2)
    ws.pointer.click = True
    ws.router.handle_pointer()
    ws.pointer.click = False
    assert ws.wm.top_kind() == "launcher", kind + " did not exit on its bar X"
    if kind == "naked":
        assert app.taps == []          # the router consumed it first


def test_the_windowed_tier_still_suppresses_the_app_bar(tmp_path):
    """In the desk world the WM's title strip carries the close, so the host
    must draw NO app strip -- muting it may not change a single pixel."""
    ws = _ws(tmp_path, sys_size=(1024, 600), windowed=True)
    ws.spine.open_app(ws.app("calc"))
    assert ws.windowed_chrome                     # the make world is open
    with_bar = _settle(ws)
    _mute_app_strip(ws)
    without_bar = _settle(ws)
    assert with_bar == without_bar


def test_no_app_module_carries_the_bar_ritual():
    """The old road is closed: the strip/tap pair lives in the router, so no
    app module may reach the bar surface at all."""
    for name in ("calc_app", "artwork", "appearance_app", "files_app",
                 "storybook_app"):
        src = runtime_file(name + ".py").read_text(encoding="utf-8")
        assert "bar_layer" not in src, name + " still reaches ws.bar_layer"
