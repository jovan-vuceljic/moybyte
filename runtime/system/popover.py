"""The bar widgets' popovers (docs/theme_and_shell_2026-11.md §8.6, the look's
step 33): each a component the popover (`widgets.Popup`) holds, hung from
its widget on every glass in the system's flat card with no wash (D-01),
its content on the public UI API's verbs.

  `clock`    MonthView   the month (`month_ui`'s page), today marked; left/right page
  `wifi`     WifiPanel   Settings' Wi-Fi page, the one implementation
  `battery`  PowerRows   on the desk: the battery's line, then Volume and
                         Brightness (`cc_ui`'s page)
             ControlCenter  on a handheld, opened by the status cluster:
                         the console's group, then each app's status rows
                         (`cc_ui`'s page)
  `status`   StatusMenu  on the desk: an app's status item's menu, its rows
                         (the same page)

The system menu is the popover's ROWS, not a component (`widgets.Popup`).

Every component's interface: `size()` -> (w, h) in pixels at the current
scales, the font scale on the desk too (its frame draws its rows at it),
`draw(cv, rect)` (the card is the popover's, `rect` inside it: shorter
than `size()` where the glass has less room under the bar, `popover_room`,
and the component's rows then tighten or scroll in it), `keys()`
-> the hint strip's keys on a handheld, `handle_input(i)` -> "local" when
only the panel's pixels moved, "global" when something outside it did,
None for nothing; `click(px, py, rect)` the same; `typing()` ->
True while typed keys are its own (B and ESC are then the text field's);
`closed()` on every close, a tap outside included.
"""

import ui_draw as _ui_draw
import layout_base as _lb
from status_items import ITEMS as _ITEMS, CAP as _CAP


def _desk():
    return _lb.metric_class() == _lb.DESK


def _pad(ws):
    return (12 if _desk() else 9) * ws.layout.fs


def _inner(ws, rect):
    """The rows' rect inside a popover's card: its padding off the card's
    top and foot, and the rows' own pad off its sides."""
    p = _pad(ws)
    x, y, w, h = rect
    return (x + p, y + p, w - 2 * p, h - 2 * p)


def _fit(ws, comp):
    """Size the popover to `comp` again where what it lists moved (the
    networks a scan found), within the glass's room: the
    next frame repaints at the new size (a mark made inside a draw is spent
    with it, so it asks for that frame)."""
    m = ws.sysmenu
    w, h = comp.size()
    h = min(h + _ui_draw.modal_drop(ws.sys_canvas), ws.popover_room())
    if m.comp is comp and m.size[1] != h:
        m.size = (m.size[0], h)
        ws.request_frame()


_MONTH_KEYS = ("change", "Month", "back", "Close")
_POWER_KEYS = ("change", "Change", "scroll", "Row", "back", "Close")
_WIFI_KEYS = ("confirm", "Join", "back", "Close")
_MENU_KEYS = ("change", "Button", "back", "Close")


class MonthView:
    """The `clock` widget's component: `month_ui`'s page, the month, today
    marked; the arrows (left/right, or a chevron on the desk and under
    touch) page months. The card keeps the height it opened at: a month
    paged to with more weeks tightens them into it."""

    def __init__(self, ws):
        self.ws = ws
        self.off = 0
        self.host = _ui_draw.AppHost()
        self.engine = None
        self.y = self.m = self.d = 0    # the month shown and its day marked (0 none)
        self._t = None                  # the date and paging they were made at
        self._off = 0
        self._wt = None                 # ... and the page was written at
        self._woff = 0

    def _sync(self):
        """The month paged to, made again where the date or the paging
        moved."""
        t = self.ws.bar_layer.today()
        if t is self._t and self.off == self._off:
            return
        self._t, self._off = t, self.off
        y, m, d = t
        if y and self.off:
            k = y * 12 + m - 1 + self.off
            y, m, d = k // 12, k % 12 + 1, 0
        self.y, self.m, self.d = y, m, d

    def size(self):
        ws = self.ws
        desk = _desk()
        fs = ws.layout.fs
        self._sync()
        h = _ui_draw.month_h(self.y, self.m, fs, desk) if self.y else 6 * 21 * fs
        return ((264 if desk else 200) * fs, 2 * _pad(ws) + h + (_foot(fs) if desk else 0))

    def month(self):
        """(year, month, the day marked), (0, 0, 0) with no wall clock."""
        self._sync()
        return self.y, self.m, self.d

    def keys(self):
        return _MONTH_KEYS

    def _engine(self):
        e = self.engine
        if e is None:
            import uitree_app
            import month_ui
            e = self.engine = uitree_app.hosted_page(month_ui.page, self.host, self, env=self)
            e.bare = True               # the popover's card is its ground
            e.open()
        return e

    def all(self):
        """The page's damage, which asks for no frame: its state moves only
        where the paging does (`page`), and that asks for its frame."""

    def draw(self, cv, rect):
        import month_ui
        ws = self.ws
        desk = _desk()
        e = self._engine()
        e.band = desk
        self._sync()
        if self._wt is not self._t or self._woff != self.off:
            self._wt, self._woff = self._t, self.off
            e.run(month_ui.poll, self, action="month_poll")
            month_ui.ui.commit(e)       # (month_ui's uitree)
        inner = _inner(ws, rect)
        self.host.begin(cv, ws.theme_colors, inner, desk, "panel")
        e.paint(0.0, cv, ws.theme_colors, inner, desk)
        if self.host.due() or self.host.tap == 2:
            ws.popover_touch()

    def page(self, n):
        self.off += n
        self.ws.popover_touch()
        return "local"

    def handle_input(self, i):
        if i.steps("left"):
            return self.page(-1)
        if i.steps("right"):
            return self.page(1)
        return None

    def click(self, px, py, rect):
        self._engine().point(px, py, True)
        return "local"

    def typing(self):
        return False

    def closed(self):
        self.off = 0
        self._t = self._wt = None
        if self.engine is not None:
            self.engine.close()
            self.engine = None
        self.host.reset()


