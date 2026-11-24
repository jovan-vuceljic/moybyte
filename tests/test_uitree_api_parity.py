"""One app says the same things on every front: what the API's parity
closed, held on each front it reaches.

- a toggle's and a slider's when= and off= (a field's already): greyed and
  no stop while the condition fails, gone where off="hide"; Python, Lua and
  a compiled app's rows;
- a scroll's follow= and snap=: Python, Lua and a compiled app's rows;
- a two-way control's when= and off= come as a pair (O01, O02) in Python as
  in Lua.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "uitree_fixtures")]

import test_uitree_lua as L  # noqa: E402

OFFS = '''
import uitree as ui

s = ui.state(ro=False, loud=False, lvl=3)


def lock():
    s.ro = not s.ro


ui.action("lock", "Lock", lock)


def build():
    with ui.page("Offs"):
        ui.button("lock")
        ui.toggle("Loud", "loud", when="!ro", off="grey")
        ui.slider("Level", "lvl", 0, 9, when="!ro", off="hide")
'''


def _python_frames(tmp_path, src, script, probe):
    import uitree_app
    import uitree_c
    import uitree_conf as C
    import uitree_parity as P
    app_py = tmp_path / "app" / "app.py"
    app_py.parent.mkdir()
    app_py.write_text(src)
    mod = C._module(str(app_py))
    cls = uitree_app.app_layer("parity_c", "Parity", mod.build, engine=uitree_c.CEngine)
    seen = {}

    def opened(ws):
        seen["app"] = P.host(ws, cls)
    return P.frames(C.CONFIGS[0], P.Surface(opened, probe=lambda ws: probe(seen["app"].engine)), script)


def test_python_a_toggle_and_a_slider_are_off_while_their_when_fails(tmp_path):
    """Loud and Level take input while unlocked; locked, the toggle greys
    (no stop: down stays on Lock) and the slider goes."""
    def probe(e):
        return "%s %s %s %s" % (e.focus_key, e.s._v["ro"], e.s._v["loud"], e.s._v["lvl"])
    fs = _python_frames(tmp_path, OFFS, ["k:down", "k:a", "k:down", "k:right", "k:up", "k:up", "k:a",
                                         "k:down"], probe)
    assert [f.state for f in fs] == [
        "lock False False 3", "loud False False 3", "loud False True 3", "lvl False True 3",
        "lvl False True 4", "loud False True 4", "lock False True 4", "lock True True 4",
        "lock True True 4"], [f.state for f in fs]
    assert fs[6].buf != fs[7].buf                   # the toggle greys and the slider goes


@pytest.mark.parametrize("call, code", [
    ('ui.toggle("Loud", "loud", when="!ro")', "O01"),
    ('ui.slider("Level", "lvl", 0, 9, off="grey")', "O02"),
    ('ui.field("Name", "name", when="!ro")', "O01"),
])
def test_python_a_controls_when_and_off_come_as_a_pair(call, code, tmp_path):
    import uitree_check
    path = tmp_path / "app.py"
    path.write_text('import uitree as ui\ns = ui.state(ro=False, loud=False, lvl=0, name="")\n'
                    'def build():\n    with ui.page("P"):\n        %s\n' % call)
    got = [(e.code, e.where[1]) for e in uitree_check.check(str(path)).errors]
    assert (code, 5) in got, got


SCROLL = '''
import uitree as ui

s = ui.state(lines=ui.model(key="n", n=0))


def opened():
    s.lines = [dict(n=i) for i in range(40)]


ui.hook("opened", opened)


def build():
    with ui.page("Log"):
        with ui.scroll("log"%s):
            with ui.rows("lines"):
                ui.label("line {.n}")
'''


def test_python_a_scroll_follows_its_foot_and_snaps(tmp_path):
    """follow=True opens the scroll at its foot: its first frame is not the
    one a scroll without it opens on; snap=True lowers beside it."""
    frames = {}
    for i, props in enumerate(("", ", follow=True, snap=True")):
        d = tmp_path / str(i)
        d.mkdir()
        frames[props] = _python_frames(d, SCROLL % props, [], lambda e: e.focus_key)[0].buf
    assert frames[""] != frames[", follow=True, snap=True"]


LUA_OFFS = '''ui.app("%s", { icon = "calc" })
local s = ui.state { ro = false, loud = false, lvl = 3 }
ui.action("lock", "Lock", function() s.ro = not s.ro end)
ui.page("p", function()
  ui.button("lock")
  ui.toggle("loud", { label = "Loud", when = "!ro", off = "grey" })
  ui.slider("lvl", { label = "Level", lo = 0, hi = 9, when = "!ro", off = "hide" })
  ui.scroll("log", { follow = true, snap = true }, function() ui.label("{lvl}") end)
end)
'''


def test_lua_a_toggle_and_a_slider_are_off_while_their_when_fails(tmp_path):
    """The same page on the Lua front: Lock greys the toggle and hides the
    slider, and the scroll's follow= and snap= lower beside them."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    L._cart(carts, "Offs", LUA_OFFS % "Offs")
    ws, drv, frame, open_cart = L._console(carts)
    open_cart(ws, "Offs")
    for _ in range(4):
        frame()
    player = ws.run.player
    assert player.cart_error is None, player.cart_error
    before = bytes(drv.rgb888())
    drv.press("a")
    frame()
    frame()
    assert player.cart_error is None, player.cart_error
    assert bytes(drv.rgb888()) != before, "locking greyed and hid nothing"
    ws.spine.exit_to_caller()


