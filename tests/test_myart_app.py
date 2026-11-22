"""My Art (runtime/apps/myart_app.py): the drawings' page, its cards, its menu
and its verbs, on the public UI API (docs/media/look_2026-10/APPS_RESTYLE.md,
My Art)."""

import os

from runtime import artwork, host_app, moy_carts
from ws_helpers import settle_badges  # noqa: E402

_DT = 1.0 / 30.0


def _ws(tmp_path, **kw):
    ws = host_app.build_workstation(str(tmp_path / "carts"), **kw)
    ws.pointer.visible = False
    return ws


def _draw(ws, name, w=320, h=240, c=8):
    moy_carts.save_file("drawings", name, moy_carts.encode_moyimg(w, h, bytes([c]) * (w * h)),
                        ws.carts_root)


def _frames(ws, n=3):
    for _ in range(n):
        ws.mark_dirty()
        ws.frame(_DT)


def _idle(ws, n=40):
    """Frames with nothing marked: the console's idle branch, where My Art
    makes the pictures its cards owe (an unlock banner on a wall clock
    would hold the frames painting)."""
    settle_badges(ws)
    ws.toast_until = 0
    for _ in range(n):
        ws.frame(_DT)


def _open(ws):
    app = ws.app("myart")
    assert ws.spine.open_app(app)
    _frames(ws)
    assert ws.wm.top_kind() == "myart"
    _idle(ws)
    return app


def _pic(app, name, w=88, h=66):
    """The picture the engine made of drawing `name` at w x h, or None."""
    for k, got in app.engine.pics.cache.items():
        if k[0].kind == "store" and k[0].key == "drawings/" + name and (k[1], k[2]) == (w, h):
            return got[1]
    return None


def _key(ws, k):
    """A typed key, through the host driver the browser and the keyboard use."""
    drv = host_app.ConsoleDriver(ws)
    drv.type_char(k)
    for _ in range(3):
        drv.frame(_DT)


def test_my_art_is_a_registered_app_the_desk_and_home_leave_out(tmp_path):
    ws = _ws(tmp_path)
    assert ws.app("myart") is not None
    assert "myart" in ws.wm.HIDDEN_APPS
    wall = [c for c in ws.carts.all if c.get("type") == "wallpaper"
            and c.get("title") == "Wallpaper"]
    assert len(wall) == 1, "the wallpaper slot is called Wallpaper"
    assert wall[0]["path"].endswith("moybyte.wallpaper.moy")


def test_the_drawings_are_cards_new_drawing_first_and_the_wallpapers_badge(tmp_path):
    ws = _ws(tmp_path)
    _draw(ws, "garden")
    _draw(ws, "rocket", c=1)
    assert ws.artwork.set_wallpaper("garden")
    ws.look.tick(0.0)
    app = _open(ws)
    assert sorted(app.drawings) == ["garden", "rocket"]
    assert app.wallpaper == "garden"
    stops = app.engine.stop_kinds()
    assert stops["+/open"] == "card", "New drawing is the first card"
    for name in ("garden", "rocket"):
        assert stops[name + "/open"] == "card"
    assert app.shown["wall"] == "Wallpaper: Garden"
    badges = dict((r["id"], r["badge"]) for r in app.shown["art"])
    assert badges == {"+": "", "garden": "wallpaper", "rocket": ""}
    # the cards' pictures are read at the card's size, never the drawing's
    pic = _pic(app, "garden")
    assert (pic.w, pic.h) == (88, 66) and pic.pix[0] == 8


