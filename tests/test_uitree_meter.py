"""A slider of `look="blocks"` (a meter: native/moy_ui's steps drawn across
the whole row, native/moy_uitree's NL_BLOCKS) from the Lua front: its
blocks span the row and left and right step it while it is focused.
Music's volume is the Python front's (`tests/test_music_app.py` taps it)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "uitree_fixtures")]

import test_uitree_lua as L  # noqa: E402

LUA_METER = '''ui.app("Meter", { icon = "volume" })
local s = ui.state { vol = 3 }
ui.page("p", function()
  ui.slider("vol", { label = "", lo = 0, hi = 10, look = "blocks" })
end)
'''


def test_a_meter_steps_by_its_keys_and_its_blocks_span_the_row(tmp_path):
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    L._cart(carts, "Meter", LUA_METER)
    ws, drv, frame, open_cart = L._console(carts)
    open_cart(ws, "Meter")
    for _ in range(4):
        frame()
    before = bytes(drv.rgb888())
    for _ in range(2):
        drv.press("right")
        frame()
    frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    after = bytes(drv.rgb888())
    w = ws.glass_canvas.w
    moved = [i // 3 % w for i in range(0, len(before), 3) if before[i:i + 3] != after[i:i + 3]]
    assert moved, "the keys lit no block"
    assert max(moved) - min(moved) >= w // 12, "a block is a tenth of the row, not a step's 6 px"