# value_row's slot of the desk's hint band (MOY_UI_M_VALUE_ROW_HINTS_DESK)
_HINTS_DESK = 17


def _foot(fs):
    """The desk's hint band under a component's rows, at font scale `fs`."""
    return _ui_draw.metrics("value_row")[_HINTS_DESK] * fs


class WifiPanel:
    """The `wifi` widget's component: Settings' Wi-Fi page (scan, pick, the
    password step, connect) drawn in the popover's card over its own UI
    context (`ui_draw.AppHost`), holding the radio lease Settings' page
    holds, released on every close. One implementation: `wifi_ui`'s
    popover page over `SettingsLayer`'s radio."""

    def __init__(self, ws):
        self.ws = ws
        self.rect = None
        self.need = 0                 # the card's height its rows take
        self.host = _ui_draw.AppHost()
        self.page = None

    def all(self):
        """The page's damage: the popover draws another frame."""
        self.ws.popover_touch()

    def size(self):
        desk = _desk()
        fs = self.ws.layout.fs
        row = _ui_draw.metrics("row")
        rh, gap = row[6 if desk else 5] * fs, row[7] * fs
        cap = _ui_draw.metrics("group")[4 if desk else 3] * fs
        n = self.ws.settings_layer.wifi_listed() + 2   # the head, the networks, Scan again
        foot = _foot(fs) if desk else 0
        self.need = 2 * _pad(self.ws) + cap + n * (rh + gap) + foot
        return ((300 if desk else 232) * fs, self.need)

    def keys(self):
        return _WIFI_KEYS

    def opened(self):
        self.host.reset()
        sl = self.ws.settings_layer
        sl.wifi_enter()
        if self.page is None:
            import wifi_ui
            self.page = wifi_ui.WifiPage(sl, self.host, self, popover=True)
        self.page.open()

    def draw(self, cv, rect):
        ws = self.ws
        self.rect = rect
        before = self._radio()
        _fit(ws, self)
        self.host.begin(cv, ws.theme_colors, _inner(ws, rect), _desk(), "panel")
        self.page.overflows = rect[3] < self.need
        self.page.draw(cv, ws.theme_colors, _inner(ws, rect), _desk(), 0.0)
        if self._radio() != before:
            ws.mark_dirty()          # the radio's state shows outside the panel
        elif self.host.due() or self.host.tap == 2:
            ws.popover_touch()        # a tap's release, next frame

    def _radio(self):
        sl = self.ws.settings_layer
        return (tuple(sl.wifi_known), self.ws.wifi_icon_kind())

    def _state(self):
        sl = self.ws.settings_layer
        return (len(sl.wifi_nets), sl.wifi_msg, sl.wifi_sel, sl.wifi_pick, sl.wifi_pw)

    def handle_input(self, i):
        before = self._state()
        radio = self._radio()
        self.page.keys(i)
        if self._radio() != radio:
            return "global"
        if self._state() != before or i.any_pressed() or i.last_key:
            return "local"            # the page resolves the keys as it draws
        return None

    def click(self, px, py, rect):
        self.host.point(px, py, True)
        return "local"

    def typing(self):
        return self.ws.settings_layer.wifi_pick is not None

    def closed(self):
        self.ws.settings_layer.wifi_leave()
        if self.page is not None:
            self.page.close()


