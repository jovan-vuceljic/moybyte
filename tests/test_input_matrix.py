"""The input conformance matrix (#242's I1; docs/refactor_2026-11.md, phase 4):
every widget kind under every input as its driver delivers it, on every
layer an app is written in.

  * ROWS, the widget kinds: a field, a list, a button, a popover, a dialog
    and a text view, each the one widget of a UI tree page.
  * COLUMNS, the inputs, each through its driver's own entry point on the
    host and never by setting the input table or calling the engine:
    the T-Deck keyboard's matrix (native/moy_input/moy_kbd.c, over an I2C
    fake: typing, and its move keys), a BLE keyboard (moy_hid.c, over a fake
    stack), the desk keyboard, the touchscreen, a mouse, the trackball and a
    gamepad (the host driver's entry points: runtime/run/host_api.py's
    ConsoleDriver), Esc as the host delivers it, and the T-Deck's Mic key (the
    matrix). Every column runs on a board's input table (moy_input's
    InputTable), the one the boards' drivers write.
  * LAYERS, the fronts of the one engine: a Python shell app (a system app's
    `uitree_app.App`), a Python cart app, a Lua app and a compiled app (C on
    sdk/include/moybyte/uitree.h, built to WASI). An ELF app has no tree and
    is no layer.

A cell is a gesture: what that input does to that widget (open a field's
edit, type into it and cancel the edit, step a list, press a button, dismiss a popover,
choose a dialog's button, drag a text view), and its effect read back from
the app's state: the engine's store on the Python layers, the state table
on the Lua layer, and the engine's trace of its state's changes on the
compiled layer. A text view's scroll is no state: its effect is the
picture moving.

Every cell passes: a cell is never marked as an expected failure.
"""

import importlib.util
import json
import os
import re
import shutil
import sys

import pytest

from runtime import moy_input as mi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
DT = 1.0 / 30.0

ROWS = ("field", "list", "button", "popover", "dialog", "text_view")
COLUMNS = ("kbd_text", "kbd_move", "ble_kbd", "desk_kbd", "touch", "mouse", "trackball", "gamepad",
           "esc", "mic")
LAYERS = ("py_shell", "py_app", "lua_app", "wasm_app")

# What each input does to each widget: the gesture a cell runs. A widget an
# input has no gesture for is no cell (a touchscreen types nothing). A field
# is a stop until Enter, A, a tap, a click or the trackball's press opens its
# edit: a key's gesture opens it first, and the T-Deck's move key crosses it
# before (it types nothing there) and types once the edit is open.
GESTURES = {
    "field": {"kbd_text": "type", "kbd_move": "type_move", "ble_kbd": "type",
              "desk_kbd": "type", "touch": "edit", "mouse": "edit", "trackball": "edit",
              "gamepad": "edit", "esc": "cancel", "mic": "cancel"},
    "list": {"kbd_move": "next", "ble_kbd": "next", "desk_kbd": "next", "touch": "next",
             "trackball": "next", "gamepad": "next"},
    "button": {"kbd_text": "press", "kbd_move": "press", "ble_kbd": "press", "desk_kbd": "press",
               "touch": "press", "trackball": "press", "gamepad": "press"},
    "popover": {"ble_kbd": "dismiss", "desk_kbd": "dismiss", "touch": "dismiss",
                "gamepad": "dismiss", "esc": "dismiss", "mic": "dismiss"},
    "dialog": {"kbd_text": "choose", "kbd_move": "choose", "ble_kbd": "choose",
               "desk_kbd": "choose", "trackball": "choose", "gamepad": "choose"},
    "text_view": {"touch": "scroll"},
}
# Not cells, because the engine's contract (docs/app_api_v1.md) defines no
# such gesture: a dialog's Esc, B or Mic take its first button (Back's
# order), and a text view's keys, pad and trackball step it as a stop.

NOT_CELLS = set()

CELLS = [(layer, row, col) for layer in LAYERS for row in ROWS for col in COLUMNS
         if col in GESTURES[row] and (layer, row, col) not in NOT_CELLS]

TYPED = "h"
LINES = "\n".join("line %d" % i for i in range(40))

# Each row's state, the one its gesture changes.
STATE = {"field": "t", "list": "c", "button": "n", "popover": "up", "dialog": "up",
         "text_view": None}


