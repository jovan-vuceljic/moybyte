"""A flowing page's foot on the C engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))

import uitree_parity as P  # noqa: E402


def test_a_foots_grey_button_stays_in_it_dimmed():
    """off="grey": an unavailable action's button stays where it stands,
    dimmed, the foot's among them (and the desk foot's rule over it)."""
    import uitree_c
    import uitree_foot_grey as F
    seen = {}

    def opened(ws):
        seen["ws"] = ws
        seen["app"] = P.host(ws, F.layer(uitree_c.CEngine), cart=True)
    f = P.frames("p4_1024x600_cs2_fs1_windowed", P.Surface(opened), ["idle:4"])[-1]
    x, y, w, h = seen["ws"].wm.windows["foot_grey_c"].content_rect()
    cols = {bytes(f.buf[(yy * f.w + xx) * 2:(yy * f.w + xx) * 2 + 2])
            for yy in range(y + h - 40, y + h) for xx in range(x + w - 160, x + w)}
    assert len(cols) > 3, "no button at the foot's end"


def test_a_pages_status_leads_its_hints_band():
    """status=: the page's words at the band's start, its keys after them."""
    import uitree_c
    import uitree_band_status as F
    seen = {}

    def opened(ws):
        seen["ws"] = ws
        seen["app"] = P.host(ws, F.layer(uitree_c.CEngine))

    def band(f):
        y0 = f.h - 20
        return [bytes(f.buf[(y * f.w + x) * 2:(y * f.w + x) * 2 + 2])
                for y in range(y0, f.h) for x in range(0, 64)]
    with_words = band(P.frames("tdeck_320x240_fs1_dark", P.Surface(opened), ["idle:4"])[-1])
    F.s._init["word"] = ""
    try:
        bare = band(P.frames("tdeck_320x240_fs1_dark", P.Surface(opened), ["idle:4"])[-1])
    finally:
        F.s._init["word"] = "View only"
    assert with_words != bare, "the status words drew nothing at the band's start"
