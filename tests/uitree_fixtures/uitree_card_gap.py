"""A grid of cards whose columns stand closer than a card's pad either side:
`pad=1` (a 1x gap) between 64-wide cards."""
import uitree as ui

s = ui.state(carts=ui.model(key="id", id="", name=""), card=ui.row_of("carts"))


def open_(row):
    pass


def opened():
    s.carts = [dict(id="c%d" % k, name="Cart %d" % k) for k in range(6)]


ui.action("open", "Open", open_, takes="row")
ui.hook("opened", opened)


def page():
    with ui.page(""):
        with ui.cards("carts", cur="card", w=64, h=64, pad=1):
            ui.card("open", label="{.name}")
