"""Pre-literate UX (#15): the visual "Make it mine" cards.

A kid who can't read should be able to change how-fast / how-many / which-
character with icons only. These tests assert:
  * the per-field `display` hints ("gauge" | "count" | "choice-icons" |
    "sprite-tiles" | "bg-thumbs") render on the Settings page without error;
  * a field with NO `display` is an ordinary card (a slider for an int), and
    one that fails `_validate_field` stays off the page;
  * a sprite-tile / choice-icon card steps its choice on a tap (a choice-icon
    card shows its choice's icon);
  * the showcase cart (Star Catcher, now sprite-tile catcher) still opens + runs
    headless, and the other seed carts still render their (text) cards.

Kept in its own file (per the issue) so it never collides with the existing
suites. Runs the same code path the device freezes (runtime/shell/console.py).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from runtime import host_app  # noqa: E402  (registers the `editors_*` aliases console needs)
from runtime import console  # noqa: E402  (import after host_app for the alias)
from runtime.editors_sheet import SpriteSheet  # noqa: E402
from runtime.host_canvas import make_system_canvas as Canvas  # noqa: E402
from runtime.input import InputState  # noqa: E402

import canvas_probe as probe  # noqa: E402  (pixel-width-agnostic "it drew" probes)


# -- a tiny in-memory Workstation fixture (no disk, no real cart) ------------

def _ws_with_cart(edit, cfg, sheet=None):
    """Build a host Workstation parked in the cards menu over an in-RAM cart with
    the given `edit` schema + `config`, ready to draw/hit-test cards."""
    canvas = Canvas(host_app.WIDTH, host_app.HEIGHT)
    inp = InputState()
    ws = console.Workstation(host_app._NullComp(), canvas, inp, [])
    ws.make_api = host_app.make_api
    ws.carts_store = host_app.moy_carts
    ws.set_pointer(console.Pointer(host_app.WIDTH, host_app.HEIGHT))
    inp.pointer = ws.pointer
    ws.cart = {"title": "T", "type": "app", "src": "", "cfg": dict(cfg),
               "edit": edit, "path": None}
    ws.run.project.config = dict(cfg)
    ws.sheet = sheet if sheet is not None else SpriteSheet()
    ws.screen = "menu"
    ws.menu_view = "cards"
    ws.run.player.draw = None
    ws.run.player.update = None
    return ws


def _draw_once(ws):
    ws.input.begin_frame()
    ws.frame(1 / 30)


def _painted_sheet():
    """A sheet with two recognizable, non-blank tiles (ids 0 and 1)."""
    sh = SpriteSheet()
    for i in range(sh.TILE):
        sh.tset(0, i, i, 11)        # green diagonal
        sh.tset(1, i, 0, 8)         # red top row
    return sh


# -- each display type renders without error --------------------------------

def _box(ws, key):
    """Card `key`'s stop on the Config page, as its last frame drew it."""
    page = ws.cards_layer.page
    for sid in page.stop_kinds():
        if sid.split("/")[0] == key:
            return page._ui.box(sid)
    return None


def test_all_display_types_render_without_error():
    sheet = _painted_sheet()
    edit = [
        {"key": "n", "type": "int", "min": 1, "max": 10, "step": 1,
         "display": "count", "icon": "star", "card": "DROP {value}"},
        {"key": "spd", "type": "int", "min": 0, "max": 100, "step": 10,
         "display": "gauge", "card": "FAST {value}"},
        {"key": "pick", "type": "choice", "choices": ["a", "b", "c"],
         "display": "choice-icons", "icons": ["star", "heart", "dot"],
         "card": "PICK {value}"},
        {"key": "who", "type": "choice", "choices": [0, 1], "tiles": [0, 1],
         "display": "sprite-tiles", "card": "WHO {value}"},
    ]
    cfg = {"n": 5, "spd": 50, "pick": "b", "who": 1}
    ws = _ws_with_cart(edit, cfg, sheet)
    _draw_once(ws)                          # must not raise
    assert ws.cart_error is None
    assert probe.drew_something(ws.run.canvas)  # something was drawn
    # every card is on the page: the meters as sliders, the pictures as pickers
    for key in ("n", "spd", "pick", "who"):
        assert _box(ws, key) is not None, key
    kinds = {r.id: (r.shape, r.k) for r in ws.cards_layer.s.cards}
    assert kinds["pick"] == ("pics", 1) and kinds["who"] == ("pics", 1)


def test_missing_display_is_an_ordinary_card():
    edit = [{"key": "size", "type": "int", "min": 0, "max": 9, "step": 1,
             "card": "SIZE {value}"}]
    ws = _ws_with_cart(edit, {"size": 3})
    _draw_once(ws)
    assert _box(ws, "size") is not None     # a slider, its value at its right
    assert ws.cards_layer.page.stop_kinds()["size/v"] == "slider"


