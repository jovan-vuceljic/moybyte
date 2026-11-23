# Map (grep -n a name to jump there):
#   fill                          the page's states from the layer's fields
#   build                         the page: caption, cards, the desk's foot, menu, dialog, toast
#   MyArtAppLayer                 the My Art app: the drawings, their verbs, the page sent to
#   MyArtAppLayer._verb           a drawing's verbs: open, wallpaper, game, rename, dup, trash
#   MyArtAppLayer.idle_step       a drawing read against what its picture was made from
"""My Art -- the drawings' page, which Paint's Open... and Files' Art open
alike, a `uitree` page the C engine lays out and paints (the look's
docs/media/look_2026-10/APPS_RESTYLE.md, My Art).

The drawings are cards, New drawing the first, each its drawing at 4:3 and
its name. A card's picture is the engine's (`image.store`): read from its
file and made whole inside the card's tile, at its own aspect, one a frame
before the frame paints (`uitree_pics`). A drawing another app
wrote since its picture was made is read again on an idle frame and made
again where its bytes moved (`ui.pictures.changed`). The drawing that is
the wallpaper wears the `wallpaper` badge, and the caption says it. Enter
(a tap) opens a drawing in Paint; M opens a card's menu -- Open in Paint,
Use as wallpaper, Put in a game... (a 320 x 240 drawing), Rename...,
Duplicate and, set apart in the danger ink, Move to Trash -- and each has
its key: W, G, R, Ctrl+D, Del. Move to Trash asks nothing: the Trash gives a
drawing back. On the desk the window's foot carries the focused card's
verbs. With nothing drawn yet the page says so and offers New drawing.
"""

import ui_font as _ui_font
import uitree as ui
import uitree_app

from layout_base import bar_rows, content_of, ground_round, metric_class, DESK
from moy_store_base import builtin_name
from artwork import picture_size, GAME_W, GAME_H
from picture_copies import PictureCopies
from drawing_pages import GamePage, shown, dot, dots
from ticks import _ticks_ms, _ticks_diff
import intents as _intents


DRAWINGS = "drawings"
TOAST_MS = 2000
NEW = "+"                       # New drawing's card: a key no drawing's name is
# The verbs' typed keys outside the engine's letters: a page's keys= takes
# no Del and no Ctrl+D, and these act only on a drawing with no page open.
_KEYS = {ord("w"): "wallpaper", ord("g"): "game", ord("r"): "rename", 0x04: "dup",
         0x7F: "trash", 0x08: "trash"}


# -- the page -----------------------------------------------------------------------

s = ui.state(
    none=False,                 # nothing drawn yet
    count="",                   # the caption: how many, and the wallpaper's drawing
    wall="",
    art=ui.model(key="id", id="", label="", icon="", tone="", badge="", pic=ui.IMAGE),
    cur=ui.row_of("art"),
    picked=False,               # a drawing is focused, not New drawing
    game_ok=False,              # ...and it is the size a game takes
    status="",                  # the desk foot's words
    menu=False,                 # the focused drawing's menu
    menu_title="",
    renaming=False,             # Rename's dialog
    rn_title="",
    name="",
    toasting=False,
    toast="",
    toast_icon="check",
)
ui.app("My Art", icon="art")


def _lay():
    """The app's Layer, which a handler's run owes a fill."""
    lay = uitree_app.env()
    lay.fill_owed = True
    return lay


def _set(lay, name, value):
    """State `name` written only where it moved."""
    if lay.shown.get(name) != value:
        lay.shown[name] = value
        setattr(s, name, value)


def _rows(lay):
    rows = [{"id": NEW, "label": "New drawing", "icon": "new", "tone": "value", "badge": "",
             "pic": None}]
    for name in lay.drawings:
        rows.append({"id": name, "label": shown(name), "icon": "", "tone": "",
                     "badge": "wallpaper" if name == lay.wallpaper else "",
                     "pic": ui.image.store(DRAWINGS + "/" + name)})
    return rows


