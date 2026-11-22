"""A page with a stepper over three values: its prev and next actions
greyed at the ends (when=), its value a template; and a placed page's row
holding one as a fill between two buttons."""
import uitree as ui

s = ui.state(n=0, word="1 / 3", first=True, last=False, log="")


def _show():
    s.word = "%d / 3" % (s.n + 1)
    s.first, s.last = s.n == 0, s.n == 2


def prev():
    s.n -= 1
    s.log += "<"
    _show()


def next_():
    s.n += 1
    s.log += ">"
    _show()


ui.action("prev", "Earlier", prev, when="!first", off="grey")
ui.action("next", "Later", next_, when="!last", off="grey")
ui.action("other", "Other", lambda: None)
ui.action("more", "More", lambda: None)


def build():
    with ui.page("Stepper"):
        ui.stepper("{word}", "prev", "next")


def build_placed():
    with ui.page("Stepper"):
        with ui.row("head", pad=4):
            ui.button("other", icon="new", alone=True, kind="bar")
            ui.stepper("{word}", "prev", "next", tone="dim", grow=True)
            ui.button("more", label="More", kind="bar")


def layer(engine, placed=False):
    import uitree_app
    return uitree_app.app_layer("stepper_fx", "Stepper fixture", build_placed if placed else build,
                                engine=engine)