def test_compiled_rows_take_a_controls_when_and_off_and_a_scrolls_follow_and_snap():
    """A compiled app's rows (no check of their own) take the props the
    engine now draws on these kinds."""
    from test_uitree_wasm import Rows, PAGE
    import uitree_c
    kinds = uitree_c._KINDS
    r = Rows()
    try:
        assert r.state("ro", 1, b"") >= 0 and r.state("lvl", 2, b"") >= 0 and r.state("loud", 1, b"") >= 0
        r.build("1 page")
        page = r.node(PAGE, "page", -1)
        tog = r.node(kinds["toggle"], "loud", page)
        sli = r.node(kinds["slider"], "lvl", page)
        scr = r.node(kinds["scroll"], "log", page)
        for node, name, src in ((tog, "bind", "loud"), (tog, "label", "Loud"), (tog, "when", "!ro"),
                                (tog, "off", "grey"), (sli, "bind", "lvl"), (sli, "label", "Level"),
                                (sli, "lo", "0"), (sli, "hi", "9"), (sli, "when", "!ro"), (sli, "off", "hide"),
                                (scr, "follow", "True"), (scr, "snap", "True")):
            assert r.prop(node, name, src) >= 0, (name, r.read("error", cap=400)[1])
    finally:
        r.close()


LUA_KEYS = '''ui.app("%s", { icon = "calc" })
local s = ui.state { n = 0, downed = false }
local function add(k) s.n = s.n + k; pmem(0, s.n) end
ui.action("go", "Go", function() add(100) end)
ui.page("p", function()
  ui.label("{n}")
  ui.canvas("pad", { draw = function(x, y, w, h) rect(x, y, x + w - 1, y + h - 1, 7) end, h = 20,
                     keys = function()
                       if btnp("a") then add(1) return true end
                       if btnp("down") and not s.downed then s.downed = true; add(10) return true end
                       return false
                     end })
  ui.button("go")
end)
'''


def test_lua_a_canvas_takes_the_keys_while_it_holds_focus(tmp_path):
    '''A Lua canvas with keys= is a stop; while it holds focus its keys=
    is handed the frame's keys first, run as a handler, and what it takes
    the page never sees: A (+1), the first down (+10, focus stays), A (+1);
    the second down it leaves, which moves focus to Go, whose A adds 100.'''
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    L._cart(carts, "Keys", LUA_KEYS % "Keys")
    ws, drv, frame, open_cart = L._console(carts)
    open_cart(ws, "Keys")
    for _ in range(4):
        frame()
    player = ws.run.player
    for key in ("a", "down", "a", "down", "a"):
        drv.press(key)
        frame()
        frame()
        assert player.cart_error is None, player.cart_error
    player.lua.flush_pmem()
    assert ws.run.project.pmem.cells[0] == 112, ws.run.project.pmem.cells[0]
    ws.spine.exit_to_caller()


def test_compiled_a_canvas_takes_the_keys_while_it_holds_focus():
    """The Lua test above in C (tests/fixtures/uitree_keys_wasm.moy, its
    `ut_canvas_keys`): the face hands the focused canvas's keys to the
    module's `_uitree_keys` before the frame, and what it takes the page
    never sees: A (+1), the first down (+10), A (+1), the second down moves
    focus to Go, whose A adds 100."""
    import uitree_conf as C
    cart = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "uitree_keys_wasm.moy")
    script = ["f:4"] + [x for k in ("a", "down", "a", "down", "a") for x in ("k:" + k, "f:2")]
    trace, _ = C.run_wasm(None, C.CONFIGS[0], script, cart=cart)
    states = [l for l in trace if l.startswith("state n ")]
    assert [l.split("-> ")[1].split()[0] for l in states] == ["'1'", "'11'", "'12'", "'112'"], trace
    assert [l for l in trace if l.startswith("action go")] == ["action go from button 'go' on 'Keys'"], trace


