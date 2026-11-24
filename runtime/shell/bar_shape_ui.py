"""The shell's bars of any other shape as placed pages: `strip`, a top or
bottom bar the themes' bar (`bar_ui.bar`) does not place, and `side`, a
left or right bar. A bar's widgets stand in the theme's order as the rows
of three models, a slot each (`lead` from the bar's start, `tail` from its
end, `mid` between them), each row a widget of `KINDS`; what it shows is
its host's to write (`bar_engine`), as the themes' bar's is.

Along a strip the chips are a row from a model (`wins`, a window each) and
the status items another (`items`); down a side bar each cell is a column
from a model's (`ui.rows(dir="col")`), a window's chip its icon alone and
an icon's cell a square. A status icon stands in its icon's square, 16
units along the bar. The bar items tap and draw as the themes' bar's do,
through its hooks (`bar_ui.PAINT`, `TAP`, `CHIP`, `ITEM`)."""

import uitree as ui
import bar_ui

KINDS = ("menu", "chips", "status", "zone", "title", "text", "spacer", "separator", "wifi", "battery",
         "clock", "close")

s = ui.state(sg=4, cw=40, sys_w=16, wicon="wifi", time="00:00", batt_icon=True, batt_glyph=False,
             title="", gaps=True, middle=False,
             wins=ui.model(key="k", k="", title="", icon="", on=False, tone=""),
             items=ui.model(key="k", k="", icon="", on=False, tone=""),
             lead=ui.model(key="k", k="", kind=ui.enum(*KINDS, init="zone"), text=""),
             mid=ui.model(key="k", k="", kind=ui.enum(*KINDS, init="zone"), text=""),
             tail=ui.model(key="k", k="", kind=ui.enum(*KINDS, init="zone"), text=""))


def cell(cv, x, y, w, h, row=None):
    """The zone and a fill: its owner draws the zone after the page."""


def close_cell(cv, x, y, w, h, row=None):
    bar_ui.PAINT[0]("close", cv, x, y, w, h)


def battery_cell(cv, x, y, w, h, row=None):
    bar_ui.PAINT[0]("battery", cv, x, y, w, h)


def _widget(row):
    if bar_ui.TAP[0] is not None:
        bar_ui.TAP[0](row.kind)


def _chip(row):
    if bar_ui.CHIP[0] is not None:
        bar_ui.CHIP[0](row.k)


def _item(row):
    if bar_ui.ITEM[0] is not None:
        bar_ui.ITEM[0](int(row.k))


ui.action("chip", "Window", _chip, takes="row")
ui.action("item", "Status", _item, takes="row")
ui.action("widget", "Open", _widget, takes="row")


def _chips(side, middle):
    if side:
        with ui.rows("wins", dir="col"):
            ui.button("chip", icon="{.icon}", alone=True, kind="bar", marked=".on", tone="{.tone}")
        ui.canvas("chips_end", cell)        # the chips' room after them: a fill down the bar
        return
    with ui.row("chips", pad=bar_ui.CHIP_PAD, gap=bar_ui.CHIP_GAP, grow=not middle):
        with ui.rows("wins", dir="row"):
            ui.button("chip", label="{.title}", icon="{.icon}", kind="bar", marked=".on", tone="{.tone}")


def _status():
    with ui.row("cluster", gap="{sg}"):
        with ui.rows("items", dir="row"):
            ui.button("item", icon="{.icon}", alone=True, kind="bar", marked=".on", tone="{.tone}")


def _battery_cells():
    ui.button("widget", icon="battery", alone=True, kind="bar", w=16, shown="batt_icon")
    ui.canvas("battery_st", battery_cell, w=16, h=16, shown="batt_glyph")


def _cases(side, middle=False):
    """Each widget's cells, along a top or bottom bar, or down a side bar
    (`side`); in a strip's middle (`middle`) the chips at their own width,
    centred with it."""
    def clock():
        if side:
            ui.button("widget", label="{time}", kind="bar", w=16)
        else:
            ui.button("widget", label="{time}", kind="bar", w="{cw}")

    return {
        "menu": lambda: ui.button("widget", icon="moy", alone=True, kind="bar", w="{sys_w}"),
        "chips": lambda: _chips(side, middle),
        "status": _status,
        "zone": lambda: ui.canvas("zone", cell, w=40, grow=True),
        "title": lambda: ui.label("{title}"),
        "text": lambda: ui.label("{.text}", tone="dim", size="text"),
        "spacer": lambda: ui.canvas("spacer", cell, w=0, grow=True),
        "separator": lambda: ui.rule(),
        "wifi": lambda: ui.button("widget", icon="{wicon}", alone=True, kind="bar", w=16),
        "battery": _battery_cells,
        "clock": clock,
        "close": lambda: ui.canvas("close_x", close_cell, w=16, h=16),
    }


def strip():
    """A top or bottom bar of any other shape: its widgets in the theme's
    order, the start slot's from its start, the end's from its end and the
    middle's centred on the bar (`middle`), the fills sharing what they
    leave; a fill between the ends where none of them fills (`gaps`)."""
    cases = _cases(False)
    with ui.page(""):
        with ui.row("bar", pad=2, gap="{sg}", grow=True):
            ui.rows("lead", by="kind", cases=cases, dir="row")
            ui.canvas("gap_a", cell, w=0, grow=True, shown="gaps")
            with ui.row("middle", mid=True, gap="{sg}", shown="middle"):
                ui.rows("mid", by="kind", cases=_cases(False, True), dir="row")
            ui.rows("tail", by="kind", cases=cases, dir="row")


def side():
    """A side bar: its widgets down it in the theme's order, an icon a
    square cell, the middle's between the ends with a fill either side
    where it holds a fixed widget or nothing fills (`gaps`)."""
    cases = _cases(True)
    with ui.page(""):
        ui.rows("lead", by="kind", cases=cases, dir="col")
        ui.canvas("gap_a", cell, w=0, grow=True, shown="gaps")
        ui.rows("mid", by="kind", cases=cases, dir="col")
        ui.canvas("gap_b", cell, w=0, grow=True, shown="gaps")
        ui.rows("tail", by="kind", cases=cases, dir="col")
