# Map (grep -n a name to jump there):
#   ThemeDoc              the theme package open in the Editor: theme.json and its tiles
#   ThemeDoc.commit       what either tab holds, written through the look
#   ThemeDoc.begin_edit   an edit of the open slot: a smooth one turns to pixels first
#   ThemeDoc.step         undo and redo, the session's alone
#   ConfigLayout          the Config tab's geometry: the code view, its status line, the hints
#   ConfigLayer           the Config tab: theme.json in the Code tab's view, json mode
#   SpritesLayout         the Sprites tab's measures, a handheld's and a desk pane's
#   SpritesLayer          the Sprites page's host (editor_theme.py): the slot, the sheet, their keys
"""The Editor's theme mode (docs/history/look_2026-10.md step 33, GAPS 56): a theme
package opened in the console's Editor with two tabs and nothing a cart has
-- no Code, Blocks, Map, Music and no Play: an edit applies live, so there is
nothing to run. Appearance's Edit theme… opens it (`Appearance.edit_file`,
which makes `custom` from a seed first), `Text.edit_theme` hands it
to the Editor (`EditorApp.open_theme`), and Done (‹, K, Esc) brings the
Editor back to where it was opened from.

**Config** is the package's theme.json, opened indented, in the Code tab's
view (`ConfigLayer` is a `CodeLayer` whose language is JSON): the gutter,
the current line, long lines fading at the edge. Its saves are the look's
(`Appearance.file_check` gates, `file_write` writes, `file_saved` installs at
the next frame), never a project's: a theme package is flat data with no
`journal/`, so undo lives in the session and a save keeps no history.

**Sprites** is its icons as 16 x 16 tiles, one a slot (runtime/toolkit/iconsets.py's
SLOTS), the open slot at its zoom with the tools and the palette. A slot of
the theme's smooth set is its mask, drawn at the zoom in solid ink on a plain
ground; painting it replaces the slot with a pixel tile in the package's
sheet (`icons.moygfx`, the pixel set's shape) and names it in the look's
`icons.pixel_slots`, and undo brings the smooth one back. The sheet shows on
the live look as it is painted (`Appearance.preview_pixels`); a save writes
the sheet and theme.json together.

Keys: the page's (`editor_theme.py`): the arrows move the slot's cursor
and A paints where it stands, one past its edge moving focus on to the
sheet, the palette and the tools; in Sprites F and V flip and R rotates,
a keyboard steps the slot with Q and W (E on the T-Deck, where W moves),
Ctrl+Tab changes tab and Esc (B on a pad) is Done; in Config, where
letters type and the trackball is the caret's arrows, Mic opens the menu
on its Home row, which leaves saving as Done does, and the tabs are a
touch's. The desk shows both tabs as panes side by side
(runtime/editors/editor_desk.py's `theme` workspace), the tab following
the focused one (F6).
"""

import json as _json

import iconsets as _iconsets
import ui_font as _ui_font
import ui_draw as _ui_draw
from layers import Layer
import text_modes as _modes
import layout_base as _lb
from code_layer import CodeLayer
from chrome import CodeLayout
from editors_code import CodeEditor
from op_history import History, OpCodec
from editors_paint_map import PaintEditor
from view_host import PageHost, checker as _checker
import editor_theme
from moy_input import CTRL as _CTRL
from theme_custom import dumps as _dumps

TAB_CONFIG = "theme_config"
TAB_SPRITES = "theme_sprites"
# (tab, label, icon): the bar's two tabs, Config's the sliders as the regular
# Editor's Config is, Sprites' the face.
TABS = ((TAB_CONFIG, "Config", "sliders"), (TAB_SPRITES, "Sprites", "sprite"))
SHEET_FILE = "icons.moygfx"      # the package's sheet where its theme.json names none
INVALID = "INVALID"              # a refused save's badge (editor_handle's)
THEME_BYTES = 16384              # style.json's theme.bytes: the cap the status line names
FIRST_SLOT = 1                   # Sprites opens on Home
RED = 8                          # the pencil's first colour
# The slots' names as the sheet's captions say them.
_NAMES = {"wifi": "Wi-Fi", "wifi_off": "Wi-Fi off", "getcarts": "Get Carts",
          "cart_py": "Python cart", "cart_lua": "Lua cart", "cart_wasm": "Compiled cart",
          "cart_p8": "PICO-8 cart"}
# The page's tools (editor_theme.TOOLS) as PaintEditor's, and back.
_TOOL_OF = dict(pencil=PaintEditor.PEN, bucket=PaintEditor.FILL, line=PaintEditor.LINE,
                rect=PaintEditor.RECT, select=PaintEditor.SELECT)
_TOOL_ID = dict((v, k) for k, v in _TOOL_OF.items())


def slot_name(slot):
    """Icon slot `slot`'s caption ("Home", "Wi-Fi off")."""
    n = _iconsets.SLOTS[slot]
    got = _NAMES.get(n)
    if got is not None:
        return got
    n = n.replace("_", " ")
    return n[:1].upper() + n[1:]


def _dot():
    return " · " if _ui_font.print_symbols() else " - "


# -- the package ------------------------------------------------------------------


class _SlotOps(OpCodec):
    """The Sprites tab's undo codec: an op is one slot's tile before and
    after and whether it drew from the sheet (a smooth slot painted is
    pixels after, smooth before)."""

    def apply(self, doc, op):
        doc._put(op[0], op[2], op[4])

    def invert(self, doc, op):
        doc._put(op[0], op[1], op[3])