# -- the pages, one source a layer ------------------------------------------------

PY = {
    "field": '''s = ui.state(t="")
ui.app("Matrix", icon="calc")


def build():
    with ui.page("Matrix"):
        ui.field("Name", "t", max=16)
''',
    "list": '''s = ui.state(items=ui.model(key="id", id=""), c="one")
ui.app("Matrix", icon="calc")


def opened():
    s.items = [{"id": "one"}, {"id": "two"}, {"id": "three"}]


def pick(row):
    s.c = row.id


ui.hook("opened", opened)
ui.action("pick", "Pick", pick, takes="row")


def build():
    with ui.page("Matrix"):
        with ui.group("Pick"):
            with ui.rows("items"):
                ui.link("pick", label="{.id}")
''',
    "button": '''s = ui.state(n=0)
ui.app("Matrix", icon="calc")


def go():
    s.n += 1


ui.action("go", "Go", go)


def build():
    with ui.page("Matrix"):
        ui.button("go")
''',
    "popover": '''s = ui.state(up=True)
ui.app("Matrix", icon="calc")


def nothing():
    pass


def shut():
    s.up = False


ui.action("anchor", "Anchor", nothing)
ui.action("into", "In", nothing)
ui.action("shut", "Close", shut)


def build():
    with ui.page("Matrix"):
        ui.button("anchor")
        with ui.popover("pop", w=120, anchor="anchor", close="shut", shown="up"):
            ui.button("into")
''',
    "dialog": '''s = ui.state(up=True)
ui.app("Matrix", icon="calc")


def shut():
    s.up = False


ui.action("no", "No", shut)
ui.action("yes", "Yes", shut)


def build():
    with ui.page("Matrix"):
        with ui.dialog("Sure?", ["no", "yes"], shown="up"):
            ui.label("Really?")
''',
    "text_view": '''s = ui.state(lines=%r)
ui.app("Matrix", icon="calc")


def build():
    with ui.page("Matrix"):
        ui.text_view("lines")
''' % LINES,
}

LUA = {
    "field": '''ui.app("Matrix", { icon = "calc" })
S = ui.state { t = "" }
ui.page("matrix", function()
  ui.field("t", { label = "Name", max = 16 })
end, { title = "Matrix" })
''',
    "list": '''ui.app("Matrix", { icon = "calc" })
S = ui.state { items = ui.model { key = "id", id = "" }, c = "one" }
ui.hook("opened", function()
  S.items:set({ { id = "one" }, { id = "two" }, { id = "three" } })
end)
ui.action("pick", "Pick", function(row) S.c = row.id end, { takes = "row" })
ui.page("matrix", function()
  ui.group("Pick", function()
    ui.rows("items", function() ui.link("pick", { label = "{.id}" }) end)
  end)
end, { title = "Matrix" })
''',
    "button": '''ui.app("Matrix", { icon = "calc" })
S = ui.state { n = 0 }
ui.action("go", "Go", function() S.n = S.n + 1 end)
ui.page("matrix", function()
  ui.button("go")
end, { title = "Matrix" })
''',
    "popover": '''ui.app("Matrix", { icon = "calc" })
S = ui.state { up = true }
ui.action("anchor", "Anchor", function() end)
ui.action("into", "In", function() end)
ui.action("shut", "Close", function() S.up = false end)
ui.page("matrix", function()
  ui.button("anchor")
  ui.popover("pop", { w = 120, anchor = "anchor", close = "shut", shown = "up" }, function()
    ui.button("into")
  end)
end, { title = "Matrix" })
''',
    "dialog": '''ui.app("Matrix", { icon = "calc" })
S = ui.state { up = true }
ui.action("no", "No", function() S.up = false end)
ui.action("yes", "Yes", function() S.up = false end)
ui.page("matrix", function()
  ui.dialog("Sure?", { buttons = { "no", "yes" }, shown = "up" }, function()
    ui.label("Really?")
  end)
end, { title = "Matrix" })
''',
    "text_view": '''ui.app("Matrix", { icon = "calc" })
S = ui.state { lines = %s }
ui.page("matrix", function()
  ui.text_view("lines")
end, { title = "Matrix" })
''' % json.dumps(LINES),
}

