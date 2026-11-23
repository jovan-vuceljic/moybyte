"""A page that shrinks under its scroll draws clamped in the frame it shrinks
(`moy_ui_api_page_again`, run from `uit_frame` on every front): the frame
after the change is the frame the page settles on, and the typed key the
first pass took lands once.

The page: rows, a field, and rows after it shown while the field is empty.
Scrolled down to the last row and back up to the field, a typed key fills
the field, which hides the rows after it: the page's rows end above the
scroll the pass drew at, and the pass runs again, clamped, with the key
already taken."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "uitree_fixtures")]

import test_uitree_lua as L  # noqa: E402

N = 12
DT = 1 / 30

PY = '''
import uitree as ui

s = ui.state(tops=ui.model(key="i", i=""), items=ui.model(key="i", i=""), draft="", picked="")


def pick(row):
    s.picked = row.i


ui.action("pick", "Choose", pick, takes="row")


def opened():
    s.tops = [dict(i="t%d" % n) for n in range(N)]
    s.items = [dict(i="b%d" % n) for n in range(N)]


ui.hook("opened", opened)


def build():
    with ui.page("Shrink"):
        with ui.rows("tops"):
            ui.link("pick", label="{.i}", value="")
        ui.field("Note", "draft")
        with ui.rows("items", shown="!draft"):
            ui.link("pick", label="{.i}", value="")
'''.replace("range(N)", "range(%d)" % N)

LUA = '''ui.app("Shrink", { icon = "calc" })
local s = ui.state { tops = ui.model { key = "i", i = "" }, items = ui.model { key = "i", i = "" },
                     draft = "", picked = "" }
ui.action("pick", "Choose", function(row) s.picked = row.i end, { takes = "row" })
ui.hook("opened", function()
  local t, b = {}, {}
  for n = 0, %d do t[#t + 1] = { i = "t" .. n }; b[#b + 1] = { i = "b" .. n } end
  s.tops:set(t)
  s.items:set(b)
end)
ui.page("Shrink", function()
  ui.rows("tops", function() ui.link("pick", { label = "{.i}", value = "" }) end)
  ui.field("draft", { label = "Note" })
  ui.rows("items", { shown = "!draft" }, function() ui.link("pick", { label = "{.i}", value = "" }) end)
end)
''' % (N - 1)


def _walk(press, frame):
    """Down to the last row, up to the field."""
    for key, n in (("down", 2 * N), ("up", N)):
        for _ in range(n):
            press(key)
            frame()
            frame()


def _settled(ws, frame):
    prev = None
    for _ in range(40):
        frame()
        cur = bytes(ws.glass_canvas._buf)
        if cur == prev:
            return cur
        prev = cur
    return prev


def test_the_python_front_draws_the_shrunk_page_clamped_and_takes_the_key_once():
    import uitree_app
    import uitree_c
    import uitree_conf as C
    import uitree_parity as P
    from runtime.host_api import ConsoleDriver
    g = P._goldens()
    root = tempfile.mkdtemp(prefix="page_again_")
    app_py = os.path.join(root, "shrink", "app.py")
    os.makedirs(os.path.dirname(app_py))
    with open(app_py, "w") as fh:
        fh.write(PY)
    mod = C._module(app_py)
    cls = uitree_app.app_layer("shrink_c", "Shrink", mod.build, engine=uitree_c.CEngine)
    ws = g._build(g.CONFIGS[C.CONFIGS[0]], os.path.join(root, "carts"))
    try:
        app = P.host(ws, cls)
        drv = ConsoleDriver(ws)

        def frame():
            g._quiesce(ws)
            ws.mark_dirty()
            drv.frame(DT)
        _settled(ws, frame)
        _walk(drv.press, frame)
        _settled(ws, frame)
        e = app.engine
        assert e.focus_key == "draft", e.focus_key
        drv.type_char(ord("x"))
        frame()
        typed = bytes(ws.glass_canvas._buf)
        assert e.s._v["draft"] == "x", e.s._v["draft"]
        assert _settled(ws, frame) == typed, "the frame the page shrank in drew it at the old scroll"
        assert e.s._v["draft"] == "x", e.s._v["draft"]
    finally:
        ws.home.go_home()
        from runtime import scheduler
        scheduler.SCHED.reset()
        g._ui().theme_uninstall()


def test_the_lua_front_draws_the_shrunk_page_clamped_and_takes_the_key_once(tmp_path):
    from runtime import host_app
    from runtime.host import moy_log
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    L._cart(carts, "Shrink", LUA)
    ws, drv, frame, open_cart = L._console(carts)
    seq = moy_log.next()
    open_cart(ws, "Shrink")
    _settled(ws, frame)
    _walk(drv.press, frame)
    _settled(ws, frame)
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    drv.type_char(ord("x"))
    frame()
    typed = bytes(ws.glass_canvas._buf)
    assert _settled(ws, frame) == typed, "the frame the page shrank in drew it at the old scroll"
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    lines = [r[4].split("[trace] ", 1)[1] for r in moy_log.read(seq, 4000) if "[trace] " in r[4]]
    drafts = [" ".join(l.split()[1:]) for l in lines if l.split()[1:3] == ["state", "draft"]]
    assert len(drafts) == 1 and drafts[0].split("-> ")[1].split()[0] == "'x'", lines
