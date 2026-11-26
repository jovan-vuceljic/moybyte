# Map (grep -n a name to jump there):
#   _BackdropLayer                      the desk's root layer: wallpaper, bar, icon column
#   _BackdropLayer.draw                 a frame: render live, restore the cache, or skip
#   _BackdropLayer._desk_sig            what the cached desk was drawn from
#   _BackdropLayer._column_sig          the icon column's own input, motion and focus
#   _BackdropLayer._column_rect         the column's rectangle, repainted alone
#   _BackdropLayer.owe_bar              a cache that takes the whole bar at its next restore
#   _BackdropLayer._draw_desktop        the desk rendered live
#   _BackdropLayer._icon_rects          the desk tiles' rectangles
#   _BackdropLayer._draw_look_icons     the tiles drawn in the theme's look
#   _BackdropLayer._open_icon           a tile opened: its app or cart
#   _BackdropLayer.handle_pointer       a tap or a drag on the desk
"""The windowed desk's ROOT layer: the wallpaper + the one OS bar + the desk
icon column, with the retained-backdrop cache a gesture blits instead of
re-rendering the desk (#58/#155), and under the theme's depth the windows'
shadows and outline fringes over whatever of it was just painted (the cache
holds the desk without them). `WindowedWM` holds one as `_backdrop_layer`
and hands it the cache state; the layer decides per frame whether to render
live, blit the cache (painting the column or the bar again over it where
only they moved), or skip the restore outright.
"""

from array import array

from layers import Layer
from widgets import _ticks_ms
import ui_draw as _ui_draw
import chrome_ops as _ch_ops
import layout_base as _layout_base
import iconsets as _iconsets
from status_items import ITEMS as _ITEMS

_NONE = -2147483648
# The column's geometry words (moy_ui_api.h's MOY_UI_CELLS_*)
_G_SIDE, _G_X0, _G_Y0, _G_PX, _G_PY, _G_ROWS, _G_TITLE_DY = 0, 2, 3, 4, 5, 6, 8


def _set(v):
    """A look leaf that is set: a value, not silent (None) or MOY_THEME_NONE."""
    return type(v) is int and v != _NONE


def _tile_fill(tiles, key):
    """Desk key `key`'s colour of a look's `tiles` (docs/history/look_2026-10.md
    step 26b), which names an app by its icon slot (Paint's `artwork` is the
    `paint` tile), or None."""
    slot = _iconsets.slot_of(key)
    v = tiles.get(_iconsets.SLOTS[slot] if slot is not None else key)
    return v if _set(v) else None


def _hex(v):
    """Look colour `v` as "#RRGGBB" (its RGB565 word widened)."""
    w = _ui_draw._C.theme_rgb(v)[0]
    r, g, b = w >> 11 & 31, w >> 5 & 63, w & 31
    return "#%02X%02X%02X" % (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2)


class _NoDamage:
    """The column page's damage: the desk draws it whole whenever it draws."""

    def all(self):
        pass


