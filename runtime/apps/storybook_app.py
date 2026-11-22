# Map (grep -n a name to jump there):
#   story_list                  the stories a drawing can be put in (Paint's door)
#   add_picture_slide           a drawing as a story's new last slide, and its undo
#   StorybookLayout             the desk editor's rects
#   Frames                      slides drawn once into layers, kept by what they show
#   fill                        the page's states from the layer's fields
#   build                       the page: the stories' cards, a story's view, the dialogs
#   StorybookAppLayer           the app: the store, Present, the desk's editor
#   StorybookAppLayer._present  Present: the slide alone, its taps and transitions
"""Storybook -- the kids' slides app (docs/media/look_2026-10/APPS_RESTYLE.md,
Storybook): a story is slides of words, shapes and pictures, an app's own
document (runtime/apps/story_doc.py), not a cart. One renderer draws a slide at
any zoom (runtime/apps/story_render.py).

  STORIES   a card a story, its first slide: the handheld's at 1/8, the
            desk's at 1/4, New story first, Present and Open in the
            window's foot, M its card's menu (Rename, Duplicate, Delete,
            which asks).
  A STORY   on the handheld, a slide at 1/4 to look at, left and right step,
            P presents: a handheld shows stories and does not edit them, so
            the edit keys answer "Stories are edited on a desk". On the desk
            the sorter and the slide editor (runtime/apps/story_edit.py).
  PRESENT   the slide alone at the largest zoom the glass takes (1:1 on the
            desk's 1024 x 600 glass, 5/16 on the handheld's 320 x 240), its
            objects appearing on taps, Fade and Swipe between slides, its
            number for a second after each change.

The stories page, a story's view and the dialogs are a UI tree page (`build`,
on the console's engine); a slide is custom drawing, in a `ui.canvas`.

A story is the `stories` item `<name>` of the user files: `story.json` and
the pictures it uses. A story whose document does not read (another format,
an old story cart's deck) is not listed: it reads as absent.
"""

import ui as _v
import uitree as ui
import uitree_app
from layers import AppLayer
from layout_base import bar_rows, content_of, metric_class, window_foot, DESK
from moy_store_base import builtin_name
from ticks import _ticks_ms, _ticks_diff
import story_doc as D
import story_render as R

KIND = "stories"
DOC = "story.json"
TOAST_MS = 2000
NUMBER_MS = 1000
FADE_FRAMES = 6                 # each way, through black
SWIPE_FRAMES = 8
COMMIT_MS = 800                 # an edit is written this long after the last
PRESENT_ZOOMS = ((1, 1), (7, 8), (3, 4), (5, 8), (1, 2), (5, 16), (1, 4), (1, 8))
DESK_BUDGET = 8 << 20           # the pictures' pixels kept, desk and handheld
HAND_BUDGET = 384 << 10
EDIT_KEYS = (13, 10, 9, 127, 4, 26, 25, 3, 22, ord("["), ord("]"), ord("n"), ord("N"),
             ord("t"), ord("T"), ord("s"), ord("S"), ord("i"), ord("I"), ord("b"),
             ord("B"), ord("y"), ord("Y"), ord("m"), ord("M"), ord("r"), ord("R"),
             ord("g"), ord("G"))
NEW = "new"                     # the desk's New story card's row
EDITOR = ("deck", "slide", "pictures")     # the desk editor's pages (runtime/apps/story_edit.py)


def dot():
    return " · " if _v.has_symbols() else " - "


def zoom_fit(w, h):
    """The largest present zoom whose slide fits w x h: (num, den)."""
    for n, d in PRESENT_ZOOMS:
        if R.size(n, d)[0] <= w and R.size(n, d)[1] <= h:
            return (n, d)
    return PRESENT_ZOOMS[-1]


def zoom_word(n, d):
    words = {(1, 1): "1:1", (1, 2): "½", (1, 4): "¼", (1, 8): "⅛", (5, 8): "5/8",
             (5, 16): "5/16", (3, 4): "¾", (7, 8): "7/8"}
    w = words.get((n, d), "%d/%d" % (n, d))
    if not _v.has_symbols():
        w = {"½": "1/2", "¼": "1/4", "⅛": "1/8", "¾": "3/4"}.get(w, w)
    return w


# -- a drawing put in a story (Paint's and My Art's Put in a story) -------------------
#
# The one door another app takes into a story: the stories as cards, and a
# drawing added as a new last slide's background (story_doc.put_drawing),
# with its undo. Stories are user files: the files role reaches them.

def story_list(carts, files=None):
    """The stories a drawing can be put in, newest first: [{"title",
    "folder", "slides", "cover"}], `cover` None (the caller draws the
    Storybook's icon). `files` is the files role (`carts`, an older caller's
    first argument, is used where it is one)."""
    store = files if files is not None else carts
    if store is None or not hasattr(store, "list"):
        return []
    names, err = store.list(KIND)
    out = []
    for name in names or ():
        blob, err = store.load(KIND, name + "/" + DOC)
        doc = D.read(blob) if blob and err is None else None
        if doc is not None:
            out.append({"title": doc["title"] or "Untitled", "folder": name,
                        "slides": len(doc["slides"]), "cover": None})
    return out


