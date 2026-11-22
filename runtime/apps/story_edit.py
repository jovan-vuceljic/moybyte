# Map (grep -n a name to jump there):
#   Editor                 the desk's story editor's state and verbs; its page is storybook_app's
#   Editor.handle_input    the editor's keys before the page's
#   Editor._slide_keys     the keys a slide takes: choose, move, resize, write, add
#   Editor.handle_pointer  a pointer on the slide: choose, drag, resize, snap
#   Editor.draw_board      the slide on its pasteboard (the page's board canvas)
#   Editor._place          Add a picture: a drawing of My Art's copied into the story
"""Storybook's editor, on the desk boards and in the web build
(docs/media/look_2026-10/APPS_RESTYLE.md, Storybook: Screens, Desk, Inputs).
A handheld does not edit a story; runtime/apps/storybook_app.py makes this only
where the console is a desk.

  SLIDES    the sorter: a card a slide at 1/4, three a row, its number and
            its transition's icon; New slide last, which opens the layouts;
            N adds after the focused slide, [ and ] move it, Ctrl+D
            duplicates it, Del deletes it, M its menu.
  A SLIDE   on its pasteboard at the largest zoom it takes (1/2 in the
            window, 5/8 where the window fills the glass): the slides column
            at its left, the style panel at its right. The keys are the
            slide's while the pasteboard holds focus, until Y or Esc with
            nothing chosen (the parts).

The page that shows all this is storybook_app's (`build`); this module holds
what it shows and what its verbs do, the selection, the handles and the drag
apart from any drawing but the pasteboard's.
  ADD A PICTURE  My Art's drawings, each copied into the story when it is
            placed (copy-on-use); a picture at half its size reads the half
            baked beside it then.
"""

import ui
import story_doc as D
import story_render as R
from ticks import _ticks_ms, _ticks_diff

KIND = "stories"
STEP, GRID = 2, 16
SNAP_POINTER, SNAP_TOUCH = 6, 12
HANDLE, HANDLE_POINTER, HANDLE_TOUCH = 8, 16, 32
GUIDE = 0x4C3FD6                # the snap guide, in every theme
DOUBLE_MS = 400
LONG_MS = 600
TRANS_ICONS = ("trans_none", "trans_fade", "trans_swipe")
TRANS_NAMES = ("None", "Fade", "Swipe")
SCALE_WORDS = ("½", "1", "2", "3", "4")
LAYOUT_ICONS = ("text", "background", "slides", "layout")
EDIT_ZOOMS = ((5, 8), (1, 2), (3, 8), (1, 4))     # the slide's on the pasteboard, the largest that fits
SHAPE_TITLES = ("Rectangle", "Rounded rectangle", "Ellipse", "Line", "Arrow", "Star",
                "Speech bubble")


def _w565(rgb):
    return ((rgb >> 19) & 31) << 11 | ((rgb >> 10) & 63) << 5 | ((rgb >> 3) & 31)


GUIDE_565 = _w565(GUIDE)
WHITE_565 = 0xFFFF