def fill(lay):
    """The page's states from the layer's fields: the cards, the caption,
    the focused drawing's verbs and foot, the menu, the dialog, the toast."""
    n = len(lay.drawings)
    _set(lay, "none", not n)
    _set(lay, "art", _rows(lay) if n else [])
    _set(lay, "count", "%d drawing%s" % (n, "" if n == 1 else "s"))
    _set(lay, "wall", "Wallpaper: " + shown(lay.wallpaper) if lay.wallpaper else "")
    name = lay.cur
    _set(lay, "picked", name is not None)
    _set(lay, "game_ok", name is not None and lay._size(name) == (GAME_W, GAME_H))
    if lay.desk:
        # the foot's words: a page state, so written only where a foot shows
        # them (focus moving moves the page's gen)
        if name is None:
            status = "%d drawings" % n
        else:
            w, h = lay._size(name)
            status = shown(name) + dot() + ("%d \u00d7 %d" % (w, h) if _ui_font.print_symbols()
                                            else "%dx%d" % (w, h))
        _set(lay, "status", status)
    menu = lay.menu and name is not None
    _set(lay, "menu", menu)
    if menu:
        _set(lay, "menu_title", shown(name))
    r = lay.renaming
    _set(lay, "renaming", r is not None)
    if r is not None:
        _set(lay, "rn_title", "Rename " + shown(r))
    t = lay.toast
    _set(lay, "toasting", t is not None)
    if t is not None:
        _set(lay, "toast", t[0])
        _set(lay, "toast_icon", t[1])
    f = lay._focus
    if f is not None:
        lay._focus = None
        if n:
            ui.focus(f + "/open")


def opened():
    fill(_lay())


def moved(row):
    """Focus moved to a card: the foot and the keys follow it."""
    lay = uitree_app.env()
    cur = None if row is None or row.id == NEW else row.id
    if cur != lay.cur:
        lay.cur = cur
        lay.fill_owed = True


def open_card(row):
    lay = _lay()
    if row.id == NEW:
        lay._verb("new")
    else:
        lay.cur = row.id
        lay._verb("open", row.id)


def _verb(verb):
    def press():
        _lay()._verb(verb)
    return press


def close_menu():
    _lay().menu = False


def cancel():
    lay = _lay()
    if lay.renaming is not None:
        lay._focus = lay.renaming
    lay.renaming = None


def rename():
    lay = _lay()
    name = lay.renaming
    lay.renaming = None
    if name is not None:
        lay._rename(name, s.name)


ui.hook("opened", opened)
ui.hook("moved", moved, takes="row")
ui.action("open", "Open", open_card, takes="row")
ui.action("new", "New drawing", _verb("new"), keys=("n",), hint="New",
          when="!none && !menu && !renaming", off="hide")
ui.action("first", "New drawing", _verb("new"))
ui.action("open_menu", "Menu", _verb("menu"), keys=("m",), when="picked && !menu && !renaming",
          off="hide")
ui.action("open_it", "Open", _verb("open"), icon="paint")
ui.action("wallpaper", "Use as wallpaper", _verb("wallpaper"), icon="wallpaper")
ui.action("game", "Put in a game", _verb("game"), icon="export", when="game_ok", off="hide")
ui.action("rename_ask", "Rename", _verb("rename"), icon="pencil")
ui.action("dup", "Duplicate", _verb("dup"), icon="dup")
ui.action("trash", "Move to Trash", _verb("trash"), icon="trash")
ui.action("close_menu", "Close", close_menu)
ui.action("cancel", "Cancel", cancel)
ui.action("rename", "Rename", rename)


