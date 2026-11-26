"""The UI tree API's Lua layer (runtime/run/uitree.lua) on the host console.

- An app written in it opens, paints, takes input and closes beside today's.
- Moy Mesh's thread and Radio ports draw their recorded frames through one
  input script, on the handheld and in a desk window
  (tests/uitree_lua_shots.py, which also draws them beside the hand-written
  pages they port).
- The checker (tools/uitree_lua_check.py): one failing case per error code a
  Lua app can raise, each reported at its file and line.
"""
import json
import os
import shutil
import sys
import tempfile
import zlib

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE, os.path.join(ROOT, "tools")]

import uitree_lua_shots as shots  # noqa: E402
import uitree_lua_check as checker  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "uitree_lua")
MESH_GOLDENS = os.path.join(HERE, "shell_goldens", "uitree_mesh.json")


def _cart(root, name, main, extra=None):
    d = os.path.join(root, name + ".moy")
    os.makedirs(d)
    files = dict(extra or {})
    files["main.lua"] = main
    man = {"format": "moy-1", "title": name, "runtime": "lua", "main": "main.lua",
           "sources": [f for f in files if f not in ("fire.lua",)],
           "extensions": ["moybyte.uitree"], "moybyte": {"type": "app", "permissions": []}}
    man["sources"].sort(key=lambda f: f == "main.lua")
    for f, text in files.items():
        with open(os.path.join(d, f), "w") as fh:
            fh.write(text)
    with open(os.path.join(d, "manifest.json"), "w") as fh:
        json.dump(man, fh)
    return d


def _console(carts, size="320"):
    from runtime import host_app
    from ws_helpers import open_cart, quiesce
    ws = host_app.build_workstation(carts, **shots.SIZES[size])
    ws.look.set_theme("moy", persist=False, variant="dark")
    ws.bar_layer.clock_text = lambda: "10:30"   # (runs compared are made minutes apart)
    drv = host_app.ConsoleDriver(ws)

    def frame():
        quiesce(ws)
        ws.mark_dirty()
        drv.frame(shots.DT)
    return ws, drv, frame, open_cart


def test_an_app_opens_paints_takes_input_and_closes(tmp_path):
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    shutil.copytree(os.path.join(FIX, "counter.moy"), os.path.join(carts, "counter.moy"))
    ws, drv, frame, open_cart = _console(carts)
    open_cart(ws, "Tree Counter")
    for _ in range(4):
        frame()
    player = ws.run.player
    assert player is not None and player.cart_error is None
    before = bytes(drv.rgb888())
    for _ in range(3):
        drv.press("a")
        frame()
        frame()
    assert player.cart_error is None
    after = bytes(drv.rgb888())
    assert before != after, "three presses of the focused Add one changed nothing on glass"
    ws.spine.exit_to_caller()
    assert player.lua is None, "the app's Lua state outlived its run"


def _form_run(carts):
    """Tree Form (tests/fixtures/uitree_lua/form.moy) opened and pressed three
    times: its frames before and after, and its pmem cell 0."""
    from runtime import host_app
    host_app.moy_carts.ensure_dirs(carts)
    shutil.copytree(os.path.join(FIX, "form.moy"), os.path.join(carts, "form.moy"))
    ws, drv, frame, open_cart = _console(carts)
    open_cart(ws, "Tree Form")
    for _ in range(4):
        frame()
    player = ws.run.player
    before = bytes(drv.rgb888())
    for _ in range(3):
        drv.press("a")
        frame()
        frame()
    assert player.cart_error is None, player.cart_error
    player.lua.flush_pmem()
    cells = ws.run.project.pmem.cells[0]
    after = bytes(drv.rgb888())
    ws.spine.exit_to_caller()
    return before, after, cells


def test_a_board_runs_the_frozen_layer_as_the_host_runs_the_files(tmp_path, monkeypatch):
    """A board reads the layer from uitree_lua (tools/uitree_lua_freeze.py):
    each text keeps its file's lines, deflated (the browser's as text), and
    Tree Form draws the same frames and keeps the same count on either as on
    the files."""
    import lua_ext
    import uitree_lua_freeze as freeze
    for name in freeze.FILES:
        with open(os.path.join(freeze.RUN, name)) as f:
            src = f.read()
        assert freeze.strip(src).count("\n") == src.count("\n"), name
    files = _form_run(str(tmp_path / "a"))
    assert files[0] != files[1] and files[2] == 3, files[2]
    mods = tmp_path / "mods"
    mods.mkdir()
    freeze.main(["", str(mods)])
    monkeypatch.syspath_prepend(str(mods))
    monkeypatch.setattr(lua_ext, "_uitree_src", {})
    monkeypatch.delitem(sys.modules, "uitree_lua", raising=False)
    try:
        with open(os.path.join(freeze.RUN, "uitree.lua")) as f:
            assert zlib.decompress(lua_ext.uitree_source(), -freeze.WBITS) == freeze.strip(f.read()).encode()
        assert _form_run(str(tmp_path / "b")) == files
    finally:
        sys.modules.pop("uitree_lua", None)
    text = tmp_path / "text"
    text.mkdir()
    freeze.main(["", str(text), "--text"])
    monkeypatch.syspath_prepend(str(text))
    monkeypatch.setattr(lua_ext, "_uitree_src", {})
    try:
        with open(os.path.join(freeze.RUN, "uitree.lua")) as f:
            assert lua_ext.uitree_source() == freeze.strip(f.read())
        assert _form_run(str(tmp_path / "c")) == files
    finally:
        sys.modules.pop("uitree_lua", None)


def test_a_deflated_chunk_has_one_window_on_every_tier():
    """The window the freeze deflates in is the ring a board's moycore
    inflates through and the widest the host's binding takes."""
    import re
    import uitree_lua_freeze as freeze
    from runtime import lua_binding
    with open(os.path.join(ROOT, "native", "moycore", "modmoycore.c")) as f:
        ring = int(re.search(r"#define MOYCORE_Z_WINDOW (\d+)", f.read()).group(1))
    assert ring == 1 << freeze.WBITS == 1 << lua_binding.Z_WBITS


@pytest.mark.parametrize("size", sorted(shots.SIZES))
@pytest.mark.parametrize("screen", sorted(shots.SCREENS))
def test_the_mesh_screens_draw_their_recorded_frames(screen, size, request):
    """Each named shot of a screen's script, pinned by its hash
    (tests/shell_goldens/uitree_mesh.json). Re-baseline as the shell goldens
    are, `MOYBYTE_UPDATE_GOLDENS=1` or `--update-goldens`, once
    `tests/uitree_lua_shots.py OUT SCREEN` shows what moved."""
    import hashlib
    import pixel_goldens
    cart, extra, script = shots.SCREENS[screen]
    (w, h), got_shots, errors, _logs = shots.play(cart, extra, script, size)
    assert errors == []
    update = os.environ.get("MOYBYTE_UPDATE_GOLDENS") or request.config.getoption("--update-goldens", default=False)
    table = {}
    if os.path.isfile(MESH_GOLDENS):
        with open(MESH_GOLDENS) as f:
            table = json.load(f)
    got = {"%s_%s_%s" % (screen, size, name): hashlib.sha256(img).hexdigest() for name, img in got_shots.items()}
    if update:
        table.update(got)
        with open(MESH_GOLDENS, "w") as f:
            json.dump(table, f, indent=2, sort_keys=True)
            f.write("\n")
        return
    moved = [pixel_goldens.check(k, got[k], table.get(k), lambda img=img: [img[y * w * 3:(y + 1) * w * 3] for y in range(h)],
                                 w, h) for k, img in zip(got, got_shots.values())]
    assert not any(moved), "the shots %s moved%s" % ([k for k, m in zip(got, moved) if m], pixel_goldens.message(moved))


def test_a_focus_on_no_node_stops_the_run_at_its_line(tmp_path):
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Focus", 'ui.app("Focus", { icon = "calc" })\n'
                          'ui.hook("opened", function() ui.focus("nope") end)\n'
                          'ui.page("p", function() ui.label("x") end)\n')
    ws, drv, frame, open_cart = _console(carts)
    open_cart(ws, "Focus")
    for _ in range(4):
        frame()
    err = ws.run.player.cart_error
    assert err and "error[N08] main.lua:2:" in err, err


