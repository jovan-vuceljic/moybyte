"""What Moy Mesh's ports draw on the C engine, from both fronts: a model's
enum field mapped through a table of its values, rows check=, a field's
when=, off= and grow=, a popover's wash=, a foot of rows and fields, an
empty with a control under it, and a role key on the focused row."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "uitree_fixtures")]

import test_uitree_lua as L  # noqa: E402

PICKS = '''
import uitree as ui

s = ui.state(regions=ui.model(key="i", i="", kind=ui.enum("near", "far", init="near")),
             region="EU", draft="", ro=False, open=False, asked=0)
ui.labels("KIND", {"near": "Near", "far": "Far"})


def pick(row):
    s.region = row.i


def lock():
    s.ro = not s.ro


def ask():
    s.asked = s.asked + 1


ui.action("pick", "Choose", pick, takes="row")
ui.action("lock", "Lock", lock)
ui.action("ask", "Ask", ask)


def opened():
    s.regions = [dict(i="EU", kind="near"), dict(i="US", kind="far")]


ui.hook("opened", opened)


def build():
    with ui.page("Picks"):
        with ui.rows("regions", current="region", check=True):
            ui.link("pick", label="{.i}", value="{.kind|map KIND}")
        ui.button("lock")
        with ui.empty("Nothing here", lines=["{asked}"]):
            ui.button("ask")
        with ui.foot():
            with ui.row("write"):
                ui.field("", "draft", when="!ro", off="grey", grow=True)
        with ui.popover("more", shown="open", wash="view"):
            ui.label("more")
'''


def test_the_python_front_draws_picks_a_greyed_field_and_an_empty_with_a_button(tmp_path):
    """The rows are picks (the current one checked), Lock greys the foot's
    field, and the empty's button is a stop under it that fires."""
    import uitree_app
    import uitree_c
    import uitree_conf as C
    import uitree_parity as P
    app_py = tmp_path / "picks" / "app.py"
    app_py.parent.mkdir()
    app_py.write_text(PICKS)
    mod = C._module(str(app_py))
    cls = uitree_app.app_layer("picks_c", "Picks", mod.build, engine=uitree_c.CEngine)
    seen = {}

    def opened(ws):
        seen["app"] = P.host(ws, cls)

    def probe(ws):
        e = seen["app"].engine
        return "%s %s %s %s" % (e.focus_key, e.s._v["region"], e.s._v["ro"], e.s._v["asked"])
    script = ["k:down", "k:a", "k:down", "k:a", "k:down", "k:a"]
    fs = P.frames(C.CONFIGS[0], P.Surface(opened, probe=probe), script)
    assert [f.state for f in fs] == [
        "EU/pick EU False 0", "US/pick EU False 0", "US/pick US False 0", "lock US False 0",
        "lock US True 0", "ask US True 0", "ask US True 1"], [f.state for f in fs]
    assert fs[3].buf != fs[4].buf                   # the field greys


LUA_PICKS = '''ui.app("Picks", { icon = "calc" })
local STATE = { "sending", "sent", { init = "sent" } }
local s = ui.state {
  msgs = ui.model { key = "n", n = 0, text = "", state = ui.opt(ui.enum(table.unpack(STATE))) },
  regions = ui.model { key = "i", i = "" }, region = "EU", draft = "", ro = false, picked = 0,
}
ui.labels("STATUS", { sending = "Sending", sent = "Sent" })
ui.action("pick", "Choose", function(row) s.region = row.i end, { takes = "row" })
ui.action("lock", "Lock", function() s.ro = not s.ro end)
ui.action("details", "Details", function(row) s.picked = row.n end, { takes = "row", keys = { "role:more" } })
ui.hook("opened", function()
  s.regions:set({ { i = "EU" }, { i = "US" } })
  s.msgs:set({ { n = 1, text = "hi", state = "sending" }, { n = 2, text = "yo" } })
end)
ui.page("p", function()
  ui.label("{picked}")
  ui.rows("regions", { current = "region", check = %s }, function() ui.link("pick", { label = "{.i}", value = "" }) end)
  ui.rows("msgs", function() ui.bubble("{.text}", { status = "{.state|map STATUS}", on = "details" }) end)
  ui.button("lock")
  ui.foot(function()
    ui.row("write", function() ui.field("draft", { label = "", grow = true, when = "!ro", off = "grey" }) end)
  end)
  ui.popover("more", { shown = "ro", wash = "view" }, function() ui.label("more") end)
end)
'''


def _lua(tmp_path, check):
    from runtime import host_app
    carts = str(tmp_path / ("carts_%s" % check))
    host_app.moy_carts.ensure_dirs(carts)
    L._cart(carts, "Picks", LUA_PICKS % check)
    ws, drv, frame, open_cart = L._console(carts)
    open_cart(ws, "Picks")
    for _ in range(4):
        frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    return ws, drv, frame


def test_the_lua_front_draws_the_same_props_and_a_role_key_takes_the_focused_row(tmp_path):
    """check= draws the current pick's check, a model's optional enum field maps
    through a table of its values alone, and the role key's row action takes
    the focused bubble's row."""
    ws, drv, frame = _lua(tmp_path, "true")
    checked = bytes(drv.rgb888())
    for _ in range(2):
        drv.press("down")
        frame()
    drv.type_char(ord("m"))            # role:more on the first bubble
    for _ in range(3):
        frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    assert bytes(drv.rgb888()) != checked           # the label reads picked = 1
    ws.spine.exit_to_caller()
    _ws, drv2, _frame = _lua(tmp_path, "false")
    assert bytes(drv2.rgb888()) != checked


def test_a_table_that_misses_an_enum_fields_value_is_t04(tmp_path):
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    L._cart(carts, "Picks", (LUA_PICKS % "true").replace('sent = "Sent" }', '}'))
    ws, drv, frame, open_cart = L._console(carts)
    open_cart(ws, "Picks")
    for _ in range(4):
        frame()
    err = ws.run.player.cart_error
    assert err and "error[T04]" in err, err


def test_a_popover_washes_what_its_wash_names(tmp_path):
    """wash="page" washes the page under the popover, wash="none" leaves it."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    for w in ("page", "none"):
        L._cart(carts, "W" + w, ('ui.app("W%s", { icon = "calc" })\nlocal s = ui.state { open = true }\n'
                                 'ui.page("p", function()\n  ui.label("under it")\n'
                                 '  ui.popover("more", { shown = "open", wash = "%s" }, function() ui.label("x") end)\n'
                                 'end)\n') % (w, w))
    ws, drv, frame, open_cart = L._console(carts)
    shots = {}
    for w in ("page", "none"):
        open_cart(ws, "W" + w)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, ws.run.player.cart_error
        shots[w] = bytes(drv.rgb888())
        ws.spine.exit_to_caller()
    assert shots["page"] != shots["none"]