def test_an_unknown_display_hint_leaves_the_card_off_the_page():
    edit = [{"key": "k", "type": "int", "min": 0, "max": 9, "step": 1,
             "display": "bananas", "card": "K {value}"},
            {"key": "ok", "type": "int", "min": 0, "max": 9, "card": "OK {value}"}]
    ws = _ws_with_cart(edit, {"k": 2, "ok": 1})
    _draw_once(ws)
    assert ws.cart_error is None
    assert _box(ws, "k") is None and _box(ws, "ok") is not None


# -- selecting without reading: a tap steps the choice -----------------------

def _tap_card(ws, key):
    """A tap on card `key` on the Config page, where its last frame drew it."""
    from ws_helpers import tap_box
    _draw_once(ws)
    tap_box(ws, _box(ws, key))


def _tap_tile(ws, key, k, n):
    """A tap on tile `k` of the `n` of picker card `key`, where its last
    frame drew it."""
    from ws_helpers import tap_box
    _draw_once(ws)
    x, y, w, h = _box(ws, key)
    tx, ty, side = ws.cards_layer.tiles(n, w, h)[k]
    tap_box(ws, (x + tx, y + ty, side, side))


def test_a_sprite_tile_card_takes_the_tile_tapped():
    edit = [{"key": "who", "type": "choice", "choices": [0, 1], "tiles": [0, 1],
             "display": "sprite-tiles", "card": "WHO {value}"}]
    ws = _ws_with_cart(edit, {"who": 0}, _painted_sheet())
    _tap_tile(ws, "who", 1, 2)
    assert ws.run.project.config["who"] == 1
    _tap_tile(ws, "who", 1, 2)
    assert ws.run.project.config["who"] == 1
    _tap_tile(ws, "who", 0, 2)
    assert ws.run.project.config["who"] == 0


def test_a_picker_steps_with_left_right_and_enter():
    edit = [{"key": "p", "type": "choice", "choices": ["x", "y", "z"],
             "display": "choice-icons", "icons": ["star", "heart", "dot"],
             "card": "P {value}"}]
    ws = _ws_with_cart(edit, {"p": "x"})
    drv = host_app.ConsoleDriver(ws)
    drv.frame(1 / 30)
    assert ws.cards_layer.page.focus_key == "p/pick"
    for key, want in (("right", "y"), ("right", "z"), ("right", "x"), ("left", "z"), ("a", "x")):
        drv.press(key)
        drv.frame(1 / 30)
        drv.frame(1 / 30)               # the key let go before the next press
        assert ws.run.project.config["p"] == want, key
    assert ws.cards_layer.page.hints()[:2] == ("confirm", "Change")


def test_a_choice_of_names_cycles_with_left_and_right():
    edit = [{"key": "c", "type": "choice", "choices": ["r", "g", "b"], "names": ["red", "green", "blue"],
             "card": "C {value}"}]
    ws = _ws_with_cart(edit, {"c": "g"})
    drv = host_app.ConsoleDriver(ws)
    drv.frame(1 / 30)
    assert ws.cards_layer.page.stop_kinds()["c/k"] == "cycle"
    row = ws.cards_layer.s.cards[0]
    assert (row.k, row.names) == (1, "red\ngreen\nblue")
    drv.press("right")
    drv.frame(1 / 30)
    assert ws.run.project.config["c"] == "b"
    for _ in range(2):
        drv.press("left")
        drv.frame(1 / 30)
        drv.frame(1 / 30)
    assert ws.run.project.config["c"] == "r"


def test_a_choice_icons_card_of_three_is_a_picker_of_its_icons():
    edit = [{"key": "p", "type": "choice", "choices": ["x", "y", "z"],
             "display": "choice-icons", "icons": ["star", "heart", "dot"],
             "card": "P {value}"}]
    ws = _ws_with_cart(edit, {"p": "x"})
    _tap_tile(ws, "p", 2, 3)
    assert ws.run.project.config["p"] == "z"
    _draw_once(ws)
    assert [(r.shape, r.k) for r in ws.cards_layer.s.cards] == [("pics", 2)]


def test_a_two_way_choice_icons_card_is_a_toggle_at_row_height():
    """Owner report 2026-10-31: the seed carts' AUTOPLAY (choices 0 and 1,
    icons close and run) drew as two big tiles in a row far taller
    than a slider's. Its two icons are off and on: a toggle row."""
    edit = [{"key": "enemies", "type": "int", "min": 1, "max": 16,
             "card": "FIGHT {value} TANKS"},
            {"key": "autoplay", "type": "choice", "choices": [0, 1],
             "icons": ["close", "run"], "display": "choice-icons",
             "card": "AUTOPLAY {value}"}]
    ws = _ws_with_cart(edit, {"enemies": 6, "autoplay": 0})
    _draw_once(ws)
    assert ws.cards_layer.page.stop_kinds()["autoplay/on"] == "toggle"
    _tap_card(ws, "autoplay")
    assert ws.run.project.config["autoplay"] == 1