def add_picture_slide(carts, files, story, name):
    """Drawing `name` (My Art's) as a new last slide of `story` (a row of
    `story_list`), its background: (title, slide number, undo), the number 0
    where it could not be added; `undo()` takes the slide out again while it
    is still the drawing's alone."""
    title = story["title"]
    i, pic, _t = D.put_drawing(files, story["folder"], name)
    if i is None:
        return (title, 0, None)

    def undo():
        return D.take_back(files, story["folder"], i, pic)
    return (title, i + 1, undo)


class StorybookLayout:
    """The desk editor's rects over the content rect: the window's tool
    row, body and foot (its full-screen arrangement where the window fills
    the glass), the sorter's grid and the slide editor's column, pasteboard
    and panel."""

    FOOT = 44
    ROW = 50

    def __init__(self, w, h, fs=1, windowed=False, cs=None):
        self.w = int(w)
        self.h = int(h)
        self.fs = fs = max(1, int(fs))
        self.cs = max(fs, int(cs)) if cs else fs
        self.windowed = bool(windowed)
        self.desk = metric_class() == DESK
        self.cx, self.cy, self.cw, self.ch = content_of(
            self.w, self.h, 0 if windowed else bar_rows(self.cs))
        content = (self.cx, self.cy, self.cw, self.ch)
        self.content = content
        self.full = self.desk and self.cw >= 1000 and self.ch >= 560
        if not self.desk:
            return
        under = window_foot() if self.windowed else 0
        self.foot, self.body = _v.cut_bottom(content, self.FOOT - under)
        x, y, w, h = content
        self.row = (x, y, w, self.ROW)
        self.row_rule = (x + 16, y + self.ROW, w - 32, 1)
        self.foot_rule = (x + 16, self.foot[1], w - 32, 1)
        self.cols = max(1, (w - 32 + 24) // (256 + 24))
        gw = self.cols * 256 + (self.cols - 1) * 24
        self.margin = max(16, (w - gw) // 2)
        self.deck_grid = (x, y + self.ROW + 1, w, self.foot[1] - y - self.ROW - 1)
        self._slide_rects()

    def _slide_rects(self):
        """The slide editor's: the slides column, the pasteboard and the
        slide on it, the style panel."""
        x, y, w, h = self.content
        top = y + (40 if self.full else self.ROW)
        bottom = self.foot[1]
        if self.full:
            self.edit_zoom = (5, 8)
            col_x, col_w = x + 8, 96
            pb = (x + 120, top + 8, 656, 500)
            self.row = (x, y, w, 40)
            self.row_rule = (x, y + 40, w, 1)
        else:
            self.edit_zoom = (1, 2)
            col_x, col_w = x + 12, 96
            pb = (x + 124, top + 8, 528, 384)
        sw, sh = R.size(self.edit_zoom[0], self.edit_zoom[1])
        bh = min(pb[3], bottom - 4 - pb[1])
        self.pasteboard = (pb[0], pb[1], pb[2], bh)
        self.slide = (pb[0] + (pb[2] - sw) // 2, pb[1] + max(8, (bh - sh) // 2), sw, sh)
        self.column = (col_x, top + 1, col_w, bottom - top - 2)
        self.column_rule = (col_x + col_w + 8, top + 1, 1, bottom - top - 2)
        px = pb[0] + pb[2] + 12
        self.panel = (px, top + 8, x + w - 16 - px, bottom - top - 16)


def cover(renderer, lay, slide, w, h, step=-1, edit=False):
    """`slide` drawn into layer `lay` covering its w x h: its own zoom, or a
    little more where the shapes differ, the overhang cut evenly."""
    if w * R.SH >= h * R.SW:
        num, den = w, R.SW
    else:
        num, den = h, R.SH
    sw, sh = R.size(num, den)
    renderer.draw(lay, slide, (w - sw) // 2, (h - sh) // 2, num, den, step, clip=(0, 0, w, h),
                  edit=edit)


class Frames:
    """Slides drawn once into layers and placed from them: kept by what
    they show (the story's generation, the slide, the size, the tap), at
    most `n`, the least recently placed going first."""

    def __init__(self, renderer, n):
        self.renderer = renderer
        self.n = n
        self._kept = {}
        self._order = []

    def get(self, cv, key, slide, w, h, step=-1, edit=False, renderer=None):
        lay = self._kept.get(key)
        if lay is not None:
            if self._order[-1] != key:
                self._order.remove(key)
                self._order.append(key)
            return lay
        while len(self._order) >= self.n:
            self._drop(self._order[0])
        lay = cv.new_layer(w, h)
        cover(renderer or self.renderer, lay, slide, w, h, step, edit)
        self._kept[key] = lay
        self._order.append(key)
        return lay

    def has(self, key):
        return key in self._kept

    def place(self, cv, key, slide, x, y, w, h, clip=None, step=-1, edit=False,
              renderer=None):
        """The slide drawn into w x h at (x, y) of `cv`, inside `clip`."""
        lay = self.get(cv, key, slide, w, h, step, edit, renderer)
        cx, cy, cw, ch = clip if clip is not None else (x, y, w, h)
        x0, y0 = max(x, cx), max(y, cy)
        x1, y1 = min(x + w, cx + cw), min(y + h, cy + ch)
        if x1 > x0 and y1 > y0:
            cv.blit_strip_rect(lay, x, y, x0, y0, x1 - x0, y1 - y0)

    def _drop(self, key):
        lay = self._kept.pop(key)
        self._order.remove(key)
        lay.release()

    def drop(self, prefix=None):
        """Forget the frames (those whose key starts with `prefix`)."""
        for key in list(self._order):
            if prefix is None or key[0] == prefix:
                self._drop(key)


# -- the page ------------------------------------------------------------------------

s = ui.state(
    page=ui.enum("stories", "view", "editor", init="stories"),
    stories=ui.model(key="id", id="", title="", sub="", icon="", tone="", pic=ui.IMAGE),
    cur=ui.row_of("stories"),
    count="",                   # "3 stories", over the cards
    none=False,                 # no story on a handheld
    status="",                  # the desk foot's words: the focused story's
    picked=False,               # a story is focused: Present and Open act on it
    menu=False,                 # the focused story's menu
    menu_title="",
    deleting=False,             # Delete's dialog
    del_title="",
    renaming=False,             # Rename's dialog
    name="",
    toasting=False,
    toast="",
    toast_icon="check",
    band="",                    # the hints band's status words: a handheld's story view is View only
)
ui.app("Storybook", icon="storybook")


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


def _cover_of(lay, entry):
    """Story `entry`'s card picture: its first slide, drawn when the engine
    asks at the card's size, its pictures read for that and let go."""
    def render(w, h):
        cv = lay._surf.canvas()
        layer = cv.new_layer(w, h)
        rend = R.Renderer(R.Images(lay._load(entry["name"]), 4 * w * h))
        cover(rend, layer, entry["doc"]["slides"][0], w, h)
        rend.images.forget()
        return layer
    return render


def _pic_rows(lay):
    rows = []
    if lay.desk:
        rows.append({"id": NEW, "title": "New story", "sub": "", "icon": "new", "tone": "value",
                     "pic": None})
    covers = lay.covers
    for e in lay.stories:
        doc = e["doc"]
        name = e["name"]
        key = "story:" + name
        if covers.get(name) is not doc:
            covers[name] = doc
            ui.pictures.put(key, render=_cover_of(lay, e))
        k = len(doc["slides"])
        rows.append({"id": name, "title": doc["title"] or "Untitled",
                     "sub": "%d slide%s" % (k, "" if k == 1 else "s"),
                     "icon": "storybook", "tone": "", "pic": ui.image.own(key)})
    return rows


def fill(lay):
    """The page's states from the layer's fields: the stories' cards and
    the focused one, the page, the dialogs, the toast, a story's view."""
    _set(lay, "stories", _pic_rows(lay))
    n = len(lay.stories)
    _set(lay, "count", "%d stor%s" % (n, "y" if n == 1 else "ies"))
    _set(lay, "none", not n and not lay.desk)
    if lay.focus_to is not None:
        s.cur = lay.focus_to
        ui.focus(lay.focus_to + "/open")
        lay.focus_to = None
    entry = lay.entry(s.cur)
    title = (entry["doc"]["title"] or "Untitled") if entry is not None else ""
    _set(lay, "picked", entry is not None)
    if entry is not None:
        k = len(entry["doc"]["slides"])
        _set(lay, "status", title + dot() + "%d slide%s" % (k, "" if k == 1 else "s"))
    else:
        _set(lay, "status", "")
    page = "view" if lay.page == "view" else "editor" if lay.page in EDITOR else "stories"
    _set(lay, "page", page)
    _set(lay, "band", "View only" if page == "view" and not lay.desk else "")
    _set(lay, "menu", lay.menu == "story")
    _set(lay, "menu_title", title)
    _set(lay, "deleting", lay.asking == "delete")
    _set(lay, "del_title", title or "this story")
    _set(lay, "renaming", lay.asking == "rename")
    t = lay.toast
    _set(lay, "toasting", t is not None)
    if t is not None:
        _set(lay, "toast", t[0])
        _set(lay, "toast_icon", t[1])


def opened():
    fill(_lay())


def moved(row):
    _lay()


def open_card(row):
    """A card taken: New story makes one; a story opens, the handheld's to
    look at, the desk's in its sorter."""
    lay = _lay()
    if row.id == NEW:
        lay._new_story()
        return
    entry = lay.entry(row.id)
    if entry is None:
        return
    lay._open_story(entry, "deck" if lay.desk else "view")
    if lay.ed is not None:
        lay.ed.opened()


def present():
    """P: the focused story presented from its first slide; a story's
    view from the slide in view."""
    lay = _lay()
    if lay.page == "view":
        lay._start(lay.cur)
        return
    entry = lay.entry(s.cur)
    if entry is not None:
        lay._open_story(entry, "view" if not lay.desk else "deck")
        lay._start(0)


def open_story():
    lay = _lay()
    entry = lay.entry(s.cur)
    if entry is not None:
        lay._open_story(entry, "deck")
        if lay.ed is not None:
            lay.ed.opened()


def prev():
    _lay()._step_view(-1)


def next_():
    _lay()._step_view(1)


def close_menu():
    _lay().menu = None


def rename_ask():
    lay = _lay()
    lay.menu = None
    entry = lay.entry(s.cur)
    lay._menu_story = entry
    if entry is not None:
        s.name = entry["doc"]["title"]
        lay.asking = "rename"


def duplicate():
    lay = _lay()
    lay.menu = None
    entry = lay.entry(s.cur)
    if entry is not None:
        lay._duplicate_story(entry)


def delete_ask():
    lay = _lay()
    lay.menu = None
    entry = lay.entry(s.cur)
    lay._menu_story = entry
    if entry is not None:
        lay.asking = "delete"


def cancel():
    _lay().asking = None


def delete():
    lay = _lay()
    lay.asking = None
    entry = lay._menu_story
    if entry is not None and entry in lay.stories:
        lay._delete_story(entry)


def rename():
    _lay()._rename_done()


ui.hook("opened", opened)
ui.hook("moved", moved, takes="row")
ui.action("open", "Open", open_card, takes="row")
ui.action("prev", "Previous slide", prev, keys=("role:left",), hint="Slides",
          when="page=view", off="hide")
ui.action("next", "Next slide", next_, keys=("role:right",), hint="Slides",
          when="page=view", off="hide")
ui.action("present", "Present", present, keys=("p",), when="picked || page=view", off="grey")
ui.action("open_story", "Open", open_story, when="picked", off="grey")
ui.action("close_menu", "Close", close_menu)
ui.action("rename_ask", "Rename…", rename_ask)
ui.action("duplicate", "Duplicate\tCtrl+D", duplicate)
ui.action("delete_ask", "Delete\tDel", delete_ask)
ui.action("cancel", "Cancel", cancel)
ui.action("delete", "Delete", delete)
ui.action("rename", "Rename", rename)


def draw_view(cv, x, y, w, h):
    """A story's view: its slide at a quarter on its shadow in an edge, the
    slide's number between the arrows that step it (dim at either end), and
    where stories are edited."""
    lay = _LAYER[0]
    st = lay.story if lay is not None else None
    _VIEW_W[0] = w
    if st is None:
        return
    fs = max(1, int(getattr(cv, "font_scale", 1)))
    th = ui.colors()
    sw, sh = R.size(fs, 4)
    sx, sy = x + (w - sw) // 2, y + 4 * fs
    cv.shadow(sx, sy, sw, sh, 0, 1, 40, 6 * fs, 0, 2 * fs, (sx, sy, sw, sh, 0))
    lay.frames.place(cv, ("view", st.gen, lay.cur, sw, sh), st.slides[lay.cur], sx, sy, sw, sh)
    cv.rectb(sx - 1, sy - 1, sw + 2, sh + 2, th["edge"])
    n = len(st.slides)
    word = "%d / %d" % (lay.cur + 1, n)
    ty = sy + sh + 4 * fs
    tw = _v.text_size(word)[0]
    mid = x + w // 2
    for k, ax in ((0, mid - tw // 2 - 36 * fs), (1, mid + tw // 2 + 12 * fs)):
        _v.at(ax, ty, 24 * fs, 16 * fs)
        _v.icon("back" if k == 0 else "forward")
        _v.label("", _DIM if (k == 0 and lay.cur == 0) or (k == 1 and lay.cur >= n - 1) else None)
    _v.at(mid - tw // 2 - 4 * fs, ty, tw + 8 * fs, 16 * fs)
    _v.label(word, _CENTRE)
    _v.at(x, ty + 16 * fs, w, 14 * fs)
    _v.label(NOTE, _DIM_CENTRE)


def view_at(ev):
    """A press on the stepper's line: the half it lands in steps."""
    lay = _lay()
    fs = lay.layout.fs
    top = 4 * fs + R.size(fs, 4)[1] + 4 * fs
    if ev.kind == "down" and top <= ev.y < top + 16 * fs and lay.story is not None:
        lay._step_view(-1 if ev.x < _VIEW_W[0] // 2 else 1)


_DIM = {"tone": "dim"}
_CENTRE = {"align": "center"}
_DIM_CENTRE = {"tone": "dim", "align": "center"}
NOTE = "Edit stories on a desk board or the web"
_VIEW_W = [0]                   # the view canvas's width, as last drawn
ui.hook("view_at", view_at, takes="pointer")
_LAYER = [None]                 # the layer whose story the view's canvas draws


def _stories():
    ui.label("{count}", tone="dim", face="caption", shown="!none")
    with ui.cards("stories", cur="cur", changed="moved", w="{@desk?256:128}",
                  h="{@desk?150:75}", shown="!none"):
        ui.card("open", label="{.title}", sub="{.sub}", icon="{.icon}", tone="{.tone}",
                image=".pic")
    ui.empty("No stories yet", icon="storybook", shown="none",
             lines=["Stories are made on a desk board", "or in the web build."])
    with ui.foot(shown="@desk"):
        ui.label("{status}", tone="dim", face="caption")
        ui.button("present", icon="play")
        ui.button("open_story", "primary", icon="folder_open")


def _view():
    ui.canvas("view", draw_view, h=190, pointer="view_at", ground="panel")


def _editor():
    pass


def build():
    with ui.page("", status="{band}"):
        ui.switch("page", {"stories": _stories, "view": _view, "editor": _editor})
        with ui.popover("story_menu", anchor="stories.cur", shown="menu", close="close_menu",
                        w="{@desk?260:180}", wash="page"):
            with ui.menu("{menu_title}"):
                ui.item("rename_ask", icon="pencil")
                ui.item("duplicate", icon="dup")
                ui.item("delete_ask", icon="trash", mkind="danger")
        with ui.dialog("Delete {del_title}?", ["cancel", "delete"], kind="danger",
                       shown="deleting"):
            ui.label("Its slides and pictures go to the Trash.", wrap="word", lines=3)
        with ui.dialog("Rename the story", ["cancel", "rename"], kind="primary",
                       shown="renaming"):
            ui.field("Name", "name", D.MAX_TITLE, hint="my story", on="rename")
        ui.toast("{toast}", icon="{toast_icon}", shown="toasting")


def is_app(cart):
    """The shipped Storybook identity cart: its title, its marker
    permission, its folder."""
    if (not cart or cart.get("title") != "Storybook"
            or "storybook" not in (cart.get("permissions") or ())):
        return False
    path = cart.get("path")
    if not path:
        return int(cart.get("version", 0)) >= 1
    return builtin_name(path) == "moybyte.storybook.moy"


class StorybookAppLayer(uitree_app.app_layer("storybook", "Storybook", build, is_app,
                                             needs=("files", "nav"))):
    """The Storybook Layer: the page's engine handed this layer as what its
    handlers reach (`uitree_app.env()`), the stories in the store, Present
    on the whole glass and the desk's editor (runtime/apps/story_edit.py),
    which draws its pages itself."""

    APP_TITLE = "Storybook"
    APP_FOLDER = "moybyte.storybook.moy"
    domain = "system"

    def __init__(self, ctx, names=None):
        super().__init__(ctx, names)
        self.engine.env = self
        self._files = ctx.files
        self._nav = ctx.nav
        self._ui = ctx.ui
        self.names = names
        cv = self._surf.canvas()
        self.layout = StorybookLayout(cv.w, cv.h, self._surf.font_scale(),
                                      self._surf.windowed(), self._surf.chrome_scale())
        self.desk = self.layout.desk
        self.engine.band = not self.desk      # a desk's window shows no hints band
        self.page = "stories"
        self.stories = []             # [{"name", "doc"}], newest first
        self.story = None             # the open story (story_doc.Story)
        self.cur = 0                  # the slide in view
        self.images = None
        self.renderer = None
        self.frames = None
        self.toast = None             # (text, icon, until ms)
        self.asking = None            # "delete", "rename": a dialog up
        self.menu = None              # "story": the focused story's menu
        self.glass = False            # presenting: the app holds the whole glass
        self.show = None              # Present's state
        self.ed = None                # the desk's editor (runtime/apps/story_edit.py)
        self.shown = {}               # each state as fill last wrote it
        self.covers = {}              # story name -> the document its card's picture shows
        self.fill_owed = True
        self.focus_to = None          # the story whose card focus moves to at the next fill
        self._focus = None            # the editor's: the id focus moves to on its next frame
        self._focused = None
        self._edited_at = None
        self._menu_story = None
        self._whole = (0, 0, 0, 0)    # the editor's page rect, the canvas's
        self._was = [None] * 6        # page, asking, menu, story, slide, stories: what the last fill saw
        _LAYER[0] = self

    # -- the page's state --------------------------------------------------------------

    def state(self):
        self.engine._bind()
        return s

    def do(self, fn, *args):
        """`fn(*args)` run as the page's handler, then the page filled, one
        commit."""
        self.engine.run(fn, *args, action="console")
        self.engine.run(fill, self, action="fill")
        ui.commit(self.engine)
        self._damage.all()

    def owe(self):
        """The layer's fields moved outside a handler: the next frame fills."""
        self.fill_owed = True
        self._damage.all()

    @property
    def typed(self):
        """Rename's field, as typed."""
        return self.state().name

    @typed.setter
    def typed(self, v):
        self.engine.run(setattr, s, "name", v, action="console")
        ui.commit(self.engine)

    def entry(self, name):
        for e in self.stories:
            if e["name"] == name:
                return e
        return None

    def focus_story(self, name):
        self.focus_to = name
        self.owe()

    def story_menu(self, entry):
        self.focus_to = entry["name"]
        self.menu = "story"
        self.owe()

    def ask(self, what, entry):
        self.focus_to = entry["name"]
        self._menu_story = entry
        if what == "rename":
            self.typed = entry["doc"]["title"]
        self.asking = what
        self.owe()

    def close_dialogs(self):
        self.asking = None
        self.menu = None
        self.owe()

    # -- the app protocol (docs/app_api_v1.md) --------------------------------

    def open(self):
        self.page = "stories"
        self.asking = None
        self.menu = None
        self.show = None
        self.glass = False
        self.toast = None
        self._scan()
        if self.desk and self.ed is None:
            from story_edit import Editor
            self.ed = Editor(self)
        self.focus_to = self.stories[0]["name"] if self.stories else (NEW if self.desk else None)
        self.fill_owed = True
        super().open()

    def relayout(self, w, h, fs, cs=None):
        super().relayout(w, h, fs, cs)
        self.layout = StorybookLayout(w, h, fs, self._surf.windowed(), cs)
        if self.ed is not None:
            self.ed.relayout()

    def close(self):
        """Leaving, by any route: the open story is written, the pictures and
        frames given back."""
        self.commit()
        self._stop_writing()
        self.glass = False
        self.show = None
        if self.frames is not None:
            self.frames.drop()
        if self.images is not None:
            self.images.forget()
        self.forget_covers()
        super().close()

    def forget_covers(self, name=None):
        """The cards' pictures let go (story `name`'s): drawn again when a
        card next shows one."""
        for n in list(self.covers):
            if name is None or n == name:
                del self.covers[n]
                ui.pictures.drop("story:" + n)
                if self.engine.pics is not None:
                    self.engine.pics.forget_own("story:" + n)
        self.fill_owed = True

    def commit(self):
        """Write the open story now (an exit path, docs/app_api_v1.md)."""
        st = self.story
        if st is None or not st.dirty:
            return
        st.dirty = False
        self._edited_at = None
        _v, err = self._files.save(KIND, st.name + "/" + DOC, D.write(st.doc))
        if err is not None:
            st.dirty = True
            self._say("This story can't be saved here", "warn")
        for e in self.stories:
            if e["name"] == st.name:
                e["doc"] = st.doc

    def page_title(self):
        """The bar's title (the window's on the desk): the open story's name,
        or the page of it that is open."""
        if self.page == "pictures":
            return "Add a picture"
        if self.story is not None and self.page != "stories":
            return self.story.title() or "Untitled"
        return None

    def typing(self):
        """A field in focus types (Rename's), and so do a slide's words
        while the desk's editor writes them."""
        ed = self.ed
        if ed is not None and self.page in EDITOR:
            return ed.writing or AppLayer.typing(self)
        return self.asking == "rename"

    def has_page(self):
        return self.page != "stories" or self.asking is not None or self.menu is not None \
            or self.show is not None

    def back(self):
        """Back one level: Present stops, a dialog or a menu closes, the
        editor's pages step back to the sorter and the stories."""
        if self.show is not None:
            self._stop()
            return True
        if self.asking is not None or self.menu is not None:
            self.close_dialogs()
            return True
        if self.ed is not None and self.page in EDITOR and self.ed.back():
            return True
        if self.page == "stories":
            return False
        self._to_stories()
        return True

    # -- the store -------------------------------------------------------------------

    def _scan(self):
        """The stories in the store, newest first, each document read
        strictly: one that does not read is not listed."""
        names, err = self._files.list(KIND)
        out = []
        for name in names or ():
            blob, err = self._files.load(KIND, name + "/" + DOC)
            doc = D.read(blob) if blob else None
            if doc is not None:
                out.append({"name": name, "doc": doc})
        self.stories = out
        self.fill_owed = True

    def _load(self, name):
        """A picture of story `name`'s, its blob or None."""
        def load(image):
            blob, err = self._files.load(KIND, name + "/" + image + ".moyimg")
            return blob if err is None else None
        return load

    def _open_story(self, entry, page):
        if self.story is not None and self.story.name != entry["name"]:
            self.commit()
        if self.story is None or self.story.name != entry["name"]:
            self.story = D.Story(entry["name"], D.copy(entry["doc"]))
            budget = DESK_BUDGET if self.desk else HAND_BUDGET
            if self.images is not None:
                self.images.forget()
            self.images = R.Images(self._load(entry["name"]), budget)
            self.renderer = R.Renderer(self.images)
            if self.frames is not None:
                self.frames.drop()
            self.frames = Frames(self.renderer, 24 if self.desk else 4)
        self.cur = 0
        self.page = page
        self.owe()

    def _to_stories(self):
        self.commit()
        name = self.story.name if self.story is not None else None
        self._stop_writing()
        self.page = "stories"
        self._scan()
        if name is not None:
            self.focus_to = name
        self.owe()

    def edited(self):
        """An edit happened: write it once the edits pause."""
        self._edited_at = _ticks_ms()
        self._damage.all()

    def _stop_writing(self):
        if self.ed is not None:
            self.ed.stop_writing()

    # -- the stories' verbs (desk) ------------------------------------------------------

    def _new_story(self):
        """A new story: one Title slide, open in the editor with its title
        to be written. It is named from its title when it is first written."""
        name, err = self._files.new_name(KIND)
        if err is not None or not name:
            self._say("No room for a new story here", "warn")
            return
        doc = D.new_doc("")
        entry = {"name": name, "doc": doc}
        _v, err = self._files.save(KIND, name + "/" + DOC, D.write(doc))
        if err is not None:
            self._say("This story can't be saved here", "warn")
            return
        self.stories.insert(0, entry)
        self._open_story(entry, "slide")
        if self.ed is not None:
            self.ed.opened(new=True)

    def _duplicate_story(self, entry):
        name, err = self._files.duplicate(KIND, entry["name"])
        if err is not None:
            self._say("This story can't be copied here", "warn")
            return
        self._scan()
        for e in self.stories:
            if e["name"] == name:
                e["doc"]["title"] = (entry["doc"]["title"] + " 2")[:D.MAX_TITLE]
                self._files.save(KIND, name + "/" + DOC, D.write(e["doc"]))
        self.focus_to = name
        self._say("Duplicated", "dup")

    def _delete_story(self, entry):
        _v, err = self._files.delete(KIND, entry["name"])
        if err is not None:
            self._say("This story can't be deleted here", "warn")
            return
        if self.story is not None and self.story.name == entry["name"]:
            self.story = None
        i = self.stories.index(entry)
        self.stories.pop(i)
        if self.stories:
            self.focus_to = self.stories[min(i, len(self.stories) - 1)]["name"]
        else:
            self.focus_to = NEW
        self._say("Moved to the Trash", "trash")

    def _rename_done(self):
        entry = self._menu_story
        t = self.typed.strip()
        self.asking = None
        self.owe()
        if entry is None or not t:
            return
        doc = entry["doc"]
        doc["title"] = t[:D.MAX_TITLE]
        self._files.save(KIND, entry["name"] + "/" + DOC, D.write(doc))
        if self.story is not None and self.story.name == entry["name"]:
            self.story.doc["title"] = doc["title"]

    # -- messages ---------------------------------------------------------------------

    def _say(self, text, icon="check"):
        self.toast = (text, icon, _ticks_ms() + TOAST_MS)
        self.owe()

    # -- input ------------------------------------------------------------------------

    def handle_input(self, inp):
        k = getattr(inp, "typed", 0)
        if self.toast is not None and (k or inp.pressed("a") or inp.pressed("b")):
            self.toast = None
            self.owe()
        if self.show is not None:
            self._present_keys(inp, k)
            return True
        if self.page in EDITOR and self.ed is not None and self.menu is None \
                and self.asking is None:
            return self.ed.handle_input(inp, k)
        if self.asking is None and self.menu is None:
            if self.page == "view" and k in (44, 46):           # , .
                self._step_view(-1 if k == 44 else 1)
                return True
            if self.page == "view" and (inp.pressed("a") or k in EDIT_KEYS):
                self._say("Stories are edited on a desk", "warn")
                return True
            if self.page == "stories" and self.desk and self._desk_keys(k):
                return True
        return self.engine.keys(inp)

    def _desk_keys(self, k):
        """The desk's stories keys: N a new story, M the focused story's
        menu, Ctrl+D a copy, Del asks to delete it."""
        if k == 110 or k == 78:                                 # n, N
            self.do(self._new_story)
            return True
        entry = self.entry(self.state().cur)
        if entry is None:
            return False
        if k == 109 or k == 77:                                 # m, M
            self.menu = "story"
        elif k == 4:
            self._duplicate_story(entry)
        elif k == 127:
            self._menu_story = entry
            self.asking = "delete"
        else:
            return False
        self.owe()
        return True

    def _step_view(self, d):
        j = max(0, min(len(self.story.slides) - 1, self.cur + d))
        if j != self.cur:
            self.cur = j
            self.owe()

    def handle_pointer(self, px, py, click):
        down = bool(getattr(self._surf.pointer(), "down", False))
        if self.show is not None:
            self._present_pointer(px, py, click, down)
            return True
        if self.page in EDITOR and self.ed is not None:
            if self.ed.handle_pointer(px, py, click, down):
                return True
            if self._ui.point(px, py, click, down):
                self._damage.all()
            return True
        return self.engine.point(px, py, click)

    # -- the frame --------------------------------------------------------------------

    def draw(self, dt):
        if self.toast is not None:
            if _ticks_diff(_ticks_ms(), self.toast[2]) >= 0:
                self.toast = None
                self.fill_owed = True
            else:
                self._damage.again()
        if self._edited_at is not None:
            if _ticks_diff(_ticks_ms(), self._edited_at) >= COMMIT_MS:
                self.commit()
            else:
                self._damage.again()
        if self.show is not None:
            self._present(self._surf.canvas())
            return
        if self.page in EDITOR and self.ed is not None:
            self._editor_frame(self._surf.canvas())
            return
        w = self._was
        if (w[0] is not self.page or w[1] is not self.asking or w[2] is not self.menu
                or w[3] is not self.story or w[4] != self.cur or w[5] != len(self.stories)):
            w[0], w[1], w[2], w[3], w[4], w[5] = (self.page, self.asking, self.menu, self.story,
                                                  self.cur, len(self.stories))
            self.fill_owed = True
        if self.fill_owed:
            self.fill_owed = False
            self.engine.run(fill, self, action="fill")
            ui.commit(self.engine)
        super().draw(dt)
        if self.page == "view" and self.story is not None:
            if _v.bar(self.story.title() or "Untitled", ("play",), (), True) == 0:
                self._start(self.cur)

    def _editor_frame(self, cv):
        """The desk editor's page (runtime/apps/story_edit.py), on the
        verbs: its own pass over the canvas, its menus and a toast."""
        th = self._theme.colors()
        whole = self._whole
        if whole[2] != cv.w or whole[3] != cv.h:
            whole = self._whole = (0, 0, cv.w, cv.h)
        self._ui.begin(cv, th, whole, True, self.layout.windowed,
                       elsewhere=self.ed.keys_elsewhere())
        _v.page("")
        if self._focus is not None:
            _v.focus(self._focus)
            self._focus = None
        page = self.page
        self.ed.draw(cv, th)
        _v.bar(self.page_title() or "", (), (), True)
        if self.toast is not None:
            lay = self.layout
            _v.at(lay.content[0], lay.content[1], lay.content[2],
                  lay.foot[1] - lay.content[1] - 12)
            _v.toast(self.toast[0], self.toast[1])
        f = _v.focus()
        if f != "Present":
            self._focused = f
        if self.page != page or self.show is not None:
            self._ui.again()
            self.fill_owed = True

    # -- Present ------------------------------------------------------------------------

    def _start(self, i):
        """Present from slide `i`: the slide alone on the whole glass."""
        if self.story is None:
            return
        self._stop_writing()
        self.commit()
        self.show = {"i": i, "step": 0, "from": None, "t": 0, "kind": "none",
                     "shown": _ticks_ms(), "was": self.page, "down": None}
        self.glass = True
        self._damage.all()

    def _stop(self):
        sh = self.show
        self.show = None
        self.glass = False
        if sh is not None:
            self.cur = sh["i"]
            if self.ed is not None:
                self.ed.presented(sh["i"])
        if self.frames is not None:
            self.frames.drop("show")
        self.owe()

    def _last_step(self, i):
        m = 0
        for o in self.story.slides[i]["objects"]:
            if o["step"] > m:
                m = o["step"]
        return m

    def _next(self):
        sh = self.show
        if sh["from"] is not None:
            return
        if sh["step"] < self._last_step(sh["i"]):
            sh["step"] += 1
            self._damage.all()
            return
        if sh["i"] + 1 >= len(self.story.slides):
            return
        self._go(sh["i"] + 1, 0)

    def _prev(self):
        sh = self.show
        if sh["from"] is not None or sh["i"] == 0:
            return
        self._go(sh["i"] - 1, self._last_step(sh["i"] - 1), back=True)

    def _go(self, j, step, back=False):
        sh = self.show
        kind = self.story.slides[j if not back else sh["i"]]["transition"]
        sh["from"] = (sh["i"], sh["step"]) if kind != "none" else None
        sh["kind"] = kind
        sh["back"] = back
        sh["t"] = 0
        sh["i"] = j
        sh["step"] = step
        sh["shown"] = _ticks_ms()
        self._damage.all()

    def _present_keys(self, inp, k):
        if inp.pressed("b") or k == 27:
            self._stop()
        elif inp.steps("right") or inp.pressed("a") or k in (13, 10, 32):
            self._next()
        elif inp.steps("left"):
            self._prev()

    def _present_pointer(self, px, py, click, down):
        sh = self.show
        if click:
            sh["down"] = (px, py)
            return
        if sh["down"] is not None and not down:
            x0, y0 = sh["down"]
            sh["down"] = None
            dx = px - x0
            if dx > 40:
                self._prev()
            else:
                self._next()

    def _present(self, cv):
        """The slide alone on the glass at the zoom it fits, on black: a
        transition's frames, then its number for a while."""
        sh = self.show
        w, h = cv.w, cv.h
        n, d = zoom_fit(w, h)
        sw, sp = R.size(n, d)
        x, y = (w - sw) // 2, (h - sp) // 2
        cv.rect(0, 0, w, h, 0)
        clip = (x, y, sw, sp)
        frm = sh["from"]
        if frm is not None:
            sh["t"] += 1
            t = sh["t"]
            if sh["kind"] == "fade":
                total = 2 * FADE_FRAMES
                if t < FADE_FRAMES:
                    self._show_slide(cv, frm[0], frm[1], x, y, sw, sp, clip)
                    a = 255 * t // FADE_FRAMES
                else:
                    self._show_slide(cv, sh["i"], sh["step"], x, y, sw, sp, clip)
                    a = 255 * max(0, total - t) // FADE_FRAMES
                cv.shadow(x, y, sw, sp, 0, 0, min(255, a), 0)
            else:
                total = SWIPE_FRAMES
                off = sw * t // total
                if sh.get("back"):
                    self._show_slide(cv, frm[0], frm[1], x + off, y, sw, sp, clip)
                    self._show_slide(cv, sh["i"], sh["step"], x + off - sw, y, sw, sp, clip)
                else:
                    self._show_slide(cv, frm[0], frm[1], x - off, y, sw, sp, clip)
                    self._show_slide(cv, sh["i"], sh["step"], x - off + sw, y, sw, sp, clip)
            if t >= total:
                sh["from"] = None
                sh["shown"] = _ticks_ms()
            self._damage.again()
        else:
            self._show_slide(cv, sh["i"], sh["step"], x, y, sw, sp, clip)
        if _ticks_diff(_ticks_ms(), sh["shown"]) < NUMBER_MS or frm is not None:
            self._number(cv, x, y, sw, sp)
            self._damage.again()

    def _show_slide(self, cv, i, step, x, y, w, h, clip):
        key = ("show", self.story.gen, i, step, w, h)
        self.frames.place(cv, key, self.story.slides[i], x, y, w, h, clip,
                          step=step)

    def _number(self, cv, x, y, sw, sh):
        """The slide's number: in the black under the slide where there is
        room, else in a half-black pill on its corner."""
        word = "%d / %d" % (self.show["i"] + 1, len(self.story.slides))
        fs = self.layout.fs
        below = cv.h - (y + sh)
        size = 13 * fs if not self.desk else 15
        tw = cv.face_width(1, size * 64, word) // 64
        if below >= size + 4:
            base = y + sh + (below + size * 7 // 10) // 2
            cv.face_text(1, size * 64, (x + sw - tw - 8 * fs) * 64, base * 64, word, 13)
            return
        pw, ph = tw + 20, size + 14
        px, py = x + sw - pw - 16, y + sh - ph - 16
        cv.shadow(px, py, pw, ph, ph // 2, 0, 128, 0)
        cv.face_text(1, size * 64, (px + 10) * 64, (py + 7 + size * 7 // 10) * 64, word, 7)
