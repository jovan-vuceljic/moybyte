"""The Files system app (#108, docs/history/look_2026-10.md step 21): the places and
a place's files in columns, drawn with the public UI API's verbs; its verbs
(rename in a dialog, copy, trash, restore, and emptying the Trash, which asks
first), the copy-on-use reuse actions, and Paint's shared OPEN picker and
autosave riding the same layer."""

from pathlib import Path

import pytest

from runtime import files_app, host_app, moy_carts
from runtime import uitree as ui
from ws_helpers import quiesce, shelf, select_on_home  # noqa: E402
from ws_helpers import build_ws as _ws

ROOT = Path(__file__).resolve().parent.parent
_DT = 1 / 30


def _open_app(ws, title):
    select_on_home(ws, title)
    ws.open()
    ws.input.begin_frame()
    ws.frame(_DT)


def _seed_drawing(carts, name, w=320, h=240, color=14):
    blob = moy_carts.encode_moyimg(w, h, bytes((color,)) * (w * h))
    return moy_carts.save_file("drawings", name, blob, carts)


def _files(ws):
    """Files opened on the home, its first frames drawn: (app, driver)."""
    _open_app(ws, "Files")
    drv = host_app.ConsoleDriver(ws)
    _frames(drv)
    return ws.app("files"), drv


def _frames(drv, n=3):
    for _ in range(n):
        drv.ws.mark_dirty()
        drv.frame(_DT)


def _press(drv, *keys):
    for k in keys:
        drv.press(k)
        _frames(drv)


def _type(drv, text):
    """Typed keys, each its own press: a frame with no key between two."""
    for ch in text:
        drv.type_char(ord(ch) if isinstance(ch, str) else ch)
        _frames(drv, 2)


def _row_xy(app, i, places=False):
    """The middle of row `i` of the files (or the places) the app drew last
    frame."""
    rid = app.shown_places()[i][0] + "/open_place" if places else files_app.row_id(i) + "/open"
    x, y, w, h = app.page_host().box(rid)
    return x + w // 2, y + h // 2


def _focus(app):
    """The focused stop's id: a row's "r<i>/open", a place's "<key>/open_place",
    a field's state name, a button's action."""
    return app.engine.focus_key


def _tap(drv, x, y):
    drv.click(x, y)
    _frames(drv)


def _art(ws, drv):
    """The Pictures place's page, reached as a person does: down twice, Enter."""
    app = ws.app("files")
    _press(drv, "down", "down", "a")
    assert (app.place, app.level) == (files_app.PICTURES, "files")
    return app


# -- the app and its pages ---------------------------------------------------------

def test_files_cart_is_well_formed_and_the_app_opens(tmp_path):
    import json
    man = json.loads((ROOT / "system_carts" / "moybyte.files.moy" / "manifest.json")
                     .read_text(encoding="utf-8"))
    assert man["moybyte"]["type"] == "app" and man["version"] >= 1
    assert "files" in man["moybyte"]["permissions"]
    compile((ROOT / "system_carts" / "moybyte.files.moy" / "main.py").read_text(),
            "main.py", "exec")

    ws = _ws(tmp_path)
    app, _drv = _files(ws)
    assert ws.cart_error is None
    assert ws.wm.top_kind() == "files"
    assert (app.place, app.level) == (files_app.PROJECTS, "places")
    assert _focus(app).endswith("/open_place")


