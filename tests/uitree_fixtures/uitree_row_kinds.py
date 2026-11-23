"""The kinds a list's rows hold beyond a toggle and a slider: a seg bound
to a row's int field (its items the lines of a row template), a canvas
handed its row by its draw, keys and pointer, with a hint; and a dialog of
two fields that on the T-Deck draws no buttons (`look="keys"`), its verb's
label a template (`labels=`)."""
import uitree as ui

s = ui.state(
    rows=ui.model(key="id", id="", shape=ui.enum("seg", "pic", init="seg"), k=0, words=""),
    asking=False, a="", b="", log="", taken=False)

DRAWN = []          # (row id, w, h) each canvas draw was handed
KEYS = []           # (row id, whether a was pressed) each keys= call was handed


def fill(rows):
    s.rows = rows


def ask():
    s.asking = True


def chose(row):
    s.log = "%s=%d" % (row.id, row.k)


def draw(cv, x, y, w, h, row):
    DRAWN.append((row.id, w, h))


def keys(i, row):
    if i.pressed("right"):
        KEYS.append(row.id)
        return True
    return False


def at(ev):
    s.log = "%s %s %d" % (ev.kind, ev.row.id if ev.row is not None else "-", ev.y)


def take():
    s.taken = True


def ok():
    s.asking = False


def cancel():
    s.asking = False


ui.hook("fill", fill, takes="arg")
ui.hook("ask", ask)
ui.hook("take", take)
ui.hook("chose", chose, takes="row")
ui.hook("at", at, takes="pointer")
ui.action("ok", "Save", ok)
ui.action("cancel", "Cancel", cancel)


def page():
    with ui.page(""):
        ui.rows("rows", by="shape", cases={
            "seg": lambda: ui.seg("Pick", ".k", text="{.words}", look="cycle", on="chose"),
            "pic": lambda: ui.canvas("pic", draw, h=30, keys=keys, pointer="at", hint="Take")})
        with ui.dialog("Two", ["cancel", "ok"], shown="asking", look="keys",
                       labels=["Cancel", "{taken?Replace:Save}"]):
            ui.field("A", "a")
            ui.field("B", "b")
