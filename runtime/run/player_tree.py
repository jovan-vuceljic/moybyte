"""A Python app cart's pages on the UI tree engine: the cart that declares
the extension `moybyte.uitree` gets `uitree` as its `ui` and the name
`cart:<id>` its declarations are made under, and its pages run on the
engine the console's own apps run on (`uitree_app`), hosted on the run's
app host (`AppFace`) the way a hosted page is: the Player's frame begins
the pass over the run's input, and the engine paints the page into the
app's content rect.

The cart declares its state, its `ui.app(...)` and its actions at the top
level, and names its root page `build`. Its `_update` and `_draw` are the
engine's: a cart defines neither. A cart whose state holds a `ui.doc`
(a text editor's document) runs on the Editor's kinds
(`uitree_c.CEditorEngine`).

Canonical home is runtime/; build.sh stages a copy into the firmware
modules/ tree, as it does player.py. The engine is imported at a tree
cart's start, never at the Player's.
"""

import layout_base as _lb
import ui_draw as _ui_draw

EXT = "moybyte.uitree"


def wants(cart):
    """Whether `cart` is a Python cart on the UI tree API."""
    return (cart.get("runtime", "python") == "python"
            and EXT in (cart.get("extensions") or ()))


def namespace(ns, cart):
    """Give the cart's namespace the UI tree API as its `ui`, and the module
    name its declarations are made under."""
    import uitree
    ns["ui"] = uitree
    ns["__name__"] = name = "cart:" + str(cart.get("id") or cart.get("title") or "")
    uitree.named(name)          # a board's frames name no module: its declarations, made under it


class _Damage:
    """The engine's `damage.all()`: the run owes a frame."""

    def __init__(self, pl):
        self.pl = pl

    def all(self):
        self.pl.face.owe()