def test_a_reopen_decodes_only_the_drawings_that_changed(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    _draw(ws, "garden")
    _draw(ws, "rocket", c=1)
    decoded = []
    real = artwork.read_cover

    def read_cover(blob, pix, w, h):
        decoded.append(blob)
        return real(blob, pix, w, h)
    monkeypatch.setattr(artwork, "read_cover", read_cover)
    app = _open(ws)
    assert len(decoded) == 2
    ws.home.go_home()
    _frames(ws)
    _open(ws)
    assert len(decoded) == 2, "a drawing no app wrote was decoded again"
    ws.home.go_home()
    path = moy_carts.file_path("drawings", "rocket", ws.carts_root)
    was = os.stat(path).st_mtime
    _draw(ws, "rocket", c=2)            # another app writes it meanwhile
    os.utime(path, (was, was))          # ...in the same second: the page keeps its order
    _frames(ws)
    _open(ws)
    assert len(decoded) == 3
    assert _pic(app, "rocket").pix[0] == 2
    assert _pic(app, "garden").pix[0] == 8


def test_the_pictures_are_made_on_idle_frames_one_a_frame_never_in_a_draw(
        tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    for i, c in enumerate((1, 2, 3)):
        _draw(ws, "pic%d" % i, c=c)
    made = []
    real = artwork.read_cover
    app = ws.app("myart")
    draw = app.draw

    def drawing(dt):
        app._in_draw = True
        try:
            return draw(dt)
        finally:
            app._in_draw = False

    def read_cover(blob, pix, w, h):
        assert not getattr(app, "_in_draw", False), "a picture made inside the draw"
        made.append(ws.frame_state.frames_drawn)
        return real(blob, pix, w, h)
    monkeypatch.setattr(artwork, "read_cover", read_cover)
    monkeypatch.setattr(app, "draw", drawing)
    assert ws.spine.open_app(app)
    _frames(ws)
    assert made == [] and app.idle_owed, "the cards drew without their pictures"
    _idle(ws)
    assert len(made) == 3 and not app.idle_owed
    assert len(set(made)) == 3, "one picture a frame, each shown by a paint of its own"
    _frames(ws)
    assert len(made) == 3 and not app.idle_owed, "every card drew its picture"


def test_an_empty_page_offers_new_drawing(tmp_path):
    ws = _ws(tmp_path)
    app = _open(ws)
    assert app.drawings == []
    assert app.shown["none"]
    assert app.engine.stop_kinds() == {"first": "button"}
    assert app.engine.hints()[:2] == ("confirm", "New drawing")


def test_del_moves_a_drawing_to_the_trash_without_asking(tmp_path):
    ws = _ws(tmp_path)
    _draw(ws, "rocket")
    app = _open(ws)
    app.focus_card("rocket")
    _frames(ws)
    assert app.cur == "rocket"
    _key(ws, 0x7F)
    assert app.drawings == []
    assert app.renaming is None and not app.menu, "no question"
    trash, _err = app._files.trash_list()
    assert any("rocket" in str(t) for t in trash)
    assert app.toast is not None and "Trash" in app.toast[0]


def test_ctrl_d_duplicates_and_r_renames_in_a_dialog(tmp_path):
    ws = _ws(tmp_path)
    _draw(ws, "rocket")
    app = _open(ws)
    app.focus_card("rocket")
    _frames(ws)
    _key(ws, 0x04)
    assert len(app.drawings) == 2
    app.focus_card("rocket")
    _frames(ws)
    _key(ws, ord("r"))
    assert app.renaming == "rocket" and app.shown["renaming"]
    app._rename("rocket", "Space ship")
    assert "space_ship" in app.drawings and "rocket" not in app.drawings


def test_the_card_menu_opens_on_m_and_washes(tmp_path):
    ws = _ws(tmp_path)
    _draw(ws, "rocket")
    app = _open(ws)
    app.focus_card("rocket")
    _frames(ws)
    _key(ws, ord("m"))
    assert app.menu and app.cur == "rocket"
    _frames(ws)
    assert app.shown["menu"] and app.shown["game_ok"], "Put in a game is on offer"
    items = [k.split("\t")[0] for k, v in app.engine.stop_kinds().items() if v == "item"]
    assert items == ["Open in Paint", "Use as wallpaper", "Put in a game\u2026", "Rename\u2026",
                     "Duplicate", "Move to Trash"]
    assert app.back() and not app.menu


def test_put_in_a_game_is_for_a_game_size_drawing_only(tmp_path):
    ws = _ws(tmp_path)
    _draw(ws, "rocket")
    _draw(ws, "wide", 1024, 600)
    app = _open(ws)
    app.focus_card("wide")
    _frames(ws)
    assert not app.shown["game_ok"]
    app._verb("game", "wide")
    assert app.game is None
    app._verb("game", "rocket")
    assert app.game is not None and app.game.carts
    _frames(ws)
    assert app.page_title() == "Put in a game"
    title = app.game.carts[0].get("title")
    drv = host_app.ConsoleDriver(ws)
    drv.press("a")                      # Enter on the first project's row
    for _ in range(3):
        drv.frame(_DT)
    assert app.game is None
    assert app.toast is not None and app.toast[0] == "Rocket is the background of " + title


def test_open_takes_the_drawing_to_paint(tmp_path):
    ws = _ws(tmp_path)
    _draw(ws, "rocket", c=3)
    app = _open(ws)
    app._verb("open", "rocket")
    _frames(ws)
    assert ws.wm.top_kind() == "artwork"
    assert ws.artwork.doc_name() == "rocket"
    assert ws.app("artwork").doc.pix[0] == 3


def test_new_drawing_opens_paint_on_a_fresh_drawing(tmp_path):
    ws = _ws(tmp_path)
    _draw(ws, "rocket")
    app = _open(ws)
    app._verb("new")
    _frames(ws)
    assert ws.wm.top_kind() == "artwork"
    assert ws.artwork.doc_name() not in (None, "rocket")
    assert (ws.app("artwork").doc.W, ws.app("artwork").doc.H) == (320, 240)


def test_the_desk_window_opens_at_its_designed_size(tmp_path):
    from runtime import wm_windowed
    assert wm_windowed.DESK_SIZES["myart"] == (900, 536)
    assert wm_windowed.DESK_SIZES["artwork"] == (900, 536)


def test_a_settled_page_paints_nothing(tmp_path):
    from ws_helpers import quiesce
    ws = _ws(tmp_path)
    _draw(ws, "rocket")
    _open(ws)
    drv = host_app.ConsoleDriver(ws)
    quiesce(ws)
    for _ in range(4):
        drv.frame(_DT)
    quiesce(ws)
    ws.mark_dirty()
    for _ in range(4):
        drv.frame(_DT)
    drawn = ws.frame_state.frames_drawn
    for _ in range(10):
        drv.frame(_DT)
    assert ws.frame_state.frames_drawn == drawn, "an idle page painted"


def test_a_drawing_written_meanwhile_is_made_again_on_an_idle_frame(tmp_path):
    """A picture made of bytes another app has since written goes: the idle
    frame reads the drawing again, and the card's picture is made anew."""
    ws = _ws(tmp_path)
    _draw(ws, "rocket", c=1)
    app = _open(ws)
    assert _pic(app, "rocket").pix[0] == 1
    _draw(ws, "rocket", c=4)            # Paint in a window beside it saves
    app._unchecked = ["rocket"]
    _idle(ws)
    assert _pic(app, "rocket").pix[0] == 4


def test_a_scrolled_cards_picture_stays_inside_its_region(tmp_path):
    """The cards scroll in a region under the caption: a card scrolled past
    the region's top shows none of its picture over the caption."""
    from runtime.layout_base import bar_rows, content_of
    ws = _ws(tmp_path)
    for i in range(9):
        _draw(ws, "pic%d" % i, c=12)
    app = _open(ws)
    app.focus_card("pic8")
    _frames(ws)
    _idle(ws)
    _frames(ws)
    cv = ws.sys_canvas
    from device_canvas import PAL565
    blue = PAL565[12]
    top = content_of(cv.w, cv.h, bar_rows(max(1, cv.font_scale)))[1]
    b = bytes(cv._buf)
    for y in range(top, top + 12):
        row = [b[2 * (y * cv.w + x)] << 8 | b[2 * (y * cv.w + x) + 1] for x in range(cv.w)]
        assert blue not in row, "a picture drawn over the caption at y=%d" % y
