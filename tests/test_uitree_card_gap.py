"""A card's box is its picture and its pad either side, the pad no wider than
half the gap between two columns (`moy_ui_api_card`): where a grid's pitch is
under a card and two pads, neighbouring cards' boxes -- what a tap and the
focus land in -- still never overlap. No golden draws such a grid."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))

from runtime import ui_draw  # noqa: E402
from ws_helpers import build_ws  # noqa: E402

RECT = (10, 20, 600, 300)


class _Damage:
    def all(self):
        pass


def test_neighbouring_cards_boxes_never_overlap(tmp_path):
    import uitree_app
    import uitree_card_gap as F
    ws = build_ws(tmp_path)
    host = ui_draw.AppHost()
    pg = uitree_app.hosted_page(F.page, host, _Damage())
    pg.bare = True
    pg.band = False
    pg.open()
    cv, th = ws.sys_canvas, ws.theme_colors
    for _ in range(3):
        host.begin(cv, th, RECT, True, elsewhere=True)
        pg.paint(0.0, cv, th, RECT, True)
    boxes = [host.box("c%d/open" % k) for k in range(6)]
    row = [b for b in boxes if b is not None and b[1] == boxes[0][1]]
    assert len(row) >= 3, boxes
    pitch = row[1][0] - row[0][0]
    assert pitch - 64 < 2 * 7, "the case: a gap under two of the card's 7-px pads"
    for a, b in zip(row, row[1:]):
        assert a[0] + a[2] <= b[0], ("neighbouring boxes overlap", a, b)
        assert a[2] >= 64, ("the box still holds its picture", a)
