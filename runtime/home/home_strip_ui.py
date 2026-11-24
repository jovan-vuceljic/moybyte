"""The home's hint strip along its foot, a page of its own (`strip`, every
class's): one `ui.hints` row, its rows the keys the selected card's verbs
and its star take and the tab keys at its end; where they run short of room
the spare rows (the star, Duplicate) go first, and a press on one does its
verb. While search is open (the fullscreen home's Games tab) the search
field stands in the verbs' place, the hints after it naming its way out.

The host is the home layer (`home_hints.HomeHints`): it writes the rows and
the search's state (`put`, run when what they are made of moves), does the
verb a press lands on (`hint_press`), filters the grid on each edit
(`search_typed`) and stops typing on Enter (`search_done`). Its state is
its own module's, so painting it beside the home's band page swaps no state
between them."""

import uitree as ui
import uitree_app

s = ui.state(hints=ui.model("id", id="", keys="", words="", tail=False, spare=False),
             searching=False, query="", search_hint="")


def put():
    """The strip's rows and its search, the host's (`HomeHints.hints_put`)."""
    uitree_app.env().hints_put(s)


def _hint(row):
    uitree_app.env().hint_press(row.id)


def _typed():
    uitree_app.env().search_typed(s.query)


def _done():
    uitree_app.env().search_done()


ui.hook("put", put)
ui.action("hint", "Do", _hint, takes="row")
ui.action("typed", "Search", _typed)
ui.action("done", "Done", _done)


def strip():
    with ui.page(""):
        with ui.split("row", sizes=("1*", "1*"), gap=0, pad=0):
            ui.field("Search", "query", max=24, changed="typed", on="done", hint="{search_hint}",
                     shown="searching")
            ui.hints("hints", keys="{.keys}", label="{.words}", tail=".tail", drop=".spare", on="hint")
