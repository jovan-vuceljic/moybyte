"""A popover's at=: the card hangs from a rect its host hands in (the
system menu's anchor: the bar's button, a long press, a cover)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "uitree_fixtures"))

from runtime import ui_draw  # noqa: E402
from ws_helpers import build_ws  # noqa: E402


class _Damage:
    def all(self):
        pass


def test_a_popover_hangs_from_the_rect_its_host_hands_in(tmp_path):
    import uitree_app
    import uitree_popover_at as F
    ws = build_ws(tmp_path)
    cv, th = ws.sys_canvas, ws.theme_colors
    host = ui_draw.AppHost()
    pg = uitree_app.hosted_page(F.page, host, _Damage())
    pg.bare = True
    pg.open()
    rect = (0, 0, cv.w, cv.h)
    for at in ((20, 30, 60, 20), (150, 100, 60, 20)):
        pg.run(F.put, "%d %d %d %d" % at, action="put")
        F.ui.commit(pg)
        for _ in range(2):              # the popover's first frame lays its body out
            host.begin(cv, th, rect, False)
            pg.paint(0.0, cv, th, rect, False)
        x, y, w, h = host.box("pop")
        assert y >= at[1] + at[3] and abs(x - at[0]) <= 8, (at, (x, y, w, h))