def test_the_handheld_walks_places_then_files_and_b_comes_back(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _seed_drawing(carts, "dragon")
    app, drv = _files(ws)
    _art(ws, drv)
    assert app.names_shown() == ["dragon"]
    assert _focus(app).endswith("/open")
    _press(drv, "b")
    assert app.level == "places" and app.place == files_app.PICTURES
    assert ws.wm.top_kind() == "files", "b left the page, not the app"


def test_a_tap_on_a_place_opens_it(tmp_path):
    ws = _ws(tmp_path)
    app, drv = _files(ws)
    keys = [p[0] for p in app.shown_places()]
    _tap(drv, *_row_xy(app, keys.index(files_app.TRASH), True))
    assert (app.place, app.level) == (files_app.TRASH, "files")


def test_the_places_count_their_files_and_themes_show_once_there_are_any(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _seed_drawing(carts, "one")
    _seed_drawing(carts, "two")
    app, _drv = _files(ws)
    assert app._count(files_app.PICTURES) == 2
    assert app._count(files_app.PROJECTS) == len(app._nav.projects())
    assert files_app.THEMES not in [p[0] for p in app.shown_places()]


def test_a_tap_on_a_row_opens_it(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _seed_drawing(carts, "one")
    _seed_drawing(carts, "two")
    app, drv = _files(ws)
    _art(ws, drv)
    assert app.cur == 0
    _tap(drv, *_row_xy(app, 1))
    assert app.sel_name() == app.names_shown()[1]
    assert ws.wm.top_kind() == "artwork"
    assert ws.artwork.doc_name() == app.names_shown()[1]


def test_the_verbs_are_the_current_rows(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _seed_drawing(carts, "dragon")
    moy_carts.save_file("docs", "note", "hi", carts)
    moy_carts.save_file("docs", "tool.py", "print(1)", carts)
    app, _drv = _files(ws)
    app.open_place(files_app.PICTURES)
    assert app._action_labels() == app.PICTURE_ACTIONS
    app.open_place(files_app.DOCUMENTS, keep="note")
    assert app._action_labels() == app.DOC_ACTIONS
    app.select("tool.py")
    assert app._action_labels()[0] == "RUN"
    app.open_place(files_app.PROJECTS)
    assert app._action_labels() == app.PROJECT_ACTIONS
    app.open_place(files_app.TRASH)
    assert app._action_labels() == (), "an empty Trash has no row to restore"


# -- Downloads ---------------------------------------------------------------------

def _arrive(carts, name, data):
    """A file landed in Downloads as a beam lands one: written there whole."""
    d = Path(moy_carts.files_root(carts)) / "Downloads"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(data if isinstance(data, bytes) else data.encode())


def test_downloads_lists_what_arrived_under_its_whole_name_and_type(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _arrive(carts, "Trip Notes.md", "# trip")
    _arrive(carts, "photo.jpg", b"\xff\xd8\xff")
    _arrive(carts, "tool.py", "print(1)")
    _arrive(carts, "readme", "plain")
    _arrive(carts, ".tool.py.moybak", "a store backup")
    _arrive(carts, ".hidden", "x")
    app, drv = _files(ws)
    keys = [p[0] for p in app.shown_places()]
    _press(drv, *(["down"] * keys.index(files_app.DOWNLOADS) + ["a"]))
    assert (app.place, app.level) == (files_app.DOWNLOADS, "files")
    assert app._count(files_app.DOWNLOADS) == 4
    kinds = {r[0]: r[2] for r in app.rows}
    assert kinds == {"Trip Notes.md": "Note", "photo.jpg": "JPG", "tool.py": "Script",
                     "readme": "File"}
    for name in kinds:
        app.select(name)
        assert app._action_labels() == app.DOWNLOAD_ACTIONS, "no RUN, whatever it is"


def test_a_download_opens_as_data_in_the_app_its_type_takes(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _arrive(carts, "tool.py", "print('ran')")
    _arrive(carts, "photo.jpg", b"\xff\xd8\xff")
    app, drv = _files(ws)
    app.open_place(files_app.DOWNLOADS, keep="photo.jpg")
    app._act("OPEN")
    assert app.status == "No app opens it"
    app.open_place(files_app.DOWNLOADS, keep="tool.py")
    app._act("OPEN")
    _frames(drv)
    assert ws.cart.get("title") == "Notes", "a script that arrived is text to edit"
    assert ws.cart_error is None


def test_a_download_is_sent_on_as_it_arrived(tmp_path, monkeypatch):
    from runtime import intents
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _arrive(carts, "Trip Notes.md", "# trip")
    sent = []
    monkeypatch.setattr(intents.INTENTS, "beam_ok", lambda: True)
    monkeypatch.setattr(intents.INTENTS, "beam", lambda item: sent.append(item) or True)
    app, _drv = _files(ws)
    app.open_place(files_app.DOWNLOADS, keep="Trip Notes.md")
    assert app._action_labels() == ("OPEN", "WITH", "SEND", "DEL")
    app._act("SEND")
    assert sent == ["Downloads/Trip Notes.md"]


def test_a_download_deletes_to_the_trash_and_restores(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _arrive(carts, "My Song.mp3", b"ID3")
    app, _drv = _files(ws)
    app.open_place(files_app.DOWNLOADS)
    app._act("DEL", "My Song.mp3")
    assert app.status == "Moved to the Trash" and app.names_shown() == []
    assert ("downloads", "My Song.mp3") in app.trash
    _arrive(carts, "My Song.mp3", b"ID3 again")
    app._refresh()
    app._act("DEL", "My Song.mp3")
    assert ("downloads", "My Song_2.mp3") in app.trash, "a collision before the extension"
    app.open_place(files_app.TRASH)
    app._act("RESTORE", "My Song_2.mp3")
    assert moy_carts.list_files("downloads", carts) == ["My Song_2.mp3"]


def test_no_folder_grant_reaches_downloads(tmp_path):
    """The shell's files grant (no folder) lists Downloads; an app's grant for
    a shared folder is refused it, and `files:downloads` grants nothing."""
    from runtime import moy_app
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _arrive(carts, "a.txt", "a")
    shell = ws.app_context("local.shellish", ("files",), "local.shellish")
    assert shell.files.list("downloads")[0] == ["a.txt"]
    for kind in ("docs", "drawings", "music", "recordings"):
        ctx = ws.app_context("local.app_" + kind, ("files",), "local.app_" + kind,
                             run=True, kind=kind)
        with pytest.raises(ValueError):
            ctx.files.list("downloads")
    assert moy_app.policy(["files:downloads"]) == ((), None)


# -- the verbs ---------------------------------------------------------------------

def test_gallery_lists_rename_copy_trash_restore(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _seed_drawing(carts, "dragon")
    app, drv = _files(ws)
    _art(ws, drv)
    assert "dragon" in app.names_shown()

    # COPY numbers upward, and the copy is current
    app._act("COPY", "dragon")
    assert "dragon_2" in app.names_shown() and app.sel_name() == "dragon_2"
    assert app.status == "Duplicated", "the verb's word, Duplicate, in its report (R4-24)"

    # RENAME in a dialog: focus opens in its field, the keys type, Enter commits
    app._act("NAME")
    _frames(drv)
    assert app.dialog == "rename" and app.rename_text == "dragon_2"
    assert _focus(app) == "typed"
    _type(drv, "\b\b")
    assert app.rename_text == "dragon"
    _type(drv, "_tower")
    _type(drv, "\r")
    assert app.dialog is None
    assert "dragon_tower" in app.names_shown() and "dragon_2" not in app.names_shown()
    assert app.sel_name() == "dragon_tower"

    # DELETE -> the restorable Trash -> RESTORE
    app._act("DEL", "dragon_tower")
    assert "dragon_tower" not in app.names_shown()
    assert ("drawings", "dragon_tower") in app.trash
    app.open_place(files_app.TRASH)
    assert app.names_shown() == ["dragon_tower"]
    app._act("RESTORE", "dragon_tower")
    assert moy_carts.load_file("drawings", "dragon_tower", carts) is not None
    assert ("drawings", "dragon_tower") not in app.trash


def test_rename_is_cancelled_by_b_with_or_without_an_edit(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _seed_drawing(carts, "dragon")
    app, drv = _files(ws)
    _art(ws, drv)
    app._act("NAME")
    _frames(drv)
    _type(drv, "xyz")
    _press(drv, "down")                    # in the open edit: the caret to the end
    assert _focus(app) != "Cancel"
    _press(drv, "b")                       # the dialog's Back: its Cancel
    assert app.dialog is None and app.names_shown() == ["dragon"]
    assert _focus(app).endswith("/open"), "focus went back to the list"
    app._act("NAME")
    _frames(drv)
    _press(drv, "b")
    assert app.dialog is None and app.names_shown() == ["dragon"]


def test_nothing_under_a_dialog_takes_input(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _seed_drawing(carts, "one")
    _seed_drawing(carts, "two")
    app, drv = _files(ws)
    _art(ws, drv)
    row = _row_xy(app, 1)
    app._act("NAME")
    _frames(drv)
    _tap(drv, *row)
    assert app.cur == 0 and app.dialog == "rename", "the list under it took the tap"


def test_backspace_on_the_list_moves_the_current_file_to_the_trash(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _seed_drawing(carts, "dragon")
    app, drv = _files(ws)
    _art(ws, drv)
    _type(drv, "\b")
    assert app.names_shown() == []
    assert ("drawings", "dragon") in app.trash
    assert app.status == "Moved to the Trash"


def test_emptying_the_trash_asks_first_and_cancel_is_where_focus_opens(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _seed_drawing(carts, "dragon")
    app, drv = _files(ws)
    _art(ws, drv)
    app._act("DEL", "dragon")
    app.open_place(files_app.TRASH)
    app._act("EMPTY")
    _frames(drv)
    assert app.dialog == "empty" and _focus(app) == "Cancel"
    assert app.trash, "nothing goes before the answer"
    _press(drv, "a")
    assert app.dialog is None and app.trash
    app._act("EMPTY")
    _frames(drv)
    _press(drv, "right", "a")
    assert app.dialog is None and not app.trash
    assert moy_carts.load_file("drawings", "dragon", carts) is None


def test_reuse_actions_are_copies(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _seed_drawing(carts, "dragon", color=20)
    app, drv = _files(ws)
    app.open_place(files_app.PICTURES, keep="dragon")

    # WALL: copy-on-set -- the wallpaper copy + My Art bg hold the pixels
    # (plus a #108 phase-2 provenance stamp, so compare decoded pixels).
    app._act("WALL", "dragon")
    ws.look.tick(0.0)                      # the change shows at the next frame
    assert ws.look.wallpaper_id == "moybyte.wallpaper" == ws.look.PICTURE
    px = moy_carts.decode_moyimg(moy_carts.load_file("drawings", "dragon", carts))
    # ...and the theme carries it: My Art's copy is custom's picture.
    assert moy_carts.decode_moyimg(ws.look.picture().decode()) == px
    assert moy_carts.decode_moyimg(moy_carts.load_artwork(carts)) == px
    wall = next(c for c in moy_carts.scan(carts) if c["title"] == "Wallpaper")
    assert moy_carts.decode_moyimg(wall["images"]["bg"]) == px
    assert moy_carts.read_provenance(moy_carts.load_artwork(carts))[0] == \
        "drawings/dragon"

    # Editing the drawing afterwards changes NOTHING until sent again.
    _seed_drawing(carts, "dragon", color=33)
    assert moy_carts.decode_moyimg(moy_carts.load_artwork(carts)) == px

    # GAME: a 320x240 copy lands in the project picked in the dialog.
    app._act("GAME", "dragon")
    assert app.dialog == "game"
    # System-app identities are never offered as projects.
    assert "Files" not in app.project_names
    assert "Paint" not in app.project_names
    assert "Calc" not in app.project_names
    _frames(drv)
    app._in(ui.focus, "%d/add" % app.project_names.index("Star Catcher"))
    _frames(drv)
    _press(drv, "a")                       # Enter on the focused target adds it
    assert app.dialog is None
    target = next(c for c in moy_carts.scan(carts) if c["title"] == "Star Catcher")
    assert "bg" in target["images"]
    assert app.status == "Added to Star Catcher"


def test_delete_of_the_open_drawing_cannot_break_paint(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    name = _seed_drawing(carts, "doomed")
    ws.artwork.open_named(name)
    app, _drv = _files(ws)
    app.open_place(files_app.PICTURES)
    app._act("DEL", name)
    # Paint now opens a fresh canvas under the stale pointer -- no crash.
    _open_app(ws, "Paint")
    assert ws.cart_error is None
    assert ws.wm.top_kind() == "artwork"


def test_paints_open_is_my_art_and_its_pick_switches_documents(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _seed_drawing(carts, "one", color=11)
    _seed_drawing(carts, "two", color=12)
    _open_app(ws, "Paint")
    app = ws.app("artwork")
    app._verb("open")                    # More's Open...: the drawings' page
    ws.frame(_DT)
    assert ws.wm.top_kind() == "myart"
    art = ws.app("myart")
    assert set(art.drawings) >= {"one", "two"}
    art._verb("open", "two")
    ws.frame(_DT)
    assert ws.wm.top_kind() == "artwork"
    assert ws.artwork.doc_name() == "two"
    assert app.doc.pix[0] == 12


def test_paint_autosaves_on_the_idle_debounce(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _open_app(ws, "Paint")
    app = ws.app("artwork")
    assert ws.artwork.doc_name() is None       # nothing saved yet
    app.doc.snapshot()
    app.doc.put(5, 5, 14)
    app.doc.finish()
    app._mark_changed()
    app.draw(app.AUTOSAVE_S + 0.1)             # the debounce flushes
    name = ws.artwork.doc_name()
    assert name is not None
    data = moy_carts.decode_moyimg(moy_carts.load_file("drawings", name, carts))
    assert data[2][5 * app.doc.W + 5] == 14


def test_new_drawing_keeps_the_old_file(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _open_app(ws, "Paint")
    app = ws.app("artwork")
    app.doc.snapshot()
    app.doc.put(1, 1, 22)
    app.doc.finish()
    app._mark_changed()
    app._verb("new")                           # New drawing asks nothing
    names = moy_carts.list_files("drawings", carts)
    assert len(names) == 1                     # the old drawing kept its file
    old = moy_carts.decode_moyimg(moy_carts.load_file("drawings", names[0], carts))
    assert old[2][1 * 320 + 1] == 22
    assert ws.artwork.doc_name() not in names  # fresh doc, unwritten until drawn on


def test_files_is_app_rejects_lookalikes(tmp_path):
    ws = _ws(tmp_path)
    real = next(c for c in ws.carts.all if c.get("title") == "Files")
    assert ws.app("files").is_app(real)
    fake = dict(real)
    fake["title"] = "files"
    assert not ws.app("files").is_app(fake)
    fake2 = dict(real)
    fake2["permissions"] = ["graphics", "input"]
    assert not ws.app("files").is_app(fake2)


# -- provenance: "used in:" + the one-tap UPDATE (#108 phase 2) -------------------

def test_usage_tracks_stale_copies_and_update_clears_them(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _seed_drawing(carts, "dragon", color=20)
    # Copy it into a project (with a provenance stamp) + set as wallpaper.
    copies = ws.app("files")._copies
    ti = copies.targets().index("Star Catcher")
    assert copies.attach(ti, "dragon")
    assert copies.set_wallpaper("dragon")

    rows = copies.usage("dragon")
    labels = {r["label"] for r in rows}
    assert "Star Catcher" in labels and "WALLPAPER" in labels
    assert all(not r["stale"] for r in rows)          # fresh copies

    # Edit the source drawing: every copy is now stale (pull-based detection).
    _seed_drawing(carts, "dragon", color=33)
    rows = copies.usage("dragon")
    assert all(r["stale"] for r in rows)

    # UPDATE (send again) the project copy -> only it clears.
    game_row = next(r for r in rows if r["label"] == "Star Catcher")
    assert copies.resend(game_row, "dragon")
    rows = {r["label"]: r["stale"] for r in copies.usage("dragon")}
    assert rows["Star Catcher"] is False
    assert rows["WALLPAPER"] is True                   # not re-sent yet


def test_files_app_use_action_lists_and_resends(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    _seed_drawing(carts, "dragon", color=20)
    ti = ws.artwork.targets().index("Star Catcher")
    ws.artwork.attach(ti, "dragon")
    app, drv = _files(ws)
    app.open_place(files_app.PICTURES, keep="dragon")
    app._act("USE", "dragon")
    assert app.dialog == "used"
    assert any(r["label"] == "Star Catcher" for r in app.used_rows)
    # Make it stale, then send it again from the dialog.
    _seed_drawing(carts, "dragon", color=33)
    app._act("USE", "dragon")
    idx = next(i for i, r in enumerate(app.used_rows)
               if r["label"] == "Star Catcher")
    assert app.used_rows[idx]["stale"] is True
    app._resend(idx)
    assert app.used_rows[idx]["stale"] is False
    _frames(drv)
    _press(drv, "b")
    assert app.dialog is None


def test_docs_and_tables_kinds_get_the_open_action(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    moy_carts.save_file("docs", "note", "hi", carts)
    app, _drv = _files(ws)
    app.open_place(files_app.DOCUMENTS)
    assert "OPEN" in app._action_labels()


def test_send_sprites_to_files_producer(tmp_path):
    carts = str(tmp_path / "carts")
    ws = _ws(tmp_path)
    # Open a project so ws.run.project.sheet is a real sprite sheet.
    ws.carts_store.create("Doodle", carts, type="game")
    ws.carts.apply(shelf(carts))
    ws.open_in_editor(next(c for c in ws.carts.all if c.get("title") == "Doodle"))
    ws.run.project.sheet.pset(0, 0, 9)
    name = ws.saves.send_sprites_to_files()
    assert name in moy_carts.list_files("sprites", carts)
    assert moy_carts.load_file("sprites", name, carts) == ws.run.project.sheet.to_hex()


# -- painting ----------------------------------------------------------------------

def test_a_settled_files_page_paints_nothing(tmp_path):
    """The verbs' settled answer, end to end: with no input the redraw gate
    draws no frame, and a press that moves nothing draws one frame of the
    same pixels and asks for none after it."""
    ws = _ws(tmp_path)
    _open_app(ws, "Files")
    quiesce(ws)
    drv = host_app.ConsoleDriver(ws)
    for _ in range(4):
        drv.frame(_DT)
    drawn = ws.frame_state.frames_drawn
    for _ in range(10):
        drv.frame(_DT)
    assert ws.frame_state.frames_drawn == drawn, "an idle Files page painted"
    before = bytes(ws.sys_canvas._buf)
    drv.press("left")                   # on a place with nothing beside it
    for _ in range(6):
        drv.frame(_DT)
    assert ws.frame_state.frames_drawn == drawn + 1, "one frame for the press, then none"
    assert bytes(ws.sys_canvas._buf) == before


# -- the desk ----------------------------------------------------------------------

def test_the_desk_shows_the_places_beside_the_files(tmp_path):
    carts = str(tmp_path / "carts")
    _seed_drawing(carts, "dragon")
    ws = host_app.build_workstation(carts, sys_size=(1024, 600), panel_diagonal_in=7.0,
                                    font_scale=1, windowed=True)
    ws.home.open_desk()
    ws.spine.open_app(ws.app("files"))
    drv = host_app.ConsoleDriver(ws)
    _frames(drv, 4)
    app = ws.app("files")
    assert _focus(app).endswith("/open"), "the desk opens on the projects' rows"
    host = app.page_host()
    assert host.box("projects/open_place") is not None and host.box("r0/open") is not None
    app._in(ui.focus, "projects/open_place")
    _frames(drv)
    _press(drv, "down", "down")
    assert app.place == files_app.PICTURES and app.names_shown() == ["dragon"]
    assert _focus(app).endswith("/open_place"), "a place opens beside the list, focus stays"


def test_the_foot_is_a_bar_with_the_primary_verb_at_its_right(tmp_path):
    """The current row's verbs sit at the foot's right, the one Enter does
    (Open) last, and no mouse button wears a key's sign."""
    ws = _ws(tmp_path)
    app, drv = _files(ws)
    _press(drv, "a")
    play, opn = app.page_host().box("v_play"), app.page_host().box("v_open")
    assert play is not None and opn is not None
    assert play[0] < opn[0], "Open, the primary, is right of Play"
    assert files_app.VERBS[-1][0] == "OPEN", "Open, Enter's verb, last"
    assert files_app._ICONS["OPEN"] != "enter"


def test_the_verbs_are_icons_at_the_foots_end_each_word_its_tooltip(tmp_path):
    """On the desk and the handheld the current row's verbs are icon buttons
    side by side at the foot's end (look="end", alone=True), Open last
    against the end; on the desk a mouse resting on one shows its word as
    the tooltip (moy_ui_api_tip), and nowhere else does."""
    from array import array
    for desk in (False, True):
        if desk:
            ws = host_app.build_workstation(str(tmp_path / "desk"), sys_size=(1024, 600),
                                            panel_diagonal_in=7.0, font_scale=1, windowed=True)
            ws.home.open_desk()
            ws.spine.open_app(ws.app("files"))
            drv = host_app.ConsoleDriver(ws)
            _frames(drv, 4)
            app = ws.app("files")
        else:
            app, drv = _files(_ws(tmp_path / "hand"))
            _press(drv, "a")
        host = app.page_host()
        boxes = [host.box(f) for v, f in files_app.VERBS if host.box(f) is not None]
        assert len(boxes) >= 2 and boxes[-1] == host.box("v_open")
        for (x, y, w, h), (x2, y2, _w2, _h2) in zip(boxes, boxes[1:]):
            assert y == y2 and x + w < x2, boxes
        assert all(w <= 40 and w <= 2 * h for _x, _y, w, h in boxes), "icons, no words"
        assert boxes[0][0] > drv.ws.sys_canvas.w // 4 or desk, "at the end, not across the foot"
    # a mouse resting over Open, in the window's content
    x, y, w, h = host.box("v_open")
    cx, cy = ws.wm.windows["files"].content_rect()[:2]
    ws.pointer.hovers = True
    ws.pointer.place(cx + x + w // 2, cy + y + h // 2)
    box = array("i", [0] * 4)
    _frames(drv)
    assert host.popped(box), "a mouse resting on Open shows its tooltip"
    ws.pointer.place(cx + x - 200, cy + y - 200)
    _frames(drv)
    assert not host.popped(box), "off the button, none"
