"""The Editor's theme mode (docs/history/look_2026-10.md step 33, GAPS 56;
runtime/editors/theme_editor.py).

* The door: Appearance's last row, Edit theme…, makes `custom` from a seed
  and opens it in the Editor on Config; Done (the bar's ‹, Esc, B) comes back.
* Config is custom's theme.json, its saves the look's (no journal), and
  the mode's one tab: the console edits no icon.
* A package's own tiles (`icons.pixel_slots`) still load: the C loader
  reads the slots and the flattening keeps them.
* EDIT ICONS and the user's icon-sheet override are gone.
* The desk shows Config as the theme workspace's one pane.
"""

import json
from pathlib import Path

import runtime  # noqa: F401  (registers the host's moy_ui)
import moy_ui
from runtime import iconsets, theme_editor, ui_draw
from ws_helpers import build_desktop_ws, build_ws



def _open(ws):
    assert ws.look.edit_file()
    ws.input.begin_frame()
    ws.frame(1 / 30)
    doc = ws.editor_app.theme
    assert doc is not None and ws.wm.top_is("menu")
    return doc


def _frames(ws, n=2):
    for _ in range(n):
        ws.input.begin_frame()
        ws.frame(1 / 30)


def _package(ws):
    return Path(ws.carts_root) / "custom.moy"


def test_the_door_opens_a_copy_on_config_and_done_comes_back(tmp_path):
    ws = build_ws(tmp_path)
    ws.spine.open_app(ws.app("appearance"))
    _frames(ws)
    doc = _open(ws)
    assert ws.look.theme_name == "custom" and ws.menu_view == "theme_config"
    assert doc.note == "Moy is built in: this is your copy, custom"
    assert doc.status() == doc.note
    assert json.loads(doc.ed.text()) == json.loads(ws.look.file_text())
    assert ws.editor_app.project is None and ws.editor is doc.ed
    ws.editor_app.close_theme()
    assert ws.editor_app.theme is None and ws.editor is None
    assert ws.wm.top_kind() == "appearance"


def test_delete_in_config_takes_the_character_after_the_caret(tmp_path):
    from runtime import host_app
    ws = build_ws(tmp_path)
    drv = host_app.ConsoleDriver(ws)
    ws.spine.open_app(ws.app("appearance"))
    drv.frame(1 / 30)
    doc = _open(ws)
    ed = doc.ed
    ed.row, ed.col, ed.sel = 0, 0, None
    line = ed.lines[0]
    for code in (0x7F, 0x08):
        drv.key_down(code)
        drv.frame(1 / 30)
        drv.key_up(code)
        drv.frame(1 / 30)
    assert ed.lines[0] == line[1:] and (ed.row, ed.col) == (0, 0)


def test_esc_and_the_bars_back_are_done(tmp_path):
    from runtime import host_app
    ws = build_ws(tmp_path)
    drv = host_app.ConsoleDriver(ws)
    ws.spine.open_app(ws.app("appearance"))
    drv.frame(1 / 30)
    _open(ws)
    drv.key_down(27)
    drv.frame(1 / 30)
    drv.key_up(27)
    drv.frame(1 / 30)
    assert ws.editor_app.theme is None and ws.wm.top_kind() == "appearance"
    _open(ws)
    drv.frame(1 / 30)
    bl = ws.bar_layer
    bar, zone = bl.cell("menu", "zone")
    zx, zy = bar[1][0] + zone[0], bar[1][1] + zone[1]
    drv.click(zx + 6, zy + zone[3] // 2)
    drv.frame(1 / 30)
    drv.frame(1 / 30)
    assert ws.editor_app.theme is None


def test_config_saves_through_the_look_and_refuses_softly(tmp_path):
    ws = build_ws(tmp_path)
    doc = _open(ws)
    d = json.loads(doc.ed.text())
    d["colors"]["dark"]["panel"] = 0
    doc.ed.set_text(json.dumps(d, indent=2))
    doc.ed.dirty = True
    assert doc.save_config(soft=True) == (True, "")
    assert json.loads((_package(ws) / "theme.json").read_text())["colors"]["dark"]["panel"] == 0
    doc.ed.set_text("{ not json")
    doc.ed.dirty = True
    ok, badge = doc.save_config(soft=True)
    assert not ok and badge.startswith("INVALID")
    assert "INVALID" in doc.status()


def test_the_loader_reads_and_writes_pixel_slots():
    src = json.dumps({"format": 2, "name": "px", "look": {"icons": {
        "pixel_slots": ["play", "home", "nope", "edit", "secret"]}}}).encode()
    got = moy_ui.theme_resolve(src)
    assert got[0] == 0 and got[1] & 4, "the name of no slot is dropped and noted"
    rc, out = ui_draw.theme_custom(src, None, None)
    assert rc == 0
    # in slot order, an alias as its slot
    assert json.loads(out)["look"]["icons"]["pixel_slots"] == ["home", "play", "pencil",
                                                               "secret"]
    assert moy_ui.theme_install(src)[0] == 0
    try:
        names = moy_ui.theme_look_fields()[0]
        look = moy_ui.theme_look("px", False)
        flags = iconsets.pixel_slots((dict(zip(names, look[0])),))
        assert [i for i in range(len(flags)) if flags[i]] == [
            iconsets.SLOT[n] for n in ("home", "play", "pencil", "secret")]
    finally:
        moy_ui.theme_uninstall()


def test_the_sheet_cap_holds_a_tile_for_every_slot():
    caps = ui_draw.sheet_caps()
    assert caps[2] >= 16 * iconsets.PIXEL_ROWS
    sheet = iconsets.blank_sheet()
    assert ui_draw.sheet_check(sheet.to_hex().encode(), caps[2])[0] == 0


def test_settings_has_no_edit_icons_and_the_store_no_override(tmp_path):
    from runtime import moy_carts, moy_sync
    ws = build_ws(tmp_path)
    assert "icons" not in [r[0] for r in ws.settings_layer._SETTINGS_ROWS]
    assert not hasattr(moy_carts, "load_system_icons")
    assert "system_icons.moygfx" not in moy_sync.SYSTEM_FILES


def test_the_tdeck_hints_name_its_own_keys(tmp_path):
    ui_draw.input_kind("tdeck")
    try:
        # Config's caret takes the ball and its letters type: Mic's menu,
        # opening on Home, is the way out
        assert theme_editor._hints_for() == ("menu", "Home")
    finally:
        ui_draw.input_kind("keys")


def test_the_desk_shows_config_alone(tmp_path):
    ws = build_desktop_ws(tmp_path, panel_diagonal_in=7.0, font_scale=1)
    ws.home.open_desk()
    ws.spine.open_app(ws.app("appearance"))
    _frames(ws)
    _open(ws)
    _frames(ws)
    desk = ws.editor_desk
    assert desk.active() and desk.key == "theme"
    tabs = [desk.tab_of(p) for p, _r, _path in desk.panes()]
    assert tabs == ["theme_config"]
    assert ws.menu_view == "theme_config"
    assert not desk.switch("code"), "a theme has no cart workspace"
    # the window's X commits what Config holds
    doc = ws.editor_app.theme
    d = json.loads(doc.ed.text())
    d["colors"]["dark"]["panel"] = 0
    doc.ed.set_text(json.dumps(d, indent=2))
    doc.ed.dirty = True
    ws.wm.close_window_kind("menu")
    d = json.loads((_package(ws) / "theme.json").read_text())
    assert d["colors"]["dark"]["panel"] == 0