def _grid():
    with ui.row("caption", pad=16, shown="!none"):
        ui.label("{count}", tone="dim", face="caption")
        ui.label("{wall}", tone="dim", face="caption", align="end", shown="wall")
    with ui.cards("art", cur="cur", changed="moved", w="{@desk?152:88}", h="{@desk?114:66}",
                  pad="{@desk?22:12}", shown="!none"):
        ui.card("open", label="{.label}", icon="{.icon}", tone="{.tone}", badge="{.badge}",
                image=".pic")
    with ui.foot(shown="@desk && !none"):
        ui.label("{status}", tone="dim", face="caption")
        ui.button("trash", "danger", shown="picked")
        ui.button("wallpaper", shown="picked")
        ui.button("game", shown="picked")
        ui.button("open_it", "primary", shown="picked")
        ui.button("new", "primary", icon="new", shown="!picked")


def _empty():
    with ui.empty("No drawings yet", icon="art", shown="none",
                  lines=["Draw something in Paint", "and it lands here."]):
        ui.button("first", "primary", icon="new", w="{@desk?180:124}", focus=True)


def build():
    with ui.page(""):
        _grid()
        _empty()
        with ui.popover("card_menu", anchor="art.cur", shown="menu", close="close_menu",
                        w="{@desk?260:186}", wash="page"):
            with ui.menu("{menu_title}"):
                ui.item("open_it", label="Open in Paint\tEnter", icon="paint")
                ui.item("wallpaper", label="Use as wallpaper\tW")
                ui.item("game", label="Put in a game" + dots() + "\tG")
                ui.item("rename_ask", label="Rename" + dots() + "\tR")
                ui.item("dup", label="Duplicate\tCtrl D")
            with ui.menu(""):
                ui.item("trash", label="Move to Trash\tDel", mkind="danger")
        with ui.dialog("{rn_title}", ["cancel", "rename"], shown="renaming"):
            ui.field("Name", "name", 32, on="rename")
        ui.toast("{toast}", icon="{toast_icon}", shown="toasting")


def is_app(cart):
    """True only for the shipped My Art identity, not a renamed or copied
    cart."""
    if not cart or cart.get("title") != "My Art":
        return False
    path = cart.get("path")
    return not path or builtin_name(path) == "moybyte.my_art.moy"


class _Owed:
    """The app's damage: what owes a frame owes the page a fill too."""

    def __init__(self, damage, lay):
        self._d, self._lay = damage, lay

    def all(self):
        self._lay.fill_owed = True
        self._d.all()

    def again(self):
        self._lay.fill_owed = True
        self._d.again()


def _check(lay, name):
    """Drawing `name` read against what its picture was made from: a
    picture of bytes that moved is made again."""
    blob, err = lay._files.load(DRAWINGS, name)
    if err is not None or not blob:
        return
    if not isinstance(blob, (str, bytes)):
        blob = bytes(blob)
    sig = (len(blob), hash(blob))
    was = lay._sigs.get(name)
    lay._sigs[name] = sig
    if was is not None and was != sig:
        ui.pictures.changed(DRAWINGS + "/" + name)
        lay._damage.all()


