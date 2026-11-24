"""The windowed desk's icon column as a page: the engine's column of tiles
(`ui.cards(look="column")`) down the desk's left edge, column after column,
shrinking until every app keeps a tile. What it shows is its host's to
write (`wm_desk._BackdropLayer`): a row a tile (its key, its app's title,
its colour of the look's `tiles` as "#RRGGBB", empty for the tile's own),
the tiles' side and their rows' pitch in pixels, and the labels' ink
("#FFFFFF" over a wallpaper, empty for the look's own). Each tile's picture
is its icon, which the host draws; opening a tile calls its `OPEN`. The
host writes the rows through the `put` hook (`PUT`)."""

import uitree as ui

_decl = {}
_decl["tiles"] = ui.model(key="k", k="", label="", fill="", pic=ui.IMAGE)
_decl["tone"] = ""
_decl["side"] = 44
_decl["pitch"] = 74
s = ui.state(**_decl)

OPEN = [None]       # the desk's open of tile k: f(k)
PUT = [None]        # the desk's write of the rows: f(s)


def put():
    PUT[0](s)


def _open(row):
    if OPEN[0] is not None:
        OPEN[0](row.k)


ui.hook("put", put)
ui.action("open", "Open", _open, takes="row")


def tiles():
    with ui.page(""):
        with ui.cards("tiles", look="column", tone="{tone}", w="{side}", h="{pitch}"):
            ui.card("open", label="{.label}", image=".pic", fill="{.fill}")
