# Map (grep -n a name to jump there):
#   -- the tool row    PICO-8's tools, the more menu's operations, their keys
#   PaintLayout        the measures the page takes: the grid's span, the palette's side
#   PaintLayer         the host of the Art tab's page: its state, its canvases, its keys
"""The sprite PAINT editor (#4/#30), the Editor's Art tab: the host of its
`uitree` page (editor_sprite.py), the handheld's tab and the desk Editor's
Sprite pane alike.

It edits the cart's SpriteSheet (ws.run.project.sheet) through `ws.paint` (a PaintEditor).
SAVE is GONE (#111, owner decision 2026-07-21): there is no SAVE button anywhere in the
editor -- CLOSE hard-commits the sheet on its way out (ws.text.leave_menu, which is
EditorApp.leave -- PLAY, a hard-commit trigger now), and the idle-typing autosave-commit +
every other tab-leaving exit path (a tab switch, PROJECTS, a window/context-X, a workspace
swap, going home) commit it too.

Boundary: the SHEET + the current-editor handle + the persistence verbs stay on
Workstation -- `ws.run.project.sheet` (single source of the pixels), `ws.paint` (the
PaintEditor handle, device/test-pinned like ws.editor), `ws.paint_status` (status), and
`ws.saves.save_sprites` / `ws.saves.share_tile_get` / `ws.saves.share_tile_put` (cart
state the device + tests pin). PaintLayer READS those and DISPATCHES to them; it owns the
page's host, the canvases' drawing (the grid, the sprite map, the flags, the preview, the
pickers' sheet) and the drag-stroke continuity state (_paint_drag). `NAMES` (palette) is
injected (the circular-import dodge).

The frame draws the "menu" strip over the page (`bar_layer.STRIP_OF`).

Responsive (#39 step 3): the tab draws on the reflowed system canvas at the panel's
native size. The page lays it out; `PaintLayout` measures what the page takes in
pixels: the grid's span, the largest multiple of 48 that fits (48 = lcm of the 8/16/24
sprite dims, so every zoom level keeps whole on-screen pixels), the palette's side, the
tools' pitch.
"""

import ui_font as _ui_font
import ui_draw as _ui_draw
import layout_base as _lb
import uitree_editor
import editor_sprite
from layers import Layer
from view_host import checker as _checker, checker_quads as _checker_quads, went_up as _went_up
from editors_paint_map import PaintEditor, _pe_line
from array import array

from layout_base import (LayoutBase, BASE_W as _BASE_W, BASE_H as _BASE_H,
                         metric_class as _metric_class, DESK as _DESK,
                         pane as _in_pane)


# -- the tool row (PICO-8's set, owner 2026-10-19) ---------------------------
# ONE row on every tier: the drawing tools -- pen, fill, shape, select and
# stamp -- then the more button, which opens the operations as a menu. Shape
# is one button over three tools: a tap selects the last shape used, a tap
# while a shape is in use moves to the next (oval -> rect -> line), and its
# icon is the shape in use. Stamp stamps the clipboard where the grid is
# tapped. The operations (copy, the flips, rotate, the shifts, mirror, clear)
# act on the selection, else the whole sprite, and each has a key on a
# keyboard (PICO-8's: F V R, the arrows, Del, Ctrl-C/X/V). UNDO/REDO are
# the bar's ONE pair (#111).
_TOOLS = ("pen", "fill", "shape", "select", "stamp", "more")
_SHAPES = (PaintEditor.OVAL, PaintEditor.RECT, PaintEditor.LINE)
# A shape's icon: the shape button wears the shape in use.
_SHAPE_ICON = {PaintEditor.OVAL: "oval", PaintEditor.RECT: "rect", PaintEditor.LINE: "line"}
# The operations the more menu runs, which close it.
_OPS = ("copy", "fliph", "flipv", "rot", "sleft", "sright", "sup", "sdown", "mirror", "clear")
# The key each operation answers to, per input (the hints' profiles,
# native/moy_ui/moy_ui_parts.c's ACT_KEYS): what the more menu shows at a
# row's right, an arrow named as the hints name it (the menu draws it as
# the hint strip's sign, never a face's arrow). The T-Deck's trackball moves
# the grid's cursor, so its shifts have no key; a gamepad and touch reach the
# operations through the menu.
_OP_KEYS = {
    "keys": {"copy": "Ctrl C", "fliph": "F", "flipv": "V", "rot": "R",
             "sleft": "left", "sright": "right", "sup": "up", "sdown": "down",
             "clear": "Del"},
    "tdeck": {"fliph": "F", "flipv": "V", "rot": "R", "clear": "Del"},
}
# The first rows' words (editor_sprite.OPS).
_OP_WORDS = {"copy": "Copy", "sleft": "Shift left"}
_KEYED = ("copy", "fliph", "flipv", "rot", "sleft", "sright", "sup", "sdown", "clear")
# The typed bytes the tab answers to, on a keyboard: PICO-8's sprite keys.
_KEY_OPS = {
    0x03: "copy", 0x18: "cut", 0x16: "paste", 0x08: "clear", 0x7F: "clear",
    ord("f"): "fliph", ord("F"): "fliph", ord("v"): "flipv", ord("V"): "flipv",
    ord("r"): "rot", ord("R"): "rot", ord("m"): "more", ord("M"): "more",
}
# The band's items before its way back: the operations' actions (the band
# draws each as the keys of the input in use, and drops one the input has no
# key for), the more menu's before the shifts', which a narrow band drops
# first. With a selection, clear takes shift's place.
_HINTS = ("flip", "Flip", "rotate", "Rotate", "more", "More", "shift", "Shift")
_HINTS_SEL = ("flip", "Flip", "rotate", "Rotate", "more", "More", "clear", "Clear")
# The desk Editor's Sprite pane: its sprite keys, the more menu, the next pane;
# an input with no Q, W or F6 names only the more menu.
_HINTS_PANE = ("Q W", "Sprite", "more", "More", "F6", "Next pane")
_HINTS_PANE_PAD = ("more", "More")
# The drawing-mode tools (current while in use); shape is any of _SHAPES.
_TOOL_MODE = {
    "pen": PaintEditor.PEN, "fill": PaintEditor.FILL, "select": PaintEditor.SELECT,
    "stamp": PaintEditor.STAMP,
}
# PICO-8's flag colours, MOY64's first sixteen: red, orange, yellow,
# green, blue, indigo, pink, peach.
_FLAG_INKS = (8, 9, 10, 11, 12, 13, 14, 15)


def _row_h(desk, fs):
    """A placed row's height (moy_uitree_walk.c's h_row): 48 on the desk,
    22 at the scale on a handheld."""
    return 48 if desk else 22 * fs