def test_a_focus_on_a_key_two_shown_nodes_have_stops_the_run_at_its_line(tmp_path):
    """The focus runs on the second frame whatever the clock reads: the
    open arms a timer of 0 ms, which its frame fires, and that arms the
    jump's, which a frame's timers pass reaches only on the next. A run's
    time() is the kernel's monotonic clock, which no host test drives."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Twice", 'ui.app("Twice", { icon = "calc" })\n'
                          'ui.action("go", "Go", function() end)\n'
                          'ui.action("jump", "Jump", function() ui.focus("go") end)\n'
                          'ui.action("arm", "Arm", function() ui.after(0, "jump") end)\n'
                          'ui.hook("opened", function() ui.after(0, "arm") end)\n'
                          'ui.page("p", function()\n'
                          '  ui.group("A", function() ui.link("go") end)\n'
                          '  ui.group("B", function() ui.link("go") end)\n'
                          'end)\n')
    ws, drv, frame, open_cart = _console(carts)
    open_cart(ws, "Twice")
    for _ in range(3):
        frame()
    err = ws.run.player.cart_error
    assert err and "error[N08] main.lua:3:" in err and "two shown nodes are keyed go" in err, err


def test_an_anchor_on_no_node_stops_the_run_at_the_popover(tmp_path):
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Anchor", 'ui.app("Anchor", { icon = "calc" })\n'
                           'local s = ui.state { open = true }\n'
                           'ui.page("p", function()\n'
                           '  ui.label("x")\n'
                           '  ui.popover("more", { shown = "open", anchor = "nope" }, function() ui.label("y") end)\n'
                           'end)\n')
    ws, drv, frame, open_cart = _console(carts)
    open_cart(ws, "Anchor")
    for _ in range(4):
        frame()
    err = ws.run.player.cart_error
    assert err and "error[N06] main.lua:5:" in err, err


def test_a_foot_that_shares_its_width_and_a_slider_icon_draw(tmp_path):
    """foot look="share" spreads its row's buttons over its width; a
    slider's icon= stands before its label: each moves the pixels."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    body = ('ui.app("%s", { icon = "calc" })\n'
            'local s = ui.state { v = 3 }\n'
            'ui.action("a", "Add", function() end)\nui.action("b", "Back", function() end)\n'
            'ui.page("p", function()\n'
            '  ui.scroll("body", function() ui.slider("v", { label = "Level", lo = 0, hi = 9%s }) end)\n'
            '  ui.foot({%s}, function() ui.row(function() ui.button("a") ui.button("b") end) end)\n'
            'end)\n')
    shots = {}
    for name, icon, look in (("Plain", "", ""), ("Shared", "", ' look = "share" '), ("Iconed", ', icon = "calc"', "")):
        _cart(carts, name, body % (name, icon, look))
    ws, drv, frame, open_cart = _console(carts)
    for name in ("Plain", "Shared", "Iconed"):
        open_cart(ws, name)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, ws.run.player.cart_error
        shots[name] = bytes(drv.rgb888())
        ws.spine.exit_to_caller()
    assert shots["Shared"] != shots["Plain"] and shots["Iconed"] != shots["Plain"]


def test_a_lua_apps_top_page_names_the_bar_on_its_own_read(tmp_path):
    """The bar names a Lua app's top page through the page title's own read
    (moy_ui_run_page_title), with nothing lent: the pushed page's, then
    the first's again after Back."""
    from runtime import host_app
    from runtime.toolkit import ui_draw
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Named", 'ui.app("Named", { icon = "calc" })\n'
          'ui.action("go", "Go", function() ui.push("more") end, { keys = { "g" } })\n'
          'ui.page("first", function() ui.label("one") end, { title = "First" })\n'
          'ui.page("more", function() ui.label("two") end, { title = "More" })\n')
    ws, drv, frame, open_cart = _console(carts)
    open_cart(ws, "Named")
    for _ in range(4):
        frame()
    first = ui_draw.page_title(ui_draw.RUN_UI)
    assert first == "First" and ws.bar_layer._title("tool") == first
    drv.type_char(ord("g"))
    frame()
    frame()
    assert ui_draw.page_title(ui_draw.RUN_UI) == "More"
    assert ws.bar_layer._title("tool") == ui_draw.page_title(ui_draw.RUN_UI)
    assert ws.run.player.face.back()
    frame()
    frame()
    assert ui_draw.page_title(ui_draw.RUN_UI) == first
    assert ws.run.player.cart_error is None, ws.run.player.cart_error


def test_a_slider_in_a_narrow_row_keeps_its_label(tmp_path):
    """A slider's row too narrow for its label, its value and its whole
    track: the track gives way, so the label still draws (it drew nothing,
    and the value stood past the row's start)."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    body = ('ui.app("%s", { icon = "calc" })\n'
            'local s = ui.state { v = 130 }\n'
            'ui.page("p", function()\n'
            '  ui.split({ dir = "row", sizes = { 3, 2 } }, function()\n'
            '    ui.label("one")\n'
            '    ui.slider("v", { label = "%s", lo = 0, hi = 999 })\n'
            '  end)\n'
            'end)\n')
    for name, label in (("Named", "Stars fall at"), ("Bare", "")):
        _cart(carts, name, body % (name, label))
    ws, drv, frame, open_cart = _console(carts)
    shots = {}
    for name in ("Named", "Bare"):
        open_cart(ws, name)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, (name, ws.run.player.cart_error)
        top = 3 * ws.sys_canvas.w * ws.layout.cy      # the page's, under the bar's title
        shots[name] = bytes(drv.rgb888())[top:]
        ws.spine.exit_to_caller()
    assert shots["Named"] != shots["Bare"]


def test_a_link_shows_its_value_whole_or_not_at_all(tmp_path):
    """A link's value too wide for the room its label leaves is left out,
    not cut to an ellipsis, and so is one that would cut its label: the
    row draws as it does with no value; one that fits beside the whole
    label draws."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    body = ('ui.app("%s", { icon = "calc" })\n'
            'ui.action("open", "Cart info", function() end)\n'
            'ui.page("p", function()\n'
            '  ui.split({ dir = "row", sizes = { 3, 2 } }, function()\n'
            '    ui.label("one")\n'
            '    ui.link("open", { label = "%s", value = "%s" })\n'
            '  end)\n'
            'end)\n')
    names = (("Long", "Cart info", "A title far too long for this"), ("None", "Cart info", ""),
             ("Short", "Cart info", "Ab"), ("Crowd", "Cart informations", "Abc"),
             ("Alone", "Cart informations", ""))
    for name, label, value in names:
        _cart(carts, name, body % (name, label, value))
    ws, drv, frame, open_cart = _console(carts)
    shots = {}
    for name, _l, _v in names:
        open_cart(ws, name)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, (name, ws.run.player.cart_error)
        top = 3 * ws.sys_canvas.w * ws.layout.cy      # the page's, under the bar's title
        shots[name] = bytes(drv.rgb888())[top:]
        ws.spine.exit_to_caller()
    assert shots["Long"] == shots["None"]
    assert shots["Short"] != shots["None"]
    assert shots["Crowd"] == shots["Alone"]


def test_a_split_a_grid_and_a_panel_draw_on_the_c_engine(tmp_path):
    """The placing kinds only the C engine draws: a split's parts, a grid's
    cells and a panel each move the pixels."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    body = ('ui.app("%s", { icon = "calc" })\n'
            'ui.action("a", "Add", function() end)\nui.action("b", "Back", function() end)\n'
            'ui.page("p", function()\n%s\nend)\n')
    pages = {
        "Plain": '  ui.label("one")\n  ui.label("two")',
        "Split": '  ui.split({ dir = "row", sizes = { 1, 1 }, gap = 6, pad = 0 }, function() ui.label("one") ui.label("two") end)',
        "Grid": '  ui.grid({ cols = 2, rows = 1 }, function() ui.button("a") ui.button("b") end)',
        "Panel": '  ui.panel("side", function() ui.label("one") end)\n  ui.label("two")',
    }
    for name, page in pages.items():
        _cart(carts, name, body % (name, page))
    ws, drv, frame, open_cart = _console(carts)
    shots = {}
    for name in pages:
        open_cart(ws, name)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, (name, ws.run.player.cart_error)
        shots[name] = bytes(drv.rgb888())
        ws.spine.exit_to_caller()
    assert shots["Split"] != shots["Plain"] and shots["Grid"] != shots["Plain"]


def test_a_status_line_is_an_apps_and_draws_on_the_c_engine(tmp_path):
    """ui.status, a page's status strip, is an app's kind: it lowers and draws."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    body = 'ui.app("%s", { icon = "calc" })\nui.page("p", function()\n%s\nend)\n'
    pages = {"Bare": '  ui.label("one")', "Strip": '  ui.label("one")\n  ui.status("left · right")'}
    for name, page in pages.items():
        _cart(carts, name, body % (name, page))
    ws, drv, frame, open_cart = _console(carts)
    shots = {}
    for name in pages:
        open_cart(ws, name)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, (name, ws.run.player.cart_error)
        shots[name] = bytes(drv.rgb888())
        ws.spine.exit_to_caller()
    assert shots["Strip"] != shots["Bare"]


