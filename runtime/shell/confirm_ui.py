"""The console's one question, a `uitree` page that `shell_cards.DeleteConfirm`
hosts over the content it dims: a dialog titled with the question, its
buttons the answers.

- A verb's question (`verb` delete, close, stop_play or receive): its line
  under the title, wrapped, the card growing to fit; Cancel (No for a
  receive) and the verb, in the danger look where it loses something.
- The first run of a cart that arrived as files (`open`): the install
  prompt's lines (`app_perms.rows`), No and Open.
- The intents' "open with" (`choose`): a menu under the line, a row each
  pick (its icon and label), and Cancel.
- Something the console tells (`tell`): its lines, and OK.
- A move of the Wi-Fi a page reaches the console over (`switch`): its
  lines, Cancel and Move; with Save between them where the network is not
  saved yet (`switch_save`), which saves it and moves nothing.

The handlers hand each answer to the host (`uitree_app.env()`), which acts
at the frame's tail.
"""

import uitree as ui
import uitree_app

VERBS = ("delete", "close", "stop_play", "receive", "open", "choose", "tell", "switch",
         "switch_save")

s = ui.state(
    title="",
    line="",
    verb=ui.enum(*VERBS, init="delete"),
    lines=ui.model(key="id", id="", text="", tone=ui.enum("plain", "dim", "danger", init="plain")),
    picks=ui.model(key="id", id="", label="", icon=""),
)


def asked():
    """The question the host holds, as the page shows it."""
    q = uitree_app.env()
    s.title, s.line, s.verb = q.title, q.line, q.verb
    s.lines = [{"id": str(i), "text": t, "tone": tone} for i, (t, tone) in enumerate(q.line_rows())]
    s.picks = [{"id": str(i), "label": r, "icon": q.icons[i] if i < len(q.icons) else ""}
               for i, r in enumerate(q.rows)]


def _cancel():
    uitree_app.env().cancel()


def _yes():
    uitree_app.env().answer()


def _save():
    uitree_app.env().saved()


def _pick(row):
    uitree_app.env().picked(int(row.id))


ui.hook("asked", asked)
ui.action("cancel", "Cancel", _cancel)
ui.action("no", "No", _cancel)
ui.action("delete", "Delete", _yes)
ui.action("close", "Close", _yes)
ui.action("stop_play", "Stop & play", _yes)
ui.action("receive", "Receive", _yes)
ui.action("open", "Open", _yes)
ui.action("ok", "OK", _yes)
ui.action("switch", "Move", _yes)
ui.action("save", "Save", _save)
ui.action("pick", "Choose", _pick, takes="row")

# A verb's question: its buttons, Cancel or No first, and whether the verb
# loses something (the danger look).
_ASKS = (("delete", "cancel", True), ("close", "cancel", True), ("stop_play", "cancel", True),
         ("receive", "no", False))


def page():
    with ui.page(""):
        for verb, no, danger in _ASKS:
            with ui.dialog("{title}", [no, verb], shown="verb=" + verb, kind="danger" if danger else "primary"):
                ui.label("{line}", wrap="word", lines=3)
        with ui.dialog("{title}", ["no", "open"], shown="verb=open"):
            _lines()
        with ui.dialog("{title}", ["ok"], shown="verb=tell"):
            _lines()
        with ui.dialog("{title}", ["cancel", "switch"], shown="verb=switch"):
            _lines()
        with ui.dialog("{title}", ["cancel", "save", "switch"], shown="verb=switch_save"):
            _lines()
        with ui.dialog("{title}", ["cancel"], shown="verb=choose"):
            with ui.menu("{line}"):
                with ui.rows("picks"):
                    ui.item("pick", label="{.label}", icon="{.icon}")


def _lines():
    with ui.rows("lines"):
        ui.label("{.text}", shown=".tone=plain", wrap="word", lines=3)
        ui.label("{.text}", tone="dim", shown=".tone=dim", wrap="word", lines=3)
        ui.label("{.text}", tone="danger", shown=".tone=danger", wrap="word", lines=3)
