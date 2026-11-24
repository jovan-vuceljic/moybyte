"""`ui.hints`: a model's rows as keycap hints along a row (§7.2), no stop; a
press on one fires on= with its row; the rows tail= holds stand at the row's
end, and where the rest run into them the rows drop= holds go first."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_DESK = dict(sys_size=(1024, 600), font_scale=1, windowed=True, panel_diagonal_in=7.0)

_LUA = """
ui.app("Lua Hints", { icon = "games" })
local s = ui.state { hints = ui.model { key = "id", id = "", keys = "", words = "", tail = false,
                                      spare = false } }
ui.hook("opened", function()
  local rows = { { id = "play", keys = "confirm", words = "Play", tail = false, spare = false },
                 { id = "copy", keys = "Y", words = "%(copy)s", tail = false, spare = true },
                 { id = "del", keys = "X", words = "Delete", tail = false, spare = false },
                 { id = "tabs", keys = "tabs", words = "Tabs", tail = true, spare = false } }
  local keep = {}
  for _, r in ipairs(rows) do
    if r.id ~= "%(without)s" then keep[#keep + 1] = r end
  end
  s.hints:set(keep)
end)
ui.action("tap", "Do", function(r) moybyte.log(6, "tapped " .. r.id) end, { takes = "row" })
ui.page("hints", function()
  ui.hints("hints", { keys = "{.keys}", label = "{.words}", tail = ".tail", drop = ".spare", on = "tap" })
end, { title = "Lua Hints" })
"""


def _lua_hints(tmp_path, copy="Duplicate", without=""):
    """A desk workstation with a Lua app whose page is one hints row (Play,
    `copy`, which may go, and Delete from its start, Tabs at its end; the
    row `without` names left out), open and drawn: its driver and a frame
    function answering the glass's bytes."""
    from runtime import host_app
    from ws_helpers import open_cart
    carts = tmp_path / "carts"
    cart = carts / "lua_hints.moy"
    cart.mkdir(parents=True)
    (cart / "manifest.json").write_text(json.dumps({
        "format": "moy-1", "title": "Lua Hints", "runtime": "lua", "main": "main.lua",
        "extensions": ["moybyte.uitree"],
        "moybyte": {"type": "app", "permissions": []}}))
    (cart / "main.lua").write_text(_LUA % dict(copy=copy, without=without))
    ws = host_app.build_workstation(str(carts), **_DESK)
    ws.pointer.visible = False
    drv = host_app.ConsoleDriver(ws)
    drv.frame(1 / 30)
    open_cart(ws, "Lua Hints")

    def frame():
        ws.mark_dirty()
        drv.frame(1 / 30)
        return bytes(ws.wm.root_canvas._buf)
    for _ in range(20):
        frame()
    return ws, drv, frame


def _row_y(ws):
    """The glass row through the hints: the one under the window's title bar
    that the most pixels apart from its ground are on."""
    return max(range(170, 260), key=lambda y: len(_inked(ws, y)))


def _inked(ws, y):
    """The x of every pixel on row `y` across the app's window (the desk's
    first, at 405..814) that is not its ground (the row's commonest colour):
    where the hints drew."""
    cv = ws.wm.root_canvas
    row = cv._buf[2 * y * cv.w:2 * (y + 1) * cv.w]
    px = [row[2 * x] | row[2 * x + 1] << 8 for x in range(cv.w)]
    span = px[412:808]
    ground = max(set(span), key=span.count)
    return [x for x in range(412, 808) if px[x] != ground]


def test_a_lua_hints_row_stands_its_end_rows_at_its_end_and_a_press_fires_its_row(tmp_path):
    from runtime.host import moy_log
    ws, drv, frame = _lua_hints(tmp_path)
    frame()
    y = _row_y(ws)
    xs = _inked(ws, y)
    assert xs, "the hints drew nothing"
    left, right = xs[0], xs[-1]
    assert right - left > 300, "Tabs stands at the row's end, apart from Play"
    drv.press("down")           # a key: the hints stay under the taps (touch alone has none)
    frame()
    seq = moy_log.next()
    for x, want in ((left + 10, "tapped play"), (right - 10, "tapped tabs")):
        drv.click(x, y)
        for _ in range(3):
            frame()
        got = [r[4] for r in moy_log.read(seq, 400) if "tapped " in r[4]]
        assert got and got[-1].endswith(want), (x, got)


def test_a_lua_hints_row_drops_its_drop_row_first_and_keeps_the_rest_in_order(tmp_path):
    """A drop= row too long for the room left of Tabs goes, Delete after it
    staying: the row draws as the one that never had it."""
    ws, _drv, frame = _lua_hints(tmp_path / "short")
    short = frame()
    ws2, _drv2, frame2 = _lua_hints(tmp_path / "long", copy="Duplicate " * 40)
    long_ = frame2()
    ws3, _drv3, frame3 = _lua_hints(tmp_path / "none", without="copy")
    none = frame3()
    y = _row_y(ws2)
    assert _inked(ws, y) != _inked(ws2, y), "the fitting Duplicate drew"
    assert _inked(ws2, y) == _inked(ws3, y), "Play, Delete and Tabs, as with no Duplicate"
    xs = _inked(ws2, y)
    assert xs and xs[-1] - xs[0] > 300, "Play and Tabs both drawn"
    assert short != long_ and none
