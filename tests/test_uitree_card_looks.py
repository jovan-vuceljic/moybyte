"""`ui.cards(look="shelf")` and `look="icons"` on the C engine
(native/moy_uitree's `draw_cells`, the toolkit's `moy_ui_api_cells_*`): a
grid of cards the engine lays out and moves, the arrows stepping the
current card across it, Enter and a tap on a card firing its action, cur=
following the current card. A Lua app's shelf and icons, the same engine's,
step and play."""

import json

import pytest

_LUA_CELLS = """
ui.app("Lua Cells", { icon = "games" })
local s = ui.state { games = ui.model { key = "name", name = "", sub = "" },
                     pick = ui.row_of("games") }
ui.hook("opened", function()
  local rows = {}
  for i = 0, 11 do rows[#rows + 1] = { name = "game " .. i, sub = "Game\\tBuilt in" } end
  s.games:set(rows)
end)
ui.action("play", "Play", function(row) moybyte.log(6, "played " .. row.name) end, { takes = "row" })
ui.page("cells", function()
  ui.cards("games", { look = "%s", cur = "pick" }, function()
    ui.card("play", { label = "{.name}", sub = "{.sub}" })
  end)
end, { title = "Lua Cells" })
"""


def _lua_cells(tmp_path, look):
    """A workstation with a Lua app whose page is a `look` grid of twelve
    cards, open and drawn: its driver and a frame function answering the
    canvas's bytes."""
    from runtime import host_app
    from ws_helpers import open_cart
    carts = tmp_path / "carts"
    cart = carts / "lua_cells.moy"
    cart.mkdir(parents=True)
    (cart / "manifest.json").write_text(json.dumps({
        "format": "moy-1", "title": "Lua Cells", "runtime": "lua", "main": "main.lua",
        "extensions": ["moybyte.ui", "moybyte.uitree"],
        "moybyte": {"type": "app", "permissions": []}}))
    (cart / "main.lua").write_text(_LUA_CELLS % look)
    ws = host_app.build_workstation(str(carts))
    ws.pointer.visible = False
    drv = host_app.ConsoleDriver(ws)
    drv.frame(1 / 30)
    open_cart(ws, "Lua Cells")

    def frame():
        ws.mark_dirty()
        drv.frame(1 / 30)
        return bytes(ws.sys_canvas._buf)
    for _ in range(20):
        frame()
    return ws, drv, frame


def _played(seq):
    from runtime.host import moy_log
    return [r[4] for r in moy_log.read(seq, 400) if "played " in r[4]]


@pytest.mark.parametrize("look,key", [("shelf", "down"), ("icons", "right")])
def test_a_lua_grid_steps_its_current_card_and_enter_plays_it(tmp_path, look, key):
    """The Lua front takes the engine's shelf and icons as they are: the
    arrow along a column of the shelf (along a row of the icons) moves the
    current card, which the frame shows, and Enter plays it."""
    from runtime.host import moy_log
    ws, drv, frame = _lua_cells(tmp_path, look)
    rest = frame()
    seq = moy_log.next()
    drv.press(key)
    moved = frame()
    assert moved != rest, "the step moved the focus mark"
    drv.press("a")
    for _ in range(3):
        frame()
    played = _played(seq)
    assert played and played[-1].endswith("played game 1"), played


@pytest.mark.parametrize("look", ["shelf", "icons"])
def test_a_tap_on_a_lua_grids_card_plays_it(tmp_path, look):
    """A tap on a card (its press and its release on it) makes it current
    and plays it: down the page's left edge, the first card a tap lands on
    is the first card."""
    from runtime.host import moy_log
    ws, drv, frame = _lua_cells(tmp_path, look)
    seq = moy_log.next()
    for y in range(30, ws.sys_canvas.h, 8):
        drv.click(40, y)
        for _ in range(3):
            frame()
        if _played(seq):
            break
    played = _played(seq)
    assert played and played[0].endswith("played game 0"), played