def test_an_int_card_steps_by_its_step_with_left_and_right():
    # A gauge card is a slider on the Settings page: left and right step it
    # by the card's own step.
    edit = [{"key": "spd", "type": "int", "min": 0, "max": 100, "step": 10,
             "display": "gauge", "card": "F {value}"}]
    ws = _ws_with_cart(edit, {"spd": 50})
    drv = host_app.ConsoleDriver(ws)
    drv.frame(1 / 30)
    drv.press("right")
    drv.frame(1 / 30)
    assert ws.run.project.config["spd"] == 60
    drv.press("left")
    drv.frame(1 / 30)
    assert ws.run.project.config["spd"] == 50


# -- the showcase cart: Star Catcher with real sprite-tile catcher ----------

def _open(ws, title):
    for i, c in enumerate(ws.launcher.items):
        if c["title"] == title:
            ws.launcher.sel = i
            ws.open()
            return
    # Not in the launcher run-grid (a WALLPAPER leaves it, spec shell_ux_v1.md): still a
    # real editable cart in the store, so open it by reference (as ws.open() does).
    cart = next((c for c in ws.carts.all if c["title"] == title), None)
    if cart is None:
        raise AssertionError("cart not found: " + title)
    ws.open_workspace(cart)
    ws.spine.play(ws.launcher_layer)


def test_showcase_star_catcher_opens_and_runs_headless(tmp_path):
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    _open(ws, "Star Catcher")
    assert ws.screen == "desktop" and ws.cart_error is None

    # the catcher is now a REAL sprite tile (frog id 0, robot id 1) -- both painted.
    assert ws.sheet.tile_image(0).pix.count(0) < 64     # tile 0 not blank
    assert ws.sheet.tile_image(1).pix.count(0) < 64     # tile 1 not blank

    for _ in range(120):                                # attract mode, no crash
        ws.input.begin_frame()
        ws.frame(1 / 30)
    assert ws.cart_error is None

    # its CATCHER card is a sprite-tile picker.
    ws.text.open_menu()
    basket = [f for f in ws.cart["edit"] if f["key"] == "basket"][0]
    assert basket["display"] == "sprite-tiles"
    _tap_tile(ws, "basket", 1, 2)                       # the robot tile
    assert ws.run.project.config["basket"] == 1
    ws.saves.apply()                                          # re-run with the new pick
    assert ws.cart_error is None
    assert ws.ns["catcher"] == 1


def test_showcase_runs_with_a_stale_string_basket(tmp_path):
    # An older config may still carry basket="frog"; the cart must not crash.
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    _open(ws, "Star Catcher")
    ws.run.project.config["basket"] = "robot"
    ws.saves.apply()
    assert ws.cart_error is None
    assert ws.ns["catcher"] == 1                        # mapped name -> tile id


# -- P3: background picker (tap a thumbnail) --------------------------------

def test_bg_thumbs_card_takes_the_preset_tapped():
    edit = [{"key": "bg", "type": "choice",
             "choices": ["dark_blue", "night", "stripes", "indigo"],
             "display": "bg-thumbs", "card": "SKY {value}"}]
    ws = _ws_with_cart(edit, {"bg": "dark_blue"})
    _tap_tile(ws, "bg", 2, 4)
    assert ws.run.project.config["bg"] == "stripes"


def test_space_desktop_bg_picker_applies_a_preset(tmp_path):
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    _open(ws, "Space Desktop")
    ws.text.open_menu()
    bg = [f for f in ws.cart["edit"] if f["key"] == "bg"][0]
    assert bg["display"] == "bg-thumbs"
    _draw_once(ws)
    ws.cards_layer.page.want_focus = "bg/pick"   # the page scrolls it into view
    for _ in range(20):
        _draw_once(ws)
    _tap_tile(ws, "bg", 2, 4)
    assert ws.run.project.config.get("bg") == "stripes"
    ws.saves.apply()                                   # the cart paints stripes, no crash
    assert ws.cart_error is None
    for _ in range(10):
        ws.input.begin_frame()
        ws.frame(1 / 30)
    assert ws.cart_error is None


# -- back-compat: existing seed carts still render their cards --------------

