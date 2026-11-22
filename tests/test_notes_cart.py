"""NOTES -- the console's one text app, and it is a CART (step 3 of
docs/theme_and_shell_2026-11.md §10), on the UI tree API (the extension
`moybyte.uitree`: runtime/run/player_tree.py).

The page is `system_carts/moybyte.notes.moy/main.py`: the vault as rows (New
note first), a dialog that names a note, the note in a text editor that
adopts its editor handle, its tools and its status line; on the desk the vault
beside the note. Everything below drives the REAL console the way a kid does
-- keys, typed keys and taps on the stops the engine drew -- and asserts what
is in the store or where the console ended up. The handle's engine is pinned
by `tests/test_editor_handle.py`, the text editor's adoption of it by
`tests/test_uitree_pycart.py`.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ws_helpers import build_desktop_ws, build_ws, select_on_home  # noqa: E402
from runtime import host_app, moy_carts, system_api  # noqa: E402

DT = 1.0 / 30
ESC = 0x1B


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _frames(drv, n=3):
    for _ in range(n):
        drv.ws.mark_dirty()
        drv.frame(DT)


def _open(ws):
    """Notes opened on the home, its first frames drawn: (namespace, driver)."""
    assert select_on_home(ws, "Notes") is not None
    ws.open()
    drv = host_app.ConsoleDriver(ws)
    _frames(drv)
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    return ws.run.player.ns, drv


def _s(ws):
    """The page's state as the engine holds it."""
    return ws.run.player.tree.engine.s._v


def _act(ws, drv, name, *args):
    ws.run.player.tree.act(name, *args)
    _frames(drv)


def _press(drv, *keys):
    for k in keys:
        drv.press(k)
        _frames(drv)


def _type(drv, text):
    for ch in text:
        drv.type_char(ord(ch) if isinstance(ch, str) else ch)
        _frames(drv, 2)


def _box(ws, id):
    """Where stop `id` drew in the Notes page's last frame."""
    got = ws.run.player.face.host().box(id)
    assert got is not None, "Notes drew no %r" % id
    return got


