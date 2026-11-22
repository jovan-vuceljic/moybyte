"""A card's and a picture's `image=` on the C engine: the front decodes the
picture off the frame (`uitree_pics.PicEngine`, on the console's idle step)
and draws it into the card's tile, clipped to the page's room; the icon tile
shows while it has none."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))

import uitree_parity as P  # noqa: E402


def _colours(f):
    return {bytes(f.buf[i:i + 2]) for i in range(0, len(f.buf), 2)}


def test_a_cards_page_draws_its_pictures():
    import uitree_c
    import uitree_cards_pics as F
    seen = {}

    def opened(ws):
        seen["app"] = P.host(ws, F.layer(uitree_c.CEngine), cart=True)
    frames = P.frames("tdeck_320x240_fs1_dark", P.Surface(opened), ["idle:40"])
    app = seen["app"].engine
    assert app.pics.stats["decoded"] == 4, app.pics.stats      # three cards' and the picture's
    assert not app.idle_owed            # settled: nothing owed, no frame asked for
    # one colour a picture: the opening's icon tiles had none of them
    assert len(_colours(frames[-1]) - _colours(frames[0])) >= len(F.COLOURS)


def test_a_picture_the_app_draws_is_drawn_at_the_cards_size_and_let_go_with_it():
    """`ui.pictures.put(KEY, render=FN)`: the engine asks the app for the
    picture at the card's size on its idle step, keeps the layer it answers
    and releases it when it lets the picture go."""
    import uitree_c
    import uitree_cards_drawn as F
    seen = {}

    def opened(ws):
        F.CANVAS[0] = ws.sys_canvas
        seen["app"] = P.host(ws, F.layer(uitree_c.CEngine), cart=True)
    frames = P.frames("tdeck_320x240_fs1_dark", P.Surface(opened), ["idle:40"])
    app = seen["app"].engine
    assert app.pics.stats["decoded"] == 3, app.pics.stats
    assert len({(w, h) for _ink, w, h in F.DRAWN}) == 1, F.DRAWN    # every card's one size
    assert len(_colours(frames[-1]) - _colours(frames[0])) >= 2
    lay = F.LAYERS[0]
    n = len(lay._buf)
    app.pics.forget_own("d0")
    assert len(lay._buf) < n, "the layer goes back with its picture"


def test_a_flowing_pages_pictures_end_over_its_hints_band():
    """A card the handheld's band cuts draws its picture down to the band
    and no further: the band's rows hold no picture's ink."""
    import uitree_c
    import uitree_cards_drawn as F
    seen = {}
    was = F.INKS
    F.INKS = (8, 11, 12) * 4

    def opened(ws):
        F.CANVAS[0] = ws.sys_canvas
        seen["app"] = P.host(ws, F.layer(uitree_c.CEngine), cart=True)
    try:
        frames = P.frames("tdeck_320x240_fs1_dark", P.Surface(opened), ["idle:40"])
    finally:
        F.INKS = was

    def band(f):
        w = f.w
        return {bytes(f.buf[i:i + 2]) for i in range((f.h - 20) * w * 2, f.h * w * 2, 2)}
    assert seen["app"].engine.pics.stats["decoded"] >= 6
    assert band(frames[-1]) == band(frames[0])
