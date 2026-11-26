# Map (grep -n a name to jump there):
#   LauncherHomeLayer           the home: wallpaper, the cells, the bar's tabs, the hints
#   LauncherHomeLayer.draw      the home frame
#   LauncherHomeLayer.at_top    up from the cards goes on to the bar
#   LauncherHomeLayer.zone_gen  the int the bar's strip key reads (the zone is HomeZone's)
#   HomeWindowLayer             the home in a desktop-mode window (PROJECTS)
"""The home (#28), extracted from Workstation (runtime/shell/console.py) as a Layer
-- docs/history/shell_layers_refactor_v1.md (Move 1b).

  * `Launcher`     -- (home_grid.py) the selection model (items/sel/scroll/nav)
                      and the `grid` arrangement's draw: a shelf of cover
                      cards in the rows the glass holds, scrolling sideways.
                      The arrangements below are its subclasses.
  * `Carousel`     -- (home_carousel.py) the home's row
                      (docs/theme_and_shell_2026-11.md §8.10): the
                      same selection model over one row of square cover cards,
                      the centre card larger by a function of its distance
                      from the centre; on the desk's metrics the selected
                      card is the hero beside its details over a shelf. Its
                      instances are ws.launcher in the `carousel`
                      arrangement, the default (the layout's `home`), and
                      ws.projects_grid, the home window's, always.
  * `IconHome`     -- (home_icons.py) the `icons` arrangement: the same model over tiles of
                      the covers' reduction that scroll down, the focused
                      cart named in a caption band on the handheld and
                      every tile named under it on the desk.
  * `LauncherHomeLayer` -- the "launcher" content Layer: the home, console mode's
                      root on every board (wallpaper -> cells -> hint strip ->
                      bar, its tabs in the bar's zone), its four tabs (Games / Mine / Apps / Make, the lists
                      ws.home.launcher_items builds) and their input. A tap on the
                      centre card is the active tab's (ws.home.launch_selected).
                      Its bases, in order: `HomeHints` (home_hints.py, the
                      hint strip, which a band frame draws), `HomeDetails`
                      (home_details.py, the desk hero's details and verb
                      buttons), `HomeZone` (home_zone.py, its tabs' row lent
                      to the bar and the tab's verbs) and `HomeSearch`
                      (home_search.py, the search line). What a frame reads every frame stays on the
                      class or its first base.
  * `HomeWindowLayer` -- the "projects" content Layer: the SAME home in a
                      desktop-mode window (docs/theme_and_shell_2026-11.md §8.10, the
                      desk's PROJECTS): the console home's design over
                      ws.projects_grid, laid out in the window's content
                      rect, opened on its Make tab.

Boundary (single source of truth): ws.launcher (the instance) + ws.open() (open the
selected cart -- lifecycle, pinned) + the cart store stay on Workstation. The card
draw needs the palette -- `NAMES` is INJECTED at construction. The rect
hit-test is `widgets.rect_in`. No circular import: this module and the home_*
modules it takes its arrangements and band frame from import no console
module (the only console touch is Launcher's lazy Layout fallback for a bare
Launcher() that no caller ever constructs).

The lent bar zone (#46): each home layer lends the bar its tabs' row
(`HomeZone.bar_zone`), which the bar draws, taps and walks with its keys; up
from the cards at their top goes on to it (`at_top`). Its `zone_gen`, the
count of the open tab's moves, is the one int the bar's strip cache reads
every frame through the row. The grid's own
`zone_gen` (bumped whenever its `sel` or `items` changes) is the grid's.
"""


from array import array

import home_band as _band
import ui_draw as _ui_draw
from widgets import rect_in as _in   # one hit-test


# The tick helpers feed the perf_capture-gated home-frame split (see draw below).
from chrome import _ticks_ms, _ticks_diff
import layout_base as _lb
from home_band import (_wall_ink, _overlaps_any, _ground_of, _dim_of, _cursor_stamp,
                       _statics_base, _Keyed, _band_key, _band_frame)
from home_hints import HomeHints, modal_keys
from home_zone import HomeZone
from home_details import HomeDetails
from home_search import HomeSearch
from layers import Layer
from home_carousel import Carousel
from home_grid import PSEUDO_TILE_TYPES


# The home layer's own words: the long press, the chevron's tooltip.
# A press held this long on a card without travel opens the card's verbs (a
# phone home screen's long press), in frame milliseconds.
LONG_PRESS_MS = 500
BACK_TIP = "Desk"    # the tooltip on the bar's chevron back to the desk


