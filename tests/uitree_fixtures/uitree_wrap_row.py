"""A wrap= row (`ui.row(wrap=True)`): its buttons packed from its start at
their natural widths, wrapping where the next does not fit; and a wrap=
row of two columns, each as wide as its widest line."""
import uitree as ui

s = ui.state(log="")


def press(arg):
    s.log = arg


ui.action("press", "Press", press, takes="arg")


def page():
    with ui.page(""):
        with ui.row("facts", wrap=True, gap=40):
            with ui.group(""):
                ui.label("Played", tone="dim", face="caption")
                ui.label("Not yet", face="ui")
            with ui.group(""):
                ui.label("By", tone="dim", face="caption")
                ui.label("Moybyte", face="ui")
        with ui.row("verbs", wrap=True, gap=14):
            for k, word in enumerate(("Play", "Change", "Duplicate", "Delete")):
                ui.button("press", arg=str(k), label=word)