def _tap(drv, box):
    x, y, w, h = box
    gx, gy = drv.ws.wm.viewport()[:2] if drv.ws.run.app_window_canvas else (0, 0)
    drv.click(gx + x + w // 2, gy + y + h // 2)
    _frames(drv)


def _seed(ws, *names):
    for n in names:
        moy_carts.save_file("docs", n, "body of " + n, ws.carts_root)


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------

def test_a_game_opened_over_notes_runs_on_its_own_draw(tmp_path):
    """A run started over Notes' (no exit between them) closes Notes' UI
    tree: the game's frames are its own `_draw`, never the page's."""
    ws = build_ws(tmp_path)
    _ns, drv = _open(ws)
    assert ws.run.player.tree is not None
    assert select_on_home(ws, "Star Catcher") is not None
    ws.open()
    _frames(drv, 6)
    assert ws.run.player.cart_error is None, ws.run.player.cart_error
    assert ws.run.player.tree is None


def test_notes_is_the_text_app_and_it_is_an_ordinary_cart(tmp_path):
    ws = build_ws(tmp_path)
    cart = next(c for c in ws.carts.all if c.get("title") == "Notes")
    assert cart.get("type") == "app"
    assert system_api.is_text_app(cart)
    assert ws.spine.is_user_app(cart), "no shell app claims it -- it runs as a cart"
    assert system_api.draws_in_look(cart), "a built-in: it draws in the look"
    assert sum(1 for c in ws.carts.all if system_api.is_text_app(c)) == 1


def test_a_copy_of_notes_draws_inside_the_cart_boundary(tmp_path):
    ws = build_ws(tmp_path)
    cart = dict(next(c for c in ws.carts.all if c.get("title") == "Notes"))
    cart["path"] = str(tmp_path / "my_notes.moy")
    assert not system_api.draws_in_look(cart)


def test_the_page_holds_only_a_handle_and_names_no_engine(tmp_path):
    """The point of the handle: what the cart holds is a SHELL object it was
    handed; a permission it did not ask for, and the engine under the page,
    have no name at all."""
    from runtime.editor_handle import EditorHandle

    ws = build_ws(tmp_path)
    _seed(ws, "one")
    ns, drv = _open(ws)
    assert callable(ns["open_editor"])
    for name in ("carts", "shell", "ui_draw", "uitree_app"):
        assert name not in ns
    _tap(drv, _box(ws, "one/open"))
    assert isinstance(ns["ed"], EditorHandle)
    assert ns["ed"] in ws.run.player.editors, "the run PINS what it opened"


# ---------------------------------------------------------------------------
# the vault
# ---------------------------------------------------------------------------

def test_the_list_is_new_note_then_the_vault_newest_first(tmp_path):
    ws = build_ws(tmp_path)
    _seed(ws, "older", "newer")
    ns, _drv = _open(ws)
    assert ns["ed"] is None, "a fresh console lands on the list"
    assert ns["names"] == moy_carts.list_files("docs", ws.carts_root)
    rows = [r.name for r in _s(ws)["notes"]]
    assert rows == [ns["NEW"]] + ns["names"], "New note is the first row"
    assert _s(ws)["view"] == "list"


def test_names_show_bare_for_notes_and_whole_for_other_files(tmp_path):
    ws = build_ws(tmp_path)
    ns, _drv = _open(ws)
    assert ns["shown"]("story_ideas") == "Story ideas"
    assert ns["shown"]("todo.txt") == "todo.txt"
    assert ns["shown"]("hello.py") == "hello.py"


def test_new_note_asks_a_name_and_makes_the_note(tmp_path):
    ws = build_ws(tmp_path)
    ns, drv = _open(ws)
    _type(drv, "n")
    assert _s(ws)["asking"] == "new"
    _type(drv, "milk")
    assert _s(ws)["typed"] == "milk"
    _type(drv, [0x0D])                         # Enter makes
    ed = ns["ed"]
    assert _s(ws)["asking"] == "none" and ed is not None and ed.name() == "milk"
    _type(drv, "eggs")                         # into the note: its text editor has the keys
    assert ed.text() == "eggs"
    ws.run.player.face.back()                  # leaves the note, saving it
    _frames(drv)
    assert ns["ed"] is None
    assert moy_carts.load_file("docs", "milk", ws.carts_root) == "eggs"
    assert "milk" in ns["names"]


def test_a_name_keeps_its_extension_and_picks_the_mode(tmp_path):
    ws = build_ws(tmp_path)
    ns, drv = _open(ws)
    for name, mode in (("todo.txt", "text"), ("data.json", "json"), ("hi.py", "code")):
        _act(ws, drv, "new")
        _type(drv, name)
        _type(drv, [0x0D])
        assert (ns["ed"].name(), ns["ed"].mode()) == (name, mode), name
        _act(ws, drv, "close")


def test_the_dialog_cancels_by_esc_and_by_its_button(tmp_path):
    ws = build_ws(tmp_path)
    ns, drv = _open(ws)
    _type(drv, "n")
    ws.run.player.face.back()
    _frames(drv)
    assert _s(ws)["asking"] == "none"
    _type(drv, "n")
    _tap(drv, _box(ws, "Cancel"))
    assert _s(ws)["asking"] == "none" and ns["ed"] is None


def test_nothing_under_the_dialog_takes_a_tap(tmp_path):
    ws = build_ws(tmp_path)
    _seed(ws, "behind")
    ns, drv = _open(ws)
    row = _box(ws, "behind/open")
    _type(drv, "n")
    _tap(drv, row)
    assert ns["ed"] is None and _s(ws)["asking"] == "new"


def test_a_row_opens_its_note_by_a_tap_and_by_its_key(tmp_path):
    ws = build_ws(tmp_path)
    _seed(ws, "story")
    ns, drv = _open(ws)
    _tap(drv, _box(ws, "story/open"))
    assert ns["ed"].name() == "story"
    assert ns["ed"].text() == "body of story"
    assert _s(ws)["view"] == "note"
    ws.run.player.face.back()
    _frames(drv)
    assert ns["ed"] is None and _s(ws)["view"] == "list"
    _press(drv, "a")                           # the focused row: the note's, where it closed
    assert ns["ed"] is not None and ns["ed"].name() == "story"


def test_the_vaults_verbs_trash_duplicate_and_rename_the_current_row(tmp_path):
    ws = build_ws(tmp_path)
    _seed(ws, "gone", "kept", "draft")
    ns, drv = _open(ws)
    _act(ws, drv, "trash", next(r for r in _s(ws)["notes"] if r.name == "gone"))
    assert "gone" not in ns["names"] and "kept" in ns["names"]
    assert ("docs", "gone") in [tuple(t[:2]) for t in moy_carts.trash_list(ws.carts_root)]
    _act(ws, drv, "duplicate", next(r for r in _s(ws)["notes"] if r.name == "kept"))
    assert len(ns["names"]) == 3
    _act(ws, drv, "rename", next(r for r in _s(ws)["notes"] if r.name == "draft"))
    assert _s(ws)["asking"] == "rename" and _s(ws)["typed"] == "Draft"
    _type(drv, [0x08] * 5 + list("final"))
    _type(drv, [0x0D])
    assert "final" in ns["names"] and "draft" not in ns["names"]
    _act(ws, drv, "rename", next(r for r in _s(ws)["notes"] if r.name == ns["NEW"]))
    assert _s(ws)["asking"] == "none", "New note's row has no name to change"


def test_the_vaults_verbs_answer_their_keys(tmp_path):
    ws = build_ws(tmp_path)
    _seed(ws, "twin")
    ns, drv = _open(ws)
    assert _s(ws)["cur"] == "twin"
    _type(drv, [0x04])                         # Ctrl+D
    assert len(ns["names"]) == 2
    _type(drv, "t")                            # T: to the Trash
    assert len(ns["names"]) == 1


def test_an_empty_vault_is_an_empty_page_whose_verb_makes_a_note(tmp_path):
    ws = build_ws(tmp_path)
    ns, drv = _open(ws)
    for n in list(ns["names"]):
        moy_carts.delete_file("docs", n, ws.carts_root)
    _act(ws, drv, "opened")
    assert _s(ws)["view"] == "empty"
    _tap(drv, _box(ws, "new"))
    assert _s(ws)["asking"] == "new"


# ---------------------------------------------------------------------------
# a note open
# ---------------------------------------------------------------------------

def test_the_tools_undo_and_redo_and_the_title_names_the_note_and_its_kind(tmp_path):
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "u", "start", ws.carts_root)
    ns, drv = _open(ws)
    _act(ws, drv, "open_name", "u")
    ed = ns["ed"]
    assert _s(ws)["title"] == "U · Markdown" and _s(ws)["status"] == "", "the kind beside the name"
    _type(drv, "ab")
    assert ed.text() == "abstart"
    _tap(drv, _box(ws, "undo"))
    assert ed.text() == "start"
    _tap(drv, _box(ws, "redo"))
    assert ed.text() == "abstart"


