"""The pause and stop cards, a `uitree` page that `shell_cards.PauseMenu`
hosts over the held game: a popover with nothing to hang from, centred on
the glass.

- Paused (`card` "menu"): the game's title and Paused, then its rows (the
  host's: Resume, Restart, Options, Quit and the rows a tier adds).
- Options (`card` "options"): the console's Volume.
- Stopped (`card` "stop"): the cart's title and Stopped (a notice's: no
  state), the sentence, then what to do -- or with Details chosen the error
  exact -- and the rows.

The handlers hand each choice to the host (`uitree_app.env()`).
"""

import uitree as ui
import uitree_app

s = ui.state(
    card=ui.enum("menu", "options", "stop", init="menu"),
    title="",
    state="",
    rows=ui.model(key="id", id="", icon=""),
    sel=ui.row_of("rows"),
    sentence="",
    words="",
    error="",
    details=False,
    vol=0,
    vlo=0,
    vhi=1,
    vicon="volume",
    w=188,
    back_word="Resume",
)


def put():
    """The card the host holds, as the page shows it."""
    uitree_app.env().put(s)


def _choose(row):
    uitree_app.env().chosen(row.id)


def _away():
    uitree_app.env().away()


def _louder():
    uitree_app.env().volume(s.vol)


ui.hook("put", put)
ui.action("choose", "Choose", _choose, takes="row")
ui.action("away", "Close", _away, hint="{back_word}")
ui.action("louder", "Volume", _louder)


def page():
    with ui.page(""):
        with ui.popover("Pause", w="{w}", close="away"):
            ui.info("{title}", "{state}", icon="moy")
            ui.rule(shown="card=stop")
            ui.label("{sentence}", wrap="word", lines=2, shown="card=stop")
            ui.label("{words}", tone="dim", wrap="word", lines=4, shown="card=stop && !details")
            ui.label("{error}", face="mono", wrap="word", lines=4, shown="card=stop && details && @desk")
            ui.label("{error}", face="mono", wrap="word", lines=3, shown="card=stop && details && !@desk")
            ui.slider("Volume", "vol", "{vlo}", "{vhi}", look="steps", icon="{vicon}", on="louder",
                      shown="card=options")
            with ui.menu("", shown="card!=options"):
                with ui.rows("rows", cur="sel"):
                    ui.item("choose", label="{.id}", icon="{.icon}")