def _cut(r, c):
    """Rect `r` cut to rect `c`, None where nothing of it is left."""
    x0, y0 = max(r[0], c[0]), max(r[1], c[1])
    x1, y1 = min(r[0] + r[2], c[0] + c[2]), min(r[1] + r[3], c[1] + c[3])
    return (x0, y0, x1 - x0, y1 - y0) if x1 > x0 and y1 > y0 else None


class _Section:
    """A page section in its slot (`status_items`, SECTION): the item's own
    engine over its own UI context, its runs as the item's process."""

    def __init__(self, ws, it):
        import uitree_app
        self.ws = ws
        self.it = it
        self.sec = it.section
        self.host = _ui_draw.AppHost()
        self.rect = None                # where it painted last, clipped to the card
        self.gen = _ITEMS.gen
        self.engine = uitree_app.hosted_page(self.sec.page, self.host, self, env=self.sec)
        self.engine.bare = True         # the card is its ground
        self.engine.band = False
        _ITEMS.run_as(it, self.engine.open)

    def all(self):
        self.ws.popover_touch()

    def changed(self):
        """The item said its section moved: the page's `changed` hook."""
        self.gen = _ITEMS.gen
        h = self.engine.actions.get("changed")
        if h is not None and h.hook:
            import uitree
            _ITEMS.run_as(self.it, self.engine.run, h.fn, action="changed")
            uitree.commit(self.engine)

    def end_stop(self, top):
        """The id of its topmost (`top`) or bottommost stop, None for none."""
        best = None
        for sid in self.engine.stop_kinds():
            b = self.host.box(sid)
            if b is not None:
                k = b[1] if top else -(b[1] + b[3])
                if best is None or k < best[0]:
                    best = (k, sid)
        return best[1] if best else None

    def at_edge(self, dy):
        """Whether its focus has no stop past it along `dy` (-1 up, 1 down):
        the key leaves the slot."""
        f = self.engine.focused_id()
        b = self.host.box(f) if f else None
        if b is None:
            return False
        for sid in self.engine.stop_kinds():
            o = self.host.box(sid)
            if o is not None and (o[1] + o[3] <= b[1] if dy < 0 else o[1] >= b[1] + b[3]):
                return False
        return True

    def close(self):
        self.engine.close()
        self.host.reset()


