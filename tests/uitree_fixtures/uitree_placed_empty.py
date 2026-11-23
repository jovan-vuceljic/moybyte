"""A page on the Editor's placed kinds: a canvas TOP pixels tall over an
empty with a button under its words."""
import uitree as ui

TOP = [1]
s = ui.state(top=1)


def opened():
    s.top = TOP[0]


ui.hook("opened", opened)
ui.action("go", "Go", lambda: None)


def build():
    with ui.page(""):
        ui.canvas("head", lambda cv, x, y, w, h: None, h="{top}")
        with ui.empty("Nothing here", icon="scene", lines=["A line that says why there is nothing"]):
            ui.button("go", label="Go")


def layer(engine):
    import uitree_app
    return uitree_app.app_layer("placed_empty", "Placed empty fixture", build, engine=engine)