C = {
    "field": '''static void page(void) {
    ut_page("matrix", "Matrix") ut_field("t", "Name");
}

EXPORT(_init) void _init(void) {
    ut_text("t", "");
    ut_open(page);
}
''',
    "list": '''enum { F_ID };
static int32_t s_items, s_c;

static void opened(int32_t row) {
    static const char rows[] = "one\\0two\\0three";
    uitree_set_model(s_items, 3, rows, sizeof rows);
}

static void pick(int32_t row) {
    char k[16];
    ut_get_cell(s_items, row, F_ID, k, sizeof k);
    ut_set_text(s_c, k);
}

static void page(void) {
    ut_page("matrix", "Matrix") {
        ut_group("Pick") {
            ut_rows("items", NULL) ut_link("pick", "{.id}");
        }
    }
}

EXPORT(_init) void _init(void) {
    s_items = ut_model("items", "id", F_ID, UT_TEXT);
    s_c = ut_text("c", "one");
    ut_hook("opened", opened);
    ut_action("pick", "Pick", pick);
    ut_open(page);
}
''',
    "button": '''static int32_t s_n;

static void go(int32_t row) { uitree_set_int(s_n, uitree_get_int(s_n) + 1); }

static void page(void) {
    ut_page("matrix", "Matrix") ut_button("go", NULL);
}

EXPORT(_init) void _init(void) {
    s_n = ut_int("n", 0);
    ut_action("go", "Go", go);
    ut_open(page);
}
''',
    "popover": '''static int32_t s_up;

static void nothing(int32_t row) {}

static void shut(int32_t row) { uitree_set_int(s_up, 0); }

static void page(void) {
    ut_page("matrix", "Matrix") {
        ut_button("anchor", NULL);
        ut_in(ut_node(UT_POPOVER, "pop")) {
            ut_p_w(120);
            ut_p_anchor("anchor");
            ut_p_close("shut");
            ut_p_shown("up");
            ut_button("into", NULL);
        }
    }
}

EXPORT(_init) void _init(void) {
    s_up = ut_bool("up", 1);
    ut_action("anchor", "Anchor", nothing);
    ut_action("into", "In", nothing);
    ut_action("shut", "Close", shut);
    ut_open(page);
}
''',
    "dialog": '''static int32_t s_up;

static void shut(int32_t row) { uitree_set_int(s_up, 0); }

static void page(void) {
    ut_page("matrix", "Matrix") {
        ut_dialog("Sure?", "up", "no", "yes") ut_label("Really?");
    }
}

EXPORT(_init) void _init(void) {
    s_up = ut_bool("up", 1);
    ut_action("no", "No", shut);
    ut_action("yes", "Yes", shut);
    ut_open(page);
}
''',
    "text_view": '''static void page(void) {
    ut_page("matrix", "Matrix") ut_text_view("lines");
}

EXPORT(_init) void _init(void) {
    ut_text("lines", "%s");
    ut_open(page);
}
''' % LINES.replace("\n", "\\n"),
}

C_APP = '''#include "moybyte/uitree.h"

#define EXPORT(name) __attribute__((export_name(#name)))

%s
EXPORT(_layout) void _layout(int32_t w, int32_t h, int32_t fs) {}
EXPORT(_update) void _update(float dt) {}
EXPORT(_draw) void _draw(void) { ut_frame(); }
'''


def _shell_layer(tmp, row):
    """The row's page as a system app: its Python source a module of its
    own, registered the way the console registers one."""
    import uitree_app
    name = "matrix_shell_" + row
    path = tmp / (name + ".py")
    path.write_text("import uitree as ui\n" + PY[row])
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return uitree_app.app_layer("matrix", "Matrix", mod.build)


# -- one layer's run of one page ---------------------------------------------------

class Kbd:
    """The T-Deck keyboard's I2C answer: one matrix frame a read."""

    def __init__(self):
        self.t = 1000
        self.frames = []

    def ms(self):
        return self.t

    def us(self):
        return self.t * 1000

    def sleep_ms(self, n):
        self.t += n

    def readfrom(self, _addr, n):
        return self.frames.pop(0) if self.frames else bytes(n)

    def writeto(self, _addr, data):
        pass


