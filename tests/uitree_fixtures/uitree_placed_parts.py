"""A page on the Editor's placed kinds with a table of parts whose canvas
takes the pointer: a press on a row is handed that row."""
import uitree as ui

s = ui.state(rows=ui.model(key="k", k=""), at=ui.row_of("rows"), pressed="")


def opened():
    s.rows = [dict(k=str(i)) for i in range(4)]


def press(ev):
    s.pressed = s.pressed + "%s:%s@%d," % (ev.kind, ev.row.k if ev.row is not None else "-", ev.y)


ui.hook("opened", opened)
ui.hook("press", press, takes="pointer")


def build():
    with ui.page("Parts"):
        with ui.table("rows", cur="at", row=40):
            ui.canvas("cell", lambda cv, x, y, w, h, row: None, pointer="press")


def layer(engine):
    import uitree_app
    return uitree_app.app_layer("placed_parts", "Placed parts fixture", build, engine=engine)
