"""A desk page's foot whose button's action is unavailable and grey: the
button stays in the foot, dimmed."""
import uitree as ui

s = ui.state(ok=False, said="")


def go():
    s.said = "went"


ui.action("go", "Go", go, when="ok", off="grey")


def build():
    with ui.page("Foot"):
        ui.label("{said}")
        with ui.foot():
            ui.label("A status")
            ui.button("go", "primary")


def layer(engine):
    import uitree_app
    return uitree_app.app_layer("foot_grey_c", "Foot", build, engine=engine)
