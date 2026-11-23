# Map (grep -n a name to jump there):
#   Carousel                    the home's row: the centre card scaled by its distance
#   Carousel._geom              its geometry: the handheld's row or the desk's hero and shelf
#   Carousel.band_pass          the row: the engine's carousel, the handheld's row or the desk's shelf
#   Carousel._band_picture      a card's picture, the engine's picture call
#   Carousel.hero_picture       the desk hero's picture, the engine's picture call
"""The home's CAROUSEL (docs/theme_and_shell_2026-11.md §8.10): the `carousel`
arrangement, the default (the layout's `home`), and the home window's,
always. On the handheld one row of square cover cards slides sideways, the
centre card larger by a function of its distance from the centre; on the
desk's metrics the selected card is the hero beside its details over a
shelf of one-size cards. A `Launcher` (home_grid.py): the same selection
model, its own geometry, motion and draw. Its instances are ws.launcher in
the `carousel` arrangement and ws.projects_grid.
"""

from array import array

import ui as _ui
import ui_draw as _ui_draw
import layout_base as _lb
from home_grid import (_COVER_BASE, _COVER_SIDE, desk_button_span, _DESK_VERB_SETS,
                       _draw_broken_badge, _draw_star_badge, _hint_strip, Launcher, _NO_KEYS,
                       PSEUDO_TILE_TYPES, _TAB_NAME)

_G_PASS = [None, None]   # the row a band pass runs on and its geometry (`_geom`)
_PK = [None, None]       # the row whose paint key was answered last, and the key (`paint_key`)
# The words of the handheld band's carousel as its last frame left it (moy_uitree.h's
# uit_carousel): its scroll, its motion (drag, fling, glide bits), the card nearest the
# centre, the card it rests on, whether it held the keys
_W_SCROLL, _W_MOTION, _W_NEAR, _W_REST, _W_FOCUS = 14, 15, 16, 17, 19
# ...and of the desk's shelf (uit_cells): its scroll, its motion, its current card, whether
# it held the keys
_D_SCROLL, _D_MOTION, _D_CUR, _D_FOCUS = 20, 21, 22, 24
_DRAG, _ON_ITS_OWN = 1, 6
# The desk's geometry words (moy_ui_api.h's MOY_UI_DESK_*): a shelf card's side, the shelf's
# top, its margin, the pane's first type scale (four, then the button height), the facts' row
# shown (the metadata's after it), the focus mark's reach, the shelf's gap
(_D_SIDE, _D_SHELF_Y, _D_PAD, _D_TS) = (12, 13, 14, 15)
_D_FACTS, _D_RING, _D_GAP = 20, 22, 23