def test_the_tools_row_ends_at_its_last_tool_while_nothing_is_refused(tmp_path):
    """The note's kind is the title's; the tools' status cell, which says a
    refusal, draws nothing while there is none (a row's status with no words),
    so the row past the last tool is the page's ground."""
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "hi.py", "print(1)\n", ws.carts_root)
    ns, drv = _open(ws)
    _act(ws, drv, "open_name", "hi.py")
    assert _s(ws)["title"] == "hi.py · Program" and _s(ws)["status"] == ""
    x, y, w, h = _box(ws, "run")
    cv = ws.sys_canvas
    line = bytes(cv._buf)[(y + h // 2) * cv.w * 2:(y + h // 2 + 1) * cv.w * 2]
    past = {line[i:i + 2] for i in range(2 * (x + w + 2), 2 * cv.w, 2)}
    assert len(past) == 1, "nothing drawn past the last tool"


def test_the_hosts_back_on_the_list_leaves_notes_and_writes_the_note(tmp_path):
    ws = build_ws(tmp_path)
    ns, drv = _open(ws)
    _type(drv, "nkept")
    _type(drv, [0x0D])
    _type(drv, "not lost")
    assert ws.run.player.face.back() is True, "the note closes first"
    _frames(drv)
    assert ws.run.player.face.back() is False, "the list's back is the host's: it leaves"
    ws.spine.exit_to_caller()
    assert ws.wm.top_kind() == "launcher"
    assert moy_carts.load_file("docs", "kept", ws.carts_root) == "not lost"
    assert ws.input.text_mode is False


def test_the_tools_select_copy_paste_and_cut(tmp_path):
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "clip", "abcdef", ws.carts_root)
    ns, drv = _open(ws)
    _act(ws, drv, "open_name", "clip")
    ed = ns["ed"]
    _tap(drv, _box(ws, "select"))
    assert ed.selecting() is True and _s(ws)["selecting"] is True
    ed.nav(3, 0)
    _frames(drv)
    _tap(drv, _box(ws, "copy"))
    ed.select_mode(False)
    ed.nav(3, 0)
    _frames(drv)
    _tap(drv, _box(ws, "paste"))
    assert ed.text() == "abcdefabc"
    ed.select_mode(True)
    ed.nav(-3, 0)
    _frames(drv)
    _tap(drv, _box(ws, "cut"))
    assert ed.text() == "abcdef"


def test_the_note_has_the_keys_and_the_keyboard_types(tmp_path):
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "keys", "x", ws.carts_root)
    ns, drv = _open(ws)
    _act(ws, drv, "open_name", "keys")
    assert ws.run.player.face.typing() is True
    assert ws.run.player.tree.engine.focus_key == "", "no tool holds focus while the note has the keys"
    _type(drv, [0x0D])
    assert ns["ed"].text() == "\nx", "Enter is the note's, never a tool's"


