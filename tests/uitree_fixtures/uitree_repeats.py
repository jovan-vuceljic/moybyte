"""A field and a long list for the frame's steps beyond its presses
(tests/test_input_repeat.py): the REP word's roll, the KEYREP word's typing."""
import uitree as ui

s = ui.state(text="", done=0, rows=ui.model(key="k", k=""), cur=ui.row_of("rows"))


def commit():
    s.done += 1


def opened():
    for i in range(40):
        s.rows.put({"k": "Row %d" % i})


def pick(row):
    s.cur = row


ui.action("commit", "Done", commit)
ui.action("pick", "Pick", pick, takes="row")
ui.hook("opened", opened)


def field():
    with ui.page("Field"):
        ui.field("Name", "text", changed="commit")


def rows():
    with ui.page("Rows"):
        with ui.rows("rows", cur="cur"):
            ui.link("pick", label="{.k}")


def secret():
    with ui.page("Probe"):
        ui.field("Password", "text", 64, secret=True)


def plain():
    with ui.page("Probe"):
        ui.field("Password", "text", 64)
