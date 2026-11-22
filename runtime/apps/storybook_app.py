# Map (grep -n a name to jump there):
#   story_list                  the stories a drawing can be put in (Paint's door)
#   add_picture_slide           a drawing as a story's new last slide, and its undo
#   StorybookLayout             the app's content rect
#   Frames                      slides drawn once into layers, kept by what they show
#   fill                        the page's states from the layer's fields
#   build                       the page: the stories' cards, a story's view, the dialogs
#   _deck                       the desk editor's sorter
#   _slide                      a slide: its tools, the column, the pasteboard, the panel
#   _pictures                   Add a picture
#   _fill_editor                the editor's states from the layer's fields
#   StorybookAppLayer           the app: the store, Present, the editor's keys
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

The stories page, a story's view, the dialogs and the desk's editor (the
sorter, a slide, Add a picture) are one UI tree page (`build`, on the
console's engine); a slide is custom drawing, in a `ui.canvas` (the view's,
the editor's pasteboard), and the cards' pictures are the app's own, drawn
when the engine asks.

A story is the `stories` item `<name>` of the user files: `story.json` and
the pictures it uses. A story whose document does not read (another format,
an old story cart's deck) is not listed: it reads as absent.
"""

import ui as _v
import uitree as ui
import uitree_app
from layers import AppLayer
from layout_base import bar_rows, content_of, metric_class, DESK
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
ADD = "add"                     # the sorter's New slide card's row
CARD = "/edit_slide"            # a sorter card's id after its row's (story_edit.card_id)
STRIPS = ("none",) + tuple("c%d" % i for i in range(16))     # a text's strip behind: none, a colour
POINTS = ("r", "l", "ur", "ul")                             # a line's way: right, left, up right, up left
SCALE_KEYS = ("s0", "s1", "s2", "s3", "s4")                 # a picture's size, story_doc.SCALES
EDITOR = ("deck", "slide", "pictures")     # the desk editor's pages (runtime/apps/story_edit.py)
BANDED = ("deck", "slide")                  # ...those whose desk window shows the hints band


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
    """The app's content rect (a window's whole buffer on the desk), and
    whether the console is a desk, where stories are edited."""

    def __init__(self, w, h, fs=1, windowed=False, cs=None):
        self.w = int(w)
        self.h = int(h)
        self.fs = fs = max(1, int(fs))
        self.cs = max(fs, int(cs)) if cs else fs
        self.windowed = bool(windowed)
        self.desk = metric_class() == DESK
        self.cx, self.cy, self.cw, self.ch = content_of(
            self.w, self.h, 0 if windowed else bar_rows(self.cs))
        self.content = (self.cx, self.cy, self.cw, self.ch)


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
    band="",                    # the hints band's status words: View only, the editor's status
    view="",                    # what the view's canvas shows: the story, its edit, the slide
    # the desk's editor (runtime/apps/story_edit.py): its page, its menus
    ed=ui.enum("deck", "slide", "pictures", init="deck"),
    ed_menu=ui.enum("none", "add", "layouts", "more", "slide", "colours", init="none"),
    slides=ui.model(key="id", id="", num="", trans="", icon="", tone="", pic=ui.IMAGE),
    dcur=ui.row_of("slides"),   # the sorter's focused card
    thumbs=ui.model(key="id", id="", num="", trans="", pic=ui.IMAGE),
    here="",                    # the slide being edited: the column's current card
    dslide=False,               # a slide's card is focused in the sorter
    can_undo=False,
    can_redo=False,
    has_obj=False,              # an object is chosen
    has_clip=False,             # one is copied
    can_prev=False,
    can_next=False,
    count_word="",              # "2/5", between the slide stepper's arrows
    board="",                   # what the pasteboard shows (Editor.board_view)
    lay0="", lay1="", lay2="", lay3="",          # the layouts menu's items
    more_title="",
    snap_word="",
    slide_title="",
    trans_word="",
    none_ok=False,              # the colours menu offers None
    colour_for=ui.enum("bg", "colour", "fill", "line", init="bg"),     # what it sets
    swatch_a=ui.model(key="id", id="", rgb=""),
    swatch_b=ui.model(key="id", id="", rgb=""),
    cur_a=ui.row_of("swatch_a"),
    cur_b=ui.row_of("swatch_b"),
    # the style panel: the chosen object's, else the slide's
    panel=ui.enum("slide", "text", "shape", "picture", "place", init="slide"),
    head="",
    head_icon="layout",
    bgs=ui.model(key="id", id="", rgb=""),
    bg_cur=ui.row_of("bgs"),
    bg_pic="None",
    trans=ui.enum(*D.TRANSITIONS, init="none"),
    font=ui.enum(*D.FONTS, init="sans"),
    size_text="",
    steps=ui.model(key="id", id="", word=""),
    step_cur=ui.row_of("steps"),
    colour_name="",
    fill_name="",
    line_name="",
    colour_chip="",             # each colour's chip on its link: "#RRGGBB", "" for None
    fill_chip="",
    line_chip="",
    align=ui.enum(*D.ALIGNS, init="left"),
    strip=ui.enum(*STRIPS, init="none"),
    appears=ui.enum("with", "tap", init="with"),
    shape=ui.enum(*D.SHAPES, init="rect"),
    lines=False,                # the shape is a line or an arrow
    width=ui.enum("thin", "thick", init="thin"),
    points=ui.enum(*POINTS, init="r"),
    scale=ui.enum(*SCALE_KEYS, init="s1"),
    clear=False,
    # Add a picture
    pic_tab=ui.enum("art", "sprites", init="art"),
    pics=ui.model(key="id", id="", title="", sub="", pic=ui.IMAGE),
    pcur=ui.row_of("pics"),
    pics_none=False,
    pic_status="",
    picked_pic=False,
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
    ep = lay.page if lay.page in EDITOR else None
    if ep != lay._ed_page:
        lay._ed_page = ep           # an editor's page entered: the slide, else its card, has focus
        if ep == "slide" and (lay._focus is None or lay._focus.endswith(CARD)):
            lay._focus = "board"
        elif lay._focus is None and ep == "deck":
            lay._focus = "%d%s" % (lay.cur, CARD)
    if lay._focus is not None:
        ui.focus(lay._focus)
        lay._focus = None
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
    if page == "editor" and lay.story is not None and lay.ed is not None:
        _fill_editor(lay)
    else:
        _set(lay, "band", "View only" if page == "view" and not lay.desk else "")
    st = lay.story
    _set(lay, "view", "%s %d %d" % (st.name, st.gen, lay.cur) if page == "view" and st is not None else "")
    if page == "view" and st is not None:
        n = len(st.slides)
        _set(lay, "can_prev", lay.cur > 0)
        _set(lay, "can_next", lay.cur < n - 1)
        _set(lay, "count_word", "%d / %d" % (lay.cur + 1, n))
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


def _slide_pic(lay, k):
    """Slide `k`'s card picture, drawn when the engine asks at the card's size."""
    def render(w, h):
        st = lay.story
        if st is None or k >= len(st.slides):
            return None
        layer = lay._surf.canvas().new_layer(w, h)
        cover(lay.renderer, layer, st.slides[k], w, h)
        return layer
    return render


def _slide_rows(lay):
    """The sorter's cards and the column's, each slide's picture put again
    where the slide changed: (cards, thumbs)."""
    import story_edit as E
    st = lay.story
    pics = lay.slide_pics
    cards, thumbs = [], []
    for k, sl in enumerate(st.slides):
        fp = st.name + repr(sl)
        for kind in ("deck:", "col:"):
            key = kind + str(k)
            if pics.get(key) != fp:
                pics[key] = fp
                ui.pictures.put(key, render=_slide_pic(lay, k))
        t = E.TRANS_ICONS[D.TRANSITIONS.index(sl["transition"])]
        n = str(k + 1)
        cards.append({"id": str(k), "num": n, "trans": t, "icon": "", "tone": "",
                      "pic": ui.image.own("deck:" + str(k))})
        thumbs.append({"id": str(k), "num": n, "trans": t, "pic": ui.image.own("col:" + str(k))})
    for key in list(pics):
        if int(key.partition(":")[2]) >= len(st.slides):
            lay.forget_pic(key)
    if len(st.slides) < D.MAX_SLIDES:
        cards.append({"id": ADD, "num": "New slide", "trans": "", "icon": "new", "tone": "value",
                      "pic": None})
    return cards, thumbs


def _rgb(c):
    return "0x%06X" % D.COLOURS[c]


def _fill_panel(lay, ed):
    """The style panel's rows: the chosen object's, else the slide's."""
    import story_edit as E
    o = ed._obj()
    sl = ed._slide_doc()
    if o is None:
        _set(lay, "panel", "slide")
        _set(lay, "head", "Slide %d" % (lay.cur + 1))
        _set(lay, "head_icon", "layout")
        bg = sl["bg"]
        recent = list(ed.recent)
        if isinstance(bg, int) and bg not in recent:
            recent = [bg] + recent[:3]
        _set(lay, "bgs", [{"id": str(c), "rgb": _rgb(c)} for c in recent])
        _set(lay, "bg_cur", str(bg) if isinstance(bg, int) else "")
        _set(lay, "bg_pic", bg if isinstance(bg, str) else "None")
        _set(lay, "trans", sl["transition"])
        return
    t = o["type"]
    if t == "picture":
        name = o["image"]
        _set(lay, "panel", "place" if name is None else "picture")
        _set(lay, "head", "Picture" if name is None else "Picture" + dot() + E._shown(name))
        _set(lay, "head_icon", "art")
        if name is not None:
            _set(lay, "scale", SCALE_KEYS[D.SCALES.index(o["scale"])])
            _set(lay, "clear", bool(o["clear"]))
    elif t == "text":
        _set(lay, "panel", "text")
        _set(lay, "head", "Text")
        _set(lay, "head_icon", "text")
        _set(lay, "strip", "none" if o["strip"] is None else "c%d" % o["strip"])
    else:
        k = D.SHAPES.index(o["shape"])
        _set(lay, "panel", "shape")
        _set(lay, "head", E.SHAPE_TITLES[k])
        _set(lay, "head_icon", "bubble" if o["shape"] == "bubble" else "shapes")
        _set(lay, "shape", o["shape"])
        _set(lay, "lines", o["shape"] in ("line", "arrow"))
        _set(lay, "fill_name", _colour_name(o["fill"]))
        _set(lay, "line_name", _colour_name(o["line"]))
        _set(lay, "fill_chip", _chip(o["fill"]))
        _set(lay, "line_chip", _chip(o["line"]))
        _set(lay, "width", "thin" if o["width"] == D.WIDTHS[0] else "thick")
        _set(lay, "points", POINTS[o["flip"]])
    if t in ("text", "shape"):
        _set(lay, "font", o["font"])
        _set(lay, "size_text", str(o["size"]))
        _set(lay, "steps", [{"id": str(v), "word": n} for n, v in D.SIZES])
        sizes = [str(v) for _n, v in D.SIZES]
        _set(lay, "step_cur", str(o["size"]) if str(o["size"]) in sizes else "")
        _set(lay, "colour_name", _colour_name(o["colour"]))
        _set(lay, "colour_chip", _chip(o["colour"]))
        _set(lay, "align", o["align"])
    _set(lay, "appears", "with" if o.get("step", 0) == 0 else "tap")


def _colour_name(c):
    return "None" if c is None else D.COLOUR_NAMES[c]


def _chip(c):
    return "" if c is None else "#%06X" % D.COLOURS[c]


def _fill_editor(lay):
    """The editor's states: its page, its menus, the sorter's and the
    column's cards, the tools' availability, the panel, Add a picture."""
    ed = lay.ed
    st = lay.story
    page = lay.page
    _set(lay, "ed", page)
    _set(lay, "ed_menu", ed.menu or "none")
    if lay._slides_at != (st.name, st.gen, len(st.slides)):
        lay._slides_at = (st.name, st.gen, len(st.slides))
        cards, thumbs = _slide_rows(lay)
        _set(lay, "slides", cards)
        _set(lay, "thumbs", thumbs)
    _set(lay, "can_undo", st.can_undo())
    _set(lay, "can_redo", st.can_redo())
    if page == "deck":
        i = ed.deck_focus()
        _set(lay, "dslide", i is not None)
        _set(lay, "band", ed.deck_status(i))
        lay.engine.band_extra(("[ ]", "Move", "Ctrl D", "Duplicate", "Del", "Delete"))
        k = D.LAYOUTS.index(ed.layout_kind)
        for j in range(4):
            _set(lay, "lay%d" % j, D.LAYOUT_NAMES[j] + ("\tEnter" if j == k else ""))
    elif page == "slide":
        n = len(st.slides)
        o = ed._obj()
        _set(lay, "here", str(lay.cur))
        _set(lay, "has_obj", o is not None)
        _set(lay, "has_clip", ed.clip is not None)
        _set(lay, "can_prev", lay.cur > 0)
        _set(lay, "can_next", lay.cur < n - 1)
        _set(lay, "count_word", "%d / %d" % (lay.cur + 1, n))
        _set(lay, "board", ed.board_view())
        _set(lay, "band", ed.slide_status())
        lay.engine.band_extra(ed.slide_hints())
        _set(lay, "more_title", ed._describe(o) if o is not None else "Slide")
        _set(lay, "snap_word", "Snap\t" + ("on" if ed.snap else "off"))
        _set(lay, "slide_title", "Slide %d" % (lay.cur + 1))
        t = D.TRANSITIONS.index(st.slides[lay.cur]["transition"])
        _set(lay, "trans_word", "Transition\t" + ("None", "Fade", "Swipe")[t])
        if ed.menu == "colours":
            c = ed.colour_now()
            _set(lay, "swatch_a", [{"id": str(j), "rgb": _rgb(j)} for j in range(8)])
            _set(lay, "swatch_b", [{"id": str(j), "rgb": _rgb(j)} for j in range(8, 16)])
            _set(lay, "cur_a", str(c) if 0 <= c < 8 else "")
            _set(lay, "cur_b", str(c) if c >= 8 else "")
            _set(lay, "none_ok", bool(ed.colour_key and ed.colour_key[1]))
            _set(lay, "colour_for", ed.colour_key[0] if ed.colour_key else "bg")
        _fill_panel(lay, ed)
    else:
        _set(lay, "band", "")
        if ed.pics is None:
            import story_edit as E
            ed._scan_pictures(lambda name, blob: ui.pictures.put(
                "draw:" + name, data=blob.encode() if isinstance(blob, str) else blob))
            x = "×" if _v.has_symbols() else "x"
            _set(lay, "pics", [{"id": name, "title": E._shown(name), "sub": "%d %s %d" % (w, x, h),
                                "pic": ui.image.own("draw:" + name)} for name, w, h in ed.pics])
            _set(lay, "pics_none", not ed.pics)
            if ed.pics:                 # the first drawing chosen, as the page opens
                s.pcur = ed.pics[0][0]
                ui.focus(ed.pics[0][0] + "/place_pic")
        name = s.pcur or None
        _set(lay, "pic_status", ed.pics_status(name))
        _set(lay, "picked_pic", name is not None)


def opened():
    fill(_lay())


def moved(row):
    _lay()


def deck_moved(row):
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
ui.hook("deck_moved", deck_moved, takes="row")
ui.action("open", "Open", open_card, takes="row")
ui.action("prev", "Previous slide", prev, keys=("role:left",), hint="Slides",
          when="page=view && can_prev", off="hide")
ui.action("next", "Next slide", next_, keys=("role:right",), hint="Slides",
          when="page=view && can_next", off="hide")
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
    """A story's view: its slide at a quarter on its shadow in an edge."""
    lay = _LAYER[0]
    st = lay.story if lay is not None else None
    if st is None:
        return
    fs = max(1, int(getattr(cv, "font_scale", 1)))
    th = ui.colors()
    sw, sh = R.size(fs, 4)
    sx, sy = x + (w - sw) // 2, y + fs
    cv.shadow(sx, sy, sw, sh, 0, 1, 40, 6 * fs, 0, 2 * fs, (sx, sy, sw, sh, 0))
    lay.frames.place(cv, ("view", st.gen, lay.cur, sw, sh), st.slides[lay.cur], sx, sy, sw, sh)
    cv.rectb(sx - 1, sy - 1, sw + 2, sh + 2, th["edge"])


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
    ui.canvas("view", draw_view, h=152, ground="panel", reads=["view"])
    ui.stepper("{count_word}", "prev", "next")
    ui.label("Edit stories on a desk board or the web", tone="dim", align="center")


# -- the desk's editor (runtime/apps/story_edit.py holds its state and verbs) ---------
#
# The sorter, a slide and Add a picture are the "editor" case's pages
# (`ed`). The slide on its pasteboard is the `board` canvas, the slide's keys
# its keys= while it holds focus; every other part is the page's.

ui.labels("TRANS", {"none": "None", "fade": "Fade", "swipe": "Swipe"})
ui.labels("FONTS", dict(zip(D.FONTS, D.FONT_NAMES)))
ui.labels("ALIGNS", {"left": "Left", "centre": "Centre", "right": "Right"})
ui.labels("STRIPS", dict(zip(STRIPS, ("None",) + D.COLOUR_NAMES)))
ui.labels("APPEARS", {"with": "With slide", "tap": "On tap"})
ui.labels("SHAPES", dict(zip(D.SHAPES, D.SHAPE_NAMES)))
ui.labels("WIDTHS", {"thin": "Thin", "thick": "Thick"})
ui.labels("POINTS", dict(zip(POINTS, ("Right", "Left", "Up right", "Up left"))))
ui.labels("SCALES", dict(zip(SCALE_KEYS, ("½", "1", "2", "3", "4"))))
ui.labels("PIC_TABS", {"art": "My Art", "sprites": "Sprites"})


def _ed():
    return _lay().ed


def edit_slide(row):
    """A sorter's card taken: its slide opens to edit; New slide's opens
    the layouts."""
    lay = _lay()
    if row.id == ADD:
        lay.ed.menu = "layouts"
        return
    lay.cur = int(row.id)
    lay.page = "slide"
    lay.ed.chosen = None
    lay._focus = "board"


def goto_slide(row):
    ed = _ed()
    ed._goto(int(row.id))
    ed.on_slide = True


def new_slide():
    _ed().menu = "layouts"


def dup_slide():
    _ed()._deck_keys(4)


def del_slide():
    ed = _ed()
    i = ed.deck_focus()
    if i is not None:
        ed._delete_slide(i)


def undo():
    _ed()._undo()


def redo():
    _ed()._undo(redo=True)


def present_ed():
    lay = _lay()
    lay._start(lay.cur)


def add():
    _ed().menu = "add"


def to_front():
    _ed()._front()


def to_back():
    _ed()._front(back=True)


def copy():
    _ed()._copy()


def paste():
    _ed()._paste()


def prev_slide():
    lay = _lay()
    lay.ed._goto(lay.cur - 1)


def next_slide():
    lay = _lay()
    lay.ed._goto(lay.cur + 1)


def menu_close():
    _ed().menu = None


def _picker(menu, a):
    def pick():
        getattr(_ed(), menu)(a)
    return pick


def board_keys(i):
    """The slide's keys while the pasteboard holds focus."""
    lay = _lay()
    return lay.ed._slide_keys(i, getattr(i, "typed", 0))


def board_at(ev):
    """A press, drag or release on the pasteboard: the slide's (choose,
    move, resize), and the keys to the slide."""
    lay = _lay()
    if ev.kind == "down":
        ui.focus("board")
    lay.ed.handle_pointer(ev.x, ev.y, ev.kind == "down", ev.kind != "up")


def draw_board(cv, x, y, w, h):
    lay = _LAYER[0]
    if lay is not None and lay.ed is not None:
        lay.ed.draw_board(cv, x, y, w, h, ui.colors())


# the style panel's rows: each writes what it shows into the slide or the chosen object

def bg_moved():
    if s.bg_cur:
        _ed()._set_slide("bg", int(s.bg_cur))


def all_colours():
    _ed().colours("bg", False)


def bg_picture():
    _ed()._open_pictures("bg")


def trans_moved():
    _ed()._set_slide("transition", s.trans)


def _setter(key, conv):
    def moved():
        _ed()._set(key, conv(getattr(s, key)))
    return moved


def size_typed():
    t = s.size_text
    if t.isdigit() and D.SIZE_MIN <= int(t) <= D.SIZE_MAX:
        _ed()._set("size", int(t))


def step_moved():
    if s.step_cur:
        _ed()._set("size", int(s.step_cur))


def strip_moved():
    _ed()._set("strip", None if s.strip == "none" else int(s.strip[1:]))


def appears_moved():
    ed = _ed()
    if s.appears == "with":
        ed._set("step", 0)
    else:
        m = 0
        for p in ed._slide_doc()["objects"]:
            m = max(m, p["step"])
        ed._set("step", min(D.MAX_OBJECTS, m + 1))


def width_moved():
    _ed()._set("width", D.WIDTHS[0 if s.width == "thin" else 1])


def points_moved():
    _ed()._set("flip", POINTS.index(s.points))


def scale_moved():
    _ed()._set("scale", D.SCALES[SCALE_KEYS.index(s.scale)])


def clear_moved():
    _ed()._set("clear", s.clear)


def pick_colour():
    _ed().colours("colour", False)


def pick_fill():
    _ed().colours("fill", True)


def pick_line():
    _ed().colours("line", True)


def add_picture():
    _ed()._open_pictures("add")


def swatch_a():
    if s.cur_a:
        _ed().colour_pick(int(s.cur_a))


def swatch_b():
    if s.cur_b:
        _ed().colour_pick(int(s.cur_b))


def no_colour():
    _ed().colour_pick(-1)


# Add a picture

def _place(name):
    ed = _ed()
    for p in ed.pics or ():
        if p[0] == name:
            ed._place(p)


def place_pic(row):
    _place(row.id)


def add_chosen():
    _place(s.pcur)


ui.action("edit_slide", "Edit", edit_slide, takes="row", hint="Edit")
ui.action("goto_slide", "Edit", goto_slide, takes="row", hint="Edit")
ui.action("new_slide", "New slide", new_slide)
ui.action("dup_slide", "Duplicate", dup_slide, when="dslide", off="grey")
ui.action("del_slide", "Delete", del_slide, when="dslide", off="grey")
ui.action("undo", "Undo\tCtrl+Z", undo, when="can_undo", off="grey")
ui.action("redo", "Redo\tCtrl+Y", redo, when="can_redo", off="grey")
ui.action("present_ed", "Present", present_ed)
ui.action("add", "Add", add)
ui.action("to_front", "Front", to_front, when="has_obj", off="grey")
ui.action("to_back", "Back", to_back, when="has_obj", off="grey")
ui.action("copy", "Copy", copy, when="has_obj", off="grey")
ui.action("paste", "Paste", paste, when="has_clip", off="grey")
ui.action("prev_slide", "Previous slide\t,", prev_slide, when="can_prev", off="grey")
ui.action("next_slide", "Next slide\t.", next_slide, when="can_next", off="grey")
ui.action("menu_close", "Close", menu_close)
_DOTS = "…"
for _a, _l in (("text", "Text\tT"), ("shape", "Shape\tS"), ("pic", "Picture" + _DOTS + "\tI"),
               ("bg", "Background" + _DOTS + "\tB")):
    ui.action("add_" + _a, _l, _picker("add_pick", _a))
for _k in range(4):
    ui.action("lay_%d" % _k, D.LAYOUT_NAMES[_k], _picker("layout_pick", _k))
for _a, _l in (("front", "Front\t]"), ("back", "Back\t["), ("copy", "Copy\tCtrl+C"),
               ("paste", "Paste\tCtrl+V"), ("centre", "Centre on the slide"), ("snap", "Snap"),
               ("dup", "Duplicate\tCtrl+D"), ("del", "Delete\tDel")):
    ui.action("more_" + _a, _l, _picker("more_pick", _a))
for _a, _l in (("trans", "Transition"), ("dup", "Duplicate\tCtrl+D"),
               ("earlier", "Move earlier\t["), ("later", "Move later\t]"), ("del", "Delete\tDel")):
    ui.action("sl_" + _a, _l, _picker("slide_pick", _a))
ui.action("all_colours", "All colours", all_colours)
ui.action("bg_picture", "Picture", bg_picture)
ui.action("pick_colour", "Colour", pick_colour)
ui.action("pick_fill", "Fill", pick_fill)
ui.action("pick_line", "Line", pick_line)
ui.action("add_picture", "Add a picture", add_picture)
ui.action("no_colour", "None", no_colour)
ui.action("place_pic", "Add", place_pic, takes="row", hint="Add")
ui.action("add_chosen", "Add", add_chosen, when="picked_pic", off="grey")
ui.hook("board_at", board_at, takes="pointer")
ui.hook("bg_moved", bg_moved)
ui.hook("trans_moved", trans_moved)
ui.hook("font_moved", _setter("font", str))
ui.hook("align_moved", _setter("align", str))
ui.hook("shape_moved", _setter("shape", str))
ui.hook("size_typed", size_typed)
ui.hook("step_moved", step_moved)
ui.hook("strip_moved", strip_moved)
ui.hook("appears_moved", appears_moved)
ui.hook("width_moved", width_moved)
ui.hook("points_moved", points_moved)
ui.hook("scale_moved", scale_moved)
ui.hook("clear_moved", clear_moved)
ui.hook("pick_a", swatch_a)
ui.hook("pick_b", swatch_b)


def _deck():
    """The sorter: its tools over a card a slide, New slide last."""
    with ui.split("col", sizes=(32, "1*"), gap="s", pad="s", rule=True):
        with ui.row("deck_tools", pad=6, gap=8):
            ui.button("new_slide", icon="layout")
            ui.button("dup_slide", icon="dup")
            ui.button("del_slide", "danger", icon="trash")
            ui.rule()
            ui.button("undo", icon="undo", alone=True, kind="bar")
            ui.button("redo", icon="redo", alone=True, kind="bar")
            ui.label("")
            ui.button("present_ed", "primary", icon="play")
        with ui.cards("slides", cur="dcur", changed="deck_moved", w=256, h=150, pad=24):
            ui.card("edit_slide", label="{.num}", label_icon="{.trans}", icon="{.icon}",
                    tone="{.tone}", image=".pic")


def _words():
    """A text's rows (a text box's, a shape's caption's)."""
    ui.seg("Font", "font", labels="FONTS", look="cycle", on="font_moved")
    ui.field("Size", "size_text", 3, changed="size_typed")
    ui.seg("", "step_cur", text="{.word}", on="step_moved")
    ui.link("pick_colour", "{colour_name}", swatch="{colour_chip}")
    ui.seg("Align", "align", labels="ALIGNS", on="align_moved")


def _head():
    ui.label("{head}", icon="{head_icon}", face="title")


def _panel_slide():
    _head()
    with ui.group("", look="rules"):
        with ui.row("bg_row", gap=0):
            ui.seg("Background", "bg_cur", text="{.rgb}", look="swatches", on="bg_moved")
            ui.button("all_colours", icon="forward", alone=True, kind="bar")
        ui.link("bg_picture", "{bg_pic}")
    ui.label("Transition", face="caption", tone="dim")
    ui.seg("", "trans", labels="TRANS", on="trans_moved")


def _panel_text():
    _head()
    with ui.group("", look="rules"):
        _words()
        ui.seg("Strip behind", "strip", labels="STRIPS", look="cycle", on="strip_moved")
        ui.seg("Appears", "appears", labels="APPEARS", on="appears_moved")


def _panel_shape():
    _head()
    with ui.group("", look="rules"):
        ui.seg("Shape", "shape", labels="SHAPES", look="cycle", on="shape_moved")
        ui.link("pick_fill", "{fill_name}", swatch="{fill_chip}", shown="!lines")
        ui.link("pick_line", "{line_name}", swatch="{line_chip}")
        ui.seg("Width", "width", labels="WIDTHS", on="width_moved")
        ui.seg("Points", "points", labels="POINTS", look="cycle", on="points_moved", shown="lines")
    with ui.group("Text", shown="!lines"):
        _words()
    ui.seg("Appears", "appears", labels="APPEARS", on="appears_moved")


def _panel_picture():
    _head()
    with ui.group("", look="rules"):
        ui.seg("Size", "scale", labels="SCALES", on="scale_moved")
        ui.toggle("Clear background", "clear", on="clear_moved")
        ui.seg("Appears", "appears", labels="APPEARS", on="appears_moved")


def _panel_place():
    _head()
    ui.link("add_picture")


def _slide():
    """A slide: its tools over the slides column, the slide on its
    pasteboard and the style panel."""
    with ui.split("col", sizes=(32, "1*"), gap="s", pad="s", rule=True):
        with ui.row("slide_tools", pad=6, gap=4):
            ui.button("add", icon="new")
            ui.rule()
            ui.button("to_front", icon="to_front")
            ui.button("to_back", icon="to_back")
            ui.rule()
            ui.button("copy", icon="copy")
            ui.button("paste", icon="paste")
            ui.rule()
            ui.button("undo", icon="undo", alone=True, kind="bar")
            ui.button("redo", icon="redo", alone=True, kind="bar")
            ui.label("")
            ui.stepper("{count_word}", "prev_slide", "next_slide")
            ui.button("present_ed", "primary", icon="play")
        with ui.split("row", sizes=(88, "1*", 244), gap="s", pad="0", rule=True):
            with ui.cards("thumbs", current="here", w=72, h=42):
                ui.card("goto_slide", label="{.num}", label_icon="{.trans}", image=".pic")
            ui.canvas("board", draw_board, pointer="board_at", keys=board_keys, reads=["board"],
                      ground="panel", mark=False)
            with ui.group(""):
                ui.switch("panel", {"slide": _panel_slide, "text": _panel_text,
                                    "shape": _panel_shape, "picture": _panel_picture,
                                    "place": _panel_place})


def _pictures():
    """Add a picture: My Art's drawings as cards, Add at the foot."""
    with ui.split("col", sizes=(32, "1*"), gap="s", pad="s", rule=True):
        with ui.row("pic_tabs", pad=6):
            ui.tabs("pic_tab", labels="PIC_TABS")
            ui.label("")
        with ui.group(""):
            with ui.cards("pics", cur="pcur", changed="deck_moved", w=152, h=112,
                          shown="pic_tab=art && !pics_none"):
                ui.card("place_pic", label="{.title}", sub="{.sub}", image=".pic")
            ui.empty("No drawings yet", icon="art", shown="pic_tab=art && pics_none",
                     lines=["Draw one in Paint, then put it", "in your story from here."])
            ui.empty("No sprites here yet", icon="sprite", shown="pic_tab=sprites",
                     lines=["A story takes My Art's drawings;", "sprites come later."])
    with ui.foot():
        ui.label("{pic_status}", tone="dim", face="caption")
        ui.button("add_chosen", "primary", icon="new")


def _editor():
    ui.switch("ed", {"deck": _deck, "slide": _slide, "pictures": _pictures})


def _ed_menus():
    with ui.popover("add_menu", anchor="add", shown="ed_menu=add", close="menu_close", w=236):
        with ui.menu(""):
            ui.item("add_text", icon="text")
            ui.item("add_shape", icon="shapes")
            ui.item("add_pic", icon="art")
            ui.item("add_bg", icon="background")
    with ui.popover("layouts", anchor="new_slide", shown="ed_menu=layouts", close="menu_close",
                    w=236):
        with ui.menu("New slide"):
            ui.item("lay_0", icon="text", label="{lay0}")
            ui.item("lay_1", icon="background", label="{lay1}")
            ui.item("lay_2", icon="slides", label="{lay2}")
            ui.item("lay_3", icon="layout", label="{lay3}")
    with ui.popover("more", anchor="board", shown="ed_menu=more", close="menu_close", w=260,
                    wash="page"):
        with ui.menu("{more_title}"):
            ui.item("more_front", icon="to_front")
            ui.item("more_back", icon="to_back")
            ui.item("more_copy", icon="copy")
            ui.item("more_paste", icon="paste")
            ui.item("more_centre", icon="align_c")
            ui.item("more_snap", icon="check", label="{snap_word}")
            ui.item("more_dup", icon="dup")
            ui.item("more_del", icon="trash", mkind="danger")
    with ui.popover("slide_menu", anchor="slides.cur", shown="ed_menu=slide", close="menu_close",
                    w=260, wash="page"):
        with ui.menu("{slide_title}"):
            ui.item("sl_trans", icon="trans_fade", label="{trans_word}")
            ui.item("sl_dup", icon="dup")
            ui.item("sl_earlier", icon="arrow_left")
            ui.item("sl_later", icon="arrow_right")
            ui.item("sl_del", icon="trash", mkind="danger")
    for key, at in (("bg", "all_colours"), ("colour", "pick_colour"), ("fill", "pick_fill"),
                    ("line", "pick_line")):
        with ui.popover("colours_" + key, anchor=at, shown="ed_menu=colours && colour_for=" + key,
                        close="menu_close", w=300):
            ui.seg("Colours", "cur_a", text="{.rgb}", look="swatches", on="pick_a")
            ui.seg(" ", "cur_b", text="{.rgb}", look="swatches", on="pick_b")
            ui.button("no_colour", shown="none_ok")


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
        _ed_menus()
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
    on the whole glass and the desk's editor's state and verbs
    (runtime/apps/story_edit.py)."""

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
        self._focus = None            # the id focus moves to at the next fill (the editor's)
        self._ed_page = None          # the editor's page the last fill saw
        self.slide_pics = {}          # the slides' card pictures put: key -> what each shows
        self._slides_at = None        # (story, gen, slides) the cards were made at
        self._edited_at = None
        self._menu_story = None
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

    def focused_id(self):
        """The id focus is on, or moves to at the next fill (a slide's page
        entered: its pasteboard)."""
        f = self._focus
        if self.page == "slide" and self._ed_page != "slide" and (f is None or f.endswith(CARD)):
            return "board"
        return f if f is not None else self.engine.focus_key

    def forget_pic(self, key):
        self.slide_pics.pop(key, None)
        ui.pictures.drop(key)
        if self.engine.pics is not None:
            self.engine.pics.forget_own(key)

    def forget_slides(self):
        """The slides' card pictures let go (a story left, the app closed)."""
        for key in list(self.slide_pics):
            self.forget_pic(key)
        self._slides_at = None

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
        self.forget_slides()
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
        self.forget_slides()
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
                and self.asking is None and self.ed.handle_input(inp, k):
            self.owe()
            return True
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
        if self.page in EDITOR:
            self.fill_owed = True     # the editor's verbs move its states outside a handler too
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
        # a desk window's band says the editor's keys; the stories' page has none
        self.engine.band = not self.desk or self.page in BANDED
        super().draw(dt)
        if self.page == "view" and self.story is not None:
            if _v.bar(self.story.title() or "Untitled", ("play",), (), True) == 0:
                self._start(self.cur)

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