def test_closing_a_note_brings_the_list_back_on_its_row(tmp_path):
    ws = build_ws(tmp_path)
    _seed(ws, *("n%02d" % i for i in range(40)))
    ns, drv = _open(ws)
    _act(ws, drv, "open_name", "n05")
    _act(ws, drv, "close")
    assert ns["ed"] is None and _s(ws)["cur"] == "n05"
    assert ws.run.player.tree.engine.focus_key == "n05/open"


def test_open_link_follows_the_carets_link_and_ticks_its_box(tmp_path):
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "other_one", "the other one", ws.carts_root)
    moy_carts.save_file("docs", "hub", "- [ ] milk\ngo [[Other one]] now", ws.carts_root)
    ns, drv = _open(ws)
    _act(ws, drv, "open_name", "hub")
    _tap(drv, _box(ws, "follow"))
    assert ns["ed"].text().startswith("- [x] milk"), "the caret's line: its box ticked"
    ns["ed"].ed.row = 1
    _tap(drv, _box(ws, "follow"))
    assert ns["ed"].name() == "other_one"


def test_a_tap_in_the_note_places_its_caret(tmp_path):
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "lines", "one\ntwo\nthree", ws.carts_root)
    ns, drv = _open(ws)
    _act(ws, drv, "open_name", "lines")
    v = ws.run.player.tree.engine.views["note"]
    r, lh = v[0], v[3]
    _tap(drv, (r[0], r[1] + 2 * lh, r[2], lh))
    assert ns["ed"].caret()[0] == 2


def test_the_last_note_reopens_on_the_next_launch(tmp_path):
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "kept", "still here", ws.carts_root)
    ns, drv = _open(ws)
    _tap(drv, _box(ws, "kept/open"))
    assert ws.system.get("moybyte.notes_last") == "kept"
    ws.spine.exit_to_caller()
    ns, _drv = _open(ws)
    assert ns["ed"] is not None and ns["ed"].name() == "kept"


def test_the_carts_files_see_no_drawing(tmp_path):
    """The cart is granted `files:documents`: a drawing a note names is not its
    to load."""
    ws = build_ws(tmp_path)
    blob = moy_carts.encode_moyimg(8, 8, bytes((14,)) * 64)
    moy_carts.save_file("drawings", "dragon", blob, ws.carts_root)
    moy_carts.save_file("docs", "art", "look\n![[dragon]]", ws.carts_root)
    ns, drv = _open(ws)
    _tap(drv, _box(ws, "art/open"))
    assert ns["ed"] is not None
    assert not ns["files"].load("dragon")[0], \
        "the CART's own files handle is scoped to docs and sees no drawing"


# ---------------------------------------------------------------------------
# the doors in and out
# ---------------------------------------------------------------------------

