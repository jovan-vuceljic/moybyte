# Map (grep -n a name to jump there):
#   EditorDesk              the desk Editor: a workspace of panes under the app's row
#   EditorDesk.active       whether the Editor shows workspaces here
#   EditorDesk.switch       change workspace, committing only dirty panes
#   EditorDesk.focus_pane   move the keys to a pane, committing nothing
#   EditorDesk.draw         ground, cards, each pane's content, headers, dividers
#   EditorDesk._tab_pane    an Editor tab drawn in a pane through a viewport
#   EditorDesk._game        the Run slot: the game's frame at a whole scale
#   EditorDesk.part         a pane of the desk's own as a page (editor_parts.PartHost)
#   EditorDesk.handle_input  the workspace chords, then the focused pane's keys
#   EditorDesk.handle_pointer  the row, the dividers, a pane's header and its content
"""The Editor on the desk (docs/media/look_2026-10/EDITOR_LAYOUT.md, concept
B, and MAXIMISE_VARIANTS.md's Resize): several of its parts at once, as five
workspaces whose dividers move: each a page of panes
(runtime/editors/editor_ui.py's `SPACES`, laid out by the Editor engine)
whose bodies this layer draws. The app's row is the band the bar lends the Editor, the head
row's desk case (runtime/editors/editor_ui.py): the workspaces, undo, redo
and Play.

A pane is a card on the Editor's ground with a 32 px header (its icon and
name, or its tabs, then its tools); the focused one takes the keys and
wears the `value` edge along its top. An Editor tab in a pane (Settings,
Code, Blocks, Sprite, Map, Scene, Sound) is that tab's own surface laid
out at the pane's size with no bar, drawn through a viewport on the
window's canvas, and its taps translated into it; the panes the desk adds
are the Run slot, drawn here, and a page each of its own (editor_part.py,
hosted by editor_parts.PartHost). Moving focus never commits; a
workspace switch commits the panes it leaves that are dirty, through
`EditorApp.commit_later`, as a tab switch does.

On a surface smaller than the workspace's least size (a doubled desk theme's
half-size surface) the focused pane stands alone over the panes area, as a
grown one does, and the keys move it to the next. On a handheld the
Editor is one tab at a time under its one bar (`EditorApp`)."""

import moybuf
import editor_heads as Heads
import editor_panes as P
import editor_parts as Parts
import view_host as _V
import layout_base as _lb
from layers import Layer
from ticks import _ticks_ms, _ticks_diff

from array import array

# The surface each Editor tab draws with and the attribute on it holding the
# layout its `relayout` builds (the window's layout context captures the same).
_OWNERS = {"cards": ("cards_layer", "layout"), "blocks": ("block_ui", "block_layout"),
           "paint": ("paint_layer", "layout"), "map": ("map_ui", "layout"),
           "scene": ("scene_ui", "layout"), "music": ("music_ui", "layout"),
           "theme_config": ("theme_config_layer", "layout")}

# The Editor's tabs (`EditorApp._offers` answers for these).
_OPENED = ("cards", "code", "blocks", "paint", "map", "scene", "music")

# The tabs whose pane layouts `warm_step` builds ahead: those `_pane_layout`
# knows how to lay out.
_OWNERS_OR_CODE = tuple(_OWNERS) + ("code",)

# The panes whose frames may be their own: a frame the engine plans as the
# pane's split frame draws it alone (`_split_frame`); the Sprite pane's while
# its pickers are up.
_OWN_FRAMES = ("blocks", "cards", "code", "theme_config", "map", "music", "paint")

# The panes whose text view moves its rows on a frame that draws the desk
# whole only because the buffer it paints lags outside the pane, where the
# WM says the buffer `shift_last` reads holds the page as the last draw left
# it: a text view's rows draw for more than their move.
_TEXT_PANES = ("code", "theme_config")

# The Editor tabs whose surface, drawn in a pane, fills the pane's whole body
# before anything else (Sprite and Map their page's ground, Scene its `body_fill`, Code its
# ground round the text view's rows, Settings its `ui.page`): their card is
# drawn down to the header only, its body never seen
# (tests/test_editor_desk.py holds it). The Sound pane's page is bare, on its
# card.
_FILLS_BODY = ("paint", "map", "scene", "code", "cards", "theme_config")

# Which workspace shows an Editor tab, for a tab opened from elsewhere (a
# crash's throw to Code, Files opening a sprite sheet).
_HOME = {"cards": "settings", "code": "code", "blocks": "code", "paint": "art",
         "map": "art", "scene": "world", "music": "sound",
         "theme_config": P.THEME}

# The tools a pane's header carries before its grow, right to left.
_HEAD_TOOLS = {"paint": (("rotate", "Rotate\tR", "rot"), ("flip", "Flip\tF", "fliph")),
               "map": (("search", "Zoom\tA", "map:zoom"), ("eraser", "Erase", "map:erase"),
                       ("select", "Select", "map:select"), ("bucket", "Fill", "map:flood"),
                       ("rect", "Box", "map:rect"), ("pencil", "Pen", "map:stamp")),
               "scene": (("search", "Zoom\tA", "scene:zoom"), ("check", "Snap", "scene:snap"),
                         ("trash", "Delete", "scene:delete"), ("to_back", "Back", "scene:back"),
                         ("to_front", "Front", "scene:front"), ("flip", "Flip", "scene:flip"))}

# The Code pane's more menu's rows: (icon, word, the Code tab's tool).
_CODE_MORE = (("select", "Select", "sel"), ("copy", "Copy\tCtrl+C", "copy"),
              ("cut", "Cut\tCtrl+X", "cut"), ("paste", "Paste\tCtrl+V", "paste"),
              ("indent", "Indent\tTab", "indent"), ("outdent", "Outdent", "outdent"),
              ("linenums", "Line numbers", "gutter"), ("code", "Complete", "auto"))



def _word(word, keys):
    """A tool's word for a menu row: its key after a tab where the hints
    name keys (a keyboard's), else the word alone."""
    return word if keys else word.split("\t")[0]


_TAB_PAD = 28               # a header tab's room beside its word
_TAB_LEAD = 12              # the tabs row's lead before its first tab (the desk's group pad)
LOUPE = 3                   # the Sheet's loupe: a held tile at 3x its 16 px
_DOUBLE_MS = 400            # a second press this soon on a header or handle
_FULL_MS = 1000

# The key event (native/moy_input/moy_input.h): the code in the low 16 bits,
# the modifiers above.
_MODS_AT = 16
_CTRL, _SHIFT, _ALT = 1, 2, 4
_F6 = 0x101 + 5
_LEFT, _RIGHT, _UP, _DOWN = 0x110, 0x111, 0x112, 0x113
_ENTERS = (10, 13)
_PAD_DIRS = (("left", -1, 0), ("right", 1, 0), ("up", 0, -1), ("down", 0, 1))
_NO_LAG = (0, 0, 0, 0)           # a split frame's target lagging nothing
_PB_MIDDLE = 2


class _Damage:
    """A workspace page's word that the desk owes a frame."""

    def __init__(self, ws):
        self.ws = ws

    def all(self):
        self.ws.mark_dirty()


