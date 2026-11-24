# Map (grep -n a name to jump there):
#   MapLayout          the map editor's geometry: the handheld page's or a desk pane's
#   MapEditorUI        the Map page's host: the panned, zoomed view, its gestures and keys
#   MapEditorUI.build  build the MapEditor over the cart's map
"""The map (tilemap) editor's UI (issue #32): a panned, zoomed view of the
map where each cell shows the placed sprite tile, and the tap-to-paint /
drag-to-pan gestures over it (#37). The page round it is
`runtime/editors/editor_map.py`'s, on the handheld its brushes, tools and
foot; in a desk Editor's Map pane the view fills the pane above a status
line, the brush is the Sheet pane's and the tools the pane header's
(`runtime/editors/editor_desk.py`). `MapEditorUI` hosts the page
(`view_host.ViewHost`): the editor's state into the page's, the view and
the brushes drawn in its canvases with their presses and keys.

One instance lives on Workstation (`ws.map_ui`), with a back-reference to it
for the cart's shared resources (the sheet and the tilemap, which a run
copies at its start). `NAMES` is injected at construction instead of
imported back from console.py, which would be a circular import.
"""

from array import array

import ui_font as _ui_font
from widgets import rect_in as _in   # one hit-test

import editor_map
from editors_paint_map import MapEditor
from view_host import ViewHost, ViewLayout, BRUSH_PAD

# TIC-80-style zoom: a small ascending list of DETAIL CELL SIZES in px. Every rung
# is a multiple of the 8px tile, so a tile UPSCALES to fill its cell exactly (scale
# = cell // 8) -- crisp pixel art, never a floating 8px tile in a bigger box. 8px is
# the floor of this list because `spr` cannot downscale: below it a tile spills over
# its neighbours.
#
# The cell size is the MAP FIELD SIZE and zoom is what changes it. It deliberately
# does NOT adapt to the map or to the screen: a wider view then shows MORE OF THE
# LEVEL at the same field size, which is what the extra pixels are for.
#
# It used to compute a cell that fit a fixed 20x15 target instead, and that inverted
# on the desktop tier -- the P4's 1024x600 picked a 29px cell and showed 26x15, FEWER
# rows than the 320x240 T-Deck on eight times the pixels, because the extra space went
# into bigger cells rather than more map.
_MV_ZOOMS = [8, 16, 24, 32]
# The OVERVIEW rung (#215), appended to `layout.zooms` AFTER the detail sizes: the
# sentinel is not a cell size but "compute the largest cell that shows the most map",
# resolved by _mv_fit_cell against the live map + view. It is the only rung that draws
# a cell as a solid block of its tile's dominant colour instead of the tile -- a
# minimap. The detail rungs are untouched, and the rung the editor OPENS on is still
# zooms[0], the 8px field size: overview is where you find yourself in a level, not
# where you paint it, and a tap on a 2px cell is not an edit gesture. Cycling reaches
# it in one wrap.
#
# The cell lives BETWEEN the two constants. _MV_FIT_MAX is one below the tile, so the
# rung is ALWAYS sub-8 and always draws blocks -- a map small enough to fit at 12px
# still gets the block view rather than a fifth, near-identical tile rung. _MV_FIT_MIN
# is the READABILITY floor (owner call on T-Deck glass, 2026-09-06): Sky Run's 100
# columns fit the 192px view only at 1px per cell, and a 1px minimap is not a picture
# of a level. Below the floor the rung stops shrinking and PANS like every other rung
# -- same camera, same clamp, and the cursor/tap/trackball paths already work at
# sub-8px cells. Seeing most of a level at 4px beats seeing all of it at 1px.
#
# This is a FIT TARGET, not a survey of shipped maps. The constants it replaced
# (_MV_FIT_COLS = 20 "widest shipped map") were read as a survey and went stale the
# day a wider map shipped; nothing here needs updating when one does, because the
# target is the whole map, whatever its size.
_MV_OVERVIEW = 0
_MV_FIT_MAX = 7
_MV_FIT_MIN = 4
# The OVERVIEW rung's name in a pane's status line ("zoom OV").
_MV_OV_LABEL = "OV"
# Map resize (#91): the largest grid Resize grows to. 96x96 = 9216
# cells (~9KB) is a generous kid level and still device-RAM-safe; shrink floors at
# 1x1 (TileMap.resize clamps too).
_MAP_MAX_DIM = 96
_MAP_MIN_DIM = 1
# The page's tools (editor_map.TOOLS) as the editor's (tool, erasing), and
# back.
_TOOL_OF = dict(pen=("stamp", False), box=("rect", False), fill=("flood", False),
                select=("select", False), erase=("stamp", True))
_TOOL_ID = {"stamp": "pen", "rect": "box", "flood": "fill", "select": "select"}
# Resize's steps: (wider, taller).
_RESIZE = {"wider": (1, 0), "narrower": (-1, 0), "taller": (0, 1), "shorter": (0, -1)}


