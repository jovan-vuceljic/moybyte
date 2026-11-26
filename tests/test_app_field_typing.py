"""A field an app's page focuses is a stop until Enter opens its edit; while
the edit is open the field takes the keyboard (the engine's typing, applied
through the input policy): the console is in text mode, so the T-Deck's W A
S D type letters and press no direction (native/moy_input/moy_kbd.c, THE
MOVE KEYS), and the trackball moves the caret. Enter ends the edit, and the
move keys step the page again. One rule for a tree app on every runtime,
Python's and Lua's; a cart's own `textmode()` still holds when no field is
focused. The trackball steps an app's page past a field, as it does every
surface that takes the keys (`Workstation.ball_steps`), and does not show
the cursor. Mic (the T-Deck's cancel), Esc and B end a field's edit: the
field gets back the text the edit began from and focus stays on it (the
engine's cancel, `face.cancel`); with no edit open, Mic stays the console's
key."""

import json
from pathlib import Path

from runtime import host_app, ui_draw
from runtime.moy_input import InputTable
from ws_helpers import build_ws, select_on_home

import pytest

DT = 1.0 / 30.0

LUA_APP = """
ui.app("Field App", { icon = "calc" })
S = ui.state { name = "", saved = 0 }
ui.action("save", "Save", function() S.saved = S.saved + 1 end)
ui.page("channel", function()
  ui.field("name", { label = "Name", max = 11, focus = true })
  ui.button("save")
end, { title = "Channel" })
"""

PY_APP = """
s = ui.state(name="", saved=0)
ui.app("Field App", icon="calc")


def save():
    s.saved += 1


ui.action("save", "Save", save)


def build():
    with ui.page("Channel"):
        ui.field("Name", "name", max=11, focus=True)
        ui.button("save")
"""

LUA_EDIT = """
ui.app("Edit App", { icon = "calc" })
S = ui.state { name = "Srbija" }
ui.action("top", "Top", function() end)
ui.action("save", "Save", function() end)
ui.page("channel", function()
  ui.button("top")
  ui.field("name", { label = "Name", max = 11, focus = true })
  ui.button("save")
end, { title = "Channel" })
"""

PY_EDIT = """
s = ui.state(name="Srbija")
ui.app("Edit App", icon="calc")


def nothing():
    pass


ui.action("top", "Top", nothing)
ui.action("save", "Save", nothing)


def build():
    with ui.page("Channel"):
        ui.button("top")
        ui.field("Name", "name", max=11, focus=True)
        ui.button("save")
"""

LUA_TWO = """
ui.app("Two Fields", { icon = "calc" })
S = ui.state { first = "aa", second = "bb" }
ui.page("radio", function()
  ui.field("first", { label = "First", max = 11 })
  ui.field("second", { label = "Second", max = 11, focus = true })
end, { title = "Radio" })
"""

LUA_TEXTMODE = """
function _init() textmode(true) end
function _draw() cls(0) end
"""


@pytest.fixture(autouse=True)
def _tdeck_keys():
    was = ui_draw.input_kind()
    ui_draw.input_kind("tdeck")
    yield
    ui_draw.input_kind(was)


def _write(carts, name, src, runtime, tree=True):
    d = carts / (name + ".moy")
    d.mkdir(parents=True, exist_ok=True)
    main = "main.lua" if runtime == "lua" else "main.py"
    man = {"format": "moy-1", "title": name, "canvas": "320x240", "runtime": runtime, "main": main,
           "moybyte": {"type": "app", "permissions": ["graphics"]}}
    if tree:
        man["extensions"] = ["moybyte.uitree"]
    (d / "manifest.json").write_text(json.dumps(man))
    (d / main).write_text(src)
    (d / "config.json").write_text("{}")


def _open(tmp_path, name, src, runtime, tree=True):
    _write(tmp_path / "carts", name, src, runtime, tree)
    ws = build_ws(tmp_path)
    drv = host_app.ConsoleDriver(ws)
    assert select_on_home(ws, name) is not None
    ws.open()
    for _ in range(3):
        drv.frame(DT)
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    assert ws.screen == "desktop"
    return ws, drv


