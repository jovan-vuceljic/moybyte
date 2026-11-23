"""`ui.cards(look="carousel")` on the C engine (native/moy_uitree's
`draw_carousel`, the toolkit's carousel verbs): one row of tiles, the centre
card's twice the others' at rest and a tile's size a function of its
distance from the centre alone; the engine moves the row (the toolkit's
table of parts): left and right glide it a card, a drag carries it and a
let-go settles on the nearest card, a tap on a neighbour glides it to the
centre, and cur= follows the card it comes to rest on; the motion is one
the frame gate sees, and a settled band draws no frame; Enter or a tap on
the centre card fires its action."""

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