def _mv_fit_cell(avail_w, avail_h, mw, mh):
    """The largest whole-pixel cell at which an mw x mh map fits an avail_w x
    avail_h view, capped at _MV_FIT_MAX and floored at _MV_FIT_MIN (#215). A map
    that needs a smaller cell than the floor does not fit whole: it draws at the
    floor and PANS, exactly as the detail rungs do."""
    if mw < 1 or mh < 1:
        return _MV_FIT_MAX
    cell = avail_w // mw
    ch = avail_h // mh
    if ch < cell:
        cell = ch
    if cell > _MV_FIT_MAX:
        return _MV_FIT_MAX
    return cell if cell > _MV_FIT_MIN else _MV_FIT_MIN


class MapLayout(ViewLayout):
    """The map editor's geometry (`view_host.ViewLayout`), its desk pane's
    view over a status line. The zoom list is the detail sizes, then the
    OVERVIEW sentinel LAST on every tier, so the rung a reader is on is a
    name, not an index."""

    ZOOMS = tuple(_MV_ZOOMS) + (48, 64, _MV_OVERVIEW)
    STATUS = True


class MapEditorUI(ViewHost):
    """The map/tilemap editor's UI: the Map page's host (editor_map.py) --
    the pan/zoom view and the brushes its canvases, their gestures and keys,
    and the page's actions over the MapEditor. One instance lives on
    Workstation (`self.map_ui`), built once in Workstation.__init__;
    `ws.map_ui.build()` is called lazily from `set_menu_view("map")` the
    first time a cart's map editor is opened."""

    def __init__(self, ws, names):
        ViewHost.__init__(self, ws, names, "map", editor_map.map_page, MapLayout)
        self.mapedit = None            # MapEditor while menu_view == "map" (#32)
        self.map_erase = False         # tap-to-erase instead of stamp
        self.map_zoom = 0              # zoom level index into layout.zooms (0 = fit)
        self.map_tool = "stamp"        # active paint tool (#91): stamp/rect/flood/select
        self._map_rect = None          # (x0,y0,x1,y1) cell corners while a RECT drags
        self._map_sel = None           # (x0,y0,x1,y1) live SELECT marquee drag box (#91)
        self._map_paint_undo = None    # ([(cx,cy,prev_byte),...],dirty,gen) for the
                                       # block painted on press (#57: the SIZE brush
                                       # stamps s x s cells); reverted if the gesture
                                       # turns out to be a pan
        self._ov_buf = None            # the OVERVIEW rung's reused quad buffer (#215)
        self._pop = False              # the resize popover is open
        self._hover_cell = None        # the cell last pressed
        self._hold = 0                 # frames a still press has been held

    # -- the page ------------------------------------------------------------

    def _sync(self):
        """The editor's state the page shows, handed to its `sync` hook
        where it moved."""
        me = self.mapedit
        lay = self.layout
        tm = self.ws.run.project.tilemap
        u = lay.unit
        first, last, words = self.pager()
        pad = BRUSH_PAD * u
        if me is None or tm is None or self.ws.run.project.sheet is None:
            vals = (True, lay.pane, "pen", "none", False, False, first, last, words, "", "", "", "",
                    "", "", lay.view_w, lay.brushes_h, lay.lines, lay.pitch, pad, 160 * u)
        else:
            tool = _TOOL_ID.get(self.map_tool, "pen")
            if tool == "pen" and self.map_erase:
                tool = "erase"
            cell = self._hover_cell
            x = "\u00d7" if _ui_font.print_symbols() else "x"
            dims = "%d%s%d" % (tm.w, x, tm.h)
            status = ""
            if lay.pane:
                parts = []
                if cell is not None:
                    parts.append("Cell %d, %d" % cell)
                parts.append("tile %d" % me.n if me.n >= 0 else "sky")
                parts.append(dims)
                parts.append("zoom " + self._mv_zoom_label())
                parts.append("hold a cell to pick its tile")
                status = " \u00b7 ".join(parts)
            vals = (False, lay.pane, tool, "resize" if self._pop else "none", me.sel is not None,
                    bool(me.has_clip), first, last, words,
                    "Tile %d" % me.n if me.n >= 0 else "Sky",
                    "Cell %d, %d" % cell if cell is not None else "Tap to paint",
                    "%d%s%d" % (me.size, x, me.size), self.zoom_word(), dims, status,
                    lay.view_w, lay.brushes_h, lay.lines, lay.pitch, pad, 160 * u)
        self.push(vals)

    def zoom_word(self):
        """The zoom button's word: the tile's scale, or Fit for the overview."""
        if self._mv_overview():
            return "Fit"
        x = "\u00d7" if _ui_font.print_symbols() else "x"
        return "%d%s" % (max(1, self._mv_metrics()[2] // 8), x)

    def act(self, verb):
        """One of the page's actions: a tool, Copy, Cut or Paste, the
        brushes' page before or after, the brush's size, the zoom, Resize
        and its four steps, or the popover closed."""
        me = self.mapedit
        if me is None:
            return
        if verb in _TOOL_OF:
            self.map_tool, self.map_erase = _TOOL_OF[verb]
            self._map_rect = None
            self._map_sel = None
            self._due = "home"          # the keys go back to the view, which the tool paints
        elif verb == "copy":
            me.copy_selection()
        elif verb == "cut":
            me.cut_selection()
        elif verb == "paste":
            self._sel_paste_default(me)
        elif verb == "bprev":
            self.page_step(-1)
        elif verb == "bnext":
            self.page_step(1)
        elif verb == "size":
            me.cycle_size()
        elif verb == "zoom":
            self.cycle_zoom()
        elif verb == "resize":
            self._pop = not self._pop
            if self._pop:
                self._due = "popped"    # its first step takes the keys at the next draw
        elif verb in _RESIZE:
            self._map_resize(*_RESIZE[verb])
        elif verb == "close":
            self._pop = False
        self.ws.mark_dirty()

    def popover(self):
        return self._pop

    def close_pop(self):
        self.act("close")

    # -- the view's keys and gestures --------------------------------------------

    def ready(self):
        return self.mapedit is not None

    def brush(self):
        return self.mapedit.n

    def set_brush(self, t):
        """The brush, the pen with it."""
        self.mapedit.n = t
        self.map_erase = False

    def view_top(self):
        return self.mapedit is not None and self.mapedit.cam_y <= 0

    def arrows(self, dx, dy):
        """The view's arrows pan the map; whether the camera followed."""
        me = self.mapedit
        was = (me.cam_x, me.cam_y)
        self.pan(dx, dy)
        return (me.cam_x, me.cam_y) != was

    def press(self, px, py):
        self._hold = 0
        self._map_click(px, py)

    def drag(self, px, py):
        self._map_pan_drag(px, py)
        self._held_pick(px, py)

    def release(self, px, py):
        self._map_release(px, py)

    # A press held still this many frames picks the tile under it.
    HOLD_FRAMES = 15

    def _held_pick(self, px, py):
        """A press held still in the view: its cell's tile becomes the
        brush and the press's stamp is taken back. Whether it picked."""
        me = self.mapedit
        if (me is None or self._panning or self.map_tool != "stamp"
                or self._hold < 0):
            return False
        self._hold += 1
        if self._hold < self.HOLD_FRAMES:
            return False
        self._hold = -1
        cell = self._map_cell_at(*self._press)
        tm = self.ws.run.project.tilemap
        if cell is None or tm is None:
            return False
        self._map_revert_paint()
        me.abort_edit()
        me.n = tm.mget(cell[0], cell[1])
        self.map_erase = False
        self._press = None
        return True

    def build(self):
        """Build the MapEditor over the cart's TileMap + sheet (both always exist
        after Workstation.open()). Edits go into the Editor's tilemap, which a
        run copies at its start and at Play (`ProjectStore.play_world`, E-02). Called from
        Text.set_menu_view("map")."""
        ws = self.ws
        if self.mapedit is None and ws.run.project.tilemap is not None and ws.run.project.sheet is not None:
            self.mapedit = MapEditor(ws.run.project.tilemap, ws.run.project.sheet)

    def reset(self):
        """Drop the active editor (a stale one must never leak into an unrelated
        cart or back to the launcher). Called from Workstation.open() (switching
        carts) and Home.go_home()."""
        self.mapedit = None

    def on_open(self):
        """Reset gesture/zoom state (#37) -- called from Text._open_map,
        before set_menu_view("map") (re)builds the editor."""
        self.map_erase = False
        self.map_zoom = 0              # the 8px field-size rung (#37 follow-up)
        self._press = None             # fresh gesture state on open (#37)
        self._panning = False
        self._drag = None
        self._map_paint_undo = None
        self.map_tool = "stamp"        # (#91) back to the plain per-cell brush
        self._map_rect = None
        self._map_sel = None

    def _mv_metrics(self):
        """The LIVE map-view metrics for the current zoom level (#37 follow-up):
        (x0, y0, cell, cols, rows). `cell` is the px per cell at the current zoom;
        `cols`/`rows` are how many whole cells fit the available rectangle. All map
        hit-testing, panning and drawing route through this so they share one cell
        size; the rectangle + zoom list come from the responsive MapLayout (#39).

        The OVERVIEW rung's entry is a sentinel, not a size: its cell is fitted to
        the live map here (#215), so a resize re-fits it with no state to keep."""
        lay = self.layout
        idx = self.map_zoom
        if idx < 0:
            idx = 0
        elif idx >= len(lay.zooms):
            idx = len(lay.zooms) - 1
        cell = lay.zooms[idx]
        if cell == _MV_OVERVIEW:
            cell = self._mv_overview_cell()
        r = self._view_r
        if r is None:
            r = (lay.view_x0, lay.view_y0, lay.view_w, lay.view_h)
        return (r[0], r[1], cell, r[2] // cell, r[3] // cell)

    def _mv_overview_cell(self):
        """The OVERVIEW rung's cell size for the map that is open."""
        lay = self.layout
        tm = self.ws.run.project.tilemap
        if tm is None:
            return _MV_FIT_MAX
        r = self._view_r
        if r is None:
            return _mv_fit_cell(lay.view_w, lay.view_h, tm.w, tm.h)
        return _mv_fit_cell(r[2], r[3], tm.w, tm.h)

    def _mv_overview(self):
        """True while the view is on the OVERVIEW rung -- the cell is below one
        tile, so cells draw as dominant-colour blocks instead of sprites."""
        lay = self.layout
        idx = self.map_zoom
        return 0 <= idx < len(lay.zooms) and lay.zooms[idx] == _MV_OVERVIEW

    def _mv_zoom_label(self):
        """The rung's badge: its ordinal for a detail size, _MV_OV_LABEL for the
        OVERVIEW rung, which has no fixed cell size to number."""
        return _MV_OV_LABEL if self._mv_overview() else str(self.map_zoom + 1)

    def _mv_area(self):
        """The current map-view rectangle (x, y, w, h) for _in() hit-tests."""
        x0, y0, cell, cols, rows = self._mv_metrics()
        return (x0, y0, cols * cell, rows * cell)

    def clamp_cam(self):
        """Clamp the camera so you can't scroll far past the map edges at the
        current zoom: the top-left visible cell stays in [0, max(0, dim - visible)],
        so a map smaller than the view always pins to (0, 0) (no panning needed)."""
        me = self.mapedit
        tm = self.ws.run.project.tilemap
        if me is None or tm is None:
            return
        x0, y0, cell, cols, rows = self._mv_metrics()
        me.cam_x = max(0, min(max(0, tm.w - cols), me.cam_x))
        me.cam_y = max(0, min(max(0, tm.h - rows), me.cam_y))

    def cycle_zoom(self):
        """Cycle to the next zoom rung -- the detail sizes in order, then OVERVIEW,
        then back to the 8px field size -- and re-clamp the camera so a zoom-out
        can't leave it scrolled off-map."""
        self.map_zoom = (self.map_zoom + 1) % len(self.layout.zooms)
        self.clamp_cam()

    def pan(self, dcx, dcy):
        """Pan the camera by (dcx, dcy) cells then clamp to the map edges at the
        current zoom (the editor's clamp, which knows the visible cols/rows -- the
        MapEditor.pan clamp is zoom-agnostic so we re-clamp here)."""
        me = self.mapedit
        if me is None:
            return
        me.cam_x = me.cam_x + dcx
        me.cam_y = me.cam_y + dcy
        self.clamp_cam()

    def wheel_zoom(self, px, py, d):
        """A wheel notch at (px, py): the next zoom in (`d` < 0, a notch up)
        or out, a whole step, the cell under the pointer kept under it. The
        overview is the press's and the A button's, never the wheel's."""
        me = self.mapedit
        lay = self.layout
        if me is None:
            return
        last = len(lay.zooms) - 1
        if lay.zooms[last] == _MV_OVERVIEW:
            last -= 1
        z = max(0, min(last, self.map_zoom - d))
        if z == self.map_zoom:
            return
        x0, y0, cell, _c, _r = self._mv_metrics()
        cx = me.cam_x + (px - x0) // cell
        cy = me.cam_y + (py - y0) // cell
        self.map_zoom = z
        x0, y0, cell, _c, _r = self._mv_metrics()
        me.cam_x = cx - (px - x0) // cell
        me.cam_y = cy - (py - y0) // cell
        self.clamp_cam()

    def step(self):
        """View pixels a map cell."""
        return self._mv_metrics()[2]

    def _map_cell_at(self, px, py):
        """The map cell (cx, cy) under pointer (px, py) accounting for the pan
        offset, or None when the pointer is outside the visible map view."""
        me = self.mapedit
        if me is None or not _in(px, py, self._mv_area()):
            return None
        x0, y0, cell, cols, rows = self._mv_metrics()
        cx = me.cam_x + (px - x0) // cell
        cy = me.cam_y + (py - y0) // cell
        return (cx, cy)

    def _map_cell_at_clamped(self, px, py):
        """Like _map_cell_at but never None: the pointer is snapped to the nearest
        visible cell then clamped to the map bounds (#91). Used by the RECT drag so
        a rubber-band that leaves the view still tracks a valid opposite corner."""
        me = self.mapedit
        tm = self.ws.run.project.tilemap
        if me is None or tm is None:
            return None
        x0, y0, cell, cols, rows = self._mv_metrics()
        rx = (px - x0) // cell
        ry = (py - y0) // cell
        if rx < 0:
            rx = 0
        elif rx > cols - 1:
            rx = cols - 1
        if ry < 0:
            ry = 0
        elif ry > rows - 1:
            ry = rows - 1
        cx = me.cam_x + rx
        cy = me.cam_y + ry
        if cx > tm.w - 1:
            cx = tm.w - 1
        if cy > tm.h - 1:
            cy = tm.h - 1
        return (cx, cy)

    # -- map resize panel (#91) ------------------------------------------------

    def _map_resize(self, dw, dh):
        """Grow/shrink the map by (dw, dh) cells on the right/bottom edge (#91),
        clamped to [_MAP_MIN_DIM, _MAP_MAX_DIM]; content is preserved (top-left
        anchored). A structural change, so it drops the in-editor undo history and
        re-clamps the camera to the new bounds."""
        tm = self.ws.run.project.tilemap
        me = self.mapedit
        if tm is None:
            return
        new_w = tm.w + dw
        new_h = tm.h + dh
        if new_w < _MAP_MIN_DIM:
            new_w = _MAP_MIN_DIM
        elif new_w > _MAP_MAX_DIM:
            new_w = _MAP_MAX_DIM
        if new_h < _MAP_MIN_DIM:
            new_h = _MAP_MIN_DIM
        elif new_h > _MAP_MAX_DIM:
            new_h = _MAP_MAX_DIM
        if new_w == tm.w and new_h == tm.h:
            return
        tm.resize(new_w, new_h)
        if me is not None:
            me.clear_history()
        self._map_rect = None
        self.clamp_cam()

    # -- SELECT-mode region actions (#91) --------------------------------------

    def _sel_paste_default(self, me):
        """The PASTE button stamps the clip at the active selection's top-left (so
        copy->paste lands in place), or at the top-left visible cell with no selection.
        In SELECT mode a tap on the map pastes at the tapped cell instead (#91)."""
        if not me.has_clip:
            return
        if me.sel is not None:
            me.paste(me.sel[0], me.sel[1])
        else:
            me.paste(me.cam_x, me.cam_y)

    def _map_paint(self, cx, cy):
        """Stamp the brush at map cell (cx, cy): the EMPTY brush (#37) clears the
        cell (paints sky/background), otherwise the brush's tile is placed. The
        ERASE toggle still forces a clear regardless of the brush. With SIZE > 1
        (#57) both stamp and erase cover the brush's whole cell block."""
        me = self.mapedit
        if me is None:
            return
        if self.map_erase or me.n < 0:
            me.erase(cx, cy)
        else:
            me.place(cx, cy)

    def _map_stamp_cells(self, cx, cy):
        """Every in-map cell the press-edge paint at (cx, cy) will touch, with its
        prior byte: [(cx, cy, prev), ...] -- the snapshot _map_revert_paint puts
        back when the gesture turns out to be a pan. Size 1 is one cell, the SIZE
        brush (#57) an s x s block (erase always the full square, a stamp the
        sheet-clamped stamp_span)."""
        me = self.mapedit
        tm = self.ws.run.project.tilemap
        if self.map_erase or me.n < 0:
            tw = th = me.size
        else:
            tw, th = me.stamp_span()
        cells = []
        for dy in range(th):
            for dx in range(tw):
                x = cx + dx
                y = cy + dy
                if 0 <= x < tm.w and 0 <= y < tm.h:
                    cells.append((x, y, tm.cells[y * tm.w + x]))
        return cells

    def _map_pan_drag(self, px, py):
        """Held-drag handler for the map view (#37): once a drag that began inside
        the map view moves past _MAP_PAN_THRESH px it latches PAN mode for the rest
        of the gesture and scrolls the camera by the drag delta (in cells), so the
        content follows the finger. A drag is a pan, not a paint -- so when it
        latches it REVERTS the cell stamped on the press edge (the tap-paint), which
        means a tap paints and a drag pans without a stray stamp at the origin."""
        press = self._press
        if press is None:
            return
        if self.map_tool == "rect":
            # RECT rubber-band (#91): track the opposite corner; no panning while a
            # box is being drawn (the d-pad/arrows still pan). Drawn as a preview.
            cell = self._map_cell_at_clamped(px, py)
            if cell is not None and self._map_rect is not None:
                x0, y0, _, _ = self._map_rect
                self._map_rect = (x0, y0, cell[0], cell[1])
            return
        if self.map_tool == "select":
            # SELECT marquee (#91): rubber-band the selection box like RECT; no pan
            # while dragging (the d-pad still pans). Committed on release.
            cell = self._map_cell_at_clamped(px, py)
            if cell is not None and self._map_sel is not None:
                x0, y0, _, _ = self._map_sel
                self._map_sel = (x0, y0, cell[0], cell[1])
            return
        if self.map_tool == "flood":
            return                             # flood already applied on the press
        if self.pan_drag(px, py, self._mv_metrics()[2]):
            # crossed the dead zone: it pans, so the press-edge stamp is taken back
            self._map_revert_paint()
            if self.mapedit is not None:       # and its open edit batch discarded (#91): the
                self.mapedit.abort_edit()      # cells are reverted, so it must not commit

    def _map_revert_paint(self):
        """Undo the block stamped on the press edge (used when a press turns into a
        pan): restore every touched cell's previous byte AND the map's dirty/gen
        counters so a pure pan is side-effect-free (no false '*' dirty flag, no
        spurious cache rebuild in a running cart). The snapshot's cells were
        validated in-map when _map_stamp_cells built it."""
        u = self._map_paint_undo
        tm = self.ws.run.project.tilemap
        if u is not None and tm is not None:
            cells, dirty, gen = u
            for cx, cy, prev in cells:
                tm.cells[cy * tm.w + cx] = prev
            tm.dirty = dirty
            tm.gen = gen
        self._map_paint_undo = None

    def _map_release(self, px, py):
        """Pointer up in the map view: the STAMP tap-paint already landed on the press
        edge (a pan would have reverted it), so it just closes the edit batch; the
        RECT tool fills its rubber-banded rectangle here as ONE undo step (#37/#91);
        the SELECT tool commits its marquee (a drag sets the selection, a tap either
        pastes the clip there or clears the selection -- mirroring the paint editor)."""
        me = self.mapedit
        if me is not None:
            if self.map_tool == "rect" and self._press is not None \
                    and self._map_rect is not None:
                x0, y0, x1, y1 = self._map_rect
                me.begin_edit()
                me.fill_rect(x0, y0, x1, y1, erase=self.map_erase)
                me.end_edit()
            elif self.map_tool == "select" and self._press is not None \
                    and self._map_sel is not None:
                x0, y0, x1, y1 = self._map_sel
                if x0 == x1 and y0 == y1:      # a tap (no marquee) -> paste or deselect
                    if me.has_clip:
                        me.paste(x0, y0)       # tap-to-stamp: drop the clip here (#91)
                    else:
                        me.clear_selection()   # tap on empty space clears the selection
                else:
                    me.set_selection(x0, y0, x1, y1)
            else:
                # STAMP: commit the press-edge stamp's batch (a no-op for flood, whose
                # batch already ended, or a pan, whose batch was aborted).
                me.end_edit()
        self._map_paint_undo = None
        self._map_rect = None
        self._map_sel = None

    def _map_click(self, px, py):
        got = self._map_cell_at(px, py)
        if got is not None:
            self._hover_cell = got
        ws = self.ws
        me = self.mapedit
        if me is None:
            return
        if _in(px, py, self._mv_area()):  # a press in the map view: start a
            tm = ws.run.project.tilemap
            if tm is None:
                return
            tool = self.map_tool
            if tool == "rect":
                # RECT (#91): remember the start corner; the drag rubber-bands the
                # rectangle, release fills it. No paint yet, no pan (the d-pad pans).
                cell = self._map_cell_at_clamped(px, py)
                self._map_rect = (cell[0], cell[1], cell[0], cell[1]) if cell else None
            elif tool == "flood":
                # FLOOD (#91): a single tap fills the contiguous region right away --
                # one committed undo step. No drag/pan follow-up.
                cell = self._map_cell_at(px, py)
                if cell is not None and 0 <= cell[0] < tm.w and 0 <= cell[1] < tm.h:
                    me.begin_edit()
                    me.flood(cell[0], cell[1], erase=self.map_erase)
                    me.end_edit()
            elif tool == "select":
                # SELECT (#91): remember the marquee start corner; the drag rubber-bands
                # the box, release commits it (a drag sets the selection, a tap pastes
                # the clip / clears). No paint, no pan (the d-pad still pans).
                cell = self._map_cell_at_clamped(px, py)
                self._map_sel = (cell[0], cell[1], cell[0], cell[1]) if cell else None
            else:
                # STAMP (#37/#57): paint immediately so a tap is responsive; remember
                # the block + its prior bytes so a drag-that-becomes-a-pan reverts it.
                cell = self._map_cell_at(px, py)
                if cell is not None:
                    cx, cy = cell
                    if 0 <= cx < tm.w and 0 <= cy < tm.h:
                        me.begin_edit()
                        self._map_paint_undo = (self._map_stamp_cells(cx, cy),
                                                tm.dirty, tm.gen)
                        self._map_paint(cx, cy)

    # -- drawing -----------------------------------------------------------------

    def draw_view(self, cv, x, y, w, h):
        """The view, the page's canvas at (x, y, w, h): the window of the map
        at the zoom, its lattice, and the RECT and SELECT overlays."""
        self.view_at(x, y, w, h)
        ws = self.ws
        NAMES = self._NAMES
        me = self.mapedit
        sheet = ws.run.project.sheet
        tm = ws.run.project.tilemap
        if me is None or sheet is None or tm is None:
            return
        x0, y0, cell, cols, rows = self._mv_metrics()
        # Visible map region: each cell is the sprite tile placed there, UPSCALED to
        # fill the cell (scale = cell // TILE, crisp pixel-art) and centered, with grid
        # lines so empty cells read as empty. Tile images are cached by id within the
        # draw so a repeated tile builds once.
        #
        # On the OVERVIEW rung (#215) the cell is below one tile, so a cell is a solid
        # block of its tile's dominant colour instead, and the lattice is SKIPPED: at
        # 2-4px a 1px grid line on every side is most of the cell, and at 1px it is the
        # whole of it -- the minimap would be a field of grey.
        overview = self._mv_overview()
        # #163 span-batch: the per-cell rect+rectb pair (2 gated calls x every
        # visible cell, the tab's dominant dispatch cost) becomes THREE merged
        # groups, pixel-identical by construction:
        #   1. backgrounds -- cells are disjoint, so the in-bounds block is ONE
        #      dark_blue rect and the out-of-bounds remainder two black strips
        #      (rects, not quads: a big one is a DMA fill where the canvas has one);
        #   2. (the tiles between them are ONE map() -- see below);
        #   3. the grid lattice, one fill_rects a cell-row -- each cell's
        #      rectb edges merged into full-length
        #      1px lines (interior edges stay DOUBLED at k*cell and k*cell-1,
        #      exactly the pixels the per-cell outlines painted; overlaps at
        #      corners are same-color idempotent).
        # Lattice draws after sprites, like the per-cell order did.
        nx = min(cols, tm.w - me.cam_x)
        ny = min(rows, tm.h - me.cam_y)
        if nx < 0:
            nx = 0
        if ny < 0:
            ny = 0
        # The packed geometry is a pure function of this key, so it is memoised:
        # a paint gesture re-hits it every frame (camera fixed), a pan/zoom/
        # relayout re-keys and rebuilds: one band of the lattice, drawn down
        # the rows by fill_rects' offset, so a rebuild is one row's quads. The
        # lattice is drawn band-by-band (per cell-row: 2 wide lines + the
        # 2·cols short verticals of that band) --
        # full-height vertical lines drawn last measured +16ms on glass: 1px
        # column-major writes fetch one cache line per row, ~3.4MB of traffic,
        # where a band's writes stay inside an L2-resident ~122KB window.
        memo = getattr(self, "_grid_memo", None)
        key = (x0, y0, cols, rows, cell, nx, ny)
        if memo is None or memo[0] != key:
            blue = NAMES["dark_blue"]
            black = NAMES["black"]
            grey = NAMES["dark_grey"]
            bg = []
            if nx and ny:
                bg.append((x0, y0, nx * cell, ny * cell, blue))
            if nx < cols:
                bg.append((x0 + nx * cell, y0, (cols - nx) * cell, rows * cell, black))
            if ny < rows and nx:
                bg.append((x0, y0 + ny * cell, nx * cell, (rows - ny) * cell, black))
            lat = ()
            if not overview:
                gw = cols * cell
                band = [x0, y0, gw, 1, grey, x0, y0 + cell - 1, gw, 1, grey]
                for j in range(cols):
                    band += (x0 + j * cell, y0, 1, cell, grey,
                             x0 + (j + 1) * cell - 1, y0, 1, cell, grey)
                lat = array("h", band)
            memo = (key, tuple(bg), lat)
            self._grid_memo = memo
        for q in memo[1]:                  # rects: a big one is a DMA fill on a P4
            cv.rect(q[0], q[1], q[2], q[3], q[4])
        if overview:
            self._draw_map_blocks(cv, tm, sheet, me, x0, y0, cell, nx, ny)
        else:
            # The visible window IS a map() region -- every detail rung's cell is a
            # whole multiple of the tile (tests/test_map_tile_blit.py pins the
            # ladder), so the cells sit on exactly the lattice blit_map walks. One
            # native call for the window replaces an Image blit per cell, and it is
            # the SAME kernel the cart's own map() runs, so a tile in the editor is
            # the tile the cart draws.
            cv.map(tm, sheet, me.cam_x, me.cam_y, nx, ny, x0, y0, -1,
                   cell // sheet.TILE)
            lat = memo[2]
            for k in range(rows):
                cv.fill_rects(lat, -1, 0, k * cell)
        # RECT preview (#91): while a box is being dragged, outline the covered cells
        # (clamped to the visible window) so the fill region is visible before release.
        if self.map_tool == "rect" and self._map_rect is not None \
                and self._press is not None:
            rx0, ry0, rx1, ry1 = self._map_rect
            if rx1 < rx0:
                rx0, rx1 = rx1, rx0
            if ry1 < ry0:
                ry0, ry1 = ry1, ry0
            ix0 = rx0 if rx0 > me.cam_x else me.cam_x
            iy0 = ry0 if ry0 > me.cam_y else me.cam_y
            vx1 = me.cam_x + cols - 1
            vy1 = me.cam_y + rows - 1
            ix1 = rx1 if rx1 < vx1 else vx1
            iy1 = ry1 if ry1 < vy1 else vy1
            if ix0 <= ix1 and iy0 <= iy1:
                rpx = x0 + (ix0 - me.cam_x) * cell
                rpy = y0 + (iy0 - me.cam_y) * cell
                rpw = (ix1 - ix0 + 1) * cell
                rph = (iy1 - iy0 + 1) * cell
                cv.rectb(rpx, rpy, rpw, rph, NAMES["yellow"])
                if rpw > 2 and rph > 2:
                    cv.rectb(rpx + 1, rpy + 1, rpw - 2, rph - 2, NAMES["yellow"])
        # SELECT overlay (#91): the committed selection is a solid white box, a live
        # marquee drag a yellow box (like the RECT preview). Both clamp to the visible
        # window. Drawn only in select mode.
        if self.map_tool == "select":
            if me.sel is not None:
                self._draw_map_box(cv, x0, y0, cell, cols, rows, me.cam_x, me.cam_y,
                                   me.sel[0], me.sel[1], me.sel[2], me.sel[3],
                                   NAMES["white"], False)
            if self._map_sel is not None and self._press is not None:
                self._draw_map_box(cv, x0, y0, cell, cols, rows, me.cam_x, me.cam_y,
                                   self._map_sel[0], self._map_sel[1],
                                   self._map_sel[2], self._map_sel[3],
                                   NAMES["yellow"], True)

    def _draw_map_blocks(self, cv, tm, sheet, me, x0, y0, cell, nx, ny):
        """The OVERVIEW rung's minimap (#215): every placed cell as a solid block of
        its tile's dominant colour, equal-colour neighbours merged into one quad per
        RUN along a row, one fill_rects batch per row. An empty cell emits nothing, so
        the map field's own blue reads as sky exactly like it does at 8px.

        The quad buffer is sized to the VISIBLE COLUMNS and reused across rows and
        frames. A whole-map array would be up to 9216 quads on a 96x96 map (the resize
        ceiling) -- ~90KB on a board, to draw a picture 96px wide."""
        if nx < 1 or ny < 1:
            return
        need = nx * 5
        buf = self._ov_buf
        if buf is None or len(buf) < need:
            buf = array("h", (0,) * need)
            self._ov_buf = buf
        cells = tm.cells
        w = tm.w
        tile_color = sheet.tile_color
        tint = {}
        for ry in range(ny):
            base = (me.cam_y + ry) * w + me.cam_x
            y = y0 + ry * cell
            n = 0
            run_c = -1
            run_x = 0
            run_n = 0
            for rx in range(nx):
                v = cells[base + rx]
                if v:
                    c = tint.get(v, -2)
                    if c == -2:
                        c = tile_color(v - 1)
                        tint[v] = c
                else:
                    c = -1
                if c == run_c:
                    run_n += 1
                    continue
                if run_c >= 0:
                    buf[n] = x0 + run_x * cell
                    buf[n + 1] = y
                    buf[n + 2] = run_n * cell
                    buf[n + 3] = cell
                    buf[n + 4] = run_c
                    n += 5
                run_c = c
                run_x = rx
                run_n = 1
            if run_c >= 0:
                buf[n] = x0 + run_x * cell
                buf[n + 1] = y
                buf[n + 2] = run_n * cell
                buf[n + 3] = cell
                buf[n + 4] = run_c
                n += 5
            if n:
                cv.fill_rects(buf, n // 5)

    def _draw_map_box(self, cv, x0, y0, cell, cols, rows, cam_x, cam_y,
                      bx0, by0, bx1, by1, color, double):
        """Outline the map-cell rectangle (bx0,by0)..(bx1,by1) (any orientation),
        clamped to the visible window, in `color` (#91 SELECT overlay). `double` draws
        an inner outline too (the thick live-drag box); a box fully off-window draws
        nothing. Mirrors the RECT-preview clamp so the two tools read alike."""
        if bx1 < bx0:
            bx0, bx1 = bx1, bx0
        if by1 < by0:
            by0, by1 = by1, by0
        ix0 = bx0 if bx0 > cam_x else cam_x
        iy0 = by0 if by0 > cam_y else cam_y
        vx1 = cam_x + cols - 1
        vy1 = cam_y + rows - 1
        ix1 = bx1 if bx1 < vx1 else vx1
        iy1 = by1 if by1 < vy1 else vy1
        if ix0 > ix1 or iy0 > iy1:
            return
        rpx = x0 + (ix0 - cam_x) * cell
        rpy = y0 + (iy0 - cam_y) * cell
        rpw = (ix1 - ix0 + 1) * cell
        rph = (iy1 - iy0 + 1) * cell
        cv.rectb(rpx, rpy, rpw, rph, color)
        if double and rpw > 2 and rph > 2:
            cv.rectb(rpx + 1, rpy + 1, rpw - 2, rph - 2, color)