def test_the_props_only_the_c_engine_draws_lower_and_draw(tmp_path):
    """A button's marked, tone and w, a group's and a row's close, a row's
    gap, pad and mid, a slider's look and a rows' changed: each
    page opens on the C engine and draws."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    head = ('ui.app("%s", { icon = "calc" })\n'
            'local s = ui.state { on = true, v = 3, q = "", items = ui.model { key = "id", id = "" } }\n'
            'ui.action("a", "Add", function() end)\nui.action("x", "Close", function() end)\n'
            'ui.action("pick", "Pick", function(row) end, { takes = "row" })\n'
            'ui.hook("opened", function() s.items:set({ { id = "one" }, { id = "two" } }) end)\n'
            'ui.page("p", function()\n%s\nend)\n')
    pages = {
        "Marked": '  ui.button("a", { marked = "on", tone = "danger", w = 60 })',
        "Closer": '  ui.group("G", { close = "x" }, function() ui.label("in") end)',
        "Spaced": '  ui.foot(function() ui.row({ close = "x", gap = 4, pad = 2, mid = true }, function() ui.button("a") end) end)',
        "Steps": '  ui.slider("v", { label = "Level", lo = 0, hi = 9, look = "steps" })',
        "Picked": '  ui.rows("items", { changed = "pick" }, function() ui.label("{.id}") end)',
    }
    for name, page in pages.items():
        _cart(carts, name, head % (name, page))
    ws, drv, frame, open_cart = _console(carts)
    for name in pages:
        open_cart(ws, name)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, (name, ws.run.player.cart_error)
        ws.spine.exit_to_caller()


def test_tabs_cards_and_a_rows_group_draw_and_a_filter_is_refused_on_the_c_engine(tmp_path):
    """Tabs over an enum, cards with their card, and a rows' group open on
    the C engine and draw; a rows' filter, which the engine does not draw
    (nor for a Python app), stops the run at its line with E00."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    head = ('ui.app("%s", { icon = "calc" })\n'
            'local s = ui.state { tab = ui.enum("a", "b", { init = "a" }), q = "",\n'
            '  items = ui.model { key = "id", id = "", kind = "" } }\n'
            'ui.labels("TABS", { a = "A", b = "B" })\n'
            'ui.action("pick", "Pick", function(row) end, { takes = "row" })\n'
            'ui.hook("opened", function() s.items:set({ { id = "one", kind = "x" }, { id = "two", kind = "y" } }) end)\n'
            'ui.page("p", function()\n%s\nend)\n')
    pages = {
        "Tabbed": '  ui.tabs("tab", { labels = "TABS", offered = { b = "q" } })',
        "Shelf": '  ui.cards("items", { w = 80, h = 60 }, function() ui.card("pick", { label = "{.id}", sub = "{.kind}" }) end)',
        "Grouped": '  ui.rows("items", { group = "{.kind}" }, function() ui.label("{.id}") end)',
        "Found": '  ui.rows("items", { filter = "q" }, function() ui.label("{.id}") end)',
    }
    for name, page in pages.items():
        _cart(carts, name, head % (name, page))
    ws, drv, frame, open_cart = _console(carts)
    for name in ("Tabbed", "Shelf", "Grouped"):
        open_cart(ws, name)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, (name, ws.run.player.cart_error)
        ws.spine.exit_to_caller()
    open_cart(ws, "Found")
    for _ in range(4):
        frame()
    err = ws.run.player.cart_error
    assert err and "error[E00] main.lua:8:" in err and "filter" in err, err


def test_a_canvas_draws_with_the_carts_verbs_inside_the_frame(tmp_path):
    """A canvas's draw runs inside the C engine's frame at the canvas's rect
    and draws with the cart's own verbs; a draw that writes state stops the
    run at its line (S06), as a mistake in a draw does."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    head = ('ui.app("%s", { icon = "calc" })\n'
            'local s = ui.state { n = 0, m = 0 }\n'
            'ui.page("p", function()\n%s\nend)\n')
    pages = {
        "Bare": '  ui.label("x")',
        "Pad": '  ui.label("x")\n  ui.canvas("pad", { h = 40, draw = function(x, y, w, h) rect(x, y, w, h, 8) end })',
        "Writes": '  ui.canvas("pad", { h = 40, draw = function(x, y, w, h)\n    s.n = 1\n  end })',
        "Reads": '  ui.canvas("pad", { h = 40, reads = { "m" }, draw = function(x, y, w, h)\n    local v = s.n\n  end })',
    }
    for name, page in pages.items():
        _cart(carts, name, head % (name, page))
    ws, drv, frame, open_cart = _console(carts)
    shots = {}
    for name in ("Bare", "Pad"):
        open_cart(ws, name)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, (name, ws.run.player.cart_error)
        shots[name] = bytes(drv.rgb888())
        ws.spine.exit_to_caller()
    assert shots["Pad"] != shots["Bare"]
    open_cart(ws, "Writes")
    for _ in range(4):
        frame()
    err = ws.run.player.cart_error
    assert err and "error[S06] main.lua:5:" in err, err
    ws.spine.exit_to_caller()
    open_cart(ws, "Reads")
    for _ in range(4):
        frame()
    err = ws.run.player.cart_error
    assert err and "error[R01] main.lua:5:" in err, err
    ws.spine.exit_to_caller()


def test_a_canvas_in_a_rows_body_is_handed_its_row(tmp_path):
    """A canvas in a rows' body draws each row, handed the row it stands in
    after its rect (read-only, as an action's row is)."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    head = ('ui.app("%s", { icon = "calc" })\n'
            'local s = ui.state { items = ui.model { key = "id", id = "" } }\n'
            'ui.hook("opened", function() s.items:set({ { id = "one" }, { id = "two" } }) end)\n'
            'ui.page("p", function()\n%s\nend)\n')
    pages = {
        "Nobody": '  ui.rows("items", {}, function() ui.canvas("lead", { h = 12, draw = function(x, y, w, h, row)\n'
                  '    if row.id == "none" then rect(x, y, w, h, 8) end end }) end)',
        "Two": '  ui.rows("items", {}, function() ui.canvas("lead", { h = 12, draw = function(x, y, w, h, row)\n'
               '    if row.id == "two" then rect(x, y, w, h, 8) end end }) end)',
    }
    for name, page in pages.items():
        _cart(carts, name, head % (name, page))
    ws, drv, frame, open_cart = _console(carts)
    shots = {}
    for name in ("Nobody", "Two"):
        open_cart(ws, name)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, (name, ws.run.player.cart_error)
        shots[name] = bytes(drv.rgb888())
        ws.spine.exit_to_caller()
    assert shots["Two"] != shots["Nobody"]


