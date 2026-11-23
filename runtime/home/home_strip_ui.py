"""The home's hint strip along its foot, a page of its own (`strip`, every
class's): one `ui.hints` row, its rows the keys the selected card's verbs
and its star take and the tab keys at its end; where they run short of room
the spare rows (the star, Duplicate) go first, and a press on one does its
verb.

The host is the home layer (`home_hints.HomeHints`): it writes the rows
(`put`, run when what they are made of moves) and does the verb a press
lands on (`hint_press`). Its state is its own module's, so painting it
beside the home's band page swaps no state between them."""

import uitree as ui
import uitree_app

s = ui.state(hints=ui.model("id", id="", keys="", words="", tail=False, spare=False))


def put():
    """The strip's rows, the host's (`HomeHints.hints_put`)."""
    uitree_app.env().hints_put(s)


def _hint(row):
    uitree_app.env().hint_press(row.id)


ui.hook("put", put)
ui.action("hint", "Do", _hint, takes="row")


def strip():
    with ui.page(""):
        ui.hints("hints", keys="{.keys}", label="{.words}", tail=".tail", drop=".spare", on="hint")
