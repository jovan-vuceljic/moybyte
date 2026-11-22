"""Tests for #94's host-side gaps in the Config ("Make it mine" cards) tab:

  1. a cart manifest/metadata editing surface -- title + author, through
     moy_carts.save_manifest_meta / Project.commit_manifest / the Config
     page's Cart info dialog (editor_settings.py).
  2. validation feedback for a bad/out-of-range `edit` field definition --
     covered in test_preliterate_ux.py alongside the existing malformed-card
     tests, not here.

`permissions` stays read-only (see the comment over moy_carts.save_manifest_meta)
-- the tracker leaves its editability an open, security-sensitive question, so
this only covers the unambiguous title/author half of the gap.
"""

from pathlib import Path
from ws_helpers import settings_box, shelf, select_on_home, tap_box  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

from runtime import moy_carts  # noqa: E402
from runtime import host_app  # noqa: E402

import canvas_probe as probe  # noqa: E402  (pixel-width-agnostic "it drew" probes)


# ----------------------------------------------------------------------------
# Layer 1: the store (moy_carts.save_manifest_meta)
# ----------------------------------------------------------------------------

def test_load_defaults_author_to_empty_string(tmp_path):
    root = str(tmp_path / "carts")
    moy_carts.ensure_dirs(root)
    cart = moy_carts.create("No Author", root, src="def _draw():\n    cls(1)\n")
    assert cart["author"] == ""                 # absent in the manifest -> ""


def test_duplicate_carries_the_author_over(tmp_path):
    root = str(tmp_path / "carts")
    moy_carts.ensure_dirs(root)
    cart = moy_carts.create("Original", root, src="def _draw():\n    cls(1)\n")
    assert moy_carts.save_manifest_meta(cart["path"], author="Ada Lovelace")
    cart = moy_carts.load(cart["path"])
    copy = moy_carts.duplicate(cart, root)
    assert copy["author"] == "Ada Lovelace"
    assert copy["title"] == "Original copy"


def test_save_manifest_meta_round_trip_preserves_other_fields(tmp_path):
    root = str(tmp_path / "carts")
    moy_carts.ensure_dirs(root)
    cart = moy_carts.create(
        "Info Cart", root, src="def _draw():\n    cls(1)\n", type="game",
        edit=[{"key": "n", "type": "int", "min": 0, "max": 9, "card": "N"}])
    moy_carts.set_graduated(cart, True)          # a field that must survive untouched

    assert moy_carts.save_manifest_meta(cart["path"], title="New Title",
                                        author="Ada Lovelace") is True
    reloaded = moy_carts.load(cart["path"])
    assert reloaded["title"] == "New Title"
    assert reloaded["author"] == "Ada Lovelace"
    # every other manifest fact rode along untouched
    assert reloaded["type"] == "game"
    assert reloaded["graduated"] is True
    assert reloaded["edit"] == cart["edit"]
    assert reloaded["src"] == cart["src"]


def test_save_manifest_meta_noop_when_unchanged(tmp_path):
    root = str(tmp_path / "carts")
    moy_carts.ensure_dirs(root)
    cart = moy_carts.create("Same", root, src="def _draw():\n    cls(1)\n")
    assert moy_carts.save_manifest_meta(cart["path"], title="Same") is False
    assert moy_carts.save_manifest_meta(cart["path"]) is False   # both None -> no-op
    assert moy_carts.save_manifest_meta(cart["path"], author="") is False  # matches default


def test_save_manifest_meta_bad_manifest_is_a_safe_false(tmp_path):
    root = str(tmp_path / "carts")
    moy_carts.ensure_dirs(root)
    assert moy_carts.save_manifest_meta(root + "/nonexistent.moy", title="X") is False


# ----------------------------------------------------------------------------
# Layer 2: Project.commit_manifest (RAM sync + store write + blank-title guard)
# ----------------------------------------------------------------------------

def _cart_with_edit_schema(root):
    return moy_carts.create(
        "Tune Me", root, src="def _draw():\n    cls(1)\n", type="app",
        edit=[{"key": "spd", "type": "int", "min": 0, "max": 10, "card": "SPD {value}"}])


def test_project_commit_manifest_persists_and_syncs_ram(tmp_path):
    root = str(tmp_path / "carts")
    moy_carts.ensure_dirs(root)
    _cart_with_edit_schema(root)
    ws = host_app.build_workstation(root)
    ws.launcher.set_items(shelf(root))
    select_on_home(ws, "Tune Me")
    ws.open_in_editor()
    assert ws.menu_view == "cards"

    titled = ws.carts.titled
    ok = ws.run.project.commit_manifest(title="Renamed", author="Kid Coder")
    assert ok is True
    assert ws.run.project.cart["title"] == "Renamed"       # in-RAM sync
    assert ws.carts.titled == titled + 1               # what a title reader keys on
    assert ws.run.project.cart["author"] == "Kid Coder"
    reloaded = moy_carts.load(ws.run.project.cart["path"])
    assert reloaded["title"] == "Renamed"
    assert reloaded["author"] == "Kid Coder"


def test_project_commit_manifest_rejects_blank_title(tmp_path):
    # A blank/whitespace title never overwrites the cart's real title -- but this
    # low-level store call still applies whichever OTHER field IS valid (the
    # all-or-nothing guard lives one layer up, in the modal's _commit_meta,
    # which never calls commit_manifest at all on a blank title -- see
    # test_meta_modal_blank_title_stays_open_with_message).
    root = str(tmp_path / "carts")
    moy_carts.ensure_dirs(root)
    cart = _cart_with_edit_schema(root)
    ws = host_app.build_workstation(root)
    ws.launcher.set_items(shelf(root))
    select_on_home(ws, "Tune Me")
    ws.open_in_editor()

    assert ws.run.project.commit_manifest(title="   ", author="Someone") is True
    assert ws.run.project.cart["title"] == "Tune Me"        # title left alone in RAM
    assert ws.run.project.cart["author"] == "Someone"       # author still applied
    reloaded = moy_carts.load(cart["path"])
    assert reloaded["title"] == "Tune Me"               # title left alone on disk
    assert reloaded["author"] == "Someone"

    # blank BOTH -> nothing to do, a clean no-op False
    assert ws.run.project.commit_manifest(title="  ", author=None) is False