def test_a_rows_list_takes_dir_col_and_refuses_another_word(tmp_path):
    """`ui.rows(model, { dir = "col" })` reaches the engine from Lua: a
    flowing page draws its rows as a list without it (the column from a
    model is a placed column's), and a word but row or col stops the run."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    head = ('ui.app("%s", { icon = "calc" })\n'
            'local s = ui.state { items = ui.model { key = "id", id = "" } }\n'
            'ui.hook("opened", function() s.items:set({ { id = "one" }, { id = "two" } }) end)\n'
            'ui.page("p", function()\n  ui.rows("items", %s, function() ui.label("{.id}") end)\nend)\n')
    for name, opts in (("Plain", "{}"), ("Col", '{ dir = "col" }'), ("Diag", '{ dir = "diag" }')):
        _cart(carts, name, head % (name, opts))
    ws, drv, frame, open_cart = _console(carts)
    shots, errors = {}, {}
    for name in ("Plain", "Col", "Diag"):
        open_cart(ws, name)
        for _ in range(4):
            frame()
        errors[name] = ws.run.player.cart_error
        _edge, bar, _dy, _cells = ws.layout.bars[0]
        below = (bar[1] + bar[3]) * ws.sys_canvas.w * 3     # (the bar names the app)
        shots[name] = bytes(drv.rgb888())[below:]
        ws.spine.exit_to_caller()
    assert errors["Plain"] is None and errors["Col"] is None, errors
    assert shots["Col"] == shots["Plain"]
    assert errors["Diag"] is not None and "dir" in str(errors["Diag"]), errors["Diag"]


def test_a_canvas_pointer_hands_down_drag_and_up_in_its_own_coordinates(tmp_path):
    """A canvas with pointer= on the C engine: a press on it hands its action
    a read-only event (kind, x, y, source) at the canvas's own coordinates,
    the drag that follows and the release, each traced as Python's are."""
    from runtime import host_app
    from runtime.host import moy_log
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Pointer", 'ui.app("Pointer", { icon = "calc" })\n'
          'local s = ui.state { got = "" }\n'
          'ui.action("feel", "Feel", function(ev) s.got = s.got .. ev.kind .. ":" .. ev.source .. " " end,\n'
          '  { takes = "pointer" })\n'
          'ui.page("p", function()\n'
          '  ui.canvas("pad", { h = 120, pointer = "feel", draw = function(x, y, w, h) rect(x, y, w, h, 8) end })\n'
          'end)\n')
    ws, drv, frame, open_cart = _console(carts)
    seq = moy_log.next()
    open_cart(ws, "Pointer")
    for _ in range(4):
        frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    cx, cy = ws.sys_canvas.w // 2, ws.sys_canvas.h // 2
    drv.touch(cx, cy)
    frame()
    drv.touch_drag(cx + 5, cy + 3)
    frame()
    drv.touch_up()
    frame()
    frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    lines = [r[4].split("[trace] ", 1)[1] for r in moy_log.read(seq, 4000) if "[trace] " in r[4]]
    acts = [" ".join(l.split()[1:]) for l in lines if l.split()[1:2] == ["action"]]
    assert acts == ["action feel from pointer down on canvas 'pad'", "action feel from pointer drag on canvas 'pad'",
                    "action feel from pointer up on canvas 'pad'"], lines
    assert any("down:touch drag:touch up:touch" in l for l in lines), lines


def test_while_a_popover_is_open_only_a_canvas_in_it_takes_a_press(tmp_path):
    """A canvas under an open popover takes no press; one inside the
    popover takes its own (docs/app_api_v1.md's canvas), as uitree_c.py's
    point() routes a Python app's."""
    from runtime import host_app
    from runtime.host import moy_log
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Modal", 'ui.app("Modal", { icon = "calc" })\n'
          'local s = ui.state { open = true }\n'
          'ui.action("under", "Under", function(ev) end, { takes = "pointer" })\n'
          'ui.action("inner", "Inner", function(ev) end, { takes = "pointer" })\n'
          'ui.page("p", function()\n'
          '  ui.canvas("pad", { h = 160, pointer = "under", draw = function(x, y, w, h) rect(x, y, w, h, 12) end })\n'
          '  ui.popover("pop", { shown = "open", anchor = "pad", w = 120 }, function()\n'
          '    ui.canvas("in", { h = 40, pointer = "inner", draw = function(x, y, w, h) rect(x, y, w, h, 8) end })\n'
          '  end)\n'
          'end)\n')
    ws, drv, frame, open_cart = _console(carts)
    open_cart(ws, "Modal")
    for _ in range(6):
        frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    w, h = ws.sys_canvas.w, ws.sys_canvas.h
    rgb = bytes(drv.rgb888())
    # colour 8 is red, 12 blue (the PICO-8 palette)
    px = [(x, y, rgb[(y * w + x) * 3], rgb[(y * w + x) * 3 + 2])
          for y in range(0, h, 2) for x in range(0, w, 2)]
    inner = [(x, y) for x, y, r, b in px if r > 200 and b < 120]
    blue = [(x, y) for x, y, r, b in px if b > 200 and r < 120]
    assert inner and blue

    def tap(x, y):
        seq = moy_log.next()
        drv.touch(x, y)
        frame()
        drv.touch_up()
        frame()
        frame()
        lines = [r[4].split("[trace] ", 1)[1] for r in moy_log.read(seq, 4000) if "[trace] " in r[4]]
        return [" ".join(l.split()[1:]) for l in lines if l.split()[1:2] == ["action"]]

    ix, iy = inner[len(inner) // 2]
    took = tap(ix, iy)
    assert any("action inner from pointer down on canvas 'in'" in l for l in took), took
    ux, uy = blue[len(blue) // 2]
    took = tap(ux, uy)
    assert not any("canvas 'pad'" in l for l in took), took


def test_a_letter_key_and_the_confirm_role_fire_on_the_c_engine(tmp_path):
    """An action's letter key fires it, traced `key 's'`, and the confirm
    role's key fires its action where nothing on the page is focused, as
    uitree_c.py's keys() fires them for a Python app."""
    from runtime import host_app
    from runtime.host import moy_log
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Keys", 'ui.app("Keys", { icon = "calc" })\n'
          'local s = ui.state { n = 0 }\n'
          'ui.action("save", "Save", function() s.n = s.n + 1 end, { keys = { "s" } })\n'
          'ui.action("go", "Go", function() s.n = s.n + 10 end, { keys = { "role:confirm" } })\n'
          'ui.page("p", function() ui.label("{n}") end)\n')
    ws, drv, frame, open_cart = _console(carts)
    seq = moy_log.next()
    open_cart(ws, "Keys")
    for _ in range(4):
        frame()
    drv.type_char(ord("s"))
    frame()
    frame()
    drv.press("a")
    frame()
    frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    lines = [r[4].split("[trace] ", 1)[1] for r in moy_log.read(seq, 4000) if "[trace] " in r[4]]
    acts = [" ".join(l.split()[1:]) for l in lines if l.split()[1:2] == ["action"]]
    assert acts == ["action save from key 's'", "action go from role confirm"], lines


def test_the_hosts_back_steps_a_lua_apps_pages_through_the_engines_way_back(tmp_path):
    """The engine offers the host's back a way back where the page has one
    (`UIT_F_BACK`: a page under the top one, the back role) and answers a
    taken one at the next frame (`e:backed()`): the pushed page goes, then
    the back role's action runs, once each; with neither the host leaves."""
    from runtime import host_app
    from runtime.host import moy_log
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    pages = ('ui.action("go", "Go", function() ui.push("two") end, { keys = { "g" } })\n'
             'ui.page("one", function() ui.label("one") end)\n'
             'ui.page("two", function() ui.label("two") end)\n')
    _cart(carts, "Plain", 'ui.app("Plain", { icon = "calc" })\n' + pages)
    _cart(carts, "Role", 'ui.app("Role", { icon = "calc" })\n'
          'ui.action("off", "Off", function() end, { keys = { "role:back" } })\n' + pages)
    ws, drv, frame, open_cart = _console(carts)
    seq = moy_log.next()
    for name in ("Plain", "Role"):
        open_cart(ws, name)
        for _ in range(4):
            frame()
        face = ws.run.player.face
        assert face.has_page() == (name == "Role"), (name, "the back role is a way back")
        drv.type_char(ord("g"))
        frame()
        frame()
        assert face.has_page(), (name, "the page under the pushed one")
        assert face.back(), (name, "the pushed page is the app's to step out of")
        frame()
        frame()
        assert face.has_page() == (name == "Role"), (name, "back on the first page")
        assert face.back() == (name == "Role"), (name, "the back role's action, or the host's")
        frame()
        frame()
        assert ws.run.player.cart_error is None, ws.run.player.cart_error
        ws.spine.exit_to_caller()
    lines = [r[4].split("[trace] ", 1)[1] for r in moy_log.read(seq, 8000) if "[trace] " in r[4]]
    acts = [" ".join(l.split()[1:]) for l in lines if l.split()[1:2] == ["action"]]
    assert acts == ["action go from key 'g'", "action go from key 'g'",
                    "action off from role back on 'one'"], lines


def test_a_typed_char_and_a_buttons_arg_reach_their_actions_on_the_c_engine(tmp_path):
    """An action's chars= is handed the character typed, as typed, and a
    button's arg= is handed to its action on a press, as uitree_c.py hands
    them to a Python app."""
    from runtime import host_app
    from runtime.host import moy_log
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Chars", 'ui.app("Chars", { icon = "calc" })\n'
          'local s = ui.state { got = "" }\n'
          'ui.action("put", "Put", function(c) s.got = s.got .. c end, { takes = "char", chars = "+7C" })\n'
          'ui.action("key", "Key", function(a) s.got = s.got .. "[" .. tostring(a) .. "]" end, { takes = "arg" })\n'
          'ui.page("p", function()\n'
          '  ui.label("{got}")\n'
          '  ui.button("key", { arg = 5, label = "five" })\n'
          'end)\n')
    ws, drv, frame, open_cart = _console(carts)
    seq = moy_log.next()
    open_cart(ws, "Chars")
    for _ in range(4):
        frame()
    for ch in "7+C":
        drv.type_char(ord(ch))
        frame()
        frame()
    drv.press("a")
    frame()
    frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    lines = [r[4].split("[trace] ", 1)[1] for r in moy_log.read(seq, 4000) if "[trace] " in r[4]]
    got = [l.split('-> ')[1].split()[0] for l in lines if l.split()[1:3] == ["state", "got"]]
    assert got == ['"7"', '"7+"', '"7+C"', '"7+C[5]"'], lines


