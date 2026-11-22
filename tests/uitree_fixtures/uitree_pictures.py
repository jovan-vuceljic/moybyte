"""A page with a seg of look="pictures" over three values: each value's
word an own picture (`own:face:K`) the app draws on a clear ground
(`ui.pictures.put(..., clear=True)`), a square of one colour in the middle
of its tile."""
import uitree as ui

s = ui.state(face=ui.enum("x", "y", "z", init="x"), log="")
ui.labels("FACES", {"x": "own:face:x", "y": "own:face:y", "z": "own:face:z"})

CANVAS = [None]         # the canvas the pictures' layers are made on (the test's glass)
INK = 8                 # the squares' colour (MOY64's red)


def _render(w, h):
    lay = CANVAS[0].new_layer(w, h)
    lay.fill565(0, 0, w, h, 0xF81F)
    lay.rect(w // 4, h // 4, w // 2, h // 2, INK)
    return lay


def opened():
    for k in ("x", "y", "z"):
        ui.pictures.put("face:" + k, render=_render, clear=True)


def took():
    s.log += s.face


ui.hook("opened", opened)
ui.hook("took", took)


def build():
    with ui.page("Pictures"):
        ui.seg("Face", "face", labels="FACES", look="pictures", on="took")


def layer(engine):
    import uitree_app
    return uitree_app.app_layer("pictures_fx", "Pictures fixture", build, engine=engine)
