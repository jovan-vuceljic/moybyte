"""A derive naming a system value (`@desk`) as a node's shown=: Go shows on
the desk, or on a handheld once Files is the view; Inline, the same
condition written in place, shows where Go does."""
import uitree as ui

s = ui.state(view=ui.enum("places", "files", init="places"))
ui.derive("go_shown", cond="@desk || view=files")


def go():
    s.view = "files"


ui.action("go", "Go", go)
ui.action("inline", "Inline", go)
ui.action("turn", "Turn", go)


def build():
    with ui.page("Derive"):
        ui.button("turn")
        ui.button("go", shown="go_shown")
        ui.button("inline", shown="@desk || view=files")


def layer(engine):
    import uitree_app
    return uitree_app.app_layer("derive_sys", "Derive", build, engine=engine)