class PaintLayout(LayoutBase):
    """What the Art page takes in pixels, from the SYSTEM canvas size
    (w, h) and font scale: the rows' pad and gap, the grid's span (the
    largest multiple of 48 its room holds: a hugely bigger drawing surface
    on a big panel, not just scaled chrome), a palette cell's side, a tool's
    pitch, and in the desk Editor's Sprite pane the flags' and the
    preview's heights. The T-Deck's 320x240 is measured by the same
    formulas as every canvas.

    The handheld's arrangement stacks the head row, the grid's row, the
    foot row and the band; the pane's the tool row, the grid's row, the
    sprite's row, the flags, the preview (a tall pane's) and the band
    (the band under an input with keys, `keys`)."""

    def __init__(self, w=_BASE_W, h=_BASE_H, font_scale=1,
                 chrome_scale=None, keys=True):
        LayoutBase.__init__(self, w, h, font_scale, chrome_scale=chrome_scale)
        self.keys = bool(keys)
        self.desk = desk = _metric_class() == _DESK
        self.pane = pane = desk and _in_pane()
        fs = self.fs
        row = _row_h(desk, fs)
        band = row if keys else 0
        cw, ch = self.cw, self.ch
        # the grid's margin, which its cursor's ring reaches into
        gm = self.gm = _ui_draw.mark_reach("cell") + 2
        self.tall = pane and ch >= 470      # 1024 x 600; a short pane (800 x 480) packs
        # the page's pad and gap at 1x (`pad1`, `gap1`; the engine scales them), and in
        # pixels for the room they leave
        sp = _lb.scale(fs)
        if pane:
            cell = 36 if self.tall else 24
            self.pad1, self.gap1 = 7, 4
            self.pad, self.gap = 7 * sp, 4 * sp
            self.pitch = cell + 4
            # the flags' row: its discs' cell, and its word's line at the
            # scale, which may reach into the rows' gap either side
            self.flag_cell = cell
            self.flags_h = max(cell + 4, _ui_draw.font("ui")[2] * fs - self.gap)
            self.preview_h = 34 + 4 if self.tall else 0
            hroom = ch - 2 * row - self.flags_h - self.preview_h - band
            wroom = (cw - 2 * self.pad - self.gap) * 4 // 5
        else:
            self.pad1, self.gap1 = (8, 10) if desk else (6, 6)
            self.pad, self.gap = self.pad1 * sp, self.gap1 * sp
            col = 300 if desk else 120 * fs       # the map's least width
            hroom = ch - 2 * row - band
            wroom = (cw - 2 * self.pad - 2 * self.gap - col) * 144 // 166
            self.flags_h = self.preview_h = self.flag_cell = 0
        span = max(48, 48 * (min(hroom, wroom) // 48))
        self.span = span
        # ...on either side, and over and under it as far as its room
        # leaves (where the ring's outer mat is cut), clear of the row under
        # it, which an arrow would take for one beside it
        # (a canvas's h= and a button's w= are in the page's unit, the
        # handheld's font scale: what the page is handed divides by it)
        self.unit = unit = 1 if desk else fs
        gmv = max(0, min(gm, (hroom - span - 2) // 2))
        self.gmv = gmv = gmv - gmv % unit
        self.grid = (span + 2 * gm, span + 2 * gmv)
        self.mpad1 = max(0, self.pad - gm) // sp
        sw = span // 8 if pane else max(6 * fs, span * 11 // 144)
        self.sw = max(1, sw // unit)        # a palette cell's side in the page's unit
        self.pal = (2 * self.sw * unit, 8 * self.sw * unit)
        self.words = False
        if not pane:
            pitch = min(48 if desk else 24 * fs, span // len(_TOOLS))
            self.pitch = pitch - pitch % unit
            # the foot's load, save and to-Files buttons wear their words
            # where the three fit beside the tools, else their icons alone
            room = cw - 2 * self.pad - len(_TOOLS) * self.pitch - 2 * (len(_TOOLS) + 2)
            need = sum([_ui_draw.print_width(w_, fs) + 28 * fs for w_ in ("Load", "Save", "To Files")])
            self.words = need + 120 * fs <= room
        # the more menu as wide as its widest row and key, the pickers as
        # their size's seg (each wider still where its text is)
        pw = _ui_draw.print_width
        most = max([pw(w_, fs) for w_ in ("Turn off mirror", "Flip across", "Shift right")])
        self.more_w = min(cw - 2 * self.pad,
                          max(260 if desk else 150 * fs, most + pw("Ctrl C", fs) + 40 * fs + 24))
        self.seg_w = pw("Size", fs) + 3 * (pw("3x3", fs) + 24 * fs) + 32 * fs
        self.k = 2 if desk else fs          # the pickers' sheet's scale...
        self.room = ch - 3 * row            # ...under the room the popover has


class _Damage:
    def __init__(self, ws):
        self.ws = ws

    def all(self):
        self.ws.mark_dirty()


class PaintLayer(Layer):
    """The Art tab's Layer (SYSTEM domain): the page (editor_sprite.py) on
    the reflowed system canvas, its host. The page's controls are its own;
    the grid, the sprite map, the flags, the preview and the pickers' sheet
    are its canvases, which this layer draws and whose presses and keys it
    takes. Reads ws.paint / ws.run.project.sheet and dispatches the
    operations and load / save / to-Files to Workstation."""

    id = "paint"
    domain = "system"

    def __init__(self, ws, names):
        self.ws = ws
        self._NAMES = names
        self._paint_drag = None       # last painted grid cell during a drag (#30)
        self._fill_fired = False      # FILL already fired this press (#90; see _paint_stroke)
        self._shape_start = None      # RECT/LINE/OVAL/SELECT drag origin cell (#90)
        self._shape_end = None        # ...and its current (clamped) end cell, for preview
        # The grid's cursor (lx, ly): the cell the pointer last pressed or
        # dragged over, moved by the arrows; `a` acts there as a tap would.
        self._cur = [0, 0]
        self._flag = 0                # the flags' cursor
        self._pop = False             # the popover open: "more", "pickers" or False
        self._shifts = False          # the more menu shows its shifts' page
        self._shape = PaintEditor.OVAL   # the shape button's shape when not in use
        self._grid_q = None           # the grid's coloured and clear cells, as quads
        self.page = None              # the page's engine (editor_sprite.py), made at its first use
        self._host = _ui_draw.AppHost("editor_sprite", self)
        self._made = [None] * 14      # what `_sync` made the page's values from
        self._shown = None            # the values it handed the page last
        self._menu_top = False        # a menu just opened: its first row takes focus at the next draw
        self._keys_shown = (None, ())  # (the input's kind, the operations' key words)
        self._band = None             # the band's items as handed the page
        self._rect = None             # the content rect, as a tuple drawn with
        self._map_wh = (0, 0)         # the map's and the flags' size, as drawn last
        self._flags_w = 0
        self.sheet_shown = None       # where the pickers' sheet drew: x0, y0, x1, y1
        self._sheet_first = 0         # the sheet's first row the pickers show...
        self._sheet_fit = 1           # ...and how many, as the last frame drew them
        self._sheet_press = None      # a press on the sheet: (its y, the first row then, moved)
        sc = ws.sys_canvas
        self._lay_args = (sc.w, sc.h, getattr(sc, "font_scale", 1), None)
        self.layout = PaintLayout(sc.w, sc.h, getattr(sc, "font_scale", 1),
                                  keys=self._keys())

    @staticmethod
    def _keys():
        """Whether the band has keys to name (none under touch)."""
        return _ui_draw.hint_kind() != "touch"

    def relayout(self, w, h, fs, cs=None):
        """Measure the page again (#39) -- called by ws.relayout on a
        font-scale change (and, later, a window resize)."""
        self._lay_args = (w, h, fs, cs)
        self.layout = PaintLayout(w, h, fs, chrome_scale=cs, keys=self._keys())

    def _sync_layout(self):
        """A change between touch and an input with keys (the band) measures
        the page again."""
        if self.layout.keys != self._keys():
            w, h, fs, cs = self._lay_args
            self.layout = PaintLayout(w, h, fs, chrome_scale=cs, keys=self._keys())

    # -- the page ------------------------------------------------------------

    def _page(self):
        """The page's engine, made and opened at its first use, the grid
        holding the keys."""
        if self.page is None:
            self.page = uitree_editor.page(editor_sprite.sprite_page, self._host,
                                           _Damage(self.ws))
            self.page.env = self            # what its handlers reach (`uitree_app.env()`)
            self.page.bare = True           # its ground is the layer's
            ws = self.ws                    # a canvas holds its press while the pointer is down
            self.page.pointer_down = lambda: bool(ws.pointer.down)
            self.page.open(hook="none")
            self._sync()
            self.run("home")
        return self.page

    @property
    def s(self):
        """The page's state."""
        self._page()._bind()
        return editor_sprite.s

    def run(self, name, *args):
        """Run the page's action or hook `name` now."""
        pg = self._page()
        pg._bind()
        pg.run_action(pg.actions[name], args, "host")

    def pointer(self):
        """The pointer, where the page's host reads whether it is held."""
        return self.ws.pointer

    def rect_of(self, key):
        """Where the last frame placed the page's node `key`, in SYSTEM
        coords (None before it drew)."""
        return None if self.page is None else self.page.rect_of(key)

    def _sync(self):
        """The editor's state the page shows, handed to its `sync` hook
        where it moved."""
        ws = self.ws
        pe = ws.paint
        lay = self.layout
        kind = _ui_draw.hint_kind()
        g = self._made
        sheet = pe.sheet if pe is not None else None
        st = ws.paint_status
        if (g[0] is pe and g[1] is lay and g[2] is st and g[3] == self._pop and g[4] == self._shifts
                and g[5] == self._shape and g[6] == kind and g[7] is sheet
                and (pe is None or (g[8] == pe.n and g[9] == pe.size and g[10] == pe.tool
                                    and g[11] == pe.color and g[12] == pe.has_clip
                                    and g[13] == pe.mirror))):
            return
        g[0], g[1], g[2], g[3], g[4], g[5], g[6], g[7] = (pe, lay, st, self._pop, self._shifts,
                                                          self._shape, kind, sheet)
        if pe is not None:
            g[8], g[9], g[10], g[11], g[12], g[13] = (pe.n, pe.size, pe.tool, pe.color,
                                                      pe.has_clip, pe.mirror)
        if self._keys_shown[0] != kind:
            ks = _OP_KEYS.get(kind, {})
            self._keys_shown = (kind, tuple("\t" + ks[o] if o in ks else "" for o in _KEYED))
        if pe is None:
            vals = (True, lay.pane, lay.tall, "0", "", "", "other", "oval", False, False, "none",
                    False, 0, "1", lay.pad1, lay.mpad1, lay.gap1, lay.grid[0], lay.grid[1],
                    lay.words, lay.sw,
                    lay.pal[0], lay.pal[1], lay.pitch, lay.flags_h,
                    lay.preview_h, 64, lay.more_w, 200, self._keys_shown[1])
        else:
            times = "×" if _ui_font.print_symbols() else "x"
            tid = "other"
            if pe.tool in _SHAPES:
                tid = "shape"
            else:
                for t in _TOOL_MODE:
                    if _TOOL_MODE[t] == pe.tool:
                        tid = t
            k, sheet_h, pick_w, _fit = self._sheet_geom(sheet)
            vals = (False, lay.pane, lay.tall, str(pe.n), "%d%s%d" % (pe.size, times, pe.size),
                    st or "", tid, _SHAPE_ICON[pe.tool if pe.tool in _SHAPES else self._shape],
                    bool(pe.has_clip), bool(pe.mirror), self._pop or "none", self._shifts,
                    pe.color, str(pe.size), lay.pad1, lay.mpad1, lay.gap1, lay.grid[0],
                    lay.grid[1] // lay.unit, lay.words, lay.sw, lay.pal[0], lay.pal[1],
                    lay.pitch // lay.unit, lay.flags_h, lay.preview_h, sheet_h // lay.unit,
                    lay.more_w, pick_w,
                    self._keys_shown[1])
        if vals != self._shown:
            self._shown = vals
            self.run("sync", vals)

    def _band_items(self):
        """The band's items: the operations' keys, the selection's while one
        is held; the pane's own while none is."""
        pe = self.ws.paint
        sel = pe is not None and pe.sel is not None
        if self.layout.pane and not sel:
            return _HINTS_PANE if _ui_draw.hint_kind() == "keys" else _HINTS_PANE_PAD
        return _HINTS_SEL if sel else _HINTS

    # -- Layer facets --------------------------------------------------------

    def draw(self, dt):
        ws = self.ws
        ws.reset_canvas_state()
        self._sync_layout()
        lay = self.layout
        r = self._rect
        if r is None or r[0] != lay.cx or r[1] != lay.cy or r[2] != lay.cw or r[3] != lay.ch:
            r = self._rect = (lay.cx, lay.cy, lay.cw, lay.ch)
        cv = ws.sys_canvas
        th = ws.theme_colors
        pg = self._page()
        cv.rect(r[0], r[1], r[2], r[3], th["surface"])
        band = self._band_items()
        if band is not self._band:
            self._band = band
            pg.band_extra(band)
        pg.band = lay.keys
        d = ws.editor_desk if lay.pane else None
        # a desk's pane the keys are not in shows no focus
        away = d is not None and d.tab_of(d.focused()[0]) != "paint"
        self._host.begin(cv, th, r, lay.desk, False, away)
        self._sync()
        if self._menu_top:
            # a menu opened (the more menu, the shifts' page) opens on its
            # first row (a row's id is its text)
            self._menu_top = False
            op = "sleft" if self._shifts else "copy"
            self.run("menu", _OP_WORDS[op] + self._keys_shown[1][_KEYED.index(op)])
        pg.paint(dt, cv, th, r, lay.desk)
        self._host.end()
        if not self._host.still():
            ws.request_frame()

    def ball_steps(self):
        """The trackball steps an open popover's rows (the more menu, a
        picker) and points at the grid otherwise (InputPolicy.ball_steps)."""
        return bool(self._pop)

    def at_top(self):
        """The page's keys went past its top, no popover open and not a desk's
        pane: an up goes on to the bar (InputRouter._bar_keys)."""
        return not self._pop and not self.layout.pane and _went_up(self.page)

    def handle_input(self, i):
        if not self._pop:
            self.handle_key(i)         # the typed keys: the operations, the sprite before, after
            if i.pressed("y") and self.ws.paint is not None:
                self._open_more()      # a gamepad's more menu
                return True
        elif i.pressed("b"):
            # B steps back: the shifts' page to the more menu, a popover shut
            if self._shifts:
                self._shifts = self._menu_top = False
            else:
                self.act("close")
            self.ws.mark_dirty()
            return True
        self._sync()
        pop = self._pop
        self._page().keys(i)          # (the page's damage marks what the keys moved)
        if not pop:
            self.ws.home.leave_or_home(self.ws.spine.exit)  # B leaves, as on every tab
        return True

    def handle_key(self, i):
        """The typed keys, a press each (the input table's `typed`, so a held
        key fires once): PICO-8's sprite keys (`_KEY_OPS`): F and V flip, R rotates, Del and Backspace clear,
        Ctrl-C copies, Ctrl-X cuts, Ctrl-V stamps, M opens the more menu, and
        Q and W (PICO-8's) or E step to the sprite before and after -- Q and
        E on the T-Deck, where W moves the cursor (moy_kbd.c, THE MOVE KEYS).
        Each has its place on the screen too, so touch reaches every one."""
        pe = self.ws.paint
        k = getattr(i, "typed", 0)
        if pe is None or not k:
            return
        if k in (0x71, 0x51, 0x77, 0x57, 0x65, 0x45):   # Q, and W or E: the sprite before, after
            pe.select(-1 if k in (0x71, 0x51) else 1)
            self.ws.mark_dirty()
            return
        op = _KEY_OPS.get(k)
        if op == "more":
            self._open_more()
        elif op is not None:
            self._do_tool(op)
            self.ws.mark_dirty()

    def handle_pointer(self, px, py, click):
        ws = self.ws
        # SYSTEM coords (#39 step 3): the Editor's lent zone (Stage 4) claims
        # its taps first, then the page's (its canvases take their presses).
        if click and ws.bar_layer.handle_bar_tap("menu", px, py):
            self._pop = False
            return True
        self._sync()
        pg = self._page()
        pg.point(px, py, click)
        q = pg.q
        if q:
            # what a canvas's press does (a sprite the sheet picked) lands
            # with the input, where a desk's frame sees what it changed
            pg.q = []
            pg._bind()
            for act, args, src in q:
                pg.run_action(act, args, src)
        return True

    # -- the page's handlers -------------------------------------------------

    def act(self, verb):
        """One of the page's actions: a tool, an operation (which closes the
        more menu), the handheld's shifts' page, the sprite before or after,
        the pickers, load, save and to-Files, or a popover closed."""
        ws = self.ws
        pe = ws.paint
        if verb == "close":
            self._pop = False
        elif verb == "shifts":
            self._shifts = self._menu_top = True
        elif verb == "pickers":
            self._open_pickers()
        elif verb == "load":
            ws.saves.share_tile_get()              # import the tile from the shared sheet
        elif verb == "save":
            ws.saves.share_tile_put()              # save the tile to the shared sheet
        elif verb == "files":
            ws.saves.send_sprites_to_files()       # export the sheet to files/Pictures/Sprites/ (#108)
        elif pe is None:
            return
        elif verb == "prev" or verb == "next":
            pe.select(-1 if verb == "prev" else 1)
        else:
            self._do_tool(verb)
            if verb in _OPS:
                self._pop = False
        ws.mark_dirty()

    def set_color(self, c):
        pe = self.ws.paint
        if pe is not None and 0 <= c < 16:
            pe.color = c
            self.ws.mark_dirty()

    def set_size(self, i):
        pe = self.ws.paint
        if pe is not None and 1 <= i <= len(pe.SIZES) and pe.SIZES[i - 1] != pe.size:
            pe.size = pe.SIZES[i - 1]
            pe._clamp_size()
            self.ws.mark_dirty()

    def _open_more(self):
        """Open the more menu (the ⋯ button, M on a keyboard, Y on a
        gamepad), or close it when it is open."""
        self._pop = False if self._pop == "more" else "more"
        self._shifts = False
        self._menu_top = bool(self._pop)
        self.ws.mark_dirty()

    def _open_pickers(self):
        """Open the pickers (the size), or close them when they are open."""
        self._pop = False if self._pop == "pickers" else "pickers"
        pe = self.ws.paint
        sheet = pe.sheet if pe is not None else None
        if self._pop and sheet is not None:
            fit = self._sheet_geom(sheet)[3]
            self._sheet_first = max(0, min(sheet.rows - fit, pe.n // sheet.cols - fit // 2))
        self.ws.mark_dirty()

    # -- the grid ------------------------------------------------------------

    def _cell(self):
        pe = self.ws.paint
        return max(1, self.layout.span // pe.dim)

    def _paint_grid_cell(self, x, y):
        """Grid-local pixel (lx, ly) under (x, y), the grid canvas's
        coordinates, or None outside the grid. The cell size shrinks as the
        sprite grows so the size*8 region always fills the grid's span (#30;
        responsive span #39)."""
        pe = self.ws.paint
        if pe is None or x < 0 or y < 0:
            return None
        cell = self._cell()
        lx, ly = x // cell, y // cell
        if lx < pe.dim and ly < pe.dim:
            return (lx, ly)
        return None

    def _grid_cell_clamped(self, x, y):
        """Grid-local cell under (x, y), CLAMPED into [0, dim) even when the pointer
        wandered off the grid -- used for the shape/select drag preview so dragging
        past an edge still tracks to the edge (#90). Returns None only with no editor."""
        pe = self.ws.paint
        if pe is None:
            return None
        cell = self._cell()
        d = pe.dim
        lx, ly = x // cell, y // cell
        lx = 0 if lx < 0 else (d - 1 if lx > d - 1 else lx)
        ly = 0 if ly < 0 else (d - 1 if ly > d - 1 else ly)
        return (lx, ly)

    def grid_pointer(self, kind, x, y):
        """A press on the grid canvas, its drag and its release, in its
        coordinates: a tap draws, a press-drag-release is ONE stroke, shape
        or selection (#30/#90), the same path for a host mouse and a device
        touch."""
        if self.ws.paint is None:
            return
        x -= self.layout.gm
        y -= self.layout.gmv
        if kind == "down":
            if self._grid_press(x, y):
                self._follow(x, y)
        elif kind == "drag":
            self._paint_drag_move(x, y)
        else:
            self._paint_release()
        self.ws.mark_dirty()

    def grid_keys(self, i):
        """The grid's keys while it holds focus: the arrows move its cursor
        -- on a desk keyboard they shift the sprite, PICO-8's keys, and the
        pointer is the cursor there; `a` acts at it as a tap there does (a
        pen dot, a fill, a one-cell shape or selection, a stamp). An arrow
        past the grid's edge is the page's, which moves focus on."""
        ws = self.ws
        pe = ws.paint
        if pe is None:
            return False
        dx = i.steps("right") - i.steps("left")
        dy = i.steps("down") - i.steps("up")
        c = self._cur
        took = False
        if (dx or dy) and _ui_draw.input_kind() == "keys":
            pe.shift(dx, dy)
            took = True
        elif dx or dy:
            d = pe.dim - 1
            x = max(0, min(d, c[0] + dx))
            y = max(0, min(d, c[1] + dy))
            took = (x, y) != (c[0], c[1])
            c[0], c[1] = x, y
        if i.pressed("a"):
            cell = self._cell()
            x = min(c[0], pe.dim - 1) * cell + cell // 2
            y = min(c[1], pe.dim - 1) * cell + cell // 2
            if self._grid_press(x, y):
                self._paint_release()
            took = True
        if took:
            ws.mark_dirty()
        return took

    def _follow(self, x, y):
        """The cursor follows the pointer over the grid."""
        cell = self._paint_grid_cell(x, y)
        if cell is not None:
            self._cur[0], self._cur[1] = cell

    def _paint_stroke(self, x, y):
        """Drag-to-draw (#30): paint the grid cell under (x, y) AND fill the line
        from the last painted cell, so a fast drag leaves no gaps. Works the same
        for a host mouse drag and a device touch drag. Returns True if a cell was
        painted."""
        pe = self.ws.paint
        cell = self._paint_grid_cell(x, y)
        if cell is None:
            self._paint_drag = None        # left the grid -> next entry starts fresh
            return False
        # Bucket tool (#90): a tap floods the contiguous region ONCE per press (no
        # drag chaining). `fill` snapshots/records its own undo step, so the brush
        # stroke machinery below is bypassed. The guard is a dedicated per-press
        # flag -- NOT _paint_drag, which resets whenever the held pointer wobbles
        # off the grid edge (above) and would re-fire a second flood (+ a surprise
        # extra undo step) on re-entry; _fill_fired only clears on pointer RELEASE.
        if pe.tool == pe.FILL:
            if not self._fill_fired:
                self._fill_fired = True
                pe.fill(cell[0], cell[1])
            self._paint_drag = cell
            return True
        last = self._paint_drag
        if last is None:
            pe.begin_stroke()              # snapshot before the first pixel (#90)
            pe.paint(cell[0], cell[1])
        else:
            for cx, cy in _pe_line(last[0], last[1], cell[0], cell[1]):
                pe.paint(cx, cy)
        self._paint_drag = cell
        return True

    def _grid_press(self, x, y):
        """A press on the pixel grid. PEN/FILL go through the continuous
        _paint_stroke path (#30); RECT/LINE/OVAL/SELECT record a drag origin
        and defer the commit to release (#90). Returns True iff the press was
        in-grid."""
        pe = self.ws.paint
        if pe.tool in (pe.RECT, pe.LINE, pe.OVAL, pe.SELECT):
            cell = self._paint_grid_cell(x, y)     # a shape/select must START in-grid
            if cell is None:
                return False
            self._shape_start = cell
            self._shape_end = cell
            return True
        if pe.tool == pe.STAMP:
            cell = self._paint_grid_cell(x, y)     # one stamp a press, its top-left here
            if cell is None:
                return False
            pe.paste(cell[0], cell[1])
            return True
        return self._paint_stroke(x, y)

    def _paint_drag_move(self, x, y):
        """A held drag. Grow the pending shape/selection preview (clamped to
        the grid), else keep painting the continuous pen/fill stroke."""
        if self._shape_start is not None:
            cell = self._grid_cell_clamped(x, y)
            if cell is not None:
                self._shape_end = cell
                self._cur[0], self._cur[1] = cell
            return
        if self._paint_stroke(x, y):
            self._follow(x, y)

    def _paint_release(self):
        """Pointer released (anywhere): commit the pending shape/selection, or close a
        brush stroke, so a whole press-drag-release is ONE undo step (#90). Idempotent
        when idle. Re-arms the once-per-press FILL guard (release is the ONLY place it
        clears -- a mid-press grid exit must not re-arm it)."""
        pe = self.ws.paint
        if pe is not None:
            if self._shape_start is not None:
                self._commit_shape_or_select(pe)
            else:
                pe.end_stroke()
        self._paint_drag = None
        self._fill_fired = False
        self._shape_start = None
        self._shape_end = None

    def _commit_shape_or_select(self, pe):
        """Turn a finished shape/select drag into an edit. RECT/LINE/OVAL stamp the
        shape; SELECT sets the selection box on a real drag, and a TAP (no drag) either
        stamps the clipboard there (move/copy) or clears the selection (#90)."""
        s = self._shape_start
        e = self._shape_end if self._shape_end is not None else s
        if pe.tool == pe.SELECT:
            if s == e:
                pe.clear_selection()           # a tap drops the selection
            else:
                pe.set_selection(s[0], s[1], e[0], e[1])
        else:
            pe.stamp_shape(s[0], s[1], e[0], e[1])

    def _do_tool(self, tid):
        """A tool or an operation on the PaintEditor (#90). Every action is
        touch-reachable; undo/redo are the ONE bar pair (#111)."""
        pe = self.ws.paint
        if pe is None:
            return
        if tid in _TOOL_MODE:                  # pen/fill/select/stamp
            pe.set_tool(_TOOL_MODE[tid])
        elif tid == "shape":                   # the last shape, else the next one
            if pe.tool in _SHAPES:
                self._shape = _SHAPES[(_SHAPES.index(pe.tool) + 1) % len(_SHAPES)]
            pe.set_tool(self._shape)
        elif tid == "more":
            self._open_more()
        elif tid == "copy":
            pe.copy_selection()
        elif tid == "cut":
            pe.cut_selection()
        elif tid == "paste":
            self._paste_default(pe)
        elif tid == "erase":
            pe.toggle_erase()
        elif tid == "mirror":
            pe.toggle_mirror()
        elif tid == "fliph":
            pe.flip_h()
        elif tid == "flipv":
            pe.flip_v()
        elif tid == "rot":
            if pe.rotate() is False:
                self.ws.paint_status = "Rotate needs a square"
        elif tid == "sleft":
            pe.shift(-1, 0)
        elif tid == "sright":
            pe.shift(1, 0)
        elif tid == "sup":
            pe.shift(0, -1)
        elif tid == "sdown":
            pe.shift(0, 1)
        elif tid == "clear":
            pe.clear()

    def _paste_default(self, pe):
        """The PASTE button stamps the clipboard at the active selection's top-left (so
        copy->paste lands in place), or at (0, 0) with no selection. In SELECT mode a
        tap on the grid pastes at the tapped cell instead (the move/copy gesture)."""
        if not pe.has_clip:
            return
        if pe.sel is not None:
            pe.paste(pe.sel[0], pe.sel[1])
        else:
            pe.paste(0, 0)

    # -- the canvases --------------------------------------------------------

    def _greys(self):
        return self.ws.look.live.fixed[:2]

    def draw_grid(self, cv, x, y, w, h):
        """The grid in the theme's roles: each pixel a cell, a clear one the
        grey checker, the cells parted by the theme's border where they are
        big enough to part, the sprite's tiles parted, the selection and a
        live shape, and the ring cursor under an input with keys."""
        ws = self.ws
        pe = ws.paint
        sheet = pe.sheet if pe is not None else None
        if sheet is None:
            return
        th = ws.theme_colors
        lay = self.layout
        gx0, gy0 = x + lay.gm, y + lay.gmv
        fs = lay.fs
        greys = self._greys()
        keyline = ws.look.live.fixed[2]
        dim, span = pe.dim, lay.span
        cell = span // dim
        if cell < 1:
            cell = 1
        ox, oy = sheet.tile_origin(pe.n)
        lines = cell >= 6
        inner = cell - 1 if lines else cell
        cs = max(3 * fs, cell // 3)
        if lines:
            cv.rect(gx0 - 1, gy0 - 1, span + 1, span + 1, th["border"])
        # The cells are disjoint, so the coloured ones are the quads of one
        # fill_rects, the clear ones' light ground those of another, and the
        # clear ones' dark squares follow: the pixels of a rect or a checker a
        # cell. (A quad's own colour is a palette index; the ground may be the
        # theme's, which only a call's colour carries.)
        n2 = 5 * dim * dim
        q = self._grid_q
        if q is None or len(q[0]) < n2:
            q = self._grid_q = (array("h", bytes(2 * n2)), array("h", bytes(2 * n2)))
        cq, gq = q
        pix = sheet.pix
        sw_ = sheet.w
        inside = ox + dim <= sw_ and oy + dim <= sheet.h
        k = g = 0
        for ly in range(dim):
            y = gy0 + ly * cell
            base = (oy + ly) * sw_ + ox
            for lx in range(dim):
                x = gx0 + lx * cell
                v = pix[base + lx] if inside else sheet.pget(ox + lx, oy + ly)
                if v:
                    cq[k] = x
                    cq[k + 1] = y
                    cq[k + 2] = inner
                    cq[k + 3] = inner
                    cq[k + 4] = v
                    k += 5
                else:
                    gq[g] = x
                    gq[g + 1] = y
                    gq[g + 2] = inner
                    gq[g + 3] = inner
                    g += 5
        if k:
            cv.fill_rects(cq, k // 5)
        if g:
            cv.fill_rects(gq, g // 5, 0, 0, greys[1])
            dark = greys[0]
            sq = _checker_quads(inner, inner, cs)
            for i in range(0, g, 5):
                for a in sq:
                    cv.fill_rects(a, -1, gq[i], gq[i + 1], dark)
        if pe.size > 1:
            tpx = span // pe.size
            for t in range(1, pe.size):
                cv.rect(gx0 + t * tpx - 1, gy0, 1, span, th["ink_dim"])
                cv.rect(gx0, gy0 + t * tpx - 1, span, 1, th["ink_dim"])
        self._draw_grid_overlay(cv, lay, pe, gx0, gy0, cell)
        # The cursor, under an input with keys (touch shows no focus, and a
        # d-pad or trackball move brings it back): the theme's ring around
        # a black keyline, on a mat of `surface` from the keyline to a pixel
        # past the ring's reach, so it reads on a cell of its own colour.
        if self._keys():
            c = self._cur
            d = pe.dim - 1
            c[0] = min(c[0], d)
            c[1] = min(c[1], d)
            x, y = gx0 + c[0] * cell, gy0 + c[1] * cell
            box = (x - 1, y - 1, cell + 1, cell + 1)
            cv.rectb(box[0], box[1], box[2], box[3], keyline)
            for o in range(1, _ui_draw.mark_reach("cell") + 2):
                cv.rectb(box[0] - o, box[1] - o, box[2] + 2 * o, box[3] + 2 * o,
                         th["surface"])
            _ui_draw.focus(cv, th, box, "cell", ring=True)

    def _draw_grid_overlay(self, cv, lay, pe, gx0, gy0, cell):
        """Overlay the active selection marquee and the live shape/select drag preview
        on the zoomed grid (#90). The committed selection and a live SELECT drag
        are one two-toned ring (design review R4-02): a line of `ink` on and
        outside the box's grid lines, then one of `surface` within, as the
        colour in use and the map's sprite are marked -- never a palette
        colour, so one tone reads against the grid's lines and any pixel in
        every theme. A live RECT/LINE/OVAL drag stamps the shape's cells in the
        current ink with a white outline so it reads even when ink == background."""
        NAMES = self._NAMES
        th = self.ws.theme_colors
        t = 2 if lay.desk else lay.fs
        lines = 1 if cell >= 6 else 0

        def ring(x0, y0, x1, y1):
            x = gx0 + x0 * cell
            y = gy0 + y0 * cell
            w = (x1 - x0 + 1) * cell
            h = (y1 - y0 + 1) * cell
            # on the box's own grid lines, where the grid draws them, and out
            for i in range(t):
                cv.rectb(x - 1 - i, y - 1 - i, w + 2 - lines + 2 * i,
                         h + 2 - lines + 2 * i, th["ink"])
            for i in range(t):
                cv.rectb(x + i, y + i, w - lines - 2 * i, h - lines - 2 * i,
                         th["surface"])

        if pe.sel is not None:
            ring(pe.sel[0], pe.sel[1], pe.sel[2], pe.sel[3])
        if self._shape_start is not None and self._shape_end is not None:
            s, e = self._shape_start, self._shape_end
            if pe.tool == pe.SELECT:
                x0 = s[0] if s[0] < e[0] else e[0]
                x1 = s[0] if s[0] > e[0] else e[0]
                y0 = s[1] if s[1] < e[1] else e[1]
                y1 = s[1] if s[1] > e[1] else e[1]
                ring(x0, y0, x1, y1)
            else:
                ink = 0 if pe.erase else pe.color
                for (x, y) in pe.shape_points(s[0], s[1], e[0], e[1]):
                    cv.rect(gx0 + x * cell, gy0 + y * cell, cell, cell, ink)
                    if cell >= 6:
                        cv.rectb(gx0 + x * cell, gy0 + y * cell, cell, cell,
                                 NAMES["white"])

    def _map_ring(self):
        """The width of each of the two lines that mark the map's sprite."""
        lay = self.layout
        return 2 if lay.desk else lay.fs

    def _map_geom(self, pe, sheet, w, h):
        """The sprite map's (k, first row, rows) in a (w, h) canvas: the
        sheet's sprites at the largest whole scale `k` that holds a row of
        them across the map with the sprite's mark beside it, as many rows as
        fit, from the row that keeps the sprite (and its size's span) in
        view. The mark lies outside the sprite."""
        cols = sheet.cols
        o = 2 * self._map_ring()            # the mark's two lines, inside the canvas
        k = max(1, (w - 2 * o) // (cols * sheet.TILE))
        tile = sheet.TILE * k
        rows = min(sheet.rows, max(1, (h - 2 * o) // tile))
        row = pe.n // cols
        first = row - (rows - pe.size) // 2
        first = max(0, min(first, sheet.rows - rows))
        return k, first, rows

    def draw_map(self, cv, x, y, w, h):
        """The sprite map (owner, 2026-10-19): the sheet around the sprite
        on the grey checker, a fade at an edge past which the sheet goes on,
        the sprite and its size's span outlined outside its pixels -- a line
        of `surface` around it, then one of `ink`, as the colour in use is
        marked, so the sprite shows whole (design review R4-03) -- and a tap
        on a sprite makes it the sprite."""
        pe = self.ws.paint
        sheet = pe.sheet if pe is not None else None
        self._map_wh = (w, h)
        if sheet is None or w <= 0 or h <= 0:
            return
        th = self.ws.theme_colors
        o = self._map_ring()
        x0, y0 = x + 2 * o, y + 2 * o
        k, first, rows = self._map_geom(pe, sheet, w, h)
        tile = sheet.TILE * k
        cols = sheet.cols
        greys = self._greys()
        _checker(cv, x0, y0, cols * tile, rows * tile, max(2, 2 * k), greys[0], greys[1])
        cv.sspr(sheet, 0, first * sheet.TILE, cols * sheet.TILE, rows * sheet.TILE,
                x0, y0, cols * tile, rows * tile, 0)
        fh = min(8 * self.layout.fs, rows * tile // 2)
        if first > 0:
            _ui_draw.fade(cv, (x0, y0, cols * tile, fh), th["surface"], True)
        if first + rows < sheet.rows:
            _ui_draw.fade(cv, (x0, y0 + rows * tile - fh, cols * tile, fh), th["surface"])
        n = pe.n
        sx = x0 + (n % cols) * tile
        sy = y0 + (n // cols - first) * tile
        span = pe.size * tile
        for i in range(1, 2 * o + 1):
            c = th["surface"] if i <= o else th["ink"]
            cv.rectb(sx - i, sy - i, span + 2 * i, span + 2 * i, c)

    def map_pick(self, x, y):
        """A tap on the sprite map, in its coordinates: the sprite under it
        becomes the sprite."""
        pe = self.ws.paint
        sheet = pe.sheet if pe is not None else None
        w, h = self._map_wh
        if sheet is None or w <= 0:
            return
        o = 2 * self._map_ring()
        k, first, rows = self._map_geom(pe, sheet, w, h)
        tile = sheet.TILE * k
        c = (x - o) // tile
        r = (y - o) // tile
        if 0 <= c < sheet.cols and 0 <= r < rows:
            pe.n = (first + r) * sheet.cols + c
            pe._clamp_size()
            self.ws.mark_dirty()

    def _flag_pitch(self, w):
        lay = self.layout
        fw = _ui_draw.print_width("Flags", lay.fs) + 12
        return max(16, min(lay.flag_cell, (w - fw) // 8))

    def draw_flags(self, cv, x, y, w, h):
        """The sprite's eight flags as toggles (Q-03): a disc in its colour
        where it is set, a ring where it is clear, then the word; the keys'
        cursor on the flag they toggle while the flags hold focus."""
        ws = self.ws
        pe = ws.paint
        if pe is None:
            return
        th = ws.theme_colors
        self._flags_w = w
        flags = ws.run.project.flags
        v = flags[pe.n] if flags is not None and pe.n < len(flags) else 0
        cell = self.layout.flag_cell
        row = self.layout.flags_h - 4
        fp = self._flag_pitch(w)
        focused = self._keys() and self.page is not None and self.page._focus_key() == "flags"
        for k in range(8):
            fx = x + k * fp
            d = max(8, min(fp, cell) - (14 if cell >= 36 else 8))
            ox, oy = fx + (fp - d) // 2, y + (row - d) // 2
            if v >> k & 1:
                cv.rrect(ox, oy, d, d, d // 2, _FLAG_INKS[k])
            else:
                cv.rrect(ox, oy, d, d, d // 2, None, th["ink_dim"])
            if focused and k == self._flag:
                _ui_draw.focus(cv, th, (fx, y + (row - cell) // 2, fp, cell), "cell", ring=True)
        line = _ui_draw.font("ui")[2] * self.layout.fs
        cv.print("Flags", x + 8 * fp + 12, y + (row - line) // 2, th["ink_dim"], 1)

    def flag_tap(self, x):
        """A tap on the flags, in their coordinates: the flag under it flips."""
        k = x // self._flag_pitch(self._flags_w)
        if 0 <= k < 8:
            self._flag = k
            self._toggle_flag(k)

    def flags_keys(self, i):
        """The flags' keys while they hold focus: left and right move along
        them, `a` flips the one the cursor is on."""
        d = i.steps("right") - i.steps("left")
        f = max(0, min(7, self._flag + d))
        took = f != self._flag
        self._flag = f
        if i.pressed("a"):
            self._toggle_flag(f)
            took = True
        if took:
            self.ws.mark_dirty()
        return took

    def _toggle_flag(self, k):
        """A flag flipped: the sprite's bit flips, and reaches the running
        game at its next frame (`ProjectStore.flag_edits`); it is saved with
        the sheet (`Project.commit_sprites`)."""
        ws = self.ws
        flags = ws.run.project.flags
        pe = ws.paint
        if flags is None or pe is None or pe.n >= len(flags):
            return
        flags[pe.n] ^= 1 << k
        ws.run.project.flags_dirty = True
        if ws.sheet is not None:
            ws.sheet.dirty = True
        ws.mark_dirty()

    def draw_preview(self, cv, x, y, w, h):
        """The sprite as the game draws it: at 1x, 2x and 4x, then the words."""
        pe = self.ws.paint
        sheet = pe.sheet if pe is not None else None
        if sheet is None:
            return
        th = self.ws.theme_colors
        fs = self.layout.fs
        h -= 4
        line = _ui_draw.font("ui")[2] * fs
        dim = pe.dim
        # The sprite's span on the sheet (tile_span_image's, clamped at its
        # edge), each size one native stretch of it with colour 0 clear.
        ox, oy = sheet.tile_origin(pe.n)
        T = sheet.TILE
        pw = min(pe.size, (sheet.w - ox) // T) * T
        ph = min(pe.size, (sheet.h - oy) // T) * T
        x1 = x + w
        times = "×" if _ui_font.print_symbols() else "x"
        for z in (1, 2, 4):
            side = dim * z
            word = "%d%s" % (z, times)
            if x + side + 4 + _ui_draw.print_width(word, fs) > x1 or side > h:
                break
            cv.sspr(sheet, ox, oy, pw, ph, x, y + h - side, pw * z, ph * z, 0)
            cv.print(word, x + side + 4, y + h - line, th["ink_dim"], 1)
            x += side + 4 + _ui_draw.print_width("4x", fs) + 14
        if x + _ui_draw.print_width("in the game", fs) <= x1:
            cv.print("in the game", x, y + h - line, th["ink_dim"], 1)

    def _sheet_geom(self, sheet):
        """The pickers' sheet: (its scale, its canvas's height, the
        popover's width, the rows it shows): the rows that fit the room
        under the popover's head, which a drag scrolls."""
        lay = self.layout
        fs = lay.fs
        m = 2 * fs
        k = lay.k
        tile = sheet.TILE * k
        fit = max(1, min(sheet.rows, (lay.room - 2 * m) // tile))
        pw = sheet.cols * tile + 2 * m
        return k, fit * tile + 2 * m, min(lay.cw - 2 * lay.pad, max(
            pw + (48 if lay.desk else 24 * fs), 300 if lay.desk else 200 * fs, lay.seg_w)), fit

    def draw_sheet(self, cv, x, y, w, h):
        """The pickers' sheet at its scale from its first row shown, colour
        0 clear over the map's grey checker, the sprite and its size's span outlined; a tap on a sprite
        makes it the sprite (`sheet_pointer`)."""
        pe = self.ws.paint
        sheet = pe.sheet if pe is not None else None
        if sheet is None:
            return
        k = self._sheet_geom(sheet)[0]
        m = 2 * self.layout.fs
        t = sheet.TILE
        # the rows the canvas holds where the card shows it (the card's room
        # may be less than the layout's measure of it)
        card = self._host.box("pick_pop")
        if card is not None:
            h = min(h, card[1] + card[3] - m - y)
        fit = self._sheet_fit = max(1, min(sheet.rows, (h - 2 * m) // (t * k)))
        first = self._sheet_first = max(0, min(sheet.rows - fit, self._sheet_first))
        x0, y0 = x + m, y + m
        self.sheet_shown = (x, y, x + w, y + h)
        greys = self._greys()
        _checker(cv, x0, y0, sheet.w * k, fit * t * k, max(2, 2 * k), greys[0], greys[1])
        cv.blit_indices_scale(sheet, 0, first * t, sheet.w, fit * t, x0, y0, k, 0)
        tx, ty = sheet.tile_origin(pe.n)
        span = pe.size * t * k
        oy = y0 + (ty - first * t) * k
        if y0 <= oy and oy + span <= y0 + fit * t * k:
            cv.rectb(x0 + tx * k - 1, oy - 1, span + 2, span + 2,
                     self.ws.theme_colors["value"])

    def sheet_pointer(self, kind, x, y):
        """The pickers' sheet under the pointer, in its coordinates: a drag
        scrolls its rows, a press released where it began makes the sprite
        under it the sprite and closes the pickers."""
        pe = self.ws.paint
        sheet = pe.sheet if pe is not None else None
        if sheet is None:
            return
        tile = sheet.TILE * self._sheet_geom(sheet)[0]
        if kind == "down":
            self._sheet_press = [y, self._sheet_first, False]
            return
        p = self._sheet_press
        if p is None:
            return
        if kind == "drag":
            if abs(y - p[0]) >= tile // 2:
                p[2] = True
            if p[2]:
                self._sheet_first = p[1] - (y - p[0]) // tile
                self.ws.mark_dirty()
            return
        self._sheet_press = None
        if not p[2]:
            self.sheet_pick(x, y)

    def sheet_pick(self, x, y):
        """A tap on the pickers' sheet, in its coordinates: the sprite under
        it becomes the sprite and the pickers close."""
        pe = self.ws.paint
        sheet = pe.sheet if pe is not None else None
        if sheet is None:
            return
        k = self._sheet_geom(sheet)[0]
        m = 2 * self.layout.fs
        tile = sheet.TILE * k
        col = (x - m) // tile
        row = (y - m) // tile
        if 0 <= col < sheet.cols and 0 <= row < self._sheet_fit:
            pe.n = (self._sheet_first + row) * sheet.cols + col
            pe._clamp_size()
            self._pop = False
            self.ws.mark_dirty()