def test_existing_seed_carts_still_render_their_cards(tmp_path):
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    for title in ("Star Catcher", "Harpoon Pop", "Tap Only Red"):
        _open(ws, title)
        if not ws.cart.get("edit"):
            ws.home.go_home()
            continue
        ws.text.open_menu()
        assert ws.menu_view == "cards"
        ws.input.begin_frame()
        ws.frame(1 / 30)                                # draws cards, no error
        assert probe.drew_something(ws.run.canvas)
        ws.home.go_home()


# -- robustness: a card the checks missed costs the page, never the frame ----

def test_a_thrown_card_is_caught_and_its_reason_shown():
    # Belt-and-braces: even if a card raises for some unforeseen reason, frame()
    # must capture it (not let it escape the loop) and show the reason.
    ws = _ws_with_cart([{"key": "k", "type": "int", "min": 0, "max": 9, "card": "K"}],
                       {"k": 1})

    def _boom():
        raise ValueError("boom")
    ws.cards_layer._rows = _boom
    _draw_once(ws)                                   # must not raise out of frame()
    assert ws.cart_error is not None
    assert "boom" in ws.cart_error
    assert ws.cards_layer.s.broken_title == "This page didn't draw"


# -- #94: a bad `edit` field def costs one card, never the tab --------------
#
# Before #94 a malformed field def only surfaced through draw()'s belt-and-
# braces try/except (test_a_thrown_card_is_caught_and_its_reason_shown, above):
# ONE bad card took the whole Config tab down to the error panel, and a
# left/right press on it could raise straight out of the input router. The
# Settings page leaves a field `_validate_field` refuses off the page.

def test_bad_edit_field_stays_off_the_page_others_still_work():
    edit = [
        {"key": "ok", "type": "int", "min": 0, "max": 9, "card": "OK {value}"},
        {"key": "bad", "type": "int", "min": 9, "max": 0, "card": "BAD"},  # min > max
    ]
    ws = _ws_with_cart(edit, {"ok": 3, "bad": 5})
    _draw_once(ws)                                    # must not raise / no error panel
    assert ws.cart_error is None
    assert _box(ws, "ok") is not None and _box(ws, "bad") is None
    assert probe.drew_something(ws.run.canvas)


def test_validate_field_catches_the_known_bad_shapes():
    v = _ws_with_cart([], {}).cards_layer._validate_field
    assert v({"key": "k", "type": "int", "min": 0, "max": 9}) is None       # fine
    assert v({"key": "k", "type": "choice", "choices": [1, 2]}) is None    # fine
    assert v("not a dict") is not None
    assert v({}) is not None                                                # no key
    assert v({"key": "k"}) is not None                                      # no/bad type
    assert v({"key": "k", "type": "int", "min": 5, "max": 1}) is not None   # min > max
    assert v({"key": "k", "type": "int", "step": 0}) is not None            # step 0
    assert v({"key": "k", "type": "choice", "choices": []}) is not None     # empty choices
    assert v({"key": "k", "type": "choice"}) is not None                    # missing choices
    assert v({"key": "k", "type": "int", "display": "choice-icons"}) is not None  # display/type mismatch
    assert v({"key": "k", "type": "int", "display": "nope"}) is not None    # unknown display


def test_left_right_input_on_malformed_card_does_not_crash():
    edit = [{"key": "bad", "type": "int", "min": 9, "max": 0, "card": "BAD"}]
    ws = _ws_with_cart(edit, {"bad": 5})
    drv = host_app.ConsoleDriver(ws)
    drv.press("left")
    drv.frame(1 / 30)                                   # must not raise
    drv.press("right")
    drv.frame(1 / 30)
    assert ws.cart_error is None
    assert ws.run.project.config["bad"] == 5


# -- many cards: the page scrolls (#3) --------------------------------------

def _many_tile_cards(n):
    return [{"key": "k%d" % i, "type": "choice", "choices": [0, 1], "tiles": [0, 1],
             "display": "sprite-tiles", "card": "K%d" % i} for i in range(n)]


def test_many_cards_scroll_the_focus_and_files_into_view():
    edit = _many_tile_cards(12)                      # more rows than one 240px page
    ws = _ws_with_cart(edit, {})
    drv = host_app.ConsoleDriver(ws)
    drv.frame(1 / 30)
    page = ws.cards_layer.page
    lay = ws.cards_layer.layout
    for _ in range(3 * len(edit)):
        if page.focus_key == "files":
            break
        drv.press("down")
        for _ in range(30):                          # the reveal glides (§7)
            drv.frame(1 / 30)
        x, y, w, h = page._ui.box(page.focus_key)
        assert lay.cy <= y and y + h <= lay.cy + lay.ch, page.focus_key   # the focus shows
    assert page.focus_key == "files"                 # the last door is reachable
