# Map (grep -n a name to jump there):
#   new_tile                    the "+ New" card
#   draw_new_art                the "+ New" card's art
#   _draw_star_badge            a favourite's star on its card
#   _hint_strip                 the hint strip's rect on a glass
#   _Cells                      a grid arrangement's geometry on a glass, the engine's
#   Launcher                    the grid arrangement: a shelf of cards that scrolls sideways
#   Launcher._geom_cells        its geometry on a glass (_Cells)
#   Launcher.cover_specs        every cover the next full draw needs
#   Launcher.band_pass          the band: the engine's shelf or icons on its own app host
#   Launcher._band_picture      a card's face, kept or drawn
#   tab_count_title             the bar's title on the home: the tab's count
#   day_words                   a date as the home says it
#   desk_buttons                a card's verbs as the desk pane's buttons
"""The home's GRID arrangement and the cards every arrangement draws.

`Launcher` is the selection model (items, sel, scroll, nav) every home
arrangement shares, and the `grid` arrangement's draw
(docs/history/look_2026-10.md step 33): a shelf of cover cards in the rows
the glass holds, scrolling sideways, each band an engine table of parts
that keeps its parts (`band_pass`). Its instance is ws.launcher in the
home's `grid` arrangement; `Carousel` (home_carousel.py) and `IconHome`
(home_icons.py) are its subclasses.

Beside it, what the arrangements and the home layers share: the "+ New"
pseudo card and its art, the favourite's star, the cover decodes and their
clean scales, the hint strip's rect, the home's tabs and their nouns, the
words a card's details say (`day_words`, `text_scale`), and the desk pane's
verb buttons (`desk_buttons`, `button_kind`), whose widest sets the desk's
geometry keeps room for (`DESK_BUTTON_SETS`, `PROJECTS_BUTTON_SETS`). A
leaf: it imports no home module.
"""

from array import array

import home_band as _band
import ui_draw as _ui_draw
import cart_listing as _cl
import iconsets as _iconsets
import layout_base as _lb
from chrome import _ticks_ms, _ticks_diff
from moy_store_base import builtin_name as _builtin_name
_KEY_MASK = 0x3FFFFFFF   # a face's gen under 2**30: a small int on a board (`_face_key`)




# The "+ New" card (Make's first, an empty Mine's only) is a
# PSEUDO entry (not a real cart): a plain dict with a marker `type` + a title,
# flowing through the SAME grid (nav/sel/tile_at) as real carts, dispatched by its
# type at tap time (create a game + open the Editor). `path` is None so cart
# management (dup/del) + the icon-sheet loader skip it, and a fresh dict per call
# avoids aliasing one shared mutable tile.
NEW_TILE_TYPE = "new"
PSEUDO_TILE_TYPES = (NEW_TILE_TYPE,)

# A cover's side (SPEC.md 3.6) and the decodes of it a card draws:
# CoverCache's BASE and HALF (cover_cache.py names them).
_COVER_SIDE = 128
_COVER_BASE = 1
_COVER_HALF = 2

# The band's table of parts (`Launcher.band_pass`): its one column, a part;
# a row's one cell; the part's cell `table_part` answers.
_PART_COL = ("",)
_ROW_CELL = ("",)
_PART = array("i", [0] * 4)
_FLOOR = array("i", [0] * 4)            # a floor rect `table_floor` answers
_FACE_GEN = [0]                         # the faces' keys (`home_band.slots`), one per layer and look
_FACE_SLOTS = 128                       # the slots the engine keeps at most (`home_band.slots`)
_FACES_BYTES = 192 << 10                # the faces' layer at most: the slots a board's cards fit
_NO_KEYS = array("i", [-1, -1])         # a band paint that keeps nothing (`band_pass`)


def new_tile():
    return {"type": NEW_TILE_TYPE, "title": "New", "path": None}


# The New tile's plus across the tile, in 32nds of its side: about the
# third a hand-drawn "add" page gives it.
NEW_PLUS = 11