class Editor:
    """The desk's editing pages of the app `app` (StorybookAppLayer): the
    story is the app's (`app.story`), so are the renderer, the frames and
    the files."""

    def __init__(self, app):
        self.app = app
        self.chosen = None            # the chosen object's index on the slide
        self.writing = False
        self.zoom = (1, 2)            # the slide's on the pasteboard (fit)
        self.slide = (0, 0, 0, 0)     # and its rect, in the board canvas's coordinates
        self._board = None            # the board's size the rect was fitted to
        self.step = STEP
        self.resizing = False
        self.snap = True
        self.clip = None              # the copied object
        self.layout_kind = "picture"
        self.recent = [15, 7, 10, 1]  # the backgrounds last used
        self.menu = None              # add, layouts, more, slide, colours, bgcolours
        self.colour_key = None        # what the colours popover sets
        self.pic_mode = "add"         # pictures: "add" a picture, or the "bg"
        self.pic_tab = 0
        self.pics = None              # [(name, w, h)] My Art's drawings
        self.added = []               # pictures copied in this session
        self.drag = None
        self.guides = ()
        self.say = ""                 # the foot's status while a drag lines up
        self._click = None            # (ms, x, y) of the last press: a double click
        self._press = None            # (ms, x, y): a press held, for a long press
        self._new = False

    # -- what the app asks -------------------------------------------------------------

    def relayout(self):
        self.app.frames.drop() if self.app.frames is not None else None
        self._board = None

    @property
    def on_slide(self):
        """The slide has the keys: the board canvas holds focus (or is about to)."""
        return self.app.focused_id() == "board"

    @on_slide.setter
    def on_slide(self, v):
        """The keys to the slide, else to the parts (the tool row's first)."""
        self.app._focus = "board" if v else "add"
        self.app.owe()

    def deck_focus(self):
        """The sorter's focused slide, or None (none, or the New slide card)."""
        f = self.app.state().dcur
        return int(f) if f and f.isdigit() and int(f) < len(self.app.story.slides) else None

    def opened(self, new=False):
        self.chosen = None
        self.writing = False
        self.menu = None
        self.resizing = False
        self._new = new
        app = self.app
        if new:
            app.page = "slide"
            self.chosen = 0
            self._write()
        app._damage.all()

    def presented(self, i):
        self.app.cur = i

    def back(self):
        app = self.app
        if self.menu is not None:
            self.menu = None
            app._damage.all()
            return True
        if app.page == "pictures":
            app.page = "slide"
            app._damage.all()
            return True
        if app.page == "slide":
            if self.writing:
                self.stop_writing()
                return True
            if self.chosen is not None:
                self.chosen = None
                app._damage.all()
                return True
            if not self.on_slide:
                self.on_slide = True
                return True
            app.page = "deck"
            app._focus = card_id(app.cur)
            app._damage.all()
            return True
        if app.page == "deck":
            self._prune()
            return False
        return False

    # -- the story's pictures ------------------------------------------------------------

    def _size_of(self, name):
        return self.app.images.size(name) or (0, 0)

    def _prune(self):
        """The pictures copied in this session that no slide uses go."""
        st = self.app.story
        if st is None:
            return
        used = st.images()
        for name in self.added:
            if name not in used:
                self.app._files.delete(KIND, st.name + "/" + name + ".moyimg")
                self.app._files.delete(KIND, st.name + "/" + name + "_h.moyimg")
        self.added = []

    # -- writing words -----------------------------------------------------------------

    def _write(self):
        """Write the chosen object's words (a text box's, a shape's)."""
        o = self._obj()
        if o is None or o["type"] not in ("text", "shape"):
            return
        st = self.app.story
        st.record(self.app.cur)
        self.writing = True
        self.app._damage.all()

    def stop_writing(self):
        if not self.writing:
            return
        self.writing = False
        st = self.app.story
        if st is not None and self._new and self.app.cur == 0:
            objs = st.objects(0)
            t = objs[0]["text"].strip() if objs and objs[0]["type"] == "text" else ""
            if t and not st.title():
                st.set_title(t)
                self._rename_item(t)
        self._new = False
        self.app.edited()

    def _rename_item(self, title):
        """A new story's item takes its title's name."""
        app = self.app
        st = app.story
        app.commit()
        name, err = app._files.rename(KIND, st.name, title)
        if err is None and name:
            for s in app.stories:
                if s["name"] == st.name:
                    s["name"] = name
            st.name = name
            app.images.load = app._load(name)

    def _type(self, k):
        app = self.app
        st = app.story
        o = self._obj()
        if o is None:
            self.writing = False
            return
        t = o["text"]
        if k == 8:
            t = t[:-1]
        elif k in (13, 10, 27):
            self.stop_writing()
            return
        elif 32 <= k < 127 and len(t) < D.MAX_TEXT:
            t += chr(k)
        else:
            return
        o["text"] = t
        st.dirty = True
        st.gen += 1
        app.edited()

    # -- the chosen object ------------------------------------------------------------------

    def _slide_doc(self):
        return self.app.story.slides[self.app.cur]

    def _obj(self):
        objs = self._slide_doc()["objects"]
        if self.chosen is None or not 0 <= self.chosen < len(objs):
            self.chosen = None
            return None
        return objs[self.chosen]

    def _bounds(self, o):
        """(x, y, w, h) an object covers, in slide pixels."""
        if o["type"] == "text":
            cv = self.app._surf.canvas()
            return (o["x"], o["y"], o["w"], self.app.renderer.box_h(cv, o))
        return D.bounds(o, self._size_of)

    def _to_screen(self, b):
        n, d = self.zoom
        sx, sy = self.slide[0], self.slide[1]
        return (sx + b[0] * n // d, sy + b[1] * n // d, b[2] * n // d, b[3] * n // d)

    def _choose(self, j):
        if self.writing:
            self.stop_writing()
        self.chosen = j
        self.resizing = False
        self.app._damage.all()

    # -- edits -----------------------------------------------------------------------------

    def _edited(self):
        self.app.edited()

    def _add(self, kind):
        app = self.app
        st = app.story
        i = app.cur
        if len(st.objects(i)) >= D.MAX_OBJECTS:
            app._say("A slide holds %d things" % D.MAX_OBJECTS, "warn")
            return
        ink = D.ink_on(st.slides[i]["bg"])
        if kind == "text":
            o = D.text_obj("", 64, 260, 896, 64, ink)
        else:
            o = D.shape_obj("round", 312, 180, 400, 220, 7, 0, 8, "", 64, 0)
        j = st.add(i, o)
        self._choose(j)
        self.on_slide = True
        if kind == "text":
            self._write()
        self._edited()

    def _delete(self):
        o = self._obj()
        if o is None:
            return
        self.app.story.delete(self.app.cur, self.chosen)
        self.chosen = None
        self.app._say("Deleted" + D_DOT() + "Ctrl+Z brings it back", "trash")
        self._edited()

    def _duplicate(self):
        if self._obj() is None:
            return
        j = self.app.story.duplicate(self.app.cur, self.chosen)
        if j is None:
            self.app._say("A slide holds %d things" % D.MAX_OBJECTS, "warn")
            return
        self._choose(j)
        self._edited()

    def _copy(self):
        o = self._obj()
        if o is None:
            return
        self.clip = (self.app.story.name, D.copy(o))
        self.app._say("Copied", "copy")

    def _paste(self):
        if self.clip is None:
            return
        name, o = self.clip
        o = D.copy(o)
        if o["type"] == "picture" and o["image"] is not None and name != self.app.story.name:
            self.app._say("A picture pastes into its own story", "warn")
            return
        st = self.app.story
        j = st.add(self.app.cur, o)
        if j is None:
            self.app._say("A slide holds %d things" % D.MAX_OBJECTS, "warn")
            return
        self._choose(j)
        self._edited()

    def _front(self, back=False):
        if self._obj() is None:
            return
        st = self.app.story
        self.chosen = st.to_back(self.app.cur, self.chosen) if back \
            else st.to_front(self.app.cur, self.chosen)
        self._edited()

    def _undo(self, redo=False):
        st = self.app.story
        got = st.redo() if redo else st.undo()
        if got is False:
            return
        if got is not None:
            self.app.cur = got
        self.app.cur = min(self.app.cur, len(st.slides) - 1)
        self.chosen = None
        self.writing = False
        self._edited()

    def _move(self, dx, dy):
        o = self._obj()
        if o is None:
            return
        st = self.app.story
        if self.resizing:
            self._resize_by(o, dx, dy)
            return
        st.place(self.app.cur, self.chosen, o["x"] + dx, o["y"] + dy, hold=False)
        self._edited()

    def _resize_by(self, o, dx, dy, keep=False):
        st = self.app.story
        i, j = self.app.cur, self.chosen
        if o["type"] == "picture":
            if o["image"] is None:
                st.place(i, j, o["x"], o["y"], max(16, o["w"] + dx), max(16, o["h"] + dy),
                         hold=False)
            else:
                k = D.SCALES.index(o["scale"])
                k = max(0, min(len(D.SCALES) - 1, k + (1 if dx + dy > 0 else -1)))
                st.set(i, j, "scale", D.SCALES[k])
        elif o["type"] == "text":
            if keep:
                st.set(i, j, "size", max(D.SIZE_MIN, min(D.SIZE_MAX, o["size"] + dx)))
            else:
                st.place(i, j, o["x"], o["y"], max(32, o["w"] + dx), None, hold=False)
        elif o["type"] == "shape":
            w, h = o["w"], o["h"]
            if keep and w:
                nw = max(8, w + dx)
                st.place(i, j, o["x"], o["y"], nw, max(8, h * nw // w), hold=False)
            else:
                st.place(i, j, o["x"], o["y"], max(0, w + dx), max(0, h + dy), hold=False)
        self._edited()

    def _centre(self):
        o = self._obj()
        if o is None:
            return
        b = self._bounds(o)
        self.app.story.place(self.app.cur, self.chosen, (D.SW - b[2]) // 2,
                             (D.SH - b[3]) // 2, hold=False)
        self._edited()

    def _goto(self, i):
        app = self.app
        i = max(0, min(len(app.story.slides) - 1, i))
        if i != app.cur:
            self.stop_writing()
            app.cur = i
            self.chosen = None
            app._damage.all()

    def _new_slide(self, after, kind=None):
        app = self.app
        kind = kind or self.layout_kind
        self.layout_kind = kind
        j = app.story.add_slide(after, kind)
        if j is None:
            app._say("A story holds %d slides" % D.MAX_SLIDES, "warn")
            return None
        app.cur = j
        app._focus = card_id(j)
        self._edited()
        return j

    def _set_slide(self, key, value):
        if self.app.story.set_slide(self.app.cur, key, value):
            if key == "bg" and isinstance(value, int):
                if value in self.recent:
                    self.recent.remove(value)
                self.recent.insert(0, value)
                self.recent = self.recent[:4]
            self._edited()

    def _set(self, key, value):
        if self._obj() is None:
            return
        if self.app.story.set(self.app.cur, self.chosen, key, value):
            self._edited()

    # -- input --------------------------------------------------------------------------

    def handle_input(self, inp, k):
        """The editor's keys before the page's: Present, the sorter's, the
        slide's while its pasteboard has focus (or its words are written),
        undo and stepping the slides while the parts have the keys. False:
        the page's."""
        app = self.app
        if self.menu is not None:
            return False
        if self.writing:
            return self._slide_keys(inp, k)
        if k in (ord("p"), ord("P")):
            app._start(app.cur)
            return True
        if app.page == "deck":
            if k in (26, 25):
                self._undo(redo=k == 25)
                return True
            return self._deck_keys(k)
        if app.page != "slide":
            return False
        if self.on_slide:
            return self._slide_keys(inp, k)
        if k in (26, 25):
            self._undo(redo=k == 25)
        elif k in (ord("y"), ord("Y")):
            self.on_slide = True
        elif k in (ord("."), ord(",")):
            self._goto(app.cur + (1 if k == ord(".") else -1))
        else:
            return False
        return True

    def _deck_keys(self, k):
        app = self.app
        st = app.story
        i = self.deck_focus()
        if i is None:
            if k in (ord("n"), ord("N")):
                self._new_slide(len(st.slides) - 1)
                return True
            return False
        if k in (ord("n"), ord("N")):
            self._new_slide(i)
        elif k in (ord("["), ord("]")):
            j = st.move_slide(i, -1 if k == ord("[") else 1)
            if j is not None:
                app.cur = j
                app._focus = card_id(j)
                self._edited()
        elif k == 4:
            j = st.duplicate_slide(i)
            if j is None:
                app._say("A story holds %d slides" % D.MAX_SLIDES, "warn")
            else:
                app._focus = card_id(j)
                self._edited()
        elif k == 127:
            self._delete_slide(i)
        elif k in (ord("m"), ord("M")):
            app.cur = i
            self.menu = "slide"
            app.owe()
        else:
            return False
        return True

    def _delete_slide(self, i):
        app = self.app
        j = app.story.delete_slide(i)
        if j is None:
            app._say("A story keeps one slide", "warn")
            return
        app.cur = j
        app._focus = card_id(j)
        app._say("Slide deleted" + D_DOT() + "Ctrl+Z brings it back", "trash")
        self._edited()

    def _slide_keys(self, inp, k):
        app = self.app
        if self.writing:
            if k:
                self._type(k)
            return True
        step = self.step
        if inp.steps("left"):
            self._move(-step, 0)
        elif inp.steps("right"):
            self._move(step, 0)
        elif inp.steps("up"):
            self._move(0, -step)
        elif inp.steps("down"):
            self._move(0, step)
        elif inp.pressed("a") or k in (13, 10):
            o = self._obj()
            if o is not None and o["type"] == "picture" and o["image"] is None:
                self._open_pictures("add")
            else:
                self._write()
        elif k == 9:
            n = len(self._slide_doc()["objects"])
            if n:
                self._choose(0 if self.chosen is None else (self.chosen + 1) % n)
        elif inp.pressed("b") or k == 27:
            if self.chosen is not None:
                self._choose(None)
            else:
                self.on_slide = False
                app._damage.all()
        elif k in (ord("t"), ord("T")):
            self._add("text")
        elif k in (ord("s"), ord("S")):
            self._add("shape")
        elif k in (ord("i"), ord("I")):
            self._open_pictures("add")
        elif k in (ord("b"), ord("B")):
            self._open_pictures("bg")
        elif k in (ord("y"), ord("Y")):
            self.on_slide = False
            app._damage.all()
        elif k in (ord("m"), ord("M")):
            self.menu = "more"
            app._damage.all()
        elif k in (ord("r"), ord("R")):
            self.resizing = not self.resizing and self.chosen is not None
            app._damage.all()
        elif k in (ord("+"), ord("=")) and self._obj() is not None:
            self._resize_by(self._obj(), 8, 8, keep=True)
        elif k in (ord("-"), ord("_")) and self._obj() is not None:
            self._resize_by(self._obj(), -8, -8, keep=True)
        elif k in (ord("g"), ord("G")):
            self.step = GRID if self.step == STEP else STEP
            app._damage.all()
        elif k == ord("]"):
            self._front()
        elif k == ord("["):
            self._front(back=True)
        elif k == 3:
            self._copy()
        elif k == 22:
            self._paste()
        elif k == 4:
            self._duplicate()
        elif k in (127, 8):
            self._delete()
        elif k == 26:
            self._undo()
        elif k == 25:
            self._undo(redo=True)
        elif k == ord("."):
            self._goto(app.cur + 1)
        elif k == ord(","):
            self._goto(app.cur - 1)
        elif k in (ord("n"), ord("N")):
            self._new_slide(app.cur)
            self.chosen = None
        return True

    # -- a pointer -----------------------------------------------------------------------

    def handle_pointer(self, px, py, click, down):
        """A pointer sample on the board, in its coordinates: True where the
        slide took it."""
        app = self.app
        if app.page != "slide" or self.menu is not None:
            return False
        sx, sy, sw, sh = self.slide
        inside = sx <= px < sx + sw and sy <= py < sy + sh
        now = _ticks_ms()
        if click:
            if not inside and self._handle_at(px, py) is None:
                return False
            self.on_slide = True
            twice = self._click is not None and _ticks_diff(now, self._click[0]) < DOUBLE_MS \
                and abs(px - self._click[1]) < 6 and abs(py - self._click[2]) < 6
            self._click = (now, px, py)
            self._press = (now, px, py)
            h = self._handle_at(px, py)
            if h is not None:
                o = self._obj()
                self.drag = ("size", h, px, py, D.copy(o))
                return True
            j = self._hit(px, py)
            if twice and j is not None and j == self.chosen:
                self._write()
                return True
            if j is None:
                self._choose(None)
                self.drag = None
                return True
            if j == self.chosen and not twice:
                under = self._hit(px, py, below=j)
                self.drag = ("maybe", j, px, py, under)
            else:
                self._choose(j)
                self.drag = ("move", j, px, py, D.copy(self._obj()))
            return True
        if self.drag is None:
            return False
        if down:
            if self._press is not None and _ticks_diff(now, self._press[0]) > LONG_MS \
                    and abs(px - self._press[1]) < 6 and abs(py - self._press[2]) < 6 \
                    and ui.input_kind() == "touch":
                self._press = None
                self.drag = None
                self.menu = "more"
                app._damage.all()
                return True
            self._drag_to(px, py)
            return True
        # released
        d = self.drag
        self.drag = None
        self._press = None
        self.guides = ()
        self.say = ""
        if d[0] == "maybe":
            if d[4] is not None:
                self._choose(d[4])      # a tap again: the one beneath
        app.story.end()
        app._damage.all()
        return True

    def _hit(self, px, py, below=None):
        """The object under the screen point, topmost first (under `below`)."""
        objs = self._slide_doc()["objects"]
        top = len(objs) - 1 if below is None else below - 1
        for j in range(top, -1, -1):
            x, y, w, h = self._to_screen(self._bounds(objs[j]))
            if x <= px < x + max(w, 4) and y <= py < y + max(h, 4):
                return j
        return None

    def _handles(self, rect):
        x, y, w, h = rect
        return ((x, y), (x + w // 2, y), (x + w, y), (x + w, y + h // 2), (x + w, y + h),
                (x + w // 2, y + h), (x, y + h), (x, y + h // 2))

    def _handle_at(self, px, py):
        o = self._obj()
        if o is None:
            return None
        reach = (HANDLE_TOUCH if ui.input_kind() == "touch" else HANDLE_POINTER) // 2
        for k, (hx, hy) in enumerate(self._handles(self._to_screen(self._bounds(o)))):
            if abs(px - hx) <= reach and abs(py - hy) <= reach:
                return k
        return None

    def _drag_to(self, px, py):
        app = self.app
        n, d = self.zoom
        kind = self.drag[0]
        if kind == "maybe":
            if abs(px - self.drag[2]) < 4 and abs(py - self.drag[3]) < 4:
                return
            j = self.drag[1]
            self.drag = ("move", j, self.drag[2], self.drag[3], D.copy(self._obj()))
            kind = "move"
        _k, j, x0, y0, was = self.drag
        dx = (px - x0) * d // n
        dy = (py - y0) * d // n
        st = app.story
        if kind == "move":
            b = self._bounds(was)
            nx, ny = was["x"] + dx, was["y"] + dy
            nx, ny = self._snapped(nx, ny, b[2], b[3], j)
            st.place(app.cur, j, nx, ny)
        else:
            self._size_drag(was, j, dx, dy)
        app._damage.all()

    def _size_drag(self, was, j, dx, dy):
        app = self.app
        st = app.story
        h = self.drag[1]
        x, y = was["x"], was["y"]
        if was["type"] == "picture" and was["image"] is not None:
            w0, h0 = self._bounds(was)[2:]
            grow = dx if h in (2, 3, 4) else -dx
            target = max(8, w0 + grow)
            src = self._size_of(was["image"])[0] or 1
            best = min(D.SCALES, key=lambda s: abs(src * s - target))
            st.set(app.cur, j, "scale", best, hold=True)
            return
        w = was.get("w", 0)
        hh = was.get("h", 0)
        if h in (0, 6, 7):
            x, w = was["x"] + dx, w - dx
        if h in (2, 3, 4):
            w = w + dx
        if was["type"] != "text":
            if h in (0, 1, 2):
                y, hh = was["y"] + dy, hh - dy
            if h in (4, 5, 6):
                hh = hh + dy
        w = max(16, w)
        hh = max(8, hh)
        st.place(app.cur, j, x, y, w, None if was["type"] == "text" else hh)

    def _snapped(self, x, y, w, h, j):
        """(x, y) moved onto a guide within the snap's reach: the slide's
        edges and centre lines, the others' edges and centres."""
        self.guides = ()
        self.say = ""
        if not self.snap:
            return x, y
        n, d = self.zoom
        reach = (SNAP_TOUCH if ui.input_kind() == "touch" else SNAP_POINTER) * d // n
        xs = [(0, "the slide's edge"), (D.SW // 2, "the slide's middle"),
              (D.SW, "the slide's edge")]
        ys = [(0, "the slide's edge"), (D.SH // 2, "the slide's middle"),
              (D.SH, "the slide's edge")]
        objs = self._slide_doc()["objects"]
        for k, o in enumerate(objs):
            if k == j:
                continue
            b = self._bounds(o)
            name = self._name_of(o)
            xs += [(b[0], name), (b[0] + b[2] // 2, name), (b[0] + b[2], name)]
            ys += [(b[1], name), (b[1] + b[3] // 2, name), (b[1] + b[3], name)]
        guides = []
        said = []
        best = None
        for v, name in xs:
            for off in (0, w // 2, w):
                gap = v - (x + off)
                if abs(gap) <= reach and (best is None or abs(gap) < abs(best[0])):
                    best = (gap, v, name)
        if best is not None:
            x += best[0]
            guides.append(("v", best[1]))
            said.append(best[2])
        best = None
        for v, name in ys:
            for off in (0, h // 2, h):
                gap = v - (y + off)
                if abs(gap) <= reach and (best is None or abs(gap) < abs(best[0])):
                    best = (gap, v, name)
        if best is not None:
            y += best[0]
            guides.append(("h", best[1]))
            if best[2] not in said:
                said.append(best[2])
        self.guides = tuple(guides)
        if said:
            self.say = "moving: lined up with " + " and ".join(said)
        return x, y

    def _name_of(self, o):
        t = o["type"]
        if t == "picture":
            return "the picture" if o["image"] is None else "the " + o["image"]
        if t == "text":
            return "the words"
        return "the " + SHAPE_TITLES[D.SHAPES.index(o["shape"])].lower()

    # -- the slide on its pasteboard (the page's `board` canvas) --------------------------

    def fit(self, w, h):
        """The slide's rect on a pasteboard w x h: the largest edit zoom
        whose slide fits it with a margin, centred."""
        for n, d in EDIT_ZOOMS:
            sw, sh = R.size(n, d)
            if sw + 12 <= w and sh + 12 <= h:
                break
        self.zoom = (n, d)
        self.slide = ((w - sw) // 2, (h - sh) // 2, sw, sh)

    def draw_board(self, cv, x, y, w, h, th):
        """The pasteboard: the slide at its edit zoom on a rounded ground,
        its edge, the grid while G steps it, the chosen object's outline
        and handles (or the caret while writing), the snap guides."""
        app = self.app
        st = app.story
        if st is None:
            return
        if self.slide[2] == 0 or self._board != (w, h):
            self._board = (w, h)
            self.fit(w, h)
        cv.rrect(x, y, w, h, 10, th["surface_alt"])
        sx, sy, sw, sh = self.slide
        sx, sy = x + sx, y + sy
        key = ("edit", st.gen, app.cur, sw, sh)
        app.frames.place(cv, key, st.slides[app.cur], sx, sy, sw, sh, edit=True)
        cv.rectb(sx - 1, sy - 1, sw + 2, sh + 2, th["edge"])
        on = self.on_slide
        if self.step == GRID and on:
            self._grid(cv, sx, sy, sw, sh)
        self._chosen(cv, th, x, y, on)
        for g in self.guides:
            self._guide(cv, g, sx, sy, sw, sh)

    def _grid(self, cv, sx, sy, sw, sh):
        n, d = self.zoom
        step = GRID * 4
        for gx in range(step, D.SW, step):
            cv.fill565(sx + gx * n // d, sy, 1, sh, 0xC618)
        for gy in range(step, D.SH, step):
            cv.fill565(sx, sy + gy * n // d, sw, 1, 0xC618)

    def _chosen(self, cv, th, ox, oy, on):
        """The chosen object's outline in its dark keyline, and its handles
        (8 x 8, white in a dark border) while the slide has the keys; while
        writing, the caret."""
        o = self._obj()
        if o is None:
            return
        x, y, w, h = self._to_screen(self._bounds(o))
        x, y = x + ox, y + oy
        cv.rectb(x - 2, y - 2, w + 4, h + 4, 0)
        cv.rectb(x - 1, y - 1, w + 2, h + 2, th["value"])
        cv.rectb(x, y, w, h, th["value"])
        if self.writing:
            self._caret(cv, o, th, ox, oy)
        elif not on:
            return
        hs = HANDLE
        for hx, hy in self._handles((x, y, w, h)):
            cv.rect(hx - hs // 2, hy - hs // 2, hs, hs, 0)
            cv.rect(hx - hs // 2 + 1, hy - hs // 2 + 1, hs - 2, hs - 2, 7)

    def _caret(self, cv, o, th, ox, oy):
        n, d = self.zoom
        rend = self.app.renderer
        if o["type"] == "text":
            bx, by, bw = o["x"], o["y"], o["w"]
            top = by * 64
        else:
            bx, by, bw, bh = R._body_box(o)
            lines = rend.words.lines(cv, o["text"], o["font"], o["size"], bw)
            top = by * 64 + (bh * 64 - len(lines) * R.line_h(o["size"])) // 2
        lines = rend.words.lines(cv, o["text"], o["font"], o["size"], bw)
        last, lw = lines[-1]
        if o["align"] == "centre":
            dx = (bw * 64 - lw) // 2
        elif o["align"] == "right":
            dx = bw * 64 - lw
        else:
            dx = 0
        cx = ox + self.slide[0] + (bx * 64 + dx + lw) * n // d // 64 + 2
        cy = oy + self.slide[1] + (top + (len(lines) - 1) * R.line_h(o["size"])) * n // d // 64
        cv.rect(cx, cy + o["size"] * n // d // 8, 2, o["size"] * n // d, th["value"])

    def _guide(self, cv, g, sx, sy, sw, sh):
        """A snap guide across the slide: indigo dashes on a white keyline."""
        n, d = self.zoom
        if g[0] == "v":
            gx = sx + g[1] * n // d
            cv.fill565(gx - 1, sy, 3, sh, WHITE_565)
            for t in range(0, sh, 8):
                cv.fill565(gx, sy + t, 1, 5, GUIDE_565)
        else:
            gy = sy + g[1] * n // d
            cv.fill565(sx, gy - 1, sw, 3, WHITE_565)
            for t in range(0, sw, 8):
                cv.fill565(sx + t, gy, 5, 1, GUIDE_565)

    def board_view(self):
        """What the board shows, as one text: the page reads it (the
        board canvas's reads=)."""
        st = self.app.story
        return "%s %d %d %r %d %d %d %d %r" % (
            st.name if st is not None else "", st.gen if st is not None else 0, self.app.cur,
            self.chosen, self.writing, self.step, self.on_slide, self.resizing, self.guides)

    # -- the words the page shows ----------------------------------------------------------

    def deck_status(self, i):
        """The sorter's band: slide `i` (the focused card's), its words, the zoom."""
        st = self.app.story
        if i is None or i >= len(st.slides):
            return ""
        out = "Slide %d" % (i + 1)
        t = self._slide_words(st.slides[i])
        if t:
            out += app_dot() + t
        return out + app_dot() + "the slides at " + _zw(1, 4)

    def _slide_words(self, s):
        for o in s["objects"]:
            if o["type"] in ("text", "shape") and o["text"]:
                return o["text"]
        return ""

    def slide_status(self):
        app = self.app
        status = "Slide %d of %d" % (app.cur + 1, len(app.story.slides))
        o = self._obj()
        if self.writing and o is not None:
            status += app_dot() + "writing" + app_dot() + "%d of %d letters" % (
                len(o["text"]), D.MAX_TEXT)
        elif self.say:
            status += app_dot() + self.say
        elif o is None:
            status += app_dot() + "nothing chosen"
        else:
            status += app_dot() + self._describe(o)
        n, d = self.zoom
        return status + app_dot() + "shown at " + _zw(n, d)

    def slide_hints(self):
        return ("back", "Done") if self.writing else ("Ctrl D", "Duplicate", "Del", "Delete")

    def pics_status(self, name):
        if name is None:
            return ""
        where = ("the background of slide %d" if self.pic_mode == "bg"
                 else "it goes on slide %d, chosen") % (self.app.cur + 1)
        return _shown(name) + app_dot() + where

    def _describe(self, o):
        t = o["type"]
        if t == "picture":
            if o["image"] is None:
                return "a place for a picture"
            s = {0.5: "half its size", 1: "its own size", 2: "twice its size"}.get(
                o["scale"], "%d times its size" % o["scale"])
            return _shown(o["image"]) + ", " + s + (", its corner colour clear"
                                                            if o["clear"] else "")
        if t == "text":
            return "words in " + D.FONT_NAMES[D.FONTS.index(o["font"])] + " " + str(o["size"])
        return SHAPE_TITLES[D.SHAPES.index(o["shape"])].lower()

    # -- the menus' picks -------------------------------------------------------------------

    def add_pick(self, a):
        """The Add menu's: a text box, a shape, a picture, a background."""
        self.menu = None
        if a == "text":
            self._add("text")
        elif a == "shape":
            self._add("shape")
        else:
            self._open_pictures("add" if a == "pic" else "bg")

    def layout_pick(self, k):
        """The layouts menu's: a new slide of layout `k` after the focused
        slide (the last where none is)."""
        app = self.app
        self.menu = None
        i = self.deck_focus()
        self._new_slide(len(app.story.slides) - 1 if i is None else i, D.LAYOUTS[k])

    def more_pick(self, a):
        self.menu = None
        if a == "front":
            self._front()
        elif a == "back":
            self._front(back=True)
        elif a == "copy":
            self._copy()
        elif a == "paste":
            self._paste()
        elif a == "centre":
            self._centre()
        elif a == "snap":
            self._toggle_snap()
        elif a == "dup":
            self._duplicate()
        else:
            self._delete()

    def slide_pick(self, a):
        """The slide menu's: its transition steps (the menu stays), a copy,
        a move, a delete."""
        app = self.app
        self.menu = None
        if a == "trans":
            t = D.TRANSITIONS.index(app.story.slides[app.cur]["transition"])
            self._set_slide("transition", D.TRANSITIONS[(t + 1) % 3])
            self.menu = "slide"
        elif a == "dup":
            j = app.story.duplicate_slide(app.cur)
            if j is None:
                app._say("A story holds %d slides" % D.MAX_SLIDES, "warn")
            else:
                app._focus = card_id(j)
                self._edited()
        elif a in ("earlier", "later"):
            j = app.story.move_slide(app.cur, -1 if a == "earlier" else 1)
            if j is not None:
                app.cur = j
                app._focus = card_id(j)
                self._edited()
        else:
            self._delete_slide(app.cur)

    def colours(self, key, none):
        """The colours menu for `key` (the slide's "bg", else the chosen
        object's), with None where `none`."""
        self.menu = "colours"
        self.colour_key = (key, none)
        self.app._damage.all()

    def colour_now(self):
        """The colour the colours menu shows chosen: an index, -1 none."""
        key, _none = self.colour_key or ("bg", False)
        if key == "bg":
            cur = self._slide_doc()["bg"]
        else:
            o = self._obj()
            cur = o.get(key) if o is not None else None
        return cur if isinstance(cur, int) else -1

    def colour_pick(self, c):
        """Colour `c` (-1 None) for what the colours menu sets."""
        key, _none = self.colour_key or ("bg", False)
        self.menu = None
        if key == "bg":
            self._set_slide("bg", c)
        else:
            self._set(key, None if c < 0 else c)

    def _toggle_snap(self):
        self.snap = not self.snap
        self.app._say("Snap " + ("on" if self.snap else "off"), "check")


    # -- Add a picture ---------------------------------------------------------------------------

    def _open_pictures(self, mode):
        app = self.app
        self.stop_writing()
        self.pic_mode = mode
        self.pics = None
        app.page = "pictures"
        app.owe()

    def _scan_pictures(self, each=None):
        """My Art's drawings, [(name, w, h)], each that reads handed to
        `each(name, blob)` as well."""
        files = self.app._files
        names, err = files.list("drawings")
        out = []
        for name in names or ():
            blob, err = files.load("drawings", name)
            size = R._blob_size(blob) if blob else None
            if size is not None:
                out.append((name, size[0], size[1]))
                if each is not None:
                    each(name, blob)
        self.pics = out

    def _place(self, pick):
        """Copy drawing `pick` into the story and put it on the slide (or
        behind it), chosen; a layout's next empty frame is chosen after."""
        app = self.app
        st = app.story
        files = app._files
        name, pw, ph = pick
        blob, err = files.load("drawings", name)
        if not blob:
            app._say("That drawing can't be read", "warn")
            return
        used = st.images()
        if len(used) >= D.MAX_IMAGES:
            app._say("A story holds %d pictures" % D.MAX_IMAGES, "warn")
            return
        img = self._image_name(name, used)
        _v, err = files.save(KIND, st.name + "/" + img + ".moyimg", blob)
        if err is None:
            err = self._bake_half(st.name, img, blob)
        if err is not None:
            app._say("This picture can't be saved here", "warn")
            return
        self.added.append(img)
        app.images.forget(img)
        app.page = "slide"
        if self.pic_mode == "bg":
            self._set_slide("bg", img)
            app._damage.all()
            return
        o = self._obj()
        i = app.cur
        if o is not None and o["type"] == "picture" and o["image"] is None:
            scale = 0.5
            for s in D.SCALES:
                if pw * s <= o["w"] and ph * s <= o["h"]:
                    scale = s
            new = D.picture_obj(img, o["x"], o["y"], scale, False, o["step"])
            j = st.add(i, new, at=self.chosen)
        else:
            scale = 0.5 if pw > 512 or ph > 300 else 1
            new = D.picture_obj(img, (D.SW - int(pw * scale)) // 2,
                                (D.SH - int(ph * scale)) // 2, scale)
            j = st.add(i, new)
        if j is None:
            app._say("A slide holds %d things" % D.MAX_OBJECTS, "warn")
            return
        self.chosen = j
        objs = st.objects(i)
        for k in range(len(objs)):
            o = objs[(j + 1 + k) % len(objs)]
            if o["type"] == "picture" and o["image"] is None:
                self.chosen = (j + 1 + k) % len(objs)
                break
        self.on_slide = True
        self._edited()

    def _image_name(self, name, used):
        base = "".join(c for c in name.lower() if c in "abcdefghijklmnopqrstuvwxyz0123456789_")
        base = (base or "pic")[:18]
        cand, n = base, 2
        while cand in used or cand in self.added:
            cand = "%s_%d" % (base, n)
            n += 1
        return cand

    def _bake_half(self, item, img, blob):
        """The picture's half, baked so a 1 px line survives (story_render.half)."""
        files = self.app._files
        got = files.decode_image(blob)
        if got is None:
            return "unreadable"
        w, h, pix = got
        half = R.half(pix, w, h)
        hb = files.encode_image(max(1, w // 2), max(1, h // 2), half)
        _v, err = files.save(KIND, item + "/" + img + "_h.moyimg", hb)
        return err


def _shown(name):
    """A file's name as words: "fish_tank" is "Fish tank"."""
    t = name.replace("_", " ")
    return t[:1].upper() + t[1:]


def card_id(i):
    """Slide `i`'s card in the sorter, as the page's focus names it."""
    return "%d/edit_slide" % i


def app_dot():
    return " · " if ui.has_symbols() else " - "


def D_DOT():
    return app_dot()


def _zw(n, d):
    from storybook_app import zoom_word
    return zoom_word(n, d)