def _lua_read(ws, expr):
    lua = ws.run.player.lua
    assert lua.exec("__READ = " + expr, "test") is None
    return lua.get_global("__READ")


def _focus(ws):
    if ws.run.player.lua is not None:
        return _lua_read(ws, "ui.sys.focus")
    return ws.run.player.tree.engine.focus_key


def _value(ws, name):
    if ws.run.player.lua is not None:
        return _lua_read(ws, "S." + name)
    return getattr(ws.run.player.ns["s"], name)


def _name(ws):
    return _value(ws, "name")


def _type(drv, text):
    for ch in text:
        drv.type_char(ord(ch))
        drv.frame(DT)
    drv.frame(DT)


def _mic(ws, drv):
    """The T-Deck's Mic let go, as console_input answers it (the host's
    table has no `start`): a field's cancel, else the console's key."""
    if not ws.input_policy.cancel():
        ws.system_key()
    for _ in range(3):
        drv.frame(DT)


def _step(drv, button):
    drv.press(button)
    for _ in range(3):
        drv.frame(DT)


def _edit(drv):
    """Enter on the focused field: its edit opens."""
    _step(drv, "run")


def _roll(ws, drv, dx, dy, notches=1):
    """The trackball rolled `notches` steps (BALL_STEP pulses each, one a
    frame)."""
    for _ in range(notches):
        ws._ball_axis_at -= ws.router.BALL_ROLLING_MS + 1
        drv.pan(dx, dy)
        for _ in range(ws.router.BALL_STEP):
            drv.frame(DT)
        drv.pan(0, 0)
        for _ in range(2):
            drv.frame(DT)


@pytest.mark.parametrize("runtime", ["lua", "python"])
def test_a_field_holds_the_keyboard_in_text_mode_while_its_edit_is_open(tmp_path, runtime):
    ws, drv = _open(tmp_path, "Field App", LUA_APP if runtime == "lua" else PY_APP, runtime)
    assert _focus(ws) == "name"
    assert not ws.input.text_mode, "a focused field is a stop: the move keys step past it"
    _step(drv, "down")
    assert _focus(ws) == "save"
    _step(drv, "up")
    assert _focus(ws) == "name" and not ws.input.text_mode
    _edit(drv)
    assert ws.input.text_mode, "Enter opens its edit: W A S D are letters there"
    for _ in range(10):
        drv.frame(DT)
    assert ws.input.text_mode, "a page drawn on change keeps its field's text mode"
    _step(drv, "run")
    assert _focus(ws) == "name" and not ws.input.text_mode, "Enter ends the edit, focus stays"


@pytest.mark.parametrize("runtime", ["lua", "python"])
def test_a_field_types_the_keys_only_while_its_edit_is_open(tmp_path, runtime):
    ws, drv = _open(tmp_path, "Field App", LUA_APP if runtime == "lua" else PY_APP, runtime)
    _type(drv, "q")
    assert _name(ws) == "", "a key on a field with no edit open types nothing"
    _edit(drv)
    _type(drv, "wasd")
    assert _name(ws) == "wasd"
    assert _focus(ws) == "name"


@pytest.mark.parametrize("runtime", ["lua", "python"])
def test_the_trackball_moves_the_caret_in_an_edit(tmp_path, runtime):
    """Enter the field, roll left twice, type x: the x lands two characters
    back. A roll up goes to the line's start, a press is Enter."""
    ws, drv = _open(tmp_path, "Field App", LUA_APP if runtime == "lua" else PY_APP, runtime)
    _edit(drv)
    _type(drv, "abcd")
    _roll(ws, drv, -1, 0, 2)
    _type(drv, "x")
    assert _name(ws) == "abxcd"
    _roll(ws, drv, 0, -1)
    _type(drv, "y")
    assert _name(ws) == "yabxcd"
    assert _focus(ws) == "name", "in an edit the roll moves the caret, not focus"
    drv.ball_click()
    for _ in range(3):
        drv.frame(DT)
    assert not ws.input.text_mode, "the trackball's press ends the edit as Enter does"
    _roll(ws, drv, 0, 1)
    assert _focus(ws) == "save", "with the edit ended the roll steps past the field"


