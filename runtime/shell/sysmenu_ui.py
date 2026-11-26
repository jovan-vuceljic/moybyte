"""The system menu's card, a `uitree` page that `shell_cards.SystemMenuUI`
hosts over the content it dims: a popover hung from the rect the host hands
in (`at`: the bar's system button, a long press's point, the desk's
PROJECTS cover), its rows the `sysmenu` Popup's, in its groups:

- The first (`cap`, its caption): the open cart's Delete, or the selected
  card's verbs, Delete set apart under them in a menu of its own -- or,
  with no cart group, the System group.
- The System group after a cart group (`more`): Home, Search, Tasks,
  beaming, Settings, About, Sleep, Restart.

A verb that destroys is a danger row. The keys are the Popup's (its rows
move and run in the input phase) and the page's focus follows its row
(`sel`); a finger's drag past the slop scrolls the rows and runs none, a
tap on a row runs it through the host (`uitree_app.env()`), and one
outside the card is the host's.
"""

import uitree as ui
import uitree_app

s = ui.state(
    at="",
    w=220,
    cap="",
    apart=False,
    more="",
    # grp: the first group, a danger row in it, a danger row set apart under
    # it, the group after it
    rows=ui.model(key="id", id="", icon="", grp=ui.enum("first", "danger", "apart", "more", init="first")),
    sel=ui.row_of("rows"),
)


def put():
    """The menu the host holds, as the page shows it."""
    uitree_app.env().put(s)


def _choose(row):
    uitree_app.env().chosen(row.id)


ui.hook("put", put)
ui.action("choose", "Choose", _choose, takes="row")
ui.action("destroy", "Choose", _choose, takes="row")     # a danger row's: the same, one per row


def page():
    with ui.page(""):
        with ui.popover("System", w="{w}", at="{at}"):
            with ui.menu("{cap}"):
                with ui.rows("rows", cur="sel"):
                    ui.item("choose", label="{.id}", icon="{.icon}", shown=".grp=first")
                    ui.item("destroy", label="{.id}", icon="{.icon}", kind="danger", shown=".grp=danger")
            with ui.menu("", shown="apart"):
                with ui.rows("rows", cur="sel"):
                    ui.item("choose", label="{.id}", icon="{.icon}", kind="danger", shown=".grp=apart")
            with ui.menu("{more}", shown="more"):
                with ui.rows("rows", cur="sel"):
                    ui.item("choose", label="{.id}", icon="{.icon}", shown=".grp=more")
