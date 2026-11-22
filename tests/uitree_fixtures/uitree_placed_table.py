"""A page on the Editor's placed kinds with a table whose canvas child draws
its rows (row= tall, each draw told its row), a grid of a fixed size beside
it (w= and h=, at the top of its cell), a label as wide as its text
(size="text") and a rule; a button opens a popover hung from it that holds
a slider."""
import uitree as ui

s = ui.state(rows=ui.model(key="k", k="", word=""), at=ui.row_of("rows"), chosen="",
             pop=False, v=5, n=0, gone=False)
DRAWN = []


def opened():
    s.rows = [dict(k=str(i), word="Row %d" % i) for i in range(4)]


def picked(row):
    s.chosen = row.k


def bump():
    s.n = s.n + 1


def open_pop():
    s.pop = not s.pop


def close_pop():
    s.pop = False


def draw_row(cv, x, y, w, h, row):
    DRAWN.append((int(row.k), y, h))


ui.hook("opened", opened)
ui.hook("picked", picked, takes="row")
for _k in "abcd":
    ui.action("bump_" + _k, "Bump", bump)
ui.action("open_pop", "Speed", open_pop)
ui.action("close_pop", "Close", close_pop)


def build():
    with ui.page("Table"):
        with ui.row("head"):
            ui.label("Name", size="text")
            ui.button("open_pop", label="Speed {v}", kind="bar", marked="pop")
        with ui.row("body", grow=True):
            with ui.table("rows", cur="at", row=17, changed="picked"):
                ui.canvas("cell", draw_row)
            with ui.grid(2, 2, w=100, h=48, gap="s"):
                ui.button("bump_a", label="A")
                ui.button("bump_b", label="B")
                ui.button("bump_c", label="C", shown="gone")
                ui.button("bump_d", label="D")
        ui.rule()
        with ui.row("foot"):
            ui.label("{n} bumps", align="end")
        with ui.popover("pop", anchor="open_pop", w=180, close="close_pop", shown="pop"):
            ui.slider("Speed", "v", 1, 30)


def layer(engine):
    import uitree_app
    return uitree_app.app_layer("placed_table_" + ("c" if "C" in engine.__name__ else "ref"),
                                "Placed table fixture", build, engine=engine)