def test_a_cancelled_timer_runs_nothing(tmp_path):
    from runtime import host_app
    from runtime.host import moy_log
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Timers", 'ui.app("Timers", { icon = "calc" })\n'
                           'local s = ui.state { log = "" }\n'
                           'ui.action("tick", "Tick", function() s.log = s.log .. "t" end)\n'
                           'ui.action("boom", "Boom", function() s.log = s.log .. "b" end)\n'
                           'ui.action("late", "Late", function() s.log = s.log .. "l" end)\n'
                           'ui.hook("opened", function()\n'
                           '  ui.after(0, "tick")\n'
                           '  ui.after(0, "boom")\n'
                           '  ui.after(60000, "late")\n'
                           '  ui.cancel("boom")\n'
                           'end)\n'
                           'ui.page("p", function() ui.label("{log}") end)\n')
    ws, drv, frame, open_cart = _console(carts)
    seq0 = moy_log.next()
    open_cart(ws, "Timers")
    for _ in range(12):
        frame()
    assert ws.run.player.cart_error is None
    lines = [r[4] for r in moy_log.read(seq0, 4000) if "[trace]" in str(r[4])]
    ran = [l.split()[3] for l in lines if " action " in l]
    assert "tick" in ran and "boom" not in ran and "late" not in ran, lines
    assert any("cancelled" in l for l in lines), lines


# -- the checker: one failing case per code ------------------------------------------

APP = 'ui.app("T", { icon = "calc" })\n'
PAGE = '\nui.page("p", function() ui.label("x") end)\n'
GO = 'ui.action("go", "Go", function() end)\n'
REC = 'local s = ui.state { r = ui.record { x = 0 } }\n'

