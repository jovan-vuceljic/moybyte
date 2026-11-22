# Map (grep -n a name to jump there):
#   shown                         a drawing's file name in words
#   game_page / story_page        the two pages: a caption, then the projects or the stories
#   SendPage                      a page over a drawing, as the app that opens it hosts it
#   GamePage                      Put in a game: the projects as a table
#   StoryPage                     Put in a story: the stories as cards
"""The pages a drawing is sent from: Put in a game and Put in a story, which
Paint and My Art both open over a drawing (docs/media/look_2026-10/
APPS_RESTYLE.md), `uitree` pages each app hosts in its frame
(`uitree_app.hosted_page`). A page answers the frame after its row or card
is chosen (`SendPage.draw`)."""

import ui as _v
import uitree as ui
import uitree_app

try:
    import storybook_app as _stories
except ImportError:
    _stories = None


def dot():
    return " · " if _v.has_symbols() else " - "


def dots():
    return "…" if _v.has_symbols() else "..."


def shown(name):
    """A drawing's file name as the pages say it: in words, its first letter up."""
    words = str(name or "").replace("_", " ")
    return words[:1].upper() + words[1:]


def stories_here():
    """Whether this build carries the Storybook a drawing can go into."""
    return _stories is not None and hasattr(_stories, "add_picture_slide")


# -- the pages ------------------------------------------------------------------------

s = ui.state(
    caption="",                 # what happens to the drawing
    games=ui.model(key="id", id="", title=""),
    game=ui.row_of("games"),
    stories=ui.model(key="id", id="", title="", sub=""),
    story=ui.row_of("stories"),
    none=False,                 # no story to put it in
)


def opened():
    uitree_app.env().fill()


def put(row):
    uitree_app.env().chose(int(row.id))


def draw_game(cv, x, y, w, h, row):
    """A project's row: its cover (its initial on a tile where it has none)
    and its title."""
    uitree_app.env().draw_game(cv, x, y, w, h, int(row.id))


def game_keys(i, row):
    """Enter on a project's row puts the drawing there."""
    if i.pressed("a"):
        uitree_app.env().chose(int(row.id))
        return True
    return False


def game_moved(row):
    """Focus moved to a project's row: its mark follows."""
    uitree_app.env().at = int(row.id) if row is not None else -1


def game_at(ev):
    """A tap on a project's row puts the drawing there."""
    if ev.kind == "up" and ev.row is not None:
        uitree_app.env().chose(int(ev.row.id))


ui.hook("opened", opened)
ui.hook("game_at", game_at, takes="pointer")
ui.hook("game_moved", game_moved, takes="row")
ui.hook("put", put, takes="row")
ui.action("put_story", "Add", put, takes="row")


def game_page():
    with ui.page(""):
        with ui.row("caption", pad=16):
            ui.label("{caption}", tone="dim", face="caption")
        with ui.scroll("games_view"):
            with ui.group("", look="card"):
                with ui.rows("games", cur="game", changed="game_moved",
                             empty="No games yet: make one in Projects"):
                    ui.canvas("game", draw_game, h="{@desk?28:20}", keys=game_keys,
                              pointer="game_at", hint="Add", mark=False, ground="surface")


def story_page():
    with ui.page(""):
        with ui.row("caption", pad=16):
            ui.label("{caption}", tone="dim", face="caption")
        with ui.cards("stories", cur="story", w="{@desk?256:128}", h="{@desk?150:75}",
                      shown="!none"):
            ui.card("put_story", label="{.title}", sub="{.sub}", icon="storybook")
        ui.label("No stories yet: make one in Storybook", tone="dim", shown="none")


class SendPage:
    """A page over drawing `name`, hosted by the app that opens it: drawn in
    the app's frame (its host begun), keyed and pointed through it. `draw`
    answers the frame after the drawing went somewhere, else None."""

    BUILD = None

    def __init__(self, host, damage, name):
        self.name = name
        self.got = None
        self.page = uitree_app.hosted_page(self.BUILD[0], host, damage, env=self)
        self.page.open()

    def fill(self):
        s.caption = shown(self.name) + self.WORDS + dots()

    def draw(self, cv, th, rect, desk, dt):
        self.page.band = not desk         # a desk's window shows no hints band
        self.page.paint(dt, cv, th, rect, desk)
        got, self.got = self.got, None
        return got

    def keys(self, i):
        return self.page.keys(i)

    def point(self, px, py, click):
        return self.page.point(px, py, click)

    def close(self):
        self.page.close()


class GamePage(SendPage):
    """Put in a game: the projects as a table, each its cover; Enter adds
    the drawing as the project's background (`PictureCopies.attach`). Its
    answer is the title of the project the drawing went into; "" where the
    copy failed (`copies.last_error`)."""

    BUILD = (game_page,)
    WORDS = " becomes the background of"

    def __init__(self, copies, nav, name, host, damage):
        self.copies = copies
        self.nav = nav
        self.carts = copies.target_carts()
        self.at = 0                   # the row focus is on
        SendPage.__init__(self, host, damage, name)

    def fill(self):
        SendPage.fill(self)
        s.games = [{"id": str(i), "title": c.get("title") or ""} for i, c in enumerate(self.carts)]

    def chose(self, i):
        if 0 <= i < len(self.carts):
            got = self.copies.attach(i, self.name)
            self.got = got if got else ""

    def draw_game(self, cv, x, y, w, h, i):
        if not 0 <= i < len(self.carts):
            return
        cart = self.carts[i]
        fs = max(1, int(getattr(cv, "font_scale", 1)))
        th = ui.colors()
        if i + 1 < len(self.carts):
            cv.rect(x + 8 * fs, y + h - 1, w - 16 * fs, 1, th["border"])
        if i == self.at:
            cv.rect(x + 2 * fs, y + 3 * fs, 3 * fs, h - 6 * fs, th["focus"])
        side = 16 * fs
        px, py = x + 8 * fs, y + (h - side) // 2
        cover = self.nav.cover(cart)
        if cover:
            cv.cover(cover.pix, cover.w, 0, 0, cover.w, cover.h, px, py, side, side, side // 4, False)
        else:
            _v.initial((px, py, side, side), cart.get("title") or "", side // 4)
        tx = px + side           # the label keeps its own lead
        _v.at(tx, y, max(0, x + w - tx - 8 * fs), h)
        _v.label(cart.get("title") or "")


class StoryPage(SendPage):
    """Put in a story: the stories as cards; a card chosen adds the drawing
    to that story as a new last slide's picture (the Storybook's
    `add_picture_slide`). Its answer is (story title, slide, undo)."""

    BUILD = (story_page,)
    WORDS = " becomes a new last slide of"

    def __init__(self, carts, files, name, host, damage):
        self.carts = carts
        self.files = files
        self.stories = _stories.story_list(carts, files) if _stories is not None else []
        SendPage.__init__(self, host, damage, name)

    def fill(self):
        SendPage.fill(self)
        rows = []
        for i in range(len(self.stories)):
            st = self.stories[i]
            n = st["slides"]
            rows.append({"id": str(i), "title": st["title"],
                         "sub": "%d slide%s" % (n, "" if n == 1 else "s")})
        s.stories = rows
        s.none = not rows

    def chose(self, i):
        if _stories is not None and 0 <= i < len(self.stories):
            self.got = _stories.add_picture_slide(self.carts, self.files, self.stories[i], self.name)