class Carousel(Launcher):
    """The home's carousel (docs/theme_and_shell_2026-11.md §8.10, the 2026-10
    look's steps 17 and 18), on the class in force. On the handheld one row
    of square cover cards slides sideways, the card at the centre larger: a
    card's size is a function of its distance from the centre and of
    nothing else -- 1.0 at one pitch or more, rising to the centre scale at
    distance 0 -- so a settled row is a still row. The row rests with a card
    at the centre: a drag, a fling or a key moves the offset, and once the
    motion is spent a GLIDE carries the nearest card the rest of the way
    (`flinging` covers both, so every moving frame takes the drag partial).
    `sel` changes only on settle, and so does the bar's zone (`zone_gen`).
    On the desk the selected card is the hero beside its details, over a
    shelf of one-size cards: a key or a tap selects at once and the shelf
    glides to show it two cards in, a drag scrolls the shelf alone, and the
    hero follows the selection (`statics_sel`).

    The cards lie on the home's wallpaper, so a moving frame cannot shift the
    band's pixels (the wallpaper would slide with them): it restores the
    wallpaper around the cards from the band's capture
    (`LauncherHomeLayer._backdrop_fill`) and paints the cards over it. On
    the handheld the band is the engine's carousel (`ui.cards(look=
    "carousel")`, `home_ui.band`) on the band's host: its geometry, its
    keys, its pointer, its motion and its settle are the engine's, its
    cards' pictures and the ground under the band the home's (`_page_pass`),
    and the class reads the row back as the band's last frame left it. On
    the desk the band is the same page's shelf (the carousel look on the
    desk class): its geometry beside the hero, its keys, its pointer and
    its glide the engine's too."""

    arrangement = "carousel"
    page_fn = "band"                # its handheld band's page (home_ui)
    verb_sets = _DESK_VERB_SETS     # the buttons its desk pane keeps rows for

    def __init__(self, items, layout=None, names=None):
        self._g_lay = None            # the layout _g was computed for
        self._g_reach = 0
        self._g_keys = True
        self._g = None
        self.layout = None
        # the handheld row's offset before its band's first frame (`scroll`)
        self._scroll = 0
        self._quiet_for = None        # the geometry `quiet` was computed for
        self._quiet_q = ()
        self._dg = array("i", [0] * 24)     # the desk's geometry words (`_geom_desk_at`)
        self.keyed = False            # input that may move the selection waits on a pass
        self._down = False            # ...the pointer was down at its last sample
        Launcher.__init__(self, items, layout, names)

    # -- geometry ------------------------------------------------------------

    def _geom(self):
        """(tabs, band, card, pitch, ring, gap, plate_h, centre_y, foot,
        desk): the handheld's (`_geom_hh`) or the desk's (`_geom_desk`) on
        the class in force. A card is square (a cover is, SPEC.md 3.6) and
        shows its whole cover at a clean scale (`_clean_side`). Inside a
        band pass, the one it began under (`band_pass`)."""
        if _G_PASS[0] is self:
            return _G_PASS[1]
        lay = self.layout
        reach = _ui_draw.mark_reach("card")    # the centre card's focus mark
        keys = _ui_draw.hint_kind() != "touch"    # touch alone shows no hint strip
        if self._g_lay is lay and self._g_reach == reach and self._g_keys == keys:
            return self._g
        self._g = (self._geom_hh(lay, keys) if _lb.metric_class() == _lb.HANDHELD
                   else self._geom_desk(lay, keys))
        self._g_lay = lay
        self._g_reach = reach
        self._g_keys = keys
        return self._g

    def _geom_hh(self, lay, keys=True):
        """The handheld home's geometry (docs/history/look_2026-10.md step 17),
        the same tuple with its foot: no tab row (the tabs are the bar's),
        the band from the content's top to the hint strip along its foot
        (none with no `keys`: touch shows no keycaps, and the cards take its
        height), and in it the band page's carousel's geometry, the
        engine's (moy_uitree.h's uit_carousel_geom): a neighbour's side, the
        pitch, the hero twice the side, its title and its metadata under
        it."""
        hints = _hint_strip(lay, keys, False)
        band = (lay.cx, lay.cy, lay.cw, hints[1] - lay.cy)
        q = self._cq
        q[0], q[1], q[2], q[3] = band
        g = self._cg
        self._band_page().carousel_geom(q, lay.fs, False, g)
        card, pitch = g[0], g[1]
        return (None, band, card, pitch, g[9], pitch - card, 0, g[2],
                (g[3], g[4], g[5], g[6], g[7], hints), None)

    def _geom_desk(self, lay, keys=True):
        """The desk home's geometry (`_geom_desk_at`) with room in its pane
        for as many rows of buttons as its width wraps them to
        (`desk_button_span`): a pane narrowed by a smaller hero is laid out
        again, the rows it then needs kept."""
        span = 0
        for _ in range(3):
            g = self._geom_desk_at(lay, keys, span)
            dk = g[9]
            got = desk_button_span(dk[2], lay.fs, dk[5][6], dk[5][4], self.verb_sets)
            if got <= span:
                break
            span = got
        return g

    def _geom_desk_at(self, lay, keys, brows):
        """The desk home's geometry, the engine's (the carousel look on the
        desk class, moy_ui_api_carousel_desk): the hero at the top left, the
        details pane beside it (or under it in a narrow window), the shelf
        under them bleeding off the right edge, its caption over it, the
        hint strip `_hint_strip` along the foot. The tuple's band is the
        shelf's (its caption, its cards, their lift and their shadows); the
        desk's own is (the hero, the pane's x, its width, the shelf's top,
        its margin, (the pane's title, metadata, fact caption and value
        scales, a button's height, the pane's height, the render scale),
        the pane's y, (facts, metadata) shown, `brows`)."""
        hints = _hint_strip(lay, keys, True)
        q = self._cq
        q[0], q[1], q[2], q[3] = lay.cx, lay.cy, lay.cw, hints[1] - lay.cy
        d = self._dg
        self._band_page().carousel_desk(q, lay.fs, keys, brows, d)
        shelf, shelf_y = d[_D_SIDE], d[_D_SHELF_Y]
        desk = ((d[0], d[1], d[2], d[3]), d[4], d[6], shelf_y, d[_D_PAD],
                (d[_D_TS], d[_D_TS + 1], d[_D_TS + 2], d[_D_TS + 3], d[_D_TS + 4], d[7],
                 _lb.render_scale()),
                d[5], (d[_D_FACTS] != 0, d[_D_FACTS + 1] != 0), brows)
        return (None, (d[8], d[9], d[10], d[11]), shelf, shelf + d[_D_GAP], d[_D_RING],
                d[_D_GAP], 0, shelf_y + shelf // 2, (0, 0, 0, 0, 0, hints), desk)

    def handheld(self):
        """Whether the home is the handheld's (step 17): its tabs in the bar,
        its foot under the band."""
        g = self._geom()
        return g[8] is not None and g[9] is None

    def desk(self):
        """Whether the home is the desk's console home (step 18): the hero,
        its details and the shelf, its tabs in the bar and its foot the
        hint strip."""
        return self._geom()[9] is not None

    def foot(self):
        """(title y, title h, title scale, meta y, meta h, the hint strip's
        rect) on the handheld, the hint strip's rect last on the desk's
        console home, else None."""
        return self._geom()[8]

    def hero_rect(self):
        """The desk home's hero, or None."""
        dk = self._geom()[9]
        return None if dk is None else dk[0]

    def quiet(self):
        """The home's quiet rectangles (docs/theme_and_shell_2026-11.md §3.9), which
        a per-glass wallpaper keeps its subject out of: on the handheld the
        title and the metadata, a column as wide as the hero and half a
        neighbour each side, and the hint strip; on the desk the hero and
        its details, the shelf's band and the hint strip. Computed once per
        geometry."""
        g = self._geom()
        if self._quiet_for is g:
            return self._quiet_q
        foot, dk = g[8], g[9]
        if foot is None:
            q = ()
        elif dk is None:
            title_y, _th, _ts, meta_y, meta_h, hints = foot
            lay = self.layout
            tw = min(lay.cw, 3 * g[2])
            q = ((lay.cx + (lay.cw - tw) // 2, title_y, tw,
                  meta_y + meta_h - title_y), hints)
        else:
            (hx, hy, hero, _h), dx, dw, dy = dk[0], dk[1], dk[2], dk[6]
            q = ((hx, hy, max(dx + dw, hx + hero) - hx,
                  max(hy + hero, dy + dk[5][5]) - hy), g[1], foot[5])
        self._quiet_for = g
        self._quiet_q = q
        return q
    def band_rect(self):
        """The carousel band: every card at any scale, the centre's ring and
        its title plate. The rect the drag partial fills and hands as damage."""
        return self._geom()[1]

    def card_side(self):
        return self._geom()[2]

    def pitch(self):
        return self._geom()[3]

    # -- the offset, the motion, the selection ---------------------------------

    def _hh(self):
        """The handheld band's carousel as its page's last frame left it
        (`_cw`, moy_uitree.h's uit_carousel, read once a pass), else None:
        on the desk, or before the band's first frame."""
        if not self._cw_ok or self._geom()[9] is not None:
            return None
        return self._cw

    def _dw(self):
        """The desk's shelf as its page's last frame left it (`_cw`,
        moy_uitree.h's uit_cells, read once a pass), else None: on the
        handheld, or before the shelf's first frame."""
        if not self._cw_ok or self._geom()[9] is None:
            return None
        return self._cw

    @property
    def sel(self):
        return self._sel

    @sel.setter
    def sel(self, value):
        if value != getattr(self, "_sel", None):
            self.zone_gen += 1
        self._sel = value
        # A selection made from outside (a tab switch, a resume, a remote
        # run) brings its card to the centre: on the handheld the band's
        # current card, where its row lands while it rests (`band_set`);
        # the settle's own assignment lands where the row already rests.
        if self.layout is not None and not self.moving:
            self._scroll = self._rest_of(value)

    def _rest_of(self, i):
        """The offset the handheld's row rests at with card `i` at the
        centre (the desk's shelf lands itself)."""
        return max(0, i) * self.pitch()

    @property
    def scroll(self):
        """The pixel offset: the handheld band's as its last frame left it,
        else clamped against the live layout."""
        w = self._hh()
        if w is not None:
            return w[_W_SCROLL]
        w = self._dw()
        if w is not None:
            return w[_D_SCROLL]
        return max(0, min(self._scroll, self.max_scroll()))

    @scroll.setter
    def scroll(self, value):
        self._scroll = max(0, min(int(value), self.max_scroll()))

    @property
    def dragging(self):
        """True while a drag (past the slop) moves the row."""
        w = self._hh()
        if w is not None:
            return w[_W_MOTION] & _DRAG != 0
        w = self._dw()
        return w is not None and w[_D_MOTION] & _DRAG != 0

    @property
    def flinging(self):
        """True while the row moves on its own: a released fling, or the
        glide that carries a card to the centre (a key's motion too) --
        the frames that take the band's partial."""
        w = self._hh()
        if w is not None:
            return w[_W_MOTION] & _ON_ITS_OWN != 0
        w = self._dw()
        return w is not None and w[_D_MOTION] & _ON_ITS_OWN != 0

    @property
    def moving(self):
        w = self._hh()
        if w is not None:
            return w[_W_MOTION] != 0
        w = self._dw()
        return w is not None and w[_D_MOTION] != 0

    def max_scroll(self):
        g = self._geom()
        if g[9] is not None:
            # the shelf's last card ends its margin short of the band's edge
            n = len(self.items)
            return max(0, (n - 1) * g[3] + g[2] + 2 * g[9][4] - g[1][2]) if n else 0
        return max(0, (len(self.items) - 1) * self.pitch())

    def nearest(self):
        """The card nearest the centre at the current offset (the handheld
        band's as its last frame left it); on the desk's shelf, the
        selected one."""
        n = len(self.items)
        if not n:
            return 0
        g = self._geom()
        if g[9] is not None:
            return max(0, min(n - 1, self._sel))
        w = self._hh()
        if w is not None:
            return min(n - 1, w[_W_NEAR])
        g = g[3]
        n -= 1
        # (`scroll`, clamped to the handheld's `max_scroll`, in pitches)
        g = (min(self._scroll, n * g) + g // 2) // g
        return 0 if g < 0 else n if g > n else g

    # -- cards -----------------------------------------------------------------

    def _visible(self):
        """(index, rect) of every card in the band as its last frame laid
        them out (the engine's tiles), the selected one last -- the order
        they paint in."""
        c = self.nearest()
        out = [(i, r) for i, r in ((i, self.tile_rect(i)) for i in range(len(self.items)))
               if r is not None]
        out.sort(key=lambda e: e[0] == c)
        return out

    def tile_rect(self, i):
        """Card `i`'s box as the band's last frame laid it out (the
        handheld's tile, the desk shelf's card), or None where it lies
        outside the band."""
        pg = self._bpage
        if not (0 <= i < len(self.items)) or pg is None:
            return None
        t = self._ct
        if not (pg.carousel_tile(i, t) if self.handheld() else pg.cells_tile(i, t)):
            return None
        return (t[0], t[1], t[2], t[3])

    def tile_at(self, px, py):
        pg = self._bpage
        if pg is None:
            return None
        i = pg.carousel_at(px, py) if self.handheld() else pg.cells_at(px, py)
        return i if 0 <= i < len(self.items) else None

    def plate_rect(self):
        """The handheld's title and metadata lines across the band; on the
        desk, the details pane beside the hero."""
        g = self._geom()
        bx, by, bw, bh = g[1]
        if g[9] is not None:
            return (g[9][1], g[9][6], g[9][2], g[9][5][5])
        f = g[8]
        return (bx, f[0], bw, f[3] + f[4] - f[0])

    def action_rects(self):
        return None

    def statics_sel(self):
        return self._sel if self.desk() else -1

    def paint_key(self):
        """What the band's pixels depend on besides the offset and the
        statics: the selection, the motion (a card at rest wears its mark),
        whether the tabs or the bar hold the focus (the mark goes), the
        centre card's title and star. The same tuple while they stand."""
        it = self.items[self.nearest()] if self.items else None
        f = self.favorite_for
        title = it and it.get("title")
        star = it is not None and f is not None and bool(f(it))
        broken = self.broken_key()
        k = _PK[1] if _PK[0] is self else None
        if (k is None or k[0] != self._sel or k[1] != self.moving or k[2] != self.tab_focus
                or k[3] != title or k[4] != star or k[5] != broken):
            k = _PK[1] = (self._sel, self.moving, self.tab_focus, title, star, broken)
            _PK[0] = self
        return k

    def favorite_rect(self, i):
        """The centre card's favorite-star badge, at rest."""
        if (self.favorite_for is None or not self.items or i is None
                or self.moving or i != self.nearest()):
            return None
        if not (0 <= i < len(self.items)):
            return None
        it = self.items[i]
        if it.get("type") in PSEUDO_TILE_TYPES or not it.get("path"):
            return None
        hero = self.hero_rect()
        if hero is not None and hero[2] * _lb.render_scale() < _COVER_SIDE:
            return None                  # a small hero wears no badge (F, the menu)
        r = hero or self.tile_rect(i)
        return None if r is None else self._favorite_badge_geom(r)

    def cover_specs(self):
        out = []
        for it in self.items:
            if it.get("type") in PSEUDO_TILE_TYPES or not it.get("path"):
                continue
            out.append((it, _COVER_BASE))
        return out

    def draw(self, cv, sheet_for=None, key=_NO_KEYS, over=None, beside=None):
        return self.band_pass(cv, sheet_for, None, key, True, over, beside)

    def repaint_band(self, cv, sheet_for, fill, key=_NO_KEYS, over=None, beside=None, need=False,
                     marks=False, whole=False):
        """A band frame: the row (`band_pass`) over the ground `fill` puts
        back around its cards, every card's corner rows with `marks` (the
        buffer may hold the focus mark on another card)."""
        return self.band_pass(cv, sheet_for, fill, key, whole, over, beside, need, marks)

    def band_key(self):
        return self.paint_key()

    def band_pass(self, cv, sheet_for, fill, key=_NO_KEYS, whole=True, over=None, beside=None,
                  need=False, marks=False, note=False):
        """The row, on the band's own app host: the band's page
        (`_band_page`, the engine's carousel: on the handheld its row, on
        the desk its shelf) drawn in the band, moving itself (its keys and
        its pointer the host's: `band_keys`, `band_point`) and marking its
        centre at rest while the cards hold the keys (not the tab row's),
        its caption white over black on a wallpaper (`wall_ink`). It keeps
        no tiles: a pass that draws the band draws it whole, over the
        ground `fill` puts back there first (None: a full paint drew it),
        and names what it drew (`ui.held`) so the floor's end says whether
        every buffer holds it. A pass that finds the buffer holding the band
        as it stands (nothing moving, nothing to take) and a `note` pass,
        the band lying there by other means, draw none of it and name it,
        its page standing as it was (`AppHost.stand`). `beside` draws
        first. The pass draws under the geometry it begins with (`_geom`)."""
        g = _G_PASS[1] = self._geom()
        _G_PASS[0] = self
        try:
            return self._page_pass(cv, g, fill, key, whole, over, beside, need, note)
        finally:
            _G_PASS[0] = _G_PASS[1] = None

    def _page_pass(self, cv, g, fill, key, whole, over, beside, need, note):
        """The band pass (`band_pass`) under geometry `g`: the band's page
        painted in the band on the class in force, the words it left read
        back (the handheld's carousel, `_hh`; the desk's shelf, `_dw`) and
        the selection taken from them: the card the handheld's row settled
        on, the desk shelf's current card."""
        desk = g[9] is not None
        host = self._band_host()
        held = self._begin_band(cv, g[1], desk, key, need, over, not self.tab_focus)
        if held is None:
            return None
        if key[0] < 0:
            # (the band not the home's alone on the glass: no buffer holds its frame)
            if need:
                _ui.end()
                return None
            held = False
        whole = whole or not held
        if beside is not None:
            beside(cv, whole)
        del self.floor[:]
        del self.copied[:]
        pg = self._band_page()
        puts = not note and self._band_cards()
        w = self._dw() if desk else self._hh()
        if desk:
            wm, wf, kf = _D_MOTION, _D_FOCUS, self._cells_key
        else:
            wm, wf, kf = _W_MOTION, _W_FOCUS, self._cards_key
        if (not note and not whole and not puts and not host.owed and not self._fed
                and w is not None and not w[wm] and w[wf] != self.tab_focus
                and _ui.held("cards", kf(key, w))):
            note = True                     # (the buffer holds it as it stands)
        self._fed = False
        if note:
            host.stand()                    # (where no pass of this frame draws the page)
        else:
            self.keyed = False
            if fill is not None:
                fill(cv, g[1])
            self._gcv = cv
            self.floor.append(g[1])
            pg.paint(0, cv, self.theme, g[1], desk)
            self._gcv = None
            if desk:
                self._cw_ok = pg.cells(self._cw)
                w = self._dw()
            else:
                self._cw_ok = pg.carousel(self._cw)
                w = self._hh()
        if w is not None:
            got = w[_D_CUR] if desk else w[_W_REST]
            if got != self._sel and got < len(self.items):
                self.zone_gen += 1
                self._sel = got             # the row settled, the shelf's card moved
            # what the band shows, under its key: each buffer that drew it so holds it
            _ui.held("cards", kf(key, w))
        end = 0 if _ui.held_all() else -1
        _ui.end()
        return end

    @staticmethod
    def _cards_key(key, w):
        """What the band shows under the home's band key `key` and its
        carousel's words `w`: its scroll, its motion, the card nearest the
        centre and whether it wears the focus mark (-1: no buffer holds it).
        Each step held under 2**27: no long int a frame."""
        k = key[1]
        if k < 0:
            return -1
        k = ((k & 0x3fffff) * 31 + w[_W_SCROLL]) & 0x3fffff
        k = ((k * 31 + w[_W_NEAR]) & 0x3fffff) * 31 + w[_W_MOTION]
        return (k & 0x3fffff) * 2 + w[_W_FOCUS]

    def band_keys(self, i):
        """The band host's keys (`Launcher.band_keys`); a step, a notch or
        Enter may move or open the selection (`keyed`)."""
        if (i.steps("left") or i.steps("right") or i.pressed("a") or i.pressed("run")
                or getattr(i, "wheel_x", 0) or getattr(i, "wheel_y", 0)):
            self.keyed = True
        return Launcher.band_keys(self, i)

    def band_point(self, px, py, click, down):
        """The band host's pointer (`Launcher.band_point`); a release may
        tap a card current (`keyed`)."""
        if self._down and not down:
            self.keyed = True
        self._down = down
        return Launcher.band_point(self, px, py, click, down)

    def _set_more(self, q):
        """Whether the desk shelf's card side or its caption moved."""
        return len(q) < 4 or q[2] != self._geom()[2] or q[3] != self.tab

    def band_set(self, s):
        """The band's current card and its words' ink (`Launcher.band_set`),
        and on the desk its shelf's card side and caption (the tab's name)."""
        Launcher.band_set(self, s)
        g = self._geom()
        desk = g[9] is not None
        s.side = g[2] if desk else 64
        s.caption = _TAB_NAME.get(self.tab, "") if desk else ""
        self._set = (self._sel, self.wall_ink, g[2], self.tab)

    def _put_more(self, p):
        """Whether what the rows were put from moved beside the items: the
        centre card's play record, which its caption says."""
        c = self.nearest()
        return c < len(p[1]) and p[1][c] != self.played(self.items[c])

    def _band_picture(self, node, pic, r):
        """A card of the band's page (the engine's picture call, `r` its
        tile, clip, flags, corners): its picture (`_draw_picture`), at rest
        on the centre the favourite's star, the broken mark, the frame of a
        square card. Every card holds one."""
        if r is None:
            return True
        i = self._pic_ix.get(pic)
        items = self.items
        if i is None or i >= len(items):
            return False
        it = items[i]
        cv = self._gcv
        cv.clip(r[4], r[5], r[6], r[7])
        pseudo = it.get("type") in PSEUDO_TILE_TYPES
        cr = r[9]
        # (a cover's draw reads the tile by index, so `r` serves; the rest take it whole)
        self._draw_picture(cv, it, (r[0], r[1], r[2], r[3]) if pseudo else r, r[8] & 4 != 0, None, cr,
                           _COVER_BASE, i)
        star = r[8] & 8 and self.favorite_for is not None and it.get("path") and not pseudo
        broken = self.is_broken(it)
        if star or broken or not cr:
            rect = (r[0], r[1], r[2], r[3])
            names = self._NAMES
            if star:
                _draw_star_badge(cv, names, self.theme or {}, self._favorite_badge_geom(rect),
                                 bool(self.favorite_for(it)))
            if broken:
                _draw_broken_badge(cv, names, self.theme or {}, self._broken_badge_geom(rect))
            if not cr:
                self._card_frame(cv, rect)
        cv.clip()
        return True

    def _corner_r(self, side):
        """The corner radius of a card `side` across under the theme's depth:
        on the handheld its `card_r` on the hero and 7/10 of it on a
        neighbour, on the desk `card_r` on the shelf and 7/5 of it on the
        hero."""
        r = _ui_draw.depth()[1]
        g = self._geom()
        if g[9] is not None:              # the desk's
            return r * 7 // 5 if side > g[2] else r
        return r if side > g[2] else r * 7 // 10

    def paint_hero(self, pg, cv, th, rect):
        """The desk home's hero page (`home_ui.hero`, a full paint's or the
        selection part's) in its rect, its picture the selected card's
        (`hero_picture`)."""
        self._gcv = cv
        pg.paint(0.0, cv, th, rect, True)
        self._gcv = None

    def hero_picture(self, node, pic, r):
        """The desk hero's picture (the engine's picture call, `r` its box,
        clip, flags and corners): the selected card's picture over the box,
        its favourite star (on a hero of the cover's side
        or more in glass pixels), its broken mark, the frame of a square
        card."""
        if r is None:
            return True
        if not self.items:
            return False
        it = self.items[self.nearest()]
        cv = self._gcv
        cv.clip(r[4], r[5], r[6], r[7])
        hero = (r[0], r[1], r[2], r[3])
        cr = r[9]
        self._draw_picture(cv, it, hero, True, None, cr)
        names = self._NAMES
        if (self.favorite_for is not None and it.get("path")
                and hero[2] * _lb.render_scale() >= _COVER_SIDE
                and it.get("type") not in PSEUDO_TILE_TYPES):
            _draw_star_badge(cv, names, self.theme or {}, self._favorite_badge_geom(hero),
                             bool(self.favorite_for(it)))
        if self.is_broken(it):
            _draw_broken_badge(cv, names, self.theme or {}, self._broken_badge_geom(hero))
        if not cr:
            self._card_frame(cv, hero)
        cv.clip()
        return True

    def _dims(self, centre):
        """A handheld neighbour's dimming (step 15), off the centre."""
        if centre or self.dim is None or not self.handheld():
            return None
        return self.dim