# code: (main.lua, the line the error names, a fire.lua run after the build or None)
CASES = {
    "A01": (APP + GO + 'ui.page("p", function() ui.button(function() end) end)\n', 3, None),
    "A02": (APP + 'local s = ui.state { m = ui.model { key = "id", id = "" }, cur = ui.opt(ui.row_of("m")) }\n'
            'ui.action("del", "Delete", function(a) end, { row = "cur", takes = "arg", off = "hide" })' + PAGE, 3, None),
    "A03": (APP + 'ui.action("go", "Go", function(a, b) end)' + PAGE, 2, None),
    "A08": (APP + 'ui.action("go", "", function() end)' + PAGE, 2, None),
    "A09": (APP + 'ui.action(3, "Go", function() end)' + PAGE, 2, None),
    "A10": (APP + 'ui.after(100, "go")\n' + GO + PAGE, 2, None),
    "B01": (APP + 'local s = ui.state { n = 0 }\nui.page("p", function()\n  if s.n > 0 then ui.label("x") end\nend)\n', 4, None),
    "B02": (APP + 'local s = ui.state { n = 0 }\nui.page("p", function()\n  s.n = 1\n  ui.label("x")\nend)\n', 4, None),
    "B03": (APP + 'ui.page("p", function()\n  ui.action("go", "Go", function() end)\nend)\n', 3, None),
    "C01": (APP + 'local s = ui.state { n = 0 }\nui.page("p", function() ui.label("x", { shown = "{n}" }) end)\n', 3, None),
    "C02": (APP + 'local s = ui.state { a = false, b = false, c = false }\n'
            'ui.page("p", function() ui.label("x", { shown = "a && b || c" }) end)\n', 3, None),
    "C01 single": (APP + 'local s = ui.state { a = false, b = false }\n'
                   'ui.page("p", function() ui.label("x", { shown = "a & b" }) end)\n', 3, None),
    "C03": (APP + 'local s = ui.state { a = false, b = false, c = false }\n'
            'ui.page("p", function() ui.label("x", { shown = "a && (b || c)" }) end)\n', 3, None),
    "D01": (APP + 'ui.app("T2", { icon = "calc" })' + PAGE, 2, None),
    "D02": ('ui.app("T", { icon = "calc", size = 3 })' + PAGE, 1, None),
    "D04": (PAGE, "load", None),
    "E00": (APP + 'ui.page("p", function() ui.label("x", { span = 2 }) end)\n', 2, None),
    "E01": (APP + 'local s = ui.state { e = ui.enum("a", "b") }' + PAGE, 2, None),
    "E02": (APP + 'local s = ui.state { e = ui.enum("a", "b", { init = "c" }) }' + PAGE, 2, None),
    "E03": (APP + 'local s = ui.state { e = ui.enum("a", 3, { init = "a" }) }' + PAGE, 2, None),
    "G01": (APP + 'local s = ui.state { n = 0 }\nui.derive("x", { cond = "y" })\nui.derive("y", { cond = "x" })' + PAGE, 3, None),
    "H01": (APP + 'ui.hook("tick", function() end)\nui.page("p", function() ui.button("tick") end)\n', 3, None),
    "H03": (APP + 'ui.hook("tick", function() end, { hint = "Tick" })' + PAGE, 2, None),
    "I02": (APP + 'ui.action("go", "Go", function() end, { icon = "{n}" })' + PAGE, 2, None),
    "K01": (APP + 'ui.action("go", "Go", function() end, { keys = { "role:home" } })' + PAGE, 2, None),
    "N09": ('ui.app("T", { icon = "calc", slots = { "run" } })' + PAGE, 1, None),
    "N09 column": (APP + 'local s = ui.state { items = ui.model { key = "id", id = "" } }\n'
                   'ui.page("p", function() ui.cards("items", { look = "column" }, function()\n'
                   '  ui.card("pick", { label = "{.id}" }) end) end)\n', 3, None),
    "N09 fill": (APP + 'local s = ui.state { items = ui.model { key = "id", id = "" } }\n'
                 'ui.action("pick", "Pick", function(row) end, { takes = "row" })\n'
                 'ui.page("p", function() ui.cards("items", {}, function()\n'
                 '  ui.card("pick", { label = "{.id}", fill = "{.id}" }) end) end)\n', 5, None),
    "K02": (APP + 'ui.action("go", "Go", function() end, { keys = { "s" } })\n'
            'ui.action("stop", "Stop", function() end, { keys = { "s" } })' + PAGE, 3, None),
    "K03": (APP + 'ui.action("go", "Go", function() end, { keys = { "alt+x" } })' + PAGE, 2, None),
    "N01": (APP + 'ui.page("p", function() ui.label("x", { nope = 1 }) end)\n', 2, None),
    "N01 scroll": (APP + 'ui.page("p", function() ui.scroll(function() ui.label("x") end) end)\n', 2, None),
    "N01 derive": (APP + 'local s = ui.state { n = 0 }\nui.derive("big", "bool", "n>3")' + PAGE, 3, None),
    "N01 text derive": (APP + 'local s = ui.state { n = 0 }\nui.derive("left", { text = "{n} left" })\n'
                        'ui.derive("big", { cond = "n>3", text = "x" })' + PAGE, 4, None),
    "N02": (APP + GO + 'ui.page("p", function()\n  ui.button("go")\n  ui.button("go")\nend)\n', 5, None),
    "N03": (APP + 'local s = ui.state { m = ui.model { key = "id", id = "" } }\nui.page("p", function()\n'
            '  ui.rows("m", function()\n    ui.rows("m", function() ui.label("x") end)\n  end)\nend)\n', 5, None),
    "N04": (APP + 'ui.at(0, 0, 10, 10)' + PAGE, 2, None),
    "O01": (APP + 'local s = ui.state { a = false }\nui.action("go", "Go", function() end, { when = "a" })' + PAGE, 3, None),
    "O02": (APP + 'ui.action("go", "Go", function() end, { off = "grey" })' + PAGE, 2, None),
    "O04": (APP + 'local s = ui.state { a = false }\nui.page("p", function() ui.label("x", { when = "a" }) end)\n', 3, None),
    "P01": (APP + 'ui.action("open", "Open", nil, { push = "nope" })' + PAGE, 2, None),
    "P02": (APP + 'ui.action("open", "Open", nil, { push = "p", takes = "row" })' + PAGE, 2, None),
    "P03": (APP + 'ui.action("open", "Open", function() end, { push = "p" })' + PAGE, 2, None),
    "P04": (APP + 'local s = ui.state { n = 0 }' + PAGE + 'ui.page("q", function() ui.label("y") end, { arg = "n" })\n',
            4, None),
    "S01": (APP + 'local s = ui.state { n = 0 }\nlocal x = s.nope' + PAGE, 3, None),
    "S02": (APP + REC + 'ui.action("go", "Go", function()\n  s.r = { x = "a" }\nend)' + PAGE, 4, 'ui._fire("go")\n'),
    "S03": (APP + REC + 'ui.action("go", "Go", function()\n  s.r.x = 1\nend)' + PAGE, 4, 'ui._fire("go")\n'),
    "S04": (APP + REC + 'ui.action("go", "Go", function()\n  local v = s.r.nope\nend)' + PAGE, 4, 'ui._fire("go")\n'),
    "S05": (APP + REC + 'ui.action("go", "Go", function()\n  s.r = 5\nend)' + PAGE, 4, 'ui._fire("go")\n'),
    "S06": (APP + 'local s = ui.state { n = 0 }\ns.n = 1' + PAGE, 3, None),
    "P05": (APP + 'ui.action("go", "Go", function()\n  ui.pop()\nend)' + PAGE, 3, 'ui._fire("go")\n'),
    "S07": (APP + 'local s = ui.state { m = ui.model { name = "" } }' + PAGE, 2, None),
    "S09": (APP + 'local s = ui.state { n = 0 }\nui.derive("big", { cond = "n>3" })\n'
            'ui.action("go", "Go", function()\n  s.big = true\nend)' + PAGE, 5, 'ui._fire("go")\n'),
    "S11": (APP + 'local s = ui.state { r = ui.row_of(3) }' + PAGE, 2, None),
    "S13": (APP + 'local s = ui.state { x = print }' + PAGE, 2, None),
    "T01": (APP + 'local s = ui.state { n = 0 }\nui.page("p", function() ui.label("{n|nope}") end)\n', 3, None),
    "T02": (APP + 'ui.page("p", function() ui.label("{@nope}") end)\n', 2, None),
    "T03": (APP + 'local s = ui.state { n = 0 }\nui.page("p", function() ui.label("{n.x}") end)\n', 3, None),
    "T03 signal": (APP + 'local s = ui.state { t = "" }\nui.page("p", function() ui.info("Signal", { signal = "{t}" }) end)\n', 3, None),
    "N01 labels": (APP + GO + 'ui.page("p", function()\n'
                   '  ui.dialog("D", { buttons = { "go" }, labels = { "A", "B" } }, function() end)\nend)\n', 4, None),
    "N01 signal": (APP + 'ui.page("p", function() ui.info("Signal", { signal = "3 bars" }) end)\n', 2, None),
    "N01 edit word": (APP + 'local s = ui.state { t = "" }\nui.page("p", function() ui.field("t", { edit = "always" }) end)\n', 3, None),
    "N01 keys word": (APP + 'local s = ui.state { t = "" }\nui.page("p", function() ui.field("t", { keys = "qwerty" }) end)\n', 3, None),
    "N01 gap word": (APP + 'ui.page("p", function() ui.split({ dir = "row", sizes = { 1, 1 }, gap = "s" }, function() end) end)\n', 2, None),
    "T04": (APP + 'local s = ui.state { e = ui.enum("a", "b", { init = "a" }) }\nui.labels("L", { a = "A" })\n'
            'ui.page("p", function() ui.label("{e|map L}") end)\n', 4, None),
    "T05": (APP + 'ui.page("p", function() ui.label("{.x}") end)\n', 2, None),
    "U02": (APP + 'local s = ui.state { go = 0 }\n' + GO + PAGE, 3, None),
    "W01": (APP + 'local s = ui.state { t = "" }\nui.action("go", "Go", function(row) end, { takes = "row" })\n'
            'ui.page("p", function() ui.field("t", { on = "go" }) end)\n', 4, None),
    # what only the source read sees
    "Q01": (APP + 'ui.action("go", "Go", function()\n  undefined_thing()\nend)' + PAGE, 3, None),
    "S13 source": (APP + 'local s = ui.state { a = nil, n = 0 }' + PAGE, 2, None),
    "P01 source": (APP + 'ui.action("go", "Go", function()\n  ui.push("nope")\nend)' + PAGE, 3, None),
    "A01 source": (APP + 'ui.action("go", "Go", function()\n  ui.post("nope")\nend)' + PAGE, 3, None),
    "A02 source": (APP + 'ui.hook("h", function() end)\nui.action("go", "Go", function()\n  ui.post("h", 3)\nend)'
                   + PAGE, 4, None),
    "S09 source": (APP + 'local s = ui.state { n = 0 }\nui.derive("big", { cond = "n>3" })\n'
                   'ui.action("go", "Go", function()\n  s.big = true\nend)' + PAGE, 5, None),
    "S03 source": (APP + REC + 'ui.action("go", "Go", function()\n  s.r.x = 1\nend)' + PAGE, 4, None),
    "S04 source": (APP + REC + 'ui.action("go", "Go", function()\n  local v = s.r.nope\nend)' + PAGE, 4, None),
}

# The one code a Lua app cannot reach: X01 is the layer's own assertion that a
# condition was checked at build.
NOT_RAISABLE = {"X01"}
# what only a frame raises, cased on the console above
RUN_CASES = {"N08", "N06", "R01"}


def test_every_code_the_layer_raises_has_a_case():
    import re
    with open(checker.LAYER) as fh:
        raised = set(re.findall(r'fail\("([A-Z][0-9]{2})"', fh.read()))
    with open(checker.__file__) as fh:
        raised |= set(re.findall(r'_err\("([A-Z][0-9]{2})"', fh.read()))
    cased = {c.split()[0] for c in CASES}
    assert raised - NOT_RAISABLE - RUN_CASES - cased == set()
    assert cased - raised == set()


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_checker_reports_each_code_at_its_line(case, tmp_path):
    main, line, fire = CASES[case]
    code = case.split()[0]
    extra = {"fire.lua": fire} if fire else None
    d = _cart(str(tmp_path), "case", main, extra)
    errors = [e for e in checker.check(d, after=["fire.lua"] if fire else ()) if e.startswith("error[")]
    where = "load" if line == "load" else "main.lua:%d" % line
    want = "error[%s] %s:" % (code, where)
    assert any(e.startswith(want) for e in errors), "%s not in %r" % (want, errors)
    for e in errors:
        assert "; fix: " in e and "(expected " in e, e


@pytest.mark.parametrize("cart", ["counter", "mesh_thread", "mesh_radio"])
def test_the_fixtures_check_clean(cart, tmp_path):
    d = os.path.join(str(tmp_path), cart + ".moy")
    shutil.copytree(shots.fixture(cart), d)
    for f in ("mesh.lua", "data.lua"):
        src = os.path.join(shots.MESH, f) if f == "mesh.lua" else os.path.join(shots.fixture("mesh_thread"), f)
        if not os.path.exists(os.path.join(d, f)):
            shutil.copy(src, d)
    assert checker.check(d) == []