class EditorDesk(Layer):
    """The desk Editor's content layer (the "menu" window's, while `active`)."""

    id = "editor_desk"

    def __init__(self, ws, host):
        self.ws = ws
        self._host = host("editor")
        self.key = "settings"           # the workspace shown
        self._focus = {}                # workspace -> the focused pane's index
        self._tabs = {}                 # pane -> its open tab's index
        self.grown = None               # the pane grown over the workspace
        self._pages = {}                # workspace -> its page (editor_ui.SPACES)
        self._placed = None             # the one on show placed: (panes, dividers)
        self._placed_for = (None, None, 0, True, 0, None)   # ...for (key, area, unit, game,
                                                            # focused pane, grown pane)
        self._lay = {}                  # (tab, w, h, fs, cs) -> the pane's layout
        self._drag = None               # a divider held: (path, i, axis, at, stop, live)
        self._on_div = False            # the pointer went down on a divider: the frame's
        self._heads = {}                # pane index -> its header's page host (`head`)
        self._head_down = None          # the pane whose header a press went down in
        self._head_due = False          # a header took input its next whole frame answers
        self._code_rows = (None, ())    # the Code more menu's rows, for the hints' kind
        self._press = None              # the pane a press went down in
        self._was_down = False          # the pointer was held at the sample before
        self._head_over = None          # (pane index, x, y) where a mouse over a header was last
        self._last = (None, 0)          # the last press: its target, when
        self._ev = 0                    # last frame's key event
        self._shown = None              # the workspace whose panes were built
        self._seen = None               # the Editor's tab as the desk last left it
        self._zoomed = None             # the cart the desk zooms were set for
        self._flash = None              # (pane, why): a divider stopped at its minimum
        self._sheet_page = 0
        self._loupe = None              # (tile, x, y): a press held on the Sheet
        self._still = None
        self.part_state = {}            # the parts' kept state (the palette's category, the
                                        # Reference's sound and map cell) and the more menus
        self._parts = {}                # part -> its page's host (`Parts.PAGES`)
        self._mid = None                # the middle button's last place, while held
        self._scale = 0                 # the Run slot's scale, last drawn
        self._still_at = None           # where the game stands on the surface
        self._picked = 0                # the sprite picked with no Sprite pane built
        self._was_playing = False
        self.paused = False             # the Run slot's pause: the run held, its still shown
        self._back_tab = {}             # a pane's tab before Play took it to Game
        self._fresh = 0                 # this frame's key event, where it is new
        self._tools_x = {}              # pane index -> its header tools' left edge
        self._warm = {}                 # sig -> placed, built ahead
        self._warm_for = None           # what the workspaces were warmed for
        self._warm_left = []            # ...and those still to warm
        self._warm_due = False          # a quiet frame has warming to do
        self.dt = 0
        # The shown protocol (docs/surface_model_v1.md §14.3): what the
        # buffer this draw goes into lags (`retained`), and what the draw
        # changed (`changed`). What the desk draws outside the pane the keys
        # reach is a function of `_surround`, its gen `_gen` (`_split_frame`).
        self._surround = None
        self._gen = 0
        self._changed = None
        self._acts = 0                  # input the desk took itself (a press, a chord)
        self._in_code = False           # this press went to the focused pane (its own frames)
        self._box = array("i", [0] * 4)
        # ...and while its focused pane is the Code tab (or theme Config), on
        # every frame: the WM's word for the buffer, the lag it named, what
        # the desk was a function of at the last code frame, and whether the
        # buffer `shift_last` reads holds the page as the last draw left it
        # (`vouched`: 2, 3 where the ring says the buffer this frame paints
        # holds it too, else 1, 0 untold).
        self._ret = array("i", [0] * 5)
        self._within = array("i", [0] * 4)   # what the pane drew inside alone
        self._moves = None              # the pane whose text view moves on a whole frame
        self._clip = None               # the rect a frame of the Sound pane's own is clipped to
        # the layout the desk drew in last: its window's, which the WM has
        # not installed yet where it asks HELD and takes_lag
        self._drew_in = None
        self._vouch = 0

    # -- where it applies -------------------------------------------------------

    def active(self):
        """Whether the Editor shows workspaces: a desk, and an open cart or a
        theme in the Editor's theme mode."""
        return _lb.metric_class() == _lb.DESK and (
            self.ws.cart is not None or self.ws.editor_app.theme is not None)

    def theme_shown(self, on):
        """The theme mode opened (`on`) or left: its one workspace, Config
        alone, else the workspace the cart had."""
        if on and self.key != P.THEME:
            self._was = self.key
            self.key = P.THEME
        elif not on and self.key == P.THEME:
            self.key = getattr(self, "_was", None) or "settings"
        else:
            return
        self.grown = None
        self._placed = None
        self._shown = None

    def _unit(self):
        return max(1, _lb.chrome_size(self.ws.look.effective_font_scale())
                   // _lb.render_scale())

    def _area(self):
        lay = self.ws.layout
        g = P.GUTTER * self._unit()
        return (lay.cx + g, lay.cy + g, lay.cw - 2 * g, lay.ch - 2 * g)

    def min_window(self):
        """The least window the workspace on show holds, at the font scale
        (as a registered app's minimum is): its panes' minimums, the gutters
        round them, the band and the window's strip."""
        mw, mh = self.minimum()
        u = self._unit()
        fs = max(1, self.ws.look.effective_font_scale())
        g = 2 * P.GUTTER * u
        band = _lb.bar_rows(self.ws.look.effective_chrome_scale())
        return (-(-(mw + g + 2) // fs), -(-(mh + g + band + 48 * u) // fs))

    def _blocks(self):
        cart = self.ws.cart
        return bool(cart is not None and cart.get("blocks") and self.ws.text.takes_blocks())

    def lacks(self):
        """The panes the open cart has not got: each whose Editor tab, or
        the tab it serves, the Editor does not offer it (`_offers`)."""
        offers = self.ws.editor_app._offers
        return tuple(c for c in P.CONTENTS
                     if P.tab_for(c) in _OPENED and not offers(P.tab_for(c)))

    def keys(self):
        """The workspace keys the open cart has, in the row's order."""
        return [k for k, _l, _i in self.ws.editor_app.workspaces()]

    def _page(self, key=None):
        """Workspace `key`'s page (editor_ui.SPACES): its panes, whose
        bodies this desk draws (`pane_body`)."""
        key = key or self.key
        page = self._pages.get(key)
        if page is None:
            import editor_ui
            import uitree_editor
            page = uitree_editor.page(editor_ui.SPACES[key], self._host, _Damage(self.ws))
            self._pages[key] = page
        return page

    def _sync(self, page, area, u):
        """What the workspace's shape and starting sizes follow, written
        into its page's state: the area (`big`, the 1024 arrangement; the
        right column 660 at 1240x760 units and over, its Run slot 512; the
        Sprite 330 where the area is 420 units tall, else 320) and the cart
        (its tabs, blocks, the Game while no window holds it)."""
        import editor_ui
        st = editor_ui.s
        page._bind()
        w, h = area[2], area[3]
        big = P.wide(w)
        col = 660 if w >= 1240 * u and h >= 760 * u else 340
        offers = self.ws.editor_app._offers
        vals = (("big", big), ("by_blocks", self._blocks()), ("game", self.shows_game()),
                ("col_w", col), ("run_h", 512 if col == 660 else 282),
                ("art_w", 400 if big else 330 if h >= 420 * u else 320),
                ("set_w", 360 if big else 300),
                ("grown", self._grown_key(page)))
        for nm, v in vals:
            self._put(st, nm, v)
        for tab in _OPENED:
            self._put(st, "has_" + tab, bool(offers(tab)))

    @staticmethod
    def _put(st, nm, v):
        if st._v[nm] != v:
            st._v[nm] = v
            st._ver[nm] += 1

    def _grown_key(self, page):
        g = self.grown
        if g is None:
            return None
        for node, _r, _p in page.arranged[0]:
            if self._contents(page, node) == g:
                return node.key
        return None

    @staticmethod
    def _contents(page, node):
        """The contents a pane of the page shows: its tabs on offer, else
        its one."""
        page._bind()
        got = page._offered(node)
        return (node.key,) if got is None else got

    def _place(self, key, area, u):
        """Workspace `key` placed over `area`: its page synced and laid out,
        its held sizes the board's for this project and size where they are
        new; (panes, dividers) in reading order, each pane as (contents,
        rect, path), each divider as (path, index, "h" | "v", rect)."""
        page = self._page(key)
        page.unit = u
        mem = self._mem_key(key, area)
        if getattr(page, "mem", None) != mem:
            self._sync(page, area, u)
            self._restore(page, area, mem)
        self._sync(page, area, u)
        page.place(area)
        arr = page.arranged[0]
        if arr:
            # the pane the keys reach: the one a pane alone stands for
            want = arr[min(self._focus.get(key, 0), len(arr) - 1)][0].key
            if page.pane_cur != want:
                page.pane_cur = want
                if page.alone_pane is not None:
                    page.place(area)
        got = ([(self._contents(page, n), r, p) for n, r, p in page.arranged[0]],
               list(page.arranged[1]))
        page.desk_keys = [n.key for n, _r, _p in page.arranged[0]]
        return got

    def _restore(self, page, area, mem):
        """The page's held sizes the board's for `mem`: every one absent,
        then each split's sizes where it still fits the tree (a remembered
        layout of another tree, or a hand-edited one, reads as absent)."""
        import editor_ui
        st = editor_ui.s
        for nm in editor_ui.SIZES:
            self._put(st, nm, None)
        page.mem = mem
        page.place(area)
        saved = self._saved().get(mem)
        if not isinstance(saved, list):
            return
        by = {}
        for sp in page.splits.values():
            by[sp[8]] = sp
        got = []
        for item in saved:
            if not (isinstance(item, list) and len(item) == 2):
                return
            path, sizes = tuple(item[0]), item[1]
            sp = by.get(path)
            if sp is None or not isinstance(sizes, list) or len(sizes) != len(sp[1]) \
                    or not all(isinstance(v, int) and v >= 0 for v in sizes):
                return
            got.append((sp[1], sizes))
        for kids, sizes in got:
            for k, v in zip(kids, sizes):
                if "size" in k.l and not k.l.get("grow"):
                    self._put(st, k.l["size"], v)

    def shows_game(self):
        """Whether the workspaces hold the Game tab: not while the game
        plays in a desk window of its own (the pause card's Play in a
        window, owner 2026-10-31), when the panes left take its room; it
        comes back when that window closes."""
        win = getattr(self.ws.wm, "windows", {}).get("desktop")
        return win is None or not win.own

    def _warm_sig(self, key, area, u):
        cart = self.ws.cart or {}
        return (key, area, u, self._blocks(), cart.get("path") or cart.get("title"),
                self.shows_game(), self.lacks())

    def warm_step(self):
        """On a quiet frame, one workspace not on show made ready as its first
        switch would make it -- its page synced, its sizes restored and
        placed, each of its tab panes' layouts built at the pane's size -- so
        the switch only draws. One a call, in the Editor window's layout
        context; nothing once every workspace is ready for this cart and
        size, and nothing while a pane stands alone or a divider is held.
        Each is taken by `placed` once, as a fresh placement would have
        been made."""
        if not self._warm_due or self._drag is not None:
            return
        if not self.active() or self.key not in P.KEYS:
            self._warm_due = False
            return
        run = getattr(self.ws.wm, "in_window", None)
        if (run is None or not run("menu", self._warm_next)) and self.ws.screen == "menu":
            self._warm_next()

    def _warm_mark(self, area, u):
        return self._warm_sig(None, area, u) + (self.ws.look.look_gen,)

    def _warm_next(self):
        area = self._area()
        u = self._unit()
        mark = self._warm_mark(area, u)
        if self._warm_for != mark:
            self._warm_for = mark
            self._warm.clear()
            self._warm_left = [k for k in self.keys() if k != self.key]
        left = self._warm_left
        self._warm_due = len(left) > 1
        while left:
            key = left.pop(0)
            sig = self._warm_sig(key, area, u)
            if key == self.key or sig in self._warm:
                continue
            placed = self._place(key, area, u)
            page = self._page(key)
            if page.alone_pane is not None:
                continue                      # one pane at a time here
            self._warm[sig] = placed
            for pane, r, _path in placed[0]:
                for c in pane:
                    tab = P.CONTENTS[c][2]
                    if tab is not None and tab in _OWNERS_OR_CODE:
                        self._pane_layout(tab, self._body(r, u, pane))
            return

    def placed(self):
        """The workspace on show at the surface's size, as its page placed
        it: (panes, dividers) (`_place`)."""
        area = self._area()
        u = self._unit()
        game = self.shows_game()
        fi = self._focus.get(self.key, 0)
        got = self._placed
        f = self._placed_for
        if got is not None and f[0] == self.key and f[1] == area and f[2] == u and f[3] == game \
                and f[4] == fi and f[5] == self.grown:
            return got
        warm = self._warm.pop(self._warm_sig(self.key, area, u), None) if self._warm else None
        got = self._placed = warm if warm is not None else self._place(self.key, area, u)
        self._placed_for = (self.key, area, u, game, fi, self.grown)
        return got

    def minimum(self):
        """The least panes area the workspace on show holds (w, h)."""
        self.placed()
        return self._page().minimum()

    def _mem_key(self, key, area):
        cart = self.ws.cart or {}
        return "%s|%s|%dx%d%s" % (cart.get("path") or cart.get("title") or "",
                                  key, area[2], area[3],
                                  "" if self.shows_game() else "|nogame")

    def _saved(self):
        got = self.ws.system.get("editor_panes", None)
        return got if isinstance(got, dict) else {}

    def _remember(self):
        """The held sizes of the workspace on show kept on the board, per
        project, workspace and size: [[path, sizes], ...] a split."""
        page = self._pages.get(self.key)
        if page is None or not page.splits:
            return
        self._placed = None
        self.placed()
        rows = sorted((sp[8], sp[2]) for sp in page.splits.values())
        got = dict(self._saved())
        got[page.mem] = [[list(p), list(sz)] for p, sz in rows]
        self.ws.system.set("editor_panes", got)

    def _sizes_moved(self):
        """A held size changed in the page's hands (a divider, Ctrl+0,
        Ctrl+Alt+arrows): placed again, remembered, drawn."""
        self._placed = None
        self._remember()
        self.ws.mark_dirty()

    # -- workspaces and focus ---------------------------------------------------

    def panes(self):
        return self.placed()[0]

    def focused(self):
        """(pane, rect, path) of the focused pane."""
        panes = self.panes()
        i = self._focus.get(self.key, 0)
        return panes[min(i, len(panes) - 1)]

    def tab_of(self, pane):
        """The content key a pane shows: its open tab."""
        return pane[min(self._tabs.get(pane, 0), len(pane) - 1)]

    def switch(self, key):
        """Show workspace `key`. The panes left behind that hold an edit owe
        their commit (`EditorApp.commit_later`); focus lands where it was."""
        if key == self.key or key not in self.keys() or self.key == P.THEME:
            return False
        app = self.ws.editor_app
        for pane, _r, _p in self.panes():
            tab = P.CONTENTS[self.tab_of(pane)][2]
            if tab is not None and not app._tab_is_clean(tab):
                app.commit_later(tab)
        if self.key == "sound":
            self.ws.music_ui._stop_music_preview()
        self.key = key
        app.zone_gen += 1               # the row marks the workspace on show
        self.grown = None
        self._placed = None
        self._shown = None
        self._land()
        return True

    def step(self, d):
        keys = self.keys()
        if self.key not in keys:
            return False
        i = (keys.index(self.key) + d) % len(keys)
        return self.switch(keys[i])

    def _land(self):
        """The workspace's panes built, and the focused pane's tab the
        Editor's (the history's and the keyboard's)."""
        if self._shown == self.key:
            return
        self._shown = self.key
        app = self.ws.editor_app
        for pane, _r, _p in self.panes():
            for c in pane:
                tab = P.CONTENTS[c][2]
                if tab is not None:
                    app.build_tab(tab)
        self.focus_pane(self._focus.get(self.key, 0))
        self._desk_zooms()

    def _desk_zooms(self):
        """The Map and the Scene open at 2x on a desk (EDITOR_LAYOUT.md),
        once a cart; the wheel and A move them after."""
        ws = self.ws
        path = (ws.cart or {}).get("path")
        if self._zoomed == path:
            return
        mu, su = ws.built("map_ui"), ws.built("scene_ui")
        if mu is None and su is None:
            return
        self._zoomed = path
        if mu is not None and mu.map_zoom == 0:
            mu.map_zoom = 1                 # 16 px a cell: 2x
        if su is not None and su.scene_zoom == 0:
            su.scene_zoom = 1

    def focus_pane(self, i):
        """Move the keys to pane `i` (reading order). Commits nothing."""
        panes = self.panes()
        i %= len(panes)
        self._focus[self.key] = i
        tab = P.CONTENTS[self.tab_of(panes[i][0])][2]
        app = self.ws.editor_app
        if tab is not None:
            app.focus_tab(tab)
        self._seen = app.tab
        self.ws.mark_dirty()

    def follow(self):
        """A tab opened from outside the desk (`EditorApp.set_tab`): its
        workspace, its pane focused."""
        tab = self.ws.editor_app.tab
        if tab == self._seen:
            self._land()
            return
        self._seen = tab
        cur = self.focused()
        if P.CONTENTS[self.tab_of(cur[0])][2] == tab:
            self._land()
            return
        for k in (self.key, _HOME.get(tab)):
            if k is None:
                continue
            if k != self.key:
                self.key = k
                self.ws.editor_app.zone_gen += 1
                self.grown = None
                self._placed = None
                self._shown = None
            for n, (pane, _r, _p) in enumerate(self.panes()):
                for t, c in enumerate(pane):
                    if P.CONTENTS[c][2] == tab:
                        self._tabs[pane] = t
                        self._focus[self.key] = n
                        self._land()
                        self.focus_pane(n)
                        return

    def alone(self):
        """The pane shown over the whole panes area, or None: the grown one,
        else the focused one where the area is under the workspace's least
        size (one pane at a time)."""
        self.placed()
        page = self._page()
        if page.alone_pane is None:
            return None
        return self._contents(page, page.alone_pane)

    def grow(self, pane=None):
        """Grow a pane over the workspace, or back (Ctrl+Shift+Enter, Esc,
        a double tap on its header, its grow tool)."""
        if pane is None or self.grown == pane:
            self.grown = None
        else:
            self.grown = pane
        self.ws.mark_dirty()

    # -- a tab in a pane ----------------------------------------------------------

    def laid_out(self, tab):
        """(body, layout) of the pane on show whose content is tab `tab`'s
        surface, in the window's content space, as its draw and its pointer
        lay it out (`_in_pane`), else None."""
        alone = self.alone()
        for pane, r, _path in self.panes():
            if alone is not None:
                if pane != alone:
                    continue
                r = self._area()
            if P.CONTENTS[self.tab_of(pane)][2] == tab:
                body = self._body(r, self._unit(), pane)
                return body, self._pane_layout(tab, body)
        return None

    def _pane_layout(self, tab, r):
        """The layout tab `tab`'s surface takes in a pane `r` big: built by
        its own `relayout` at that size with no bar, once per size (and for
        Code, per whether it shows its symbol keys, and for Sprite, per
        whether its hints have keys to name, which the last input decides:
        a layout that disagrees is one the tab rebuilds as it draws, every
        frame)."""
        ws = self.ws
        fs = ws.look.effective_font_scale()
        cs = ws.look.effective_chrome_scale()
        sym = tab == "code" and ws.code_layer.wants_symbols()
        keys = tab == "paint" and ws.paint_layer._keys()
        key = (tab, r[2], r[3], fs, cs, ws.look.look_gen, sym, keys)
        lay = self._lay.get(key)
        if lay is not None:
            return lay
        cv = ws.sys_canvas
        vp = cv.viewport()
        cv.set_viewport(vp[0] + r[0], vp[1] + r[1], r[2], r[3])
        _lb.in_pane(True)
        old = self._layout_of(tab)
        try:
            if tab == "code":
                ws.relayout_code()
            else:
                name, _attr = _OWNERS[tab]
                getattr(ws, name).relayout(r[2], r[3], fs, cs)
            lay = self._layout_of(tab)
        finally:
            _lb.in_pane(False)
            self._set_layout(tab, old)
            cv.set_viewport(*vp)
        if len(self._lay) > 24:
            self._lay.clear()
        self._lay[key] = lay
        return lay

    def _layout_of(self, tab):
        ws = self.ws
        if tab == "code":
            return ws.code_layout
        name, attr = _OWNERS[tab]
        return getattr(getattr(ws, name), attr)

    def _set_layout(self, tab, lay):
        ws = self.ws
        if tab == "code":
            ws.code_layout = lay        # the editor's view size is the page's, set as it draws
            return
        name, attr = _OWNERS[tab]
        setattr(getattr(ws, name), attr, lay)

    def _in_pane(self, tab, r, fn, *args):
        """Run `fn(*args)` with tab `tab`'s surface laid out in pane rect
        `r` and the canvas's viewport on it; the bar is not the pane's."""
        ws = self.ws
        lay = self._pane_layout(tab, r)
        old = self._layout_of(tab)
        cv = ws.sys_canvas
        vp = cv.viewport()
        self._set_layout(tab, lay)
        cv.set_viewport(vp[0] + r[0], vp[1] + r[1], r[2], r[3])
        bar = ws.bar_layer
        bar.held = True
        try:
            return fn(*args)
        finally:
            bar.held = False
            cv.set_viewport(*vp)
            if tab != "code":
                self._set_layout(tab, old)
            else:
                ws.code_layout = old

    def _surface(self, tab):
        """What tab `tab` draws with in a pane: its content layer, the Sound
        pane's own page for the music tab (`SoundPane`)."""
        ws = self.ws
        return ws.music_ui.sound if tab == "music" else ws.layer_of(tab)

    def part(self, c):
        """The host of the part pane content `c` shows (`Parts.PAGES`), made
        at its first use."""
        name = Parts.part_of(self, c)
        got = self._parts.get(name)
        if got is None:
            got = self._parts[name] = Parts.PartHost(self, c, name)
        return got

    def _tab_pane(self, tab, r, dt, own=False, moves=False):
        layer = self._surface(tab)
        if layer is None:
            return
        # the WM's word for the pane's frame (`window_frame`), which its
        # page's shift and rows frames and the page held under its modal
        # (`Hold`) read: on a split frame the WM's own where it says the
        # buffer holds the window as the last draw left it; a whole frame a
        # window's, but for a text view's moves out of the last frame
        # (`_TEXT_PANES`)
        host = self._host
        was = host.window(self._vouch if own and self._vouch >= 2 else 2 if moves else 1)
        try:
            self._in_pane(tab, r, layer.draw, dt)
        finally:
            host.window(was)

    # -- drawing ------------------------------------------------------------------

    # -- a prompt's rows (docs/history/scroll_and_text_2026-10.md §5) -----------------------
    #
    # While a pane's tab has a prompt up (the Blocks entry prompts) the desk
    # under it does not change but by input that reaches
    # it, and the window's content speaks the shown protocol: a frame whose
    # input only typed into the prompt's field or moved its focus, into a
    # buffer that holds the desk as the last draw left it, draws the prompt's
    # changed rows alone and says so (`changed`), so the window's stamp copies
    # those rows and nothing else.

    def _prompt(self):
        """(tab, its layer, pane, rect) of the Blocks pane on show while its
        prompt is up, which takes the keys, else None."""
        if self.ws.block_ui.blk_kbd is None:
            return None
        alone = self.alone()
        for pane, r, _path in self.panes():
            if alone is not None:
                if pane != alone:
                    continue
                r = self._area()
            if P.CONTENTS[self.tab_of(pane)][2] == "blocks":
                return "blocks", self.ws.block_ui, pane, r
        return None

    @property
    def HELD(self):
        ws = self.ws
        was = ws.layout
        if self._drew_in is not None:
            ws.layout = self._drew_in
        try:
            return self._own_pane() is not None
        finally:
            ws.layout = was

    def retained(self, known, x0, y0, x1, y1):
        r = self._ret
        r[0] = 1 if known else 0
        r[1] = x0
        r[2] = y0
        r[3] = x1
        r[4] = y1

    def vouched(self, v):
        self._vouch = v

    def takes_lag(self, lag):
        """Whether this frame's draw repaints `lag` [x0, y0, x1, y1), what
        its target lags (a direct render's): a pane's own frames repaint a
        lag inside that pane; a lag outside the pane would draw the desk
        whole and leave the next buffer as far behind."""
        if lag[2] <= lag[0] or lag[3] <= lag[1]:
            return True
        ws = self.ws
        was = ws.layout
        if self._drew_in is not None:
            ws.layout = self._drew_in
        try:
            return self._takes(lag)
        finally:
            ws.layout = was

    def _takes(self, lag):
        own = self._own_pane()
        if own is None:
            return False
        b = own[3] if own[0] == "music" else own[4]
        return (lag[0] >= b[0] and lag[1] >= b[1] and lag[2] <= b[0] + b[2]
                and lag[3] <= b[1] + b[3])

    def _head_h(self, u):
        """A pane header's height: its row (`P.HEADER` units), or where the
        UI face's line at the font scale is taller (Large text), that line
        and a margin, so its words never run into the body under it."""
        return max(P.HEADER * u, _V.ui_face_line() * self.ws.look.effective_font_scale() + 4 * u)

    def changed(self):
        return self._changed

    def unclip(self, cv):
        """A draw's own clip let go: back to the frame's (`_split_frame`)."""
        if self._clip is None:
            cv.clip()
        else:
            cv.clip(*self._clip)

    # -- a pane's own frames (docs/history/scroll_and_text_2026-10.md §15 P5) -------------
    #
    # While the focused pane shows Blocks, Settings, the Code tab, theme
    # Config, the Map or the Sound pane, the desk speaks the shown protocol:
    # a frame the engine plans as that pane's split frame (its input reached
    # only that pane, and nothing another pane draws changed: no edit the
    # other panes show, the made code, the sounds list) draws that pane alone
    # and names it as what it changed. A tab's pane draws its body (its
    # header holds nothing the frame moved); the Sound pane, whose header
    # shows what its keys change, its card, header and body.

    def _own_pane(self):
        """(content, tab, pane, rect, body, index) of the focused pane where
        its frames may be its own, else None."""
        if self._menu_open() or self._head_due:
            return None                 # a header's menu over the panes, or its answer due
        pane, r, _path = self.focused()
        alone = self.alone()
        if alone is not None:
            if pane != alone:
                return None
            r = self._area()
        c = self.tab_of(pane)
        if c not in _OWN_FRAMES:
            return None
        tab = P.CONTENTS[c][2]
        if self._surface(tab) is None:
            return None
        if c == "paint" and self.ws.layer_of(tab)._pop != "pickers":
            return None
        return (c, tab, pane, r, self._body(r, self._unit(), pane),
                self._focus.get(self.key, 0))

    def _sprite_owes(self):
        """Whether a Sprite pane shown beside the one the keys are in owes
        its page the next frame (its first places its focus): that frame
        draws whole."""
        for _n, pane, _r in self._shown_panes():
            if self.tab_of(pane) == "paint":
                pg = self.ws.paint_layer.page
                return pg is not None and pg.owes
        return False

    def _own_data(self, c):
        """What the frame's input may change that a pane besides `c` draws or
        `c`'s header shows: an edit's undo step, the sounds, the blocks'
        object, the Map's tools, the Code pane's file and find tool."""
        ws = self.ws
        if c == "cards":
            h = getattr(ws.run.project, "config_hist", None)
            return None if h is None else (id(h), h.gen)
        if c in ("code", "theme_config"):
            return (ws.text.code_file_name(), bool(ws.layer_of(c)._find_open))
        if c == "blocks":
            bu = ws.block_ui
            be = bu.blocks_ed
            if be is None:
                return None
            return (id(be), be._hist.gen, be.target, bu.blk_graduated)
        if c == "music":
            snd = ws.music_ui.sound
            me = snd.editor()
            if me is None:
                return None
            if snd.asking():
                return False            # a popover over the panes beside it
            return (id(me), me._hist.gen, me.view, me.sfx_idx, me.track_idx,
                    len(me.bank.sfx), len(me.bank.music), ws.music_ui.music_preview)
        if c == "map":
            mu = ws.map_ui
            return (mu.map_tool, mu.map_erase)
        if c == "paint":
            pe = ws.paint
            if pe is None:
                return False
            return (pe.n, pe.size, pe.sheet, pe.sheet.gen)
        return None

    def _split_frame(self, dt, own):
        """The frame as the split frame of the pane the keys reach, where
        the engine plans one (`AppHost.split_frame`, docs/history/ui_api_2026-10.md
        §5a): that pane drawn alone -- its body (`own`; the Sound pane its
        card, header and body) -- and what
        it changed said (`changed`). True where it drew. The desk gives the
        engine what it draws outside the pane as a gen, and None where that
        changes on its own this frame."""
        ws = self.ws
        host = self._host
        b = self._box
        if own is None:
            host.split_frame(None, False, 0, _NO_LAG, b)
            return False
        cv = ws.sys_canvas
        look = ws.look
        app = ws.editor_app
        ret = self._ret
        u = self._unit()
        c, tab, pane, r, _body, _n = own
        data = self._own_data(c)
        known = ret[0] != 0
        lag = ret[1:]
        still = not (data is False or app.playing() or ws.animating(dt, False)
                     or self._loupe is not None
                     or (c == "paint" and ws.paint_layer._host.tap == 2
                         and ws.paint_layer._host.tap_armed())
                     or (c != "paint" and self._sprite_owes()))
        key = (c, tab, self._acts, self.key, self._focus.get(self.key, 0), self.grown, pane,
               r, self.placed()[0], cv.w, cv.h, look.look_gen, look.effective_font_scale(),
               look.effective_chrome_scale(), ws.bar_layer.shown_gen("menu"), data,
               self._flash)
        if key != self._surround:
            self._surround = key
            self._gen = (self._gen + 1) & 0x3FFFFFFF
        top = 0 if c == "music" else r[3] - self._body(r, u, pane)[3]
        v = host.split_frame(self._gen if still else None, known, top, lag, b)
        if v == host.SPLIT_WHOLE:
            return False
        body = (b[0], b[1], b[2], b[3])
        x0, y0, x1, y1 = b[0], b[1], b[0] + b[2], b[1] + b[3]
        if v == host.SPLIT_LAGS:
            # the buffer lags outside the pane: the
            # frame draws whole, and what it changed is still the pane
            # alone -- everything else
            # draws as the frame before showed it -- so the buffers behind
            # catch up rather than lag whole again; a text view moves its
            # rows out of the last frame all the same
            self._changed = [x0, y0, x1, y1]
            if c in _TEXT_PANES and self._vouch >= 2:
                self._moves = pane
            return False
        if c == "music":
            # its page, then the desk's verbs run whole (focus rests on the
            # first pane's header), their pixels clipped to the pane
            th = ws.theme_colors
            self._corners(cv, th["panel"], r[0], r[1], r[2], r[3], P.RADIUS * u)
            top = r[1] - ws.layout.cy
            if r[1] == self._area()[1] and top > 0:
                # the margin over it, where its header's focus ring reaches,
                # among what the frame changed
                cv.rect(r[0], ws.layout.cy, r[2], top, th["panel"])
                y0 = min(y0, ws.layout.cy)
            pb = self._body(r, u, pane)
            self._card(cv, th, r, True, u)
            self._clip = r
            cv.clip(*r)
            try:
                self._draw_head(own[5], pane, r, u, dt)
            finally:
                self._clip = None
                cv.clip()
            self._tab_pane(tab, pb, dt, True)
        else:
            self._tab_pane(tab, body, dt, True)
            if c == "cards" and self._own_data(c) != data:
                # a card's value is set by the page's draw, an undo step the
                # Editor's strip shows: the strip drawn over this frame too
                ws.bar_layer.draw_status_strip("menu")
                for bx, by, bw, bh in ws.bar_layer.bar_rects("menu"):
                    x0, y0 = min(x0, bx), min(y0, by)
                    x1, y1 = max(x1, bx + bw), max(y1, by + bh)
                self._changed = [x0, y0, x1, y1]
                return True
            w = self._within
            if self._host.within(w):
                # it drew inside that rect of the pane alone (a modal's band
                # over the page it left)
                self._changed = [body[0] + w[0], body[1] + w[1], body[0] + w[0] + w[2],
                                 body[1] + w[1] + w[3]]
                return True
        self._changed = [x0, y0, x1, y1]
        return True

    def draw(self, dt):
        ws = self.ws
        self._drew_in = ws.layout
        self.dt = dt
        self.follow()
        self._play_tabs()
        if not self._warm_due and self.key in P.KEYS \
                and self._warm_for != self._warm_mark(self._area(), self._unit()):
            self._warm_due = True
        self._changed = None
        try:
            own = self._own_pane()
            if not self._split_frame(dt, own):
                self._draw(dt)
                if own is not None and self._changed is None:
                    cv = ws.sys_canvas
                    self._changed = [0, 0, cv.w, cv.h]
        finally:
            self._ret[0] = 0
            self._vouch = 0
            self._moves = None

    def _draw(self, dt):
        ws = self.ws
        cv = ws.sys_canvas
        th = ws.theme_colors
        lay = ws.layout
        u = self._unit()
        panes, divs = self.placed()
        alone = self.alone()
        self._ground(cv, th["panel"], lay, panes, divs, alone, u)
        shown = self._shown_panes()
        self._still_at = None
        for n, pane, r in shown:
            self.pane_body(n, pane, r, dt)
            cv.clip()
        self._frame(cv, th, shown, u, dt)
        if self._loupe is not None and not ws.pointer.down:
            self._loupe = None
        if self._loupe is not None:
            self._draw_loupe(cv, th, u)
        ws.bar_layer.draw_status_strip("menu")
        self._dock()

    def pane_body(self, n, pane, r, dt):
        """Pane `n` in its rect `r`: its card, its header (where no More
        menu of its hangs over the panes: `_frame` draws that one last),
        then its body -- its tab's surface, the Run slot or its part's
        page, over whatever of the header's marks reach past it."""
        ws = self.ws
        cv = ws.sys_canvas
        th = ws.theme_colors
        u = self._unit()
        c = self.tab_of(pane)
        body = self._body(r, u, pane)
        tab = P.CONTENTS[c][2]
        filled = (body[1] if tab in _FILLS_BODY and self._surface(tab) is not None else 0)
        self._card(cv, th, r, n == self._focus.get(self.key, 0), u, filled)
        if not self._headless(pane) and not self._head_over_panes(n):
            self._draw_head(n, pane, r, u, dt)
        if tab is not None:
            self._tab_pane(tab, body, dt, moves=pane == self._moves)
        elif c == "game":
            self._game(cv, th, body, u)
        elif c in Parts.PAGES:
            self.part(c).draw(body, dt)

    def _ground(self, cv, col, lay, panes, divs, alone, u):
        """The Editor's ground where the cards leave it showing: the margin
        round the panes area, the gutters between the panes and each card's
        corners (its rounding is drawn over them). The cards cover the rest,
        so the ground is never filled under them."""
        ax, ay, aw, ah = self._area()
        cx, cy, cw, ch = lay.cx, lay.cy, lay.cw, lay.ch
        cv.rect(cx, cy, cw, ay - cy, col)
        cv.rect(cx, ay + ah, cw, cy + ch - ay - ah, col)
        cv.rect(cx, ay, ax - cx, ah, col)
        cv.rect(ax + aw, ay, cx + cw - ax - aw, ah, col)
        rad = P.RADIUS * u
        if alone is not None:
            self._corners(cv, col, ax, ay, aw, ah, rad)
            return
        for _p, _i, _axis, (dx, dy, dw, dh) in divs:
            cv.rect(dx, dy, dw, dh, col)
        for _pane, (x, y, w, h), _path in panes:
            self._corners(cv, col, x, y, w, h, rad)

    def _corners(self, cv, col, x, y, w, h, rad):
        cv.rect(x, y, rad, rad, col)
        cv.rect(x + w - rad, y, rad, rad, col)
        cv.rect(x, y + h - rad, rad, rad, col)
        cv.rect(x + w - rad, y + h - rad, rad, rad, col)

    def _headless(self, pane):
        """The Settings workspace's game has no header: the game at 2x
        where the pane holds it (EDITOR_LAYOUT.md)."""
        return self.key == "settings" and pane == ("game",)

    def _dock(self):
        """The playtest stands in the Run slot or the Game tab, at the
        slot's whole scale (`WindowedWM.dock`): Play selects the workspace's
        Game tab, Stop gives the tab back, and a workspace with no game on
        show hides it, its run held."""
        ws = self.ws
        playing = ws.editor_app.playing()
        dock = getattr(ws.wm, "dock", None)
        if dock is None or not playing:
            return
        if self._still_at is None or self.paused:
            dock("desktop", False)
            return
        ox, oy = self._origin()
        gx, gy, gw, gh = self._still_at
        dock("desktop", (ox + gx, oy + gy, gw, gh))

    def _play_tabs(self):
        """Play selects the workspace's Game tab; Stop gives the tab back."""
        ws = self.ws
        playing = ws.editor_app.playing()
        if playing != self._was_playing:
            self._was_playing = playing
            self.paused = False
            if not playing:
                # every pane Play turned to its Game tab, shown or not (the
                # game may have left the workspaces for a window of its own)
                for pane, t in self._back_tab.items():
                    self._tabs[pane] = t
                self._back_tab.clear()
                ws.mark_dirty()
                return
            for _n, pane, _r in self._shown_panes():
                if "game" in pane and len(pane) > 1:
                    self._back_tab[pane] = self._tabs.get(pane, 0)
                    self._tabs[pane] = pane.index("game")
                    ws.mark_dirty()

    def undock(self):
        """The playtest back in a window of its own (the Editor left the
        desk's workspaces)."""
        dock = getattr(self.ws.wm, "dock", None)
        if dock is not None:
            dock("desktop", None)

    def _body(self, r, u, pane=None):
        h = 0 if pane is not None and self._headless(pane) else self._head_h(u)
        return (r[0], r[1] + h, r[2], max(0, r[3] - h))

    def _card(self, cv, th, r, focused, u, filled=0):
        """Pane `r`'s card; with `filled`, the y its content's own fill
        starts at, the card above it alone."""
        x, y, w, h = r
        rad = P.RADIUS * u
        line = None if th.get("surface_light", False) else th["border"]
        if filled:
            if filled > y:
                cv.clip(x, y, w, filled - y)
                cv.rrect(x, y, w, h, rad, th["surface"], line)
                cv.clip()
        else:
            cv.rrect(x, y, w, h, rad, th["surface"], line)
        if focused:
            cv.clip(x, y, w, P.EDGE * u)
            cv.rrect(x, y, w, h, rad, th["value"])
            cv.clip()

    def _frame(self, cv, th, shown, u, dt):
        """The dividers, a header whose More menu is open and the tag of a
        divider stopped at its minimum, after the bodies. The dividers are
        the workspace page's (`_draw_splits`: its C draws them into the
        desk host's pass, which a press on one reaches, and a pane alone is
        a split of one); each header is its pane's page (editor_head.py,
        hosted by `editor_heads.HeadHost`) on the pane's rect, drawn here
        where its More menu hangs over the panes, else under its body
        (`pane_body`). What the pass answers (a divider's
        release) shows on the frame it owes (`AppHost.owed`, asked for with
        `request_frame`)."""
        host = self._host
        host.begin(cv, th, (0, 0, cv.w, cv.h), True, True, elsewhere=True)
        self._draw_splits(u)
        host.end()
        if host.owed or host.tap == 2:
            self.ws.request_frame()     # the frame that shows what the pass answered
        drawn = 0
        due = False
        for n, pane, r in shown:
            if not self._headless(pane):
                if self._head_over_panes(n):
                    self._draw_head(n, pane, r, u, dt)      # its menu or tooltip over the panes
                drawn |= 1 << n
                due |= not self._heads[n]._host.still()
        self._head_due = due
        for n, h in self._heads.items():
            if h.pop and not drawn >> n & 1:
                h.close_pop()           # its pane left the workspace on show
        flash = self._flash
        if flash is not None and self._drag is not None:
            pane, why = flash
            for _n, p, r in shown:
                if p == pane:
                    cv.rrect(r[0] - 2 * u, r[1] - 2 * u, r[2] + 4 * u, r[3] + 4 * u,
                             (P.RADIUS + 2) * u, None, th["value"])
                    _V.label(cv, (r[0] + 8 * u, r[1] + r[3] - 28 * u, r[2] - 16 * u, 24 * u),
                             why, th["value"])

    def head(self, n):
        """The host of pane `n`'s header page, made at its first use."""
        h = self._heads.get(n)
        if h is None:
            h = self._heads[n] = Heads.HeadHost(self, n)
        return h

    def _head_over_panes(self, n):
        """Whether pane `n`'s header draws after the bodies: its More menu
        hangs over the panes, or a mouse over it shows a tooltip there."""
        o = self._head_over
        return self.head(n).pop or (o is not None and o[0] == n)

    def _draw_head(self, n, pane, r, u, dt):
        """Pane `n`'s header on its rect `r`: its focus shows where the keys
        are in it (the Sound pane's, a more menu's)."""
        h = self.head(n)
        if h.pane != pane and h.pop:
            h.close_pop()
        keys = n == self._focus.get(self.key, 0) and (h.pop or self.tab_of(pane) == "music")
        h.draw(pane, r, self._head_vals(n, pane, r, u), keys, dt)

    def _head_vals(self, n, pane, r, u):
        """Pane `n`'s header state (editor_head.sync): its kind, its words,
        its tabs, the tools that fit and the more menu's rest, the Game's,
        the Code pane's and the Sound pane's own, and its measures. The
        tools keep right of the title or tabs; tabs that would not fit
        labelled are short (the current one labelled, the others icons)."""
        ws = self.ws
        x, _y, w, h = r
        c = self.tab_of(pane)
        cell = 32 * u
        fs = ws.look.effective_font_scale()
        fixed = (cell * (1 + (c == "game")) + 4 * u
                 + (7 * cell if c == "music" else cell if c == "sounds" else 0))
        short = len(pane) > 1 and self._tabs_w(pane, -1, u) > w - fixed - 8 * u
        tools, folded = self._head_fit(pane, c, x, w, u, short)
        cur = self._tabs.get(pane, 0)
        icon = title = status = tab = file = ""
        tabs = shorts = files = ()
        find = False
        form, lead = "named", 20 * u
        cells = fixed + cell * (len(tools) + bool(folded))
        if c == "code" and len(pane) == 1:
            kind = "code"
            name = ws.text.code_file_name() or ""
            files = tuple(ws.text.code_sources() or [name])
            file = name if name in files else files[0]
            find = bool(getattr(ws.code_layer, "_find_open", False))
            cells += 3 * cell
        elif len(pane) == 1:
            kind = "title"
            label, icon, _tab, _m = P.CONTENTS[c]
            title = self._title(c, label)
            status = self._status(c)
            # nothing is cut: where the name and the tools do not fit, the
            # status gives way, then the icon, then the words (the pane's
            # icon names it, as a short pane's tabs are their icons)
            named = 22 * u + 22 * fs + self._tw(title) + 8 * fs + cells
            if status and named + self._tw(status) + 8 * fs > w:
                status = ""
            if named > w:
                status = ""
                if 10 * u + self._tw(title) + 8 * fs + cells <= w:
                    form, lead = "words", 8 * u
                else:
                    form = "icon"
        elif short:
            kind = "short"
            shorts = tuple((str(j), P.CONTENTS[k][0], P.CONTENTS[k][1], j == cur)
                           for j, k in enumerate(pane))
        else:
            kind = "tabs"
            tabs = tuple(P.CONTENTS[k][0] for k in pane)
            tab = str(cur)
        self._tools_x[n] = x + w - 2 * u - cells + 4 * u
        keys = _V.hint_kind() == "keys"
        if self._code_rows[0] != keys:
            self._code_rows = (keys, tuple((ic, _word(wd, keys), op) for ic, wd, op in _CODE_MORE))
        snd = ws.music_ui.sound.head_vals(self) if c == "music" else (False, False, "", False, False)
        return (kind, form, icon, title, status, tabs, tab, shorts,
                tuple((ic, _word(wd, keys), op, self._tool_on(op)) for ic, wd, op in reversed(tools)),
                tuple((ic, _word(wd, keys), op) for ic, wd, op in folded),
                (c == "game", self.paused, ws.editor_app.playing()), files, file, find, snd,
                c == "sounds" and self.key == "sound",
                (cell, 1, lead, max(1, h - self._head_h(u)), min(w - 16 * u, 160 * u * fs),
                 min(w - 16 * u, 200 * u * fs), self._code_rows[1]))

    def head_act(self, head, verb, *args):
        """What pane header `head`'s buttons ask: Grow, a tab, a tool (its
        more menu's too), Pause, a Code file or tool, a new sound, the Sound
        pane's tools; a more menu opened or closed."""
        ws = self.ws
        pane = head.pane
        if pane is None:
            return
        if verb == "grow":
            self.grow(pane)
        elif verb == "tab":
            j = args[0]
            if 0 <= j < len(pane) and j != self._tabs.get(pane, 0):
                self._tabs[pane] = j
                if head.n == self._focus.get(self.key, 0):
                    self.focus_pane(head.n)
        elif verb == "tool":
            self._head_tool(args[0])
        elif verb == "pause":
            self.pause(not self.paused)
        elif verb == "file":
            if args[0] and args[0] != ws.text.code_file_name():
                ws.text.open_code_file(args[0])
        elif verb == "code":
            cl = ws.code_layer
            cl.jump_anchor = head.rect_of("goto") if args[0] == "goto" else None
            cl._run_tool(args[0], ws.editor)
        elif verb == "new_sound":
            Parts.new_sound(self)
        elif verb == "sound":
            ws.music_ui.sound.head_act(self, args[0])
        ws.mark_dirty()

    def _tabs_w(self, pane, cur, u):
        """The width a pane's header tabs take: every one labelled, or with
        `cur` an index, short -- that one labelled, the others icons. A
        tab's room scales with the font where Large text outgrows the unit,
        as the engine draws it (moy_ui_parts.c's `tab_box`)."""
        k = max(u, self.ws.look.effective_font_scale())
        if cur == -1:
            return sum(self._tw(P.CONTENTS[c][0]) + _TAB_PAD * k for c in pane)
        return (32 * u * (len(pane) - 1) + (_TAB_PAD + _TAB_LEAD) * k
                + self._tw(P.CONTENTS[pane[cur]][0]))

    def _tw(self, text):
        """The pixels a header's `text` takes, in the UI face at the font scale."""
        return _V.text_w(text, self.ws.look.effective_font_scale())

    def _head_fit(self, pane, c, x, w, u, short=False):
        """The header tools a pane shows and the ones its more menu holds:
        as many as fit right of its name or tabs, the rest (the leftmost)
        folded, as the Code header's are."""
        tools = _HEAD_TOOLS.get(c, ())
        if not tools:
            return tools, ()
        cell = 32 * u
        if len(pane) == 1:
            lead = 8 * u + 28 * u + self._tw(self._title(c, P.CONTENTS[c][0]))
        else:
            lead = 4 * u + self._tabs_w(pane, self._tabs.get(pane, 0) if short else -1, u)
        room = (w - lead - 2 * u - cell - 4 * u) // cell
        if room >= len(tools):
            return tools, ()
        k = max(0, room - 1)
        return tools[:k], tools[k:]

    def _head_open(self):
        """The header whose more menu is open, or None."""
        for h in self._heads.values():
            if h.pop:
                return h
        return None

    def _menu_open(self):
        """Whether a header's more menu is open (it takes the keys and the
        pointer)."""
        return self._head_open() is not None

    def _play_slot(self):
        """The still frame's Play: the paused playtest goes on, else Play."""
        if self.paused:
            self.pause(False)
        else:
            self.ws.defer(self.ws.text.leave_menu)

    def pause(self, on):
        """The Run slot's pause: the playtest's window hides with its run
        held (`WindowedWM.dock`) and the slot shows its last frame, dimmed
        under Play; off, the run goes on where it stood and takes the keys."""
        ws = self.ws
        on = bool(on) and ws.editor_app.playing()
        if on == self.paused:
            return
        self.paused = on
        if on:
            self._dock()                    # hidden now, its run held
            ws.wm.move_focus("menu")
        else:
            win = ws.wm.windows.get("desktop")
            if win is not None:
                win.held = False            # the restore lands on the run, not its menu
            ws.run.player.pace.resume()
            if "desktop" in ws.wm.windows:
                ws.wm.move_focus("desktop")
        ws.mark_dirty()

    def _title(self, c, label):
        ws = self.ws
        if c == "paint" and ws.paint is not None:
            return "Sprite %d" % ws.paint.n
        if c == "code":
            return ws.text.code_file_name()
        if c == "music":
            return ws.music_ui.sound.title()
        return label

    def _head_tool(self, op):
        """A tool in a pane's header: the Sprite pane's flip and rotate, the
        Map pane's tools, eraser and zoom."""
        ws = self.ws
        if op.startswith("scene:"):
            su = ws.scene_ui
            se = su.sceneedit
            what = op[6:]
            if what == "zoom":
                su.cycle_zoom()
            elif se is not None:
                if what == "snap":
                    se.snap = not se.snap
                elif what == "delete":
                    se.delete_sel()
                elif what == "back":
                    se.back_sel()
                elif what == "front":
                    se.front_sel()
                elif what == "flip":
                    se.toggle_flip()
                su._sync_live()
                self._owe_restart("scene")
        elif op.startswith("map:"):
            mu = ws.map_ui
            what = op[4:]
            if what == "erase":
                mu.map_erase = not mu.map_erase
            elif what == "zoom":
                mu.cycle_zoom()
            else:
                mu.map_tool = what
                mu.map_erase = False
                mu._map_rect = None
                mu._map_sel = None
        else:
            ws.paint_layer._do_tool(op)
        ws.mark_dirty()

    def _tool_on(self, op):
        """Whether a header tool is the one in use (a current mark)."""
        if op == "scene:snap":
            se = self.ws.scene_ui.sceneedit
            return bool(se is not None and se.snap)
        if not op.startswith("map:"):
            return False
        mu = self.ws.map_ui
        what = op[4:]
        if what == "erase":
            return bool(mu.map_erase)
        return what == mu.map_tool and not mu.map_erase

    def _status(self, c):
        """A pane's dim status after its name: the game's scale."""
        if c == "game" and self._scale:
            return "%d\u00d7" % self._scale
        if c == "made":
            return "made by your blocks"
        return ""

    def _keys_pane(self):
        """The key of the page's pane the keys reach: a prompt's, else the
        focused one."""
        got = self._prompt()
        keys = self._page().desk_keys
        if got is not None:
            for n, (pane, _r, _path) in enumerate(self.panes()):
                if pane == got[2]:
                    return keys[n]
        return keys[min(self._focus.get(self.key, 0), len(keys) - 1)]

    def _draw_splits(self, u):
        """The workspace's dividers, its page's (`draw_splits`), on the
        desk's verbs: drawn, a press on one held and its line dragged, the
        release writing the sizes beside it and a double tap putting them
        back. Each split's focus is its child pane the keys reach (the
        engine's split frame and the pad's moves start there)."""
        page = self._page()
        page.mouse = bool(getattr(self.ws.pointer, "hovers", False))
        page.pane_cur = self._keys_pane()
        page.clock = _ticks_ms()
        gen = page.size_gen
        page.draw_splits()
        held = page.div_held
        self._drag = held
        self._flash = None
        if page.flash is not None and held is not None:
            pane, why = page.flash
            self._flash = (self._contents(page, pane), why)
        if page.size_gen != gen:
            self._sizes_moved()

    def _game(self, cv, th, r, u):
        """The Run slot: the game's frame at the largest whole scale the pane
        holds, centred; a still frame, dimmed under the Play glyph, while no
        game runs."""
        ws = self.ws
        gc = ws.run.canvas
        x, y, w, h = r
        pad = 4 * u
        s = max(1, min((w - 2 * pad) // gc.w, (h - 2 * pad) // gc.h))
        gw, gh = gc.w * s, gc.h * s
        self._scale = s
        gx = x + (w - gw) // 2
        gy = y + max(0, (h - gh) // 2)
        cv.clip(x, y, w, h)
        fb = getattr(gc, "flush_batch", None)
        if fb is not None:
            fb()
        live = ws.editor_app.playing() and not self.paused
        if live:
            cv.blit565_resize(gc._buf, gc.w, gc.h, gx, gy, gw, gh)
        elif s == 1:
            cv.tint565_at(gc._buf, gc.w, 0, 0, gc.w, gc.h, gx, gy, th["panel"], 140)
        else:
            # The still dimmed at the game's own size, then scaled: the same
            # pixels as the panel's colour over the scaled frame, at a
            # scale's square fewer blends.
            dim = moybuf.alloc(2 * gc.w * gc.h)
            cv.tint565(dim, gc._buf, gc.w, 0, 0, gc.w, gc.h, th["panel"], 140)
            cv.blit565_resize(dim, gc.w, gc.h, gx, gy, gw, gh)
            moybuf.free(dim)
        if not live:
            d = 48 * u                  # Play over the still (a tap on the slot plays)
            _V.glyph(cv, "run", (gx + (gw - d) // 2, gy + (gh - d) // 2, d, d), th["ink"], u)
        cv.clip()
        self._still = None if live else (gx, gy, gw, gh)
        self._still_at = (gx, gy, gw, gh)

    def _draw_loupe(self, cv, th, u):
        """The Sheet's loupe (EDITOR_LAYOUT.md): the tile under a held press
        at 3x its 16 px, on a card over the finger, inside the surface."""
        t, px, py = self._loupe
        sh = self.ws.sheet
        if sh is None:
            return
        s = LOUPE * 2 * u
        d = 8 * s
        m = 4 * u
        bw = d + 2 * m
        x = max(0, min(cv.w - bw, px - bw // 2))
        y = py - bw - 20 * u
        if y < 0:
            y = py + 20 * u
        cv.rrect(x, y, bw, bw, 6 * u, th["surface"], th["border"])
        cv.rect(x + m, y + m, d, d, th["surface_alt"])
        ox, oy = sh.tile_origin(t)
        cv.sspr(sh, ox, oy, 8, 8, x + m, y + m, d, d, 0)

    def _cur_sprite(self):
        """The sprite the Sheet and the Reference mark: the Sprite pane's,
        else the last picked."""
        ws = self.ws
        return ws.paint.n if ws.paint is not None else self._picked

    def _pick(self, t):
        """A sprite picked on the Sheet: the Sprite pane's and the map's
        brush, as a tap on the sheet picks today (no undo step)."""
        ws = self.ws
        self._picked = t
        if ws.paint is not None:
            ws.paint.n = t
        mu = ws.built("map_ui")
        if mu is not None and getattr(mu, "mapedit", None) is not None:
            mu.mapedit.n = t
        ws.mark_dirty()

    # -- input ----------------------------------------------------------------

    def handle_input(self, i):
        ws = self.ws
        ev = getattr(i, "key_event", 0) or 0
        fresh = ev != 0 and ev != self._ev
        self._ev = ev
        self._fresh = ev if fresh else 0
        if fresh and self._chord(ev & 0xFFFF, ev >> _MODS_AT):
            i.clear_edges()
            self._acts += 1
            return True
        if self._pad(i):
            i.clear_edges()
            ws.mark_dirty()
            self._acts += 1
            return True
        if self.grown is not None and i.pressed("stop") and self.escape():
            self._acts += 1
            return True
        if self._view_wheel(i):
            self._acts += 1
            return True
        h = self._head_open()
        if h is not None:
            h._page().keys(i)           # (its page's damage marks what the keys moved)
            self._acts += 1
            return True
        got = self._prompt()
        if got is not None:
            # a prompt up takes the keys, whichever pane holds them
            tab, _layer, pane, r = got
            layer = ws.layer_of(tab)
            return layer is not None and bool(
                self._in_pane(tab, self._body(r, self._unit(), pane), layer.handle_input, i))
        pane, r, _p = self.focused()
        c = self.tab_of(pane)
        tab = P.CONTENTS[c][2]
        if c == "music":
            snd = ws.music_ui.sound
            if snd.asking():
                # a popover up takes the keys (the name's field, the menu's rows)
                if self.alone() is not None:
                    r = self._area()
                self._in_pane(tab, self._body(r, self._unit(), pane), snd.page_keys, i)
            elif snd.keys(self, i, self._fresh):
                i.spend_edges()                 # a held arrow keeps its repeats
            else:
                self.head(self._focus.get(self.key, 0))._page().keys(i)
            return True
        if tab is not None:
            layer = ws.layer_of(tab)
            if layer is not None:
                if self.alone() is not None:
                    r = self._area()
                got = bool(self._in_pane(tab, self._body(r, self._unit()),
                                         layer.handle_input, i))
                if i.last_key or self._fresh or i.any_pressed():
                    self._owe_restart(tab)     # only a key edits: the check reads the doc
                return got
        if c in Parts.PAGES:
            self.part(c)._page().keys(i)
            if c == "actor":
                self._owe_restart("scene")
            return True
        return False

    def dock_keys(self, i):
        """The Editor's chords while the docked game holds the keys
        (`WindowedWM._route_key`): Ctrl+Enter, Ctrl+., the workspaces, F6."""
        ev = getattr(i, "key_event", 0) or 0
        fresh = ev != 0 and ev != self._ev
        self._ev = ev
        mods = ev >> _MODS_AT
        if not fresh or not (mods & _CTRL or (ev & 0xFFFF) == _F6):
            return False
        if (ev & 0xFFFF) == _F6:
            self.ws.wm.move_focus("menu")
        if self._chord(ev & 0xFFFF, mods):
            i.clear_edges()
            return True
        return False

    def _origin(self):
        """Where the Editor's surface sits on the glass: its window's
        content rect's corner on the desk."""
        wins = getattr(self.ws.wm, "windows", None)
        win = wins.get("menu") if wins else None
        if win is None:
            return 0, 0
        r = win.content_rect()
        return r[0], r[1]

    def _view_wheel(self, i):
        """The wheel and the middle button over the Map and the Scene
        (EDITOR_LAYOUT.md's pointing table): the wheel zooms in whole steps
        about the pointer, Shift+wheel and the wheel across pan, a middle
        drag pans. True where one acted."""
        ws = self.ws
        wy = getattr(i, "wheel_y", 0) or 0
        wx = getattr(i, "wheel_x", 0) or 0
        mid = bool((getattr(i, "pointer_buttons", 0) or 0) & _PB_MIDDLE)
        p = ws.pointer
        if not (wx or wy or mid or self._mid is not None):
            return False
        ox, oy = self._origin()
        px, py = p.x - ox, p.y - oy
        hit = None
        for _n, pane, r in self._shown_panes():
            if r[0] <= px < r[0] + r[2] and r[1] <= py < r[1] + r[3]:
                hit = (pane, r)
        if not mid:
            self._mid = None
        if hit is None:
            return False
        tab = P.CONTENTS[self.tab_of(hit[0])][2]
        if tab not in ("map", "scene"):
            if tab is None and self.tab_of(hit[0]) in ("sheet", "sprites", "stamps") and wy:
                self._sheet_page = max(0, min(3, self._sheet_page + (1 if wy > 0 else -1)))
                ws.mark_dirty()
                return True
            if tab is None and wy and self.tab_of(hit[0]) == "maps":
                self.part("maps").map_wheel(1 if wy > 0 else -1)
                return True
            if tab is None and wy and self.tab_of(hit[0]) in Parts.PAGES:
                # a part's list or text view takes the wheel where it rests
                host = self.part(self.tab_of(hit[0]))._host
                host.point(px, py, False)
                if host.wheel(0, wy):
                    ws.mark_dirty()
                return True
            return False
        body = self._body(hit[1], self._unit())
        lx, ly = px - body[0], py - body[1]
        view = ws.map_ui if tab == "map" else ws.scene_ui
        shift = (getattr(i, "mods", 0) or 0) & _SHIFT
        if mid:
            last = self._mid
            self._mid = (p.x, p.y)
            if last is not None and (p.x, p.y) != last:
                self._in_pane(tab, body, view.drag_pan, p.x - last[0], p.y - last[1])
                ws.mark_dirty()
            return True
        if shift and wy:
            wx, wy = wy, 0
        if wx:
            self._in_pane(tab, body, view.drag_pan, -wx * 24 * self._unit(), 0)
        if wy:
            self._in_pane(tab, body, view.wheel_zoom, lx, ly, -1 if wy < 0 else 1)
        ws.mark_dirty()
        return True

    def caret_keys(self):
        """Whether the arrows are a caret's: off the desk's workspaces, or
        while the focused pane is the Code tab or theme Config (another pane
        takes its own arrows)."""
        return not self.active() or self.tab_of(self.focused()[0]) in _TEXT_PANES

    def shows(self, content):
        """Whether a pane on show holds `content` as its open tab."""
        return any(self.tab_of(p) == content for _n, p, _r in self._shown_panes())

    def header_rect(self, content):
        """The header of the pane showing `content`, or None."""
        for _n, p, r in self._shown_panes():
            if self.tab_of(p) == content:
                return (r[0], r[1], r[2], self._head_h(self._unit()))
        return None

    def _owe_restart(self, tab):
        """E-02 (`EditorApp.owe_restart`): a map, scene or code edit made in
        a pane waits for the next Play. Sprite, sound and flag edits reach
        the running game at once (the sheet, bank and flags are shared)."""
        app = self.ws.editor_app
        if tab in ("map", "scene", "code") and not app._tab_is_clean(tab):
            app.owe_restart(tab)

    def escape(self):
        """Esc: a grown pane goes back (it never leaves full screen, and the
        Code pane keeps it for its popovers). True where it acted."""
        if self.grown is None or self.tab_of(self.focused()[0]) == "code":
            return False
        self.grow()
        return True

    def back(self):
        """The console's back over the desk Editor (`InputPolicy.step`):
        a grown pane goes back."""
        return self.escape()

    def _chord(self, code, mods):
        """The workspace keys (EDITOR_LAYOUT.md's input table): True where
        one acted."""
        ws = self.ws
        app = ws.editor_app
        ctrl = mods & _CTRL
        if ctrl and mods & _ALT and code in (_LEFT, _RIGHT, _UP, _DOWN):
            return self._nudge(code)
        if ctrl and not mods & (_ALT | _SHIFT) and ord("1") <= code <= ord("5"):
            keys = self.keys()
            n = code - ord("1")
            return (n < len(keys) and self.switch(keys[n])) or True
        if ctrl and code == 9:                          # Ctrl+Tab, Ctrl+Shift+Tab
            self.step(-1 if mods & _SHIFT else 1)
            return True
        if ctrl and code in (ord("]"), ord("[")):       # the browser's Ctrl+Tab
            self.step(1 if code == ord("]") else -1)
            return True
        if code == _F6 and not ctrl:
            self.focus_pane(self._focus.get(self.key, 0) + (-1 if mods & _SHIFT else 1))
            return True
        if ctrl and code in _ENTERS:
            if mods & _SHIFT:
                self.grow(self.focused()[0])
            elif app.playing():
                ws.defer(app.restart)
            else:
                ws.defer(ws.text.leave_menu)
            return True
        if ctrl and code == ord("."):
            if app.playing():
                ws.wm.close_player()
            return True
        if ctrl and code == ord("0"):
            self.placed()
            self._page().reset_sizes()
            self._sizes_moved()
            return True
        return False

    def _pad(self, i):
        """The pad's rows (EDITOR_LAYOUT.md's input table): Select and the
        d-pad move the keys to the pane that way, Select+A grows the focused
        pane. True where one acted."""
        if not i.held("select"):
            return False
        if i.pressed("a"):
            self.grow(self.focused()[0])
            return True
        for name, dx, dy in _PAD_DIRS:
            if i.pressed(name):
                # the pane that way, of the splits' panes (their focus)
                b = self._box
                f = self.focused()[1] if self.alone() is None else self._area()
                if self._host.split_toward(f[0] + f[2] // 2, f[1] + f[3] // 2, dx, dy, b):
                    cx, cy = b[0] + b[2] // 2, b[1] + b[3] // 2
                    for n, _p, r in self._shown_panes():
                        if r[0] <= cx < r[0] + r[2] and r[1] <= cy < r[1] + r[3]:
                            self.focus_pane(n)
                return True
        return False

    def select_start(self):
        """Select+Start (the pad's Play): Play, or Restart while the
        playtest runs, where the keys are the Editor's or its docked game's.
        True where it acted, so Start does not also open the system menu."""
        ws = self.ws
        if not self.active():
            return False
        holder = ws.wm.input_holder()
        win = ws.wm.windows.get("desktop")
        if holder != "menu" and not (holder == "desktop" and win is not None and win.docked):
            return False
        app = ws.editor_app
        ws.defer(app.restart if app.playing() else ws.text.leave_menu)
        return True

    def _nudge(self, code):
        """Ctrl+Alt+arrows: the focused pane's right (left and right) or
        bottom (up and down) divider moves 8 units (its page's `nudge`)."""
        self.placed()
        page = self._page()
        keys = page.desk_keys
        page.pane_cur = keys[min(self._focus.get(self.key, 0), len(keys) - 1)]
        gen = page.size_gen
        page.nudge(code)
        if page.size_gen != gen:
            self._sizes_moved()
        return True

    def handle_pointer(self, px, py, click):
        self._in_code = False
        got = self._pointer(px, py, click)
        if (click or self.ws.pointer.down) and not self._in_code:
            self._acts += 1             # a press no pane's own frames hold
        return got

    def _pointer(self, px, py, click):
        ws = self.ws
        down = ws.pointer.down
        was, self._was_down = self._was_down, down
        if self._on_div:
            # a divider's press, its drag and its release are the frame's
            # (`_dividers`)
            if self._host.point(px, py, click, down):
                ws.mark_dirty()
            if not down:
                self._on_div = False
            return True
        lay = ws.layout
        if py < lay.cy:
            if click:
                return bool(ws.bar_layer.handle_bar_tap("menu", px, py))
            return False
        if click:
            if self.alone() is None and self._host.split_at(px, py):
                self._on_div = True
                self._press = None
                self._host.point(px, py, click, down)
                ws.mark_dirty()
                return True
            self._press = None
            for n, pane, r in self._shown_panes():
                if r[0] <= px < r[0] + r[2] and r[1] <= py < r[1] + r[3]:
                    self._press = (n, pane, r)
                    if n != self._focus.get(self.key, 0):
                        self.focus_pane(n)
                    break
        elif not down and not was and ws.pointer.hovers and self._head_open() is None:
            over = self._head_at(px, py)    # a mouse over a header: what it rests on hovers
            if over is not None or self._head_over is not None:
                if over != self._head_over:
                    self._head_due = True   # the header's pass answers it: a whole frame
                    ws.mark_dirty()
                self._head_over = over
                if over is not None:
                    self.head(over[0]).handle_pointer(px, py, False)
                    return True
        h = self._head_open()
        if h is not None:
            r = h._rect
            if click and r is not None and not (r[0] <= px < r[0] + r[2] and r[1] <= py < r[1] + r[3]):
                h.close_pop()           # a press off its pane closes its menu
            else:
                h.handle_pointer(px, py, click)     # (its page's damage marks what moved)
            return True
        p = self._press
        if p is None:
            return False
        n, pane, r = p
        u = self._unit()
        head = 0 if self._headless(pane) else self._head_h(u)
        if click and py < r[1] + head and px < self._tools_x.get(n, r[0] + r[2]):
            if self._double(("head", pane), _ticks_ms()):
                self.grow(pane)
                return True
        if click and py < r[1] + head:
            self._head_down = n         # its drag and release are the header's too
        if py < r[1] + head or self._head_down == n:
            if not down and not click:
                self._head_down = None
            if click or down or self._head_down is not None:
                self._head_due = True   # the header's pass answers it: a whole frame
            self.head(n).handle_pointer(px, py, click)
            return True
        c = self.tab_of(pane)
        body = self._body(r, u, pane)
        tab = P.CONTENTS[c][2]
        if c == "music":
            self._in_pane(tab, body, ws.music_ui.sound.handle_pointer, px - body[0], py - body[1], click)
            ws.mark_dirty()
            self._in_code = True
            return True
        if tab is not None:
            layer = ws.layer_of(tab)
            if layer is None:
                return False
            got = bool(self._in_pane(tab, body, layer.handle_pointer,
                                     px - body[0], py - body[1], click))
            self._in_code = c in _OWN_FRAMES
            if click or tab != "code":
                self._owe_restart(tab)         # Code's pointer edits are taps (its keys)
            if tab == "scene" and self._blocks():
                ws.block_ui._sync_target_from_scene()   # its scripts, in the Blocks pane
            return got
        if c == "game":
            if click and (self.paused or not ws.editor_app.playing()):
                self._play_slot()
            return True
        if c in Parts.PAGES:
            self.part(c).handle_pointer(px, py, click)
            ws.mark_dirty()
            if c == "actor":
                self._owe_restart("scene")
            return True
        return True

    def _head_at(self, px, py):
        """(pane index, x, y) where (px, py) is on a shown pane's header,
        else None."""
        u = self._unit()
        for n, pane, r in self._shown_panes():
            if (not self._headless(pane) and r[0] <= px < r[0] + r[2]
                    and r[1] <= py < r[1] + self._head_h(u)):
                return (n, px, py)
        return None

    def _shown_panes(self):
        alone = self.alone()
        if alone is not None:
            for n, (pane, _r, _p) in enumerate(self.panes()):
                if pane == alone:
                    return [(n, pane, self._area())]
        return [(n, pane, r) for n, (pane, r, _p) in enumerate(self.panes())]

    def _double(self, target, now):
        was, t = self._last
        self._last = (target, now)
        if was == target and _ticks_diff(now, t) < _DOUBLE_MS:
            self._last = (None, 0)
            return True
        return False