def _open_files(ws):
    select_on_home(ws, "Files")
    ws.open()
    _frames(host_app.ConsoleDriver(ws))
    return ws.app("files")


def test_files_opens_a_note_in_notes_and_x_returns_to_files(tmp_path):
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "letter", "dear you", ws.carts_root)
    app = _open_files(ws)
    app.open_place("documents")
    app._act("OPEN", "letter")
    _frames(host_app.ConsoleDriver(ws))
    assert ws.wm.top_is_player() and ws.cart.get("title") == "Notes"
    ed = ws.run.player.ns["ed"]
    assert (ed.name(), ed.text()) == ("letter", "dear you")
    ws.spine.exit_to_caller()
    assert ws.wm.top_kind() == "files", "X returns to whoever asked"


def test_the_request_is_taken_once_and_a_re_run_lands_on_the_list(tmp_path):
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "letter", "dear you", ws.carts_root)
    app = _open_files(ws)
    app.open_place("documents")
    app._act("OPEN", "letter")
    _frames(host_app.ConsoleDriver(ws))
    assert ws._text_request is None
    ws.system.delete("moybyte.notes_last")
    ws.run.player.start(ws.run.project)
    _frames(host_app.ConsoleDriver(ws))
    assert ws.run.player.ns["ed"] is None


# ---------------------------------------------------------------------------
# a program runs from its note, and comes back to it
# ---------------------------------------------------------------------------

def test_a_program_shows_run_and_a_note_does_not(tmp_path):
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "hi.py", "print('hi')\n", ws.carts_root)
    moy_carts.save_file("docs", "hi.lua", "print('hi')\n", ws.carts_root)
    moy_carts.save_file("docs", "list", "milk", ws.carts_root)
    ns, drv = _open(ws)
    for name in ("hi.py", "hi.lua"):
        _act(ws, drv, "open_name", name)
        assert ns["ed"].can_run() is True
        assert _box(ws, "run")[0] > _box(ws, "paste")[0], "Run stands after the clipboard's tools"
    _act(ws, drv, "open_name", "list")
    assert ns["ed"].can_run() is False
    assert ws.run.player.face.host().box("run") is None


def test_run_saves_the_program_runs_it_and_comes_back_to_it(tmp_path):
    """Opened from Files: Run writes the edit, the script runner starts on
    THAT document, and its exit lands back in Notes on the same program, the
    caret where it was -- whose own X still goes back to Files."""
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "hi.py", "print('hello')\n", ws.carts_root)
    app = _open_files(ws)
    app.open_place("documents")
    app._act("OPEN", "hi.py")
    drv = host_app.ConsoleDriver(ws)
    _frames(drv)
    ed = ws.run.player.ns["ed"]
    ed.nav(0, 1)
    _type(drv, "print('again')")
    caret = ed.caret()
    assert ed.dirty()
    _tap(drv, _box(ws, "run"))
    assert ws.cart.get("type") == "script" and ws.cart.get("title") == "hi"
    assert moy_carts.load_file("docs", "hi.py", ws.carts_root) == \
        "print('hello')\nprint('again')"
    assert ws.script_console.text() == "hello\nagain"
    ws.spine.exit_to_caller()
    _frames(drv)
    assert ws.wm.top_is_player() and ws.cart.get("title") == "Notes"
    back = ws.run.player.ns["ed"]
    assert back is not ed and back.name() == "hi.py"
    assert back.caret() == caret
    ws.spine.exit_to_caller()
    assert ws.wm.top_kind() == "files", "Notes' own X still returns to Files"


def test_a_program_that_does_not_parse_says_so_in_the_console(tmp_path):
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "bad.py", "def (\n", ws.carts_root)
    ns, drv = _open(ws)
    _act(ws, drv, "open_name", "bad.py")
    _tap(drv, _box(ws, "run"))
    assert ws.cart.get("type") == "script"
    assert "SyntaxError" in ws.script_console.text()
    ws.spine.exit_to_caller()
    _frames(drv)
    assert ws.cart.get("title") == "Notes"
    assert ws.run.player.ns["ed"].name() == "bad.py"


