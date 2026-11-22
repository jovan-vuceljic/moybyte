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