class CartTree:
    """The engine of one Python cart's pages (above), held by its Player as
    `player.tree`: `input` and `aim` begin the run's frame (`AppFace.begin`),
    `update` and `draw` are its update and draw."""

    def __init__(self, pl, ns):
        import uitree as _S
        import uitree_app as _app
        _S.named(None)
        decl = _S.decl_of(ns["__name__"])
        if decl.app is None:
            raise _S.UIError("D04", "the app has no ui.app declaration", where=(ns["__name__"], 0),
                             fix='ui.app("Title", icon="...") after ui.state(...)')
        build = ns.get("build")
        if not callable(build):
            raise _S.UIError("P01", "the app has no root page", where=(ns["__name__"], 0),
                             fix="def build(): with ui.page(...): ... -- the page the app opens on")
        docs, rest = [], []
        for k, t in decl.state._t.items():
            (docs if isinstance(t, _S.Doc) else rest).append(k)
        editor = bool(docs)
        self.pl = pl
        self.decl = decl
        face = pl.face
        self._host = face.host()
        self.engine = eng = _app._engine_class(True, editor)(build, self._host, _Damage(pl), gen=True)
        self.editor = editor
        self._docs = tuple(docs)    # the text editors' keys, in a frame's walk without an iterator
        self._rest = tuple(rest)    # every other state's key: the page's shape and words
        self._left = [0] * len(docs)
        self._ed = [None] * len(docs)   # each text editor's document's editor the last frame drew
        self._row = [-1] * len(docs)    # ...its caret
        self._col = [-1] * len(docs)
        self._sig = -1              # the sum of the other states' versions the last frame drew
        if editor:
            eng.pointer_down = self._down
        self.dt = 0.0
        self._held = None           # the text editor a press placed the caret in, until its release
        eng.open()
        pl.ui[0] = self._host.ctx   # the open's fresh context: the run's frame is its

    def _down(self):
        return bool(getattr(self.pl.ws.pointer, "down", False))

    def update(self, dt):
        """The run's update: the engine's time step (the input went in
        before the frame began, `input`)."""
        self.dt = dt

    def input(self):
        """The frame's input into the engine, before the run's frame
        begins (`AppFace.begin`), so what it changes is the frame's to plan:
        a declared action's key, a role's, the text editor's typing, and a
        press in a text editor, which places its caret (a drag after it
        extends the selection in select mode; the view's own drag scrolls
        it). A deaf run's keys are another window's."""
        pl = self.pl
        if pl.deaf or pl.detached:
            return
        eng = self.engine
        eng.keys(pl.ws.input, False)
        if self.editor:
            gp = getattr(pl.ws.input, "game_pointer", None)    # a frame with no pointer published has none
            if gp is not None and (gp[2] or self._held is not None):
                self._text_pointer(gp[0], gp[1], gp[2], gp[3])

    def _text_pointer(self, px, py, click, down):
        eng = self.engine
        if click:
            self._held = None
            if eng.popover_shown() or eng.dialog_shown():
                return
            docs = self._docs
            for i in range(len(docs)):
                key = docs[i]
                got = _ui_draw.text_at(self._host, key, px, py) if key in eng.views else None
                if got is not None:
                    self._held = key
                    self._place(key, got, False)
                    return
            return
        key = self._held
        if not down:
            self._held = None
            return
        doc = eng.s._v[key]
        if doc.ed.select_sticky:
            got = _ui_draw.text_at(self._host, key, px, py)
            if got is not None:
                self._place(key, got, True)

    def _place(self, key, cell, select):
        eng = self.engine
        doc = eng.s._v[key]
        ed = doc.ed
        if cell[0] >= len(ed.lines):
            return
        if not select and ed.select_sticky:
            doc.place(cell[0] + 1, cell[1] + 1)
            ed.begin_select()       # select mode: a fresh press anchors a fresh range
        else:
            doc.place(cell[0] + 1, cell[1] + 1, select)
        eng.s._ver[key] += 1
        self.pl.face.owe()

    def draw(self):
        """The page, painted into the app's content rect in the pass the
        run's frame began; an editor handle a text editor adopted gets its
        frame (`EditorHandle.tick`: its idle save)."""
        pl = self.pl
        cv = pl.run.canvas
        desk = pl.run.app_full_canvas and _lb.metric_class() == _lb.DESK
        self.engine.paint(self.dt, cv, pl.ws.theme_colors, pl.face.ui_room(), desk)
        eds = pl.editors
        for i in range(len(eds)):
            if eds[i].live:
                eds[i].tick()

    def typing(self):
        """Whether a text editor the last frame drew holds the keys, no
        dialog or popover over it: the run takes typed bytes, and no stop
        of its page holds focus (`AppFace.begin`), so a key is the text's."""
        if not self.editor:
            return False
        eng = self.engine
        if eng.dialog_shown() or eng.popover_shown():
            return False
        docs = self._docs
        for i in range(len(docs)):
            if eng.te_drawn(docs[i]):
                return True
        return False

    def aim(self, host, over):
        """Before `host` begins the frame: where a text editor's editor moved
        its top line since the view last drew (a key, a typed line, Go to),
        the view shows that line first (`ui_draw.text_aim`); a wrapped
        view's rows are its own, so where its caret moved (a key, an edit, a
        tap) it moves only as far as it needs to show the caret's row
        (`ui_draw.text_reveal`). The move is the frame's shift. A caret left
        alone asks for nothing, so a drag or a fling takes the view anywhere
        and it stays there. A document just adopted shows from its top. Where a state but a document moved since the
        last frame (a page, a switch's case, a dialog, a label's words), or
        a text editor's columns scrolled across, or rect
        `over` (x, y, w, h; w 0 none) was drawn over the view after the last
        pass (`AppFace.overdrew`), the frame draws whole. The engine plans
        the rest of the page's frame, as it does a hosted page's."""
        eng = self.engine
        ver = eng.s._ver
        rest = self._rest
        sig = 0
        for i in range(len(rest)):
            sig += ver.get(rest[i], 0)
        if sig != self._sig:
            self._sig = sig
            host.whole()            # the page's shape or words may have moved
            return
        docs = self._docs
        for i in range(len(docs)):
            key = docs[i]
            v = eng.views.get(key)
            if v is None or not eng.te_drawn(key):
                continue
            doc = eng.s._v[key]
            ed = doc.ed
            if ed is not self._ed[i]:
                # a document adopted: its view from its top line
                self._ed[i] = ed
                self._row[i] = ed.row
                self._col[i] = ed.col
                _ui_draw.text_aim(host, key, ed.top, len(ed.lines))
                host.whole()
            elif not doc.wrap:
                if ed.top != v[1]:
                    _ui_draw.text_aim(host, key, ed.top, len(ed.lines))
            elif ed.row != self._row[i] or ed.col != self._col[i]:
                self._row[i] = ed.row
                self._col[i] = ed.col
                _ui_draw.text_reveal(host, key, ed.lines, ed.row, ed.col)
            if not doc.wrap and ed.left != self._left[i]:     # wrapped lines never pan
                self._left[i] = ed.left
                host.whole()
            r = v[0]
            if (over[2] and over[0] < r[0] + r[2] and r[0] < over[0] + over[2]
                    and over[1] < r[1] + r[3] and r[1] < over[1] + over[3]):
                host.whole()

    def act(self, name, *args):
        """Run the cart's declared action or hook `name` now, as one commit
        (a host's or a test's way in, as a key or a tap is the user's)."""
        eng = self.engine
        eng.run_action(eng.actions[name], args, "host")
        self.pl.face.owe()

    def back(self, take):
        """The host's back into the app (`take`): a dialog, a popover or a
        page above the first is left, or the app's back action runs, True;
        False where it has none, and the host leaves the app. Without
        `take`, whether it has a view of its own open."""
        eng = self.engine
        if take:
            return bool(eng.back())
        return bool(eng.has_page()) or eng.popover_key() is not None

    def close(self):
        """The run ends: every drawn commit field's draft is written, the
        engine's store let go."""
        eng = self.engine
        eng.leave()
        eng.forget()
        import uitree
        uitree.forget(self.decl)