@pytest.mark.parametrize("runtime", ["lua", "python"])
def test_the_pads_d_pad_moves_the_caret_in_an_edit(tmp_path, runtime):
    ws, drv = _open(tmp_path, "Field App", LUA_APP if runtime == "lua" else PY_APP, runtime)
    _step(drv, "a")
    assert ws.input.text_mode, "A opens the edit"
    _type(drv, "abc")
    _step(drv, "left")
    _step(drv, "left")
    _type(drv, "x")
    assert _name(ws) == "axbc"
    _step(drv, "down")
    _type(drv, "y")
    assert _name(ws) == "axbcy", "down goes to the end of a one-line field"
    assert _focus(ws) == "name"


def test_a_lua_carts_textmode_reaches_the_keyboard(tmp_path):
    ws, drv = _open(tmp_path, "Typing Cart", LUA_TEXTMODE, "lua", tree=False)
    assert ws.input.text_mode, "textmode(true) from a Lua cart is the console's text mode"


@pytest.mark.parametrize("runtime", ["lua", "python"])
def test_the_trackball_steps_an_apps_page_and_shows_no_cursor(tmp_path, runtime):
    ws, drv = _open(tmp_path, "Field App", LUA_APP if runtime == "lua" else PY_APP, runtime)
    assert ws.input_policy.ball_steps(), "an app's page takes the trackball as its W A S D"
    ws._ball_axis_at -= ws.router.BALL_ROLLING_MS + 1
    drv.pan(0, 1)
    for _ in range(2):
        drv.frame(DT)
    drv.pan(0, 0)
    for _ in range(3):
        drv.frame(DT)
    assert _focus(ws) == "save", "a roll down is a step down the page"
    assert not ws.pointer.visible


@pytest.mark.parametrize("runtime", ["lua", "python"])
def test_mic_cancels_an_apps_field_edit(tmp_path, runtime):
    ws, drv = _open(tmp_path, "Edit App", LUA_EDIT if runtime == "lua" else PY_EDIT, runtime)
    assert _focus(ws) == "name"
    _edit(drv)
    _type(drv, "xy")
    assert _name(ws) == "Srbijaxy"
    _mic(ws, drv)
    assert _name(ws) == "Srbija", "Mic gives the field back the text the edit began from"
    assert _focus(ws) == "name", "and ends the edit, focus staying on the field"
    assert not ws.input.text_mode
    assert not ws.sysmenu.open, "a cancel is not the console's key"


@pytest.mark.parametrize("runtime", ["lua", "python"])
def test_mic_on_a_field_with_no_edit_opens_the_menu(tmp_path, runtime):
    ws, drv = _open(tmp_path, "Edit App", LUA_EDIT if runtime == "lua" else PY_EDIT, runtime)
    assert _focus(ws) == "name"
    assert not ws.run.player.face.cancel()
    _edit(drv)
    _type(drv, "x")
    drv.type_char(8)                     # typed and deleted: the edit ends with its text
    for _ in range(2):
        drv.frame(DT)
    _mic(ws, drv)
    assert not ws.sysmenu.open and not ws.input.text_mode, "Mic ends an open edit"
    assert _name(ws) == "Srbija"
    _mic(ws, drv)
    assert ws.sysmenu.open, "with no edit open Mic is the console's key"
    assert _name(ws) == "Srbija"


@pytest.mark.parametrize("runtime", ["lua", "python"])
def test_enter_keeps_what_it_confirmed(tmp_path, runtime):
    ws, drv = _open(tmp_path, "Edit App", LUA_EDIT if runtime == "lua" else PY_EDIT, runtime)
    _edit(drv)
    _type(drv, "1")
    drv.type_char(13)
    for _ in range(2):
        drv.frame(DT)
    assert _name(ws) == "Srbija1"
    assert not ws.run.player.face.cancel(), "Enter ends the edit: nothing to give back"
    _edit(drv)
    _type(drv, "2")
    _mic(ws, drv)
    assert _name(ws) == "Srbija1"