def test_project_commit_manifest_noop_without_a_real_cart():
    ws = host_app.build_workstation(None)
    ws.run.project.cart = None
    assert ws.run.project.commit_manifest(title="X") is False


# ----------------------------------------------------------------------------
# Layer 3: the Config page's Cart info dialog (open/type/commit/cancel)
# ----------------------------------------------------------------------------

def _open_cards_for(ws, title):
    select_on_home(ws, title)
    ws.open_in_editor()
    assert ws.menu_view == "cards"
    drv = host_app.ConsoleDriver(ws)
    drv.frame(1 / 30)
    return drv


def _frames(drv, n=2):
    for _ in range(n):
        drv.frame(1 / 30)


def _type(drv, text):
    for ch in text:
        drv.type_char(ord(ch))
        _frames(drv)


def test_info_button_tap_opens_the_modal(tmp_path):
    root = str(tmp_path / "carts")
    moy_carts.ensure_dirs(root)
    _cart_with_edit_schema(root)
    ws = host_app.build_workstation(root)
    ws.launcher.set_items(shelf(root))
    _open_cards_for(ws, "Tune Me")
    assert ws.cards_layer.s.asking == "none"
    tap_box(ws, settings_box(ws, "cart_info"))       # the page's door
    assert ws.cards_layer.s.asking == "meta"
    ws.input_policy.sync()                              # the frame's look at the mode
    assert ws.input.text_mode is True                   # typing mode armed


def test_meta_modal_edits_title_and_author_and_commits(tmp_path):
    root = str(tmp_path / "carts")
    moy_carts.ensure_dirs(root)
    cart = _cart_with_edit_schema(root)
    ws = host_app.build_workstation(root)
    ws.launcher.set_items(shelf(root))
    drv = _open_cards_for(ws, "Tune Me")

    cl = ws.cards_layer
    cl.run("cart_info")
    _frames(drv)
    assert cl.page.focus_key == "f_title"               # starts on the title
    assert cl.s.f_title == "Tune Me"                    # pre-filled from the cart
    _type(drv, "\b" * len("Tune Me") + "Star Racer")
    _type(drv, "\t")                                   # Tab: Made by
    assert cl.page.focus_key == "f_author"
    _type(drv, "Ada\r")                                # Enter saves

    assert cl.s.asking == "none"                        # dialog closed
    ws.input_policy.sync()
    assert ws.input.text_mode is False                  # keyboard restored
    assert ws.run.project.cart["title"] == "Star Racer"
    assert ws.run.project.cart["author"] == "Ada"
    reloaded = moy_carts.load(cart["path"])
    assert reloaded["title"] == "Star Racer"
    assert reloaded["author"] == "Ada"


def test_meta_modal_blank_title_stays_open_with_message(tmp_path):
    root = str(tmp_path / "carts")
    moy_carts.ensure_dirs(root)
    _cart_with_edit_schema(root)
    ws = host_app.build_workstation(root)
    ws.launcher.set_items(shelf(root))
    drv = _open_cards_for(ws, "Tune Me")

    cl = ws.cards_layer
    cl.run("cart_info")
    _frames(drv)
    _type(drv, "\b" * len("Tune Me"))                  # backspace to empty
    assert cl.s.f_title == ""
    _type(drv, "\r")                                   # Enter: try to commit

    assert cl.s.asking == "meta"                        # stayed open
    assert cl.s.ask_msg == "Give it a title."
    assert ws.run.project.cart["title"] == "Tune Me"    # unchanged
    _type(drv, "X")
    assert cl.s.ask_msg == ""                           # the next key clears the line


def test_meta_modal_cancel_discards_edits(tmp_path):
    root = str(tmp_path / "carts")
    moy_carts.ensure_dirs(root)
    cart = _cart_with_edit_schema(root)
    ws = host_app.build_workstation(root)
    ws.launcher.set_items(shelf(root))
    drv = _open_cards_for(ws, "Tune Me")

    cl = ws.cards_layer
    cl.run("cart_info")
    _frames(drv)
    _type(drv, "XXXXX\x1b")                            # Esc cancels

    assert cl.s.asking == "none"
    ws.input_policy.sync()
    assert ws.input.text_mode is False
    assert ws.run.project.cart["title"] == "Tune Me"    # discarded
    reloaded = moy_carts.load(cart["path"])
    assert reloaded["title"] == "Tune Me"


def test_meta_modal_draws_without_crashing_and_reset_closes_it(tmp_path):
    root = str(tmp_path / "carts")
    moy_carts.ensure_dirs(root)
    _cart_with_edit_schema(root)
    ws = host_app.build_workstation(root)
    ws.launcher.set_items(shelf(root))
    drv = _open_cards_for(ws, "Tune Me")

    ws.cards_layer.run("cart_info")
    _frames(drv)                                        # draws the dialog, must not raise
    assert ws.cart_error is None
    assert probe.drew_something(ws.run.canvas)

    ws.cards_layer.reset()                              # switching cart must not leak it
    _frames(drv)
    assert ws.cards_layer.s.asking == "none"
    ws.input_policy.sync()                              # the next frame's look
    assert ws.input.text_mode is False