class _BackdropLayer(Layer):
    """The real desktop root (wallpaper + ONE OS bar) with a DRAG cache (#58).
    The home is a launch surface only while the process stack has no windows;
    as soon as PLAY/CHANGE pushes one, this layer replaces it so the home
    never reads as wallpaper behind Studio. During a drag/resize only the window
    position changes, so the first frame captures the desktop and later frames
    blit the retained backdrop.

    Correctness: this layer precedes _win_layer in the z-order, so the capture
    snapshots the desktop backdrop with NO windows on it; each drag frame blits
    that clean backdrop (erasing the dragged window's old position for free) and
    _win_layer then stamps the windows at their current spots. Double-buffer-safe
    -- the cache is its own off-screen buffer, re-blitted into whichever ping-pong
    buffer the frame targets. The desktop background routes only its OS bar;
    hidden Library cards cannot be activated through it."""

    id = "launcher"
    domain = "system"

    def __init__(self, wm):
        self.wm = wm
        self.ws = wm.ws
        self._cat_at = [None, None, None]  # what `_cat_sig` was made at (`_column_sig`)
        self._cat_sig = None
        self._catalog = None          # the `_icon_catalog` `_cat_sig` was made of
        # The column's rects (`_icon_rects`), the quiet rectangles and the
        # tiles' look, each kept while what it was made from stands: a live
        # desk draws the column every frame.
        self._rects_at = [None, None, None]
        self._rects = None
        self._quiet_at = [None, None]
        self._quiet = None
        self._style_at = [None, None, None]
        self._tink = 0                # the tiles' icons' ink (`_draw_look_icons`)
        # The column's page (`desk_ui.tiles`) on its own app host, what its
        # rows were last put from, its pictures' keys, its geometry's words
        # and the count its input and its motion move (`_desk_sig`).
        self._page = None
        self._host = None
        self._put_at = [None, None, None, None, None]
        self._pic_ix = {}
        self._g = array("i", [0] * 16)
        self._band = array("i", [0] * 4)
        self._cells = array("i", [0] * 25)   # the column as it drew (`focused`)
        self._gcv = None
        self._box = [0, 0, 0, 0]      # a tile's icon square (`_tile_picture`)
        self._open_fn = self._tile_open   # (bound once: a frame allocates none)
        self._fed = 0
        self._fed_drawn = 0           # the `_fed` the cache's column was painted at
        self._mark = False            # the column could show its focus mark as it drew
        self._bar_owed = False        # the windows' chips moved since the cache's bar
        self._bar_stop = None         # the desk bar's stop the keys were on as it drew
        self._popped = False          # the column's last paint showed a popover
        self._pop = array("i", [0] * 4)
        self._col_at = None           # the `_icon_rects` `_col` was made of
        self._col = None
        self._sig_keys = [None] * 11  # `_desk_sig`'s values, compared in place
        self._sig_gen = 0             # ...and the count that moves with them

    def draw(self, dt):
        wm = self.wm
        # A CONTENT gesture (a finger scrolling inside a window) counts as a
        # gesture for cache purposes, exactly like a window drag/resize (#155,
        # owner "the project picker is choppy, the play launcher is smooth").
        # The desk cannot change while a window's content is being dragged, but
        # this layer used to re-render the whole desktop -- wallpaper cover-crop
        # + icon column + bar -- on EVERY such frame. Measured on glass during a
        # picker scroll: 107ms of a 181ms frame (~5fps) against the fullscreen
        # Library's 36ms, which pays no desk at all. The cached blit is ~26ms.
        # Same staleness trade the window-drag path already accepts: a clock tick
        # mid-gesture waits for the release, which re-renders live.
        content_anim = wm._content_gesture or wm._content_flinging()
        gesture = (wm._drag is not None or wm._resize is not None
                   or content_anim)
        # The cache is gated on the desk being UNCHANGED, not on being in a
        # gesture (#155). Gating it on the gesture meant every non-gesture
        # painted frame re-rendered the whole desk -- wallpaper cover-crop + icon
        # column + bar -- which on P4 glass is a 120ms frame, and one landed on
        # every gesture RELEASE. The desk's own content is a pure function of the
        # signature below; the clock is the one live part and it is repainted
        # over the cached blit instead of invalidating it.
        if wm._pop_live():
            wm._pop_restore(False)            # start as if no popover were drawn
        sig = self._desk_sig()
        stale = sig != wm._desk_sig
        wm._damage_rects = None               # opened below where describable
        # A change to the window SHAPE (open/close/minimize/move/resize) uncovers
        # desk the departed window was covering -- pixels the skip's own
        # justification ("fully covered by the window's stamp") no longer holds
        # for. The desk STATICS are unchanged then (the cache stays valid); only
        # the restore must actually run again, so reset the skip streak. Same
        # one-signature-beats-hunting-mutation-sites rule as the stamp voider.
        # (Owner report 2026-07-27: "close it and it remains as an artifact on
        # the desktop" -- the close frame skipped the restore outright.)
        # A DISCRETE shape change (open/close/minimize/maximize) restores the
        # WHOLE cached desk into the frame's buffer, never a gesture's union
        # (which would miss the footprint of another window that departed),
        # and every buffer after it takes it again (the streak). The cache is
        # the desk as its last live render captured it, and the statics' sig
        # renders it live again when any of it moved, so the open of an app
        # pays a copy, not a render of the desk.
        # NEVER for gesture-driven changes: the trail machinery restores a
        # gesture's footprint, and a full restore on every drag frame or on
        # its RELEASE is the 120ms frame #155 killed. So the holder TRACKS the
        # sig silently while a gesture is live -- release finds it equal --
        # and only a discrete change (open/close/min/max) restores whole.
        # Focus is deliberately NOT in this sig: focus moves no desk pixels.
        s = wm._shape_sig()
        # order + geometry; focus too under the depth, whose shadows and
        # outline fringes (drawn here, draw_unders) follow it (odd: the
        # shape's count, even: the places', so the two never meet)
        wsig = 2 * s + 1 if _ui_draw.depth()[12] else 2 * wm._place_gen
        if wsig != wm._desk_win_sig:
            wm._desk_win_sig = wsig
            if wm._drag is None and wm._resize is None:
                wm._desk_streak = 0
                wm._gesture_hist = []
                wm._rest = None
                self._bar_owed = True
        # The keys walked onto, along or off the desk's bar: its focus mark
        # is the bar's, which the cache holds as it was, so the bar is drawn
        # again over it and taken in.
        bl = self.ws.bar_layer
        stop = bl.focus if bl.focus_where == "desk" else None
        if stop != self._bar_stop:
            self._bar_stop = stop
            self._bar_owed = True
            wm._desk_streak = 0
        if wm.full_cover() >= 0:
            # A full-screen window covers the desk, its bar and the shadows
            # cast on it: nothing here shows, so nothing is drawn. Leaving
            # full screen is a shape change, which restores the desk whole.
            wm._desk_painted = False
            wm._damage_rects = ()
            return
        moves = wm.desk_moves(dt)             # its pixels move on their own
        # The column's page took input or moves (a press, a focus step), or
        # its focus mark came or went (the keys went to a window or the bar,
        # or came back; touch shows none): it alone is painted again over the
        # cache (`_parts_again`) where the backdrop under it can be put back
        # and no gesture restores a union.
        mark = (wm.focus_key is None and not _ui_draw.on_bar()
                and _ui_draw.input_kind() != "touch")
        if mark != self._mark:
            self._mark = mark
            self._fed += 1
        col = self._fed != self._fed_drawn
        if (stale or wm.backdrop_disabled or wm._backdrop_unsupported or moves
                or (col and (gesture or not wm._backdrop_valid or self._popped
                             or self.ws.wallpaper.restore_key(False) is None))):
            wm._desk_sig = sig
            self._fed_drawn = self._fed
            self._bar_owed = False
            wm._backdrop_valid = False        # live: re-render (a still one re-snapshots)
            wm._desk_streak = 0
            wm._desk_painted = True           # wiped the buffer -> windows repaint
            if wm._gesture_hist and not gesture:
                wm._gesture_hist = []         # gesture over: drop the damage trail
            wm._rest = None                   # a live desk lays every buffer whole
            self._draw_desktop(dt)
            if not moves:
                # (a desk that moves renders live again next frame: its
                # snapshot would be thrown away unread; a gesture's first
                # frame, over a held wallpaper, takes it below)
                wm._capture_backdrop()
            self._bar_drawn(wm._backdrop_valid)
            wm.draw_unders()
            # This buffer holds the cache it just took, and the clock: one of the N.
            wm._desk_streak = 1 if wm._backdrop_valid else 0
            wm._clock_drawn()
            return
        if wm._backdrop_valid:
            # CONTENT gesture: the window is STATIONARY, so the desk outside it
            # never changes and the desk under it is fully covered by the
            # window's own stamp. Once the cache has been laid into BOTH
            # ping-pong buffers (two consecutive gesture frames), every later
            # frame's target already holds the right pixels -- skip the restore
            # entirely. That is the last ~28ms between a windowed content scroll
            # and the fullscreen Library's (owner: "choppy vs smooth"). A window
            # DRAG still restores every frame: there the window moves, so the
            # backdrop it uncovers is genuinely damaged.
            if wm._drag is None and wm._resize is None:
                # A VISIBLE cursor whose drawn state changed forces the restore:
                # the cursor sprite from the last paint is baked into the
                # retained buffer, and skipping here left a trail of stale
                # cursors across the desk (measured on the host: from the third
                # consecutive moving frame on). Finger gestures keep the #155
                # skip -- the cursor is hidden there, nothing to erase.
                tile = self.ws.bar_layer.tile_on()
                if tile != wm._tile_shown:
                    # a popover opened or closed over a bar item it selects:
                    # every buffer takes the item as it now stands
                    wm._tile_shown = tile
                    wm._desk_streak = 0
                ptr = self.ws.ptr_state()
                last = self.ws.last_ptr
                cursor_live = ((ptr is not None and ptr[2])
                               or (last is not None and last[2]))
                if not (cursor_live and ptr != last) and not col \
                        and wm._desk_streak >= wm.retained_n() and not wm._scrim_up():
                    wm._desk_painted = False   # untouched: windows may skip too
                    wm._damage_rects = ()      # the desk changed nowhere
                    wm._desk_clock()
                    return
                wm._desk_streak += 1
            wm._desk_painted = True
            _perf = getattr(self.ws, "perf_capture", False)
            _t0 = _ticks_ms() if _perf else 0
            union = wm._blit_backdrop_cache()
            if wm._restored is None:
                laid = wm._bar_laid           # the cache's bar, laid whole
                laid[0] = self.ws.frame_state.frames_drawn
                laid[1] = wm._cache_clock
            if col or self._bar_owed:
                self._parts_again(col)
            if wm._restored is not False:
                wm.draw_unders(wm._restored)
            land = getattr(wm.root_canvas, "show_landed", None)
            if land is not None:
                land()                         # the last frame's stamp landed under it
            if _perf:
                self.ws.pf_wm_restore = _ticks_ms() - _t0
            if union is not None:
                one = wm._damage_one             # the desk changed inside the gesture
                one[0] = union
                wm._damage_rects = one
            bar = self.ws.bar_layer
            wm._desk_clock()
            if bar.tile_on() != wm._desk_tile:
                wm._outside_f = self.ws.frame_state.frames_drawn
                bar.redraw_tile("desk")        # the cache holds the button's other state
            return
        wm._desk_streak = 0
        wm._desk_painted = True
        wm._rest = None
        self._fed_drawn = self._fed
        self._bar_owed = False
        self._draw_desktop(dt)                # cache lost: render + re-snapshot
        wm._capture_backdrop()
        self._bar_drawn(wm._backdrop_valid)
        wm.draw_unders()
        wm._desk_streak = 1 if wm._backdrop_valid else 0
        wm._clock_drawn()

    def _desk_sig(self):
        """Everything the desk's wallpaper + icon column depends on, the
        layout's content rect among it (the bars a mode switch moves): a count
        that moves whenever any of it does.

        The apps' status items are in its bar (their `gen`).

        The column page's input and motion are not (`_fed`): a change of
        the column alone paints the column again (`_parts_again`).

        Deliberately NOT the clock (repainted over the cache instead) and NOT
        ws.covers.gen: a cover landing in the picker would otherwise invalidate
        the desk on the very frames a scroll is trying to stay cheap. Cheap to
        compute -- no per-frame scan of the cart list (`_column_sig`)."""
        ws = self.ws
        cv = ws.sys_canvas
        lay = ws.layout
        look = ws.look
        k = self._sig_keys
        if (k[0] != cv.w or k[1] != cv.h or k[2] != look.look_gen
                or k[3] != look.effective_font_scale() or k[4] != look.wallpaper_id
                or k[5] != self._column_sig() or k[6] != lay.cx or k[7] != lay.cy
                or k[8] != lay.cw or k[9] != lay.ch or k[10] != _ITEMS.gen):
            k[0] = cv.w
            k[1] = cv.h
            k[2] = look.look_gen
            k[3] = look.effective_font_scale()
            k[4] = look.wallpaper_id
            k[5] = self._column_sig()
            k[6] = lay.cx
            k[7] = lay.cy
            k[8] = lay.cw
            k[9] = lay.ch
            k[10] = _ITEMS.gen
            # the WM's one count: a new layer never repeats an old one's
            self.wm._desk_count += 1
            self._sig_gen = self.wm._desk_count
        return self._sig_gen

    def _parts_again(self, col):
        """The parts of the desk that moved, painted again over the cached
        desk this frame's restore laid whole, and taken into the cache, which
        then holds the desk a live render would have left: with `col` the
        icon column (the backdrop under its rect put back,
        `Wallpaper.restorer`, and its page painted), and after a window
        opened, closed or moved the bar (its chips, and their marks over its
        edge, are the windows'). A column paint that showed a popover takes
        the whole root into the cache. This buffer is the first to hold the
        new cache."""
        wm = self.wm
        rc = wm.root_canvas
        cache = wm._backdrop
        cut = hasattr(cache, "blit_strip_rect")
        whole = not cut
        if col:
            wp = self.ws.wallpaper
            r = self._column_rect()
            wp.restorer(rc, wp.restore_key(False))(rc, r)
            self._fed_drawn = self._fed
            self._draw_desk_icons()
            whole = whole or self._popped
            if not whole:
                cache.blit_strip_rect(rc, 0, 0, r[0], r[1], r[2], r[3])
        if self._bar_owed:
            self._bar_owed = False
            bar = self.ws.bar_layer
            bar.draw_status_strip("desk")
            wm._desk_tile = bar.tile_on()
            if not whole:
                for b in wm.root_ctx.layout.bars:
                    r = b[1]
                    cache.blit_strip_rect(rc, 0, 0, r[0], r[1], r[2], r[3])
            self._bar_drawn(True)
        if whole:
            wm._capture_backdrop()
        wm._desk_streak = 1

    def owe_bar(self):
        """The cache's bar holds chips that moved since: the next restore
        that lays it draws the bar whole again and takes it in
        (`_parts_again`)."""
        self._bar_owed = True

    def _bar_drawn(self, cached):
        """The bar was drawn whole into this frame's buffer as it stands, and
        with `cached` into the cache too: the clock it shows need not paint
        again over it (`_desk_clock`)."""
        wm = self.wm
        laid = wm._bar_laid
        laid[0] = self.ws.frame_state.frames_drawn
        laid[1] = self.ws.bar_layer.clock_text()
        if cached:
            wm._cache_clock = laid[1]

    def _column_rect(self):
        """(x, y, w, h) the icon column paints in: its tiles and their
        labels, 8 pixels clear at the font scale for the focus mark and a
        press, within the desk. Kept while the column's rects stand."""
        rects = self._icon_rects()
        if self._col_at is rects:
            return self._col
        dx, dy, dw, dh = self.wm.desk_rect()
        pad = 8 * self.ws.look.effective_font_scale()
        x0, y0, x1, y1 = dx + dw, dy + dh, dx, dy
        for _key, box, band, _label, _cart in rects:
            x0 = min(x0, box[0], band[0])
            y0 = min(y0, box[1], band[1])
            x1 = max(x1, box[0] + box[2], band[0] + band[2])
            y1 = max(y1, box[1] + box[3], band[1] + band[3])
        x0, y0 = max(dx, x0 - pad), max(dy, y0 - pad)
        x1, y1 = min(dx + dw, x1 + pad), min(dy + dh, y1 + pad)
        self._col_at = rects
        self._col = (x0, y0, max(0, x1 - x0), max(0, y1 - y0))
        return self._col

    def _column_sig(self):
        """What the icon column takes from the apps and the roster: each
        tile's key, label and cart folder (`_icon_catalog`). Made again only
        when the roster or a title moves (`CartManager.gen`, `titled`) or
        the apps do, so a cart installed or removed that is no tile of the
        column leaves the desk's cache whole: a live desk is a full repaint."""
        ws = self.ws
        carts = ws.carts
        at = self._cat_at
        n = len(getattr(ws, "app_layers", ()))
        if at[0] != carts.gen or at[1] != carts.titled or at[2] != n:
            at[0] = carts.gen
            at[1] = carts.titled
            at[2] = n
            cat = self._catalog = self._icon_catalog()
            self._cat_sig = tuple((key, label, c.get("path") if c else None)
                                  for key, label, c in cat)
        return self._cat_sig

    def _draw_desktop(self, dt):
        self.ws.wallpaper.draw(dt, quiet=self.quiet())
        self._draw_desk_icons()
        self.ws.bar_layer.draw_status_strip("desk")

    def quiet(self):
        """The desk's quiet rectangles (docs/theme_and_shell_2026-11.md §3.9): the
        bars and the icon column, its tiles and labels as one rectangle per
        column. Made when the column or the bars move."""
        rects = self._icon_rects()
        bars = self.ws.wallpaper.bars()
        at = self._quiet_at
        if at[0] is rects and at[1] is bars:
            return self._quiet
        at[0] = rects
        at[1] = bars
        cols = {}
        for _key, box, band, _label, _cart in rects:
            x0 = min(box[0], band[0])
            y0 = min(box[1], band[1])
            x1 = max(box[0] + box[2], band[0] + band[2])
            y1 = max(box[1] + box[3], band[1] + band[3])
            c = cols.get(box[0])
            if c is not None:
                x0, y0 = min(x0, c[0]), min(y0, c[1])
                x1, y1 = max(x1, c[2]), max(y1, c[3])
            cols[box[0]] = (x0, y0, x1, y1)
        self._quiet = bars + tuple(
            (x0, y0, x1 - x0, y1 - y0) for x0, y0, x1, y1 in
            (cols[k] for k in sorted(cols)))
        return self._quiet

    # -- desk icons (#105: desktop mode's launch surface) ---------------------
    #
    # A static v1 column: PLAY (console mode, over the home), PROJECTS (the
    # home in a window, on Make), then the home's Apps tab: every registered
    # app (minus HIDDEN_APPS), then the installed app- and tool-typed carts no
    # app claims (Notes; a kid's installed app). The column is a page of the
    # engine's (`desk_ui.tiles`, `ui.cards(look="column")`), which lays it
    # out, draws it and takes its keys and taps; the icons render before the
    # drag backdrop capture, so the drag cache carries them for free.

    ICON_GLYPHS = {"play": "run", "projects": "edit"}

    @property
    def HIDDEN_APPS(self):
        """The WM's: reached through Settings, not a desk tool."""
        return self.wm.HIDDEN_APPS

    def _icon_catalog(self):
        """[(key, label, cart)]: the labels are the titles as their apps name
        them. A registered app's key is its id; an unclaimed app cart's is
        its icon set slot where its id's last part names one (Notes'
        `notes`) and no registered app has that id, else its whole id."""
        ws = self.ws
        out = [("play", "Play", None), ("projects", "Projects", None)]
        carts = ws.home.runs_here(ws.carts.all)
        apps = getattr(ws, "app_layers", ())
        for app in apps:
            if app.id in self.HIDDEN_APPS or not getattr(app, "DESK_TILE", True):
                continue
            cart = None
            for c in carts:
                if app.is_app(c):
                    cart = c
                    break
            if cart is None:
                # No cart in the store carries it (a C3 Zero's store holds a
                # handful): open_app could not open it, so it has no tile.
                continue
            out.append((app.id, str(ws.spine.app_title(app.id) or app.id.upper()), cart))
        for c in ws.home.unclaimed_apps(carts):
            cid = str(c.get("id") or c.get("title") or "")
            tail = cid.rsplit(".", 1)[-1]
            key = tail if tail in _iconsets.SLOT and ws.registered_app(tail) is None else cid
            out.append((key, str(c.get("title") or tail), c))
        return out

    def _icon_rects(self):
        """[(key, box_rect, label_rect, label, cart), ...] -- the engine's
        column of tiles (`desk_ui.tiles`, `ui.cards(look="column")`) as its
        geometry lays them out, laid out again when the column
        (`_column_sig`), the font scale or the desk's rect moves; callers
        read it and never change it."""
        ws = self.ws
        fs = ws.look.effective_font_scale()
        d = self.wm.desk_rect()
        sig = self._column_sig()
        at = self._rects_at
        if at[0] is sig and at[1] == fs and at[2] == d and self._rects is not None:
            return self._rects
        at[0] = sig
        at[1] = fs
        at[2] = d
        pg = self._tiles_page()
        self._tiles_put(ws)
        band = self._band
        for i in range(4):
            band[i] = d[i]
        g = self._g
        out = []
        if pg.cells_geom(band, fs, _layout_base.metric_class() == _layout_base.DESK, g):
            side, px, py, rows = g[_G_SIDE], g[_G_PX], g[_G_PY], max(1, g[_G_ROWS])
            line = _ui_draw.font("ui")[2] * fs
            i = 0
            for key, label, cart in self._catalog:
                x = g[_G_X0] + i // rows * px
                y = g[_G_Y0] + i % rows * py
                out.append((key, (x, y, side, side),
                            (x + side // 2 - px // 2, y + g[_G_TITLE_DY], px, line), label, cart))
                i += 1
        self._rects = out
        return out

    def _tiles_page(self):
        """The column's page (`desk_ui.tiles`) on its app host, made at its
        first use, its pictures the tiles' icons (`_tile_picture`)."""
        pg = self._page
        if pg is None:
            import uitree_app
            import desk_ui
            self._host = _ui_draw.AppHost()
            pg = uitree_app.hosted_page(desk_ui.tiles, self._host, _NoDamage())
            pg.bare = True
            pg.band = False
            pg.pictures = self._tile_picture
            pg.open()
            self._page = pg
        return pg

    def _tiles_put(self, ws):
        """The page's rows, its tiles' size and its labels' ink, written
        where what they are made from moved: the column, the look, the
        wallpaper and the font scale."""
        import desk_ui
        look = ws.look.live.look
        fs = ws.look.effective_font_scale()
        on = ws.look.wallpaper_id is not None
        sig = self._column_sig()
        at = self._put_at
        gen = ws.look.look_gen
        if at[0] is sig and at[1] is look and at[2] == on and at[3] == gen and at[4] == fs:
            return
        at[0] = sig
        at[1] = look
        at[2] = on
        at[3] = gen
        at[4] = fs
        desk_ui.PUT[0] = self._put_rows
        try:
            self._page.run(desk_ui.put, action="put")
        finally:
            desk_ui.PUT[0] = None
        desk_ui.ui.commit(self._page)

    def _put_rows(self, s):
        """The column page's rows (desk_ui's `put`): a tile an entry of the
        column, and the tiles' size and their labels' ink."""
        import desk_ui
        ws = self.ws
        look = ws.look.live.look
        fs = ws.look.effective_font_scale()
        tiles = dict(look[2]) if len(look) > 2 else {}
        rows = []
        ix = {}
        for key, label, cart in self._catalog:
            pic = desk_ui.ui.image.own(key)
            ix[repr(pic)] = (key, cart)
            v = _tile_fill(tiles, key)
            rows.append(dict(k=key, label=label, fill="" if v is None else _hex(v), pic=pic))
        s.tiles = rows
        s.tone = "#FFFFFF" if ws.look.wallpaper_id is not None else ""
        s.side = _layout_base.metric("tile", fs)
        s.pitch = _layout_base.metric("tile_cell", fs)
        self._pic_ix = ix

    def _tile_picture(self, node, pic, r):
        """A tile's icon (the engine's picture call, `r` its square -- 24 of
        the tile's 44 -- and its clip): its app's icon from the theme's set
        in the tiles' ink, else its cart's own art, else the desk's glyph."""
        if r is None:
            return True
        e = self._pic_ix.get(pic)
        cv = self._gcv
        if e is None or cv is None:
            return False
        key = e[0]
        cart = e[1]
        box = self._box
        box[0] = r[0]
        box[1] = r[1]
        box[2] = r[2]
        box[3] = r[3]
        cv.clip(r[4], r[5], r[6], r[7])
        tink = self._tink
        if not self.ws.draw_icon(key, box, tink, cv):
            img = self.ws.covers.icon_sheet_for(cart) if cart is not None else None
            if img is not None:
                sc = max(1, r[2] // 16)
                cv.spr(img, r[0] + (r[2] - 16 * sc) // 2, r[1] + (r[3] - 16 * sc) // 2, sc)
            else:
                _ch_ops.glyph(cv, self.ICON_GLYPHS.get(key, "app"), box, tink)
        cv.clip()
        return True

    def _draw_look_icons(self, ws, cv, th):
        """The column's page (`desk_ui.tiles`) painted on its app host, the
        keys its own while the desk holds them: each tile the look's part
        (`ui.bar_part`'s BAR_TILE) in its app's colour of the look's
        `tiles` where it names one, its app's icon (`_tile_picture`) in
        `tile_ink` (else the ink), its label in `label.ink` (else the ink)
        over `label.shadow` where the look sets one; over a wallpaper,
        white over a shadow. A tile opened opens its app after the frame."""
        import desk_ui
        look = ws.look.live.look
        at = self._style_at
        gen = ws.look.look_gen
        if at[0] is not look or at[1] is not th or at[2] != gen:
            at[0] = look
            at[1] = th
            at[2] = gen
            tink = look[0].get("tile_ink")
            self._tink = tink if _set(tink) else th.get("ink", 0)
        self._icon_rects()                  # (the page made)
        self._tiles_put(ws)
        pg = self._page
        host = self._host
        rect = self.wm.desk_rect()
        desk = _layout_base.metric_class() == _layout_base.DESK
        t = _ui_draw.UI_TARGET
        was = self._was
        was[0] = t[0]
        was[1] = t[1]
        was[2] = t[2]
        was[3] = t[3]
        try:
            host.whole()
            host.begin(cv, th, rect, desk, False, self.wm.focus_key is not None)
            self._gcv = cv
            desk_ui.OPEN[0] = self._open_fn
            pg.paint(0, cv, th, rect, desk)
            _ui_draw.page_end()
        finally:
            desk_ui.OPEN[0] = None
            self._gcv = None
            t[0] = was[0]
            t[1] = was[1]
            t[2] = was[2]
            t[3] = was[3]
        self._popped = host.popped(self._pop)
        if host.moving:
            self._fed += 1                  # (it moves on: the next frame draws it again)
            ws.request_frame()

    _was = [None, None, None, None]

    def _tile_open(self, key):
        """The page's tile `key` opened (Enter, a tap): its app opens after
        the frame that showed the tap."""
        for k, _label, cart in self._catalog:
            if k == key:
                self.ws.defer(lambda: self._open_icon(key, cart), toast=False)
                return

    def _draw_desk_icons(self):
        ws = self.ws
        self._draw_look_icons(ws, ws.sys_canvas, ws.theme_colors)

    def _open_icon(self, key, cart=None):
        """Open the tile `key` names: an unclaimed app cart's tile (`cart`
        set, no registered app's) runs its cart as the home's Apps tab does."""
        ws = self.ws
        if key == "play":
            ws.home.open_library()
        elif key == "projects":
            ws.home.open_projects()
        else:
            app = ws.app(key)
            if app is not None and (cart is None or app.is_app(cart)):
                ws.spine.open_app(app)
            elif cart is not None:
                ws.open(cart)

    def focused(self):
        """The key of the tile the keys are on as the last frame drew the
        column (uit_cells), None where the column does not hold the focus."""
        pg, cat, w = self._page, self._catalog, self._cells
        if pg is None or not cat or not pg.cells(w) or not w[24]:
            return None
        i = w[22]
        return cat[i][0] if 0 <= i < len(cat) else None

    def handle_input(self, i):
        """The desk's keys (no window holds them): the column page's, its
        tiles stepped and opened by its cards."""
        h = self._host
        if h is not None and h.keys(i):
            self._fed += 1
            self.ws.mark_dirty()
        return True

    def handle_pointer(self, px, py, click):
        if click and self.ws.bar_layer.bar_at("desk", px, py):
            self.ws.bar_layer.handle_bar_tap("desk", px, py)
            return True
        h = self._host
        if h is not None and h.point(px, py, click, self.ws.pointer.down):
            self._fed += 1
            self.ws.mark_dirty()
        return True
