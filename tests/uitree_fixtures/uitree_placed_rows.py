"""Pages on the Editor's placed kinds and a flowing one: a placed page's
rows lists whose bodies are rows (a rows' body and a by= case), a placed
row of two groups, a rows list standing in the page's stack over a button,
and a flowing page with a split among its rows."""
import uitree as ui

s = ui.state(items=ui.model(key="k", k="", name=""), cur=ui.row_of("items"),
             kinds=ui.model(key="k", k="", name="", kind=ui.enum("x", "y", init="x")))


def opened():
    s.items = [dict(k="a", name="Alpha"), dict(k="b", name="Beta"), dict(k="c", name="Gamma")]
    s.kinds = [dict(k="p", name="Pear", kind="x"), dict(k="q", name="Quince", kind="y"),
               dict(k="r", name="Rye", kind="x")]


ui.hook("opened", opened)
ui.action("go", "Go", lambda row: None, takes="row")
ui.action("left", "Left", lambda: None)
ui.action("right", "Right", lambda: None)
ui.action("after", "After", lambda: None)


def _x():
    with ui.row("xrow", pad=10):
        ui.label("X {.name}")
        ui.button("go", label="Go")


def _y():
    ui.label("Y {.name}")


def rows_page():
    with ui.page(""):
        with ui.scroll("view"):
            with ui.rows("items", cur="cur"):
                with ui.row("inrow", pad=10):
                    ui.label("{.name}")
                    ui.button("go", label="Go")
            ui.label("By kind")
            ui.rows("kinds", by="kind", cases={"x": _x, "y": _y})


def bare_page():
    with ui.page(""):
        with ui.rows("items", cur="cur"):
            ui.button("go", label="{.name}")
        ui.button("after", label="After")


def groups_page():
    with ui.page(""):
        with ui.row("two"):
            with ui.group("left"):
                ui.button("left", label="Left")
            with ui.group("right"):
                ui.button("right", label="Right")


def split_page():
    with ui.page("Split"):
        ui.label("Before")
        with ui.split("row", sizes=(1, 1)):
            with ui.group(""):
                ui.label("L1")
                ui.label("L2")
                ui.label("L3")
            with ui.group(""):
                ui.label("R1")
        ui.button("after", label="After")


def layer(build, engine):
    import uitree_app
    return uitree_app.app_layer("prows_" + build.__name__[:6], "Placed rows fixture", build, engine=engine)