def _stop(ws):
    """One frame of a board's input with a keyboard's Esc (`stop`) pressed,
    through the console's router."""
    was = ws.input
    i = InputTable()
    i.source("kbd").set_button("stop", True)
    i.begin_frame()
    ws.input = i
    try:
        ws.router.handle_input()
    finally:
        ws.input = was


@pytest.mark.parametrize("how", ["escape", "stop"])
@pytest.mark.parametrize("runtime", ["lua", "python"])
def test_esc_cancels_a_field_edit_before_it_goes_back(tmp_path, how, runtime):
    ws, drv = _open(tmp_path, "Edit App", LUA_EDIT if runtime == "lua" else PY_EDIT, runtime)
    _edit(drv)
    _type(drv, "xy")
    assert ws.run.player.face.has_page(), "an edit in progress is the app's to step out of"
    if how == "escape":
        drv.escape()
    else:
        _stop(ws)
    for _ in range(3):
        drv.frame(DT)
    assert _name(ws) == "Srbija"
    assert _focus(ws) == "name"
    assert ws.screen == "desktop", "the first Esc cancels the edit, the app stays"


def test_each_fields_cancel_gives_it_its_own_text(tmp_path):
    """A cancelled field gets its text back; the field above, edited next,
    keeps its own, and an edit there cancels to that."""
    ws, drv = _open(tmp_path, "Two Fields", LUA_TWO, "lua")
    assert _focus(ws) == "second"
    _edit(drv)
    _type(drv, "x")
    _mic(ws, drv)
    assert (_value(ws, "first"), _value(ws, "second")) == ("aa", "bb")
    _step(drv, "up")
    assert _focus(ws) == "first" and not ws.input.text_mode
    _edit(drv)
    _type(drv, "y")
    assert _value(ws, "first") == "aay"
    _mic(ws, drv)
    assert (_value(ws, "first"), _value(ws, "second")) == ("aa", "bb")
    assert not ws.sysmenu.open




# -- the shell's own apps ---------------------------------------------------------
#
# A shell app's field is drawn through its AppHost's context, so Mic reaches it
# there (`InputPolicy.cancel` asks `ui_draw.app_cancel` where the app has
# no `cancel` of its own). Each row opens the app's field on a draft and
# names where the app keeps it.

def _files_rename(ws):
    app = ws.app("files")
    app.open_place("documents")
    app._act("NAME", "notes")
    return lambda: app.rename_text


def _appearance_name(ws):
    app = ws.app("appearance")
    app.open_name()
    app.name_text = "bubble"
    app._damage.all()
    return lambda: app.name_text


def _storybook_rename(ws):
    app = ws.app("storybook")
    app.typed = "Mine"
    app.asking = "rename"
    app._damage.all()
    return lambda: app.typed


def _myart_rename(ws):
    app = ws.app("myart")
    app._verb("rename", "kite")
    return lambda: app.engine.s._v["name"]


SHELL_FIELDS = {"files": _files_rename, "appearance": _appearance_name,
                "storybook": _storybook_rename, "myart": _myart_rename}


@pytest.mark.parametrize("app_id", sorted(SHELL_FIELDS))
def test_mic_cancels_a_shell_apps_field(tmp_path, app_id):
    carts = str(tmp_path / "carts")
    from runtime import moy_carts
    moy_carts.save_file("docs", "notes", "x", carts)
    moy_carts.save_file("drawings", "kite",
                        moy_carts.encode_moyimg(8, 8, bytes((14,)) * 64), carts)
    ws = host_app.build_workstation(carts)
    drv = host_app.ConsoleDriver(ws)
    ws.spine.open_app(ws.app(app_id))
    for _ in range(3):
        drv.frame(DT)
    draft = SHELL_FIELDS[app_id](ws)
    for _ in range(3):
        drv.frame(DT)
    was = draft()
    _type(drv, "xy")
    assert draft() == was + "xy", "the field types each key once"
    _mic(ws, drv)
    assert draft() == was, "Mic gives the field back the text the edit began from"
    assert not ws.sysmenu.open, "a cancel is not the console's key"
    assert ws.wm.top_kind() == app_id, "and the app stays"


