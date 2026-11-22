"""A popover hung from the rect its host hands in (`at=`, "X Y W H")."""
import uitree as ui

s = ui.state(at="")


def put(at):
    s.at = at


def go():
    pass


ui.hook("put", put, takes="arg")
ui.action("go", "Go", go)


def page():
    with ui.page(""):
        with ui.popover("pop", w=120, at="{at}"):
            ui.link("go")