@pytest.mark.parametrize("kind, name, src, says", [
    ("canvas", "text", "True", "no prop 'text'"),           # a name the spec only designs
    ("rule", "label", "x", "no prop 'label'"),              # a head name on a kind whose head it is not
    ("canvas", "caption", "x", "no prop 'caption'"),
])
def test_compiled_rows_refuse_what_no_engine_draws_on_the_kind(kind, name, src, says):
    """The engine's check at lowering takes a store head name only on the
    kind whose head it is, and refuses a name it does not hold: a compiled app can
    name nothing that silently draws nothing."""
    from test_uitree_wasm import Rows, PAGE, E_CHECK
    import uitree_c
    r = Rows()
    try:
        r.build("1 page")
        page = r.node(PAGE, "page", -1)
        n = r.node(uitree_c._KINDS[kind], "n", page)
        assert r.prop(n, name, src) == E_CHECK
        assert says in r.read("error", cap=400)[1], r.read("error", cap=400)[1]
    finally:
        r.close()


# the shell's own names (the contract's `"owner": "shell"` and `shell_words`): an app is refused
# each, N09, on every front, and the shell's pages keep them
SHELL_PY = ("import uitree as ui\n"
            "s = ui.state(m=ui.model(key=\"k\", k=\"\"), n=0)\n"
            "ui.action(\"open\", \"Open\", lambda row: None, takes=\"row\")\n"
            "def build():\n"
            "    with ui.page(\"P\"):\n"
            "        %s\n")


@pytest.mark.parametrize("node", [
    'ui.slot("run")',
    'ui.tools("bar", lend="bar")',
    'ui.cards("m", look="column")',
])
def test_a_python_cart_is_refused_the_shell_s_own_and_the_shell_keeps_it(node, tmp_path, monkeypatch):
    import uitree_check
    src = SHELL_PY % node
    (tmp_path / "shellish.py").write_text(src)
    got = [(e.code, e.where[1]) for e in uitree_check.check(str(tmp_path / "shellish.py")).errors]
    assert ("N09", 6) in got, got
    monkeypatch.syspath_prepend(str(tmp_path))
    kept = [e.code for e in uitree_check.check("shellish").errors]   # a module of the shell's
    assert "N09" not in kept, kept


def test_a_python_cart_is_refused_a_shell_prop_and_app_field(tmp_path):
    import uitree_check
    (tmp_path / "fill.py").write_text(
        SHELL_PY.replace("def build", "ui.app(\"A\", slots=[\"run\"])\ndef build") %
        'with ui.cards("m"):\n            ui.card("open", label="{.k}", fill="{.k}")')
    got = [(e.code, e.where[1]) for e in uitree_check.check(str(tmp_path / "fill.py")).errors]
    assert ("N09", 4) in got and ("N09", 8) in got, got


@pytest.mark.parametrize("kind, name, src", [
    ("slot", None, None),
    ("lent", None, None),
    ("cards", "look", "column"),
    ("card", "fill", "{.k}"),
    ("tools", "lend", "bar"),
])
def test_compiled_rows_refuse_the_shell_s_own(kind, name, src):
    """A compiled app's store is an app's: the engine refuses a shell kind at
    its node and a shell prop or word at its prop, as the Lua and Python
    fronts do at the call."""
    from test_uitree_wasm import Rows, PAGE, E_CHECK
    import uitree_c
    r = Rows()
    try:
        r.build("1 page")
        page = r.node(PAGE, "page", -1)
        n = r.node(uitree_c._KINDS[kind], "n", page)
        if name is None:
            assert n == E_CHECK
        else:
            assert n >= 0 and r.prop(n, name, src) == E_CHECK
        assert "N09" in r.read("error", cap=400)[1], r.read("error", cap=400)[1]
    finally:
        r.close()


def test_compiled_a_status_line_is_an_app_s():
    """A status line is an app's kind (a page's status strip): a compiled
    app's store takes it, as Python's and Lua's fronts do."""
    from test_uitree_wasm import Rows, PAGE
    import uitree_c
    r = Rows()
    try:
        r.build("1 page")
        page = r.node(PAGE, "page", -1)
        assert r.node(uitree_c._KINDS["status"], "s", page) >= 0, r.read("error", cap=400)[1]
    finally:
        r.close()


def test_a_python_cart_s_status_line_checks_clean(tmp_path):
    import uitree_check
    (tmp_path / "strip.py").write_text(SHELL_PY % 'ui.status("{n} · ready")')
    assert [e.code for e in uitree_check.check(str(tmp_path / "strip.py")).errors] == []
