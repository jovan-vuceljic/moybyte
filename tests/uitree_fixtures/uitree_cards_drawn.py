"""A cards page whose pictures the app draws when the engine asks
(`ui.pictures.put(KEY, render=FN)`): each card shows its icon tile until its
picture is drawn, at the card's size, into a layer the engine keeps."""
import uitree as ui

INKS = (8, 11, 12)
CANVAS = [None]                 # the canvas a layer is made on (the test's console's)
DRAWN = []
LAYERS = []

s = ui.state(art=ui.model("name", name="", pic=ui.IMAGE))


def _drawer(ink):
    def render(w, h):
        cv = CANVAS[0]
        lay = cv.new_layer(w, h)
        lay.rect(0, 0, w, h, ink)
        DRAWN.append((ink, w, h))
        LAYERS.append(lay)
        return lay
    return render


def opened():
    for i, ink in enumerate(INKS):
        ui.pictures.put("d%d" % i, render=_drawer(ink))
        s.art.put(dict(name="drawn %d" % i, pic=ui.image.own("d%d" % i)))


def open_(row):
    pass


ui.hook("opened", opened)
ui.action("open", "Open", open_, takes="row")


def build():
    with ui.page("Drawn"):
        with ui.cards("art", w=48, h=48):
            ui.card("open", label="{.name}", image=".pic", icon="star")


def layer(engine):
    import uitree_app
    return uitree_app.app_layer("drawn_c", "Drawn", build, engine=engine)
