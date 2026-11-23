"""The home's pages the home layers host. The carousel arrangement's band
(`band`): the tab's cards as the engine's carousel, which moves itself on
the band's host (`home_carousel.Carousel._page_pass`): on the handheld its
row, on the desk its shelf under the hero and the details; the grid
arrangement's (`shelf`) and the icons arrangement's (`icons`) the engine's
shelf and icons, on every class (`home_grid.Launcher._cells_pass`). The
host puts their rows (`band_put`), the card a selection made from outside
lands them on and their words' ink (`band_set`), and draws their pictures.

The desk home's hero (`hero`): the selected card's picture, which the
host draws, a tap on it the tab's tap (`HomeDetails.hero_press`). Its
details pane (`page`), beside the hero
(`home_details.HomeDetails`): the selected card's title,
its metadata line, its description, its facts (how often and when it was
played, who made it) and its verb buttons, the tab's tap verb first, the
facts and the buttons at the hero's foot (a `grow=True` row over them).

The host writes what the card shows (`put`, run when the card, the tab or
the verbs move). Its buttons are places, the card's verbs in order (`b0`,
`b1`, ...), so the button the keys are on stays a stop of the frame before
when the card's verbs change; the host keeps the keys and hands the page
the one they are on as its focus.
"""

import uitree as ui
import uitree_app

BUTTONS = 4          # the most verbs a card shows: Projects' Make card's
FACTS = 3            # the most facts a card shows: Played, Last, By

SHOWN = tuple("b%d" % k for k in range(BUTTONS))      # each button shown
LABELS = tuple("l%d" % k for k in range(BUTTONS))     # ...its words
ICONS = tuple("i%d" % k for k in range(BUTTONS))      # ...its glyph, "" none
KINDS = tuple("k%d" % k for k in range(BUTTONS))      # ...its look
ARGS = tuple(str(k) for k in range(BUTTONS))
FACT_KEYS = tuple("fk%d" % k for k in range(FACTS))   # each fact's caption
FACT_VALUES = tuple("fv%d" % k for k in range(FACTS))  # ...and its value

_decl = dict(title="", title_scale=1, meta="", desc="", desc_w=0, meta_on=True, facts_on=True)
for _k in range(BUTTONS):
    _decl[SHOWN[_k]] = False
    _decl[LABELS[_k]] = ""
    _decl[ICONS[_k]] = ""
    _decl[KINDS[_k]] = ui.enum("normal", "primary", "danger", init="normal")
for _k in range(FACTS):
    _decl[FACT_KEYS[_k]] = ""
    _decl[FACT_VALUES[_k]] = ""
_decl["cards"] = ui.model("id", id="", name="", sub="", pic=ui.IMAGE)    # the band's cards
_decl["sel"] = ui.row_of("cards")        # ...the one it rests on
_decl["tone"] = ""       # ...and its caption's ink ("" the theme's)
_decl["side"] = 64       # ...its cards' side (the desk shelf's, in glass pixels)
_decl["caption"] = ""    # ...and the desk shelf's caption
_decl["hero"] = ui.IMAGE     # the desk hero's picture: the selected card's
_decl["hero_side"] = 128     # ...and its side, in glass pixels
s = ui.state(**_decl)


def put():
    """What the card shows, the host's (`HomeDetails.details_put`)."""
    uitree_app.env().details_put(s)


def _press(arg):
    uitree_app.env().details_press(int(arg))


def band_put():
    """The band's cards, the host's (`Carousel.band_put`)."""
    uitree_app.env().band_put(s)


def band_set():
    """The band's current card and its caption's ink, the host's
    (`Carousel.band_set`)."""
    uitree_app.env().band_set(s)


def _open(row):
    uitree_app.env().band_open(row)


def _hero():
    uitree_app.env().hero_press()


ui.hook("put", put)
ui.hook("band_put", band_put)
ui.hook("band_set", band_set)
ui.action("press", "Choose", _press, takes="arg")
ui.action("open", "Open", _open, takes="row")
ui.action("play", "Open", _hero)


def band():
    with ui.page(""):
        with ui.cards("cards", look="carousel", cur="sel", tone="{tone}", w="{side}", label="{caption}"):
            ui.card("open", label="{.name}", sub="{.sub}", image=".pic")


def shelf():
    with ui.page(""):
        with ui.cards("cards", look="shelf", cur="sel", tone="{tone}"):
            ui.card("open", label="{.name}", sub="{.sub}", image=".pic")


def icons():
    with ui.page(""):
        with ui.cards("cards", look="icons", cur="sel", tone="{tone}"):
            ui.card("open", label="{.name}", sub="{.sub}", image=".pic")


def page():
    with ui.page(""):
        with ui.row("words", wrap=True):
            with ui.group("", gap=12):
                ui.label("{title}", face="title", scale="{title_scale}")
                ui.label("{meta}", tone="dim", face="ui", shown="meta_on && meta")
                ui.label("{desc}", tone="dim", face="ui", wrap="word", lines=2, w="{desc_w}", shown="desc")
        ui.row("fill", grow=True)                   # the facts and the buttons at the hero's foot
        with ui.row("foot", wrap=True):
            with ui.group("", gap=16):
                with ui.row("facts", wrap=True, gap=48, shown="facts_on && fk0"):
                    for k in range(FACTS):
                        with ui.group("", gap=6, shown=FACT_KEYS[k]):
                            ui.label("{%s}" % FACT_KEYS[k], tone="dim", face="ui")
                            ui.label("{%s}" % FACT_VALUES[k], face="ui")
                with ui.row("verbs", wrap=True, gap=14):
                    for k in range(BUTTONS):
                        ui.button("press", "{%s}" % KINDS[k], arg=ARGS[k], label="{%s}" % LABELS[k],
                                  icon="{%s}" % ICONS[k], shown=SHOWN[k], look="large")


def hero():
    with ui.page(""):
        ui.picture(image="hero", side="{hero_side}", on="play", look="tile")


DESK_PAGES = (page, hero)    # a handheld's home has no details pane: its image carries none