def test_a_run_that_cannot_start_badges_the_program_and_stays(tmp_path, monkeypatch):
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "gone.py", "print(1)\n", ws.carts_root)
    ns, drv = _open(ws)
    _act(ws, drv, "open_name", "gone.py")
    ed = ns["ed"]
    monkeypatch.setattr(ws, "run_script", lambda kind, name: (False, "CAN'T READ IT"))
    _tap(drv, _box(ws, "run"))
    assert ws.cart.get("title") == "Notes" and ns["ed"] is ed
    assert ed.badge() == "CAN'T READ IT"
    assert _s(ws)["status"] == "CAN'T READ IT"


def test_home_from_the_script_forgets_the_way_back(tmp_path):
    ws = build_ws(tmp_path)
    moy_carts.save_file("docs", "hi.py", "print(1)\n", ws.carts_root)
    ns, drv = _open(ws)
    _act(ws, drv, "open_name", "hi.py")
    _tap(drv, _box(ws, "run"))
    assert ws.cart.get("type") == "script"
    ws.home.go_home()
    assert ws._script_return is None
    assert not ws.wm.top_is_player()


# ---------------------------------------------------------------------------
# the desk: a window is the app's surface
# ---------------------------------------------------------------------------

def _desk(tmp_path):
    ws = build_desktop_ws(tmp_path, font_scale=1, panel_diagonal_in=7.0)   # the P4: a desk
    _seed(ws, "story")
    ns, drv = _open(ws)
    return ws, ns, drv


def test_on_the_desk_the_window_is_the_page_with_no_bar_inside_it(tmp_path):
    ws, ns, drv = _desk(tmp_path)
    assert ws.run.app_window_canvas and ws.run.app_full_canvas
    win = ws.wm.windows["desktop"]
    cx, cy, cw, ch = win.content_rect()
    assert ns["content_rect"]() == (0, 0, cw, ch), "the page begins under the title strip"
    assert ws.wm.viewport() == (cx, cy, 1)
    assert ws.run.canvas.w >= cw and ws.run.canvas.h >= ch


def test_the_desk_shows_the_vault_beside_the_note(tmp_path):
    ws, ns, drv = _desk(tmp_path)
    row = _box(ws, "story/open")
    _tap(drv, row)
    assert ns["ed"].name() == "story"
    sel = _box(ws, "select")
    assert sel[0] > row[0] + row[2], "the note's tools stand beside the vault"
    assert ws.run.player.face.host().box("story/open") is not None, "the vault stays"


def test_new_note_over_an_open_note_takes_the_keys_and_its_buttons_work(tmp_path):
    """Owner report 2026-10-31: New note tapped while a note was open left the
    keyboard on the note, so the name was typed into the note."""
    ws, ns, drv = _desk(tmp_path)
    _act(ws, drv, "open_name", "story")
    _tap(drv, _box(ws, ns["NEW"] + "/open"))
    assert _s(ws)["asking"] == "new"
    _type(drv, "plan")
    assert _s(ws)["typed"] == "plan"
    assert ns["ed"].text() == "body of story", "nothing typed into the note"
    _tap(drv, _box(ws, "Make"))
    assert _s(ws)["asking"] == "none" and ns["ed"].name() == "plan"
    assert _s(ws)["cur"] == "plan", "the vault stands on the new note"


def test_the_canvas_goes_back_when_notes_closes(tmp_path):
    ws, ns, drv = _desk(tmp_path)
    ws.spine.exit_to_caller()
    _frames(drv)
    assert not ws.run.app_window_canvas and not ws.run.app_full_canvas


def test_on_the_desk_run_comes_back_to_the_notes_window(tmp_path):
    ws, ns, drv = _desk(tmp_path)
    moy_carts.save_file("docs", "hi.py", "print('desk')\n", ws.carts_root)
    _act(ws, drv, "open_name", "hi.py")
    _tap(drv, _box(ws, "run"))
    assert ws.cart.get("type") == "script"
    assert ws.script_console.text() == "desk"
    ws.spine.exit_to_caller()
    _frames(drv)
    assert ws.wm.top_is_player() and ws.cart.get("title") == "Notes"
    assert ws.run.player.ns["ed"].name() == "hi.py"
    assert ws.run.app_window_canvas, "back in its window"
