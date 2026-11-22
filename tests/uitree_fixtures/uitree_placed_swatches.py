"""A page on the Editor's placed kinds with a seg of the swatches look over
a row_of (each row's word its colour), a canvas that answers the pointer,
a row of icon buttons of their own width beside a word, and a button that
opens a popover hung `at=` a rect whose list of links is a menu, each row
its link's icon."""
import uitree as ui

s = ui.state(dots=ui.model(key="k", k="", rgb=0), dot=ui.row_of("dots"), presses=0, pop=False,
             items=ui.model(key="k", k="", label="", icon=""), took="", at="10 40 180 0")


def opened():
    s.dots = [dict(k=k, rgb=v) for k, v in (("red", 0xFF004D), ("green", 0x00E436), ("blue", 0x29ADFF))]
    s.dot = "red"
    s.items = [dict(k="a", label="Alpha", icon="music"), dict(k="b", label="Beta", icon="new")]


def pressed(ev):
    if ev.kind == "down":
        s.presses = s.presses + 1


def open_pop():
    s.pop = True


def close_pop():
    s.pop = False


def took(row):
    s.took = row.k
    s.pop = False


def draw_area(cv, x, y, w, h):
    pass


ui.hook("opened", opened)
ui.hook("pressed", pressed, takes="pointer")
ui.action("open_pop", "Open", open_pop)
ui.action("close_pop", "Close", close_pop)
ui.action("take", "Take", took, takes="row")
ui.action("one", "One", lambda: None)
ui.action("two", "Two", lambda: None)


def build():
    with ui.page("Swatches"):
        with ui.row("brush", pad=12):
            ui.seg("Colour", "dot", text="{.rgb}", look="swatches")
        ui.canvas("area", draw_area, pointer="pressed")
        with ui.row("ops", pad=12):
            ui.button("one", icon="new", alone=True, w=14)
            ui.button("two", icon="trash", alone=True, w=14)
            ui.button("open_pop", label="Menu", kind="bar")
        with ui.popover("pop", at="{at}", w=180, close="close_pop", shown="pop"):
            with ui.rows("items"):
                ui.link("take", label="{.label}", icon="{.icon}")


def layer(engine):
    import uitree_app
    return uitree_app.app_layer("placed_swatches", "Placed swatches fixture", build, engine=engine)
