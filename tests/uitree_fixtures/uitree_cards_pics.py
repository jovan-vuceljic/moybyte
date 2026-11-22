"""A cards page of the app's own pictures (PNGs, `ui.pictures.put`), a card each,
and one picture at its own place: each shows its icon tile until the engine
has decoded its picture."""
import uitree as ui

COLOURS = (b"\xff\x00\x4d", b"\x00\xe4\x36", b"\x29\xad\xff")

s = ui.state(art=ui.model("name", name="", pic=ui.IMAGE), cover=ui.IMAGE)

def opened():
    import cover_png
    for i, c in enumerate(COLOURS):
        ui.pictures.put("p%d" % i, data=cover_png.encode_indexed(bytes(cover_png.SIDE * cover_png.SIDE), c))
        s.art.put(dict(name="art %d" % i, pic=ui.image.own("p%d" % i)))
    s.cover = ui.image.own("p0")

def open_(row):
    pass


ui.hook("opened", opened)
ui.action("open", "Open", open_, takes="row")

def build():
    with ui.page("Pics"):
        ui.picture("cover", side=40, icon="star")
        with ui.cards("art", w=48, h=48):
            ui.card("open", label="{.name}", image=".pic", icon="star")

def layer(engine):
    import uitree_app
    return uitree_app.app_layer("pics_c", "Pics", build, engine=engine)