class LauncherHomeLayer(HomeHints, HomeDetails, HomeZone, HomeSearch, Layer):
    """The "launcher" content Layer (system domain): the home, console mode's root.
    draw composes the wallpaper backdrop -> the tab row and the cards (`grid`,
    ws.launcher) -> the top bar; input is the grid nav / selection, dispatching
    the active tab's tap (ws.home.launch_selected). Owns the cursor's hover state
    (_lhover), the tab-row focus; `grid` is the single source
    it reads. `HomeWindowLayer` is the same home in a window."""

    id = "launcher"
    domain = "system"
    strip = "home"            # the bar strip it draws and taps (BarLayer's `where`)
    ON_WALLPAPER = True
    searchable = True         # Games carries SEARCH (the query is the home's)
    KEYS_IDLE = True          # its keys step the grid and the tabs; the glides are its draw's

    def __init__(self, ws, names):
        self.ws = ws
        self._NAMES = names
        self._lhover = (-1, -1)       # the last pointer sample (a release is not a move)
        self._back_tip = False        # a mouse rests on the bar's way back to the desk
        self._tip_at = [None, None, None]   # its pill's (w, h), and the layout and look it was laid out in
        self._hold = None             # a press on a card: [index, x, y, ms held]
        self._on_open = self._band_open     # the handheld band's card opened (`Carousel.on_open`)
        self._on_bar = False          # the keys are on the home's bar (BarLayer.focus_enter)
        # The band frame's keys (`_band_frame`; #58/#66: a FULL home repaint
        # stacks megabytes of writes on a board): the band table's
        # (`_band_key`), the hint strip's and the caption band's (`_beside`),
        # and the rects `_beside` drew.
        self._sk = _Keyed()
        self._bk = _Keyed()
        self._keys = array("i", [-1, -1])
        self._keyed_gen = -1          # the cover gen `_band_key` keyed the band under
        self._hk = _Keyed()
        self._beside_drew = []
        # what the hint strip's key was made of, and the key (`_outside_key`)
        self._ok = [None, None, None, None, None, None, None, None, None, None, None]
        self._st_parts = [None] * 16  # the statics key's parts (`_statics_key`)
        # Retained WHOLE-frame cache (2026-07-27, the damage-model doctrine at
        # shelf granularity): the last full home frame, captured at the END of
        # a live paint (right after our own last pixel -- overlays/cursor draw
        # AFTER this layer, so the copy is exactly our output) and stamped back
        # on re-entry when NOTHING the frame reads has changed (_retained_key)
        # -- a repeat home visit becomes one full-screen blit instead of the
        # ~150ms wallpaper + panel + cards + bar rebuild. An idle frame
        # captures only what every buffer holds (`capture_due`, owed by a
        # still frame): the P4 root rotates its buffers, so after present the
        # canvas's CURRENT buffer may hold an older frame, and an idle capture
        # of it would cache another screen's pixels under this frame's key.
        self._lib_cache = None        # cv.new_layer sized to the canvas
        self._lib_key = None          # _retained_key at capture
        self._cap_owed = None         # (frame, key, parts) a still frame owes
        self._debt_owed = None        # the frame a step left a buffer behind (`debt_due`)
        self._lib_unsupported = False # web RecordingLayer: no pixels to copy
        # The wallpaper under the carousel band, captured on every full paint
        # right after the wallpaper drew: a moving frame restores the band's
        # backdrop from it (the cards lie on the wallpaper, so the band cannot
        # shift). The key is what the capture was taken under -- the canvas,
        # the theme, the wallpaper and the band rect.
        self._band_bg = None          # cv.new_layer sized to the band
        self._band_key = None
        # The desk home's still-backdrop frames (`_try_still_frame`): the
        # keys its parts are named under in the band host's paints
        # (`ui.held`: the backdrop, the selection, the shelf, the bar); the
        # backdrop `restore_key` this frame answered; and the parts the
        # retained frame was captured under (`_capture_retained` copies only
        # the ones that moved).
        self._stk = _Keyed()
        self._slk = _Keyed()
        self._shk = _Keyed()
        self._bd_now = None
        self._lib_parts = None

    @property
    def grid(self):
        """The card model this home draws: ws.launcher, whose class is the
        layout's arrangement."""
        return self.ws.launcher

    def _grid_or_none(self):
        """The card model, None while it is not minted yet (the window's
        before its first open, the home's during the console's build)."""
        try:
            return self.grid
        except AttributeError:
            return None

    def _wall(self):
        """(white, black) where this home lies on a wallpaper (`_wall_ink`),
        else None."""
        return _wall_ink(self.ws)

    def at_top(self):
        """Up goes on to the bar (InputRouter._bar_keys): from the
        handheld's carousel, the grid's and the icons' top row, and the
        desk's shelf where its card has no buttons; from the desk pane's
        buttons the pane's page hands the keys on (`details_owed`)."""
        ws = self.ws
        grid = self._grid_or_none()
        if grid is None or self._btn is not None or getattr(ws, "search_typing", False):
            return False
        if self._carousel():
            return not (grid.desk() and self._desk_buttons())
        return grid.top_row()

    def bar_focus(self, on):
        """The keys go on to the home's bar (`on`) or off it: the cards let
        their focus mark go meanwhile, one mark a screen."""
        self._on_bar = on
        g = self._grid_or_none()
        if g is not None:
            g.tab_focus = on or getattr(self, "_btn", None) is not None
        self.ws.mark_dirty()

    def _statics_key(self, cv):
        """Everything the home frame's STATIC chrome (wallpaper backdrop +
        Library panel fill/header/footer) is a pure function of: the shared
        base plus the wallpaper, the search field and the keys a modal's hint
        strip names (`modal_keys`, the bar's left out). A key change forces
        full paints until the streak re-arms. Where the keys are -- the bar,
        a card -- is not in it: the tabs are the bar's, which a band frame
        draws, the hint strip names the bar's keys under its own key
        (`_outside_key`)
        and the selected card wears the focus as its part's gen. The base's
        six (`_statics_base`) then these, read into a kept list and made a
        tuple only where one moved from the key the band last keyed on
        (`_band_key`): that tuple while they stand."""
        ws = self.ws
        g = self.grid
        look = ws.look
        v = self._st_parts
        v[0] = cv.w
        v[1] = cv.h
        v[2] = ws.layout.fs
        v[3] = look.look_gen
        v[4] = g.band_rect()
        v[5] = len(g.items)
        v[6] = look.wallpaper_id
        mk = modal_keys(ws)
        v[7] = None if mk is _ui_draw.BAR_KEYS else mk
        v[8] = getattr(ws, "search_query", "")
        typing = v[9] = getattr(ws, "search_typing", False)
        v[10] = typing and ws.text.can_type()
        v[11] = g.tab
        v[12] = self._button_focus
        v[13] = g.arrangement
        v[14] = g.statics_sel()
        v[15] = self._back_tip
        k = self._sk.v
        i = 0
        if k is not None:
            while i < 16 and v[i] == k[i]:
                i += 1
        return k if i == 16 else tuple(v)

    def _retained_key(self, cv, statics=None):
        """Everything the WHOLE home frame's pixels are a pure function of: the
        chrome statics (`statics`, where the caller made them this frame)
        plus the grid's dynamics (selection, scroll
        offset as it was set -- its clamp is a function of the statics' band
        and item count -- the cover-cache generation, trackball hover, the
        items and the titles they carry (the list, never mutated, and the
        roster's count of titles taken in place), the settings rows'
        generation for the favorites and the play records), the bar's own
        pixel key (`shown_key` -- clock minute, wifi state, the look; reusing
        it means the bar's cache discipline IS this cache's discipline) and
        the samples and keys the hint strip's page took (`_sgen`).
        Anything that draws a pixel of the home frame and is NOT derivable
        from this tuple is a staleness bug -- the silent-cache family
        surface_model_v1.md §14.2 documents -- so additions to the home draw
        must extend this key."""
        ws = self.ws
        g = self.grid
        return (self._statics_key(cv) if statics is None else statics, g.sel,
                g.scroll, ws.covers.gen, self._lhover, g.items,
                ws.carts.titled, ws.system.gen(), ws.bar_layer.shown_key("home"),
                self._on_bar, self._sgen)

    def _try_stamp_retained(self, cv, dt):
        """Present the retained home frame when nothing it depends on changed:
        one full-screen blit (~26ms on P4 glass) instead of the full rebuild.
        Only for settled frames -- a drag/fling wants the partial path, and an
        animating overlay/wallpaper means the pixels are NOT a pure function
        of the key. Returns True when the frame was presented."""
        ws = self.ws
        cache = self._lib_cache
        if (cache is None or self._lib_unsupported
                or self.grid.dragging or self.grid.flinging
                or ws.animating(dt)):
            return False
        # A canvas that retains nothing (RETAINED_FRAMES < 1) holds no frame to
        # capture from or replay.
        if getattr(cv, "RETAINED_FRAMES", 0) < 1:
            return False
        if cache.w != cv.w or cache.h != cv.h:
            return False
        if self._retained_key(cv) != self._lib_key:
            return False
        cv.blit_strip(cache, 0, 0)
        return True

    def prealloc_retained(self):
        """Mint the retained-frame layer on an IDLE frame (called from frame()'s
        idle branch): the device new_layer pre-collects, which measured as a
        371ms first home visit when the allocation rode the capture's paint
        frame (~150ms collect + ~35ms copy on top of the ~180ms live paint).
        Allocation reads no pixels, so the ping-pong trap in __init__'s note
        does not apply -- only the CAPTURE must stay on the paint path."""
        ws = self.ws
        if self._lib_unsupported:
            return
        cv = ws.sys_canvas
        if getattr(cv, "RETAINED_FRAMES", 0) < 1:
            return
        g = self._grid_or_none()
        if g is not None and not g.moving and ws.screen == self.id:
            g.mint_faces()               # (only under the home: a face is the home's)
        cache = self._lib_cache
        try:
            if cache is None or cache.w != cv.w or cache.h != cv.h:
                self._lib_cache = cv.new_layer(cv.w, cv.h)
                self._lib_key = None      # freshly minted: no captured pixels
                self._lib_parts = None
            self._band_layer(cv)
        except Exception:  # noqa: BLE001
            self._lib_cache = None
            self._band_bg = None
            self._lib_unsupported = True

    def _band_layer(self, cv):
        """The band backdrop's layer, minted (or re-minted for a new band
        size) on demand."""
        bx, by, bw, bh = self.grid.band_rect()
        bg = self._band_bg
        if bg is None or bg.w != bw or bg.h != bh:
            if bg is not None and getattr(bg, "release", None) is not None:
                bg.release()
            self._band_bg = bg = cv.new_layer(bw, bh)
            self._band_key = None
        return bg

    def release_retained(self):
        """Free the retained-frame layer (the fit check's release, after any
        parked window stamps): True when there was one. The next settled
        visit re-mints and re-captures it. The band's backdrop and the
        cards' kept faces go with it."""
        freed = self.grid.release_faces()
        for name in ("_lib_cache", "_band_bg"):
            cache = getattr(self, name)
            if cache is None:
                continue
            setattr(self, name, None)
            rel = getattr(cache, "release", None)
            if rel is not None:
                rel()
            freed = True
        self._lib_key = None
        self._lib_parts = None
        self._band_key = None
        return freed

    def _band_key_of(self, cv):
        ws = self.ws
        return _statics_base(ws, cv, self.grid) + (ws.look.wallpaper_id,)

    def _capture_band_backdrop(self, cv, dt):
        """Copy the band's rect of the wallpaper just drawn -- before any
        chrome or card -- on every full paint, so an edited wallpaper (the
        Paint app's document keeps its id) is never restored stale. Not while
        the wallpaper animates (those frames are full paints anyway) and not
        on a canvas that retains nothing."""
        ws = self.ws
        self._band_key = None
        if (self._lib_unsupported or ws.animating(dt)
                or ws.wallpaper.restore_key(True) is not None):
            return                # (a wallpaper that restores needs no copy)
        if getattr(cv, "RETAINED_FRAMES", 0) < 1:
            return
        key = self._band_key_of(cv)
        try:
            bg = self._band_layer(cv)
            bx, by, _bw, _bh = self.grid.band_rect()
            bg.blit_strip(cv, -bx, -by)
            self._band_key = key
        except Exception:  # noqa: BLE001 -- forfeit, as the retained frame does
            self._band_bg = None
            self._band_key = None
            self._lib_unsupported = True

    def _backdrop_fill(self, cv, r):
        """The band's backdrop inside rect `r`: the wallpaper, restored from
        the captured band."""
        bx, by, _bw, _bh = self.grid.band_rect()
        cv.blit_strip_rect(self._band_bg, bx, by, r[0], r[1], r[2], r[3])

    def _capture_retained(self, cv, dt, parts=None):
        """Capture the frame just painted into the retained cache -- called at
        the END of a live draw, while cv is still the back buffer being painted
        (pre-present, so it is provably THIS frame; see __init__'s ping-pong
        note for why an idle capture cannot be trusted). Overlays and the
        cursor draw after this layer, so the copy is exactly our output. Costs
        one full-screen copy (~26ms on P4) charged only when the key CHANGED --
        once per settled state, not per frame. Skipped mid-drag/fling (the key
        carries the scroll offset, so every frame would re-capture) and while
        anything animates (those pixels are not a pure function of the key),
        which also forfeits the frame it holds: a live wallpaper has moved
        under it, and a gesture holding the wallpaper still must not stamp
        the frame of another moment (`Wallpaper.held`)."""
        ws = self.ws
        if self._lib_unsupported or self.grid.dragging or self.grid.flinging:
            return
        if ws.animating(dt):
            if ws.wallpaper.is_animating(dt):
                self._lib_key = None
            return
        if getattr(cv, "RETAINED_FRAMES", 0) < 1:
            return              # a canvas that retains nothing has no frame to copy
        key = self._retained_key(cv)
        if key == self._lib_key:
            return
        if parts is None and self._carousel():
            parts = self._still_parts(cv, ws.wallpaper.restore_key(True))
        bar = ws.bar_layer.shown_gen("home")
        try:
            cache = self._lib_cache
            lp = self._lib_parts
            if cache is None or cache.w != cv.w or cache.h != cv.h:
                cache = self._lib_cache = cv.new_layer(cv.w, cv.h)
                lp = None
            ws.perf.note_cost("home.frame.capture")
            if parts is not None and lp is not None and lp[0] == parts[0]:
                # The captured frame has this one's backdrop: only the
                # parts that moved since are copied.
                for r in self._moved_rects(parts, lp, bar):
                    cache.blit_strip_rect(cv, 0, 0, r[0], r[1], r[2], r[3])
            else:
                cache.blit_strip(cv, 0, 0)
            self._lib_key = key
            self._lib_parts = None if parts is None else parts + (bar,)
        except Exception:  # noqa: BLE001 -- a recording root has no pixels to
            self._lib_cache = None     # copy; forfeit the mechanism for the
            self._lib_key = None       # session rather than retry every paint
            self._lib_parts = None
            self._lib_unsupported = True

    def _moved_rects(self, parts, was, bar):
        """The rects of the desk home's frame `parts` (and bar key `bar`)
        that differ from the frame `was` held, where the two share a
        backdrop: the selection's, the band, the bar's and the hint strip."""
        g = self.grid
        out = []
        if was[1] != parts[1]:
            out.append(self._sel_rect())
        if was[2] != parts[2]:
            out.append(g.band_rect())
        if was[3] != bar:
            out.extend(self.ws.wallpaper.bars())
        h = g.foot()[5]
        if h[2] > 0 and h[3] > 0:
            out.append(h)
        return out

    def _carousel(self):
        """Whether the home shows the carousel (else the grid arrangement)."""
        return isinstance(self.grid, Carousel)

    def _try_band_frame(self, cv, dt):
        """The home's band frame (`_band_frame`), timed for the home
        diag's HITCH split: only once the band's backdrop holds this frame's
        wallpaper, every arrangement's cards lying on it. Any frame takes it
        -- a step, a settle -- where the wallpaper puts its own pixels back
        (the hint strip lies on it) on a canvas that keeps them (not a
        recording root, `_lib_unsupported`), but on the desk's carousel, whose
        selection is the hero beside the band (`_try_still_frame`). Never
        under touch's search line, which lies in the band."""
        bd = self._bd_now
        if bd is not None:
            fill = self.ws.wallpaper.restorer(cv, bd)
        elif (self._band_bg is None or self._band_key is None
              or self._band_key != self._band_key_of(cv)):
            return False
        else:
            fill = self._backdrop_fill
        if self._search_line() is not None or self._shelf_fed():
            return False
        steps = (bd is not None and not self._lib_unsupported
                 and not (self._carousel() and self.grid.desk()))
        return _band_frame(self, cv, dt, self.grid, self.id, fill, self.strip,
                           timed=True, steps=steps)

    def _face_key(self, bd):
        """What the cards' kept faces (`Launcher._faces_for`) are drawn
        under for a paint over backdrop `bd` (a `restore_key`): the look's
        generation, the plain ground's colour (None over a backdrop or a
        picture) and the font scale; None where the canvas keeps no
        pixels. And whether the band's backdrop goes back in one copy
        (`restore_whole`): a baked backdrop, a picture or the band's
        capture, whose cut round the cards costs more in calls than the
        bytes it saves."""
        ws = self.ws
        g = self.grid
        g.frame_no = ws.frame_state.frames_drawn
        g.restore_whole = True
        if self._lib_unsupported:
            g.face_key = None
            return
        gen = ws.look.look_gen
        flat = bd[1] if bd is not None and bd[0] == "bg" else None
        fs = ws.layout.fs
        k = g.face_key
        if k is None or k[0] != gen or k[1] != flat or k[2] != fs:
            g.face_key = (gen, flat, fs)     # (kept while it holds: a frame allocates nothing)

    def _outside_key(self):
        """What the home's parts outside the band show of the selection:
        the hint strip its verbs and its star (`_hint_groups`), or the bar's
        keys while the bar has them (`_draw_hints`), the handheld
        icons' caption band its cart and the day its line counts from. The
        hint strip's is made again only where what it is made of moved: the
        grid's selection or items (its `zone_gen`), its tab, the favourites
        (the settings rows' generation), the keys on the bar, the store's
        `can_manage`, the pointer samples the strip took (`_sgen`) and the
        input whose keys it names (a gamepad connecting changes them)."""
        g = self.grid
        ws = self.ws
        m = self._ok
        zg = g.zone_gen
        sg = ws.system.gen()
        tk = self._on_bar
        cm = getattr(ws, "can_manage", True)
        pg = self._sgen
        hk = _ui_draw.hint_kind()
        if not (m[1] == zg and m[0] is g and m[2] == g.tab and m[3] == sg and m[4] == tk
                and m[5] == cm and m[6] is g.favorite_for and m[9] == pg and m[10] == hk):
            it = self.favourable()
            m[7] = (self.zone_verbs(), it is not None and ws.carts.is_favorite(it), tk, pg, hk)
            m[0] = g
            m[1] = zg
            m[2] = g.tab
            m[3] = sg
            m[4] = tk
            m[5] = cm
            m[6] = g.favorite_for
            m[9] = pg
            m[10] = hk
        hint = m[7]
        now = m[8]
        if now is None or now[0] is not hint:
            now = m[8] = (hint, None)
        return now

    def _beside(self, cv, whole, draw=True):
        """The parts outside the band a selection changes (the hint strip,
        the handheld icons' caption band), inside the band's frame: each
        named under its key (`ui.held`) and drawn where the buffer this
        frame paints holds another selection's, or `whole`; their rects in
        `_beside_drew`. With `draw` False they are only named (a frame
        that drew them by other means)."""
        drew = self._beside_drew
        del drew[:]
        g = self.grid
        now = self._outside_key()
        if now is None:
            return
        kh = self._hk.of(now[0])
        held = _band.held("hint", kh)
        # where the last frame's buffer holds the frame round the band and
        # the part as this frame draws them, the part is copied out of it
        cl = (getattr(cv, "copy_last", None)
              if draw and not whole and _band.held_last("band", self._keys[0]) else None)
        if draw and (whole or not held):
            h = g.foot()[5]
            if h[2] > 0 and h[3] > 0:
                if not (cl is not None and _band.held_last("hint", kh)
                        and cl(h[0], h[1], h[2], h[3])):
                    self.ws.wallpaper.restorer(cv, self._bd_now)(cv, h)
                    self._draw_home_chrome(cv)
                drew.append(h)

    def _name_beside(self, cv, whole):
        """`_beside` naming the parts a whole paint drew."""
        self._beside(cv, whole, False)

    def _band_settle(self, end, whole=True):
        """After a band frame with nothing moving, by its floor's end
        (`ui.table_floor`): where every buffer holds this frame, the
        retained frame is owed to an idle frame (`capture_due`); where one
        lags behind a frame that drew the band `whole` (more than half of
        it: a scroll's, a jump's, a cover's landing), the frame that brings
        one more buffer to it is asked for, while nothing moves and no
        press waits (`_still_debt`). Behind a step that drew its cells
        alone, that frame is owed to an idle frame (`debt_due`): a frame
        between two steps of a rolling ball would only delay the second,
        and the next step's floor takes what that buffer lacks."""
        if end == 0:
            # (the statics this frame's band key was made of: `_band_key`)
            key = self._retained_key(self.ws.sys_canvas, self._sk.v)
            if key != self._lib_key:
                self._cap_owed = (self.ws.frame_state.frames_drawn, key, None)
        elif end == -1:
            if whole:
                self._still_debt()
            else:
                self._debt_owed = self.ws.frame_state.frames_drawn

    def _band_note(self, cv, dt, vouch=True):
        """A frame that put the band there by other means (the retained
        frame's stamp, a still frame that drew no band): the band's kept
        table and the parts beside it noted as this frame holds them."""
        g = self.grid
        return g.band_pass(cv, self.ws.covers.sheet_icon, None, _band_key(self, cv, dt, g, vouch),
                           True, _cursor_stamp(self.ws), self._name_beside if vouch else None,
                           note=True)

    def _band_landed(self, cv, dt, vouch=True):
        """After a pass that drew the band: where a cover landed while it
        drew (the cover gen moved from the one its key holds), the cards
        drew it, so the band is noted again under the key the new gen is
        in: the buffer then holds the band whole under that key. Answers
        whether it noted."""
        if self.ws.covers.gen != self._keyed_gen:
            self._band_note(cv, dt, vouch)
            return True
        return False

    # -- the desk home's still-backdrop frame ------------------------------
    #
    # On the desk the home is a still backdrop under three parts that
    # change: the hero with its details pane (the selection), the shelf's
    # band and the bar. A frame repaints only the parts the buffer it paints
    # lacks, where the wallpaper can put its own pixels back
    # (`Wallpaper.restore_key`): every buffer holds this backdrop once the
    # RETAINED_FRAMES frames before this one were the home's alone, on it,
    # and each of those frames left its buffer holding its own parts. A
    # part that differs from any of theirs lags in this frame's buffer.

    def _still_parts(self, cv, bd):
        """(backdrop, selection, band) keys of the desk home's frame: what
        everything outside the selection's rect and the band is a pure
        function of (the wallpaper's `restore_key` `bd` among it), what the
        hero and its details are, and what the shelf's band is (each of
        its moving frames another: its page moves in its pass). None off
        the desk, or where the backdrop cannot be put back."""
        g = self.grid
        if bd is None or not g.desk():
            return None
        ws = self.ws
        typing = getattr(ws, "search_typing", False)
        base = (bd, cv.w, cv.h, ws.layout.fs, ws.look.look_gen, g._geom(),
                ws.look.wallpaper_id, modal_keys(ws), getattr(ws, "search_query", ""),
                typing, typing and ws.text.can_type(), self._on_bar, self._back_tip)
        items = g.items
        it = items[g.nearest()] if items else None
        rows = ws.system.gen()
        gen = ws.covers.gen
        sel = g.statics_sel()
        return (base,
                (g.tab, sel, it, it and it.get("title"), it and it.get("description"),
                 gen, rows, self._dgen, g.today()),
                (g.tab, sel, gen, self._lhover, tuple(i.get("title") for i in items),
                 rows, g.scroll, g.moving and ws.frame_state.frames_drawn, g.tab_focus))

    def _sel_rect(self):
        """The desk home's hero and details pane with all they cast (the
        hero's shadow, a button's focus mark),
        between the bar and the shelf's band: what a change of the
        selection repaints."""
        g = self.grid
        lay = self.ws.layout
        q = g.quiet()[0]
        d = _ui_draw.depth()
        m = _ui_draw.mark_reach("cell") + 1
        if d[5]:
            m += d[8] + max(abs(d[9]), abs(d[10]))    # the hero's shadow
        x0 = max(lay.cx, q[0] - m)
        y0 = max(lay.cy, q[1] - m)
        x1 = min(lay.cx + lay.cw, q[0] + q[2] + m)
        y1 = min(g.band_rect()[1], q[1] + q[3] + m)
        return (x0, y0, x1 - x0, y1 - y0)

    def _fill_around_hero(self, cv, r, fill):
        """Put the backdrop back in the selection's rect `r` but under the
        hero, which paints its square opaque but for its corners' rows (as
        a shelf card does, `Carousel._fill_around_cards`); all of it in one
        copy where the band's goes back so (`restore_whole`)."""
        hx, hy, hs, _h = self.grid.hero_rect()
        x0 = r[0]
        y0 = r[1]
        x1 = r[0] + r[2]
        y1 = r[1] + r[3]
        if self.grid.restore_whole or not (x0 <= hx and y0 <= hy and hx + hs <= x1
                                           and hy + hs <= y1):
            fill(cv, r)
            return
        k = self.grid._corner_r(hs)
        k = min(k + _ui_draw.mark_reach("card") + 1 if k else 0, hs // 2)
        fill(cv, (x0, y0, r[2], hy - y0))
        fill(cv, (x0, hy + hs, r[2], y1 - hy - hs))
        fill(cv, (x0, hy, hx - x0, hs))
        fill(cv, (hx + hs, hy, x1 - hx - hs, hs))
        if k:
            fill(cv, (hx, hy, hs, k))
            fill(cv, (hx, hy + hs - k, hs, k))

    def _content_alone(self, dt):
        """Whether this frame's pixels are the home's alone: on top, nothing
        animating (its own band page moving on its own draws in the band),
        nothing drawn over it (`content_alone`)."""
        ws = self.ws
        wm = ws.wm
        if ws.animating(dt, False):
            return False
        top = getattr(wm, "top_kind", None)
        if top is not None and top() != self.id:
            return False
        alone = getattr(wm, "content_alone", None)
        return alone is not None and alone()

    def _note_still(self, cv, parts, bar=None):
        """Name this painted frame's parts in the band host's paint
        (`ui.held`, the paint the band's pass began this frame): the
        backdrop, the selection, the shelf, the bar's key (`shown_gen`) its
        strip was drawn under and the hint strip's. Answers whether every
        buffer now holds every part named (`ui.held_all`)."""
        if bar is None:
            bar = self.ws.bar_layer.shown_gen("home")
        self.grid.resume_band_host(cv)
        _band.held("still", self._stk.of(parts[0]))
        _band.held("sel", self._slk.of(parts[1]))
        _band.held("shelf", self._shk.of(parts[2]))
        _band.held("bar", bar)
        now = self._outside_key()
        if now is not None:
            _band.held("hint", self._hk.of(now[0]))
        return _band.held_all()

    def _try_still_frame(self, cv, dt):
        """The desk home's frame over its still backdrop: the parts this
        frame's buffer lacks (`ui.held` in the band host's paint) put back
        over the wallpaper's own pixels, and the bar. False when the frame
        must take another path."""
        ws = self.ws
        if (self._lib_unsupported or self._back_tip
                or self._search_line() is not None):
            return False
        parts = self._still_parts(cv, self._bd_now)
        if parts is None or not self._content_alone(dt):
            return False
        bar = ws.bar_layer.shown_gen("home")
        now = self._outside_key()
        kb = self._stk.of(parts[0])
        ks = self._slk.of(parts[1])
        kd = self._shk.of(parts[2])
        kr = bar
        kh = self._hk.of(now[0])
        g = self.grid
        fed = self._shelf_fed()
        g.begin_band_host(cv)
        if not _band.held("still", kb):
            return False                 # (the buffer holds another backdrop)
        laid = []
        if fed:
            # the shelf's input moves its selection in its pass: the band
            # first, then the parts keyed on the card it made current (a
            # backdrop that moved with it, the pane's rows, is a full paint's)
            laid = self._lay_parts(cv, dt, False, True, True)
            self._band_note(cv, dt)      # (under the keys of the card it made current)
            parts = self._still_parts(cv, self._bd_now)
            if self._stk.of(parts[0]) != kb:
                return False
            ks = self._slk.of(parts[1])
            kd = self._shk.of(parts[2])
            g.resume_band_host(cv)
        # what the buffer this frame paints lacks, and what the buffer the
        # last frame painted holds as this frame would draw it (§14.6),
        # asked before anything draws through another host
        sel_lag = not _band.held("sel", ks)
        band_lag = not _band.held("shelf", kd) and not fed
        bar_lag = not _band.held("bar", kr)
        hint_lag = not _band.held("hint", kh)
        last = _band.held_last("still", kb)
        rows = last and _band.held_last("bar", kr)
        sel_last = last and _band.held_last("sel", ks)
        band_last = last and _band.held_last("shelf", kd)
        hint_last = last and _band.held_last("hint", kh)
        wm = ws.wm
        # A part the last frame painted as this one would is copied out of
        # its buffer (§14.6): whole rows where the bar there is this one's.
        lay_sel = sel_lag and not (sel_last and self._copy_part(cv, self._sel_rect(), rows))
        lay_band = band_lag and not (band_last and self._copy_part(cv, g.band_rect(), rows))
        if bar_lag and rows and not (lay_sel or lay_band):
            for r in ws.wallpaper.bars():
                if not self._copy_part(cv, r, True):
                    break
            else:
                bar_lag = False
        laid += self._lay_parts(cv, dt, lay_sel, lay_band, sel_lag)
        h = g.foot()[5]
        # the hint strip, where the buffer shows another selection's verbs:
        # copied where the last frame drew these, else drawn
        if (h[2] > 0 and h[3] > 0 and (hint_lag or _overlaps_any(laid, (h,)))
                and not (hint_last and not _overlaps_any(laid, (h,))
                         and self._copy_part(cv, h, rows))):
            laid.append(h)
            ws.wallpaper.restorer(cv, self._bd_now)(cv, h)
            self._draw_home_chrome(cv)
            wm.hand_content_damage(cv, h[0], h[1], h[2], h[3])
        if not (lay_band or fed):
            self._band_note(cv, dt)      # (the buffer holds the band as it is)
        # A strip this buffer holds under this key stays, unless a part
        # above was put back over it.
        if bar_lag or _overlaps_any(laid, ws.wallpaper.bars()):
            ws.bar_layer.draw_status_strip("home")
        if self._note_still(cv, parts, bar):
            # every buffer holds this frame: the retained frame takes it once
            # nothing waits on the board (`capture_due`)
            key = self._retained_key(cv)
            if key != self._lib_key:
                self._cap_owed = (ws.frame_state.frames_drawn, key, parts)
        else:
            self._still_debt()
        return True

    def _shelf_fed(self):
        """Whether the desk carousel's shelf has input that may move its
        selection waiting on its page's next pass (a key, a release): the
        frame's band pass moves it before the hero and the details draw it
        (a still frame lays the band first; the band frame and the retained
        stamp, which draw no hero, decline the frame)."""
        return self._carousel() and self.grid.keyed and self.grid.desk()

    def debt_due(self):
        """Ask, on an idle frame, for the frame a step owed (`_band_settle`)
        where no frame has painted since it and nothing moves."""
        owed = self._debt_owed
        self._debt_owed = None
        ws = self.ws
        if owed is not None and owed + 1 == ws.frame_state.frames_drawn and not self.grid.moving:
            ws.mark_dirty()

    def capture_due(self):
        """Take the retained frame a still frame owed (`_cap_owed`) on an
        idle frame: every buffer held that frame when it was owed and still
        does while no frame has painted since and its key holds. Dropped
        otherwise -- a painted frame never pays it, so a run of taps does
        not; the next still frame that finds every buffer holding it owes
        it again."""
        owed = self._cap_owed
        self._cap_owed = None
        ws = self.ws
        if owed is None or ws.frame_state.frames_drawn != owed[0] + 1:
            return
        cv = ws.sys_canvas
        if self._retained_key(cv) == owed[1]:
            self._capture_retained(cv, 1 / 60, owed[2])

    def _copy_part(self, cv, r, rows):
        """Part rect `r` copied out of the buffer the last frame drew into,
        which holds it as this frame would draw it (§14.6) -- its whole rows
        with `rows`: what else they hold, the backdrop and the bar, is this
        frame's there too. False where the canvas cannot copy."""
        if rows:
            r = (0, r[1], cv.w, r[3])
        if not hasattr(cv, "copy_last") or not cv.copy_last(r[0], r[1], r[2], r[3]):
            return False
        self.ws.wm.hand_content_damage(cv, r[0], r[1], r[2], r[3])
        return True

    def _lay_parts(self, cv, dt, sel_lag, band_lag, marks):
        """Put the lagging parts back over the backdrop and draw them; the
        rects laid. `marks`: the buffer may hold the focus mark on another
        card."""
        ws = self.ws
        fill = ws.wallpaper.restorer(cv, self._bd_now)
        g = self.grid
        wm = ws.wm
        laid = []
        if sel_lag:
            r = self._sel_rect()
            laid.append(r)
            self._fill_around_hero(cv, r, fill)
            cv.clip(r[0], r[1], r[2], r[3])
            self._draw_details(cv)
            cv.clip()
            wm.hand_content_damage(cv, r[0], r[1], r[2], r[3])
        if band_lag:
            g.repaint_band(cv, ws.covers.sheet_icon, fill, _band_key(self, cv, dt, g, True),
                           _cursor_stamp(ws), None, False, marks, True)
            bx, by, bw, bh = g.band_rect()
            laid.append((bx, by, bw, bh))
            wm.hand_content_damage(cv, bx, by, bw, bh)
        return laid

    def _band_owed(self):
        """Whether a band pass that answered -1 (a buffer lags its band)
        owes the frames that bring every buffer to it: where the wallpaper
        puts its own pixels back and the band's keys stand. Keys of -1 (the
        band not the home's alone on the glass: a dialog over it) keep
        nothing, so no frame pays that debt."""
        return self._bd_now is not None and self._keys[0] != -1

    def _still_debt(self):
        """Ask for the frame that brings one more buffer to this frame,
        while nothing moves and no press waits on it (as the windowed WM
        pays its own, `debt_owed`)."""
        ws = self.ws
        if (not self.grid.moving and not ws.ptr_changed()
                and not getattr(ws.pointer, "down", False)):
            ws.request_frame()

    def draw(self, dt):
        """The home desktop: wallpaper backdrop -> cart icon grid -> top status
        strip. The wallpaper is drawn first and the rest layer over it, exactly the
        Picotron model (wallpaper shows through the chrome). All on the SYSTEM canvas,
        reflowed to its size + font scale (#39).

        There is no bottom tool dock: the launcher dropped it in #46 (its
        code/draw/map/run slots had no cart to act on, so it was a dead row) and it
        was deleted outright on 2026-08-21 -- see bar_layer.py. Settings is reached
        via the gear in the status strip; the cart grid keeps the freed bottom band
        (Layout.grid_bottom)."""
        ws = self.ws
        cv = ws.sys_canvas
        if ws.menu_ui.put_home(cv, dt):
            # the system menu's frame of the home, washed: the buffers hold
            # the scrim, no frame of the home's own (no band paint names
            # the home's parts in it)
            return
        carousel = self._carousel()
        if carousel:
            self.grid.dim = _dim_of(ws)
            self.details_owed()
        if self.grid.on_open is not self._on_open:
            self.grid.on_open = self._on_open
        self.grid.wall_ink = self._wall()
        self.grid.ground = _ground_of(ws)
        # Kinetic fling (#113) and the shelf's glide: advance the row BEFORE
        # painting, and keep the redraw gate open until it rests (the
        # handheld's carousel moves itself in its band's pass). Both ride
        # the partial path (its gate includes flinging).
        self.grid.anim_frame(dt)
        if self.grid.flinging:
            ws.request_frame()
        self._bd_now = ws.wallpaper.restore_key(True)
        if carousel:
            self.grid.restore_whole = True
        else:
            self._face_key(self._bd_now)
        if carousel and self._try_still_frame(cv, dt):
            return
        if self._try_band_frame(cv, dt):    # the band's frame (#58/#66): it names
            return                          # the band and the hint strip alone
        # Retained-frame stamp (2026-07-27): a re-entry whose pixels are provably
        # identical to the captured frame presents it in one blit. Bookkeeping
        # matches a full paint exactly -- pixel-wise it IS one -- so the
        # band's record stays honest.
        # (under the menu's hold the retained frame is the one before it)
        if (not ws.menu_ui.holds_home() and not self._shelf_fed()
                and self._try_stamp_retained(cv, dt)):
            if self._band_note(cv, dt) == -1 and self._band_owed():
                self._still_debt()
            parts = self._still_now(cv, dt)
            if parts is not None and not self._note_still(cv, parts):
                self._still_debt()
            return
        # perf_capture (#66 instrument-before-cutting): time the home frame's
        # three sections so a slow launcher frame names its eater (PERF's
        # home= field carries ws.pf_home -- wallpaper vs grid vs bar).
        _t0 = _ticks_ms() if getattr(ws, "perf_capture", False) else None
        ws.wallpaper.draw(dt, home=True, quiet=self._quiet(ws))
        self._capture_band_backdrop(cv, dt)
        _t1 = _ticks_ms() if _t0 is not None else None
        # The hint strip and the cells' band (docs/theme_and_shell_2026-11.md
        # §8.10) over the wallpaper; the cards draw inside the band.
        self._draw_home_chrome(cv)
        if not carousel:                      # (a carousel's cards draw: no faces)
            self._face_key(ws.wallpaper.restore_key(True))
        # (the band's kept table records this paint: the cursor's stamp about
        # to land on top in it, and the parts beside the band named)
        end = self.grid.draw(cv, ws.covers.sheet_icon, _band_key(self, cv, dt, self.grid, True),
                             _cursor_stamp(ws), self._name_beside)
        self._band_landed(cv, dt)
        if carousel and self.grid.desk():
            self._draw_details(cv)
        _t2 = _ticks_ms() if _t0 is not None else None
        ws.bar_layer.draw_status_strip("home")
        if self._back_tip:
            self._draw_back_tip(cv)
        if _t0 is not None:
            _t3 = _ticks_ms()
            ws.pf_home = (_ticks_diff(_t1, _t0), _ticks_diff(_t2, _t1),
                           _ticks_diff(_t3, _t2))
        if end == -1 and self._band_owed():
            self._still_debt()       # every buffer to this frame: the next step is a band frame
        parts = self._still_now(cv, dt)
        owed = parts is not None and not self._note_still(cv, parts)
        if not ws.menu_ui.holds_home():
            # (under the menu the retained frame stays the one its close stamps)
            self._capture_retained(cv, dt, parts)   # retain this frame for re-entry stamps
        if owed:
            self._still_debt()

    def _still_now(self, cv, dt):
        """This whole frame's parts where it is the home's alone, else None."""
        if not self._carousel() or not self._content_alone(dt):
            return None
        return self._still_parts(cv, self.ws.wallpaper.restore_key(True))

    def _hover_back(self, px, py, click, down):
        """Whether a mouse rests on the bar's chevron back to the desk (the
        home in console mode over a desk, `BarLayer.back_rect`): a pointer
        that moves with nothing held, never a touch, which has no hover."""
        if click or down or _ui_draw.input_kind() == "touch":
            return False
        r = self.ws.bar_layer.back_rect("home")
        return r is not None and _in(px, py, r)

    def _draw_back_tip(self, cv):
        """The chevron's tooltip, `BACK_TIP` in the flat toast of
        `overlay_ui.tip` under it, its left edge the chevron's: where it
        goes, which the bare chevron does not say (owner, 2026-10-19). The
        pill is laid out once out of sight for its size, again when the
        layout or the look moves."""
        ws = self.ws
        r = ws.bar_layer.back_rect("home")
        if r is None:
            return
        import console_notices as _cn
        n = ws.notices
        n.put_overlay(_cn.TIP, "tip", BACK_TIP)
        at = self._tip_at
        look = ws.look.look_gen
        if at[0] is None or at[1] is not ws.layout or at[2] != look:
            at[1] = ws.layout
            at[2] = look
            got = n.paint_overlay(_cn.TIP, cv, n.room(_cn.TIP, -2 * cv.w, 0, cv.w, cv.h))
            at[0] = (got[2], got[3])
        u = _lb.unit()
        n.paint_overlay(_cn.TIP, cv, n.room(_cn.TIP, r[0], ws.layout.cy + 4 * u, at[0][0], at[0][1]))

    def _draw_home_chrome(self, cv):
        """The hint strip along the home's foot (its tabs are the bar's)."""
        self._draw_hints(cv)

    def _search_open(self):
        """Whether the home's search is open: a query held or being typed."""
        ws = self.ws
        return bool(self.searchable and (getattr(ws, "search_query", "")
                                         or getattr(ws, "search_typing", False)))

    def _search_line(self):
        """(x, y, w, h) of the handheld home's search line while search is
        open: the hint strip, or under touch, which has none, a line on the
        home's ground 4 units over the glass's foot (design review R5-04);
        None while search is closed."""
        if not self._search_open():
            return None
        rect = self.grid.foot()[5]
        if rect[3] > 0:
            return rect
        lay = self.ws.layout
        h = lay.line_h
        return (rect[0], lay.cy + lay.ch - 4 * lay.fs - h, rect[2], h)

    def _quiet(self, ws):
        """The home's quiet rectangles for its wallpaper: the bars and the
        arrangement's own (`quiet`); kept while both are the same objects,
        so a live wallpaper's frame builds nothing."""
        bars = ws.wallpaper.bars()
        own = self.grid.quiet()
        hit = getattr(self, "_quiet_key", None)
        if hit is not None and hit[0] is bars and hit[1] is own:
            return hit[2]
        q = bars + own
        self._quiet_key = (bars, own, q)
        return q

    def handle_input(self, i):
        ws = self.ws
        if getattr(ws, "search_typing", False):
            return self._search_keys(i)
        ws.ach_ui.konami_watch(i)
        if self._pane_keys(i):
            return True
        if self._hint_keys(i):
            return True
        grid = self.grid
        # The band page's keys (the carousel, §12, the grid, the icons): the
        # arrows (a held key's repeats, the wheel's notches) step it, Enter
        # opens its card (`_band_open`); up at the top goes on to the bar
        # (`at_top`, the router's), on the desk's carousel to the details
        # pane's buttons first.
        if grid is None:
            self._card_keys(i)
            return True
        desk = self._carousel() and grid.desk()
        if grid.band_keys(i):
            ws.mark_dirty()
        if i.steps("up") and desk and self._desk_buttons():
            self._button_focus = 0
        self._card_keys(i)
        return True

    def _card_keys(self, i):
        """The card's keys beside the arrows: a gamepad's X its verbs, B
        back, Home the home key."""
        ws = self.ws
        if i.pressed("x"):
            self.open_card_menu()            # a gamepad's X: the card's verbs
        if i.pressed("b") and ws.ach_ui._konami_pos == 0:
            self._back()                     # (a B inside the Konami code is the code's)
        elif i.pressed("home"):
            ws.home.home_key()

    def favourable(self):
        """The selected card where it takes the favourite star (a cart of
        the store's on a home that keeps favourites), else None."""
        grid = self.grid
        it = grid.selected()
        if grid.favorite_for is None or it is None or not it.get("path") \
                or it.get("type") in PSEUDO_TILE_TYPES:
            return None
        return it

    def toggle_favourite(self):
        """Star or unstar the selected card (the badge's tap, F, the card
        menu's row); False where it takes no star."""
        it = self.favourable()
        if it is None:
            return False
        self.ws.carts.toggle_favorite(it)
        return True

    def _back(self):
        """B: closes a held search, cleared; else the home's X, from a
        keyboard -- where the X shows."""
        if self._search_open():
            self.ws.home.close_search(clear=True)
        elif self.ws.bar_layer.show_x(self.strip):
            self.ws.home.open_desk()

    # The doors out of the home.
    def _launch(self):
        self.ws.home.launch_selected(self.grid)

    def _band_open(self):
        """The handheld band's card opened (Enter, a tap on the centre card
        at rest): the active tab's tap, behind the painted frame (#184)."""
        self.ws.defer(self._launch)

    def _change(self):
        self.ws.home.change_selected(self.grid)

    def _new(self):
        self.ws.home.new_cart_and_edit(self.grid)

    def _grid_pointer(self, px, py, click):
        """The grid and icons arrangements' pointer, their band page's: a
        drag scrolls the cells and a release flings them, a tap on a card
        selects it and fires the active tab's tap (`_band_open`), so a drag
        never launches; a mouse's cursor selects the card it moves onto."""
        ws = self.ws
        grid = self.grid
        down = ws.pointer.down
        if grid.band_point(px, py, click, down):
            ws.mark_dirty()
        if click or down:
            self._lhover = (px, py)
            return True
        if self._lhover == (-1, -1):
            self._lhover = (px, py)
        elif (px, py) != self._lhover:
            self._lhover = (px, py)
            i = grid.tile_at(px, py)
            if i is not None and i != grid.sel:
                grid.sel = i
                # A selection move MARKS DIRTY (#177): in a window the content
                # freeze reuses the retained buffer on position-only frames.
                ws.mark_dirty()
        return True

    def handle_pointer(self, px, py, click):
        # The home (§12): the bar and the tab row fire on the press edge; the
        # carousel rides ui.DragTap, so a tap fires on a clean RELEASE and a
        # drag can never launch a cart. A tap on the centre card is the
        # active tab's tap; on any other card it glides that card to the
        # centre. The favorite star on the centre card fires on the press.
        ws = self.ws
        down = ws.pointer.down
        grid = self.grid
        tip = self._hover_back(px, py, click, down)
        if tip != self._back_tip:
            self._back_tip = tip
            ws.mark_dirty()
        if not click and self._sptr and self._strip_point(px, py, False, down):
            return True
        if click:
            self._hold = None
            if self._button_focus is not None:
                self._button_focus = None    # a press takes the keys' mark away
            if ws.bar_layer.handle_bar_tap(self.strip, px, py):
                return True
            if self._search_tap(px, py) or self._strip_point(px, py, True, down):
                return True
            frect = grid.favorite_rect(grid.sel)
            if frect is not None and _in(px, py, frect):
                self.toggle_favourite()
                return True
        if self._carousel() and grid.desk() and self._pane_point(px, py, click, down):
            return True
        if self._long_press(px, py, click, down):
            return True
        if not self._carousel():
            return self._grid_pointer(px, py, click)
        # the carousel's band page's pointer: a drag moves the row (the
        # desk's shelf) and a release flings it, a tap slides a card to the
        # centre (on the desk makes it current) or opens the current one
        # (`_band_open`)
        if grid.band_point(px, py, click, down):
            ws.mark_dirty()
        if click or down:
            self._lhover = (px, py)
        return True

    def _long_press(self, px, py, click, down):
        """A press held `LONG_PRESS_MS` on a card without travel selects
        that card and opens its verbs (`open_card_menu`), the phone home
        screens' long press; the gesture ends there, so its release is no
        tap. True the frame it opens."""
        grid = self.grid
        if click:
            i = grid.tile_at(px, py)
            self._hold = None if i is None else [i, px, py, 0.0]
            return False
        h = self._hold
        if h is None:
            return False
        slop = 4 * self.ws.layout.fs + 2              # the DragTap's own
        if not down or grid.dragging or abs(px - h[1]) > slop or abs(py - h[2]) > slop:
            self._hold = None
            return False
        h[3] += self.ws.frame_state.frame_dt_ms
        if h[3] < LONG_PRESS_MS:
            return False
        self._hold = None
        grid.band_cancel()                             # the gesture ends untapped
        if h[0] != grid.sel and 0 <= h[0] < len(grid.items):
            grid.sel = h[0]
        self.open_card_menu((h[1], h[2]))
        self.ws.mark_dirty()
        return True

    def open_card_menu(self, at=None):
        """The selected card's verbs (`card_verbs`) as a menu hung at `at`,
        (x, y) on the system canvas -- a long press's point, else the
        card's middle (the desk's hero's): a long press, a gamepad's X, the
        strip's Options. False where the card has none."""
        if not self.card_verbs():
            return False
        if at is None:
            grid = self.grid
            r = grid.hero_rect() if self._carousel() and grid.desk() else None
            r = r or grid.tile_rect(grid.sel)
            if r is None:
                c = self.ws.layout
                at = (c.cx + c.cw // 2, c.cy + c.ch // 2)
            else:
                at = (r[0] + r[2] // 2, r[1] + r[3] // 2)
        return self.ws.menu_ui.open_card(self, at)

    # -- the lent left zone (Stage 4, #46 zoned bar) --------------------------

    _zone_tab = None     # the open tab `zone_gen` last saw
    _zone_n = 0          # ...and the count it moved

    @property
    def zone_gen(self):
        """What the zone's pixels follow, as one int that only grows: a
        count of the open tab's moves (the row's own moves are its
        `BarZone.gen`, which the bar adds)."""
        tab = self.grid.tab
        if tab != self._zone_tab:
            self._zone_tab = tab
            self._zone_n += 1
        return self._zone_n

    def _do_verb(self, verb):
        """One of the active tab's verbs on the selected card (§12's table),
        from a zone chip, a hint or its key."""
        ws = self.ws
        if verb in ("play", "open"):
            ws.defer(self._launch)   # #184: start behind the paint
        elif verb == "change":
            ws.defer(self._change)
        elif verb == "new":
            ws.defer(self._new)
        elif verb == "copy":
            ws.carts.dup(self.grid.selected())
        elif verb == "delete":
            ws.confirm.ask(self.grid.selected())   # never on one press: it asks
        elif verb == "favourite":
            self.toggle_favourite()
        elif verb == "send":
            ws.link.beam_send(ws, self.grid.selected())
        elif verb == "save":
            ws.page.save_cart(self.grid.selected())
        elif verb == "pod":
            ws.page.play_on_console(self.grid.selected())
        elif verb == "options":
            self.open_card_menu()
        elif verb == "window":
            ws.defer(self._play_window)
        else:
            ws.home.toggle_search()
        ws.mark_dirty()

    def _play_window(self):
        """Make's Play on the desk: the selected cart run in a desk window
        with its strip, not full screen (`WindowedWM.play_in_window`)."""
        sel = self.grid.selected()
        if sel is None:
            return
        self.ws.open(sel)
        self.ws.wm.play_in_window()


class HomeWindowLayer(LauncherHomeLayer):
    """The "projects" content Layer: the home in a desktop-mode window, the
    desk's PROJECTS (docs/theme_and_shell_2026-11.md §8.10). The same tabs,
    sources, taps and verbs over its own card model, ws.projects_grid, a
    `Carousel` whatever the fullscreen home's arrangement, opened on Make:
    the console home's design (step 18) laid out in the window's content
    rect -- the hero, its details and buttons, the shelf under them, the
    hint strip along the foot and the tabs in the window's band. A narrow
    window stands the hero over its details (`Carousel._geom_desk`).

    A window is a tool space: the panel field under the cards, never the
    wallpaper (the desk shows its own around the window), so nothing in it
    animates and an idle window draws nothing. The WM retains the window's
    buffer, so it keeps no retained frame of its own; a drag rides the
    shared `_band_frame` and the WM's content-gesture path."""

    id = "projects"
    strip = "projects"
    searchable = False

    @property
    def grid(self):
        return self.ws.projects_grid

    def _back(self):
        """B closes this window alone, as its title strip's X does."""
        self.ws.wm.close_window_kind(self.id)

    def _desk_verbs(self):
        """The home's buttons, and on Make a real card's Play third (owner,
        2026-10-31): the game in a desk window, where a desk play is full
        screen."""
        out = LauncherHomeLayer._desk_verbs(self)
        if self.grid.tab == "make" and "change" in out:
            out = list(out)
            out.insert(min(2, len(out)), "window")
        return out

    def _wall(self):
        return None                           # the window lies on its panel

    def _hover_back(self, px, py, click, down):
        return False                          # the window's X is the way out

    def prealloc_retained(self):
        return

    def release_retained(self):
        return False

    def _panel_fill(self, cv, r):
        """The band's backdrop: the window's panel."""
        cv.rect(r[0], r[1], r[2], r[3], self.ws.theme_colors["panel"])

    def _try_band_frame(self, cv, dt):
        return _band_frame(self, cv, dt, self.grid, self.id, self._panel_fill,
                           self.strip)

    def _outside_key(self):
        return None

    def draw(self, dt):
        ws = self.ws
        cv = ws.sys_canvas
        grid = self.grid
        th = ws.theme_colors
        dim = _dim_of(ws)                     # the neighbours dim toward the panel
        grid.dim = None if dim is None else (th["panel"], dim[1])
        grid.wall_ink = None
        grid.anim_frame(dt)
        self.details_owed()
        if grid.flinging:
            ws.request_frame()
        if self._try_band_frame(cv, dt):    # drag-scroll fast path (#113)
            return
        cv.cls(th["panel"])
        self._draw_home_chrome(cv)
        grid.draw(cv, ws.covers.sheet_icon, _band_key(self, cv, dt, grid, False),
                  _cursor_stamp(ws))
        self._band_landed(cv, dt, False)
        if grid.desk():
            self._draw_details(cv)
        ws.bar_layer.draw_status_strip(self.strip)
