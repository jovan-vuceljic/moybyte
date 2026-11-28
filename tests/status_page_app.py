"""A user's Python app's status section as a page (status_items, SECTION),
for tests/test_status_items.py: a canvas that draws and takes a tap, and a
button under it, each recording the process it ran as."""

import uitree as ui
from runtime import moy_log

s = ui.state(n=0)
RAN = []                        # (what, the process it ran as)
DRAWN = []                      # each draw's rect


def draw_dot(cv, x, y, w, h):
    DRAWN.append((x, y, w, h))
    cv.rect(x + 2, y + 2, 8, 8, ui.colors()["value"])


def dot_at(ev):
    if ev.kind == "up":
        RAN.append(("dot", moy_log.current()))


def ping():
    RAN.append(("ping", moy_log.current()))


def changed():
    RAN.append(("changed", moy_log.current()))


ui.hook("dot_at", dot_at, takes="pointer")
ui.hook("changed", changed)
ui.action("ping", "Ping", ping)


def page():
    with ui.page(""):
        with ui.split("col", sizes=(24, 24, "1*"), gap=6, pad=6):
            ui.canvas("dot", draw_dot, pointer="dot_at")
            ui.button("ping")
            ui.label("")


class PageSection:
    page = staticmethod(page)

    def height(self, desk):
        return 72 if desk else 66
