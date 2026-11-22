"""`ui.month` on the C engine (native/moy_uitree's draw_month) from the Lua
front: the month its year= and month= ints name, redrawn where they move.
The Python front's month is the clock popover's (`tests/test_bar_popovers.py`
pages it by its keys and its chevrons)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "uitree_fixtures")]

import test_uitree_lua as L  # noqa: E402

LUA_CAL = '''ui.app("Cal", { icon = "clock" })
local s = ui.state { y = 2026, m = 2, today = 3 }
ui.action("next", "Next", function() s.m = s.m + 1; s.today = 0 end)
ui.page("p", function()
  ui.button("next")
  ui.month({ year = "{y}", month = "{m}", today = "{today}", next = "next" })
end)
'''


def test_a_lua_app_draws_a_month_on_the_c_engine(tmp_path):
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    L._cart(carts, "Cal", LUA_CAL)
    ws, drv, frame, open_cart = L._console(carts)
    open_cart(ws, "Cal")
    for _ in range(4):
        frame()
    before = bytes(drv.rgb888())
    drv.press("a")
    for _ in range(3):
        frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    assert bytes(drv.rgb888()) != before        # March, no day marked
