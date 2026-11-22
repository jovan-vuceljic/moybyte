"""A seg of `look="pictures"` (native/moy_ui's moy_ui_api_pics, drawn by
native/moy_uitree's draw_pics): its values' pictures in tiles at the row's
right, the current one's on the selection plate; one stop whose left and
right step it and wrap, activation taking the next and a tap the tile it
lands on. A picture put with `clear=True` shows the plate where it has its
corner's colour. The Lua front builds it too (its tiles' plates, no
pictures: the Lua layer draws none yet); the Editor's Config pickers are
its other user (tests/test_preliterate_ux.py)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "uitree_fixtures")]

import uitree_parity as P  # noqa: E402


def _live(tmp_path):
    import uitree_c
    import uitree_pictures as F
    from runtime import host_app
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    ws.pointer.visible = False
    F.CANVAS[0] = ws.sys_canvas
    app = P.host(ws, F.layer(uitree_c.CEngine), cart=True)
    drv = host_app.ConsoleDriver(ws)
    _settle(ws, drv)
    return ws, drv, app.engine


def _settle(ws, drv, n=6):
    for _ in range(n):
        ws.mark_dirty()
        drv.frame(1 / 30)


def _px(ws, drv, x, y):
    w = ws.glass_canvas.w
    b = drv.rgb888()
    i = (y * w + x) * 3
    return tuple(b[i:i + 3])


def test_its_keys_wrap_and_activation_takes_the_next(tmp_path):
    ws, drv, e = _live(tmp_path)
    for k in ("right", "right", "right", "left", "a"):
        drv.press(k)
        _settle(ws, drv, 2)
    assert e.s.log == "yzxzx"


def test_a_tap_takes_its_tile_and_the_picture_shows_the_plate_round_it(tmp_path):
    from ws_helpers import picker_tile
    ws, drv, e = _live(tmp_path)
    row = e._ui.box("face")
    tiles = [picker_tile(ws, row, 3, k) for k in range(3)]
    x, y, side, _ = tiles[2]
    drv.click(x + side // 2, y + side // 2)
    _settle(ws, drv)
    assert e.s.face == "z"
    for k, (x, y, side, _) in enumerate(tiles):
        plate = _px(ws, drv, x + side // 8, y + side // 2)       # outside the square: the plate
        square = _px(ws, drv, x + side // 2, y + side // 2)
        assert plate != (0xF8, 0x00, 0xF8), "the clear ground is left out"
        assert square != plate, "tile %d shows its picture" % k
    plates = [_px(ws, drv, x + side // 8, y + side // 2) for x, y, side, _ in tiles]
    assert plates[0] == plates[1] != plates[2], "the current tile is on the selection plate"


LUA_PICS = '''ui.app("Pics", { icon = "image" })
local s = ui.state { face = ui.enum("x", "y", "z", { init = "x" }), log = "" }
ui.labels("FACES", { x = "own:face:x", y = "own:face:y", z = "own:face:z" })
ui.hook("took", function() s.log = s.log .. s.face end)
ui.page("p", function()
  ui.seg("face", { label = "Face", labels = "FACES", look = "pictures", on = "took" })
end)
'''


def test_the_lua_front_builds_it_and_its_keys_step_it(tmp_path):
    import test_uitree_lua as L
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    L._cart(carts, "Pics", LUA_PICS)
    ws, drv, frame, open_cart = L._console(carts)
    open_cart(ws, "Pics")
    for _ in range(4):
        frame()
    before = bytes(drv.rgb888())
    for k in ("right", "right", "right", "a"):
        drv.press(k)
        frame()
        frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    assert bytes(drv.rgb888()) != before, "the selection plate moved to the next tile"
