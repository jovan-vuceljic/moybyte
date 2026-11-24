"""Sizes a flowing page sets: a label's scale= (a display line) and w= (a
measure), a button's look="hero", a group's gap=, a row in a group's
column, and a grow= row that stands what follows it at the page's foot."""
import uitree as ui

s = ui.state(log="")
PROSE = "Bubbles float up the screen. Tap the red ones and let the rest go. " * 3


def press(arg):
    s.log = arg


ui.action("press", "Press", press, takes="arg")


def page_s2():
    with ui.page(""):
        ui.label("Title", face="title", scale=2)
        ui.button("press", arg="0", label="Under")


def page_s3():
    with ui.page(""):
        ui.label("Title", face="title", scale=3)
        ui.button("press", arg="0", label="Under")


def page_wide():
    with ui.page(""):
        ui.label(PROSE, wrap="word", lines=8, w=600)
        ui.button("press", arg="0", label="Under")


def page_narrow():
    with ui.page(""):
        ui.label(PROSE, wrap="word", lines=8, w=200)
        ui.button("press", arg="0", label="Under")


def page_foot():
    with ui.page(""):
        ui.label("Over")
        ui.row("fill", grow=True)
        with ui.row("foot", wrap=True):
            with ui.group("", gap=20):
                ui.button("press", arg="0", label="Plain")
                with ui.row("verbs", wrap=True, gap=14):
                    ui.button("press", arg="1", label="Large", look="hero")
                    ui.button("press", arg="2", label="Large")


PAGES = (page_s2, page_s3, page_wide, page_narrow, page_foot)
