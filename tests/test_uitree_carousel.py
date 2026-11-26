"""`ui.cards(look="carousel")` on the C engine (native/moy_uitree's
`draw_carousel`, the toolkit's carousel verbs): one row of tiles, the centre
card's twice the others' at rest and a tile's size a function of its
distance from the centre alone; the engine moves the row (the toolkit's
table of parts): left and right glide it a card, a drag carries it and a
let-go settles on the nearest card, a tap on a neighbour glides it to the
centre, and cur= follows the card it comes to rest on; the motion is one
the frame gate sees, and a settled band draws no frame; Enter or a tap on
the centre card fires its action. The built and the compiled page run in
the Python front; a Lua app's carousel, the same engine's, glides, rests,
plays and takes its caption's tone=."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))

import uitree_parity as P  # noqa: E402


@pytest.fixture(params=["built", "compiled"])
def live(tmp_path, monkeypatch, request):
    """A workstation with the fixture open, its page built or loaded compiled
    (tools/uitree_compile.py): its driver, its engine, its host and the tiles
    each frame hands the front end (picture, r)."""
    import uitree_aot
    import uitree_c
    import uitree_carousel as F
    from runtime import host_app
    loaded = []
    if request.param == "compiled":
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import uitree_compile as UC
        monkeypatch.setattr(uitree_aot, "BLOBS", UC.compile_modules(["uitree_carousel"]).pages)
        load = uitree_c.CEngine._load

        def _load(self, x):
            r = load(self, x)
            if getattr(self.pages[0], "__module__", None) == F.__name__:
                loaded.append(r)        # (the fixture's page: not the home band's)
            return r
        monkeypatch.setattr(uitree_c.CEngine, "_load", _load)
    tiles = []
    was = uitree_c.CEngine._pic

    def pic(self, node, p, r):
        if r is not None and r[8] & 2:
            tiles.append((p, tuple(r[k] for k in range(12))))
        return was(self, node, p, r)
    monkeypatch.setattr(uitree_c.CEngine, "_pic", pic)
    ws = host_app.build_workstation(str(tmp_path / "carts"))
    ws.pointer.visible = False
    app = P.host(ws, F.layer(uitree_c.CEngine), cart=True)
    drv = host_app.ConsoleDriver(ws)
    host = ws._app_hosts[app.id]

    def frames(n, dt=1 / 30):
        for _ in range(n):
            del tiles[:]
            drv.frame(dt)

    frames(30)
    assert loaded == ([True] if request.param == "compiled" else []), loaded
    return ws, drv, app.engine, host, tiles, frames


def _sizes(tiles):
    """The tiles of the last frame drawn: (centre?, x, side), left to right."""
    return sorted(((r[8] & 4) != 0, r[0], r[2]) for _p, r in tiles)


def _settle(live, n=60):
    ws, drv, e, host, tiles, frames = live
    for _ in range(n):
        ws.mark_dirty()
        frames(1)
        if not host.moving:
            break
    ws.mark_dirty()
    frames(1)


def test_the_centre_tile_is_twice_its_neighbours_and_sizes_go_by_distance(live):
    ws, drv, e, host, tiles, frames = live
    _settle(live)
    got = sorted(tiles, key=lambda t: t[1][0])
    sides = [r[2] for _p, r in got]
    centre = [r for _p, r in got if r[8] & 4]
    assert len(centre) == 1 and centre[0][2] == max(sides), got
    assert centre[0][8] & 8, "at rest"
    side = min(sides)
    assert centre[0][2] == 2 * side, sides
    assert e.s.pick == "game 0"


def test_right_glides_the_row_a_card_and_cur_follows(live):
    ws, drv, e, host, tiles, frames = live
    _settle(live)
    host_box = host.box("games")
    assert host_box is not None
    drv.press("right")
    ws.mark_dirty()
    frames(1)
    assert host.moving, "a step glides: the frame gate sees the motion"
    assert e.s.pick == "game 0", "cur= is the card the row rests on"
    mid = []
    for _ in range(3):
        ws.mark_dirty()
        frames(1)
        mid.append([r[2] for _p, r in sorted(tiles, key=lambda t: t[1][0])])
    _settle(live)
    assert not host.moving
    assert e.s.pick == "game 1"
    got = sorted(tiles, key=lambda t: t[1][0])
    sides = [r[2] for _p, r in got]
    # a tile's size is a function of its distance alone: the row reads the same both ways
    # from its centre, mid-glide too where the two middle tiles share it out
    cx = [r[0] + r[2] // 2 for _p, r in got if r[8] & 4][0]
    left = sorted((cx - (r[0] + r[2] // 2), r[2]) for _p, r in got if r[0] + r[2] // 2 < cx)
    right = sorted(((r[0] + r[2] // 2) - cx, r[2]) for _p, r in got if r[0] + r[2] // 2 > cx)
    for (dl, sl), (dr, sr) in zip(left, right):
        assert sl == sr and abs(dl - dr) <= 1, (left, right)
    assert any(len(set(m)) > 2 for m in mid), ("mid-glide the sizes ease between", mid)
    assert max(sides) == 2 * min(sides)


def test_a_settled_band_draws_no_frame(live):
    ws, drv, e, host, tiles, frames = live
    _settle(live)
    frames(5)
    d0 = ws.frame_state.frames_drawn
    frames(20)
    assert ws.frame_state.frames_drawn == d0
    assert not host.moving


def test_enter_plays_the_centre_card(live):
    ws, drv, e, host, tiles, frames = live
    _settle(live)
    drv.press("right")
    _settle(live)
    drv.press("a")
    frames(3)
    assert e.s.played == "game 1", e.s.played


def _centre(tiles):
    """The centre tile's centre (x, y) in the last frame drawn."""
    r = [r for _p, r in tiles if r[8] & 4][0]
    return r[0] + r[2] // 2, r[1] + r[3] // 2


