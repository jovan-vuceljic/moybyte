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
    ns["__name__"] = "cart:" + str(cart.get("id") or cart.get("title") or "")


class _Damage:
    """The engine's `damage.all()`: the run owes a frame."""

    def __init__(self, pl):
        self.pl = pl

    def all(self):
        self.pl.face.owe()


class CartTree:
    """The engine of one Python cart's pages (above), held by its Player as
    `player.tree`; `update` and `draw` are the run's frame."""

    def __init__(self, pl, ns):
        import uitree as _S
        import uitree_app as _app
        decl = _S.decl_of(ns["__name__"])
        if decl.app is None:
            raise _S.UIError("D04", "the app has no ui.app declaration", where=(ns["__name__"], 0),
                             fix='ui.app("Title", icon="...") after ui.state(...)')
        build = ns.get("build")
        if not callable(build):
            raise _S.UIError("P01", "the app has no root page", where=(ns["__name__"], 0),
                             fix="def build(): with ui.page(...): ... -- the page the app opens on")
        editor = False
        for t in decl.state._t.values():
            if isinstance(t, _S.Doc):
                editor = True
        self.pl = pl
        face = pl.face
        self.engine = eng = _app._engine_class(True, editor)(build, face.host(), _Damage(pl))
        if editor:
            eng.pointer_down = self._down
        self.dt = 0.0
        eng.open()

    def _down(self):
        return bool(getattr(self.pl.ws.pointer, "down", False))

    def update(self, dt):
        """The frame's input into the engine: a declared action's key, a
        role's, the text editor's typing. A deaf run's keys are another
        window's."""
        self.dt = dt
        pl = self.pl
        if not (pl.deaf or pl.detached):
            self.engine.keys(pl.ws.input, False)

    def draw(self):
        """The page, painted into the app's content rect in the pass the
        run's frame began."""
        pl = self.pl
        cv = pl.run.canvas
        desk = pl.run.app_full_canvas and _lb.metric_class() == _lb.DESK
        self.engine.paint(self.dt, cv, pl.ws.theme_colors, pl.face.ui_room(), desk)

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