class MyArtAppLayer(uitree_app.app_layer("myart", "My Art", build, is_app,
                                         needs=("files", "nav", "artwork", "carts",
                                                "wallpaper"))):
    """The My Art app: the page's engine handed this layer as what its
    handlers reach (`uitree_app.env()`), the drawings and their verbs, and
    Put in a game hosted over the page."""

    TITLE = "My Art"

    def __init__(self, ctx, names=None):
        super().__init__(ctx, names)
        self.engine.env = self
        self._files = ctx.files
        self._nav = ctx.nav
        self._art = ctx.artwork
        self._wall = ctx.wallpaper
        self._ui = ctx.ui
        self.copies = PictureCopies(ctx)
        self.names = names
        self.desk = metric_class() == DESK
        self._damage = _Owed(self._damage, self)
        self.shown = {}               # each state as last written (`_set`)
        self.fill_owed = True
        self.drawings = []            # names, newest first
        self.sizes = {}               # name -> (w, h), read from its head
        self.wallpaper = None         # the drawing the wallpaper was copied from
        self.cur = None               # the drawing focus is on (None: New drawing)
        self.menu = False             # the focused card's menu is open
        self.renaming = None          # the drawing Rename asks a name for
        self.game = None              # Put in a game, over the page
        self.toast = None             # (text, icon, until ms)
        self._focus = None            # the card focus moves to on the next fill
        self._sigs = {}               # name -> (length, hash) of the bytes last read
        self._unchecked = []          # the drawings to read against their pictures, one an idle frame

    # -- the drawings -----------------------------------------------------------

    def _refresh(self):
        files = self._files
        names, err = files.list(DRAWINGS) if files.ready() else ([], None)
        self.drawings = list(names or []) if err is None else []
        self.sizes = {}
        self.wallpaper = self._wall_source()
        if self.cur not in self.drawings:
            self.cur = None
        self.fill_owed = True

    def _size(self, name):
        got = self.sizes.get(name)
        if got is None:
            blob, err = self._files.load(DRAWINGS, name)
            got = (picture_size(blob) if err is None else None) or (0, 0)
            self.sizes[name] = got
        return got

    def _wall_source(self):
        """The drawing the wallpaper in force was copied from, or None."""
        wp = self.copies.wallpaper_id()
        if wp is None or self._wall.current() != wp:
            return None
        blob, err = self._wall.load_copy()
        if err is not None or not blob:
            return None
        got = self._files.provenance(blob)
        src = got[0] if got else None
        if not src or not str(src).startswith(DRAWINGS + "/"):
            return None
        name = str(src)[len(DRAWINGS) + 1:]
        return name if name in self.drawings else None

    # -- the app protocol (docs/app_api_v1.md) ----------------------------------

    def open(self):
        self.menu = False
        self.renaming = None
        self._close_game()
        self.toast = None
        self._refresh()
        self._unchecked = list(self.drawings)
        self.cur = self.drawings[0] if self.drawings else None
        self._focus = self.cur or NEW
        super().open()

    def close(self):
        self.menu = False
        self.renaming = None
        self._close_game()
        self._unchecked = []
        super().close()

    def _close_game(self):
        if self.game is not None:
            self.game.close()
            self.game = None
            self._ui.reset()

    @property
    def idle_owed(self):
        return bool(self._unchecked) or self.engine.idle_owed

    def idle_step(self):
        """A frame with nothing to paint: a picture owed is made, else a
        drawing is read against the picture made from it."""
        if self.engine.idle_owed or not self._unchecked:
            super().idle_step()
            return
        self.engine.run(_check, self, self._unchecked.pop(0), action="check")

    def has_page(self):
        return self.menu or self.renaming is not None or self.game is not None

    def back(self):
        if self.renaming is not None:
            self._focus = self.renaming
            self.renaming = None
        elif self.menu:
            self.menu = False
            self._focus = self.cur
        elif self.game is not None:
            self._close_game()
            self._focus = self.cur
        else:
            return False
        self._damage.all()
        return True

    def page_title(self):
        return "Put in a game" if self.game is not None and not self.desk else None

    def owe(self):
        """The page's states owe a fill, and the page a frame."""
        self._damage.all()

    # -- input ------------------------------------------------------------------

    def handle_input(self, inp):
        k = getattr(inp, "typed", 0)
        if self.toast is not None and (k or inp.any_pressed()):
            self.toast = None
            self._damage.all()
        if inp.pressed("b"):
            self.back()
            return True
        if self.game is not None:
            return self.game.keys(inp)
        if k and not self.has_page() and self.cur is not None:
            verb = _KEYS.get(k + 32 if 65 <= k <= 90 else k)
            if verb is not None:
                self._verb(verb)
                return True
        return self.engine.keys(inp)

    def handle_pointer(self, px, py, click):
        if self.game is not None:
            return self.game.point(px, py, click)
        return self.engine.point(px, py, click)

    # -- verbs ------------------------------------------------------------------

    def _say(self, text, icon="check"):
        self.toast = (text, icon, _ticks_ms() + TOAST_MS)
        self._damage.all()

    def _open(self, name):
        """A drawing to the app that opens pictures, by the intents' route
        (runtime/system/intents.py), as Files' OPEN goes."""
        _intents.INTENTS.open_with(_intents.SHELL, _intents.item_of(DRAWINGS, name), False)

    def focus_card(self, name):
        """Focus to drawing `name`'s card (New drawing's with None)."""
        self.cur = name
        self._focus = name or NEW
        self._damage.all()

    def do_menu(self, name):
        """Drawing `name`'s menu open over its card."""
        self.cur = name
        self._verb("menu", name)

    def verb(self, verb, name=None):
        self._verb(verb, name)

    def _verb(self, verb, name=None):
        name = name or self.cur
        files = self._files
        self.menu = False
        if verb == "new":
            got, err = files.new_name(DRAWINGS)
            if err is None:
                self._open(got)
            return
        if name is None:
            return
        if verb == "menu":
            self.menu = True
        elif verb == "open":
            self._open(name)
        elif verb == "wallpaper":
            if self.copies.set_wallpaper(name):
                self.wallpaper = name
                self._say(shown(name) + " is the wallpaper")
            else:
                self._say(self.copies.last_error or "Can't use it", "warn")
        elif verb == "game":
            if self._size(name) == (GAME_W, GAME_H):
                self._ui.reset()
                self.game = GamePage(self.copies, self._nav, name, self._ui, self._damage)
        elif verb == "rename":
            self.renaming = name
            self.engine.run(_named, shown(name), action="rename")
        elif verb == "dup":
            got, err = files.duplicate(DRAWINGS, name)
            if err is None:
                self._refresh()
                self._focus = got
                self.cur = got
                self._say("Duplicated as " + shown(got))
            else:
                self._say(str(err), "warn")
        elif verb == "trash":
            _got, err = files.delete(DRAWINGS, name)
            if err is None:
                i = self.drawings.index(name) if name in self.drawings else 0
                self._refresh()
                nxt = self.drawings[min(i, len(self.drawings) - 1)] if self.drawings else None
                self.cur = nxt
                self._focus = nxt or NEW
                self._say("Moved " + shown(name) + " to the Trash", "trash")
            else:
                self._say(str(err), "warn")
        self._damage.all()

    def _rename(self, name, text):
        new = str(text).strip().replace(" ", "_").lower()
        if not new or new == name:
            self._focus = name
            return
        got, err = self._files.rename(DRAWINGS, name, new)
        if err is not None:
            self._focus = name
            self._say(str(err), "warn")
            return
        new = got or new
        self._art.follow(DRAWINGS, name, new)
        self._refresh()
        self.cur = new
        self._focus = new
        self._damage.all()

    # -- the frame --------------------------------------------------------------

    def draw(self, dt):
        if self.toast is not None:
            if _ticks_diff(_ticks_ms(), self.toast[2]) >= 0:
                self.toast = None
                self.fill_owed = True
            else:
                self._damage.again()
        self.engine.band = not self.desk      # a desk's window shows no hints band, as it never did
        if self.fill_owed:
            self.fill_owed = False
            self.engine.run(fill, self, action="fill")
            ui.commit(self.engine)
        g = self.game
        if g is None:
            super().draw(dt)
            return
        cv = self._surf.canvas()
        th = self._theme.colors()
        content = self.content_rect(cv)
        ground_round(cv, content, th["panel"])
        self._ui.begin(cv, th, content, self.desk, self._surf.windowed())
        got = g.draw(cv, th, content, self.desk, dt)
        if got is not None:
            name = g.name
            self._close_game()
            self._focus = name
            # the answer came after the pass: the next frame shows the page and its toast
            self.toast = ((shown(name) + " is the background of " + got, "check") if got else
                          (self.copies.last_error or "Can't put it there", "warn")) + (
                _ticks_ms() + TOAST_MS,)
            self._damage.again()

    def content_rect(self, cv):
        fs = max(1, getattr(cv, "font_scale", 1))
        cs = max(fs, self._surf.chrome_scale() or fs)
        return content_of(cv.w, cv.h, 0 if self._surf.windowed() else bar_rows(cs))


def _named(text):
    s.name = text