def _matrix(*keys, mic=False):
    d = bytearray(5)
    for at, bit, code, _sym in mi.raw_keys():
        if chr(code) in keys:
            d[at] |= bit
    if mic:
        d[0] |= 0x40
    return bytes(d)


_STATE_LINE = re.compile(r"\[trace\] \S+\s+state\s+(\S+)\s+(.*?)\s+->\s+(.*?)\s+\(")


def _value(v):
    """A state's value as the effects compare it: a bool its 0 or 1, a
    trace's quoted text its text, its digits their int."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, str) and len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1]
    if v in ("true", "false", "True", "False"):
        return int(v in ("true", "True"))
    if isinstance(v, str) and re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


class Rig:
    """A workstation on a board's input table with every driver attached,
    one page open on one layer."""

    def __init__(self, tmp_path, layer, row, monkeypatch, built):
        from runtime import host_app
        from runtime.host import moy_log
        from ws_helpers import open_cart
        import uitree_parity as P
        monkeypatch.setattr(host_app, "InputState", mi.InputTable)
        self.layer, self.row = layer, row
        self.tmp, self.monkeypatch, self.built = tmp_path, monkeypatch, built
        root = str(tmp_path / "carts")
        host_app.moy_carts.ensure_dirs(root)
        tree = {"extensions": ["moybyte.uitree"]}
        if layer == "py_app":
            _write(root, "matrix_py.moy", dict(tree, runtime="python", main="main.py"), {"main.py": PY[row]})
        elif layer == "lua_app":
            _write(root, "matrix_lua.moy", dict(tree, runtime="lua", main="main.lua"), {"main.lua": LUA[row]})
        elif layer == "wasm_app":
            shutil.copytree(built[row], os.path.join(root, "matrix_c.moy"))
        self.ws = ws = host_app.build_workstation(root)
        # A board's inputs as the hints know them, the T-Deck's and the
        # host's: the Mic key's tap is a field's Cancel where the T-Deck
        # keyboard is the input in use.
        ws.use_inputs((("kbd", "tdeck"), ("ball", "tdeck"), ("ble", "keys"),
                       ("local", "keys"), ("touch", "touch")))
        ws.look.set_theme("moy", persist=False)
        ws.pointer.visible = False
        ws.bar_layer.clock_text = lambda: "10:30"
        self.drv = host_app.ConsoleDriver(ws)
        self.kbd_bus = Kbd()
        self.kbd_bus.frames = [b"\x00"]
        self.kbd = mi.KbdDriver(ws.input, self.kbd_bus)
        self.kbd.raw_mode = True
        from test_ble_keyboard import FakeStack, _ready
        self.ble = mi.HidMachine(ws.input, FakeStack())
        _ready(self.ble)
        self.seq = moy_log.next()
        if layer == "py_shell":
            self.app = P.host(ws, _shell_layer(tmp_path, row))
        else:
            open_cart(ws, "Matrix")
            if ws.confirm.open:
                act = ws.confirm._act
                ws.confirm.cancel()
                act()
            assert ws.run.player.cart_error is None, ws.run.player.cart_error
        self.frames(4)

    # -- frames and reads

    def frames(self, n=1):
        from ws_helpers import quiesce
        for _ in range(n):
            self.kbd.pass_()
            self.ble.frame()
            quiesce(self.ws)
            self.ws.mark_dirty()
            self.drv.frame(DT)

    def engine(self):
        """The Python layers' engine, else None."""
        if self.layer == "py_shell":
            return self.app.engine
        if self.layer == "py_app":
            return self.ws.run.player.tree.engine
        return None

    def state(self):
        """The row's state: {name: value}, and a text view's picture."""
        name = STATE[self.row]
        if name is None:
            return {"pic": self.shot()}
        if self.row == "field":
            got = self._state(name)
            got["typing"] = int(bool(self.ws.input_policy.typing()))
            return got
        return self._state(name)

    def _state(self, name):
        eng = self.engine()
        if eng is not None:
            return {name: _value(eng.s._v[name])}
        if self.layer == "lua_app":
            lua = self.ws.run.player.lua
            assert lua.exec("__READ = S.%s; if type(__READ) == 'boolean' then __READ = __READ and 1 or 0 end"
                            % name, "test") is None
            return {name: _value(lua.get_global("__READ"))}
        from runtime.host import moy_log
        v = {"t": "", "c": "one", "n": 0, "up": 1}[name]
        for r in moy_log.read(self.seq, 4000):
            m = _STATE_LINE.search(r[4])
            if m and m.group(1) == name:
                v = _value(m.group(3))
        return {name: v}

    def shot(self):
        return bytes(self.drv.rgb888())

    def touch_point(self):
        """Where on the screen a tap presses the row's widget (the list's
        second row): found once on a Python layer's page of its own, by
        tapping down the page's middle until one takes. A flowing page
        keeps no rects, and every cart layer lays a page out as the Python
        cart's engine does, so a cart's point is that one's."""
        kind = "py_shell" if self.layer == "py_shell" else "py_app"
        got = POINT.get((kind, self.row))
        if got is None:
            ref = Rig(self.tmp / ("touch_" + kind), kind, self.row, self.monkeypatch, self.built)
            sx, sy, sw, sh = ref.ws.app_content_rect()
            took = {"button": lambda s: s["n"] == 1, "list": lambda s: s["c"] == "two",
                    "field": lambda s: s["typing"] == 1}[self.row]
            for y in range(sy + 2, sy + sh, 6):
                ref.tap(sx + sw // 2, y)
                if took(ref.state()):
                    got = POINT[(kind, self.row)] = (sx + sw // 2, y)
                    break
            if kind != "py_shell":
                ref.ws.spine.exit()
            assert got is not None, "no tap down the page's middle takes its %s" % self.row
        return got

    # -- the inputs, each through its driver

    def kbd_key(self, *keys, mic=False):
        self.kbd_bus.frames = [_matrix(*keys, mic=mic)]
        self.frames(1)
        self.kbd_bus.frames = [bytes(5)]
        self.frames(2)

    def ble_key(self, usage):
        self.ble.notify(3, 3, bytes((0, 0, usage, 0, 0, 0, 0, 0)))
        self.frames(1)
        self.ble.notify(3, 3, bytes(8))
        self.frames(2)

    def desk_key(self, code):
        self.drv.key_down(code)
        self.frames(1)
        self.drv.key_up(code)
        self.frames(2)

    def desk_type(self, ch):
        self.drv.type_char(ord(ch))
        self.frames(2)

    def ball(self, steps):
        """The trackball rolled down `steps` notches, each held until the
        surface takes a step."""
        for _ in range(steps):
            self.drv.pan(0, 1)
            self.frames(6)
            self.drv.pan(0, 0)
            self.frames(2)

    def pad(self, name):
        self.drv.press(name)
        self.frames(3)

    def tap(self, x, y):
        self.drv.click(int(x), int(y))
        self.frames(3)

    def mouse_click(self, x, y):
        """A mouse's: the cursor moved there, then its click."""
        self.drv.hover(int(x), int(y))
        self.frames(1)
        self.drv.click(int(x), int(y))
        self.frames(3)

    def drag(self, x, y, dy):
        self.drv.touch(int(x), int(y))
        self.frames(1)
        for i in range(1, 5):
            self.drv.touch_drag(int(x), int(y + dy * i / 4))
            self.frames(1)
        self.drv.touch_up()
        self.frames(3)


ENTER, ESC, DOWN = 0x28, 0x29, 0x51
POINT = {}
USAGE = {"h": 0x0B}


def gesture(rig, col, what):
    """Run `what` (the row's gesture) by input `col`."""
    if what == "choose":
        what = "press"              # the dialog's focused button, its first
    if col == "kbd_text":
        if what == "type":
            rig.kbd_key("\r")
        rig.kbd_key(TYPED if what == "type" else "\r")
    elif col == "kbd_move":
        if what == "type_move":
            rig.kbd_key("s")            # a step past the field: no letter
            rig.kbd_key("\r")
            rig.kbd_key("s")
        elif what == "press":
            rig.kbd_key("\r")
        elif what == "next":
            rig.kbd_key("s")
            rig.kbd_key("\r")
        else:
            for _ in range(3):
                rig.kbd_key("s")
    elif col == "ble_kbd":
        if what == "type":
            rig.ble_key(ENTER)
            rig.ble_key(USAGE[TYPED])
        elif what == "press":
            rig.ble_key(ENTER)
        elif what == "next":
            rig.ble_key(DOWN)
            rig.ble_key(ENTER)
        elif what == "dismiss":
            rig.ble_key(ESC)
        else:
            for _ in range(3):
                rig.ble_key(DOWN)
    elif col == "desk_kbd":
        if what == "type":
            rig.desk_key(13)
            rig.desk_type(TYPED)
        elif what == "press":
            rig.desk_key(13)
        elif what == "next":
            rig.desk_key(mi.KEY_DOWN)
            rig.desk_key(13)
        elif what == "dismiss":
            rig.desk_key(27)
        else:
            for _ in range(3):
                rig.desk_key(mi.KEY_DOWN)
    elif col == "mouse":
        rig.mouse_click(*rig.touch_point())
    elif col == "touch":
        if what == "dismiss":
            sx, sy, sw, sh = rig.ws.app_content_rect()
            rig.tap(sx + sw - 4, sy + sh - 4)
            return
        if what in ("press", "next", "edit"):
            rig.tap(*rig.touch_point())
        else:
            sx, sy, sw, sh = rig.ws.app_content_rect()
            rig.drag(sx + sw // 2, sy + sh // 2 + 30, -60)
    elif col == "trackball":
        if what in ("press", "edit"):
            rig.drv.ball_click()
            rig.frames(3)
        elif what == "next":
            rig.ball(1)
            rig.drv.ball_click()
            rig.frames(3)
        else:
            rig.ball(3)
    elif col == "gamepad":
        if what in ("press", "edit"):
            rig.pad("a")
        elif what == "next":
            rig.pad("down")
            rig.pad("a")
        elif what == "dismiss":
            rig.pad("b")
        else:
            for _ in range(3):
                rig.pad("down")
    elif col == "esc":
        if what == "cancel":
            rig.desk_key(13)
            rig.desk_type(TYPED)
        rig.drv.escape()
        rig.frames(3)
    elif col == "mic":
        if what == "cancel":
            rig.kbd_key("\r")
            rig.desk_type(TYPED)
        rig.kbd_key(mic=True)


def effect(what, before, after):
    """Whether `after` is the gesture's effect on `before`."""
    if what == "type":
        return after["t"] == TYPED
    if what == "type_move":
        return after["t"] == "s"
    if what == "edit":
        return after["typing"] == 1 and before["typing"] == 0
    if what == "cancel":
        return after["t"] == "" and after["typing"] == 0
    if what == "next":
        return after["c"] != before["c"]
    if what == "press":
        return after["n"] == before["n"] + 1
    if what in ("dismiss", "choose"):
        return after["up"] == 0
    if what == "scroll":
        return after["pic"] != before["pic"]
    raise AssertionError(what)


# -- the compiled pages, built once --------------------------------------------------

def _write(root, name, man, files, title="Matrix"):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    full = {"format": "moy-1", "title": title, "id": "test." + name.split(".")[0],
            "canvas": "320x240", "moybyte": {"type": "app", "permissions": []}}
    full.update(man)
    with open(os.path.join(d, "manifest.json"), "w") as f:
        json.dump(full, f)
    for n, text in files.items():
        os.makedirs(os.path.dirname(os.path.join(d, n)), exist_ok=True)
        with open(os.path.join(d, n), "w") as f:
            f.write(text)
    with open(os.path.join(d, "config.json"), "w") as f:
        f.write("{}")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """{row: cart folder} for the compiled pages, or the exception a host
    with no wasi-sdk raised."""
    from tools import wasm_cart
    out = {}
    base = tmp_path_factory.mktemp("matrix_c")
    for row in ROWS:
        src = "src_" + row
        _write(str(base), src, {"runtime": "wasm", "main": "main.wasm", "memory": 2,
                                "extensions": ["moybyte.app"]}, {"src/main.c": C_APP % C[row]})
        dst = str(base / ("wasm_" + row + ".moy"))
        try:
            wasm_cart.build(str(base / src), dst)
            out[row] = dst
        except Exception as exc:  # noqa: BLE001 -- a host with no wasi-sdk
            out[row] = exc
    return out


def _needs_build(built, layer, row):
    if layer != "wasm_app":
        return
    got = built[row]
    if isinstance(got, Exception):
        if os.environ.get("CI"):
            raise got
        pytest.skip("no wasm build here: %s" % got)


@pytest.mark.parametrize("layer,row,col", CELLS, ids=["-".join(c) for c in CELLS])
def test_cell(tmp_path, monkeypatch, built, layer, row, col):
    what = GESTURES[row][col]
    _needs_build(built, layer, row)
    rig = Rig(tmp_path, layer, row, monkeypatch, built)
    try:
        before = rig.state()
        gesture(rig, col, what)
        after = rig.state()
        assert effect(what, before, after), (
            "%s: %s by %s: %r -> %r" % (layer, what, col,
                                        {k: v for k, v in before.items() if k != "pic"},
                                        {k: v for k, v in after.items() if k != "pic"}))
    finally:
        if layer != "py_shell":
            rig.ws.spine.exit()


# -- widget state (phase 8): a field's edit and a popover's size are its own ----------

STACK_PY = """s = ui.state(a="aa", b="bb", up=False)
ui.app("Stack", icon="calc")


def nothing():
    pass


def shut():
    s.up = False


def show(on):
    s.up = on == 1


def focus_on(key):
    ui.focus(key)


ui.action("open", "Open", nothing)
ui.action("shut", "Close", shut)
ui.hook("show", show, takes="arg")
ui.hook("focus_on", focus_on, takes="arg")


def build():
    with ui.page("Stack"):
        ui.field("Name", "a", max=11)
        ui.button("open")
        with ui.popover("pop", w=160, anchor="open", close="shut", shown="up"):
            ui.field("Note", "b", max=11)
"""


class _Stack:
    """A Python app's page whose field a popover with a field of its own
    stacks over; the engine and its records are the one every runtime
    draws through."""

    def __init__(self, tmp_path):
        from test_app_field_typing import _open
        self.ws, self.drv = _open(tmp_path, "Stack", STACK_PY, "python")
        self.tree = self.ws.run.player.tree
        self.eng = self.tree.engine

    def ab(self):
        v = self.eng.s._v
        return v["a"], v["b"]

    def run(self, name, arg):
        """A hook of the app's run as its host runs one, then the frames
        that show it."""
        self.tree.act(name, arg)
        for _ in range(3):
            self.drv.frame(DT)


def test_a_stacked_fields_cancel_gives_each_field_its_own_text(tmp_path):
    """A field edited under a popover whose field takes an edit of its own:
    each field's record keeps the text its edit began from, so the popover's
    cancel gives its field its text, and the page's, focused and edited
    again, cancels to its own."""
    from test_app_field_typing import _edit, _mic, _type
    from runtime import ui_draw
    was = ui_draw.input_kind()
    ui_draw.input_kind("tdeck")
    try:
        st = _Stack(tmp_path)
        st.run("focus_on", "a")
        _edit(st.drv)
        _type(st.drv, "x")
        st.run("show", 1)
        st.run("focus_on", "b")
        _edit(st.drv)
        _type(st.drv, "y")
        assert st.ab() == ("aax", "bby")
        _mic(st.ws, st.drv)
        assert st.ab() == ("aax", "bb")
        st.run("show", 0)
        st.run("focus_on", "a")
        _edit(st.drv)
        _type(st.drv, "z")
        assert st.ab() == ("aaxz", "bb")
        _mic(st.ws, st.drv)
        assert st.ab() == ("aax", "bb")
        assert not st.ws.sysmenu.open, "the page's field had its own edit to cancel"
    finally:
        ui_draw.input_kind(was)


def test_a_popover_first_shows_at_its_settled_box(tmp_path):
    """A popover with no size kept shows on the frame that opens it, at the
    box it rests at: every frame after the one that opens it draws the
    same. The badge banner its open raised is taken down first: its shine
    moves with the clock."""
    from ws_helpers import quiesce
    st = _Stack(tmp_path)
    quiesce(st.ws)
    base = bytes(st.drv.rgb888())
    st.tree.act("show", 1)
    shots = []
    for _ in range(4):
        st.ws.mark_dirty()
        st.drv.frame(DT)
        shots.append(bytes(st.drv.rgb888()))
    assert shots[0] != base, "the frame that opens it shows nothing of it"
    rest = shots[1] == shots[2] == shots[3]
    assert rest, "the popover's box moved after it first showed"