def test_a_drag_carries_the_row_and_a_let_go_settles_on_the_nearest_card(live):
    ws, drv, e, host, tiles, frames = live
    _settle(live)
    cx, cy = _centre(tiles)
    drv.touch(cx, cy)
    ws.mark_dirty()
    frames(1)
    xs = []
    for i in range(1, 6):
        drv.touch_drag(cx - i * 3, cy)
        ws.mark_dirty()
        frames(1)
        xs.append(min(r[0] for _p, r in tiles))
    assert xs == sorted(xs, reverse=True) and xs[-1] < xs[0], ("the row follows the finger", xs)
    assert e.s.pick == "game 0"
    drv.touch_up()
    _settle(live)
    assert not host.moving
    assert e.s.pick == "game 0", "a short drag settles back on the card it left"
    assert _centre(tiles) == (cx, cy)
    assert e.s.played == "", "a drag opens nothing"


def test_a_tap_on_a_neighbour_glides_it_in_and_a_tap_on_the_centre_plays(live):
    ws, drv, e, host, tiles, frames = live
    _settle(live)
    cx, cy = _centre(tiles)
    nb = [r for _p, r in tiles if not r[8] & 4 and r[0] > cx][0]
    drv.touch(nb[0] + nb[2] // 2, nb[1] + nb[3] // 2)
    ws.mark_dirty()
    frames(1)
    drv.touch_up()
    ws.mark_dirty()
    frames(1)
    assert host.moving and e.s.played == ""
    _settle(live)
    assert e.s.pick == "game 1" and _centre(tiles) == (cx, cy)
    drv.touch(cx, cy)
    ws.mark_dirty()
    frames(1)
    drv.touch_up()
    frames(3)
    assert e.s.played == "game 1", e.s.played


# -- the Lua front ---------------------------------------------------------------

_LUA_CAROUSEL = """
ui.app("Lua Carousel", { icon = "games" })
local s = ui.state { games = ui.model { key = "name", name = "", sub = "" },
                     pick = ui.row_of("games") }
ui.hook("opened", function()
  local rows = {}
  for i = 0, 6 do rows[#rows + 1] = { name = "game " .. i, sub = "Game\\tBuilt in" } end
  s.games:set(rows)
end)
ui.action("play", "Play", function(row) moybyte.log(6, "played " .. row.name) end, { takes = "row" })
ui.page("carousel", function()
  ui.cards("games", { look = "carousel", cur = "pick", w = %(w)d, tone = "%(tone)s",
                      label = "%(label)s" }, function()
    ui.card("play", { label = "{.name}", sub = "{.sub}" })
  end)
end, { title = "Lua Carousel" })
"""


_DESK = dict(sys_size=(1024, 600), font_scale=1, windowed=True, panel_diagonal_in=7.0)


def _lua_carousel(tmp_path, tone, desk=False, label=""):
    """A workstation (the handheld, or the desk where `desk`) with a Lua app
    whose page is a carousel of seven cards in caption ink `tone`, its desk
    shelf's caption `label`, open and drawn: its driver and a frame function
    answering the glass's bytes."""
    import json
    from runtime import host_app
    from ws_helpers import no_unlock_banner, open_cart
    carts = tmp_path / "carts"
    cart = carts / "lua_carousel.moy"
    cart.mkdir(parents=True)
    (cart / "manifest.json").write_text(json.dumps({
        "format": "moy-1", "title": "Lua Carousel", "runtime": "lua", "main": "main.lua",
        "extensions": ["moybyte.uitree"],
        "moybyte": {"type": "app", "permissions": []}}))
    (cart / "main.lua").write_text(_LUA_CAROUSEL % dict(tone=tone, label=label,
                                                       w=64 if desk else 32))
    ws = host_app.build_workstation(str(carts), **_DESK if desk else {})
    no_unlock_banner(ws)                        # (a badge's banner shines with the clock)
    ws.pointer.visible = False
    ws.bar_layer.clock_text = lambda: "10:30"   # (frames of two consoles compare)
    drv = host_app.ConsoleDriver(ws)
    drv.frame(1 / 30)
    open_cart(ws, "Lua Carousel")

    glass = ws.wm.root_canvas if desk else ws.sys_canvas

    def frame():
        ws.mark_dirty()
        drv.frame(1 / 30)
        return bytes(glass._buf)
    for _ in range(30):
        frame()
    return ws, drv, frame


def test_a_lua_carousel_glides_a_card_rests_and_plays_the_card_it_rests_on(tmp_path):
    """The Lua front takes the engine's carousel as it is: right glides the
    row over frames that differ, it rests on the next card, and Enter plays
    the card it rests on."""
    from runtime.host import moy_log
    ws, drv, frame = _lua_carousel(tmp_path, "")
    rest = frame()
    seq = moy_log.next()
    drv.press("right")
    moving = [frame() for _ in range(4)]
    assert len(set(moving)) == 4 and rest not in moving, "the row glides"
    for _ in range(20):
        frame()
    assert frame() == frame() != rest, "it rests, a card along"
    drv.press("a")
    for _ in range(3):
        frame()
    played = [r[4] for r in moy_log.read(seq, 400) if "played " in r[4]]
    assert played and played[-1].endswith("played game 1"), played


def test_a_lua_carousels_caption_takes_its_tone(tmp_path):
    """tone= inks the caption under the row: the same carousel with the
    theme's ink and with a colour differs in the caption's rows alone."""
    _ws, _drv, frame = _lua_carousel(tmp_path / "ink", "")
    ink = frame()
    ws, _drv, frame = _lua_carousel(tmp_path / "red", "#FF0000")
    red = frame()
    span = 2 * ws.sys_canvas.w
    rows = [r for r in range(ws.sys_canvas.h) if ink[r * span:(r + 1) * span] != red[r * span:(r + 1) * span]]
    assert rows, "the tone changed nothing"
    assert rows[-1] - rows[0] < ws.sys_canvas.h // 4, ("the caption's rows alone", rows)


def test_a_lua_carousel_on_the_desk_is_a_shelf_whose_current_card_moves_at_once(tmp_path):
    """On the desk class the carousel look is a shelf of same-size cards:
    right makes the next card current in the frame it is pressed (the
    shelf, its cards all on the glass, does not move), it rests there, and
    Enter plays the current card."""
    from runtime.host import moy_log
    ws, drv, frame = _lua_carousel(tmp_path, "", desk=True, label="Games")
    rest = frame()
    seq = moy_log.next()
    drv.press("right")
    moved = frame()
    assert moved != rest, "the current card moved"
    assert [frame() for _ in range(3)] == [moved] * 3, "at once: nothing glides"
    drv.press("a")
    for _ in range(3):
        frame()
    played = [r[4] for r in moy_log.read(seq, 400) if "played " in r[4]]
    assert played and played[-1].endswith("played game 1"), played


def test_a_desk_shelfs_caption_is_its_label_and_its_count(tmp_path):
    """label= captions the desk shelf over its cards, with the count of its
    cards: the same shelf with another label differs in the caption's rows
    alone, above the cards; with none the count stands alone."""
    ws, _drv, frame = _lua_carousel(tmp_path / "games", "", desk=True, label="Games")
    games = frame()
    _ws, _drv, frame = _lua_carousel(tmp_path / "tools", "", desk=True, label="Tools")
    tools = frame()
    _ws, _drv, frame = _lua_carousel(tmp_path / "none", "", desk=True)
    bare = frame()
    w = ws.wm.root_canvas.w
    span = 2 * w

    def rows(a, b):
        return [r for r in range(len(a) // span) if a[r * span:(r + 1) * span] != b[r * span:(r + 1) * span]]
    moved = rows(games, tools)
    assert moved, "the label changed nothing"
    assert moved[-1] - moved[0] < 40, ("the caption's rows alone", moved)
    bare = rows(games, bare)
    assert bare and moved[0] - 4 <= bare[0] and bare[-1] <= moved[-1] + 4, (
        "no label: the count alone, on the caption's rows", bare, moved)


_LUA_TILE = """
ui.app("Lua Tile", { icon = "games" })
local s = ui.state { side = 96 }
ui.action("play", "Play", function() moybyte.log(6, "played the tile") end)
ui.page("tile", function()
  ui.picture({ icon = "games", side = "{side}", %(look)s on = "play" })
end, { title = "Lua Tile" })
"""


def _lua_tile(tmp_path, look):
    """A desk workstation with a Lua app whose page is one picture of look
    `look` that plays on=, open and drawn: its driver and a frame function
    answering the glass's bytes."""
    import json
    from runtime import host_app
    from ws_helpers import no_unlock_banner, open_cart
    carts = tmp_path / "carts"
    cart = carts / "lua_tile.moy"
    cart.mkdir(parents=True)
    (cart / "manifest.json").write_text(json.dumps({
        "format": "moy-1", "title": "Lua Tile", "runtime": "lua", "main": "main.lua",
        "extensions": ["moybyte.uitree"],
        "moybyte": {"type": "app", "permissions": []}}))
    (cart / "main.lua").write_text(_LUA_TILE % dict(look='look = "%s",' % look if look else ""))
    ws = host_app.build_workstation(str(carts), **_DESK)
    ws.pointer.visible = False
    drv = host_app.ConsoleDriver(ws)
    drv.frame(1 / 30)
    open_cart(ws, "Lua Tile")

    def frame():
        ws.mark_dirty()
        drv.frame(1 / 30)
        return bytes(ws.wm.root_canvas._buf)
    for _ in range(10):
        frame()
    return ws, drv, frame


def test_a_lua_picture_tile_is_a_stop_its_on_fires_from(tmp_path):
    """The Lua front takes ui.picture: look="tile" draws it as a carousel's
    tile of its own (not the plain picture's card), and with on= it is a
    stop, so Enter on it fires on=."""
    from runtime.host import moy_log
    _ws, _drv, frame = _lua_tile(tmp_path / "card", "")
    card = frame()
    _ws, drv, frame = _lua_tile(tmp_path / "tile", "tile")
    tile = frame()
    assert tile != card, "the tile look draws its own"
    seq = moy_log.next()
    drv.press("a")
    for _ in range(3):
        frame()
    played = [r[4] for r in moy_log.read(seq, 400) if "played " in r[4]]
    assert played and played[-1].endswith("played the tile"), played