def _brings_back(hist, slot):
    """Whether undo brings slot `slot`'s smooth icon back: a step on the
    stack turned it to pixels."""
    for op in hist._undo:
        if op[0] == slot and not op[3] and op[4]:
            return True
    return False


class ThemeDoc:
    """`custom` open in the Editor: its theme.json as Config's buffer, its
    pixel tiles and the slots drawn from them as the Sprites tab's, and what
    each tab holds unwritten. `made` is the theme it was copied from just
    now, which Config's status line names once."""

    def __init__(self, ws, made=None):
        self.ws = ws
        look = ws.look
        self.name = look.theme_name
        self.note = None
        if made is not None:
            how = "is built in" if made in _builtin_names() else "stays as it is"
            self.note = "%s %s: this is your copy, %s" % (
                made[:1].upper() + made[1:], how, self.name)
        self.max_chars = look.max_chars
        text = look.file_text() or ""
        self.ed = CodeEditor(_modes.pretty(_modes.JSON, text)[:self.max_chars], 32, 12,
                             clip=getattr(ws, "clipboard", None))
        self.badge = ""
        self.saved = True              # Config's text is the file's
        self._wgen = look.file_gen
        # Sprites: a working copy of the theme's tiles and slot flags, shown
        # on the live look while it is open.
        src = look.pixel_sheet
        self.sheet = _iconsets.blank_sheet()
        if src is not None:
            n = min(len(src.pix), len(self.sheet.pix))
            self.sheet.pix[:n] = src.pix[:n]
        self.sheet.dirty = False
        flags = look.pixel_slots
        self.flags = bytearray(flags) if flags is not None else bytearray(len(_iconsets.SLOTS))
        self.pe = PaintEditor(self.sheet)
        self.pe.color = RED
        self.slot = FIRST_SLOT
        self.pe.n = self.slot
        self.cur = [0, 0]
        self.hist = History(self, _SlotOps(), max_undo=32, persisted=False)
        self.sprites_dirty = False
        self._pre = None               # the open edit's (slot, tile, flag)
        self._look_gen = look.look_gen
        look.preview_pixels(self.sheet, self.flags)

    # -- the slot ---------------------------------------------------------------

    def select(self, slot):
        """Open slot `slot` (the sheet's, wrapping)."""
        n = len(_iconsets.SLOTS)
        self.slot = slot % n
        self.pe.n = self.slot
        self.pe.sel = None
        self.ws.mark_dirty()

    def is_pixels(self, slot):
        return bool(self.flags[slot])

    def tile(self, slot):
        """Slot `slot`'s 256 palette indices in the sheet."""
        ox, oy = self.sheet.tile_origin(slot)
        out = bytearray(256)
        get = self.sheet.pget
        for y in range(16):
            for x in range(16):
                out[y * 16 + x] = get(ox + x, oy + y)
        return out

    def _set_tile(self, slot, pix):
        ox, oy = self.sheet.tile_origin(slot)
        put = self.sheet.pset
        for y in range(16):
            for x in range(16):
                put(ox + x, oy + y, pix[y * 16 + x])

    def _put(self, slot, pix, flag):
        """Undo's and redo's write: slot `slot` as `pix`, drawn from the
        sheet where `flag`."""
        self._set_tile(slot, pix)
        self.flags[slot] = 1 if flag else 0
        self.sprites_dirty = True
        self.select(slot)
        self.ws.look.preview_pixels(self.sheet, self.flags)

    def seed(self, slot):
        """The tile a smooth slot turns into when it is painted: the mask
        the slot shows at the zoom, each pixel it sets in the ink, so the
        first dot changes that dot and nothing else of the icon; the pixel
        set's own tile where the live set has no mask for it."""
        mask = self.mask(slot)
        if mask is None:
            sheet = _iconsets.pixel_sheet()
            if sheet is not None and slot < sheet.count:
                ox, oy = sheet.tile_origin(slot)
                out = bytearray(256)
                for y in range(16):
                    for x in range(16):
                        v = sheet.pget(ox + x, oy + y)
                        out[y * 16 + x] = v if v != sheet.clear else self.sheet.clear
                return out
        ink = 0 if self.ws.theme_colors.get("surface_light", False) else 7
        out = bytearray(bytes((self.sheet.clear,)) * 256)
        if mask is not None:
            for i in range(256):
                if mask[i]:
                    out[i] = ink
        return out

    def mask(self, slot):
        """The live set's 16 px mask of slot `slot` as 256 flags (1 where the
        canvas sets the pixel), or None where the set has none."""
        spec = self.ws.icon_spec()
        name = spec[1] if spec is not None and spec[0] == "smooth" else _iconsets.DEFAULT_SET
        return _iconsets.mask16(name, slot)

    # -- an edit ----------------------------------------------------------------

    def begin_edit(self):
        """An edit of the open slot starts: a smooth slot becomes the tile it
        is painted from, in the same undo step as the edit."""
        if self._pre is not None:
            return
        s = self.slot
        self._pre = (s, self.tile(s), self.flags[s])
        if not self.flags[s]:
            self._set_tile(s, self.seed(s))
            self.flags[s] = 1

    def end_edit(self):
        """The edit closes: one undo step where it changed the slot."""
        pre = self._pre
        if pre is None:
            return
        self._pre = None
        s, before, was = pre
        after = self.tile(s)
        if after == before and was == self.flags[s]:
            return
        self.hist.record((s, before, after, was, self.flags[s]))
        self.sprites_dirty = True
        self.ws.look.preview_pixels(self.sheet, self.flags)
        self.ws.history.edit_ms = None
        self.ws.bar_layer.invalidate()

    def state(self):
        """The open slot's state line: "Home · smooth", "Home · pixels ·
        Undo brings it back"."""
        s = self.slot
        if not self.flags[s]:
            return slot_name(s) + _dot() + "smooth"
        if _brings_back(self.hist, s):
            return slot_name(s) + _dot() + "pixels" + _dot() + "Undo brings it back"
        return slot_name(s) + _dot() + "pixels"

    # -- undo -------------------------------------------------------------------

    def history(self, tab, router):
        """The History the bar's pair walks on `tab`: Config's typing bursts
        (the router's, over this buffer), Sprites' slot steps."""
        if tab == TAB_SPRITES:
            return self.hist
        return router.code_op_history()

    def step(self, router, tab, redo):
        """Undo (or redo) one step of `tab`: True where one was taken."""
        if tab != TAB_SPRITES:
            router.close_code_burst()
        hist = self.history(tab, router)
        if hist is None:
            return False
        can = hist.can_redo() if redo else hist.can_undo()
        if not can or (hist.redo() if redo else hist.undo()) is None:
            return False
        if tab != TAB_SPRITES:
            self.ed.dirty = True
            self.saved = False
        self.ws.mark_dirty()
        self.ws.bar_layer.invalidate()
        return True

    def can(self, router, tab, redo):
        hist = self.history(tab, router)
        if hist is None:
            return False
        if redo:
            return hist.can_redo()
        return hist.can_undo() or (tab != TAB_SPRITES and router._code_burst_pending())

    # -- the saves --------------------------------------------------------------

    def clean(self, tab):
        if tab == TAB_SPRITES:
            return not self.sprites_dirty
        return not self.ed.dirty and self.saved

    def save_config(self, soft=False):
        """Write Config's text: (ok, badge). `soft` (the idle save) refuses a
        text the loader would not take and badges it; every other caller is
        an exit and writes it anyway, keeping the badge (a kid's text is
        theirs; the loader refuses it the next time the theme loads)."""
        look = self.ws.look
        self.ws.history.close_code_burst()
        body = self.ed.text()[:self.max_chars]
        good, why = _modes.check(_modes.JSON, body)
        out = body
        if good:
            good, why, out = look.file_check(body)
            if not good:
                out = body
        self.badge = why if good else (INVALID + " " + why).rstrip()
        if not good and soft:
            return (False, self.badge)
        err = look.file_write(out)
        if err is not None:
            return (False, str(err))
        self.ed.dirty = False
        self.saved = True
        self.note = None
        self._wgen = look.file_gen
        if good:
            look.file_saved(out)
        self.ws.mark_dirty()
        return (True, self.badge)

    def save_sprites(self):
        """Write the tiles and theme.json naming them and the slots drawn from
        them, in one write of the package: True when written."""
        if not self.sprites_dirty:
            return False
        look = self.ws.look
        if not self.clean(TAB_CONFIG):
            self.save_config()
        text = look.file_text()
        try:
            d = _json.loads(text) if text else None
        except ValueError:
            d = None
        if type(d) is not dict:
            return False
        name = d.get("icons")
        if type(name) is not str or not name.endswith(".moygfx"):
            name = SHEET_FILE
        d["icons"] = name
        lk = d.get("look")
        if type(lk) is not dict:
            lk = d["look"] = {}
        ic = lk.get("icons")
        if type(ic) is not dict:
            ic = lk["icons"] = {}
        slots = [_iconsets.SLOTS[i] for i in range(len(self.flags)) if self.flags[i]]
        if slots:
            ic["pixel_slots"] = slots
        else:
            ic.pop("pixel_slots", None)
        out = _dumps(d).decode()
        good, _why, body = look.file_check(out)
        if not good:
            return False
        err = look.file_write(body, {name: self.sheet.to_hex().encode()})
        if err is not None:
            self.badge = str(err)
            return False
        self.sprites_dirty = False
        self.sheet.dirty = False
        look.file_saved(body)
        look.file_gen += 1             # Config, with no edits, reads it again
        self.ws.mark_dirty()
        return True

    def save_tab(self, tab, soft=False):
        """Tab `tab`'s save: Config's (`soft`: the idle one, which refuses a
        text the loader would not take), Sprites'. True when it wrote."""
        if tab == TAB_SPRITES:
            return self.save_sprites()
        if self.clean(TAB_CONFIG):
            return False
        return self.save_config(soft)[0]

    def commit(self):
        """Every exit's hard commit: what either tab holds unwritten."""
        self.end_edit()
        if not self.clean(TAB_CONFIG):
            self.save_config()
        self.save_sprites()

    def follow(self):
        """A write made elsewhere (a Sprites save, the Appearance rows):
        Config with no edits reads the file again, and Sprites, with none,
        takes the look's slots again once it installs."""
        ws = self.ws
        look = ws.look
        if look.file_gen != self._wgen and self.clean(TAB_CONFIG):
            self._wgen = look.file_gen
            text = look.file_text()
            if text is not None:
                self.ed.set_text(_modes.pretty(_modes.JSON, text)[:self.max_chars])
                ws.history.drop_code_history()
        if look.look_gen != self._look_gen:
            self._look_gen = look.look_gen
            if not self.sprites_dirty and self._pre is None:
                flags = look.pixel_slots
                self.flags[:] = flags if flags is not None else bytes(len(self.flags))
                look.preview_pixels(self.sheet, self.flags)

    def status(self):
        """Config's status line: the copy's note once, else the file, its
        size against the cap and whether it is saved (or the badge)."""
        if self.note is not None:
            return self.note
        n = len(self.ed.text())
        kb = THEME_BYTES
        size = "%d.%d of %d KB" % (n // 1024, (n % 1024) * 10 // 1024, kb // 1024)
        tail = self.badge or ("Saved" if self.clean(TAB_CONFIG) else "Edited")
        return "theme.json" + _dot() + size + _dot() + tail


def _builtin_names():
    from chrome import THEME_NAMES
    return THEME_NAMES


# -- the hint strips ----------------------------------------------------------------


def _hints_for(tab):
    """Config's keys for the hint input (`ui_draw.hint_kind`): the T-Deck's
    are its own (moy_ui_parts.c's ACT_KEYS), a keyboard's its chords, none
    under touch alone."""
    inp = _ui_draw.hint_kind()
    if inp == "touch":
        return ()
    if inp == "tdeck":
        return ("menu", "Home")     # the menu opens on its Home row
    if inp == "pad":
        return ("back", "Done")
    return ("Ctrl Tab", "Sprites", "back", "Done")


# -- Config -------------------------------------------------------------------------


class ConfigLayout(CodeLayout):
    """The Code tab's geometry for Config: no symbol keys, the status line
    over the hint strip where the input has keys."""

    def __init__(self, w, h, font_scale=1, chrome_scale=None, keys=True):
        CodeLayout.__init__(self, w, h, font_scale, chrome_scale, symbols=False)
        fs = self.fs
        desk = _lb.metric_class() == _lb.DESK
        self.keys = keys
        hint_h = (max(34 // _lb.render_scale(), 18 * fs) if desk else 22 * fs) \
            if keys and not desk else 0
        self.hints = (self.cx, self.cy + self.ch - hint_h, self.cw, hint_h) if hint_h else None
        band = self.status_band[3]
        y = self.cy + self.ch - hint_h - band
        self.status_band = (self.cx, y, self.cw, band)
        self.status_text = (self.status_text[0], y, self.status_text[2], band)
        self.rows = max(4, (y - self.y0) // self.lh)


class ConfigLayer(CodeLayer):
    """The Config tab: the package's theme.json in the Code tab's view, its
    language JSON, the theme's status line under it. The buffer is the open
    ThemeDoc's (`ws.editor` while the theme mode is open), its keys the Code
    tab's less what JSON has no use for (completion, Go to, the scripts)."""
    # Esc closes theme mode back to Appearance (its handle_input), not
    # the Editor's leave.
    ESC_LEAVES = False

    id = TAB_CONFIG
    PAGE = "config_page"

    def __init__(self, ws, names):
        CodeLayer.__init__(self, ws, names)
        self.layout = None
        self._args = None

    def relayout(self, w, h, fs, cs=None):
        self._args = (w, h, fs, cs)
        self.layout = ConfigLayout(w, h, fs, cs, keys=_ui_draw.hint_kind() != "touch")

    def _sync(self):
        """Lay the tab out where nothing has (a desk pane lays it out at the
        pane's size, `EditorDesk._in_pane`), and again on a handheld where the
        input moved between touch and keys (the hint strip)."""
        ws = self.ws
        if self.layout is None:
            sc = ws.sys_canvas
            self.relayout(sc.w, sc.h, ws.look.effective_font_scale(),
                          ws.look.effective_chrome_scale())
        elif (self._args is not None and ws.editor_app._desk() is None
              and self.layout.keys != (_ui_draw.hint_kind() != "touch")):
            self.relayout(*self._args)

    def _doc(self):
        return self.ws.editor_app.theme

    def _lang(self):
        return "json"

    def wants_symbols(self):
        return False

    def wants_tools(self):
        return False

    def _recheck_err(self):
        self.ws.crash_popup = None

    def open_scripts(self):
        pass

    def _with(self, fn, *args):
        """Run `fn` with the Code tab's layout handle on Config's and the
        buffer the open theme's: what every CodeLayer verb reads."""
        ws = self.ws
        doc = self._doc()
        if doc is None:
            return None
        self._sync()
        lay = self.layout
        ed = doc.ed
        if (ed.COLS, ed.ROWS) != (lay.cols, lay.rows):
            ed.set_view_size(lay.cols, lay.rows)
        old_lay, old_ed = ws.code_layout, ws.editor
        ws.code_layout, ws.editor = lay, ed
        try:
            return fn(*args)
        finally:
            ws.code_layout = old_lay
            if ws.editor is ed:
                ws.editor = old_ed

    def draw(self, dt):
        doc = self._doc()
        if doc is not None:
            doc.follow()
        self._with(CodeLayer.draw, self, dt)

    def _frame_keys(self):
        return _hints_for(TAB_CONFIG)

    def _note(self):
        """The theme's status line."""
        doc = self._doc()
        if doc is None:
            return ("", False)
        return (doc.status(), doc.note is not None)

    def handle_input(self, i):
        doc = self._doc()
        if doc is None:
            return True
        k = i.typed
        app = self.ws.editor_app
        if k:
            mods = getattr(i, "mods", 0)
            if k == 0x09 and mods & _CTRL:
                app.theme_tab(TAB_SPRITES)
                return True
            if k == 27 and not (self._find_open or self._cmp_open or self._jump_open):
                self.ws.defer(app.close_theme)
                return True
        if _ui_draw.input_kind() == "pad" and i.pressed("b"):
            self.ws.defer(app.close_theme)          # a gamepad types nothing here
            return True
        got = self._with(CodeLayer.handle_input, self, i)
        if k and doc.ed.dirty:
            doc.saved = False
            doc.note = None
        return got if got is not None else True

    def handle_pointer(self, px, py, click):
        return self._with(CodeLayer.handle_pointer, self, px, py, click)

    def nav(self, dx, dy, select=None):
        doc = self._doc()
        if doc is not None:
            doc.ed.move(dy, dx, select)


def _contrast(th):
    return bool(th.get("contrast", False))


# -- Sprites ------------------------------------------------------------------------


class SpritesLayout:
    """The Sprites tab's measures (the mockups' `theme_sprites` and
    `theme_desk`), the page's (`editor_theme.py`) to lay out: the open
    slot's zoom (`cell`) and its canvas's width (`grid_w`, the margin, the
    slot and the gap to the sheet), the sheet's tiles, their pitch and
    rows, a palette cell's side and a tool's pitch. A handheld's is the
    T-Deck's and, under touch or the tap floor, the S3's (28 px slots,
    swatches and tools, the sheet paged); a desk pane's names every slot
    under its tile."""

    def __init__(self, w, h, font_scale=1, chrome_scale=None, keys=True):
        base = _lb.LayoutBase(w, h, font_scale, chrome_scale=chrome_scale)
        self.cx, self.cy, self.cw, self.ch = base.cx, base.cy, base.cw, base.ch
        fs = self.fs = base.fs
        self.keys = keys
        self.desk = desk = _lb.metric_class() == _lb.DESK
        self.pane = _lb.pane()
        # the tap floor's (the S3's chrome scale over its font scale) or a
        # touch input's: 28 px slots, swatches and tools, the sheet paged
        self.touch = touch = not keys or base.cs > base.fs
        self.unit = 1 if desk else fs
        if desk:
            self.cell, self.mx, self.my, gap = 16, 16, 14, 24
            self.tsz, self.sw = 36, 20
            # a slot's pitch holds its name at the font's scale
            self.tile, self.pitch, self.pitch_y = 32, 64 * fs, 40 + 16 * fs
            self.legend_h = 10 + 10 * fs
        else:
            self.cell = (13 if touch else 9) * fs
            self.mx = self.my = 8 * fs
            gap = 12 * fs
            self.tsz = (30 if touch else 22) * fs
            self.sw = (31 if touch else 12) * fs
            step, tc = ((32, 28) if touch else (19, 16))
            self.pitch = self.pitch_y = step * fs
            self.tile = tc * fs
            self.legend_h = 16 * fs
        self.grid_w = self.mx + 16 * self.cell + gap
        # the handheld's column beside the slot: the sheet's rows (four at
        # most) and the slot's name and state lines (`lines`) its room holds
        # over the palette, the pager under touch; a desk's rows are what its
        # pane holds (`sheet`)
        self.rows, self.lines = 4, 2
        # the slot's canvas: as tall as its zoom, short of the tools under it
        # (a stop whose foot touches the next row's loses the arrows to it)
        self.grid_h = self.my + 16 * self.cell + 4
        if not desk:
            row = 22 * fs
            room = self.ch - row - (row if keys else 0)
            self.grid_h = min(self.grid_h, room - fs)
            avail = room - 2 * self.sw - (row if touch else 0) - self.legend_h - self.my
            while self.rows > 1 and self.rows * self.pitch_y + self.lines * row > avail:
                if self.lines:
                    self.lines -= 1
                else:
                    self.rows -= 1

    def sheet(self, w, h):
        """The sheet's (columns, rows) in a canvas w x h."""
        cols = max(1, (w - 4 * (1 if self.desk else self.fs)) // self.pitch)
        if not self.desk:
            return cols, self.rows
        return cols, max(1, min(6, (h - self.my - self.legend_h) // self.pitch_y))


# The band's items before its way back (a desk pane's: the slot's keys and the next pane)
_BAND_TDECK = ("flip", "Flip", "rotate", "Rotate")
_BAND_KEYS = ("Q W", "Icon", "flip", "Flip", "rotate", "Rotate")
_BAND_PANE = ("Q W", "Icon", "F6", "Next pane")


class SpritesLayer(PageHost, Layer):
    """The Sprites tab's content layer (system domain, as the sprite
    tab's), the host of its page (`editor_theme.py`)."""
    # Esc closes theme mode back to Appearance (its handle_input), not
    # the Editor's leave.
    ESC_LEAVES = False
    KEYS_IDLE = True                # its keys move the cursor and act on a press

    id = TAB_SPRITES
    domain = "system"
    def ball_steps(self):
        """The trackball points at the icon and its colours."""
        return False

    def __init__(self, ws, names):
        PageHost.__init__(self, ws, names, TAB_SPRITES, editor_theme.theme_page)
        self.layout = None
        self._args = None
        self._drag = None
        self._shape0 = None
        self._band = None               # the band's items as handed the page
        self._cell = 1                  # the slot's zoom as its canvas drew it last
        self._sheet_r = None            # ...and the sheet's

    def relayout(self, w, h, fs, cs=None):
        self._args = (w, h, fs, cs)
        self.layout = SpritesLayout(w, h, fs, cs, keys=_ui_draw.hint_kind() != "touch")

    def _lay(self):
        """Lay the tab out where nothing has (a desk pane lays it out at the
        pane's size, `EditorDesk._in_pane`), and again on a handheld where the
        input moved between touch and keys."""
        ws = self.ws
        if self.layout is None:
            sc = ws.sys_canvas
            self.relayout(sc.w, sc.h, ws.look.effective_font_scale(),
                          ws.look.effective_chrome_scale())
        elif (self._args is not None and ws.editor_app._desk() is None
              and self.layout.keys != (_ui_draw.hint_kind() != "touch")):
            self.relayout(*self._args)

    def _doc(self):
        return self.ws.editor_app.theme

    # -- the page ------------------------------------------------------------

    def _sync(self):
        """The open theme's state the page shows, handed to its `sync`
        hook where it moved."""
        doc = self._doc()
        lay = self.layout
        u = lay.unit
        per, first = self._page_of()
        n = len(_iconsets.SLOTS)
        name = status = ""
        tool, color = "pencil", 0
        if doc is not None:
            name = slot_name(doc.slot)
            st = doc.state()
            status = st if lay.pane else st.split(_dot(), 1)[1] if _dot() in st else st
            tool = _TOOL_ID.get(doc.pe.tool, "pencil")
            color = doc.pe.color & 15
        pages = max(1, -(-n // per))
        vals = (lay.pane, lay.touch and not lay.desk, lay.lines > 0, lay.lines > 1, name, status,
                "%d / %d" % (first // per + 1, pages), first == 0, first + per >= n, tool, color,
                lay.grid_w // u, lay.grid_h // u, (lay.my + lay.rows * lay.pitch_y + lay.legend_h) // u, lay.tsz // u,
                lay.sw // u, 60 if lay.pane else 18, 34 if lay.pane else 18, 4)
        self.push(vals)

    def _page_of(self):
        """(slots a page of the sheet shows, the first it shows)."""
        lay = self.layout
        r = self._sheet_r
        cols, rows = lay.sheet(r[2], r[3]) if r is not None else (1, lay.rows)
        per = cols * rows
        doc = self._doc()
        slot = doc.slot if doc is not None else 0
        if lay.desk:
            return per, max(0, (slot // cols - rows + 1)) * cols
        return per, (slot // per) * per

    def draw(self, dt):
        doc = self._doc()
        self._lay()
        if doc is not None:
            doc.follow()
        pg = self._page()
        lay = self.layout
        band = (_BAND_PANE if lay.pane else _BAND_KEYS) if _ui_draw.hint_kind() == "keys" else \
            _BAND_TDECK if _ui_draw.hint_kind() == "tdeck" else ()
        if band is not self._band:
            self._band = band
            pg.band_extra(band)
        pg.band = lay.keys
        PageHost.draw(self, dt)

    def act(self, verb):
        """A tool picked, or the sheet's page before or after."""
        doc = self._doc()
        if doc is None:
            return
        if verb in _TOOL_OF:
            doc.pe.set_tool(_TOOL_OF[verb])
            self._due = "home"              # the keys go back to the slot
        else:
            per, first = self._page_of()
            n = len(_iconsets.SLOTS)
            doc.select(max(0, first - per) if verb == "sprev" else min(n - 1, first + per))
        self.ws.mark_dirty()

    def set_color(self, c):
        doc = self._doc()
        if doc is not None:
            doc.pe.color = c
            self.ws.mark_dirty()

    # -- the slot ------------------------------------------------------------

    def grid_pointer(self, kind, x, y):
        """A press on the slot, its drag and its release, in its coordinates."""
        doc = self._doc()
        lay = self.layout
        if doc is None:
            return
        c = self._cell
        cx, cy = (x - lay.mx) // c, (y - lay.my) // c
        inside = 0 <= cx < 16 and 0 <= cy < 16
        if kind == "down":
            if inside:
                self._press(doc, cx, cy)
        elif kind == "drag":
            if inside and (self._drag is not None or self._shape0 is not None):
                self._move(doc, cx, cy)
        elif self._drag is not None or self._shape0 is not None:
            self._release(doc)
        self.ws.mark_dirty()

    def grid_keys(self, i):
        """The slot's keys while it holds focus: the arrows move the
        cursor (one past its edge is the page's), A paints where it stands."""
        doc = self._doc()
        if doc is None:
            return False
        dx = i.steps("right") - i.steps("left")
        dy = i.steps("down") - i.steps("up")
        took = False
        if dx or dy:
            x, y = doc.cur[0] + dx, doc.cur[1] + dy
            if 0 <= x < 16 and 0 <= y < 16:
                doc.cur[0], doc.cur[1] = x, y
                took = True
        if i.pressed("a") or i.pressed("run"):
            self._press(doc, doc.cur[0], doc.cur[1])
            self._release(doc)
            took = True
        if took:
            self.ws.mark_dirty()
        return took

    def draw_grid(self, cv, x, y, w, h):
        """The open slot at its zoom: in pixels its tile's colours on the grey
        checker; still smooth its mask in solid ink on a plain ground, a cell
        set where the canvas would set it. The centre lines, then the
        cursor's ring."""
        doc = self._doc()
        if doc is None:
            return
        th = self.ws.theme_colors
        lay = self.layout
        gx, gy = x + lay.mx, y + lay.my
        c = self._cell = max(1, min(lay.cell, (w - 2 * lay.mx) // 16, (h - lay.my - 2) // 16))
        span = 16 * c
        s = doc.slot
        line = th["border"]
        if doc.is_pixels(s):
            g = self.ws.look.live.fixed[:2]
            _checker(cv, gx, gy, span, span, c, g[0], g[1])
            ox, oy = doc.sheet.tile_origin(s)
            clear = doc.sheet.clear
            get = doc.sheet.pget
            for yy in range(16):
                for xx in range(16):
                    v = get(ox + xx, oy + yy)
                    if v != clear:
                        cv.rect(gx + xx * c, gy + yy * c, c, c, v)
        else:
            cv.rect(gx, gy, span, span, th["surface"])
            cv.rectb(gx, gy, span, span, line)
            mask = doc.mask(s)
            if mask is not None:
                ink = th["ink"]
                for yy in range(16):
                    row = yy * 16
                    for xx in range(16):
                        if mask[row + xx]:
                            cv.rect(gx + xx * c, gy + yy * c, c, c, ink)
        cv.rect(gx + 8 * c, gy, 1, span, line)
        cv.rect(gx, gy + 8 * c, span, 1, line)
        pe = doc.pe
        if pe.sel is not None:
            x0, y0, x1, y1 = pe.sel
            cv.rectb(gx + x0 * c, gy + y0 * c, (x1 - x0 + 1) * c, (y1 - y0 + 1) * c, th["value"])
        if lay.keys:
            keyline = self.ws.look.live.fixed[2]
            bx, by = gx + doc.cur[0] * c, gy + doc.cur[1] * c
            box = (bx - 1, by - 1, c + 2, c + 2)
            cv.rectb(box[0], box[1], box[2], box[3], keyline)
            cv.rectb(box[0] - 1, box[1] - 1, box[2] + 2, box[3] + 2, th["surface"])
            _ui_draw.focus(cv, th, (box[0] - 1, box[1] - 1, box[2] + 2, box[3] + 2),
                           "cell", ring=True)

    # -- the sheet -----------------------------------------------------------

    def sheet_tap(self, x, y):
        """A tap on the sheet, in its coordinates: its slot opens."""
        doc = self._doc()
        r = self._sheet_r
        if doc is None or r is None:
            return
        lay = self.layout
        cols, rows = lay.sheet(r[2], r[3])
        cx, cy = x // lay.pitch, (y - lay.my) // lay.pitch_y
        per, first = self._page_of()
        s = first + cy * cols + cx
        if 0 <= cx < cols and 0 <= cy < rows and s < len(_iconsets.SLOTS):
            doc.select(s)
            self.ws.mark_dirty()

    def sheet_keys(self, i):
        """The sheet's keys while it holds focus: the arrows move along it,
        up and down past the page shown to the page before or after; one
        past its edge is the page's."""
        doc = self._doc()
        r = self._sheet_r
        if doc is None or r is None:
            return False
        dx = i.steps("right") - i.steps("left")
        dy = i.steps("down") - i.steps("up")
        if not (dx or dy):
            return False
        cols = self.layout.sheet(r[2], r[3])[0]
        k = doc.slot
        x = k % cols + dx
        s = k + dx + dy * cols
        if not (0 <= x < cols and 0 <= s < len(_iconsets.SLOTS)):
            return False
        doc.select(s)
        self.ws.mark_dirty()
        return True

    def draw_sheet(self, cv, x, y, w, h):
        """The sheet: a smooth slot as the set draws it, a slot in pixels
        from the tiles with a `value` dot in its corner; the open one marked
        (a ring on the desk, every slot named under its tile); the legend
        under it: a pixel tile's dot is "pixel art"."""
        self._sheet_r = (x, y, w, h)
        doc = self._doc()
        if doc is None:
            return
        ws = self.ws
        th = ws.theme_colors
        lay = self.layout
        cols, rows = lay.sheet(w, h)
        per, first = self._page_of()
        n = len(_iconsets.SLOTS)
        t = lay.tile
        ink = th["ink"]
        dot = th["value"] if not _contrast(th) else th["ink"]
        cap = _ui_draw.font("caption")
        y0 = y + lay.my
        for k in range(per):
            s = first + k
            if s >= n:
                break
            sx, sy = x + (k % cols) * lay.pitch, y0 + (k // cols) * lay.pitch_y
            if lay.desk:
                sx += (lay.pitch - t) // 2
            if s == doc.slot:
                _ui_draw.focus(cv, th, (sx - 2, sy - 2, t + 4, t + 4), "cell", ring=lay.desk)
            kind = _iconsets.SLOTS[s]
            if doc.is_pixels(s):
                img = doc.sheet.tile_image(s, doc.sheet.clear)
                sc = max(1, t // 16)
                cv.spr(img, sx + (t - 16 * sc) // 2, sy + (t - 16 * sc) // 2, sc)
                d = 5 if lay.desk else 4 if t >= 28 else 3
                cv.rrect(sx + t - d - (0 if lay.desk else 1), sy, d, d, d // 2 + 1, dot)
            else:
                box = 16 * max(1, t // 16) if lay.desk else 16 * lay.fs
                ox = sx + (t - box) // 2
                oy = sy + (t - box) // 2
                if not ws.draw_icon(kind, (ox, oy, box, box), ink, cv):
                    ws.icon(kind, ox, oy, cv, ink=ink)
            if lay.desk:
                was = _ui_draw.print_font(cap[0])
                try:
                    name = _ui_draw.print_cut(slot_name(s), lay.pitch - 4, 1)
                    nw = _ui_draw.print_width(name, 1)
                    nx = sx - (lay.pitch - t) // 2 + (lay.pitch - nw) // 2
                    cv.print(name, nx, sy + t + 6, ink if s == doc.slot else th["ink_dim"], 1)
                finally:
                    _ui_draw.print_font(was)
        f = 1 if lay.desk else lay.fs
        d = 5 if lay.desk else 4 * f
        lx = x + (4 if lay.desk else 0)
        ly = y0 + rows * lay.pitch_y + 2 * f
        ty = ly + 6 * f - cap[3] * f // 2 - 1
        cv.rrect(lx, ty + cap[3] * f // 2 - d // 2 + 2, d, d, d // 2 + 1, dot)
        was = _ui_draw.print_font(cap[0])
        try:
            cv.print("pixel art", lx + (10 if lay.desk else 8 * f), ty, th["ink_dim"], 1)
        finally:
            _ui_draw.print_font(was)

    def draw_preview(self, cv, x, y, w, h):
        """The open slot as the shell draws it: at 1x (on the desk 1x and 2x)."""
        doc = self._doc()
        if doc is None:
            return
        th = self.ws.theme_colors
        kind = _iconsets.SLOTS[doc.slot]
        if self.layout.pane:
            self._slot_at(cv, th, doc, kind, x, y + (h - 16) // 2, 16)
            self._slot_at(cv, th, doc, kind, x + 26, y + (h - 32) // 2, 32)
        else:
            self._slot_at(cv, th, doc, kind, x + (w - 16) // 2, y + (h - 16) // 2, 16)

    def _slot_at(self, cv, th, doc, kind, x, y, box):
        ws = self.ws
        s = _iconsets.SLOT[kind]
        if doc.is_pixels(s):
            img = doc.sheet.tile_image(s, doc.sheet.clear)
            cv.spr(img, x, y, max(1, box // 16))
            return
        if not ws.draw_icon(kind, (x, y, box, box), th["ink"], cv):
            ws.icon(kind, x, y, cv, ink=th["ink"])

    # -- input -------------------------------------------------------------------

    def handle_input(self, i):
        ws = self.ws
        doc = self._doc()
        if doc is None:
            return True
        app = ws.editor_app
        k = i.typed
        if k:
            mods = getattr(i, "mods", 0)
            if k == 0x09 and mods & _CTRL:
                app.theme_tab(TAB_CONFIG)
                return True
            if k == 27:
                ws.defer(app.close_theme)
                return True
            if k == 0x1A:
                ws.history.undo()
                return True
            if k == 0x19:
                ws.history.redo()
                return True
            if k in (0x71, 0x51):
                doc.select(doc.slot - 1)
                return True
            if k in (0x77, 0x57, 0x65, 0x45):
                doc.select(doc.slot + 1)
                return True
            op = _KEY_OPS.get(k)
            if op is not None:
                self._op(doc, op)
                return True
        if i.pressed("b"):
            ws.defer(app.close_theme)
            return True
        self._lay()
        self._page().keys(i)
        return True

    def handle_pointer(self, px, py, click):
        ws = self.ws
        if click and ws.bar_layer.handle_bar_tap("menu", px, py):
            return True
        if self._doc() is None:
            return True
        self._lay()
        PageHost.handle_pointer(self, px, py, click)
        return True

    def _op(self, doc, op):
        pe = doc.pe
        doc.begin_edit()
        if op == "fliph":
            pe.flip_h()
        elif op == "flipv":
            pe.flip_v()
        elif op == "rot":
            pe.rotate()
        doc.end_edit()
        self.ws.mark_dirty()

    def _press(self, doc, x, y):
        pe = doc.pe
        doc.cur[0], doc.cur[1] = x, y
        doc.begin_edit()
        if pe.tool == PaintEditor.PEN:
            pe.paint(x, y)
            self._drag = (x, y)
        elif pe.tool == PaintEditor.FILL:
            pe.fill(x, y)
        else:
            self._shape0 = (x, y)
        self.ws.look.pixels_moved()

    def _move(self, doc, x, y):
        pe = doc.pe
        doc.cur[0], doc.cur[1] = x, y
        if pe.tool == PaintEditor.PEN and self._drag is not None:
            for px, py in _line(self._drag[0], self._drag[1], x, y):
                pe.paint(px, py)
            self._drag = (x, y)
            self.ws.look.pixels_moved()

    def _release(self, doc):
        pe = doc.pe
        if self._shape0 is not None:
            x0, y0 = self._shape0
            x1, y1 = doc.cur
            if pe.tool == PaintEditor.SELECT:
                pe.set_selection(x0, y0, x1, y1)
            else:
                pe.stamp_shape(x0, y0, x1, y1)
        self._drag = None
        self._shape0 = None
        doc.end_edit()


def _line(x0, y0, x1, y1):
    """The cells from (x0, y0) to (x1, y1), Bresenham's."""
    out = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        out.append((x0, y0))
        if x0 == x1 and y0 == y1:
            return out
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


# PICO-8's sprite keys (paint_layer's): F and V flip, R rotates.
_KEY_OPS = {ord("f"): "fliph", ord("F"): "fliph", ord("v"): "flipv", ord("V"): "flipv",
            ord("r"): "rot", ord("R"): "rot"}
