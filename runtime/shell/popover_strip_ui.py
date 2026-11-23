"""The hint strip under a bar widget's popover on a handheld home: the
popover's component's keys (its `keys()`, pairs of a key and what it does)
as one `ui.hints` row over the home's strip, a page of its own so it swaps
no state with the home's (`home_strip_ui`). Its host is the system menu
(`shell_cards.SystemMenuUI`): it writes the rows where the component's keys
are others (`put`) and paints the page in the strip's rect on the panel."""

import uitree as ui
import uitree_app

s = ui.state(hints=ui.model("id", id="", keys="", words=""))


def put():
    """The component's keys as the page's rows, the host's (`strip_put`)."""
    uitree_app.env().strip_put(s)


ui.hook("put", put)


def strip():
    with ui.page(""):
        ui.hints("hints", keys="{.keys}", label="{.words}")
