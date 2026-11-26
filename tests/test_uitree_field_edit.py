"""A field's edit and its two words (docs/app_api_v1.md §7.3, owner
2026-11-24): a focused field is a stop until Enter, A, a tap or a click
opens its edit; `edit="open"` opens it as focus comes onto the field and keeps
it open past Enter (a page that exists for typing), and `keys="number"` names the on-screen
keyboard's layout for it (#239), which draws nothing. Each front takes,
checks and stores both: Python, Lua and a compiled app's (the one C store
under all three). The keys every input sends a field are
tests/test_input_matrix.py's; the T-Deck's W A S D across a field are
tests/test_tdeck_move_keys.py's."""

import os
import sys

import pytest

from test_app_field_typing import DT, _edit, _focus, _lua_read, _name, _open, _roll, _type

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

LUA_OPEN = """
ui.app("Open App", { icon = "calc" })
S = ui.state { name = "" }
ui.page("search", function()
  ui.field("name", { label = "Find", max = 11, edit = "open", keys = "number" })
end, { title = "Search" })
"""

PY_OPEN = """
s = ui.state(name="")
ui.app("Open App", icon="calc")


def build():
    with ui.page("Search"):
        ui.field("Find", "name", max=11, edit="open", keys="number")
"""


def _dump(ws):
    if ws.run.player.lua is not None:
        return _lua_read(ws, "ui._dump()")
    return ws.run.player.tree.engine.dump()


@pytest.mark.parametrize("runtime", ["lua", "python"])
def test_an_open_field_opens_its_edit_as_focus_comes_onto_it(tmp_path, runtime):
    ws, drv = _open(tmp_path, "Open App", LUA_OPEN if runtime == "lua" else PY_OPEN, runtime)
    assert _focus(ws) == "name"
    assert ws.input.text_mode, "edit=\"open\": the page's field types at once"
    _type(drv, "12")
    assert _name(ws) == "12"
    drv.type_char(13)
    for _ in range(2):
        drv.frame(DT)
    assert ws.input.text_mode and _focus(ws) == "name", "Enter commits with the edit going on"
    _type(drv, "3")
    assert _name(ws) == "123"
    drv.escape()
    for _ in range(3):
        drv.frame(DT)
    assert _name(ws) == "12", "Esc gives back what Enter did not commit"
    assert not ws.input.text_mode and _focus(ws) == "name", "and ends the edit, focus staying"
    _edit(drv)
    assert ws.input.text_mode


@pytest.mark.parametrize("runtime", ["lua", "python"])
def test_edit_and_keys_are_stored_in_the_store(tmp_path, runtime):
    ws, _drv = _open(tmp_path, "Open App", LUA_OPEN if runtime == "lua" else PY_OPEN, runtime)
    line = next(ln for ln in _dump(ws).splitlines() if " field " in ln)
    assert "edit='open'" in line and "keys='number'" in line, line


PAGE = ("import uitree as ui\n"
        "s = ui.state(t=\"\")\n"
        "def build():\n"
        "    with ui.page(\"P\"):\n"
        "        ui.field(\"T\", \"t\", %s)\n")


@pytest.mark.parametrize("prop, ok", [("edit=\"open\", keys=\"number\"", True), ("edit=\"stop\", keys=\"text\"", True),
                                      ("edit=\"always\"", False), ("keys=\"qwerty\"", False)])
def test_python_a_field_takes_the_words_and_refuses_another(prop, ok, tmp_path):
    import uitree_check
    (tmp_path / "f.py").write_text(PAGE % prop)
    got = [e.code for e in uitree_check.check(str(tmp_path / "f.py")).errors]
    assert got == ([] if ok else ["N01"]), got


def test_compiled_a_field_takes_the_words_and_refuses_another():
    from test_uitree_wasm import Rows, PAGE as PG, E_CHECK
    import uitree_c
    r = Rows()
    try:
        r.build("1 page")
        page = r.node(PG, "page", -1)
        f = r.node(uitree_c._KINDS["field"], "f", page)
        assert r.prop(f, "edit", "open") >= 0
        assert r.prop(f, "keys", "number") >= 0
        assert r.prop(f, "keys", "qwerty") == E_CHECK
        assert "N01" in r.read("error", cap=400)[1]
        assert r.prop(f, "edit", "always") == E_CHECK
    finally:
        r.close()


def test_compiled_the_trackball_moves_the_caret_in_an_edit(tmp_path, monkeypatch, built):
    """Enter a compiled app's field, type, roll left twice, type x: the x
    lands two characters back."""
    from test_input_matrix import Rig, _needs_build
    _needs_build(built, "wasm_app", "field")
    rig = Rig(tmp_path, "wasm_app", "field", monkeypatch, built)
    try:
        rig.desk_key(13)
        for ch in "abcd":
            rig.desk_type(ch)
        assert rig.state()["t"] == "abcd"
        _roll(rig.ws, rig.drv, -1, 0, 2)
        rig.desk_type("x")
        assert rig.state() == {"t": "abxcd", "typing": 1}
    finally:
        rig.ws.spine.exit()


from test_input_matrix import built  # noqa: E402,F401 -- the compiled pages, built once


LUA_NAME = LUA_OPEN.replace('keys = "number"', 'keys = "name"')
PY_NAME = PY_OPEN.replace('keys="number"', 'keys="name"')


@pytest.mark.parametrize("runtime", ["lua", "python"])
def test_a_name_field_refuses_what_a_name_cannot_hold_as_it_is_typed(tmp_path, runtime):
    """keys="name" (issue 270): a capital lands as its small letter and a
    space as -, a - or _ first and anything outside a-z 0-9 _ - never land,
    so nothing typed flashes in and is taken back."""
    ws, drv = _open(tmp_path, "Open App", LUA_NAME if runtime == "lua" else PY_NAME, runtime)
    _type(drv, "-_My Th!eme?")
    assert _name(ws) == "my-theme"
