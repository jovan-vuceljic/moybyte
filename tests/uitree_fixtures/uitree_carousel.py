"""A carousel (`ui.cards(look="carousel")`): seven cards in one row, each with
a picture of its own (`ui.pictures.put`), the centre card's name and its sub
line's items under the band; Enter plays the centre card."""
import uitree as ui

COLOURS = (b"\xff\x00\x4d", b"\x00\xe4\x36", b"\x29\xad\xff")
N = 7

s = ui.state(games=ui.model("name", name="", sub="", pic=ui.IMAGE), pick=ui.row_of("games"), played="")


def opened():
    import cover_png
    for i, c in enumerate(COLOURS):
        ui.pictures.put("p%d" % i, data=cover_png.encode_indexed(bytes(cover_png.SIDE * cover_png.SIDE), c))
    s.games = [dict(name="game %d" % i, sub="Game\tBuilt in", pic=ui.image.own("p%d" % (i % 3)))
               for i in range(N)]


def play(row):
    s.played = row.name


ui.hook("opened", opened)
ui.action("play", "Play", play, takes="row")


def build():
    with ui.page("Carousel"):
        with ui.cards("games", look="carousel", cur="pick", w=32):
            ui.card("play", label="{.name}", sub="{.sub}", image=".pic", icon="star")


def layer(engine):
    import uitree_app
    return uitree_app.app_layer("carousel_c", "Carousel", build, engine=engine)