def draw_new_art(cv, th, rect, r, stepped, spec, fs=1):
    """The "+ New" card's picture over `rect` (corners `r`): a blank page,
    the theme's `surface`, with icon set `spec`'s plus (`iconsets.plus`) in
    `ink_accent`, the accent ink the theme holds readable on that surface.
    No rim, as a cover has none; but where the theme casts no shadow a page
    on a ground of its own colour would show only its plus, so there it is
    framed in the theme's `border`, 2 px at font scale `fs`: the page
    inside the frame keeps a cover's corners `r` and the frame's run round
    them, `r` plus its width, so the frame's corner reads rounded at 1x as
    a filled cover's does where a thin line at `r` reads square (design
    review R5-10, F6-04)."""
    x = rect[0]
    y = rect[1]
    w = rect[2]
    h = rect[3]
    if not _ui_draw.depth()[5]:
        line = 2 * fs
        cv.rrect(x, y, w, h, r + line, th.get("border", 0), stepped=stepped)
        cv.rrect(x + line, y + line, w - 2 * line, h - 2 * line, r, th.get("surface", 0),
                 stepped=stepped)
    else:
        cv.rrect(x, y, w, h, r, th.get("surface", 0), stepped=stepped)
    s = min(w, h) * NEW_PLUS // 32
    _iconsets.plus(cv, (x + (w - s) // 2, y + (h - s) // 2, s, s),
                   th.get("ink_accent", th.get("ink", 0)), spec, stepped)


def _dot_top(y, s, d):
    """The top of a `d`-pixel dot between words of the `ui` face drawn at
    row `y` and scale `s`: on the middle of a version 2 face's lowercase
    (its x-height taken as half its ascent), on the line's middle in a
    pixel face."""
    f = _ui_draw.font()
    if not _ui_draw.font_v2(f[0]):
        return y + (f[2] * s - d) // 2
    asc = f[3] * s
    return y + asc - (asc // 2 + d) // 2


_STAR = {}           # chip side -> (edge runs, inside runs) of its star


def _star_runs(side):
    """The star of a `side`-square chip as runs (dx, dy, w) from the chip's
    top left: (its edge, its inside). A five-pointed star, point up, about
    10 pixels across in a 16-pixel chip so the chip's rim stands clear of
    its points (design review R4-30), its box centred on the chip, sampled
    at pixel centres about the chip's centre pixel, so its halves mirror
    each other; its edge the pixels with a side out of it. Made once a
    side."""
    got = _STAR.get(side)
    if got is not None:
        return got
    import math
    ro = side * 0.31
    ri = ro * 0.42
    c = side // 2
    pts = []
    for k in range(10):
        a = math.pi * (k / 5.0 - 0.5)
        r = ro if k % 2 == 0 else ri
        # its points reach ro up and 0.81 ro down: lowered by half the odds
        pts.append((r * math.cos(a), r * math.sin(a) + ro * 0.095))

    def inside(px, py):
        hit = False
        j = 9
        for i in range(10):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
                hit = not hit
            j = i
        return hit

    on = [[inside(x - c, y - c) for x in range(side)] for y in range(side)]

    def edge(x, y):
        return any(not (0 <= x + dx < side and 0 <= y + dy < side and on[y + dy][x + dx])
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))

    runs = ([], [])
    for y in range(side):
        for want in (0, 1):
            x = 0
            while x < side:
                if on[y][x] and (edge(x, y) == (want == 0)):
                    x0 = x
                    while x < side and on[y][x] and (edge(x, y) == (want == 0)):
                        x += 1
                    runs[want].append((x0, y, x - x0))
                else:
                    x += 1
    got = _STAR[side] = (tuple(runs[0]), tuple(runs[1]))
    return got


def _draw_star_badge(cv, names, th, rect, on):
    """The favourite star's corner badge (#105): a round chip on the
    theme's surface holding a five-pointed star, gold inside an orange edge
    when `on`, its edge alone in the dim ink when not. The chip's rim is the
    dim ink too, so it holds on a cover as dark as the chip."""
    x, y, side, _h = rect
    cv.rrect(x, y, side, side, side // 2, th.get("surface", names["white"]),
             ring=th.get("ink_dim", names["light_grey"]))
    edge, inner = _star_runs(side)
    if on:
        gold = names["yellow"]
        for dx, dy, w in inner:
            cv.rect(x + dx, y + dy, w, 1, gold)
        ink = names["orange"]
    else:
        ink = th.get("ink_dim", names["light_grey"])
    for dx, dy, w in edge:
        cv.rect(x + dx, y + dy, w, 1, ink)


def _draw_broken_badge(cv, names, th, rect):
    """The crash guard's corner badge on a cart it turned off (#160): the
    favourite star's round chip on the theme's surface, ringed in red and
    holding a red cross."""
    x, y, side, _h = rect
    red = names["red"]
    cv.rrect(x, y, side, side, side // 2, th.get("surface", names["white"]), ring=red)
    t = max(2, side // 7)
    m = side * 2 // 7               # the cross's inset from the chip's edge
    n = side - 2 * m - t + 1        # its rows
    for k in range(n):
        cv.rect(x + m + k, y + m + k, t, 1, red)
        cv.rect(x + side - m - t - k, y + m + k, t, 1, red)


# The value_row metrics' slots (MOY_UI_M_VALUE_ROW_*): the desk's key cap, and
# the band of hints, the handheld's and the desk's.
VR_KEY_DESK, VR_HINTS, VR_HINTS_DESK = 15, 16, 17


def _hint_strip(lay, keys, desk):
    """The home's hint strip along the content's foot, (x, y, w, h): the
    handheld's 20 rows at the font scale, the desk's 34 glass pixels at the
    target's 1x or its key caps' height at the font scale where they are
    taller, none under touch (no `keys`), whose cards take its height.
    Every arrangement's, so the strip stays put across them."""
    if desk:
        cap = _ui_draw.metrics("value_row")[VR_KEY_DESK] * lay.fs
        h = max(34 // _lb.render_scale(), cap) if keys else 0
    else:
        h = 20 * lay.fs if keys else 0
    return (lay.cx, lay.cy + lay.ch - h, lay.cw, h)


# The cells' geometry words (moy_ui_api.h's MOY_UI_CELLS_*) and the words of the band's cells
# as its last frame left them (moy_uitree.h's uit_cells): their scroll, their motion (drag,
# fling bits), the card the keys are on, whether they held the keys.
(_G_SIDE, _G_R, _G_X0, _G_Y0, _G_PX, _G_PY, _G_ROWS, _G_COLS, _G_TITLE_DY, _G_TITLE_W, _G_GROW,
 _G_CAP_H, _G_VIEW_H) = range(13)
_W_SCROLL, _W_MOTION, _W_CUR, _W_FOCUS = 20, 21, 22, 24
_DRAG, _FLING = 1, 2


class _Cells:
    """A grid arrangement's geometry on a glass (`Launcher._cells`): `side`
    the card's (or tile's) square, its corners `r`; the first cell's left
    `x0` and top `y0` at scroll 0; the pitches `px` and `py`; the `rows`
    and `cols` the glass shows whole or cut; `band` the rect the cells lie
    in, `hints` the hint strip's and `caption` the focused cart's band (the
    handheld icons'), else None; `title_dy` the title's top under a card's,
    `title_w` its width, `grow` what focus grows a card by, `desk` the
    class."""

    def __init__(self, side, r, x0, y0, px, py, rows, cols, band, hints, caption,
                 title_dy, title_w, grow, desk):
        self.side = side
        self.r = r
        self.x0 = x0
        self.y0 = y0
        self.px = px
        self.py = py
        self.rows = rows
        self.cols = cols
        self.band = band
        self.hints = hints
        self.caption = caption
        self.title_dy = title_dy
        self.title_w = title_w
        self.grow = grow
        self.desk = desk


class Launcher:
    """The home's grid arrangement (docs/history/look_2026-10.md step 33): a shelf
    of cards, each cart's whole cover at a clean scale with the card radius
    and its title under it cut to the card's width, in as many rows as the
    glass holds under the bar (two on the T-Deck, three on the desk),
    scrolling sideways, its columns spaced so the last one on the glass
    stands cut by a third or more. The focused card grows and wears the
    theme's ring, flat -- no shadow over its neighbours -- its title bold.
    The cards lie on the home's ground, the tabs in the bar and the verbs in
    the hint strip, as the carousel's do: Enter plays, C changes.

    Keeps the selection model (items, sel, selected) the console relies on;
    The cells are the band page's `ui.cards(look="shelf")` (`home_ui.shelf`):
    the engine lays them out, draws them and moves them (keys, a drag, a
    fling, a tap), and `scroll` reads its offset along `horizontal`'s axis
    back from the engine's words. `IconHome` is the same model over
    `look="icons"`, a grid of tiles that scrolls down.

    `names` (the palette) is injected so the card draw stays free of a
    console back-import."""

    arrangement = "grid"          # the layout's `home` value this class draws
    horizontal = True             # the axis the cells scroll on
    page_fn = "shelf"             # its band's page (home_ui)

    tab_focus = False             # the tab row holds the focus, not a card

    def __init__(self, items, layout=None, names=None):
        self.items = items
        self.tab = HOME_TABS[0][0]   # the home's active tab (ws.home.set_home_tab)
        self.tab_sel = {}            # tab -> the path its card was on when left
        # bumped whenever anything the bar's zone shows changes (BarLayer
        # folds it into its cache key); set before `sel`, whose setter reads it
        self.zone_gen = 0
        self.sel = 0
        self._NAMES = names
        self.theme = None             # chrome THEME tokens (look.set_theme pushes them)
        self.icon_spec = None         # optional () -> the live icon set: "+ New"'s plus
        self.cover_for = None         # optional (cart, div) -> the cart's decoded
                                      # cover (CoverCache.cover_for, SPEC.md 3.6)
        self.covers = None            # optional: the cover cache whose `gen` the covers
                                      # `cover_for` answered are kept over (`_cover_of`)
        self.cover_ready = None       # optional (cart, div) -> the decoded cover, None
                                      # for none, False not yet (CoverCache.ready_for)
        self.tinted_for = None        # optional (cart, colour, alpha) -> the
                                      # cover dimmed (CoverCache.tinted)
        self.dim = None               # (colour, alpha 0..255): the theme dims the
                                      # carousel's neighbours (`dim_neighbours`)
        self.wall_ink = None          # (white, black) over a wallpaper (_wall_ink)
        self.ground = None            # the home's ground's colour (_ground_of)
        self.favorite_for = None      # optional cart -> bool (ws.carts.is_favorite)
        self.broken_for = None        # optional cart -> bool (ws.spine.cart_broken)
        self.broken_ids = None        # optional () -> what broken_for answers from
        self.own_for = None           # optional cart -> bool (ws.carts.is_own)
        self.plays_for = None         # optional cart -> its play record (ws.carts.plays)
        self.today_for = None         # optional () -> today as YYYYMMDD, 0 unknown
        self._card_clip = None        # the clip cards draw in while a draw runs
        self.restore_whole = False    # a band's backdrop goes back in one copy (the home's)
        self.face_key = None          # (look gen, plain ground or None): the cards'
                                      # faces are kept (`_faces_for`); None: drawn
        self.frame_no = 0             # the painted frame a paint is (the home's)
        self._face_lay = None         # the faces' layer: square slots stacked down
        self._face_geo = None         # ...the canvas, card side, margin and slots it is for
        self._face_fill = None        # ...each slot's title tile (block, letter's rects)
        self._face_of = None          # the face_key the engine's key (`_fkey`) is of
        self._fkey = 0
        self._fdiv = 0                # the cover decode, corners and ring a paint's
        self._fstepped = False        # faces are drawn with (`_faces_for`)
        self._fring = None
        self._faces_off = False       # a canvas whose layers hold no pixels
        self._faces_done = False      # a round of `mint_faces` found every face drawn
        self._c = None                # the cells laid out, and what for
        self._c_key = None
        self._host = None             # the band's app host (`band_pass`)
        self._rows = []               # the desk carousel's shelf's rows (`_band_rows`)
        self.floor = []               # the rects the band's frame draws (`band_floor`)
        self.copied = []              # ...and those it copied out of the last frame's buffer
        self.shifted = []             # (the desk carousel's: none)
        self._bpage = None            # the band's page (`_band_page`)
        self._cw = array("i", [0] * 25)     # its cells as its last frame left them (`_words`)
        self._cw_ok = False           # ...where a pass drew them
        self._cq = array("i", [0] * 4)      # a band (`_geom_cells`)
        self._cg = array("i", [0] * 16)     # ...and the cells' geometry in it
        self._ct = array("i", [0] * 4)      # a card's box (`tile_rect`)
        self._put = None              # what its rows were put from: (items, their play records)
        self._set = None              # ...and its current card and words' ink (`band_set`)
        self._pic_ix = {}             # a card's picture name -> its item
        self._fkeys = array("i")      # each card's title and type, as its face's gen (`_face_key`)
        self._covs = []               # each card's cover as `cover_for` answered it (`_cover_of`)
        self._covs_at = (-1, 0)       # ...the cover cache's gen and the decode they hold
        self._gcv = None              # the canvas a pass draws on
        self._fpend = False           # the faces are yet to be taken this pass (`_band_picture`)
        self._faces = False           # ...and whether it stamps them
        self._fed = False             # its host took input since its last pass
        self.on_open = None           # () -> the band's card opened (Enter, a tap)
        if layout is None:
            # a bare Launcher(items) (unit construction); lazy, so there is
            # no launcher_layer<->console module-load cycle
            from console import Layout
            layout = Layout()
        self.set_layout(layout)

    def set_layout(self, layout):
        """Adopt a new layout (a size or font-scale change). The scroll is
        not re-clamped here (it clamps lazily on read): the windowed tier
        applies every window's layout to both home models on each context
        switch, and an eager clamp against a small window would lose the
        position. The scroll ring keys on the geometry itself
        (`_statics_base`), so a paint recorded under another layout never
        matches."""
        self.layout = layout

    # -- geometry ------------------------------------------------------------

    def _cells(self):
        """The cells on the class in force (`_Cells`): the band's page's
        geometry (moy_ui_api_cells_geom, `_geom_cells`), laid out once per
        layout, theme depth and input."""
        lay = self.layout
        keys = _ui_draw.hint_kind() != "touch"     # touch alone shows no hint strip
        depth = _ui_draw.depth()
        k = self._c_key
        if k is not None and k[0] is lay and k[1] == keys and k[2] is depth:
            return self._c
        self._c = self._geom_cells(lay, keys, _lb.metric_class() != _lb.HANDHELD)
        self._c_key = (lay, keys, depth)
        return self._c

    def _geom_cells(self, lay, keys, desk):
        """The cells' geometry: the band from the content's top to the hint
        strip (`_hint_strip`) and the engine's grid in it (the page's
        `cells_geom`)."""
        hints = _hint_strip(lay, keys, desk)
        band = (lay.cx, lay.cy, lay.cw, hints[1] - lay.cy)
        q = self._cq
        q[0], q[1], q[2], q[3] = band
        g = self._cg
        self._band_page().cells_geom(q, lay.fs, desk, g)
        cap = None
        if g[_G_CAP_H]:
            cap = (band[0], band[1] + g[_G_VIEW_H], band[2], g[_G_CAP_H])
        return _Cells(g[_G_SIDE], g[_G_R], g[_G_X0], g[_G_Y0], g[_G_PX], g[_G_PY], g[_G_ROWS],
                      g[_G_COLS], band, hints, cap, g[_G_TITLE_DY], g[_G_TITLE_W], g[_G_GROW], desk)

    def handheld(self):
        return not self._cells().desk

    def desk(self):
        """Whether the home lays out on the desk's metrics: its hint strip's
        and its tabs' sizes."""
        return self._cells().desk

    def foot(self):
        """The hint strip's rect last, as the carousel's `foot` answers it."""
        return (0, 0, 0, 0, 0, self._cells().hints)

    def hero_rect(self):
        return None

    def quiet(self):
        """The rectangles a per-glass wallpaper keeps its subject out of
        (docs/theme_and_shell_2026-11.md §3.9): the cells' band and the hint strip."""
        c = self._cells()
        return (c.band, c.hints)

    def band_rect(self):
        """The rect the cells lie in (the icons' caption band under them):
        the band frame's fill and damage."""
        return self._cells().band

    def grow(self):
        """What focus grows a card by, on each side."""
        return self._cells().grow

    def top_row(self):
        """Whether the selected card stands in the cells' top row, where up
        takes the keys to the tabs."""
        c = self._cells()
        return not self.items or (self.sel % c.rows == 0 if self.horizontal
                                  else self.sel < c.cols)

    # -- selection ----------------------------------------------------------

    @property
    def sel(self):
        return self._sel

    @sel.setter
    def sel(self, value):
        # bump zone_gen on every actual change, whatever the call site, so
        # BarLayer's cache key can trust it
        if value != getattr(self, "_sel", None):
            self.zone_gen += 1
        self._sel = value

    def set_items(self, items):
        """Replace the cart list (after a create/duplicate/delete) and re-clamp the
        selection so it does not dangle past the new end."""
        self.items = items
        self.zone_gen += 1          # a rename can change the title under an unchanged sel
        if self.sel >= len(items):
            self.sel = max(0, len(items) - 1)
        self._scroll_to_sel()

    def selected(self):
        return self.items[self.sel] if self.items else None

    # -- the motion: the engine's --------------------------------------------

    def _words(self):
        """The band page's cells as its last frame left them (`_cw`,
        moy_uitree.h's uit_cells), else None before its first frame."""
        return self._cw if self._cw_ok else None

    @property
    def scroll(self):
        """The cells' scroll as the band's last frame left it."""
        w = self._words()
        return w[_W_SCROLL] if w is not None else 0

    @scroll.setter
    def scroll(self, value):
        """The engine's: the selection's card is in view (`_scroll_to_sel`)."""

    @property
    def dragging(self):
        """True while a drag (past the slop) moves the cells."""
        w = self._words()
        return w is not None and w[_W_MOTION] & _DRAG != 0

    @property
    def flinging(self):
        """True while a released fling carries the cells."""
        w = self._words()
        return w is not None and w[_W_MOTION] & _FLING != 0

    @property
    def moving(self):
        w = self._words()
        return w is not None and w[_W_MOTION] != 0

    def anim_frame(self, dt):
        """The cells move themselves in their band's pass."""
        return False

    def _scroll_to_sel(self):
        """The selection made from outside: the band's page lands on it,
        in view with its margin, at its next pass (`band_set`)."""

    def band_keys(self, i):
        """The keys this frame, the band page's (its cells step, scroll and
        open themselves): whether a frame is owed, which then draws the
        band (`band_pass`)."""
        fed = self._band_host().keys(i)
        if fed:
            self._fed = True
        return fed

    def band_point(self, px, py, click, down):
        """A pointer sample, the band host's (a drag scrolls the cells and a
        release flings them, a tap opens a card): whether it is the band's,
        or the band owes a frame, which then draws the band."""
        h = self._band_host()
        fed = h.point(px, py, click, down) or h.owed
        if fed:
            self._fed = True
        return fed

    def band_cancel(self):
        """The gesture on the band ends untapped (a long press took it)."""
        self._band_host().clear()

    # -- cells ----------------------------------------------------------------

    def tile_rect(self, i):
        """Card `i`'s box as the band's last frame laid it out, or None where
        it lies outside the band."""
        t = self._ct
        if not (0 <= i < len(self.items)) or not self._band_page().cells_tile(i, t):
            return None
        return (t[0], t[1], t[2], t[3])

    def tile_at(self, px, py):
        """The card whose box or title lies under (px, py) in the band."""
        i = self._band_page().cells_at(px, py)
        return i if 0 <= i < len(self.items) else None

    def favorite_rect(self, i):
        """No badge on a cell: F and the card's menu star it."""
        return None

    def action_rects(self):
        return None

    def statics_sel(self):
        return -1

    def paint_key(self):
        """What a recorded paint's band pixels depend on besides the offset:
        the selection, whose card wears the ring."""
        return self.sel

    def band_key(self):
        """What the band's every card is a function of beside the look, the
        covers and its row's cards (`band_pass`'s key): nothing; the
        selection's card is its row's gen."""
        return None

    def cover_specs(self):
        """Every (cart, div) cover the next full draw requests: each card's
        whole cover at its clean side's decode."""
        div = self._face_div(self._cells().side)
        return [(it, div) for it in self.items
                if it.get("path") and it.get("type") not in PSEUDO_TILE_TYPES]

    # -- the draw -------------------------------------------------------------

    def draw(self, cv, sheet_for=None, key=_NO_KEYS, over=None, beside=None):
        """The band's cells over the backdrop the home drew (a full paint's):
        drawn whole (`band_pass`); the floor's end."""
        return self.band_pass(cv, sheet_for, None, key, True, over, beside)

    def repaint_band(self, cv, sheet_for, fill, key=_NO_KEYS, over=None, beside=None, need=False):
        """A band frame: the band (`band_pass`), the ground put back by
        `fill(cv, rect)` under it."""
        return self.band_pass(cv, sheet_for, fill, key, False, over, beside, need)

    def _band_host(self):
        """The band's app host (`ui_draw.AppHost`): the context its table
        is drawn in, made once."""
        h = self._host
        if h is None:
            h = self._host = _ui_draw.AppHost()
        return h

    def _band_rows(self, n):
        """The band table's rows, `n` of them, each one cell: kept while `n`
        is (the desk carousel's shelf)."""
        rows = self._rows
        if len(rows) != n:
            rows = self._rows = [_ROW_CELL] * n
        return rows

    def begin_band_host(self, cv):
        """Begin this painted frame's paint on the band's host, drawing
        nothing, its keys the cards' where they hold them (as the band's
        pass begins it): the parts the home names there (`home_band.held`) are
        then asked for, the band's pass resuming it."""
        host = self._band_host()
        host.whole()
        host.begin(cv, self.theme, self.band_rect(), self.desk(), False, self.tab_focus)

    def resume_band_host(self, cv):
        """Point the verbs at the band's host again, beginning nothing:
        the parts named in the paint this frame began there."""
        self._band_host().resume(cv, self.theme)

    def _begin_band(self, cv, b, desk, key, need, over=None, keys=False):
        """Begin the band's frame on its host, the keys its own where `keys`
        (the cards hold them, not the tab row or the desk's buttons): whether
        the buffer this frame paints holds the band as a frame drew it under
        `key` (`home_band.held`); None, with the frame ended, where `need` asks for
        that and it does not. A frame begun on it already (`begin_band_host`,
        an earlier pass) resumes: its page's motion steps once a frame."""
        host = self._band_host()
        if host.begun():
            host.resume(cv, self.theme)     # (its keys and its clock the frame's first pass's)
        else:
            host.whole()
            host.begin(cv, self.theme, b, desk, False, not keys)
        # (a stamp drawn over the frame round the band: no later frame of
        # the band's puts that buffer's frame back)
        held = _band.held("band", key[0] if over is None or (
            b[0] <= over[0] and over[0] + over[2] <= b[0] + b[2]
            and b[1] <= over[1] and over[1] + over[3] <= b[1] + b[3]) else -1)
        if need and not held:
            host.end()
            return None
        return held

    def band_floor(self, cv, fill, copy=True):
        """The floor of the band's table (`home_band.table_floor`): each rect the
        frame draws, kept in `floor`, its ground put back by `fill` where
        given; then the floor's end. With `copy`, first the rects the
        buffer the last frame painted holds as this frame draws them
        (`home_band.table_copy`), copied out of it (`copy_last`) into `copied`:
        the double buffer's catch-up of a step costs a copy, not its
        cards."""
        fl = self.floor
        del fl[:]
        cp = self.copied
        del cp[:]
        r = _FLOOR
        cl = getattr(cv, "copy_last", None) if copy else None
        if cl is not None:
            while _band.table_copy(r) > 0:
                if not cl(r[0], r[1], r[2], r[3]):
                    _band.table_copy(r, True)  # (drawn: the floor answers it)
                    break
                cp.append((r[0], r[1], r[2], r[3]))
        v = _band.table_floor(r)
        while v > 0:
            q = (r[0], r[1], r[2], r[3])
            fl.append(q)
            if fill is not None:
                fill(cv, q)
            v = _band.table_floor(r)
        return v

    def band_pass(self, cv, sheet_for, fill, key=_NO_KEYS, whole=True, over=None, beside=None,
                  need=False, note=False):
        """The band, on its own app host: its page (`_band_page`, the engine's
        shelf or icons: `home_ui.shelf`, `home_ui.icons`) drawn in the band,
        moving itself (its keys and its pointer the host's: `band_keys`,
        `band_point`) and ringing its current card while the cards hold the
        keys (not the tab row's), its words white over black on a wallpaper
        (`wall_ink`), every card's face the home's (`_band_picture`). It
        keeps no tiles: a pass that draws the band draws it whole, over the
        ground `fill` puts back there first (None: a full paint drew it),
        and names what it drew (`home_band.held`) so the floor's end says whether
        every buffer holds it. A pass that finds the buffer holding the band
        as it stands (nothing moving, nothing to take) and a `note` pass,
        the band lying there by other means, draw none of it and name it,
        its page standing as it was (`AppHost.stand`). `beside` draws
        first. Answers the floor's end, or None where `need` and the buffer
        does not hold the band under `key`."""
        c = self._cells()
        b = c.band
        host = self._band_host()
        held = self._begin_band(cv, b, c.desk, key, need, over, not self.tab_focus)
        if held is None:
            return None
        if key[0] < 0:
            # (the band not the home's alone on the glass: no buffer holds its frame)
            if need:
                host.end()
                return None
            held = False
        whole = whole or not held
        if beside is not None:
            beside(cv, whole)
        del self.floor[:]
        del self.copied[:]
        pg = self._band_page()
        puts = not note and self._band_cards()
        w = self._words()
        if (not note and not whole and not puts and not host.owed and not self._fed
                and w is not None and not w[_W_MOTION] and w[_W_FOCUS] != self.tab_focus
                and _band.held("cards", self._cells_key(key, w))):
            note = True                     # (the buffer holds it as it stands)
        self._fed = False
        if note:
            host.stand()                    # (where no pass of this frame draws the page)
        else:
            if fill is not None:
                fill(cv, b)
            self._gcv = cv
            self._fpend = True              # (the faces taken at the first picture)
            self.floor.append(b)
            pg.paint(0, cv, self.theme, b, c.desk)
            self._gcv = None
            self._cw_ok = pg.cells(self._cw)
            w = self._words()
        if w is not None:
            if w[_W_CUR] != self._sel and w[_W_CUR] < len(self.items):
                self.zone_gen += 1
                self._sel = w[_W_CUR]       # the keys moved the selection
            _band.held("cards", self._cells_key(key, w))
        end = 0 if _band.held_all() else -1
        host.end()
        return end

    @staticmethod
    def _cells_key(key, w):
        """What the band shows under the home's band key `key` and its
        cells' words `w`: their scroll, their motion, the current card and
        whether it wears the focus mark (-1: no buffer holds it). Each step
        held under 2**27: no long int a frame."""
        k = key[1]
        if k < 0:
            return -1
        k = ((k & 0x3fffff) * 31 + w[_W_SCROLL]) & 0x3fffff
        k = ((k * 31 + w[_W_CUR]) & 0x3fffff) * 31 + w[_W_MOTION]
        return (k & 0x3fffff) * 2 + w[_W_FOCUS]

    def _band_page(self):
        """The band's page (`page_fn`: `home_ui.shelf`, `home_ui.icons`) on
        the band's host, made at its first use: on the home's ground, its
        pictures the home's."""
        pg = self._bpage
        if pg is None:
            import uitree_app
            import home_ui
            pg = uitree_app.hosted_page(getattr(home_ui, self.page_fn), self._band_host(), self,
                                        env=self)
            pg.bare = True
            pg.band = False
            pg.pictures = self._band_picture
            pg.open()
            self._bpage = pg
        return pg

    def all(self):
        """The band page's damage: the home paints its band when it moves."""

    def _band_cards(self):
        """Put the band page's rows (`band_put`) where what they show moved:
        the items; and its current card and its words' ink (`band_set`)
        where the home moved them: whether it put either."""
        items = self.items
        p = self._put
        put = False
        if p is None or p[0] is not items or self._put_more(p):
            import home_ui
            pg = self._bpage
            pg.run(home_ui.band_put, action="band_put")
            home_ui.ui.commit(pg)
            put = True
        q = self._set
        if q is None or q[0] != self._sel or q[1] is not self.wall_ink or self._set_more(q):
            import home_ui
            pg = self._bpage
            pg.run(home_ui.band_set, action="band_set")
            home_ui.ui.commit(pg)
            put = True
        return put

    def _put_more(self, p):
        """Whether what the rows were put from moved beside the items: the
        current card's play record, which its sub line says (the icons'
        caption band)."""
        if self.horizontal:
            return False
        c = self._sel
        return c < len(p[1]) and p[1][c] != self.played(self.items[c])

    def band_put(self, s):
        """The band's cards as its page's rows (home_ui's `band_put`): each
        card's title ("New" on the "+ New" card), its metadata (`_meta`),
        apart by tabs, and its picture, which the home draws
        (`_band_picture`); and what each card's face is keyed by beside its
        path (`_face_key`)."""
        import home_ui
        items = self.items
        rows = []
        ix = {}
        recs = []
        keys = array("i")
        for i in range(len(items)):
            it = items[i]
            k = str(i)
            name = "New" if it.get("type") == NEW_TILE_TYPE else str(it.get("title") or "")
            pic = home_ui.ui.image.own(k)
            ix[repr(pic)] = i
            recs.append(self.played(it))
            keys.append((hash(it.get("title")) ^ (hash(it.get("type")) << 15)) & _KEY_MASK)
            rows.append(dict(id=k, name=name, sub="\t".join(self._meta(it)), pic=pic))
        s.cards = rows
        self._pic_ix = ix
        self._fkeys = keys
        self._covs = [None] * len(items)
        self._put = (items, recs)

    def _set_more(self, q):
        """Whether what the band's words were set from moved beside its
        current card and its ink."""
        return False

    def band_set(self, s):
        """The band's current card, the one a selection made from outside
        lands it on, and its words' ink: white (over black) on a wallpaper
        (`wall_ink`), else the theme's (home_ui's `band_set`)."""
        s.sel = str(self._sel)
        s.tone = "" if self.wall_ink is None else "#FFFFFF"
        self._set = (self._sel, self.wall_ink)

    def band_open(self, row):
        """The band page's card action (Enter, a tap on a card): the
        home's `on_open`."""
        if self.on_open is not None:
            self.on_open()

    def _band_picture(self, node, pic, r):
        """A card of the band's page (the engine's picture call, `r` its box,
        clip, flags, corners, side): its face (`_face`), out of its kept
        face where the home keeps faces and it is not the focused one
        (`_stamp_face`). Every card holds one."""
        if r is None:
            return True
        i = self._pic_ix.get(pic)
        items = self.items
        if i is None or i >= len(items):
            return False
        it = items[i]
        cv = self._gcv
        if self._fpend:
            self._fpend = False
            c = self._cells()
            self._faces = (self.face_key is not None
                           and self._faces_for(cv, c.side, c.r, self._face_cap(c)))
        cv.clip(r[4], r[5], r[6], r[7])
        if self._faces and not r[8] & 1:
            self._stamp_face(cv, it, i, r, r[9])
        else:
            self._face(cv, it, r, r[9], self._cover_of(i, it, self._face_div(r[10])))
        cv.clip()
        return True

    def _face_cap(self, c):
        """The slots the cards' faces lie in (`_faces_for`): the band's
        cards and a row past either end at least, and as many as
        `_FACES_BYTES` holds of them up to the engine's `_FACE_SLOTS`, so the
        faces of the rows a scroll passes stay drawn (an idle frame draws
        them outward from the band, `mint_faces`)."""
        least = (c.cols + 2) * c.rows if self.horizontal else (c.rows + 2) * c.cols
        s = c.side + 2 * (0 if c.r else self.layout.fs - 1)
        most = min(_FACE_SLOTS, _FACES_BYTES // (2 * s * s))
        return least if least > most else most

    def _faces_for(self, cv, side, r, cap):
        """Whether this paint stamps its cards from their kept faces
        (`home_band.slots` on the table just drawn: the engine keeps which card's
        face each slot holds), `cap` of them on canvas `cv`, drawn for
        cards of `side` with corners `r`, where the home keeps them
        (`face_key`): the faces' layer made for them, each slot the card's
        square and the square frame's margin round it. A canvas whose layer
        holds no pixels forfeits them."""
        key = self.face_key
        if key is None or self._faces_off:
            return False
        m = 0 if r else self.layout.fs - 1
        g = self._face_geo
        if (self._face_lay is None or g[0] is not cv or g[1] != side or g[2] != m
                or g[3] != cap):
            self.release_faces()
            s = side + 2 * m
            try:
                self._face_lay = cv.new_layer(s, s * cap)
            except Exception:  # noqa: BLE001 -- a recording canvas: draw the cards
                self._faces_off = True
                return False
            self._face_geo = (cv, side, m, cap)
            self._face_fill = [None] * cap
            self._face_of = None
        if self._face_of is not key:
            # (another layer or look: every face is drawn again)
            self._face_of = key
            _FACE_GEN[0] = self._fkey = (_FACE_GEN[0] + 1) & 0x3fffffff
        _band.slots(cap, self._fkey)
        self._faces_done = False         # (the table drawn: its rows to name again)
        # what every face of this paint is drawn with, read once a paint
        self._fdiv = self._face_div(side)
        self._fstepped = bool(_ui_draw.depth()[4])
        self._fring = self._face_ring()
        return True

    def release_faces(self):
        """Give the faces' layer back (the fit check's release, a layout
        change, an arrangement left): True when there was one."""
        lay = self._face_lay
        if lay is None:
            return False
        self._face_lay = None
        self._face_fill = None
        rel = getattr(lay, "release", None)
        if rel is not None:
            rel()
        return True

    def faces_bytes(self):
        """The faces' layer's bytes, 0 where none is kept."""
        if self._face_lay is None:
            return 0
        g = self._face_geo
        s = g[1] + 2 * g[2]
        return s * s * g[3] * 2

    def _face_key(self, i, cover, mint):
        """The slot of card `i`'s face (`home_band.slot`), keyed by what it is drawn
        from: its path (its title where it has none), a string its item
        holds, as the name; its title, type (an int `band_put` kept) and
        cover's serial as the gen, all under 2**30, so a frame allocates
        nothing."""
        it = self.items[i]
        gen = self._fkeys[i] ^ (0 if cover is None else cover.serial & _KEY_MASK)
        return _band.slot(it.get("path") or it.get("title") or "", gen, mint)

    def _face_div(self, n):
        """The decode a card of side `n` draws its cover from."""
        return _cover_div_for(n)

    def _cover_of(self, i, it, div):
        """The cover card `it` (index `i`) draws at decode `div`
        (`cover_for`), None for the "+ New" page and for a cart whose cover
        is not there (its title tile). A cover found is kept for the card
        until the cover cache moves (`covers.gen`) or another decode is
        asked, so a moving frame asks the cache nothing (its key a tuple
        a call)."""
        if self.cover_for is None or it.get("type") in PSEUDO_TILE_TYPES:
            return None
        if self.covers is None:
            return self.cover_for(it, div)
        covs = self._covs
        gen = self.covers.gen
        at = self._covs_at
        if at[0] != gen or at[1] != div:
            for k in range(len(covs)):
                covs[k] = None
            self._covs_at = (gen, div)
        c = covs[i] if i < len(covs) else None
        if c is None:
            c = self.cover_for(it, div)
            if i < len(covs):
                covs[i] = c
        return c

    def _face(self, cv, it, pic, r, cover):
        """A card's face over `pic` (corners `r`, the cells' radius and its
        growth): its picture (`_face_picture`), then its rim, the edge ring
        or the square frame."""
        self._face_picture(cv, it, pic, r, cover)
        if r:
            cv.rrect(pic[0], pic[1], pic[2], pic[3], r, None, ring=self._face_ring())
        else:
            self._card_frame(cv, pic)

    def _face_ring(self):
        """The colour of the edge ring a face with round corners wears
        (`_face`'s), None for none."""
        return (self.theme or {}).get("edge", 0)

    def _face_picture(self, cv, it, pic, r, cover):
        """A card's picture over `pic`, corners `r`: the "+ New" page, the
        cover drawn from `cover`, else the title tile (`_draw_picture`'s,
        undimmed, with the cover in hand)."""
        stepped = bool(_ui_draw.depth()[4])
        if it.get("type") in PSEUDO_TILE_TYPES:
            draw_new_art(cv, self.theme or {}, pic, r, stepped,
                         self.icon_spec() if self.icon_spec is not None else None,
                         self.layout.fs)
        elif cover is not None:
            cv.cover(cover.pix, cover.w, 0, 0, cover.w, cover.h, pic[0], pic[1], pic[2],
                     pic[3], r, stepped)
        else:
            self._draw_title_tile(cv, it, pic, r)

    def _stamp_face(self, cv, it, i, t, r, plain=True):
        """Card `it` (index `i`) over `t` (the picture call's box and clip,
        `_band_picture`'s), corners `r`, out of its kept face (`home_band.slot`),
        clipped to its clip: copied from the slot holding the card
        as it is now --
        whole on a plain ground, which the slot's corners were drawn over;
        over a backdrop, as where the corners lie over anything but the
        plain ground (not `plain`: the shelf's shadows), a corner's partly
        covered pixels blend over what lies under them, and are drawn as the
        card draws them (`DeviceCanvas.face`, a cover's and a title tile's;
        the "+ New" page's rows under its corners from its own draw,
        clipped). A card no slot holds is drawn as it is: a paint never
        draws a face, so a step that brings in a cold row evicts nothing
        (the idle frames' `mint_faces` draws them)."""
        x, y, n = t[0], t[1], t[2]
        cover = self._cover_of(i, it, self._fdiv)
        new = it.get("type") in PSEUDO_TILE_TYPES
        j = self._face_key(i, cover, False)
        if j < 0:
            self._face(cv, it, t, r, cover)
            return
        m = self._face_geo[2]
        s = self._face_geo[1] + 2 * m
        lay = self._face_lay
        if (self.face_key[1] is None or not plain) and (r or new):
            if m == 0 and r and not new and 2 * r < n:
                fill = self._face_fill[j]
                if cover is not None or fill is not None:
                    # the face copied, its corners' partly covered pixels
                    # drawn over what is there: one call (`DeviceCanvas.face`)
                    if cover is None:
                        cv.face(lay, j * s, x, y, n, n, None, 0, 0, 0, fill[0], fill[1], r,
                                self._fstepped, self._fring)
                    else:
                        cv.face(lay, j * s, x, y, n, n, cover.pix, cover.w, cover.w,
                                cover.h, None, None, r, self._fstepped, self._fring)
                    return
            # the "+ New" page's frame runs round its corners: its rows
            # under them drawn from its own draw, the rest copied
            k = r + 2 * self.layout.fs + 1
            if 2 * k >= n:
                y0 = y1 = y + n // 2
            else:
                y0 = y + k
                y1 = y + n - k
        else:
            y0 = y - m
            y1 = y + n + m
        # (one name a line: four names from four values build a tuple)
        bx0 = t[4]
        by0 = t[5]
        bx1 = t[4] + t[6]
        by1 = t[5] + t[7]
        ry0 = y0 if y0 > by0 else by0
        ry1 = y1 if y1 < by1 else by1
        rx0 = x - m if x - m > bx0 else bx0
        rx1 = x + n + m if x + n + m < bx1 else bx1
        if ry1 > ry0 and rx1 > rx0:
            cv.blit_strip_rect(lay, x - m, y - m - j * s, rx0, ry0, rx1 - rx0, ry1 - ry0)
        if y0 > y - m and rx1 > rx0:
            self._face_rows(cv, it, t, r, cover, rx0, rx1,
                            y - m if y - m > by0 else by0, y0 if y0 < by1 else by1)
            self._face_rows(cv, it, t, r, cover, rx0, rx1,
                            y1 if y1 > by0 else by0, y + n + m if y + n + m < by1 else by1)
            cv.clip(t[4], t[5], t[6], t[7])

    def _draw_face(self, j, it, r, cover, new):
        """Card `it`'s face drawn into slot `j`, over the plain ground where
        the faces have one, and what its corners are drawn from kept beside
        it (a title tile's block and letter)."""
        g = self._face_geo
        n = g[1]
        m = g[2]
        s = n + 2 * m
        lay = self._face_lay
        sy = j * s
        lay.clip(0, sy, s, s)
        flat = self.face_key[1]
        if flat is not None:
            lay.rect(0, sy, s, s, flat)
        self._face(lay, it, (m, sy + m, n, n), r, cover)
        lay.clip()
        self._face_fill[j] = None if cover is not None or new else \
            _ui_draw.initial_parts(lay, it.get("title") or "", n, n)

    def mint_faces(self, ms=4):
        """On a frame nothing waits on: draw the faces the engine names
        next (`home_band.slot_next`: the cards the band shows, then the rows past
        either end of it, nearest first) whose covers are decoded or known absent, for
        about `ms` -- a step then copies the row it brings in -- the walk
        itself held to `ms` too, the next such frame going on from where
        it stopped (a key between two frames waits on neither). True where
        one was drawn. A round that found every face drawn ends the asking
        until the band's table is drawn again (`_faces_for`)."""
        if self._faces_done:
            return False
        g = self._face_geo
        ready = self.cover_ready
        if (self._face_lay is None or self.face_key is None or ready is None
                or self._host is None or self._put is None or self._put[0] is not self.items):
            return False
        c = self._cells()
        if c.side != g[1] or (0 if c.r else self.layout.fs - 1) != g[2]:
            return False                 # (the faces are another layout's)
        self._host.resume(g[0], self.theme)
        items = self.items
        sel = self.sel if self._focused(True) else -1
        r = self._face_r()
        t0 = _ticks_ms()
        done = 0
        owed = False                     # a part whose cover has yet to land
        i = _band.slot_next()
        while i >= 0:
            if i < len(items) and i != sel:
                it = items[i]
                new = it.get("type") in PSEUDO_TILE_TYPES
                cover = None if new else ready(it, self._fdiv)
                if cover is False:       # (its cover lands first: the paint takes it)
                    owed = True
                else:
                    j = self._face_key(i, cover, True)
                    if j >= _band.SLOT_MINT:
                        self._draw_face(j - _band.SLOT_MINT, it, r, cover, new)
                        done += 1
            if _ticks_diff(_ticks_ms(), t0) >= ms:
                return done > 0          # (the round goes on from here next time)
            i = _band.slot_next()
        if not done and not owed:
            self._faces_done = True
        return done > 0

    def _face_r(self):
        """The corners a face is drawn with."""
        return self._cells().r

    def _face_rows(self, cv, it, t, r, cover, x0, x1, y0, y1):
        """Card `it`'s face over `t` drawn in rows [y0, y1) of columns
        [x0, x1) alone: the rows under its corners, over what is there."""
        if y1 > y0:
            cv.clip(x0, y0, x1 - x0, y1 - y0)
            self._face(cv, it, t, r, cover)

    def _focused(self, selected):
        """Whether the selected card wears the focus: the keys are on the
        cells, not the tabs or the bar."""
        return selected and not self.tab_focus

    # -- pictures -------------------------------------------------------------

    def _dims(self, centre):
        """(colour, alpha) a card's cover is dimmed toward, or None."""
        return None

    def _draw_title_tile(self, cv, it, rect, r):
        """A card for a cart with no cover: a generated one, its title's
        initial on the colour block that stays the cart's
        (`ui_draw.initial_cover`)."""
        _ui_draw.initial_cover(cv, rect, r, it.get("title") or "",
                               bool(_ui_draw.depth()[4]))

    def _draw_hh_cover(self, cv, it, rect, centre, r=None, div=_COVER_BASE, i=None):
        """A card's picture: the whole cover (decode `div`) scaled to the
        card (a carousel neighbour's dimmed once and kept where the theme
        dims them, step 15), else the title tile. `r`: its corners, where
        the caller has them; `i`: the card's index, where the caller has
        it, whose cover is then the one kept for it (`_cover_of`)."""
        if r is None:
            r = self._corner_r(rect[2])
        stepped = bool(_ui_draw.depth()[4])
        cover = None
        if self.cover_for is not None:
            dim = self._dims(centre)
            if dim is not None and self.tinted_for is not None:
                cover = self.tinted_for(it, dim[0], dim[1])
                if cover is not None:
                    cv.cover(cover.pix, cover.w, 0, 0, cover.w, cover.h, rect[0],
                             rect[1], rect[2], rect[3], r, stepped)
                    return
            cover = self.cover_for(it, div) if i is None else self._cover_of(i, it, div)
        if cover is not None:
            cv.cover(cover.pix, cover.w, 0, 0, cover.w, cover.h, rect[0], rect[1],
                     rect[2], rect[3], r, stepped)
        else:
            self._draw_title_tile(cv, it, rect, r)

    def _draw_picture(self, cv, it, rect, centre, sheet_for=None, r=None,
                      div=_COVER_BASE, i=None):
        """A card's picture over its whole rect: the "+ New" card's blank
        page (`draw_new_art`) in the corners a cover of its size takes, else
        its cover (`_draw_hh_cover`). `r`: its corners, where the caller has
        them."""
        if r is None:
            r = self._corner_r(rect[2])
        if it.get("type") in PSEUDO_TILE_TYPES:
            draw_new_art(cv, self.theme or {}, rect, r,
                         bool(_ui_draw.depth()[4]),
                         self.icon_spec() if self.icon_spec is not None else None,
                         self.layout.fs)
        else:
            self._draw_hh_cover(cv, it, rect, centre, r, div, i)

    def _corner_r(self, side):
        return self._cells().r

    def _favorite_badge_geom(self, rect, left=False):
        """The corner badge square for card rect `rect` -- one formula shared by
        the draw path and favorite_rect (hit-test), so they can never desync.
        `left`: the top-left corner's, the broken mark's."""
        x, y, w, _h = rect
        fs = self.layout.fs
        sz = max(14 * fs, 16, 12 * _lb.unit()) | 1      # odd: the star centres on a pixel
        pad = max(2 * fs, _ui_draw.depth()[1] // 2 + 2)
        return (x + pad if left else x + w - sz - pad, y + pad, sz, sz)

    def _broken_badge_geom(self, rect):
        """The broken mark's square on card rect `rect`: the star's, in the
        top-left corner, no wider than a quarter of a small card."""
        x, y, sz, _sz = self._favorite_badge_geom(rect, True)
        sz = min(sz, rect[2] // 4) | 1
        return (x, y, sz, sz)

    def is_broken(self, it):
        """Whether card `it` wears the crash guard's mark: a cart on the Make
        tab the guard turned off."""
        f = self.broken_for
        return (f is not None and self.tab == "make" and bool(it.get("path"))
                and it.get("type") not in PSEUDO_TILE_TYPES and f(it))

    def broken_key(self):
        """What the cards' broken marks are a function of: the Make tab's
        broken ids, None anywhere else."""
        f = self.broken_ids
        return f() if f is not None and self.tab == "make" else None

    def _card_frame(self, cv, rect):
        """A card's thin border where the theme's cards are square (`card_r`
        0)."""
        th = self.theme or {}
        fs = self.layout.fs
        x = rect[0]
        y = rect[1]
        w = rect[2]
        h = rect[3]
        for i in range(fs):
            cv.rectb(x - i, y - i, w + 2 * i, h + 2 * i, th.get("border", self._NAMES["black"]))

    # -- the selected card's words -------------------------------------------

    def played(self, it):
        """(times run, day of the last run or 0) of the card's play record
        (`CartManager.plays`), or None."""
        f = self.plays_for
        return None if f is None or it.get("type") in PSEUDO_TILE_TYPES else f(it)

    def today(self):
        """Today as YYYYMMDD, 0 where there is no wall clock."""
        f = self.today_for
        return 0 if f is None else f()

    def _meta(self, it, played=True):
        """The metadata of the selected card, its items: the cart's genre
        where its manifest names one (SPEC.md 3.7) and its kind where not,
        where it came from (built in, the kid's own, installed) and, where
        its play record has a day and `played`, when it was last played
        (the desk's details pane says that in its facts)."""
        if it.get("type") in PSEUDO_TILE_TYPES:
            return ("A new game",)
        kind = _cl.genre_word(it.get("genre")) or _KIND_NAME.get(it.get("type"), "App")
        path = it.get("path")
        if self.own_for is not None and self.own_for(it):
            src = "Yours"
        elif (_builtin_name(path) is not None if path
              else (it.get("id") or "").startswith("moybyte.")):
            src = "Built in"
        else:
            src = "Installed"
        rec = self.played(it) if played else None
        words = day_words(rec[1], self.today()) if rec is not None else None
        if words is None:
            return (kind, src)
        if words in ("Today", "Yesterday"):
            words = words.lower()
        return (kind, src, "Played " + words)


def _cover_div_for(side):
    """The cover decode a card `side` across draws: the whole cover where it
    takes 128 or more, else its half (a handheld shelf card's 1x, an icon's
    reduction)."""
    return _COVER_BASE if side > _COVER_SIDE // 2 else _COVER_HALF


# The home's tabs (docs/theme_and_shell_2026-11.md §8.10), in tab-row order, and
# the noun the bar's title counts each in.
HOME_TABS = (("games", "Games"), ("mine", "Mine"), ("apps", "Apps"),
             ("make", "Make"))
_TAB_NAME = dict(HOME_TABS)
_TAB_NOUN = {"games": ("GAME", "GAMES"), "mine": ("CART", "CARTS"),
             "apps": ("APP", "APPS"), "make": ("PROJECT", "PROJECTS")}
_KIND_NAME = {"game": "Game", "app": "App", "tool": "Tool", "wallpaper": "Wallpaper"}
# The home's hint strip (steps 17 and 18): each verb's key and words. The
# keys stay off the T-Deck keyboard's buttons (moy_kbd.c: w a s d, l, k), so
# Duplicate is Y on a keyboard, and a gamepad's Y names nothing on the home: its X
# opens the card's verbs ("options"), the star among them.
_VERB_HINT = {"play": ("confirm", "Play"), "open": ("confirm", "Open"),
              "change": ("C", "Change"), "search": ("search", "Search"),
              "new": ("N", "New"), "copy": ("Y", "Duplicate"),
              "delete": ("X", "Delete"),
              "favourite": ("F", "Add favourite"), "options": ("options", "Options"),
              "window": ("P", "Play")}
SHELF_GAP = 42       # the details block's foot to the shelf's caption, in
                     # glass pixels: the full PROJECTS window's, at every size
DETAILS_MIN = 280    # the narrowest details pane beside the hero, in glass
                     # pixels at the target's 1x: a primary button and one more
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
           "Oct", "Nov", "Dec")


def _days(ymd):
    """Days since 1970-01-01 of a YYYYMMDD date (the civil-from-days
    inverse)."""
    y, m, d = ymd // 10000, ymd // 100 % 100, ymd % 100
    if m <= 2:
        y -= 1
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    return era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468


def day_words(day, today):
    """A YYYYMMDD day as the home says it, beside `today` (0: unknown):
    Today, Yesterday, N days ago within a week, else the date, its year
    where it is not this one. None for no day."""
    if not day:
        return None
    if today:
        n = _days(today) - _days(day)
        if n == 0:
            return "Today"
        if n == 1:
            return "Yesterday"
        if 1 < n < 7:
            return "%d days ago" % n
    y, m = day // 10000, day // 100 % 100
    out = "%d %s" % (day % 100, _MONTHS[(m - 1) % 12])
    return out if today and today // 10000 == y else "%s %d" % (out, y)


def text_scale(px, fs, role="ui"):
    """The whole scale `role`'s face draws a line about `px` glass pixels
    tall in, the font scale `fs` at the least."""
    lh = _ui_draw.font(role)[2]
    return max(fs, (px + lh // 2) // max(1, lh))


_PRIMARY = ("play", "open", "new", "change")    # a first button that is the tab's tap


def button_kind(k, verb):
    """The look of the desk pane's `k`th button, `verb`'s: the first a
    primary where it plays, opens, makes or changes, Delete a danger."""
    return "primary" if k == 0 and verb in _PRIMARY else ("danger" if verb == "delete" else "normal")


def desk_buttons(verbs):
    """A card's `verbs` as the desk pane's buttons: ((label, kind), ...)."""
    return tuple((_VERB_HINT[v][1], button_kind(k, v)) for k, v in enumerate(verbs))


# The most buttons a desk card shows, per kind of tab: a played tab's
# (Games, Mine), Make's on a real card. The details pane keeps room for as
# many rows as the widest of them wraps to (the engine's desk geometry), so
# the shelf stays put as the selection moves.
DESK_BUTTON_SETS = (desk_buttons(("play", "change", "copy")),
                    desk_buttons(("change", "copy", "delete")))
# ...and the desk's Projects window's, whose Make card has Play third
PROJECTS_BUTTON_SETS = DESK_BUTTON_SETS + (desk_buttons(("change", "copy", "window", "delete")),)


def tab_count_title(tab, n):
    """The bar's title on the home: the active tab's count."""
    one, many = _TAB_NOUN.get(tab, ("CART", "CARTS"))
    return "%d %s" % (n, one if n == 1 else many)
