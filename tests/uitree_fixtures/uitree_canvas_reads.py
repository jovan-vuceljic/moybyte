"""A page whose canvas names the states its draw reads (reads=), and one
whose canvas names none."""
import uitree as ui

s = ui.state(n=3, other=0)
DREW = []


def draw_n(cv, x, y, w, h):
    DREW.append(s.n)
    cv.rect(x, y, min(w, 4 * s.n), h, 7)


def draw_other(cv, x, y, w, h):
    DREW.append(s.other)


def build_reads():
    with ui.page("Reads"):
        ui.label("{other}")
        ui.canvas("dial", draw_n, h=20, reads=["n"])


def build_none():
    with ui.page("None"):
        ui.label("{other}")
        ui.canvas("dial", draw_n, h=20)


def build_wrong():
    with ui.page("Wrong"):
        ui.canvas("dial", draw_other, h=20, reads=["n"])


def layer(engine, build):
    import uitree_app
    return uitree_app.app_layer(build.__name__[6:] + "_cr", "Reads", build, engine=engine)