def test_a_carousel_steps_and_plays_its_centre_card_on_the_c_engine(tmp_path):
    """A Lua app's `ui.cards(look="carousel")` lowers and draws on the C
    engine, right glides it a card (cur= follows) and the confirm role plays
    the centre card, as for a Python app (tests/test_uitree_carousel.py)."""
    from runtime import host_app
    from runtime.host import moy_log
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Row", 'ui.app("Row", { icon = "calc" })\n'
          'local s = ui.state { items = ui.model { key = "id", id = "", kind = "" }, at = ui.row_of("items") }\n'
          'ui.action("pick", "Pick", function(row) end, { takes = "row" })\n'
          'ui.hook("opened", function() s.items:set({ { id = "one", kind = "x" }, { id = "two", kind = "y" },\n'
          '  { id = "three", kind = "z" } }) end)\n'
          'ui.page("p", function()\n'
          '  ui.cards("items", { look = "carousel", cur = "at", w = 32 }, function()\n'
          '    ui.card("pick", { label = "{.id}", sub = "{.kind}", icon = "star" }) end)\n'
          'end)\n')
    ws, drv, frame, open_cart = _console(carts)
    seq = moy_log.next()
    open_cart(ws, "Row")
    for _ in range(6):
        frame()
    drv.press("right")
    for _ in range(30):
        frame()
    drv.press("a")
    frame()
    frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    lines = [r[4].split("[trace] ", 1)[1] for r in moy_log.read(seq, 4000) if "[trace] " in r[4]]
    assert any("'one' -> 'two'" in l and "(carousel)" in l for l in lines), lines
    acts = [l for l in lines if l.split()[1:3] == ["action", "pick"]]
    assert len(acts) == 1 and "'two/pick'" in acts[0], lines


def test_a_cells_clear_colour_draws_the_checker_on_the_c_engine(tmp_path):
    """ui.cells' clear= from Lua: colour 0's cell is transparency's grey
    checker (chrome.FIXED's dark and light) under a white stroke, where
    without it the cell is black."""
    from runtime import host_app
    import chrome
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    body = ('ui.app("%s", { icon = "calc" })\n'
            'local s = ui.state { c = 3 }\n'
            'ui.page("p", function()\n'
            '  ui.cells("c", { first = 0, count = 16, cols = 4, side = 24%s })\n'
            'end)\n')
    for name, clear in (("Plain", ""), ("Clear", ", clear = 0")):
        _cart(carts, name, body % (name, clear))
    ws, drv, frame, open_cart = _console(carts)
    shots = {}
    for name in ("Plain", "Clear"):
        open_cart(ws, name)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, (name, ws.run.player.cart_error)
        shots[name] = bytes(drv.rgb888())
        ws.spine.exit_to_caller()

    def count(buf, rgb):
        r, g, b = (rgb >> 16) & 0xf8, (rgb >> 8) & 0xfc, rgb & 0xf8
        return sum(1 for i in range(0, len(buf), 3)
                   if buf[i] & 0xf8 == r and buf[i + 1] & 0xfc == g and buf[i + 2] & 0xf8 == b)

    dark, light = chrome.FIXED[0] & 0xffffff, chrome.FIXED[1] & 0xffffff
    for rgb in (dark, light):
        assert count(shots["Clear"], rgb) > count(shots["Plain"], rgb), hex(rgb)


def test_a_text_views_gutter_numbers_its_lines_on_the_c_engine(tmp_path):
    """ui.text_view's gutter= from Lua: the lines' numbers stand before
    them, which shifts the text right; without it the text starts at the
    view's edge."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    body = ('ui.app("%s", { icon = "calc" })\n'
            'local s = ui.state { t = "x = 1\\ny = 2\\nz = 3" }\n'
            'ui.page("p", function()\n'
            '  ui.text_view("t", { syntax = "python"%s })\n'
            'end)\n')
    for name, gutter in (("Plain", ""), ("Numbered", ", gutter = true")):
        _cart(carts, name, body % (name, gutter))
    ws, drv, frame, open_cart = _console(carts)
    shots = {}
    for name in ("Plain", "Numbered"):
        open_cart(ws, name)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, (name, ws.run.player.cart_error)
        shots[name] = bytes(drv.rgb888())
        ws.spine.exit_to_caller()
    assert shots["Plain"] != shots["Numbered"]


def test_a_lists_changed_runs_on_a_users_move_only_on_the_c_engine(tmp_path):
    """A list's changed= runs where the user moves its cursor from one of
    its rows to another, never where focus arrives on it from the button
    above, as it does for a Python app."""
    from runtime import host_app
    from runtime.host import moy_log
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Moves", 'ui.app("Moves", { icon = "calc" })\n'
          'local s = ui.state { items = ui.model { key = "id", id = "" }, cur = ui.row_of("items") }\n'
          'ui.hook("opened", function() s.items:set({ { id = "a" }, { id = "b" }, { id = "c" } }) end)\n'
          'ui.action("top", "Top", function() end)\n'
          'ui.action("go", "Go", function(row) end, { takes = "row" })\n'
          'ui.action("moved", "Moved", function(row) end, { takes = "row" })\n'
          'ui.page("p", function()\n'
          '  ui.button("top")\n'
          '  ui.rows("items", { cur = "cur", changed = "moved" }, function() ui.link("go", { label = "{.id}" }) end)\n'
          'end)\n')
    ws, drv, frame, open_cart = _console(carts)
    seq = moy_log.next()
    open_cart(ws, "Moves")
    for _ in range(4):
        frame()
    for k in ("down", "down", "up"):
        drv.press(k)
        frame()
        frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    lines = [r[4].split("[trace] ", 1)[1] for r in moy_log.read(seq, 4000) if "[trace] " in r[4]]
    seen = [" ".join(l.split()[1:]) for l in lines if l.split()[1:3] in (["action", "moved"], ["state", "cur"])]
    assert seen == ["state cur '' -> 'a' (focus)",
                    "state cur 'a' -> 'b' (focus)", "action moved from rows 'items' cur moved",
                    "state cur 'b' -> 'a' (focus)", "action moved from rows 'items' cur moved"], lines


def test_a_canvas_in_a_table_is_handed_the_press_on_its_row(tmp_path):
    """A table's canvas child with pointer= is handed a press with the row it
    lands on (ev.row), in that row's coordinates, as a Python app's is."""
    from runtime import host_app
    from runtime.host import moy_log
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Taps", 'ui.app("Taps", { icon = "calc" })\n'
          'local s = ui.state { items = ui.model { key = "id", id = "" }, cur = ui.row_of("items"), got = "" }\n'
          'ui.hook("opened", function() s.items:set({ { id = "a" }, { id = "b" }, { id = "c" } }) end)\n'
          'ui.hook("press", function(ev) s.got = s.got .. ev.kind .. ":" .. ev.row.id .. "@" .. ev.y .. "," end,'
          ' { takes = "pointer" })\n'
          'ui.page("p", function()\n'
          '  ui.table("items", { cur = "cur", row = 30 }, function()\n'
          '    ui.canvas("cell", { pointer = "press", draw = function(x, y, w, h, row) end })\n'
          '  end)\n'
          'end)\n')
    ws, drv, frame, open_cart = _console(carts)
    seq = moy_log.next()
    open_cart(ws, "Taps")
    for _ in range(4):
        frame()
    for y in (50, 80):
        drv.click(40, y)
        frame()
        frame()
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    lines = [r[4].split("[trace] ", 1)[1] for r in moy_log.read(seq, 4000) if "[trace] " in r[4]]
    got = [l.split("-> ", 1)[1].split('"')[1] for l in lines if l.split()[1:3] == ["state", "got"]][-1]
    taps = [t.split(":")[1] for t in got.split(",") if t.startswith("down")]
    (r1, y1), (r2, y2) = [t.split("@") for t in taps]
    assert (y1, ord(r2) - ord(r1)) == (y2, 1), (got, lines)


def test_a_split_among_a_pages_rows_takes_its_cells_height_on_the_c_engine(tmp_path):
    """A split between a flowing page's rows stands where they flow, as tall
    as its tallest cell: the button after it is under the split's three
    rows (the first tap down the page that fires it is past them), as on a
    Python app's page."""
    from runtime import host_app
    from runtime.host import moy_log
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Flow", 'ui.app("Flow", { icon = "calc" })\n'
          'local s = ui.state { n = 0 }\n'
          'ui.action("after", "After", function() s.n = s.n + 1 end)\n'
          'ui.page("p", function()\n'
          '  ui.label("Before")\n'
          '  ui.split({ dir = "row", sizes = { 1, 1 } }, function()\n'
          '    ui.group("", function() ui.label("L1") ui.label("L2") ui.label("L3") end)\n'
          '    ui.group("", function() ui.label("R1") end)\n'
          '  end)\n'
          '  ui.button("after")\n'
          'end)\n')
    ws, drv, frame, open_cart = _console(carts)
    seq = moy_log.next()
    open_cart(ws, "Flow")
    for _ in range(4):
        frame()
    hit = None
    for y in range(30, 230, 6):
        drv.click(160, y)
        frame()
        frame()
        lines = [r[4] for r in moy_log.read(seq, 4000) if "[trace] " in r[4]]
        if any("action  after" in l or "action after" in l for l in lines):
            hit = y
            break
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    assert hit is not None and hit > 28 + 4 * 18, hit