class _Rows:
    """The status items' rows (`cc_ui`'s page) in a popover's card, over
    its own UI context: the base of the control center and an item's desk
    menu. The page's handlers reach the host through `level`, `wifi`,
    `press` and `slot_keys`; `poll` writes what it shows. A page section
    paints in its group's slot after the page (`_Section`)."""

    CC = False                  # the console's group with Wi-Fi
    POWER = False               # ... with the battery's line

    def __init__(self, ws):
        self.ws = ws
        self.rect = None
        self.host = _ui_draw.AppHost()
        self.page = None
        self.gen = -1                 # the items' gen the groups were written at
        self.secs = [None] * _CAP     # each group's page section, made as it shows
        self.held = None              # the stop the page's focus was on last frame

    def items(self):
        """The items whose rows the page lists, in order."""
        return ()

    def all(self):
        """The page's damage: the popover draws another frame."""
        self.ws.popover_touch()

    def keys(self):
        return _POWER_KEYS

    def _engine(self):
        e = self.page
        if e is None:
            import uitree_app
            import cc_ui
            e = self.page = uitree_app.hosted_page(cc_ui.page, self.host, self, env=self)
            e.bare = True               # the popover's card is its ground
            e.open()
        return e

    def poll(self, s):
        s.cc = self.CC
        s.power = self.POWER
        g = _ITEMS.gen
        if g != self.gen:
            import cc_ui
            self.gen = g
            cc_ui.put_items(self.items(), self.CC, _desk())

    def draw(self, cv, rect):
        import cc_ui
        ws = self.ws
        self.rect = rect
        g = self.gen
        e = self._engine()
        e.band = _desk()          # a handheld's popover strip says its keys
        e.run(cc_ui.poll, self, action="cc_poll")
        if g != self.gen and g != -1:
            _fit(ws, self)
        cc_ui.ui.commit(e)        # (cc_ui's uitree)
        inner = _inner(ws, rect)
        desk = _desk()
        self.host.begin(cv, ws.theme_colors, inner, desk, "panel")
        e.paint(0.0, cv, ws.theme_colors, inner, desk)
        if self.host.due() or self.host.tap == 2:
            ws.popover_touch()
        self._sections(cv, inner, desk)

    def _sections(self, cv, inner, desk):
        """Each page section painted in its slot, clipped to the card; focus
        landing on a slot goes to the section's stop nearest where it came
        from."""
        import cc_ui
        ws, e = self.ws, self.page
        if e is None:
            return                          # its paint closed the popover
        th = ws.theme_colors
        items = self.items()
        f = e.focused_id()
        any_ = False
        for g in range(_CAP):
            it = items[g] if g < len(items) else None
            sc = self.secs[g]
            if it is None or _ITEMS.page(it) is None:
                if sc is not None:
                    sc.close()
                    self.secs[g] = None
                continue
            if sc is None or sc.sec is not it.section:
                if sc is not None:
                    sc.close()
                sc = self.secs[g] = _Section(ws, it)
            r = e.slot_rect(cc_ui.SLOTS[g])
            sc.rect = _cut(r, inner) if r is not None else None
            if sc.rect is None:
                continue
            if sc.gen != _ITEMS.gen:
                sc.changed()
            held = f == cc_ui.SLOTS[g]
            if held and (self.held != f or not sc.engine.focused_id()):
                was = self.host.box(self.held) if self.held and self.held != f else None
                sc.engine.want_focus = sc.end_stop(was is None or was[1] < r[1])
            sc.host.begin(cv, th, sc.rect, desk, "panel", elsewhere=not held)
            _ITEMS.run_as(it, sc.engine.paint, 0.0, cv, th, sc.rect, desk)
            if sc.host.due() or sc.host.tap == 2:
                ws.popover_touch()
            any_ = True
        self.held = f
        if any_:
            self.host.resume(cv, th)        # the page's context is the verbs' again

    def slot_keys(self, g, i):
        """The keys while group `g`'s slot holds the page's focus: the
        section's, but up past its top stop or down past its bottom one,
        which leave the slot (False)."""
        sc = self.secs[g]
        if sc is None:
            return False
        dy = -1 if i.pressed("up") else 1 if i.pressed("down") else 0
        if not sc.engine.focused_id():
            sc.engine.want_focus = sc.end_stop(dy >= 0)
            return True
        if dy and sc.at_edge(dy):
            return False
        _ITEMS.run_as(sc.it, sc.engine.keys, i, False)
        return True

    def press(self, row):
        import cc_ui
        k, r, v = cc_ui.pressed(row)
        it = _ITEMS.slots[k]
        if not it.pid:
            return
        if r < 0:
            self.ws.notices.open_status_app(it)
        else:
            _ITEMS.panels[k]._press(r, v)
        self.ws.mark_dirty()

    def handle_input(self, i):
        e = self._engine()
        e.keys(i, damage=False)
        return "local" if i.any_pressed() or i.last_key else None

    def click(self, px, py, rect):
        for sc in self.secs:
            r = sc.rect if sc is not None else None
            if r is not None and r[0] <= px < r[0] + r[2] and r[1] <= py < r[1] + r[3]:
                _ITEMS.run_as(sc.it, sc.engine.point, px, py, True)
                return "local"
        self._engine().point(px, py, True)
        return "local"

    def typing(self):
        return False

    def closed(self):
        if self.page is not None:
            self.page.close()
            self.page = None
        for g in range(_CAP):
            if self.secs[g] is not None:
                self.secs[g].close()
                self.secs[g] = None
        self.held = None
        self.gen = -1
        self.host.reset()


def _rows_h(n, fs, desk=False):
    """`n` stacked rows' height at font scale `fs`."""
    row = _ui_draw.metrics("row")
    return n * (row[6 if desk else 5] + row[7]) * fs


def _item_h(it, fs, desk=False):
    """Item `it`'s part of the page at font scale `fs`: its section's slot,
    or its rows."""
    if _ITEMS.page(it) is not None:
        return _ITEMS.height(it, desk) * fs + _ui_draw.metrics("row")[7] * fs
    return _rows_h(_ITEMS.rows(it), fs, desk)


