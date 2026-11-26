# Map (grep -n a name to jump there):
#   -- bar geometry           the bar's constants (console.py imports them back)
#   ZoneLook                  the look of a row an app lends the bar (BarZone's)
#   BarLayer                  the theme layout's bars: cells, strips, clock, taps
#   BarLayer.invalidate       repaint the cached bar strips
#   BarLayer.bar_rects        where the bars are on a surface; content_rect, what they leave
#   BarLayer.cell             where a widget is: its bar and its cell
#   BarLayer._draw_bar        one bar's cached strip at its rect
#   BarLayer.redraw_clock     repaint just the clock cell
#   BarLayer.handle_bar_tap   the bars' tap slice, shared by every surface
"""The shell's bars (#46; docs/theme_and_shell_2026-11.md §8.2, §8.5): every bar the
theme's layout resolves to, on any edge, each a cached strip of widget cells
(`shell_layout.pack`), extracted from Workstation (runtime/shell/console.py) as its
own surface -- docs/history/shell_layers_refactor_v1.md.

This module is the SINGLE SOURCE of the bar geometry constants (`_STATUS_H`,
`_BAR_*`). They're consumed BOTH here (BarLayer's draw + hit-testing) AND by
console.py's own chrome (the `Layout` class + a few derived constants), so rather
than duplicate them (drift), console.py imports them back from here (re-exported
under the same names) -- the same pattern block_editor_ui.py uses for its `_BLK_*`.

The BOTTOM DOCK this module used to own is GONE (2026-08-21): a six-slot
HOME/CODE/DRAW/MAP/RUN/SET tool switcher left over from the pre-2026-07 shell,
whose slots still routed into that shell's entry points. The 2026-07 shell
navigates by the zoned bar, the home's tabs and the context-X, and the launcher had
already stopped drawing the dock in #46 -- Settings was its last caller, on the
fullscreen tiers only (the windowed WM suppressed it). Do not re-grow it;
`tests/test_desktop_shell.py::test_the_pre_2026_07_bottom_dock_is_gone` is the
ratchet.

`BarLayer` reaches everything else through its `self.ws` back-ref; the chrome's
chip (`mini_btn`) is this module's function. Only
`NAMES` (palette) is injected at construction -- the same circular-import dodge the
other extracted UIs use, since console.py builds the one BarLayer instance a
Workstation holds; the rect hit-test `_in` is widgets', imported directly. The trivial time helpers `_ticks_ms`/
`_ticks_diff` are duplicated here (time-only) for the clock.
"""
import wallclock as _wc
from layout_base import (BAR_ROWS, bar_rects_of, bars_in_force,
                         content_of)
from shell_layout import pack as _pack, cell_of as _cell_of, without as _without


# The clock's text while the wall clock does not hold real time, and its date.
UNSYNCED = "--:--"
_NO_DATE = (0, 0, 0)


# -- bar geometry (single source; console.py imports these back) --------------
# Every rect here is in BAR coordinates (row 0 is the bar's first row, wherever
# BarLayer places the bar). The bars on the fixed 320x240 GAME canvas take these
# fixed constants; the launcher/Settings bar reflows via Layout on the SYSTEM
# canvas. The hamburger (≡) is the LEFT-MOST icon (slot 0); the tool switchers
# HOME/EDIT/PAINT/MAP/BLOCKS/MUSIC follow one stride apart.
_BAR_ICON = 16              # icon sprite side (16x16, from the IconSheet)
_BAR_GAP = 2               # px between adjacent bar icons
_BAR_STRIDE = _BAR_ICON + _BAR_GAP        # 18: left-edge step between icons
_BAR_Y = 1                 # icons sit 1px down in the 18px bar (1px top/bottom margin)
# Cached bar strips kept per `where`, one per destination canvas. 2 covers the
# windowed WM's root-canvas / window-buffer alternation; each costs cv.w * bar_h * 2
# bytes (~36KB at 1024 wide), so this is a small, bounded PSRAM trade for not
# rebuilding the strip on every switch.
_BAR_STRIP_SLOTS = 2


def _meets(a, b):
    """Whether rects `a` and `b` overlap."""
    return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
            and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


def _union(a, b):
    """The least rect holding rects `a` and `b` (`a` None: `b`)."""
    if a is None:
        return b
    x0 = min(a[0], b[0])
    y0 = min(a[1], b[1])
    return (x0, y0, max(a[0] + a[2], b[0] + b[2]) - x0, max(a[1] + a[3], b[1] + b[3]) - y0)


def _cut(a, b):
    """Rect `a` inside rect `b` (empty where they do not meet)."""
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    return (x0, y0, min(a[0] + a[2], b[0] + b[2]) - x0, min(a[1] + a[3], b[1] + b[3]) - y0)


def _release_layer(lay):
    """A strip is a root-canvas layer, off the gc heap on a board (nothing
    collects it): an evicted or outgrown strip is given back here, or every
    window the desk opens leaks its bar strip (~80KB a round on the Guition
    P4, 2026-09-09). Probed: a recording tier's layer has no release."""
    rel = getattr(lay, "release", None)
    if rel is not None:
        rel()
_STATUS_H = BAR_ROWS    # the bar's rows (16px icons + 1px top/bottom margin)
_BAND_TAP = 36          # a tool's compact band at its least: the chevron's tap

# -- today's bar on the fixed 320x240 GAME canvas: the cells
# `shell_layout.pack` gives the default layout there (a running tool/app's
# strip, `BarLayer._zone_is_game`; tests/test_bars.py holds the packing to
# them): the battery hard right.
_ZONE_BATT = (320 - 2 - _BAR_ICON, _BAR_Y, _BAR_ICON, _BAR_ICON)
# Wi-Fi a status gap from the battery (shell_layout.pack's at font scale 1).
_ZONE_WIFI = (_ZONE_BATT[0] - _BAR_ICON - 4, _BAR_Y, _BAR_ICON, _BAR_ICON)
_ZONE_GEAR = (_ZONE_WIFI[0] - _BAR_STRIDE, _BAR_Y, _BAR_ICON, _BAR_ICON)
# The context X (tap to exit the active app).
_ZONE_CONTEXT_X = (_ZONE_GEAR[0] - _BAR_STRIDE, _BAR_Y, _BAR_ICON, _BAR_ICON)
_ZONE_CLOCK = (_ZONE_CONTEXT_X[0] - 2 - 5 * 8, 0, 5 * 8, 18)
_ZONE_LEFT_GAME = (2, _BAR_Y, _ZONE_CLOCK[0] - 4, _BAR_ICON)     # the app-lent rect

# The status widgets that give their room to a zone too narrow for what its
# owner draws (`BarLayer._make_room`), in the order they give it: the battery
# first, then the Wi-Fi. The clock never does.
_YIELD = ("battery", "wifi")
# Under this charge the bar's battery is drawn low, all in the danger ink;
# its exact level is Settings' (owner, 2026-11-05).
LOW_BATTERY = 15


from ticks import _ticks_ms, _ticks_diff
from widgets import rect_in as _in
import chrome_ops as _ch
import moy_ui as _C
import ui_draw as _ui_draw
import layout_base as _layout_base
import iconsets as _iconsets
import bar_engine as _bar_engine
import bar_ui as _bar_ui
from shell_layout import ITEMS as _SL_ITEMS, RING_ROOM as _RING_ROOM
from status_items import ITEMS as _ITEMS, PAUSED as _PAUSED, ERROR as _ERROR


def _bar_text_w(s):
    """A bar `text` widget's width at scale 1, in the print font it draws in."""
    return _ui_draw.print_width(s, 1)


# The band's edge line faces the content (ui.frame_band's `side`).
_BAND_SIDE = {"top": _ui_draw.BAND_BOTTOM, "bottom": _ui_draw.BAND_TOP,
              "left": _ui_draw.BAND_RIGHT, "right": _ui_draw.BAND_LEFT}
# The OS widgets a bar paints itself (the zone is its owner's, the chips the
# WM's, a spacer nothing).
_PAINTED = ("menu", "close", "wifi", "battery", "clock", "title", "text", "separator",
            "status")
# The widgets whose tap is the OS's (§4): the system menu, the X, and the
# three that open a component (§8).
_TAPPED = ("clock", "menu", "wifi", "battery", "close", "status")
# The widgets a handheld's status cluster joins into one focus stop, which
# opens the control center (the `battery` widget's component).
_CLUSTER = ("status", "wifi", "battery")
# The focus items that are stops of the bar page on a bar it draws.
_PAGE_STOPS = ("menu", "chip", "status", "wifi", "battery", "clock")
# A bar's titles where no running cart names one.
_TITLES = {"projects": "PROJECTS", "settings": "SETTINGS", "desk": "DESK",
           "webconsole": "Web console", "tasks": "Tasks"}
# _cart_bar_key's fields every bar folds, and the ones a widget adds (field 2:
# whether focus marks draw, which the lent zone's current tab shows).
_KEY_ALWAYS = (0, 3, 4, 10, 12)
_KEY_OF = {"clock": (1,), "zone": (2, 5, 6, 8, 9), "title": (6, 8), "wifi": (7,),
           "menu": (11,), "status": (13,), "battery": (13,), "chips": (14,)}
_KEY_N = 15                 # 12: the item keys focus (`focus_item`); 13: the status
                            # items and the selected widget (`_status_key`); 14: the
                            # taskbar chips (the window manager's `chips_gen`)
_KEY_ALL = (1 << _KEY_N) - 1
_KEY_UNDO = 1 << 9          # drawn only by the Editor's zone ("menu")
_KEY_CHIPS = 1 << 14
# the fields drawn in a part of the bar: the zone, the pill, the chips
_KEY_PARTS = (1 << 6) | (1 << 12) | _KEY_CHIPS


# A look leaf no theme sets (moy_theme.h's MOY_THEME_NONE).
_NONE = -2147483648


def _paged(edge, cells):
    """Whether the bar page draws a bar's widgets (`_page_draw`): a top or
    bottom bar whose cells are the page's in its order, some of
    `bar_engine.LEFT` from its start and of its RIGHT from its end, its
    zone among them (`bar_engine.placed`, read off the packing)."""
    if edge not in ("top", "bottom"):
        return False
    zone = False
    side = 0
    for name, _r, _t, slot in cells:
        if name in _bar_engine.LEFT:
            if slot != 0 or side:
                return False
            zone = zone or name == "zone"
        elif name in _bar_engine.RIGHT or name == "status":
            if slot != 2:
                return False
            side = 1
        else:
            return False
    return zone


def _band_part():
    """The look's band for the metric class in force: the desk bar's or the
    handheld bar's (ui.bar_part)."""
    if _layout_base.metric_class() == _layout_base.DESK:
        return _ui_draw.BAR_BAND
    return _ui_draw.BAR_HH_BAND


# -- the chrome's chip ----------------------------------------------------------

def mini_btn(label, rect, fill, cv, label_rect=None):
    """A tiny labelled chip on `cv` (ui_draw.mini_btn): the Settings steppers'
    and the update screen's vocabulary."""
    _ui_draw.mini_btn(cv, rect, label, fill, label_rect)


# The strip each content surface takes, keyed by its layer's id: the frame
# draws it after the surface's page (`BarLayer.draw_surface`).
STRIP_OF = {"settings": "settings", "cards": "menu", "tasks": "tasks", "webconsole": "webconsole",
            "map": "menu", "scene": "menu", "music": "menu", "paint": "menu"}
# The surfaces that draw their strip themselves, and why the frame cannot.
STRIP_SELF = {
    "block_editor_ui.py": "an entry prompt draws over the bar",
    "code_layer.py": ("the stop card's See-why popup draws over the bar (the theme's"
                      " Config is a CodeLayer)"),
    "editor_desk.py": "the dock draws over the bar",
    "launcher_layer.py": ("the home's retained frame draws the strip only where its"
                          " buffer lacks it, and the back tip over it"),
    "home_band.py": "the band frame draws the strip between the band and the damage it hands",
    "wm_desk.py": "the windows paint over the desk's bar",
    "console.py": ("a running tool's strip is on the game canvas inside the Player's"
                   " tick, or after the composite"),
    "shell_cards.py": "the pause card is an overlay: its bar over its scrim",
}


# The slot of a theme's icon set (runtime/toolkit/iconsets.py) a lent row's
# icon draws where it differs from the IconSheet's kind: the sliders for
# Config (the gear is Settings', owner 2026-10-19) and the face for Sprites.
SET_KIND = {"edit": "sliders", "paint": "sprite", "run": "play"}


def _block_set(block, field, value):
    """Field `field` (0 .. 31) of block `block` (a str, its id) set to
    `value` through the engine -- an int as it is, None as a value of its
    own, anything else by its hash: True where the field changed. A bar's
    strip keys its parts on a block of the fields their state lies in."""
    if value is None:
        v = 0x3fffffff
    elif isinstance(value, int):
        v = value
    else:
        v = hash(value)
    return _C.api_block_set(block, field, v)


def _block_gen(block):
    """Block `block`'s generation: moved by every change, 0 where no field
    was ever set."""
    return _C.api_block_gen(block)


def _block_since(block, gen):
    """The fields of block `block` set to another value after generation
    `gen`, a bit each: what a part drawn at `gen` draws again."""
    return _C.api_block_since(block, gen)


def _block_key(block):
    """What block `block`'s fields show, hashed: a key that matches again
    once every field is back to a value it had."""
    return _C.api_block_key(block)


