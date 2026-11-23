"""The handheld Editor's Map, Scene, Music and Blocks tabs on the public UI
API (docs/history/look_2026-10.md step 30; docs/media/look_2026-10/EDITOR_LAYOUT.md's
`*-editor` pictures): each tab's pages driven through the host's pointer
and keys, and a settled tab painting nothing."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from runtime import host_app                # noqa: E402
from ws_helpers import settle_badges  # noqa: E402

DT = 1 / 30


@pytest.fixture
def hh(tmp_path):
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    drv = host_app.ConsoleDriver(ws)
    cart = next(c for c in ws.carts.all if c.get("title") == "Star Catcher")
    ws.open_in_editor(cart)
    return ws, drv


def _open(hh, tab):
    ws, drv = hh
    ws.text.set_menu_view(tab)
    ws.pointer.visible = False
    settle_badges(ws)
    ws.toast_until = 0
    for _ in range(3):
        drv.frame(DT)
    return ws, drv


def _tap(drv, rect, dx=None):
    x, y, w, h = rect
    drv.click(x + (w // 2 if dx is None else dx), y + h // 2)
    for _ in range(3):
        drv.frame(DT)


def _settles(ws, drv):
    for _ in range(4):
        drv.frame(DT)
    drawn = ws.frame_state.frames_drawn
    for _ in range(8):
        drv.frame(DT)
    return ws.frame_state.frames_drawn == drawn


# -- Music ------------------------------------------------------------------------------

def _music(hh):
    ws, drv = _open(hh, "music")
    mu = ws.music_ui
    if mu.musicedit is None:
        pytest.skip("no sound bank on this build")
    return ws, drv, mu, mu.page


def test_the_music_pad_edits_the_step_under_the_cursor(hh):
    ws, drv, mu, page = _music(hh)
    me = mu.musicedit
    before = me.cur_step()[0]
    _tap(drv, page.rect_of("higher"))
    assert me.cur_step()[0] == before + 1
    n = me.step_count()
    _tap(drv, page.rect_of("add"))
    assert me.step_count() == n + 1
    from runtime.music_editor_ui import ROW
    x, y, w, _h = page.rect_of("steps")
    _tap(drv, (x, y, w, ROW), dx=16)   # the steps' first row, as they show at the top
    assert me.step == 0


def test_a_finger_drag_scrolls_the_steps(hh):
    """A press held and dragged up the steps scrolls them (the page's host
    reads the console's pointer as held), and moves no cursor."""
    ws, drv, mu, page = _music(hh)
    me = mu.musicedit
    while me.step_count() * 17 < 2 * page.rect_of("steps")[3]:
        me.add_step()
    me.step = 0
    for _ in range(3):
        ws.mark_dirty()
        drv.frame(DT)
    step = me.step
    top = []
    draw = mu.draw_row
    mu.draw_row = lambda cv, i, x, y, w, h: (top.append(i), draw(cv, i, x, y, w, h))
    x, y, w, h = page.rect_of("steps")
    x, y = x + w // 2, y + h - 4
    drv.touch(x, y)
    drv.frame(DT)
    for _ in range(12):
        y -= 8
        drv.touch_drag(x, y)
        drv.frame(DT)
    drv.touch_up()
    top.clear()
    ws.mark_dirty()
    drv.frame(DT)
    assert min(top) > 0, "the steps did not scroll under the finger"
    assert me.step == step, "a drag moved the cursor"


def test_the_music_tabs_chevrons_and_hear(hh):
    ws, drv, mu, page = _music(hh)
    me = mu.musicedit
    x, y, w, h = page.rect_of("stepper#1")          # the stepper's forward half
    _tap(drv, (x + w // 2, y, w - w // 2, h))
    assert me.sfx_idx == 1
    x, y, w, h = page.rect_of("view")
    _tap(drv, (x, y, w, h), dx=70)               # Song, the strip's second tab
    assert me.view == me.SONG_VIEW
    was = me.cur_track().pattern[me.slot]
    _tap(drv, page.rect_of("higher"))            # the song's first pad row steps the slot's sound
    assert me.cur_track().pattern[me.slot] != was
    _tap(drv, page.rect_of("hear"))
    assert mu.music_preview is not None
    _tap(drv, page.rect_of("hear"))
    assert mu.music_preview is None


def test_a_sound_with_a_name_is_named_and_one_without_is_numbered(hh):
    from runtime.music_editor_ui import sound_name
    ws, drv, mu, page = _music(hh)
    bank = mu.musicedit.bank
    bank.sfx[0].name = "tune"
    assert sound_name(bank, 0) == "0 tune"
    bank.sfx[0].name = None
    assert sound_name(bank, 0) == "Sound 0"


def test_the_speed_popover_sets_the_speed_and_b_closes_it(hh):
    ws, drv, mu, page = _music(hh)
    me = mu.musicedit
    _tap(drv, page.rect_of("speed_open"))
    assert mu.popped()
    was = me.cur_sfx().speed
    drv.press("right")                 # the focused slider takes the arrows
    for _ in range(2):
        drv.frame(DT)
    assert me.cur_sfx().speed == was + 1
    drv.press("b")
    drv.frame(DT)
    assert not mu.popped()
    assert ws.menu_view == "music"


def test_the_keys_move_the_cursor_and_its_note(hh):
    ws, drv, mu, page = _music(hh)
    me = mu.musicedit
    me.select_cursor(0)
    drv.press("down")
    drv.frame(DT)
    assert me.step == 1
    p = me.cur_step()[0]
    drv.press("right")
    drv.frame(DT)
    assert me.cur_step()[0] == p + 1


def test_a_settled_music_tab_paints_nothing(hh):
    ws, drv, mu, page = _music(hh)
    assert _settles(ws, drv)
    _tap(drv, page.rect_of("higher"))
    assert _settles(ws, drv)


# -- Map --------------------------------------------------------------------------------

def _map(hh):
    ws, drv = _open(hh, "map")
    mu = ws.map_ui
    assert mu.layout.verbs and mu.mapedit is not None
    return ws, drv, mu, mu


def _view_cell(mu, cx, cy):
    x0, y0, cell, _c, _r = mu._mv_metrics()
    me = mu.mapedit
    return (x0 + (cx - me.cam_x) * cell + cell // 2, y0 + (cy - me.cam_y) * cell + cell // 2)


def test_a_tap_in_the_view_paints_and_a_brush_tap_picks(hh):
    ws, drv, mu, page = _map(hh)
    tm = ws.run.project.tilemap
    bx, by, _w, _h = mu.rect_of("brushes")
    drv.click(bx + 6 + 22 + 5, by + 6 + 5)          # the second brush
    drv.frame(DT)
    assert mu.mapedit.n == mu._map_palette_ids()[1]
    x, y = _view_cell(mu, 2, 3)
    drv.click(x, y)
    for _ in range(2):
        drv.frame(DT)
    assert tm.mget(2, 3) == mu.mapedit.n
    assert mu._hover_cell == (2, 3)


def test_a_still_hold_in_the_view_picks_the_cells_tile(hh):
    ws, drv, mu, page = _map(hh)
    tm = ws.run.project.tilemap
    tm.mset(4, 4, 7)
    mu.mapedit.n = 2
    x, y = _view_cell(mu, 4, 4)
    drv.touch(x, y)
    for _ in range(mu.HOLD_FRAMES + 2):
        drv.frame(DT)
    drv.touch_up()
    drv.frame(DT)
    assert mu.mapedit.n == 7
    assert tm.mget(4, 4) == 7, "the hold took its stamp back"


def test_the_foot_picks_the_tools_the_size_and_the_zoom(hh):
    ws, drv, mu, page = _map(hh)
    _tap(drv, page.rect_of("box"))
    assert mu.map_tool == "rect"
    _tap(drv, page.rect_of("erase"))
    assert (mu.map_tool, mu.map_erase) == ("stamp", True)
    _tap(drv, page.rect_of("pen"))
    assert (mu.map_tool, mu.map_erase) == ("stamp", False)
    size = mu.mapedit.size
    _tap(drv, page.rect_of("size"))
    assert mu.mapedit.size != size
    _tap(drv, page.rect_of("zoom"))
    assert mu.map_zoom == 1
    assert page.zoom_word().startswith("2")
    _tap(drv, page.rect_of("select"))
    _tap(drv, page.rect_of("copy"))
    assert not mu.mapedit.has_clip, "no selection: Copy is off"
    mu.mapedit.set_selection(0, 0, 1, 1)
    ws.mark_dirty()
    drv.frame(DT)
    _tap(drv, page.rect_of("copy"))
    assert mu.mapedit.has_clip


def test_resize_grows_the_map_from_its_popover(hh):
    ws, drv, mu, page = _map(hh)
    tm = ws.run.project.tilemap
    w = tm.w
    _tap(drv, page.rect_of("resize"))
    assert mu._pop
    drv.frame(DT)                    # the card's first frames measure its rows
    drv.frame(DT)
    _tap(drv, page._host.box("wider"))
    assert tm.w == w + 1
    drv.press("b")
    drv.frame(DT)
    assert not mu._pop


def _key(drv, k, n=1):
    for _ in range(n):
        drv.press(k)
        for _ in range(2):
            drv.frame(DT)


def test_the_keys_pan_the_view_and_reach_the_brushes_and_the_tools(hh):
    """Keys alone: the arrows pan the view, and one the camera cannot
    follow moves on -- right to the brushes, whose arrows move the brush,
    down to the tools; Enter on a tool takes it and hands the keys back to
    the view."""
    ws, drv, mu, page = _map(hh)
    me = mu.mapedit
    assert page.page._focus_key() == "view"
    _key(drv, "a", 3)                   # A steps the zoom: 32 px a cell, the map past the view
    assert mu.map_zoom == 3
    for _ in range(200):
        if page.page._focus_key() != "view":
            break
        _key(drv, "right")
    assert page.page._focus_key() == "brushes" and me.cam_x > 0
    n = me.n
    _key(drv, "down")
    assert me.n != n and page.page._focus_key() == "brushes"
    _key(drv, "left", 8)
    assert page.page._focus_key() == "view"
    for _ in range(200):
        if page.page._focus_key() != "view":
            break
        _key(drv, "down")
    assert page.page._focus_key() in ("pen", "box", "fill", "select", "erase")
    while page.page._focus_key() != "pen":
        _key(drv, "left")
    _key(drv, "right")
    assert page.page._focus_key() == "box"
    _key(drv, "a")
    assert mu.map_tool == "rect"
    assert page.page._focus_key() == "view"


def test_a_settled_map_tab_paints_nothing(hh):
    ws, drv, mu, page = _map(hh)
    assert _settles(ws, drv)
    _tap(drv, page.rect_of("box"))
    assert _settles(ws, drv)


# -- Scene ------------------------------------------------------------------------------

def _scene(hh):
    ws, drv = _open(hh, "scene")
    su = ws.scene_ui
    assert su.layout.verbs and su.sceneedit is not None
    return ws, drv, su, su


def _world_px(su, wx, wy):
    x0, y0, scale, _vw, _vh = su._sv_metrics()
    se = su.sceneedit
    return x0 + (wx - se.cam_x) * scale + 2, y0 + (wy - se.cam_y) * scale + 2


def test_the_stamp_tool_places_and_the_pick_tool_does_not(hh):
    ws, drv, su, page = _scene(hh)
    se = su.sceneedit
    n = len(se.rows)
    x, y = _world_px(su, 200, 8)
    drv.click(x, y)
    for _ in range(2):
        drv.frame(DT)
    assert len(se.rows) == n, "the pick tool places nothing on empty world"
    _tap(drv, page.rect_of("stamp"))
    assert su.tool == "stamp"
    bx, by, _w, _h = page.rect_of("stamps")
    drv.click(bx + 6 + 22 + 4, by + 6 + 4)           # the second stamp
    drv.frame(DT)
    assert se.n == su.brush_ids()[1]
    drv.click(x, y)
    for _ in range(2):
        drv.frame(DT)
    assert len(se.rows) == n + 1 and se.selected()["tile"] == se.n


def test_the_actors_verbs_flip_and_remove_the_picked_actor(hh):
    ws, drv, su, page = _scene(hh)
    se = su.sceneedit
    se.place(64, 64, "coin")
    n = len(se.rows)
    ws.mark_dirty()
    drv.frame(DT)
    _tap(drv, su._host.box("Flip"))
    assert se.selected().get("flip")
    _tap(drv, su._host.box("Remove"))
    assert len(se.rows) == n - 1 and se.selected() is None


def test_a_tag_is_typed_in_its_popover(hh):
    ws, drv, su, page = _scene(hh)
    se = su.sceneedit
    se.place(64, 64, "coin")
    ws.mark_dirty()
    drv.frame(DT)
    _tap(drv, su._host.box("Tag"))
    drv.frame(DT)
    assert su.popover() and ws.input.text_mode, "its field holds the keys"
    for ch in "gem":
        drv.type_char(ord(ch))
        drv.frame(DT)
    drv.type_char(0x0D)
    for _ in range(3):              # the page redraws without the popover
        drv.frame(DT)               # and the input policy reads that
    assert se.selected()["tag"] == "coingem"
    assert not su.popover() and not ws.input.text_mode


def test_snap_and_zoom_from_the_foot(hh):
    ws, drv, su, page = _scene(hh)
    se = su.sceneedit
    snap = se.snap
    _tap(drv, page.rect_of("snap"))
    assert se.snap != snap
    _tap(drv, page.rect_of("zoom"))
    assert su.scene_zoom == 1


def test_the_scene_tab_by_keys_alone(hh):
    """The view's arrows nudge a picked actor and pan an empty pick; an
    arrow the camera cannot follow moves focus on, to the column and the
    foot, whose tools A presses."""
    ws, drv, su, page = _scene(hh)
    se = su.sceneedit
    se.place(64, 64, "coin")
    ws.mark_dirty()
    drv.frame(DT)
    assert page.page._focus_key() == "view"
    _key(drv, "right")
    assert se.selected()["x"] > 64
    se.sel = None
    _key(drv, "right", 3)
    assert se.cam_x > 0
    for _ in range(200):
        if page.page._focus_key() != "view":
            break
        _key(drv, "down")
    assert page.page._focus_key() in ("pick", "stamp", "snap", "zoom")
    while page.page._focus_key() != "pick":
        _key(drv, "left")
    _key(drv, "right")
    assert page.page._focus_key() == "stamp"
    _key(drv, "a")
    assert su.tool == "stamp" and page.page._focus_key() == "view"


def test_a_settled_scene_tab_paints_nothing(hh):
    ws, drv, su, page = _scene(hh)
    assert _settles(ws, drv)
    _tap(drv, page.rect_of("stamp"))
    assert _settles(ws, drv)


# -- Blocks -----------------------------------------------------------------------------

def _blocks(hh, title="Coin Quest"):
    ws, drv = hh
    cart = next(c for c in ws.carts.all if c.get("title") == title)
    ws.open_in_editor(cart)
    ws, drv = _open(hh, "blocks")
    bu = ws.block_ui
    assert bu.blocks_ed is not None
    return ws, drv, bu, bu.page()


def _item(bu, page, word):
    """The open menu's item that reads `word`: its rect."""
    assert any(bu.menu_word(i) == word for i in range(len(bu.blk_menu["items"])))
    return bu._host.box(word)                    # a menu item's id is its text


def test_the_objects_tabs_pick_whose_scripts_show(hh):
    ws, drv, bu, page = _blocks(hh)
    assert bu.blocks_ed.target is None
    tags = bu._roster_tags()
    assert tags, "Coin Quest's objects have scripts"
    x, y, w, h = page.rect_of("obj")
    drv.click(x + 8 + 50 + 6, y + h // 2)         # the tab after the Stage's
    for _ in range(3):
        drv.frame(DT)
    assert bu.blocks_ed.target == tags[0]


def test_add_opens_the_menu_and_a_pick_inserts_the_block(hh):
    ws, drv, bu, page = _blocks(hh)
    be = bu.blocks_ed
    be.cur = next(i for i, r in enumerate(be.rows) if r.kind == "insert")
    n = len(be.rows)
    _tap(drv, page.rect_of("add"))
    assert bu.blk_menu is not None and bu.blk_menu["mode"] == "cat"
    _tap(drv, _item(bu, page, "Control"))
    assert bu.blk_menu["mode"] == "blk"
    _tap(drv, _item(bu, page, "forever"))
    assert bu.blk_menu is None
    assert len(be.rows) > n
    assert any(r.kind == "block" and r.block.get("t") == "forever" for r in be.rows)


def test_the_menus_keys_are_the_engines_and_b_steps_back(hh):
    ws, drv, bu, page = _blocks(hh)
    _tap(drv, page.rect_of("add"))
    drv.press("down")
    drv.frame(DT)
    drv.press("a")
    for _ in range(2):
        drv.frame(DT)
    assert bu.blk_menu["mode"] == "blk", "the second kind opened"
    drv.press("b")
    drv.frame(DT)
    drv.frame(DT)
    assert bu.blk_menu["mode"] == "cat"
    drv.press("b")
    drv.frame(DT)
    drv.frame(DT)
    assert bu.blk_menu is None
    assert ws.menu_view == "blocks"


def test_delete_and_see_code_from_the_foot(hh):
    ws, drv, bu, page = _blocks(hh)
    be = bu.blocks_ed
    be.cur = next(i for i, r in enumerate(be.rows) if r.kind == "block" and r.depth > 0)
    n = len(be.rows)
    _tap(drv, page.rect_of("delete"))
    assert len(be.rows) < n
    _tap(drv, page.rect_of("code"))
    assert ws.menu_view == "code"


def test_a_tap_on_a_row_picks_it(hh):
    ws, drv, bu, page = _blocks(hh)
    from runtime.block_editor_ui import ROW
    be = bu.blocks_ed
    be.cur = 0
    x, y, w, h = page.rect_of("lines")
    drv.click(x + 20, y + 2 * ROW + ROW // 2)
    for _ in range(2):
        drv.frame(DT)
    assert be.cur == 2                 # the outline at its top


def test_a_settled_blocks_tab_paints_nothing(hh):
    ws, drv, bu, page = _blocks(hh)
    assert _settles(ws, drv)
    _tap(drv, page.rect_of("add"))
    assert _settles(ws, drv)