def test_a_size_text_label_draws_as_measured_and_an_icon_alone_draws_on_the_c_engine(tmp_path):
    """From Lua: a size="text" label in a row draws the same pixels as with
    face="ui", the face it is measured in (it drew as a plain row once and
    cut its text), and a dim label with an icon and no words draws its icon."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    body = ('ui.app("%s", { icon = "calc" })\n'
            'ui.page("p", function()\n'
            '  ui.row(function()\n'
            '    ui.label("Sound effects for the long level", { size = "text"%s })\n'
            '    ui.label("12 notes", { tone = "dim" })\n'
            '  end)\n'
            '  ui.row(function() ui.label("", { tone = "dim"%s }) end)\n'
            'end)\n')
    cases = {"Plain": ("", ""), "Face": (', face = "ui"', ""), "Icon": ("", ', icon = "music"')}
    for name, (face, icon) in cases.items():
        _cart(carts, name, body % (name, face, icon))
    ws, drv, frame, open_cart = _console(carts)
    shots = {}
    for name in cases:
        open_cart(ws, name)
        for _ in range(4):
            frame()
        assert ws.run.player.cart_error is None, (name, ws.run.player.cart_error)
        shots[name] = bytes(drv.rgb888())[20 * 320 * 3:]   # below the bar, which carries the title
        ws.spine.exit_to_caller()
    assert shots["Plain"] == shots["Face"]
    assert shots["Icon"] != shots["Plain"]


def test_a_grids_spacing_is_an_int_and_a_word_stops_the_run_at_its_line(tmp_path):
    """A grid's and a split's gap= and pad= are ints at 1x, which the engine
    scales: from Lua an int draws, a spacing word stops the run at its line
    with N01."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    body = ('ui.app("%s", { icon = "calc" })\n'
            'ui.action("a", "Add", function() end)\nui.action("b", "Back", function() end)\n'
            'ui.page("p", function()\n'
            '  ui.grid({ cols = 2, rows = 1, gap = %s }, function() ui.button("a") ui.button("b") end)\n'
            'end)\n')
    for name, gap in (("Word", '"s"'), ("Int", "4")):
        _cart(carts, name, body % (name, gap))
    ws, drv, frame, open_cart = _console(carts)
    got = {}
    for name in ("Word", "Int"):
        open_cart(ws, name)
        for _ in range(4):
            frame()
        got[name] = ws.run.player.cart_error
        ws.spine.exit_to_caller()
    assert got["Int"] is None, got["Int"]
    assert got["Word"] and "error[N01] main.lua:5:" in got["Word"], got["Word"]


def test_a_page_pushed_over_itself_with_another_row_gives_the_first_its_row_back(tmp_path):
    """A page that takes a row (arg=) keeps the row it was pushed with: pushed
    over itself with another row, its Back shows the first row again, the
    page under writing its arg back as it shows."""
    from runtime import host_app
    from runtime.host import moy_log
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Rows", '''ui.app("Rows", { icon = "list" })
S = ui.state { items = ui.model { key = "id", id = "", name = "" }, sel = ui.row_of("items") }
ui.hook("opened", function() S.items:set({ { id = "a", name = "Apples" }, { id = "b", name = "Bread" } }) end)
ui.action("open", "Open", function(row) ui.push("details", row) end, { takes = "row" })
ui.action("other", "Other", function() ui.push("details", "b") end, { keys = { "o" } })
ui.page("shelf", function()
  ui.rows("items", function() ui.link("open", { label = "{.name}" }) end)
end, { title = "Shelf" })
ui.page("details", function()
  ui.label("{sel.name}")
  ui.button("other")
end, { title = "Details", arg = "sel" })
''')
    ws, drv, frame, open_cart = _console(carts)
    seq = moy_log.next()
    open_cart(ws, "Rows")
    for _ in range(4):
        frame()
    pl = ws.run.player

    def sel():
        assert pl.lua.exec("__R = S.sel and S.sel.id or ''", "test") is None
        return pl.lua.get_global("__R")
    drv.press("a")                      # the first row, Apples
    frame()
    frame()
    assert sel() == "a"
    drv.type_char(ord("o"))             # the same page over it, on Bread
    frame()
    frame()
    assert sel() == "b"
    assert pl.face.back()
    frame()
    frame()
    assert sel() == "a", "the page under shows the row it was pushed with"
    assert pl.face.back()
    frame()
    frame()
    assert pl.cart_error is None, pl.cart_error
    lines = [r[4].split("[trace] ", 1)[1] for r in moy_log.read(seq, 8000) if "[trace] " in r[4]]
    pages = [" ".join(l.split()[1:]) for l in lines if l.split()[1:2] == ["page"]]
    assert pages == ["page push page 2, opened from 'a/open'", "page push page 3, opened from 'other'",
                     "page back page 2, focus back to 'other'", "page back page 1, focus back to 'a/open'"], lines
    ws.spine.exit_to_caller()


def test_a_pages_shown_runs_at_its_push_and_at_the_back_onto_it(tmp_path):
    """A page's shown= runs when the page becomes the top page, by a push
    or by Back, after Back has written its arg= back and before the frame
    that draws it; not at the open, which is the opened hook's."""
    from runtime import host_app
    from runtime.host import moy_log
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Rows", '''ui.app("Rows", { icon = "list" })
S = ui.state { items = ui.model { key = "id", id = "", name = "" }, sel = ui.row_of("items") }
seen = {}
ui.hook("opened", function() S.items:set({ { id = "a", name = "Apples" }, { id = "b", name = "Bread" } }) end)
ui.hook("shelf_shown", function() seen[#seen + 1] = "shelf" end)
ui.hook("details_shown", function() seen[#seen + 1] = S.sel.id end)
ui.action("open", "Open", function(row) ui.push("details", row) end, { takes = "row" })
ui.action("other", "Other", function() ui.push("details", "b") end, { keys = { "o" } })
ui.page("shelf", function()
  ui.rows("items", function() ui.link("open", { label = "{.name}" }) end)
end, { title = "Shelf", shown = "shelf_shown" })
ui.page("details", function()
  ui.label("{sel.name}")
  ui.button("other")
end, { title = "Details", arg = "sel", shown = "details_shown" })
''')
    ws, drv, frame, open_cart = _console(carts)
    seq = moy_log.next()
    open_cart(ws, "Rows")
    for _ in range(4):
        frame()
    pl = ws.run.player

    def seen():
        assert pl.lua.exec("__R = table.concat(seen, ' ')", "test") is None
        return pl.lua.get_global("__R")
    assert seen() == ""
    drv.press("a")
    frame()
    frame()
    drv.type_char(ord("o"))
    frame()
    frame()
    assert seen() == "a b"
    assert pl.face.back()
    frame()
    frame()
    assert seen() == "a b a", "Back onto the page runs its shown= on the row it was pushed with"
    assert pl.face.back()
    frame()
    frame()
    assert seen() == "a b a shelf"
    assert pl.cart_error is None, pl.cart_error
    lines = [r[4].split("[trace] ", 1)[1] for r in moy_log.read(seq, 8000) if "[trace] " in r[4]]
    shown = [" ".join(l.split()[1:]) for l in lines if "the page shown" in l]
    assert shown == ["action details_shown from the page shown"] * 3 + ["action shelf_shown from the page shown"], lines
    ws.spine.exit_to_caller()


def test_a_pages_shown_names_an_action_that_takes_nothing(tmp_path):
    """shown= is checked where the pages are: a name no action has is A01."""
    from runtime import host_app
    carts = str(tmp_path / "carts")
    host_app.moy_carts.ensure_dirs(carts)
    _cart(carts, "Shown", '''ui.app("Shown", { icon = "list" })
ui.page("home", function() ui.label("Hi") end, { title = "Home", shown = "nothing_here" })
''')
    ws, drv, frame, open_cart = _console(carts)
    open_cart(ws, "Shown")
    for _ in range(3):
        frame()
    err = ws.run.player.cart_error
    assert err and "error[A01]" in err and "nothing_here" in err, err
    ws.spine.exit_to_caller()