class _Console(_Rows):
    """A page with the console's group: Volume and Brightness as Settings'
    levels (`SettingsLayer.set_level`), then Wi-Fi or the battery's line;
    Brightness where there is a panel light (`ws.panel_light`), Wi-Fi where
    there is a radio."""

    def rows(self):
        """The console group's rows: Volume, Brightness and Wi-Fi as there
        are a light and a radio."""
        ws = self.ws
        return 1 + bool(ws.panel_light) + (ws.wifi is not None)

    def poll(self, s):
        ws = self.ws
        s.light = bool(ws.panel_light)
        s.radio = ws.wifi is not None
        sl = ws.settings_layer
        cur, lo, hi = sl.level("volume")
        s.vol, s.vlo, s.vhi = cur, lo, hi
        s.vicon = "mute" if cur == lo else "volume"
        s.bri, s.blo, s.bhi = sl.level("brightness")
        s.wicon = "wifi" if ws.wifi_icon_kind() == "wifi" else "wifi_off"
        s.net = self._network()
        _Rows.poll(self, s)

    def level(self, key, v):
        self.ws.settings_layer.set_level(key, v)
        self.ws.mark_dirty()

    def wifi(self):
        ws = self.ws
        ws.close_popover()
        ws.toggle_popover("wifi")

    def _network(self):
        """The Wi-Fi row's value: the network joined, else Off."""
        w = self.ws.wifi
        try:
            st = w.status() if w is not None else None
        except Exception:  # noqa: BLE001 -- a status hiccup reads as no link
            st = None
        return st[1] if st and st[0] and st[1] else "Off"


class ControlCenter(_Console):
    """A handheld's control center, the `battery` widget's component there,
    which the bar's status cluster opens (docs/theme_and_shell_2026-11.md
    §8.6): `cc_ui`'s page, the console's group first (Volume, Brightness,
    Wi-Fi), then each app's rows under its app's name, in the bar's order.
    Its first view ends FIRST_FOOT under the first app's group; the page
    scrolls the rest. The battery has no row: the bar's glyph shows it low
    and charging, and Settings keeps its exact level."""

    CC = True
    W = 232                     # at the font scale
    FIRST_FOOT = 6
    SCRIM = 128                 # the page beside it dims by half, in both themes

    def items(self):
        return _ITEMS.shown

    def column(self):
        """(the first view's height, the column's), from the panel's top."""
        fs = self.ws.layout.fs
        grp = _ui_draw.metrics("group")
        cap, gap = grp[3] * fs, grp[5] * fs
        y = 2 * _pad(self.ws) + _rows_h(self.rows(), fs)
        first = None
        for it in _ITEMS.shown:
            y += gap + cap + _item_h(it, fs)
            if first is None:
                first = y + self.FIRST_FOOT * fs
        return (y if first is None else min(first, y)), y

    def size(self):
        ws = self.ws
        first, _end = self.column()
        lay = ws.layout
        room = lay.ch
        strip = ws.menu_ui.about._strip()
        if strip is not None and lay.cy < strip[1] < lay.cy + room:
            room = strip[1] - lay.cy           # above the hint strip
        return (self.W * lay.fs, min(first, room - 4 * lay.fs))


class PowerRows(_Console):
    """The desk battery's popover, the `battery` widget's component there:
    the console's group with the battery's line (its level where the board
    reads one) over Volume and Brightness."""

    POWER = True

    def __init__(self, ws):
        _Console.__init__(self, ws)
        self.lvl = -1                   # the level the line was written at

    def poll(self, s):
        lvl = self.ws.battery_level()
        if lvl != self.lvl:
            self.lvl = lvl
            s.battery = "Battery" if lvl is None else "%d%%" % lvl
        _Console.poll(self, s)

    def size(self):
        fs = self.ws.layout.fs
        n = 2 + bool(self.ws.panel_light)       # the battery's line, Volume, Brightness
        return (300 * fs, 2 * _pad(self.ws) + _rows_h(n, fs, True) + _foot(fs))


class StatusMenu(_Rows):
    """An app's status item's menu on the desk, hung from its cell in the
    bar's right zone: its rows in the popover's card, the page's keys' band
    under them. No wash: the desk's menus take none."""

    def __init__(self, ws, item):
        _Rows.__init__(self, ws)
        self.item = item

    def items(self):
        it = self.item
        return (it,) if it is not None and it.pid else ()

    def size(self):
        fs = self.ws.layout.fs
        # under touch alone there are no hints, and no room kept for them
        foot = 0 if _ui_draw.input_kind() == "touch" else _foot(fs)
        it = self.item
        h = _item_h(it, fs, True) if it is not None and it.pid else 0
        return (404 * fs, 2 * _pad(self.ws) + h + foot)

    def keys(self):
        return _MENU_KEYS


def component_for(ws, widget):
    """The component a bar widget opens (§8's table, fixed per widget); none
    for the wifi widget of a console with no radio (a browser page no
    Zero serves)."""
    if widget == "clock":
        return MonthView(ws)
    if widget == "wifi":
        return WifiPanel(ws) if ws.wifi is not None else None
    if widget == "battery":
        return PowerRows(ws) if _desk() else ControlCenter(ws)
    if widget == "status":
        return StatusMenu(ws, ws.status_open)
    return None
