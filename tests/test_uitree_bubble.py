"""`ui.bubble` and `ui.rows(..., by=)` on the C engine (native/moy_uitree's
draw_bubble and uit_row_body), from both fronts: each row draws the case its
enum field names, a bubble is a stop whose press fires its on= with the row,
and by='s mistakes are the spec's codes (§10.4)."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "uitree_fixtures")]

import test_uitree_lua as L  # noqa: E402

CHAT = '''
import uitree as ui

s = ui.state(msgs=ui.model(key="n", n=0, kind=ui.enum("day", "msg", "failed", init="day"), text="", side="in"),
             picked=0, resent=0)


def details(row):
    s.picked = row.n


def resend(row):
    s.resent = row.n


ui.action("details", "Details", details, takes="row")
ui.action("resend", "Resend", resend, takes="row")


def opened():
    s.msgs = [dict(n=1, kind="day", text="Today", side="in"),
              dict(n=2, kind="msg", text="hello there", side="in"),
              dict(n=3, kind="failed", text="lost one", side="out")]


ui.hook("opened", opened)


def build():
    with ui.page("Chat"):
        ui.rows("msgs", {
            "day": lambda: ui.label("{.text}"),
            "msg": lambda: ui.bubble("{.text}", side="{.side}", head="Ana", status="Sent", on="details"),
            "failed": lambda: ui.bubble("{.text}", side="out", tone="failed", status="Not sent",
                                        on="resend"),
        }, by="kind")
'''


def test_rows_by_kind_draw_each_rows_case_and_a_bubble_fires_its_row(tmp_path):
    """The day row is a label (no stop), the two bubbles the page's stops in
    row order; a press on each fires its own case's action with its row."""
    import uitree_app
    import uitree_c
    import uitree_conf as C
    import uitree_parity as P
    app_py = tmp_path / "chat" / "app.py"
    app_py.parent.mkdir()
    app_py.write_text(CHAT)
    mod = C._module(str(app_py))
    cls = uitree_app.app_layer("chat_c", "Chat", mod.build, engine=uitree_c.CEngine)
    seen = {}

    def opened(ws):
        seen["app"] = P.host(ws, cls)

    def probe(ws):
        e = seen["app"].engine
        return "%s %s %s" % (e.focus_key, e.s._v["picked"], e.s._v["resent"])
    fs = P.frames(C.CONFIGS[0], P.Surface(opened, probe=probe), ["k:a", "k:down", "k:a"])
    assert [f.state for f in fs] == ["2/bubble#0 0 0", "2/bubble#0 2 0", "3/bubble#0 2 0",
                                     "3/bubble#0 2 3"], [f.state for f in fs]


BY = ('import uitree as ui\n'
      's = ui.state(m=ui.model(key="n", n=0, kind=ui.enum("a", "b", init="a")))\n'
      'def build():\n    with ui.page("P"):\n')


@pytest.mark.parametrize("code,call", [
    ("T03", 'ui.rows("m", {"a": lambda: ui.label("x")}, by="n")'),
    ("T02", 'ui.rows("m", {"a": lambda: ui.label("x"), "b": lambda: ui.label("y"), "c": lambda: ui.label("z")}, by="kind")'),
    ("T04", 'ui.rows("m", {"a": lambda: ui.label("x")}, by="kind")'),
    ("N01", 'ui.rows("m", {}, by="kind")'),
    ("N01", 'ui.rows("m", {"a": lambda: ui.label("x")})'),
])
def test_a_bad_by_is_the_specs_code_at_its_line(code, call, tmp_path):
    import uitree_check
    path = tmp_path / "by.py"
    path.write_text(BY + "        " + call + "\n")
    r = uitree_check.check(str(path))
    assert (code, 5) in [(e.code, e.where[1]) for e in r.errors], r.text()


LUA_CHAT = '''ui.app("Chat", { icon = "bubble" })
local s = ui.state { msgs = ui.model { key = "n", n = 0, kind = ui.enum("day", "msg", { init = "day" }), text = "" }, picked = 0 }
ui.action("details", "Details", function(row) s.picked = row.n end, { takes = "row" })
ui.hook("opened", function() s.msgs:set({ { n = 1, kind = "day", text = "Today" }, { n = 2, kind = "msg", text = "hi" } }) end)
ui.page("p", function()
  ui.label("{picked}")
  ui.rows("msgs", { by = "kind" }, {
    day = function() ui.label("{.text}") end,
    msg = function() ui.bubble("{.text}", { side = "out", signal = 3, max = 1, lines = 2, on = "details" }) end,
  })
end)
'''


def test_a_lua_app_draws_rows_by_kind_and_a_bubble_on_the_c_engine(tmp_path):
    """The same page from Lua, lowered into the C engine: it draws, and the
    bubble, the page's one stop, fires its action with its row."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    L._cart(carts, "Chat", LUA_CHAT)
    ws, drv, frame, open_cart = L._console(carts)
    open_cart(ws, "Chat")
    for _ in range(4):
        frame()
    before = bytes(drv.rgb888())
    drv.press("a")
    for _ in range(3):
        frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    assert bytes(drv.rgb888()) != before        # the label reads picked = 2


def test_an_info_and_a_link_draw_their_signal_tag_and_tone_on_the_c_engine(tmp_path):
    """An info's and a link's signal=, tag= and tone= lower into the C
    engine, and each moves the pixels of the plain row."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    head = ('ui.app("%s", { icon = "calc" })\nlocal s = ui.state { bars = 3 }\n'
            'ui.action("go", "Go", function() end)\nui.page("p", function()\n%s\nend)\n')
    pages = {
        "Plain": '  ui.info("Signal", { value = "ok" })\n  ui.link("go", { value = "" })',
        "Signal": '  ui.info("Signal", { value = "ok", signal = "{bars}" })\n  ui.link("go", { value = "" })',
        "Toned": '  ui.info("Signal", { value = "ok", tone = "danger" })\n  ui.link("go", { value = "" })',
        "Tagged": '  ui.info("Signal", { value = "ok" })\n  ui.link("go", { value = "", tag = "Public" })',
    }
    for name, page in pages.items():
        L._cart(carts, name, head % (name, page))
    ws, drv, frame, open_cart = L._console(carts)
    shots = {}
    for name in pages:
        open_cart(ws, name)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, (name, ws.run.player.cart_error)
        shots[name] = bytes(drv.rgb888())
        ws.spine.exit_to_caller()
    assert all(shots[n] != shots["Plain"] for n in ("Signal", "Toned", "Tagged"))