# -- a cart app: Notes ------------------------------------------------------------
#
# Notes' list and its new-note dialog are an app's page like any other: the
# keyboard is in text mode while the dialog's field holds focus, and back in
# game mode on the list and after Mic cancels the field.

def test_notes_holds_text_mode_only_while_its_field_does(tmp_path):
    ws = build_ws(tmp_path)
    drv = host_app.ConsoleDriver(ws)
    assert select_on_home(ws, "Notes") is not None
    ws.open()
    for _ in range(3):
        drv.frame(DT)
    st = ws.run.player.tree.engine.s._v      # the page's state
    assert ws.run.player.ns["ed"] is None and ws.screen == "desktop"
    assert not ws.input.text_mode, "the list steps with the move keys"
    _type(drv, "n")
    assert st["asking"] == "new", "N opens the new-note dialog"
    assert ws.input.text_mode, "its field types"
    _type(drv, "ab")
    assert st["typed"] == "ab"
    _mic(ws, drv)
    assert st["asking"] == "none" or st["typed"] == "", "Mic gives back the empty draft"
    assert not ws.input.text_mode, "off the field the keyboard is the page's again"
    assert not ws.sysmenu.open, "a cancel is not the console's key"


def test_a_paste_from_outside_lands_in_a_note_whole(tmp_path):
    """A paste from outside the console (a browser page's clipboard,
    ConsoleDriver.paste) reaches a note's editor through the console's
    clipboard and its Paste: its lines whole, in one frame."""
    ws = build_ws(tmp_path)
    drv = host_app.ConsoleDriver(ws)
    assert select_on_home(ws, "Notes") is not None
    ws.open()
    for _ in range(3):
        drv.frame(DT)
    _type(drv, "n")
    _type(drv, "pasted")
    _type(drv, "\r")
    for _ in range(3):
        drv.frame(DT)
    ed = ws.run.player.ns["ed"]
    assert ed is not None and ws.input.text_mode
    drv.paste("first line\nsecond line\n")
    for _ in range(2):
        drv.frame(DT)
    assert ed.text() == "first line\nsecond line\n"


# -- a uitree app -------------------------------------------------------------------
#
# A uitree App's page draws through its engine's host, which it answers as its
# `page_host()` (runtime/shell/layers.py): the input policy reads its focused
# field there, as it reads an AppHost app's, while Back stays the engine's.

def test_a_uitree_apps_field_holds_text_mode_and_mic_cancels_its_edit(tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))
    import uitree_counter as C
    import uitree_parity as P
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    drv = host_app.ConsoleDriver(ws)
    app = P.host(ws, C.layer())
    for _ in range(3):
        drv.frame(DT)
    policy = ws.input_policy
    assert not policy.typing() and not ws.input.text_mode, "the page's first stop is no field"
    for _ in range(6):
        if app.engine.focus_key == "name":
            break
        _step(drv, "down")
    assert not policy.typing(), "a focused field is a stop until Enter"
    _edit(drv)
    assert policy.typing() and ws.input.text_mode, "an open edit types: W A S D are letters there"
    assert app.engine.has_page() is True, "an open edit is the app's to step out of"
    _type(drv, "xy")
    assert C.s.name == "xy", app.engine.trace_text()
    _mic(ws, drv)
    assert C.s.name == "", "Mic gives the field back the text the edit began from"
    assert not policy.typing() and not ws.input.text_mode, "and ends the edit"
    assert not ws.sysmenu.open, "a cancel is not the console's key"
    assert ws.wm.top_kind() == app.id, "and the app stays"