class ZoneLook:
    """The bar's look for a row an app lends it (`uitree_editor.BarZone`'s
    `look`): each cell the replay lays out -- a tab, an icon, a word, a line
    of text, a hairline -- drawn in the bar's vocabulary on the canvas it
    hands, at the font scale, in the theme's icon set where its look names
    one. `where` is the strip the row stands on."""

    def __init__(self, ws, where):
        self.ws = ws
        self.where = where

    def zone_scale(self):
        """The FONT scale, which `ui_draw.tab`/`ui_draw.button` draw the
        zone's cells at (a chip laid out at the chrome scale and drawn at
        the font scale opens the wrong tab, #203)."""
        return max(1, self.ws.layout.fs)

    def tab_pad(self):
        return _ui_draw.metrics("tab")[_ui_draw.TAB_PAD] * self.zone_scale()

    def tab_width(self, label, icon, h):
        got = _ui_draw.tab_row_rects((0, 0, 1 << 14, h), [(label, label)], self.zone_scale())
        return got[0][1][2] if got else h

    def word_width(self, label, icon, h):
        fs = self.zone_scale()
        return (_BAR_ICON + 4 + 8) * fs + _ui_draw.print_width(label, fs)

    def draw_tab(self, cv, r, cur, label, icon, labelled, every):
        """A tab in cell `r`. Where the row names `every` tab, each is a tab
        chip, the current one on its plate; where it names the current one
        alone (a narrow zone), that one is the theme's current mark as a pill
        (`_open_mark`) with its name in the mark's ink, as the home's bar tabs
        are, and the rest are icons."""
        ws = self.ws
        th = ws.theme_colors
        sets = ws.icon_spec() is not None
        if labelled and cur and not every:
            ink = self._open_mark(cv, r)
            _ui_draw.tab(cv, th, r, False, label, True,
                         th["chrome_ink"] if ink is None else ink,
                         ws.icon_image_keyed(icon),
                         icon_draw=self._set_icon(cv, ink) if sets else None, kind=icon)
            return
        if labelled:
            band_ink = th["ink"] if ws.bar_layer.zone_band_light(self.where) else None
            draw = self._set_icon(cv, open_kind=icon if cur else None,
                                  open_ink=_ui_draw.current_ink(cv, th), lead=True) \
                if sets else None
            _ui_draw.tab(cv, th, r, cur, label, True, band_ink, ws.icon_image_keyed(icon),
                         icon_draw=draw, kind=icon)
            return
        ink = self._open_mark(cv, r) if cur else None
        box = _BAR_ICON * self.zone_scale()
        x = r[0] + (r[2] - box) // 2
        y = r[1] + (r[3] - box) // 2
        ws.icon(SET_KIND.get(icon, icon) if sets else icon, x, y, cv, ink=ink)

    def draw_icon(self, cv, r, icon, on, primary, marked=False):
        """A button as its icon: a plain one in the chrome ink (undo and redo
        in the disabled ink when off), a primary one (Play, Restart, Stop) in
        `value`; `marked` wears the dot of a thing owed."""
        ws = self.ws
        th = ws.theme_colors
        box = _BAR_ICON * self.zone_scale()
        x = r[0] + (r[2] - box) // 2
        y = r[1] + (r[3] - box) // 2
        if not primary:
            self._draw_history_icon(cv, icon, x, y, box, on) if icon in ("undo", "redo") \
                else ws.icon(icon, x, y, cv)
        elif icon == "stop":
            m = 4 * self.zone_scale()
            cv.rect(x + m, y + m, box - 2 * m, box - 2 * m, th["value"])
        elif ws.icon_spec() is not None and icon == "run":
            self._draw_play(cv, (x, y, box, box), th["value"])
        elif not ws.draw_icon(SET_KIND.get(icon, icon), (x, y, box, box), th["value"], cv):
            ws.icon(icon, x, y, cv)
        if marked:
            self._mark(cv, x, y)

    def draw_word(self, cv, r, label, icon, primary, marked=False):
        """A button worded: Play the primary button where the theme names no
        icon set, else its glyph and word bare on the band (`_bare_play`);
        another its glyph and word bare (`_bare_action`)."""
        ws = self.ws
        if icon == "run" and ws.icon_spec() is None:
            _ui_draw.button(cv, ws.theme_colors, r, label.upper(), kind="primary", glyph="run",
                            glyph_draw=_ui_draw.glyph_draw)
        elif icon == "run":
            self._bare_play(cv, r)
        else:
            x, y = self._bare_action(cv, r, label, None if icon == "stop" else icon)
            if marked:
                self._mark(cv, x, y)

    def open_more(self, rows, r):
        """A lent row's More menu (`BarZone.open_more`): `rows` (word,
        icon, take) as the system menu's card hung below cell `r`, the
        zone's coordinates on the bar `where` names."""
        ws = self.ws
        bl = ws.bar_layer
        ox = oy = 0
        for bar in bl._packed(self.where):
            if bl.lent_zone(self.where, bar) is not None:
                ox, oy = bar[1][0], bar[1][1]
                break
        if bl._in_window(self.where):
            kind = ws.wm.top_kind() if self.where == "app" else self.where
            win = ws.wm.windows.get(kind)
            if win is not None:
                c = win.content_rect()
                ox, oy = ox + c[0], oy + c[1]
        items = [("item", word.upper(), take, icon, word) for word, icon, take in rows]
        ws.menu_ui.open_at(items, (ox + r[0] + r[2] // 2, oy + r[1] + r[3]))

    def draw_text(self, cv, r, text):
        th = self.ws.theme_colors
        fs = self.zone_scale()
        tf = _ui_draw.font("ui")
        was = _ui_draw.print_font(tf[0])
        try:
            cut = _ui_draw.print_cut(text, max(0, r[2] - 4 * fs), fs)
            cv.print(cut, r[0] + 2 * fs, r[1] + (r[3] - tf[2] * fs) // 2,
                     th["chrome_ink_dim"], 1)
        finally:
            _ui_draw.print_font(was)

    def draw_line(self, cv, x, zone):
        fs = self.zone_scale()
        cut = 3 * fs
        cv.rect(x, zone[1] + cut, fs, zone[3] - 2 * cut, self.ws.theme_colors["border"])

    def _mark(self, cv, x, y):
        """The dot of a thing owed (Restart's, while an edit waits for it),
        on the top left corner of the icon at (x, y)."""
        fs = self.zone_scale()
        d = 6 * fs
        cv.rrect(x - 2 * fs, y - 4 * fs, d, d, d // 2, self.ws.theme_colors["value"])

    def _open_mark(self, cv, r):
        """The open tab's mark on a narrow zone, the home's bar tabs' own:
        the theme's current mark as a pill. The ink its icon and name take,
        None for the chrome ink."""
        fs = self.zone_scale()
        return _ui_draw.current(cv, self.ws.theme_colors, r, r=5 * fs, fs=fs)

    def _set_icon(self, cv, ink=None, open_kind=None, open_ink=None, lead=False):
        """A tab's icon_draw: the theme's icon set's slot for a kind, in
        `ink` (default the chrome ink), and the open tab's kind `open_kind`
        in `open_ink` where the current mark gives one. `lead` (a labelled
        chip, whose icon leads its name) moves the icon left by the blank
        columns before its ink, so the ink starts at the chip's pad as the
        name ends at it, and the pill's two pads match."""
        ws = self.ws
        if ink is None:
            ink = ws.theme_colors["chrome_ink"]
        spec = ws.icon_spec() if lead else None

        def draw(kind, r):
            c = open_ink if open_ink is not None and kind == open_kind else ink
            slot = SET_KIND.get(kind, kind)
            span = _iconsets.ink_span(slot, r[2], r[3], spec) if spec is not None else None
            if span is not None:
                r = (r[0] - span[0], r[1], r[2], r[3])
            return ws.draw_icon(slot, r, c, cv)
        return draw

    def _draw_play(self, cv, rect, ink):
        """Play, the set's bare glyph, in a stroke as heavy as the tab
        icons': a smooth set's 16 px mask draws the triangle's 2-unit stroke
        1.33 px wide, whose diagonals antialias to a grey the tab icons'
        verticals do not (Contrast's disabled ink is a grey), so below the
        20 px mask it draws twice, a column apart -- a 2 px stroke (design
        review R3-26)."""
        ws = self.ws
        if not ws.draw_icon("play", rect, ink, cv):
            return False
        spec = ws.icon_spec()
        if spec is not None and spec[0] == "smooth" \
                and min(rect[2], rect[3]) < _iconsets.SIZES[1]:
            ws.draw_icon("play", (rect[0] + 1, rect[1], rect[2], rect[3]), ink, cv)
        return True

    def _bare_play(self, cv, r):
        """Play under a theme's icon set: the set's glyph and the word, in
        `value`, on the band with no plate, at the right of `r` (D-03.3)."""
        ink = self.ws.theme_colors["value"]
        fs = self.zone_scale()
        box = _BAR_ICON * fs
        gap = 4 * fs
        tw = _ui_draw.print_width("Play", fs)
        x = r[0] + r[2] - box - gap - tw - 4 * fs
        self._draw_play(cv, (x, r[1] + (r[3] - box) // 2, box, box), ink)
        line = _ui_draw.font("ui")[2] * fs
        cv.print("Play", x + box + gap, r[1] + (r[3] - line) // 2, ink, 1)

    def _bare_action(self, cv, r, word, slot):
        """A button's glyph and word in `value` with no plate, at the right
        of `r`, as Play is drawn; Stop's glyph (`slot` None) a square, ■ (no
        set draws one). Where its icon stands, (x, y)."""
        ws = self.ws
        ink = ws.theme_colors["value"]
        fs = self.zone_scale()
        box = _BAR_ICON * fs
        gap = 4 * fs
        tw = _ui_draw.print_width(word, fs)
        x = r[0] + r[2] - box - gap - tw - 4 * fs
        y = r[1] + (r[3] - box) // 2
        if slot is None:
            m = 4 * fs
            cv.rect(x + m, y + m, box - 2 * m, box - 2 * m, ink)
        elif not ws.draw_icon(slot, (x, y, box, box), ink, cv):
            _ch.glyph(cv, slot, (x, y, box, box), ink)
        line = _ui_draw.font("ui")[2] * fs
        cv.print(word, x + box + gap, r[1] + (r[3] - line) // 2, ink, 1)
        return x, y

    def _draw_history_icon(self, cv, icon, x, y, ic, enabled):
        """Undo or redo (#88), in the theme's `disabled` ink when the journal
        has nothing to walk: the theme's icon set's in `ui_draw.disabled_ink`,
        or, where the theme names no set, the plain glyph in that ink (an
        IconSheet has no dimmed sprite)."""
        ws = self.ws
        if enabled:
            ws.icon(icon, x, y, cv)
            return
        ink = _ui_draw.disabled_ink(ws.theme_colors)
        if not ws.draw_icon(icon, (x, y, ic, ic), ink, cv):
            _ch.glyph(cv, icon, (x, y, ic, ic), ink)


class BarLayer:
    """The shell's bars (#46), migrated out of Workstation as its own surface
    (docs/history/shell_layers_refactor_v1.md Phase 2): every bar of the
    resolved layout (docs/theme_and_shell_2026-11.md §8.2), each a row of widget
    cells packed at relayout (`shell_layout.pack`) -- the OS widgets (`menu`,
    `close`, `clock`, `wifi`, `battery`, `title`, `text`, `separator`) drawn by
    the bar itself through the kernel's cell painter, the taskbar `chips` by the
    WM over the strip, and the `zone` LENT to whichever app is active --
    `launcher_layer`/`settings_layer`/`editor_app` each implement
    `draw_zone(cv, rect)` (paint the lent rect) + `zone_tap(px, py)` (claim a tap
    inside it) + `zone_gen` (an int bumped whenever their zone's pixels change).
    Today's bar is the default seed's layout: the zone left, the chips over the
    middle, the clock, X, ≡, wifi and battery right.

    `where` still selects which screen is asking (`"home"` / `"settings"` /
    `"menu"` / `"tool"`), but it's no longer a set of hardcoded draw bodies: a
    GAME shows no bar (Stage 5 retired the #71 pause frame, and a run that
    stopped shows the stop card); `"tool"` (Part 4) is the minimal bar a running
    TOOL/APP shows so it's exitable (back + title + status, NO tab ladder). The
    `"tool"` branch returns before any `owner.draw_zone` call, so `draw_zone`
    stays structurally unreachable while a Player is top-of-stack (the perf
    guardrail); the home/settings/menu three route through the SAME generalized
    cache (below) into whichever app owns `where`.

    The #43 strip cache is KEPT AND GENERALIZED, not duplicated: `_cart_bar_key`
    takes `where` and folds in the active app's `zone_gen` + `ws.can_manage`, so ONE
    offscreen strip per bar serves every `where` and re-renders WHOLE only when a
    key field that bar shows changes (app switch / clock tick / zone-content change
    / theme edit) -- never a bare frame, and never a bar for a widget it does not
    hold. `_render_cart_bar(cv, key, i)` renders bar `i` of the zoned layout.

    Boundary decisions (deliberate, see the doc):
      * The chrome's glyph and chip are this module's `glyph` and `mini_btn`;
        the icon toolkit (ws.icon / ws.bar_image) stays on Workstation and the
        bar is a consumer of it (via self.ws).
      * `bar_img_cache` (per-kind icon Image cache backing ws.icon) stays on ws;
        `_bar_cache_gen` (the strip cache generation) lives here, bumped
        through invalidate(); the look's changes reach the strips through
        `ws.look.look_gen` in their key.

    The bar is CHROME the content composes, not a standalone stack layer: it's
    SYSTEM-domain on the launcher, Settings and every Editor tab (drawn on
    sys_canvas) and GAME-domain on a running tool's strip (drawn on the fixed game canvas, `zone_is_game`), and it draws
    at their rects (`bar_rects`), LAST over each content's paint, which lays
    out in what the bars leave (`content_rect`). The frame draws a surface's
    strip after its page (`draw_surface`, `STRIP_OF`), but for the surfaces
    `STRIP_SELF` names, which call draw_status_strip(where) themselves; the
    pointer methods delegate their bar slice to
    handle_bar_tap(where, ...), which takes
    canvas coordinates and hit-test in the coordinates of the bar they land on.
    An app's zone_tap takes the lent rect as a parameter: the zone's cell, in
    the game canvas's packing or the responsive layout's. Inside a window the
    layout packs the window's band (`layout_base.BAND`, today's bar at the
    window's top whatever the theme's layout) and only its zone draws.

    `NAMES` (palette) is injected at construction (the same circular-import dodge
    the other extracted UIs use)."""

    def __init__(self, ws, names):
        self.ws = ws
        self._NAMES = names
        # True while a desk Editor pane draws an Editor tab
        # (runtime/editors/editor_desk.py): the pane takes no bar, and the tab's own
        # strip draw and bar tap are no-ops.
        self.held = False
        self._app_zones = {}            # app id -> the row its page lends (`_app_zone`)
        self._row_k = [None, -1, 0, 0]  # row_need's last: its zone, zone_gen, font scale, need
        self._k8 = [None, 0]            # key[8]'s title, and the times it moved
        self._cr_last = None            # content_rect's last (x, y, w, h)
        self._cr_game = [0, 0, None, None]   # ...and a game zone's: w, h, bars, rect
        # Cached top bar (#43, generalized in Stage 4 to every `where`): rendered
        # ONCE into an offscreen strip and blitted each frame (one flat copy)
        # instead of re-rendering ~9 sprites + glyph + text every frame.
        # `_bar_strips` maps `where` -> a small MRU list of [strip, key, canvas]:
        # the offscreen layer,
        # the state key it holds (None = stale) and the canvas it was built on (a
        # web-view swap, OR switching between the game canvas and the system canvas,
        # forces a rebuild); `_bar_cache_gen` is bumped by the explicit invalidators
        # (invalidate()), and `ws.look.look_gen` in the key repaints a look change. Keyed per
        # `where` (was one shared slot) because the windowed WM (wm_windowed.py)
        # draws TWO bars per frame -- the desktop root's "home" bar and the focused
        # window's own -- and a shared slot would rebuild both every frame. On the
        # fullscreen-stack tiers only one `where` is ever active, so the dict holds
        # one live entry, exactly as cheap as the old single slot.
        #
        # Each `where` keeps up to _BAR_STRIP_SLOTS of them, one per destination
        # canvas (see _draw_top_bar_cart). Two is the measured alternation -- root
        # canvas vs window buffer; a third destination would simply thrash as
        # before, which is a perf floor, not a correctness problem.
        self._bar_strips = {}
        self._bar_cache_gen = 0
        # Clock-text cache (#66): (second, string) -- see clock_text.
        self.clock_at = -1           # when the clock was read, and how long
        self._clock_hold = 0          # its text holds from then (_clock_text)
        self._clock_hm = (-1, -1)
        self._clock_cache = ""
        self._date_cache = (0, 0, 0)
        # The root canvas the bar strips are published to (publish_strips),
        # and the clock text redraw_clock last painted there.
        self._strip_cv = None
        self._clock_drawn = None
        # The game canvas's packing (_packed) and what it was packed from;
        # each packing's per-bar key fields (_key_fields).
        self._game_of = None
        self._game_size = None
        self._game_pack = None
        self._band_wm = None          # the WM `_band_fs` was read off
        self._band_fs = None          # ...its game_is_fullscreen
        self._band_vp = None          # the viewport the tool band was placed for
        self._band_of = None          # ...and the layout packing it took
        self._band = None             # a tool cart's compact bar on the glass (tool_band)
        self._band_pack = None
        self._fields_of = None
        self._fields = ()
        self._need = _KEY_ALL
        # Each `where`'s frame key, filled in place (_fill_key).
        self._keys = {}
        self._blk = {}                # where -> its block of fields in the engine, by id
        # The keys on the bar (`focus_enter`): the `where` whose bar holds
        # them, the item index and the focused item as (bar index, rect in
        # that bar's coordinates).
        self.focus = None
        self.focus_where = None
        self._page_at = [None, None, None]      # the bar the page draws: where, its rect, its cells
        self._plate_at = [None, 0, 0, 0, None]  # the system plate's box: the cells, the bar's x, y, h
        self.focus_item = None
        self._items_lgen = -1         # the status items' count the packing holds
        self._hooks = None            # the bar page's actions' ways out (`_page_draw`)
        self._stop_rects = []         # the page's status item rects (`_page_stop`)
        self._chip_stops = []         # the page's chip rects on the desk (`focus_items`, `_page_stop`)
        _ui_draw.on_bar(False)
        _bar_engine.forget()          # (what another console's bar handed the page)
        _bar_ui.PAINT[0] = _bar_ui.TAP[0] = _bar_ui.CHIP[0] = _bar_ui.ITEM[0] = None

    def invalidate(self):
        """Repaint every cached bar strip on the next frame: something its key
        does not carry moved its pixels (a bar placement, a journal flip)."""
        self._bar_cache_gen += 1

    # -- the strips a rotated compositor presents ------------------------------

    def publish_strips(self, cv=None):
        """Hand the bar strips to a root canvas that presents them as rects of
        their own (the rotated compositor's `set_strips`; absent elsewhere):
        every bar in force, at the root's size. `cv` is the root, kept for the
        relayouts that publish again; every repaint that changes a strip's
        pixels on it says so through `strip_moved`."""
        if cv is not None:
            self._strip_cv = cv
        cv = self._strip_cv
        ss = getattr(cv, "set_strips", None)
        if ss is None:
            return
        r = getattr(self.ws, "render_scale", 1)
        ss([(x * r, y * r, w * r, h * r) for x, y, w, h in
            bar_rects_of(cv.w // r, cv.h // r, self.ws.layout.status_h, bars_in_force())])

    def strip_moved(self, cv, x, y, w, h):
        """New pixels landed in (x, y, w, h) of the bar on `cv`: when that is
        the published root, the strips there ride its next presented frame.
        A bar drawn through a viewport of the root is a window's, drawn
        straight into the glass (the windowed WM's direct render): its
        pixels are the window's, which the WM describes."""
        if cv is self._strip_cv and not getattr(cv, "_ox", 0) and not getattr(cv, "_oy", 0):
            sm = getattr(cv, "strip_moved", None)
            if sm is not None:
                sm(x, y, w, h)

    # -- draw ----------------------------------------------------------------

    def draw_surface(self, layer, dt, app=False):
        """Draw content `layer`, then the strip its surface takes, LAST (chrome
        over its page): `STRIP_OF`'s, else with `app` (the full-screen frame's
        word) a registered app's "app" strip, the host's guarantee; none for
        a surface that draws its own (`STRIP_SELF`)."""
        layer.draw(dt)
        ws = self.ws
        where = STRIP_OF.get(layer.id)
        if where is None:
            if not app:
                return
            got = ws.app(layer.id)
            if got is None or getattr(got, "glass", False) or ws.wm.desk_open():
                return
            where = "app"
        elif self.strip_is_title(layer):
            return
        self.draw_status_strip(where)

    def strip_is_title(self, layer):
        """Whether content `layer`'s bar is its desk window's title strip,
        windowed or full screen: the task manager and Settings lend the bar
        no zone there, so they draw no band."""
        ws = self.ws
        return ws.windowed_chrome and layer in (ws.tasks_layer, ws.settings_layer)

    def draw_status_strip(self, where):
        """The strip `where` names ("home" / "settings" / "menu" / "tool" /
        ...), drawn through the ONE generalized cache mechanism below
        (_draw_top_bar_cart) -- there is no per-`where` draw body here; the
        zoning happens inside _render_cart_bar."""
        if self.held:
            return
        self._draw_top_bar_cart(where)

    # -- zone plumbing (Stage 4, #46 zoned bar) -------------------------------
    #
    # "where" identifies which screen is asking; these helpers answer the THREE
    # questions that differ per `where`: who owns the lent left zone, which canvas
    # + rect it draws into, and whether it draws on the fixed 320x240 GAME canvas
    # (a running tool's strip) or the responsive SYSTEM canvas -- both show the
    # SAME bar.

    def _zone_owner(self, where):
        """What answers for `where`'s lent left zone, or None (a running
        tool's strip lends none, see _render_cart_bar): the owning app, or,
        for an app on `uitree` whose page lends the bar a row, that row's
        zone (its `bar_zone`, `uitree_editor.BarZone`), which replays it
        and takes its taps through the app's engine."""
        o = self._zone_app(where)
        if where == "app" and o is not None:
            return self._app_zone(o)
        z = getattr(o, "bar_zone", None)
        return o if z is None else z

    def _app_zone(self, app):
        """The zone of registered app `app`, whose page lends the bar a row
        (`LENDS_BAR`): the shell's replay of it (`uitree_editor.BarZone`,
        made at the first ask and kept), after the title the app names
        (`bar_title`)."""
        z = self._app_zones.get(app.id)
        if z is None:
            from uitree_editor import BarZone
            z = self._app_zones[app.id] = BarZone(app.engine, ZoneLook(self.ws, "app"), host=app)
        z.back_title = app.bar_title        # (a new one moves its zone_gen)
        return z

    def _zone_app(self, where):
        ws = self.ws
        if where == "home":
            return ws.launcher_layer
        if where == "projects":
            return ws.projects_layer
        if where == "menu":
            return ws.editor_app
        if where == "app":
            # a registered app whose page lends the bar a row (`_app_zone`)
            app = ws.app(ws.wm.top_kind())
            return app if getattr(app, "LENDS_BAR", False) else None
        if STRIP_OF.get(where) == where:  # a registered app's own strip
            return ws.app(where)          # (Settings', the task manager's)
        return None

    def zone_is_game(self, where):
        """True for the surfaces that draw on the fixed 320x240 GAME canvas -- since
        the #39 step-3 conversions moved every Editor tab onto the responsive SYSTEM
        canvas, that's only the Part-4 "tool" bar (a running tool/app is on the game
        canvas).

        The one exception is a RESPONSIVE app cart (#181): it drew on the SYSTEM
        canvas, so its exitable strip has to be the responsive geometry too --
        the fixed cluster would leave the context-X stranded 700px left of the
        right edge on the P4. `app_full_canvas` is False for every game, every
        fixed app cart and every shipped system app, so nothing else moves.

        "app" is a REGISTERED system app's strip (console.py's host guarantee):
        the app draws on the SYSTEM canvas, so its strip does too. Drawn on
        the game canvas instead, a board with a separate system canvas (the
        Guition S3's 480x320) showed the app's bar band empty and had no
        context-X under the finger."""
        ws = self.ws
        run = ws.run
        if where != "tool" or run.app_full_canvas:
            return False
        # A tool's strip is the look's bar on the system canvas: the one
        # every app shows where that canvas is the game's
        # (docs/history/look_2026-10.md step 27a), else the compact band over the
        # game's top rows (`tool_band`, step 33); in a desk window, the
        # game canvas's.
        return ws.sys_canvas is not run.canvas and self.tool_band() is None

    def tool_band(self):
        """Where a running tool cart's compact bar sits on the system
        canvas, (x, y, w, h), or None where the tool draws on that canvas
        itself: over the game canvas's 18 rows at the viewport's scale, and
        where those are fewer than the glass's bar, the letterbox above them
        too, so the chevron and the title are a tap. The console draws it
        after the composite (`Workstation._draw_tool_band`)."""
        ws = self.ws
        run = ws.run
        gc = run.canvas
        if gc is ws.sys_canvas or run.app_full_canvas:
            return None
        wm = ws.wm
        if wm is not self._band_wm:           # cached by WM identity: a bound
            self._band_wm = wm                # method is an allocation a frame
            self._band_fs = getattr(wm, "game_is_fullscreen", None)
        if self._band_fs is not None and not self._band_fs():
            return None
        vp = wm.viewport()
        if vp is not self._band_vp:
            self._band_vp = vp
            ox, oy, sc = vp
            view = getattr(ws, "game_view", None)
            gw = view[2] if view is not None else gc.w
            h = _STATUS_H * sc
            bottom = oy + h
            y = max(0, min(oy, bottom - _BAND_TAP * ws.layout.fs))
            self._band = (ox, y, gw * sc, bottom - y)
        return self._band

    def _tool_pack(self, band):
        """The compact band's packing: the bar in force's first bar on the
        band, its Moy tile, chevron and title, battery and clock (no Wi-Fi,
        no X: the chevron is the way back)."""
        layout = self.ws.layout
        po = layout._pack_of
        if self._band_pack is None or self._band_of is not po or self._band_pack[0][1] != band:
            of, cs, fs, _sys_len = po
            top = _without(of[:1], ("wifi", "close", "chips"))
            bh = band[3]
            got = _pack(band[2], bh, bh, cs, fs, layout.clock_w, _bar_text_w,
                        of=((("top",) + top[0][1:]),),
                        sys_len=_layout_base.sys_tile(bh)[2])
            edge, _r, dy, cells = got[0]
            self._band_pack = ((edge, band, dy, cells),)
            self._band_of = po
        return self._band_pack

    def _bar_canvas(self, where, game=None):
        """`where`'s canvas; `game` is `_zone_is_game(where)` where the caller
        has it already (each read of `ws.sys_canvas` is a property call)."""
        if game is None:
            if where == "app":
                return self.ws.sys_canvas
            game = self.zone_is_game(where)
        # an "app" strip on the game canvas: that canvas IS the system one
        if game:
            return self.ws.run.canvas
        return self.ws.sys_canvas

    def _bar_h(self, where):
        """The rows of a BAR_ROWS-row bar on `where`'s canvas: every bar's
        size is in those."""
        if self.zone_is_game(where):
            return _STATUS_H
        return self.ws.layout.status_h

    # -- where the bars are: the one author for draws and taps -----------------
    #
    # A bar's pixels and its cells (shell_layout.pack) are in BAR coordinates,
    # row 0 its first; the bar itself sits at its rect on `where`'s canvas. The
    # responsive surfaces read the packing their layout made at relayout (a
    # window's layout packs its band); a strip on the fixed game canvas packs
    # the bars in force once per placement, at that canvas's 320x240 and
    # scale 1.

    def _sync_items(self):
        """Pack the bars again where the apps' status items came or went
        (`status_items.ITEMS.layout_gen`): the count `shell_layout.pack`
        reserves their cell for."""
        lg = _ITEMS.layout_gen
        if lg == self._items_lgen:
            return
        self._items_lgen = lg
        n = _ITEMS.count()
        if _SL_ITEMS[0] != n:
            _SL_ITEMS[0] = n
            self._game_of = None
            repack = getattr(self.ws.layout, "repack", None)
            if repack is not None:
                repack()
        self.invalidate()

    def _packed(self, where, game=None):
        self._sync_items()
        if game is None:
            game = self.zone_is_game(where)
        if where == "tool" and not game:
            band = self.tool_band()
            if band is not None:
                return self._tool_pack(band)
        if game:
            of = bars_in_force()
            cv = self.ws.run.canvas
            gs = self._game_size
            if (self._game_of is not of or gs is None
                    or gs[0] != cv.w or gs[1] != cv.h):
                self._game_of = of
                self._game_size = (cv.w, cv.h)
                self._game_pack = _pack(cv.w, cv.h, _STATUS_H, 1, 1, 5 * 8, _bar_text_w, of)
            return self._game_pack
        layout = self.ws.layout
        room = getattr(layout, "room", None)
        if room is None:
            return layout.bars
        got = room.get(where)
        if got is None:
            got = room[where] = self._make_room(where, layout.bars)
        return got

    def _make_room(self, where, bars):
        """`where`'s packing: the layout's `bars`, less the status widgets
        (`_YIELD`, in order) its zone owner needs the room of. An owner with
        a `zone_need(h)` -- the narrowest rect, at band height `h`, in which
        everything it draws stands at the tap floor -- takes a widget's room
        until its rect is that wide, and only where the room reaches it (a
        layout whose status cluster is on another bar keeps it). Inside a
        window the zone runs to the strip's end already (`lent_zone`)."""
        owner = self._zone_owner(where)
        need = getattr(owner, "zone_need", None)
        if need is None or self._in_window(where):
            return bars
        layout = self.ws.layout
        if where == "menu":
            # The Editor's one bar shows no Wi-Fi (EDITOR_LAYOUT.md's
            # handheld): its tabs, undo, redo and Play by the battery and clock.
            bars = layout.bars_without(("wifi",))
        had = self._owner_w(where, bars)
        if had is None or had[0] >= need(had[1]):
            return bars
        out = bars
        for k in range(1, len(_YIELD) + 1):
            wider = layout.bars_without(_YIELD[:k] + (("wifi",) if where == "menu" else ()))
            got = self._owner_w(where, wider)
            if got is None or got[0] <= had[0]:
                break
            out, had = wider, got
            if got[0] >= need(got[1]):
                break
        return out

    def _owner_w(self, where, packed):
        """(width, height) of the rect `where`'s zone owner gets in
        `packed`, past the chevron where the bar draws one; None where the
        packing places no zone."""
        got = _cell_of(packed, "zone")
        if got is None:
            return None
        _x, _y, w, h = got[1]
        if where != "menu" and self._way_back(where) and _cell_of(packed, "close") is None:
            w -= self._back_w(False)
        return w, h

    def bar_rects(self, where):
        """Every bar `where` shows, as (x, y, w, h) on its canvas."""
        return tuple(b[1] for b in self._packed(where))

    def bar_rect(self, i, where):
        return self._packed(where)[i][1]

    def content_rect(self, where):
        """`where`'s canvas less its bars: what the surface under them lays
        out in, (x, y, w, h)."""
        cv = self._bar_canvas(where)
        if where == "tool" and self.ws.run.app_window_canvas:
            wh = self.ws.app_window_size()       # a window's: its title strip is the bar
            return self._kept_rect(0, 0, wh[0], wh[1])
        if self.zone_is_game(where):
            of = bars_in_force()
            g = self._cr_game
            if g[0] != cv.w or g[1] != cv.h or g[2] is not of:
                g[0] = cv.w
                g[1] = cv.h
                g[2] = of
                g[3] = content_of(cv.w, cv.h, _STATUS_H, of)
            return g[3]
        L = self.ws.layout
        return self._kept_rect(L.cx, L.cy, L.cw, L.ch)

    def _kept_rect(self, x, y, w, h):
        """(x, y, w, h), the tuple answered last while it holds: an app asks
        `content_rect()` every frame it draws."""
        r = self._cr_last
        if r is None or r[0] != x or r[1] != y or r[2] != w or r[3] != h:
            r = self._cr_last = (x, y, w, h)
        return r

    def bar_at(self, where, px, py):
        """True when (px, py) on `where`'s canvas is on one of its bars."""
        for b in self._packed(where):
            if _in(px, py, b[1]):
                return True
        return False

    def cell(self, where, name):
        """(bar, cell rect) of `where`'s first `name` widget, the cell in its
        bar's coordinates and the bar as `shell_layout.pack` gives it; None
        where no bar places one."""
        for b in self._packed(where):
            for c in b[3]:
                if c[0] == name:
                    return b, c[1]
        return None

    def row_need(self, where):
        """The narrowest zone holding the row `where`'s page lends the bar
        as icons (`BarZone.zone_need`) at its zone's height; 0 where it lends
        none. Kept while the zone's generation and the font scale stand."""
        z = self._zone_owner(where)
        need = getattr(z, "zone_need", None)
        if need is None:
            return 0
        k = self._row_k
        g, fs = z.zone_gen, self.ws.layout.fs
        if k[0] is not z or k[1] != g or k[2] != fs:
            got = self.cell(where, "zone")
            k[0], k[1], k[2] = z, g, fs
            k[3] = need(got[1][3]) if got is not None else 0
        return k[3]

    def zone_rect(self, where):
        """The rect LENT to `where`'s app for its draw_zone/zone_tap, in its
        bar's coordinates."""
        for bar in self._packed(where):
            zone = self.lent_zone(where, bar)
            if zone is not None:
                return zone
        return (0, 0, 0, 0)

    def lent_zone(self, where, bar):
        """The zone cell of `bar` (a packed bar of `where`'s) as its owner
        draws into it and hit-tests it, in the bar's coordinates: the cell,
        run on to a window strip's end inside a window; None where the bar
        places no zone. The draw and the tap both take it from here."""
        for c in bar[3]:
            if c[0] == "zone":
                if self._in_window(where):
                    return self._window_zone(bar[1], c[1])
                return c[1]
        return None

    def _window_zone(self, rect, zone):
        """A window's strip paints none of the OS widgets, so its zone runs on
        to the strip's end, its own left margin kept at the right; in a
        full-screen window's row, between its title slot and its controls
        (`WindowedWM.band_span`)."""
        span = self.ws.wm.band_span()
        if span is not None:
            return (span[0], zone[1], max(0, span[1] - span[0]), zone[3])
        return (zone[0], zone[1], max(zone[2], rect[2] - 2 * zone[0]), zone[3])

    def lends_band(self, where):
        """Whether `where`'s content draws the band a window's layouts take:
        a full-screen window's row is then that band (`WindowedWM._band_is_row`)."""
        return (where != "home" and self._zone_owner(where) is not None
                and not self.strip_is_title(self.ws.layer_of(where)))

    def paint_band(self, cv, rect):
        """A window's band ground at `rect` on `cv`, its line under it: what a
        full-screen row with no band of its app's lies on."""
        th = self.ws.theme_colors
        light = th.get("bar_light", False) or th.get("band_light", False)
        _ui_draw.frame_band(cv, th, rect, light, _BAND_SIDE["top"])

    def zone_band_light(self, where):
        """True when `where`'s bar band is LIGHT -- an in-window band under a
        theme whose window bands are light (`band_light`), or ANY band when the
        theme's OS bar itself is light (`bar_light`) -- zone owners pick their band
        ink with this so lent-zone text stays readable on either band."""
        th = self.ws.theme_colors
        if th.get("bar_light", False):
            return True
        return self._in_window(where) and th.get("band_light", False)

    def _in_window(self, where):
        """True when `where`'s bar is being drawn INSIDE a window of the windowed
        WM (#73): every zoned screen except the desktop root's "home" bar. The
        window bar then suppresses the OS widgets (no copied taskbar) -- the
        WM's title strip carries min/max/close instead. Always False on the
        fullscreen-stack tiers (ws.windowed_chrome stays False there)."""
        return getattr(self.ws, "windowed_chrome", False) and where not in (
            "home", "desk", "tool", "app")

    # -- draw + cache (the #43 strip, generalized to every `where`) -----------

    def _draw_top_bar_cart(self, where, lay=None, also=None):
        """The ONE cached bar draw for every `where` (Stage 4 generalizes what was
        the running-cart-only strip cache): each bar's pixels rendered ONCE into
        an offscreen strip and blit_strip'd each frame (one flat copy a bar)
        instead of re-rendering ~9 16x16 sprites + a glyph + text every frame --
        ~6ms of wasted draw the #43 cache exists to avoid. When a field of the
        key that the bar shows changes (app switch / clock tick / zone-content
        change / theme edit / font-size change) that bar's strip is re-rendered
        WHOLE, then reused; a bar without the clock never re-renders on its
        tick. The strips are purely the DRAW; hit-testing goes through the
        packed cells / zone_tap, so caching can't desync taps. `lay`, a rect
        on the canvas: that part of the bars alone laid, onto `also` too
        (`lay_chips`, which answers)."""
        game = self.zone_is_game(where)
        cv = self._bar_canvas(where, game)
        packed = self._packed(where, game)
        fields = self._key_fields(packed)
        key = self._keys.get(where)
        if key is None:
            key = self._keys[where] = [None] * _KEY_N
        self._fill_key(key, where, cv, self._shown(where), self._block(where))
        if hasattr(cv, "_lr"):
            # The canvas is itself a RecordingLayer (a windowed-WM window buffer on
            # the web console): a strip cache NESTED in a recorded layer can't ship
            # (blit_strip of a raw strip isn't a recordable op), so render the bars
            # directly -- a live window re-records its whole stream anyway, and the
            # dozen icon/text commands are far lighter than an inlined pixel strip.
            for i in range(len(packed)):
                r = packed[i][1]
                if lay is not None:
                    if not _meets(r, lay):
                        continue
                    cv.clip(lay[0], lay[1], lay[2], lay[3])
                if r[0] or r[1]:
                    cv.camera(-r[0], -r[1])
                self._render_cart_bar(cv, key, i)
                if r[0] or r[1]:
                    cv.camera(0, 0)
                if lay is not None:
                    cv.clip()
            return False
        bars = self._bar_strips.get(where)
        if bars is None:
            bars = []
            self._bar_strips[where] = bars
        while len(bars) < len(packed):
            bars.append([])
        for i in range(len(packed)):
            r = packed[i][1]
            if lay is None:
                self._draw_bar(cv, bars[i], r, key, fields[i], i)
            elif _meets(r, lay):
                strip = self._draw_bar(cv, bars[i], r, key, fields[i], i, False)
                x, y, w, h = _cut(lay, r)
                if hasattr(cv, "blit_strip_rect"):
                    cv.blit_strip_rect(strip, r[0], r[1], x, y, w, h)
                else:
                    cv.blit_strip(strip, r[0], r[1])     # (the whole bar, current)
                if also is not None:
                    also.blit_strip_rect(strip, r[0], r[1], x, y, w, h)
                self.strip_moved(cv, x, y, w, h)
        return True

    def _key_fields(self, packed):
        """For each bar of `packed`, the `_cart_bar_key` fields its pixels show:
        the shared ones, then each of its widgets' values, and their union as
        a bit per field (`_need`). Once per packing."""
        if self._fields_of is not packed:
            out = []
            need = 0
            for b in packed:
                f = list(_KEY_ALWAYS)
                for c in b[3]:
                    for k in _KEY_OF.get(c[0], ()):
                        if k not in f:
                            f.append(k)
                out.append(tuple(f))
                for k in f:
                    need |= 1 << k
            self._need = need
            self._fields_of = packed
            self._fields = tuple(out)
        return self._fields

    def _shown(self, where):
        """The key fields `where`'s bars draw, as `_need`'s bits (after
        `_key_fields` of its packing): the undo/redo dims only in the
        Editor's zone."""
        return self._need if where == "menu" else self._need & ~_KEY_UNDO

    def shown_gen(self, where):
        """An int that moves whenever what `where`'s bars draw does: what
        the fields of its block in the engine show, hashed (`_block_key`),
        the fields filled again on each ask as the bar's own draw fills
        them (`_fill_key`). The key a part named per buffer folds
        (`home_band.held`), and the key a cache over a whole frame that includes
        the bar folds: a state left and come back to matches again."""
        return self._shown_now(where)

    def shown_key(self, where):
        """`shown_gen`: the one int serves both."""
        return self._shown_now(where)

    def _block(self, where):
        """`where`'s block of fields in the engine (`_block_set`), by
        its id: each field set as the bar fills it, so the engine says
        which moved since a strip was drawn (`_block_since`)."""
        b = self._blk.get(where)
        if b is None:
            b = self._blk[where] = "bar." + where
        return b

    def _shown_now(self, where):
        game = self.zone_is_game(where)
        cv = self._bar_canvas(where, game)
        self._key_fields(self._packed(where, game))
        key = self._keys.get(where)
        if key is None:
            key = self._keys[where] = [None] * _KEY_N
        blk = self._block(where)
        self._fill_key(key, where, cv, self._shown(where), blk)
        return _block_key(blk)

    def _draw_bar(self, cv, slots, rect, key, fields, i, blit=True):
        """Bar `i`'s strip at `rect` on `cv`, from the slot that holds it for
        `cv`, re-rendered when a field of `key` it shows moved; the strip
        alone, laid nowhere, without `blit`."""
        bx, by, bw, bh = rect
        # One slot PER CANVAS, most-recently-used first. The windowed WM draws the
        # same `where` into DIFFERENT canvases from frame to frame -- straight into
        # the root canvas through a viewport on a quiet frame (wm_paint
        # _direct_render), into the window's own buffer otherwise -- so a slot that
        # remembers only one canvas reads every switch as a canvas swap and rebuilds.
        # That cost 72ms of an 86ms Settings frame on P4 glass, twice per gesture
        # (press edge + release edge), because the rebuild calls new_layer and the
        # P4's new_layer pre-collects. Same failure the per-`where` keying above
        # already fixed once, one axis over.
        slot = None
        for s in slots:
            if s[2] is cv:
                slot = s
                break
        if slot is None:
            if len(slots) >= _BAR_STRIP_SLOTS:
                slot = slots.pop()                 # evict the least-recently-used
                _release_layer(slot[0])            # ...its layer belongs to a
                slot[0] = None                     # canvas we are no longer drawing
                slot[1] = None                     # into, so it is rebuilt below
                slot[2] = None
                slot[3] = None
            else:
                # [strip, the block's generation it was drawn at, canvas,
                #  the item the keys were on]
                slot = [None, None, None, None]
            slots.insert(0, slot)
        else:
            # Move to front. By IDENTITY, not list.remove(), whose == would happily
            # match a different all-None slot.
            for j in range(len(slots)):
                if slots[j] is slot:
                    if j:
                        slots.insert(0, slots.pop(j))
                    break
        strip = slot[0]
        # The active canvas can SWAP at runtime (the device web view binds a recording
        # TeeCanvas in place of the raw DeviceCanvas, #41) OR change identity/size as
        # `where` moves between the fixed game canvas and the responsive system canvas
        # (Stage 4) or between the root canvas and a window buffer (wm_windowed.py).
        # A strip allocated on the OLD canvas/size is the wrong layer for the new
        # one (a raw DeviceCanvas strip blitted through the Tee has no RecordingLayer
        # hooks -- '_end_batch' AttributeError -- and it wouldn't be recorded for the
        # browser anyway), so rebuild whenever either changes.
        canvas_changed = slot[2] is not cv
        size_changed = strip is None or strip.w != bw or strip.h != bh
        fresh = size_changed or canvas_changed or slot[1] is None
        part = 0
        blk = self._block(key[0])
        if not fresh:
            # the fields this bar shows set since the strip was drawn
            # (`_block_since`): those drawn in a part of the bar draw
            # that part again (`_render_cart_part`); any other, the strip
            m = 0
            for k in fields:
                m |= 1 << k
            part = _block_since(blk, slot[1]) & m
            if part & ~_KEY_PARTS:
                fresh = True
                part = 0
        if fresh:
            # (Re)build the cached strip. new_layer gives a same-type/-palette canvas the
            # bar body draws into in BAR coordinates, so the cached pixels are
            # byte-identical to drawing straight onto cv at the bar's rect. Reuse the
            # buffer across re-renders when the size is unchanged; allocate a fresh
            # layer on first build / a resize / a canvas swap.
            if size_changed or canvas_changed:
                self.ws.perf.note_cost("bar.strip.alloc")
                _release_layer(strip)              # the old size's / canvas's
                strip = cv.new_layer(bw, bh)
                slot[0] = strip
                slot[2] = cv
            self.ws.perf.note_cost("bar.strip.render")
            self._render_cart_bar(strip, key, i)
        elif part:
            self.ws.perf.note_cost("bar.strip.part")
            self._render_cart_part(strip, key, i, part, slot[3])
        if fresh or part:
            slot[1] = _block_gen(blk)
            slot[3] = key[12]
        if not blit:
            return strip
        cv.blit_strip(strip, bx, by)
        if fresh or part:
            self.strip_moved(cv, bx, by, bw, bh)
        return strip

    def _cart_bar_key(self, where):
        """The cache key for the bar: every piece of state that changes ANY `where`
        variant's PIXELS. A different key forces a strip re-render; an unchanged key
        reuses the cached strip. `where` is key[0] (so a screen switch always
        invalidates); then the clock text (ticks ~once/min), the look's
        generation + the glyph font scale (a theme or icon edit / resize must
        repaint),
        whether writes are enabled (the launcher's NEW/DUP/DEL visibility), the
        active app's OWN `zone_gen` (Stage 4: an int the app bumps whenever ITS
        lent zone's content changes -- e.g. EditorApp.set_tab, Launcher.sel/
        set_items -- so a real zone-content change is the ONLY thing that forces a
        re-render beyond the shared dimensions here), and a generation counter the
        explicit invalidators bump (a bar placement, a journal flip)."""
        key = [None] * _KEY_N
        self._fill_key(key, where, self._bar_canvas(where), _KEY_ALL, None)
        return tuple(key)

    def _fill_key(self, key, where, cv, need, blk):
        """Write `_cart_bar_key`'s fields into `key` in place: the ones `need`
        names (a bit per field), plus the shared ones every bar folds. The
        frame's draw fills `where`'s one list with only what the bars on show
        draw, so a painted frame allocates no key and reads no state it does
        not show; a field it skips keeps the value no bar compares. Each
        field then goes to `blk`, `where`'s block in the engine
        (`_block_set`), which knows the fields that moved since a strip
        drew them; None sets none (a key asked for alone)."""
        ws = self.ws
        key[0] = where
        if need & 2:
            key[1] = self.clock_text()
        if need & 4:
            key[2] = _ui_draw.marks_on()
        key[3] = ws.look.look_gen
        key[4] = getattr(cv, "font_scale", 1)
        if need & 32:
            key[5] = bool(ws.can_manage)
        if need & 64:
            owner = self._zone_owner(where)
            key[6] = owner.zone_gen if owner is not None else 0
        if need & 128:
            key[7] = ws.wifi_icon_kind()      # the wifi status glyph
        if need & 256:
            # the tool bar's title (a registered app's: its top page's)
            t = self._title(where) if ws.cart else self.page_named(key[0])
            k8 = self._k8
            if k8[0] != t:
                k8[0] = t
                k8[1] = (k8[1] + 1) & 0x3fffffff   # (the block's field: made again)
            key[8] = t
        if need & _KEY_UNDO:
            # #111: the local op-history dim state (RAM-only; journal flips
            # invalidate explicitly)
            key[9] = ws.history.bar_undo_bits()
        key[10] = self._bar_cache_gen
        key[12] = self.focus_item if self.focus_where == where else None
        if need & 2048:
            m = getattr(ws, "sysmenu", None)       # the system button's open plate
            key[11] = m is not None and m.open and m.widget == "menu"
        if need & 8192:
            key[13] = self._status_key()
        if need & _KEY_CHIPS:
            g = getattr(ws.wm, "chips_gen", None)
            key[14] = g() if g is not None else 0
        if blk is not None:
            for i in range(_KEY_N):
                # (the title by the count of times it moved)
                _block_set(blk, i, self._k8[1] if i == 8 else key[i])

    def _status_key(self):
        """Key field 13: the status items' generation, and which bar item is
        selected (its popover open): 1 the control center (the `battery`
        widget's, on a handheld), 2 + k item k's menu (the desk), 0 none."""
        m = getattr(self.ws, "sysmenu", None)
        sel = 0
        if m is not None and m.open:
            if m.widget == "battery" and self._cluster():
                sel = 1
            elif m.widget == "status":
                sel = 2 + self.ws.status_open_k
        return (_ITEMS.gen * 8 + sel) * 4 + self._battery_state()

    def _battery_state(self):
        """The battery glyph's state: 0 as drawn, 1 low (under LOW_BATTERY
        percent), 2 charging, where the board's gauge reads them."""
        ws = self.ws
        if ws.battery_charging():
            return 2
        lvl = ws.battery_level()
        return 1 if lvl is not None and lvl < LOW_BATTERY else 0

    def _cluster(self, game=False):
        """Whether the bars hold a handheld's status cluster: the status
        items, Wi-Fi and battery, one focus stop opening the control center."""
        return not game and _layout_base.metric_class() != _layout_base.DESK

    def _render_cart_bar(self, cv, key, i=0):
        """Bar `i` (`_render_bar`), and the focus mark on the item the keys
        are on where it is in this bar (`focus_item`, key field 12): the
        pill, its plate under the item and its ring round it."""
        f = key[12]
        pill = self._pill(key[0], i, f) if f is not None and f[0] == i \
            and self._page_stop(key[0], f) is None else None
        self._render_bar(cv, key, i)
        if pill is not None:
            _ui_draw.focus(cv, self.ws.theme_colors, pill[0], r=pill[1], fs=pill[2],
                           after=True, pill=True)

    def _render_cart_part(self, cv, key, i, part, old):
        """Bar `i`'s strip drawn again where the fields `part` (a bit each,
        `_KEY_PARTS`) show: its zone (field 6, its owner's generation) and
        the focus pill's plate and ring where they were (`old`, the item
        the keys were on at the last draw) and where they are (field 12),
        the bar's pixels under them put back (`_render_bar` inside the
        rect alone)."""
        where = key[0]
        packed = self._packed(where)[i]
        bar = (0, 0, packed[1][2], packed[1][3])
        rect = None
        fs = self.ws.layout.fs
        if part & (1 << 6):
            # (the zone's span, the bar's full height: the open tab's mark
            # lies on the bar's edge past the zone)
            z = self.lent_zone(where, packed)
            # (a bar with a title cell and no zone shows the field too: whole)
            rect = bar if z is None else (z[0] - 2 * fs, 0, z[2] + 4 * fs, bar[3])
        if part & _KEY_CHIPS:
            for c in packed[3]:
                if c[0] == "chips":
                    rect = _union(rect, self._chips_span(c[1], packed))
        f = key[12]
        pill = self._pill(where, i, f) if f is not None and f[0] == i \
            and self._page_stop(where, f) is None else None
        for it in (old, f):
            if it is not None and it[0] == i:
                if it is not f or pill is None:
                    if self._page_stop(where, it) is not None:
                        # the page's mark: its bar item's pill and ring, the bar's height
                        r = it[1]
                        m = bar[3] // 2
                        rect = _union(rect, (r[0] - m, 0, r[2] + 2 * m, bar[3]))
                        continue
                p = pill if it is f else self._pill(where, i, it)
                b = p[0]
                m = 2 * p[2] + 2 * fs
                rect = _union(rect, (b[0] - m, b[1] - m, b[2] + 2 * m, b[3] + 2 * m))
        if rect is None:
            return
        rect = _cut(rect, bar)
        if rect[2] <= 0 or rect[3] <= 0:
            return
        cv.clip(rect[0], rect[1], rect[2], rect[3])
        self._render_bar(cv, key, i, None, rect)
        if pill is not None:
            _ui_draw.focus(cv, self.ws.theme_colors, pill[0], r=pill[1], fs=pill[2],
                           after=True, pill=True)
        cv.clip()

    def _pill(self, where, i, item):
        """(box, radius, unit) of the focus pill on `item` (`focus_items`)
        in bar `i`, in its bar's coordinates. An OS widget's is one height on
        every widget, the system tile's and a ring either side, centred
        across the bar: as wide as the tile and its ring on the system
        button, as a status icon and a ring and a unit either side, as the
        clock's digits and a ring and a unit either side, inside the bar.
        On the zone's targets, the back chevron and the row it is
        their rect and a ring round it."""
        _bi, r, name = item
        packed = self._packed(where)[i]
        bar = packed[1]
        bar = (0, 0, bar[2], bar[3])
        u = _layout_base.unit()
        fs = self.ws.layout.fs
        rad = 5 * fs
        across = packed[0] in ("left", "right")
        if name == "cluster" and not across:
            got = self._cluster_box(packed[3])
            if got is not None:
                return got, 6 * fs, u
        t = 4 * u
        if across or name not in ("menu", "wifi", "battery", "clock"):
            y0 = max(0, r[1] - t)
            y1 = min(bar[3], r[1] + r[3] + t)
            return (r[0] - t, y0, r[2] + 2 * t, y1 - y0), rad, u
        thick = bar[3]
        tile = self.sys_tile(r, bar, False)
        h = min(thick, tile[3] + 2 * t)
        y = (thick - h) // 2
        if name == "menu":
            return (tile[0] - t, y, tile[2] + 2 * t, h), rad, u
        if name == "clock":
            w = _ui_draw.print_width(self.clock_text(), fs)
            x0, x1 = r[0] - t - u, r[0] + w + t + u
        else:
            side = 16 * u + 2 * (t + u)
            x0 = r[0] + (r[2] - side) // 2
            x1 = x0 + side
        x1 = min(x1, bar[2])
        return (x0, y, x1 - x0, h), rad, u

    def _render_bar(self, cv, key, i=0, pill=None, only=None):
        """Render bar `i`'s pixels onto `cv` (the offscreen strip, or any canvas)
        for `key[0]` (`where`), in bar coordinates. The pieces are the kernel's
        strip (native/moy_play/moy_chrome.c: a widget's cell) and the
        toolkit's band, the one body every bar draws with; the lent zone is its
        app's. Factored out of _draw_top_bar_cart so the SAME drawing serves
        the cache build and the direct path. `only`, a rect in the bar,
        draws the cells and the zone that meet it alone (`_render_cart_part`,
        the canvas clipped to it)."""
        ws = self.ws
        where = key[0]
        mp = _ch.chrome_inks(ws.theme_colors, self._NAMES)
        packed = self._packed(where)[i]
        edge, rect, dy, cells = packed
        game = self.zone_is_game(where)
        # Part 4: a TOOL/APP runs WITH a minimal bar so it's EXITABLE: the OS
        # widgets, its TITLE in the zone (no tab ladder, no draw_zone: the
        # play-frame guardrail holds). Every other bar is the zoned bar: the
        # band (a window's light toolbar under a light theme), the OS widgets
        # -- suppressed inside a window (#73), whose WM title strip carries
        # min/max/close -- then the active app's LENT zone.
        tool = where in ("tool", "app")
        light = False if tool else self.zone_band_light(where)
        inside = self._in_window(where)
        looked = not game and not inside
        bar = (0, 0, rect[2], rect[3])
        if not looked:
            _ui_draw.frame_band(cv, ws.theme_colors, bar, light, _BAND_SIDE[edge])
        elif not self._home_ground(cv, where, -rect[0], -rect[1]):
            _ui_draw.bar_part(cv, ws.theme_colors, _band_part(), bar, _BAND_SIDE[edge])
        if pill is not None:
            # the focus pill's plate, under the item it marks
            _ui_draw.focus(cv, ws.theme_colors, pill[0], r=pill[1], fs=pill[2], pill=True)
        if not inside:
            cs = 0 if game else ws.layout.cs
            across = edge in ("left", "right")
            show_x = self.show_x(where)
            # (a page marks an open status item; a handheld's open cluster is the bar's)
            sel = None if game or across or (looked and not self._cluster(game)) \
                else self._selected_box(where, cells)
            if sel is not None:
                # the bar item whose popover is open: selected, the tabs' fill
                fs = ws.layout.fs
                _ui_draw.current(cv, ws.theme_colors, sel, r=5 * fs, fs=fs)
            if looked:
                self._page_draw(cv, where, bar, edge, cells, only)
            else:
                for name, r, text, _slot in cells:
                    if name in _PAINTED and (show_x or name != "close"):
                        if only is not None and not _meets(r, only):
                            continue
                        self._paint_cell(cv, mp, where, name, r, text, cs, dy, across, game)
        zone = self.lent_zone(where, packed)
        if zone is None or (only is not None and not _meets(zone, only)):
            return
        back = self.draws_back(where)
        owner = self._zone_owner(where)
        if tool:
            if back and owner is not None:
                # the title, then the row the app's page lends (`BarZone`)
                self._paint_back_title(cv, self._title_zone(where, zone), self._title(where),
                                       bar, game)
                owner.draw_zone(cv, self._row_zone(where, zone, bar, game))
                return
            if back:
                self._paint_back_title(cv, zone, self._title(where), bar, game)
                return
            _ch.replay(mp.chrome_strip_cell("title", zone, 0, dy, self._title(where), False),
                       cv, ws)
            return
        if owner is not None:
            title = getattr(owner, "back_title", None) if back else None
            if title:
                self._paint_back_title(cv, zone, title, bar, game)
                return
            if back:
                self._paint_back_title(cv, zone, None, bar, game)
                zone = self.past_back(zone, game)
            owner.draw_zone(cv, zone)

    # -- the bar page (runtime/shell/bar_ui.py) ----------------------------------------

    def _page_draw(self, cv, where, bar, edge, cells, clip=None):
        """The themes' bar's widgets drawn by the bar page (`bar_engine.draw`)
        at `bar` on `cv` (its strip, or the canvas it lies on), `clip` the
        part drawn again; the page's canvases are `_page_paint`'s."""
        names, cw, sys_w, n_items = self._page_names(cells)
        ws = self.ws
        L = ws.layout
        at = self._page_at
        at[0], at[1], at[2] = where, bar, cells
        paint = self._page_painter
        if paint is None:
            paint = self._page_painter = self._page_paint
        _bar_ui.PAINT[0] = paint
        hooks = self._hooks
        if hooks is None:
            hooks = self._hooks = (self.page_tap, self._chip_tap, self._item_tap)
        _bar_ui.TAP[0], _bar_ui.CHIP[0], _bar_ui.ITEM[0] = hooks
        self._page_items(where)
        if "menu" in names:
            self._sys_plate(cv, bar, cells, clip, edge in ("left", "right"))
        if not _paged(edge, cells):
            _bar_engine.draw_shaped(cv, ws.theme_colors, bar, edge, cells, L.cs, L.fs, cw or L.clock_w,
                                    sys_w, n_items, ws.wifi_icon_kind(), self.clock_text(),
                                    self._battery_state() != 0, self._title(where), self.show_x(where),
                                    clip, self._wins())
            return
        f = self.focus_item
        focus = self._page_stop(where, f) if f is not None and self.focus_where == where else None
        _bar_engine.draw(cv, ws.theme_colors, bar, names, L.cs, L.fs, cw or L.clock_w, sys_w,
                         n_items, ws.wifi_icon_kind(), self.clock_text(), self._battery_state() != 0,
                         clip, self._wins(), focus)

    def _sys_plate(self, cv, bar, cells, clip, across=False):
        """The system button's plate under the page's `menu` item: the
        theme's own part on its tile (`sys_tile`) in the item's cell,
        pressed while the system menu shows; nothing where `clip`, the part
        drawn again, misses it."""
        got = self._plate_at
        if got[0] is not cells or got[1] != bar[0] or got[2] != bar[1] or got[3] != bar[3]:
            r = None
            for c in cells:
                if c[0] == "menu":
                    r = c[1]
                    break
            if r is None:
                got[4] = None
            else:
                tx, ty, tw, tht = self.sys_tile(r, (0, 0, bar[2], bar[3]), across)
                got[4] = (tx + bar[0], ty + bar[1], tw, tht)
            got[0], got[1], got[2], got[3] = cells, bar[0], bar[1], bar[3]
        box = got[4]                    # (kept while the packing and the bar's place stand)
        if box is None:
            return
        tx, ty, tw, tht = box
        if clip is not None and (clip[0] >= tx + tw or tx >= clip[0] + clip[2]
                                 or clip[1] >= ty + tht or ty >= clip[1] + clip[3]):
            return
        m = self.ws.sysmenu
        part = _ui_draw.BAR_HH_SYS if _band_part() == _ui_draw.BAR_HH_BAND else _ui_draw.BAR_SYS
        _ui_draw.bar_part(cv, self.ws.theme_colors, part, box, m.open and m.widget == "menu")

    def page_tap(self, name):
        """The bar page's open of an OS widget (`bar_ui.TAP`): its component,
        the control center for any of a handheld's cluster; the clock's tap
        also counts toward its Easter egg."""
        ws = self.ws
        if name == "clock":
            ws.ach_ui._tap_clock()
        else:
            ws.ach_ui._clock_taps = 0
        ws.widget_tap("battery" if name in _CLUSTER and self._cluster() else name)

    def _chip_tap(self, kind):
        """The bar page's tap of a window's chip (`bar_ui.CHIP`): the window
        manager's."""
        tap = getattr(self.ws.wm, "chip_tap", None)
        if tap is not None:
            tap(kind)

    def _item_tap(self, k):
        """The bar page's open of status item `k`'s menu (`bar_ui.ITEM`)."""
        it = _ITEMS.at(k)
        if it is not None:
            self.ws.notices.open_status_menu(it)

    def _page_stop(self, where, item):
        """The id of the bar page's stop under focus item `item` of
        `where`'s bars (`focus_items`), or None where the page draws no stop
        there (the zone's targets, a handheld's cluster, a hand-drawn
        battery, a bar the page does not draw)."""
        name = item[2]
        if name not in _PAGE_STOPS:
            return None
        bar = self._packed(where)[item[0]]
        if not _paged(bar[0], bar[3]) or self._in_window(where):
            return None
        if name == "status":
            rects = self.page_item_rects(bar, self._stop_rects)
            x = item[1][0]
            for k in range(len(rects)):
                if rects[k][0] == x:
                    return _bar_engine.item_key(k)
            return None
        if name == "chip":
            x = bar[1][0] + item[1][0]
            for k, r in self.page_chip_rects(bar, self._chip_stops) or ():
                if r[0] == x:
                    return _bar_engine.chip_key(k)
            return None
        if name == "battery" and self._battery_state():
            return None
        return name

    def _page_fire(self, where, item):
        """The bar page's action of the stop under focus item `item`, run
        as the page runs it on a confirm: True, or False where the page
        draws no stop there."""
        stop = self._page_stop(where, item)
        if stop is None:
            return False
        _bar_engine.fire(stop)
        return True

    def _page_items(self, where):
        """What the bar page's status items show beyond the items: which one's
        menu is open (`bar_engine.SEL`) and the look's paused ink
        (`bar_engine.PAUSED`)."""
        m = getattr(self.ws, "sysmenu", None)
        _bar_engine.SEL[0] = self.ws.status_open_k \
            if m is not None and m.open and m.widget == "status" and not self._in_window(where) else -1
        _bar_engine.PAUSED[0] = self.ws.look.live.tones.get("paused", "ink_dim")

    def page_item_rects(self, bar, out):
        """The status items of packed bar `bar` placed by the bar page,
        their rects in the bar's coordinates in the items' order into `out`,
        or None where the page does not draw that bar (`_paged`)."""
        edge, rect, _dy, cells = bar
        names, cw, sys_w, n_items = self._page_names(cells)
        L = self.ws.layout
        if not _paged(edge, cells):
            return _bar_engine.shaped_item_rects(rect, edge, cells, L.cs, L.fs, cw or L.clock_w, sys_w,
                                                 n_items, out)
        return _bar_engine.item_rects(rect, names, L.cs, L.fs, cw or L.clock_w, sys_w, n_items, out)

    def _status_boxes(self, bar, r, n):
        """The boxes of the `n` status items of status cell `r` in packed
        bar `bar`: the bar page's where it draws that bar, else the
        stride's (`_status_x`)."""
        got = self.page_item_rects(bar, []) if bar is not None else None
        if got is not None:
            return got
        x, side, step = self._status_x(r, n)
        return [(x + k * step, r[1], side, side) for k in range(n)]

    _names_of = (None, None)
    _page_painter = None            # `_page_paint` bound once

    def _page_names(self, cells):
        """A packed bar's widgets as the page takes them: their names, the
        clock's, the system button's widths and the status items' count;
        the same answer (its names the same list) while `cells` stands."""
        got = self._names_of
        if got[0] is cells:
            return got[1]
        got = self._names_of = (cells, self._names_made(cells))
        return got[1]

    @staticmethod
    def _names_made(cells):
        names = []
        cw = sys_w = n_items = 0
        for name, r, text, _slot in cells:
            names.append(name)
            if name == "clock":
                cw = r[2]
            elif name == "menu":
                sys_w = r[2]
            elif name == "status":
                n_items = text or 0
        return names, cw, sys_w, n_items

    def _wins(self):
        """The chips' rows, the window manager's (`chip_model`), else None."""
        wm = self.ws.wm
        return wm.chip_model() if hasattr(wm, "chip_model") else None

    def page_chip_rects(self, bar, out):
        """The chips of packed bar `bar` placed by the bar page, [(kind,
        rect)] on the root canvas into `out`, or None where the page does
        not draw that bar (`_paged`)."""
        edge, rect, _dy, cells = bar
        names, cw, sys_w, n_items = self._page_names(cells)
        L = self.ws.layout
        if not _paged(edge, cells):
            return _bar_engine.shaped_chip_rects(rect, edge, cells, L.cs, L.fs, cw or L.clock_w, sys_w,
                                                 n_items, self._wins() or [], out)
        return _bar_engine.chip_rects(rect, names, L.cs, L.fs, cw or L.clock_w, sys_w, n_items,
                                      self._wins() or [], out)

    def _page_again(self, cv, where, bar, span):
        """The bar page drawn again over `span` (bar coordinates) of `bar`
        (a packed bar) on the canvas it lies on, whose ground there is
        fresh (`repaint_cell`)."""
        edge, (bx, by, bw, bh), _dy, cells = bar
        clip = (bx + span[0], by + span[1], span[2], span[3])
        cv.clip(clip[0], clip[1], clip[2], clip[3])
        try:
            self._page_draw(cv, where, (bx, by, bw, bh), edge, cells, clip)
        finally:
            cv.clip()

    def _page_paint(self, name, cv, x, y, w, h):
        """A canvas of the bar page (the hand-drawn battery) through its
        painter in the bar's coordinates (the page is drawn at the bar's
        origin on `cv`)."""
        at = self._page_at
        bar, cells = at[1], at[2]
        ox, oy = _bar_engine._ORIGIN
        box = (0, 0, bar[2], bar[3])
        if ox or oy:
            cv.camera(-ox, -oy)
        try:
            x -= ox
            for c in cells:
                if c[0] == name:
                    break
            else:
                return
            if name == "close":
                if _bar_engine.SHOW_X[0]:
                    side = 16 * self.ws.layout.cs
                    self.ws.draw_icon("close", (x + (w - side) // 2, y - oy + (h - side) // 2, side, side),
                                      self.ws.theme_colors["chrome_ink"], cv)
            elif name == "battery":
                u = self.ws.layout.cs              # the page's unit
                side = 16 * u
                gy = (box[3] - side) // 2 if w < box[3] else y - oy + (h - side) // 2
                self._battery_glyph(cv, x + (w - side) // 2, gy, side, u, self._battery_state())
        finally:
            if ox or oy:
                cv.camera(0, 0)

    # -- the way back (docs/history/look_2026-10.md step 27a) --------------------------
    #
    # Back goes one level; a window's X closes it. A bar shows the way back
    # wherever there is somewhere to go (`_way_back`): as the back chevron at
    # the head of its zone, or as the `close` widget's X where its layout
    # places one (the themes without a look). The chevron, Esc and B do the
    # same thing.

    def _way_back(self, where):
        """Whether `where` has somewhere to go back to. The desk is desktop
        mode's floor and never has; the home has where the back-stack is
        deeper than its mode's floor -- console mode on a P4, whose desk waits
        beneath it -- and not where it is the floor."""
        if where == "desk":
            return False
        if where == "home":
            wm = self.ws.wm
            return wm.stack.depth() > wm.floor()
        return True

    def draws_back(self, where):
        """Whether `where`'s bar draws the back chevron at the head of its
        zone: where it has a way back and its bar places no `close`, outside
        a window (whose title strip carries close), beside a zone that draws
        (a running tool's, or one an owner lends): the pause menu's bar has
        no zone, so neither chevron, tap target nor key stop. The Editor's
        one bar draws none: Esc and B step back (EDITOR_LAYOUT.md's handheld)."""
        return (where != "menu" and not self._in_window(where) and self._way_back(where)
                and self.cell(where, "close") is None
                and (where in ("tool", "app") or self._zone_owner(where) is not None))

    def _back_w(self, game):
        """The width the chevron takes at the head of a zone: its square and
        the bar's 2-pixel pitch, what the X it replaces took."""
        u = 1 if game else _layout_base.unit()
        return 18 * u

    def past_back(self, zone, game=False):
        """`zone` less the chevron at its head: the rect its owner draws and
        hit-tests in when the bar draws the way back."""
        bw = self._back_w(game)
        return (zone[0] + bw, zone[1], max(0, zone[2] - bw), zone[3])

    def back_rect(self, where):
        """The chevron's tap target on `where`'s canvas, (x, y, w, h): the head
        of its zone; None where the bar draws no chevron."""
        if not self.draws_back(where):
            return None
        got = self.cell(where, "zone")
        if got is None:
            return None
        bar, (x, y, w, h) = got
        return (bar[1][0] + x, bar[1][1] + y,
                min(w, self._back_w(self.zone_is_game(where))), h)

    def go_back(self, where):
        """The chevron's tap: back one level from `where` -- what Esc and B
        do there (`InputPolicy.back`); the home's goes to the desk."""
        ws = self.ws
        if where == "home":
            ws.home.open_desk()
        else:
            ws.input_policy.back()
        ws.mark_dirty()

    def _paint_back_title(self, cv, r, title, bar, game=False):
        """A page's place in the bar (DESIGN.md, Bar): the back chevron in
        the zone's first square, then the page's title (None: none) in the
        `title` face, in the chrome ink. Where the title ends, in bar
        coordinates."""
        ws = self.ws
        ink = ws.theme_colors["chrome_ink"]
        x, _y, w, _h = r
        thick = bar[3]
        u = 1 if game else _layout_base.unit()
        side = 16 * u
        gy = (thick - side) // 2
        if not ws.draw_icon("back", (x, gy, side, side), ink, cv):
            _ch.glyph(cv, "arr_l", (x, gy, side, side), ink, u)
        if not title:
            return x + side
        tf = _ui_draw.font("title")
        fs = 1 if game else ws.layout.fs
        sc = 1 if game else max(fs, (16 * fs) // max(1, tf[2]))   # a heading, 16 rows
        was = _ui_draw.print_font(tf[0])
        tx = x + side + 6 * u
        s = _ui_draw.print_cut(title, max(0, x + w - tx), sc)
        if game:                       # the fixed 320x240 strip: the face's own size
            cv.print(s, tx, (thick - tf[2]) // 2, ink, 1)
        else:
            cv.print_scaled(s, tx, (thick - tf[2] * sc) // 2, ink, sc)
        end = tx + _ui_draw.print_width(s, 1 if game else sc)
        if was is not None:
            _ui_draw.print_font(was)
        return end

    # -- the title the app's top page names -----------------------------------

    def _page_ctx(self, where):
        """The ui context whose top page names `where`'s bar: the running app
        cart's ("tool"), the registered app's on top ("app"), else None."""
        ws = self.ws
        if where == "tool":
            return ws.run.player.face.page_ctx()
        if where == "app":
            app = ws.app(ws.wm.top_kind())
            return app.page_ctx() if getattr(app, "UI", False) else None
        return None

    def page_named(self, where):
        """The title of the top page the app on `where`'s bar opened in its
        last frame (`ui.page`), "" for none."""
        ctx = self._page_ctx(where)
        return _ui_draw.page_title(ctx) if ctx is not None else ""

    def _title_end(self, where, zone, bar, game):
        """Where the back chevron's title ends in bar coordinates: what the
        row a page lends the bar follows."""
        ws = self.ws
        u = 1 if game else _layout_base.unit()
        tf = _ui_draw.font("title")
        fs = 1 if game else ws.layout.fs
        sc = 1 if game else max(fs, (16 * fs) // max(1, tf[2]))
        was = _ui_draw.print_font(tf[0])
        tx = zone[0] + 16 * u + 6 * u
        s = _ui_draw.print_cut(self._title(where), max(0, zone[0] + zone[2] - tx), sc)
        end = tx + _ui_draw.print_width(s, 1 if game else sc)
        if was is not None:
            _ui_draw.print_font(was)
        return end

    # The room between an app's title and the row its page lends, at unit 1.
    ROW_GAP = 10

    def _title_zone(self, where, zone):
        """The part of `where`'s zone the back chevron and the app's title
        take when its page lends the bar a row: the zone less the room the
        row needs as icons (`zone_need`), so the title is cut before a cell
        of the row is."""
        need = self._zone_owner(where).zone_need(zone[3])
        if not need:
            return zone
        gap = self.ROW_GAP * _layout_base.unit()
        return (zone[0], zone[1], max(0, zone[2] - need - gap), zone[3])

    def _row_zone(self, where, zone, bar, game):
        """Where the row an app's page lends the bar (its `BarZone`) stands,
        in bar coordinates: after the back chevron's title, to the zone's
        end. The draw, the key walk and a tap take it from here."""
        tz = self._title_zone(where, zone)
        x = self._title_end(where, tz, bar, game) + self.ROW_GAP * _layout_base.unit()
        return (x, zone[1], max(0, zone[0] + zone[2] - x), zone[3])

    def _paint_cell(self, cv, mp, where, name, r, text, cs, dy, across, game):
        """One OS widget's cell, through the kernel's painter."""
        ws = self.ws
        s = None
        if name == "status":
            if text:
                self._game_status(cv, r, text)
            return
        if name == "clock":
            s = self.clock_text()
            if across:
                L = ws.layout
                fw = 8 if game else L.font_w
                lh = 8 if game else L.line_h
                r = (r[0] + (r[2] - 2 * fw) // 2, r[1] + (r[3] - 2 * lh) // 2,
                     2 * fw, 2 * lh)
        elif name == "wifi":
            s = ws.wifi_icon_kind()
            if s != "wifi":            # off is the quiet state: no glyph
                return
        elif name == "title":
            s = self._title(where)
        elif name == "text":
            s = text
            if across:
                tw = _bar_text_w(s) * (1 if game else ws.layout.fs)
                r = (r[0] + (r[2] - tw) // 2, r[1], tw, r[3])
        _ch.replay(mp.chrome_strip_cell(name, r, cs, dy, s, across), cv, ws)

    def _battery_glyph(self, cv, x, y, side, u, st):
        """The battery low (`st` 1: its body all in the danger ink, a sliver
        of charge) or charging (2: a charge in the accent with a bolt cut out
        of it) in the `side`-square at (x, y), unit `u`."""
        th = self.ws.theme_colors
        ink = th["danger"] if st == 1 else th["chrome_ink"]
        cx, cy = x + side // 2, y + side // 2
        x0, x1 = cx - 7 * u, cx + 5 * u
        for k in range(u):
            cv.rectb(x0 + k, cy - 4 * u + k, x1 - x0 + u - 2 * k, 8 * u - 2 * k, ink)
        cv.rect(x1 + u, cy - u, 2 * u, 2 * u, ink)
        if st == 1:
            cv.rect(x0 + 2 * u, cy - 2 * u, 2 * u, 4 * u, ink)
            return
        cv.rect(x0 + 2 * u, cy - 2 * u, x1 - x0 - 3 * u, 4 * u, th["accent"])
        cut = th.get("bar", 0)
        for k, (dx, dy) in enumerate(((1, -2), (0, -1), (-1, 0), (0, 0), (1, 0), (0, 1))):
            cv.rect(cx + dx * u, cy + dy * u, u, u, cut)

    def _status_x(self, r, n, game=False):
        """(x of the first icon, icon side, stride) of the `n` icons of
        status cell `r`: right-aligned in it, past the cluster's ring room,
        a status gap apart (`shell_layout.pack`'s)."""
        side = r[3]
        L = self.ws.layout
        cs, fs = (1, 1) if game else (L.cs, L.fs)
        sg = max(2 * cs, 4 * fs)
        x0 = r[0] + r[2] - (n * side + max(0, n - 1) * sg)
        return x0, side, side + sg

    def _game_status(self, cv, r, n):
        """The apps' status items in their cell `r` of the kernel's strip
        over a game: each its bar icon in its state's ink (the accent, the
        paused ink, the danger ink)."""
        ws = self.ws
        th = ws.theme_colors
        x, side, step = self._status_x(r, n, True)
        for k in range(n):
            it = _ITEMS.at(k)
            if it is None:
                break
            st = it.state
            ink = th["danger"] if st == _ERROR else \
                ws.look.content_colors().get("paused", th["ink_dim"]) if st == _PAUSED \
                else th["accent"]
            ws.icon(it.icon, x, r[1], cv, scale=max(1, side // 16), ink=ink)
            x += step

    def status_hit(self, r, n, px, bar=None):
        """The index of the status item under bar x `px` in status cell `r`
        holding `n` of packed bar `bar`, or None."""
        if not n:
            return None
        boxes = self._status_boxes(bar, r, n)
        for k in range(len(boxes)):
            b = boxes[k]
            if b[0] <= px < b[0] + b[2]:
                return k
        return None

    def _cluster_box(self, cells):
        """The handheld's status cluster's focus ring, (x, y, w, h) in its
        bar's coordinates: RING_ROOM out from the ink of the items, Wi-Fi
        and battery across, three units out from their icons' row down."""
        fs = self.ws.layout.fs
        u = _layout_base.unit()
        x0 = x1 = None
        y = side = 0
        paged = _paged("top", cells)        # (a cluster stands on a top or bottom bar)
        for name, r, text, _slot in cells:
            if paged and name in _CLUSTER:
                a, b = r[0], r[0] + r[2] - 1            # the page's cells: each its ink wide
            elif name == "status" and text:
                a = self._status_x(r, text)[0] + u
                b = a
            elif name in ("wifi", "battery"):
                a, b = self._ink(name, r)
            else:
                continue
            x0 = a if x0 is None else min(x0, a)
            x1 = b if x1 is None else max(x1, b)
            y, side = r[1], r[3]
        if x0 is None:
            return None
        o = _RING_ROOM * fs
        t = 3 * fs
        return (x0 - o, y - t, x1 - x0 + 1 + 2 * o, side + 2 * t)

    def _selected_box(self, where, cells):
        """The box of the bar item whose popover is open, which wears the
        selected fill: the cluster (the control center) on a handheld, a
        status item (its menu) on the desk. None for none."""
        m = getattr(self.ws, "sysmenu", None)
        if m is None or not m.open or self._in_window(where):
            return None
        if m.widget == "battery" and self._cluster():
            return self._cluster_box(cells)
        if m.widget != "status":
            return None
        k = self.ws.status_open_k
        for name, r, text, _slot in cells:
            if name == "status" and text and 0 <= k < text:
                x, side, step = self._status_x(r, text)
                u = _layout_base.unit()
                return (x + k * step - 3 * u, r[1] - (3 * u) // 2, side + 6 * u, side + 3 * u)
        return None

    def _ink(self, name, r):
        """(first, last) column of status widget `name`'s ink in its cell `r`
        of a horizontal bar, as a bar page draws it: an icon's from
        its set's mask (the wider of Wi-Fi's two states), the fallback
        battery's from its outline, the clock's its cell."""
        x, _y, w, _h = r
        if name == "clock":
            return (x, x + w - 1)
        u = _layout_base.unit()
        side = 16 * u
        gx = x + (w - side) // 2
        sp = self.ws.icon_spec()
        kinds = ("wifi", "wifi_off") if name == "wifi" else (name,)
        a = b = None
        for k in kinds:
            got = _iconsets.ink_span(k, side, side, sp)
            if got is not None:
                a = got[0] if a is None else min(a, got[0])
                b = got[1] if b is None else max(b, got[1])
        if a is not None:
            return (gx + a, gx + b)
        side = 12 * u
        gx = x + (w - side) // 2
        if name == "battery":
            bx = gx + (side - 12 * u) // 2
            return (bx, bx + 12 * u - 1)
        return (gx, gx + side - 1)

    def sys_tile(self, r, bar, across):
        """The system button's tile in its cell `r` of bar rect `bar`: 36x34 on
        the desk's 40-row bar, 22x20 on the handheld's 28, in proportion on
        another (`layout_base.sys_tile`), centred in its cell and across the
        bar."""
        thick = bar[2] if across else bar[3]
        tw, th, _len = _layout_base.sys_tile(thick)
        if across:
            return ((thick - tw) // 2, r[1] + (r[3] - th) // 2, tw, th)
        return (r[0] + (r[2] - tw) // 2, (thick - th) // 2, tw, th)

    def _title(self, where):
        """The `title` widget's string: the page an app names (its
        `page_title()`), the running cart's or the open project's, else the
        surface's name."""
        ws = self.ws
        if where == "app":
            z = self._zone_owner(where)
            t = z.back_title if z is not None else None
            if t:
                return t                    # the title its page's row stands after
        t = self.page_named(where)
        if t:
            return t                        # its top page's
        if where == "app":
            kind = ws.wm.top_kind()
            app = ws.app(kind)
            t = app.page_title() if app is not None else None
            if t:
                return t                    # a page of the app names its own
            c = ws.app_carts.get(kind)
            if c is not None:
                return c.get("title") or ""     # the cart it was opened on
        if where in ("tool", "app", "menu") and ws.cart:
            return ws.cart.get("title") or ""
        if where == "home":
            return ws.home.home_title()
        return _TITLES.get(where, "")

    def show_x(self, where):
        """The `close` widget's X, where a layout places one: wherever there
        is a way back (`_way_back`)."""
        return self._way_back(where)

    def _home_ground(self, cv, where, x, y):
        """Paint the handheld home's backdrop under its bar where the look
        draws the bar with no band (`hhbar.style` none) and the home's
        ground is a backdrop of its own, not the `desktop` colour a band
        would fill (Blocks' sunflower; docs/history/look_2026-10.md step 26b): the
        screen's surface at (x, y) of `cv`, inside its clip. True when
        painted; no wallpaper is under a bar here."""
        ws = self.ws
        if where != "home" or _layout_base.metric_class() == _layout_base.DESK \
                or ws.look.wallpaper_id is not None:
            return False
        style = ws.look.live.look[0].get("hhbar.style")
        if style not in (None, 0, _NONE):
            return False
        rec = ws.look.backdrop("home")
        if not rec:
            return False
        if ws.wallpaper.put_baked(cv, rec, x, y):
            return True
        sc = ws.sys_canvas
        cv.backdrop(rec, ws.theme_colors["desktop"], surface=(x, y, sc.w, sc.h))
        return True

    def repaint_cell(self, where, name, span=None):
        """Paint the ground of cell `name` of an already-drawn bar again: the
        band the strip itself draws (the light-theme in-window band is a
        different token), minus its edge line so the repaint can never eat
        it. What draws in the cell next lands on fresh pixels -- the clock
        over its old digits, the taskbar chips' labels and corners, which
        blend. `span(cell, bar)`, where given, names the rect in the bar
        to paint instead: what draws there reaches past its cell. (canvas,
        bar, cell rect on the canvas, whether the look drew the band), or
        None where no bar places the cell."""
        cv = self._bar_canvas(where)
        if cv is None:
            return None
        got = self.cell(where, name)
        if got is None:
            return None
        bar, r = got
        g = self._ground_of(bar, span(r, bar) if span is not None else r)
        looked = self._paint_ground(cv, where, bar, g)
        return cv, bar, (r[0] + bar[1][0], r[1] + bar[1][1], r[2], r[3]), looked

    @staticmethod
    def _ground_of(bar, r):
        """Rect `r` of packed bar `bar` (bar coordinates) on its canvas, less
        the band's edge line, which a repaint never eats."""
        edge, (bx, by, bw, bh), _dy, _cells = bar
        cx, cy, cw, ch = r
        cx += bx
        cy += by
        if edge == "top":
            ch = min(ch, max(0, by + bh - 1 - cy))
        elif edge == "bottom":
            if cy == by:
                cy, ch = by + 1, ch - 1
        elif edge == "left":
            cw = min(cw, max(0, bx + bw - 1 - cx))
        elif cx == bx:
            cx, cw = bx + 1, cw - 1
        return (cx, cy, cw, ch)

    def _paint_ground(self, cv, where, bar, g):
        """The band the strip itself draws, again inside `g` (`_ground_of`) on
        `cv`: whether the look drew it."""
        edge, r = bar[0], bar[1]
        th = self.ws.theme_colors
        cv.clip(g[0], g[1], g[2], g[3])
        looked = not self.zone_is_game(where) and not self._in_window(where)
        if not looked:
            _ui_draw.frame_band(cv, th, r, self.zone_band_light(where), _BAND_SIDE[edge])
        elif not self._home_ground(cv, where, 0, 0):
            _ui_draw.bar_part(cv, th, _band_part(), r, _BAND_SIDE[edge])
        cv.clip()
        return looked

    def drop_strips(self, where):
        """Give back `where`'s cached strips: a bar shown only for a while
        (over the pause card) leaves nothing behind it."""
        bars = self._bar_strips.pop(where, None)
        for slots in bars or ():
            for slot in slots:
                if slot:
                    _release_layer(slot[0])
        self._keys.pop(where, None)

    def tile_on(self):
        """What of the bar's pixels an open popover selects: 1 the system
        button's tile (its menu is up), 2 + k status item k's cell (its
        menu), 0 none."""
        m = self.ws.sysmenu
        if not m.open:
            return 0
        if m.widget == "menu":
            return 1
        if m.widget == "status":
            return 2 + self.ws.status_open_k
        return 0

    def redraw_tile(self, where):
        """Repaint JUST the system button's cell of an already-drawn bar, its
        tile open or not as the menu now stands: the desk's change of it
        when the menu's scrim rides, or a cached desk that holds the other
        state."""
        got = self.repaint_cell(where, "menu", self._tile_span)
        if got is None:
            return
        cv, bar, (x, y, w, h), looked = got
        if not looked:
            return
        edge, (bx, by, bw, bh), _dy, cells = bar
        self._page_again(cv, where, bar, self._tile_span((x - bx, y - by, w, h), bar))
        self.strip_moved(cv, x, y, w, h)
        self._redraw_status(where)

    def _chips_span(self, cell, bar):
        """The chips' cell and the reach of their marks past it
        (`chip_reach`), in the bar (bar coordinates)."""
        return self.chip_reach(bar, cell)

    def chip_reach(self, bar, r):
        """Rect `r` of packed bar `bar` (a chip's, or the chips' cell, in
        the bar's coordinates) and the reach of the marks past it: five
        units each way along the bar, across its whole thickness (a mark
        lies on its edge line); down a side bar the whole bar, whose chips
        move what follows them down it."""
        bw, bh = bar[1][2], bar[1][3]
        if bar[0] in ("left", "right"):
            return (0, 0, bw, bh)
        u = 5 * self.ws.layout.fs
        a = max(0, r[0] - u)
        return (a, 0, min(bw, r[0] + r[2] + u) - a, bh)

    def lay_chips(self, where, r, also=None):
        """Rect `r` (on `where`'s canvas) of its bars laid again from their
        strips, brought current first: the chips there as the bar's one
        draw paints them (`_render_bar`, its chips' part drawn again when
        they moved, `_KEY_CHIPS`), so a rect laid over a bar drawn whole is
        byte for byte that bar. Onto `also` too, where given (the desk's
        cache of itself): False where the canvas keeps no strips (a
        RecordingLayer), which paints the bars there straight onto it and
        nothing onto `also`."""
        return self._draw_top_bar_cart(where, r, also)

    def _redraw_status(self, where):
        """Repaint the status items' cell of an already-drawn bar, the open
        menu's item selected as it now stands (`tile_on`)."""
        got = self.repaint_cell(where, "status", self._status_span)
        if got is None:
            return
        cv, bar, (x, y, w, h), looked = got
        edge, (bx, by, bw, bh), _dy, cells = bar
        if not looked or edge in ("left", "right"):
            return
        span = self._status_span((x - bx, y - by, w, h), bar)
        self._page_again(cv, where, bar, span)
        self.strip_moved(cv, span[0] + bx, span[1] + by, span[2], span[3])

    def _status_span(self, r, bar):
        """The status cell and the selected fill's reach past it, in its
        bar."""
        u = _layout_base.unit()
        return (r[0] - 3 * u, r[1] - 2 * u, r[2] + 6 * u, r[3] + 4 * u)

    def _tile_span(self, r, bar):
        """The system button's cell and its tile, whose corners reach past
        it, as one rect in its bar."""
        edge, (_bx, _by, bw, bh) = bar[0], bar[1]
        tx, ty, tw, th = self.sys_tile(r, (0, 0, bw, bh), edge in ("left", "right"))
        x0, y0 = min(r[0], tx), min(r[1], ty)
        x1, y1 = max(r[0] + r[2], tx + tw), max(r[1] + r[3], ty + th)
        return (x0, y0, x1 - x0, y1 - y0)

    def redraw_clock(self, where):
        """Repaint JUST the clock cell of an already-drawn bar (#155).

        Lets the desk backdrop cache survive a clock tick. The desk render is
        wallpaper cover-crop + icon column + this bar, ~77ms on the P4, and the
        clock is the only part of it that changes while nothing else does -- so
        without this, ticking the minute invalidated the whole cached desk once a
        second. The cell is the clock's own (no other widget's cell overlaps
        it, the taskbar chips stop short of it), so repainting it cannot erase
        them. A layout with no clock has nothing to repaint."""
        ws = self.ws
        got = self.repaint_cell(where, "clock")
        if got is None:
            return
        cv, bar, (x, y, w, h), looked = got
        edge, (bx, by, bw, bh), dy, _cells = bar
        th = ws.theme_colors
        text = self.clock_text()
        across = edge in ("left", "right")
        if looked:
            self._page_again(cv, where, bar, (x - bx, y - by, w, h))
        elif across:
            cv.camera(-bx, -by)
            mp = _ch.chrome_inks(th, self._NAMES)
            self._paint_cell(cv, mp, where, "clock", (x - bx, y - by, w, h), None,
                             ws.layout.cs, dy, True, False)
            cv.camera(0, 0)
        else:
            cv.print(text, x, by + 3 + dy, th["chrome_ink"], 1)
        if text != self._clock_drawn:
            self._clock_drawn = text
            self.strip_moved(cv, x, y, w, h)

    def clock_text(self):
        """The local HH:MM (`wallclock`: the console's time zone), or
        UNSYNCED while the clock does not hold real time -- a board before
        its first NTP answer, whose clock counts from power-on and would read
        as a time of day. The cart bar's cache KEY calls this every frame it
        paints (#66), so the clock is read when its text can next change --
        the next minute, or each second while unsynced -- and its strings are
        made only when it did."""
        now = _ticks_ms()
        if self.clock_at >= 0 and _ticks_diff(now, self.clock_at) < self._clock_hold:
            return self._clock_cache
        lt = _wc.localtime()
        if lt is None:
            self._date_cache = _NO_DATE
            self._clock_hm = (-1, -1)
            self._clock_cache = UNSYNCED
            self.clock_at = now
            self._clock_hold = 1000
            return UNSYNCED
        a, b = lt[3], lt[4]
        if lt[0] != self._date_cache[0] or lt[1] != self._date_cache[1] \
                or lt[2] != self._date_cache[2]:
            self._date_cache = (lt[0], lt[1], lt[2])
        if a != self._clock_hm[0] or b != self._clock_hm[1]:
            self._clock_hm = (a, b)
            self._clock_cache = "%02d:%02d" % (a, b)
        self.clock_at = now
        self._clock_hold = (60 - lt[5]) * 1000
        return self._clock_cache

    def today(self):
        """(year, month, day) from the clock's per-second read, (0, 0, 0)
        where there is no wall clock."""
        self.clock_text()
        return self._date_cache

    # -- the keys on the bar (owner call 2026-10-26) ---------------------------
    #
    # Up past the top of the surface under a bar walks focus onto the bar:
    # left and right walk its items, confirm opens one as a tap on it does,
    # down and back come off it. A lent row's cells are its items in their
    # places (the home's tabs and the Editor's among the OS widgets, owner
    # call 2026-10-27): the walk opens none, confirm opens one. A window's
    # bar keeps the desk's own ways.

    def focus_items(self, where):
        """The items the keys walk on `where`'s bars, left to right, as
        [(bar index, rect in its bar's coordinates, widget name or None)]:
        the OS widgets a tap opens, the back chevron, a running app's lent
        tools and the zone's own targets (`zone_targets`, where its owner
        names them)."""
        out = []
        if self._in_window(where):
            return out
        packed = self._packed(where)
        game = self.zone_is_game(where)
        show_x = self.show_x(where)
        back = self.draws_back(where)
        for bi in range(len(packed)):
            bar = packed[bi]
            rects = []
            cluster = None
            hh = self._cluster(game) and bar[0] in ("top", "bottom")
            for c in bar[3]:
                if hh and c[0] in _CLUSTER:
                    cluster = c[1] if cluster is None else _union(cluster, c[1])
                elif c[0] == "status":
                    n = c[2] or 0
                    if n:
                        for b in self._status_boxes(bar, c[1], n):
                            rects.append(((b[0], c[1][1], b[2], c[1][3]), "status"))
                elif c[0] in _TAPPED and (show_x or c[0] != "close"):
                    rects.append((c[1], c[0]))
            if cluster is not None:
                rects.append((cluster, "cluster"))
            if where == "desk":
                bx, by = bar[1][0], bar[1][1]
                for _k, r in self.page_chip_rects(bar, self._chip_stops) or ():
                    rects.append(((r[0] - bx, r[1] - by, r[2], r[3]), "chip"))
            zone = self.lent_zone(where, bar)
            if zone is not None:
                owner = self._zone_owner(where)
                if back:
                    rects.append(((zone[0], zone[1], self._back_w(game), zone[3]), None))
                if where in ("tool", "app"):
                    if back and owner is not None:
                        box = (0, 0, bar[1][2], bar[1][3])
                        for r in owner.zone_targets(self._row_zone(where, zone, box, game)):
                            rects.append((r, None))
                elif owner is not None and not (back and getattr(owner, "back_title", None)):
                    targets = getattr(owner, "zone_targets", None)
                    if targets is not None:
                        for r in targets(self.past_back(zone, game) if back else zone):
                            rects.append((r, None))
            rects.sort(key=lambda c: c[0][0])
            for r, name in rects:
                out.append((bi, r, name))
        return out

    def focus_enter(self, where, at=None, k=None):
        """The keys walk onto `where`'s bar: onto item `k`, else the item
        `at` (a bar-coordinate x the item spans), else the first. False
        where the bar has no such item."""
        items = self.focus_items(where)
        if k is None:
            k = 0
            if at is not None:
                for j in range(len(items)):
                    r = items[j][1]
                    if r[0] <= at < r[0] + r[2]:
                        k = j
                        break
        if not 0 <= k < len(items):
            return False
        self.focus_where = where
        if where == "home":
            self.ws.launcher_layer.bar_focus(True)
        self._focus_on(items, k)
        return True

    def _focus_on(self, items, k):
        if not items:
            self.focus_leave()
            return
        k = max(0, min(len(items) - 1, k))
        self.focus = k
        self.focus_item = items[k]
        _ui_draw.on_bar(True)
        self.ws.mark_dirty()

    def focus_leave(self):
        """The keys come off the bar, back to the surface under it."""
        where = self.focus_where
        self.focus = self.focus_where = self.focus_item = None
        _ui_draw.on_bar(False)
        ws = self.ws
        ws.mark_dirty()
        if where == "home":
            ws.launcher_layer.bar_focus(False)

    def focus_keys(self, i):
        """A frame's keys while they are on the bar: left and right walk
        its items, confirm opens the focused one (a tap at its middle) -- a zone's tab
        it opens takes the keys down into it (the owner's `zone_opened`) --
        down, back and stop come off it, up stays. True where they were the
        bar's."""
        where = self.focus_where
        items = self.focus_items(where)
        if not items or self.ws.router.bar_where() != where:
            self.focus_leave()
            return False
        if i.steps("left"):
            self._focus_on(items, self.focus - 1)
        elif i.steps("right"):
            self._focus_on(items, self.focus + 1)
        elif i.steps("down") or i.pressed("b") or i.pressed("stop"):
            self.focus_leave()
        elif i.pressed("a") or i.pressed("run"):
            bi, r, _name = items[max(0, min(len(items) - 1, self.focus))]
            bar = self._packed(where)[bi]
            mid = r[0] + r[2] // 2
            owner = self._zone_owner(where)
            if getattr(owner, "zone_opened", None) is not None:
                owner.zone_opened = False
            if not self._page_fire(where, items[max(0, min(len(items) - 1, self.focus))]):
                self._tap_bar(where, bar, mid, r[1] + r[3] // 2)
            ws = self.ws
            ws.mark_dirty()
            if ws.router.bar_where() != where or getattr(owner, "zone_opened", False):
                # the tap left the surface (back, a door), or opened one of
                # the zone's tabs, which takes the keys down into it
                self.focus_leave()
            else:
                # the item tapped (undo, a widget under its popover), the
                # nearest where the bar laid it out again
                items = self.focus_items(where)
                k = 0
                for j in range(len(items)):
                    q = items[j][1]
                    if abs(q[0] + q[2] // 2 - mid) < abs(items[k][1][0] + items[k][1][2] // 2 - mid):
                        k = j
                self._focus_on(items, k)
        elif not i.steps("up"):
            return False
        return True

    def handle_bar_tap(self, where, px, py):
        """The zoned bars' tap slice (Stage 4), shared by every screen they draw
        on: the clock Easter egg, the ≡ system menu, the wifi status icon, and
        the X (where a layout places one) are OS-owned, IDENTICAL wherever a bar shows them (same as
        the draw), checked first so a tap on any never falls through to the lent
        zone. Anything else on a bar routes to the active app's zone_tap over its
        lent zone. Returns True iff a bar (or the app's zone) consumed the tap.
        The clock-run reset runs for ANY non-clock tap (byte-identical to the
        pre-Stage-4 launcher pointer), so taps that fall through to the content
        still reset it. (px, py) are on `where`'s canvas; every cell is in its
        bar's coordinates."""
        if self.held:
            return False
        ws = self.ws
        for bar in self._packed(where):
            r = bar[1]
            if _in(px, py, r):
                return self._tap_bar(where, bar, px - r[0], py - r[1])
        ws.ach_ui._clock_taps = 0
        return False

    def _tap_bar(self, where, bar, px, py):
        ws = self.ws
        cells = bar[3]
        zone = self.lent_zone(where, bar)
        if self._in_window(where):
            # Inside a WM window (#73) the bar has NO OS widgets (suppressed in
            # the draw), so there is nothing OS-owned to hit -- the tap goes
            # straight to the app's lent zone; closing lives on the WM title strip.
            owner = self._zone_owner(where)
            return bool(owner.zone_tap(px, py, zone)) \
                if owner is not None and zone is not None else False
        hit = None
        cluster = None
        hh = self._cluster(self.zone_is_game(where)) and bar[0] in ("top", "bottom")
        for c in cells:
            if hh and c[0] in _CLUSTER:
                cluster = c if cluster is None else (c[0], _union(cluster[1], c[1]))
            if c[0] in _TAPPED and _in(px, py, c[1]):
                hit = c
                break
        if hit is None and cluster is not None and _in(px, py, cluster[1]):
            hit = cluster               # the gaps between the cluster's icons are its own
        name = hit[0] if hit is not None else None
        # Clock Easter egg (#21): tapping the bar's clock _CLOCK_TAP_GOAL times
        # wakes the Time Traveler; every tap also opens (or closes) its calendar.
        # Checked before the ≡/X/zone so a tap on the clock never falls through.
        if name == "clock":
            ws.ach_ui._tap_clock()
        else:
            ws.ach_ui._clock_taps = 0            # any other bar tap resets the run
        # The ≡, the clock, wifi and battery open their component
        # (docs/theme_and_shell_2026-11.md §8.6): the system menu as the popup it
        # is, the rest a popover hung from the widget, in both modes -- wifi's
        # the Settings WIFI panel, the one wifi implementation. Consumed, so a tap never
        # leaks to the lent zone.
        if name in _CLUSTER and self._cluster(self.zone_is_game(where)) \
                and bar[0] in ("top", "bottom"):
            ws.widget_tap("battery")         # the cluster opens the control center
            return True
        if name == "status":
            k = self.status_hit(hit[1], hit[2] or 0, px, bar)
            if k is not None:
                ws.notices.open_status_menu(_ITEMS.at(k))
            return True
        if name in ("clock", "menu", "wifi", "battery"):
            ws.widget_tap(name)
            return True
        # The X, where a layout places `close` (spec Section 9): tap to EXIT the active surface toward
        # its mode's root. On the home it leaves console mode for the desk beneath
        # (docs/theme_and_shell_2026-11.md §8.1); where the home is the floor it draws no X
        # and is not tested. A running TOOL (Part 4) pops to its RUN caller (spec
        # Section 6's test-play round trip -- go_home for a launcher-launched tool, but
        # the Editor tab if a tool is ever PLAYed from the editor); every other taskbar
        # app (Editor/Settings) uses the screen-string exit.
        if name == "close" and self.show_x(where):
            if where == "home":
                ws.home.open_desk()
            elif where in ("tool", "app"):
                ws.spine.exit_to_caller()
            else:
                ws.spine.exit()
            return True
        owner = self._zone_owner(where)
        if zone is not None and self.draws_back(where):
            game = self.zone_is_game(where)
            if zone[0] <= px < zone[0] + self._back_w(game):
                self.go_back(where)
                return True
            box = (0, 0, bar[1][2], bar[1][3])
            if where in ("tool", "app") and owner is not None:
                return bool(owner.zone_tap(px, py, self._row_zone(where, zone, box, game)))
            if owner is not None and not getattr(owner, "back_title", None):
                zone = self.past_back(zone, game)
        # Pass the SAME lent rect the draw used, in the bar coordinates (px, py) are
        # in now, so an app's zone_tap hit-tests its icons at the exact positions
        # draw_zone drew them wherever the bar sits.
        if owner is None or zone is None:
            return False
        return bool(owner.zone_tap(px, py, zone))

