# Map (grep -n a name to jump there):
#   HomeHints                the mixin the home's hint strip lives on (its first base)
#   modal_keys               the keys a system modal's strip names
#   HomeHints._hint_groups   the selected card's verbs and star, as the strip names them
#   HomeHints._draw_hints    the hint strip along the home's foot: its page
#   HomeHints.hints_put      the strip's hints, its page's rows
#   HomeHints._strip_point   a pointer sample on the strip
#   HomeHints._search_keys   the keys while a query is typed: the search field's
#   HomeHints._hint_keys     a verb's letter, the star's, from a keyboard
"""The home's HINT STRIP: the keycap hints along the home's foot -- the
selected card's verbs and its star, the bar's keys while it has them, a
system modal's while one holds them (`modal_keys`) -- the engine's hints
row on a page of its own (`home_strip_ui.strip`) on the wallpaper's ink, which
fits them and does the verb a press lands on, and their letters on a
keyboard. A mixin over `LauncherHomeLayer`, its FIRST base: a band frame
draws the strip beside the band (`_beside`) on every moving frame, and on
MicroPython a method the class lacks is looked up through its bases in
order. The selection it names is the layer's;
its own state is the hints as they were put last (`_hint_moved`), so a
full paint of the home -- every frame over a live wallpaper -- draws it
with nothing made.
"""

import ui_draw as _ui_draw
import ui_host as _ui_host
import layout_base as _lb
from home_grid import _VERB_HINT, VR_HINTS, VR_HINTS_DESK
from widgets import rect_in as _in   # one hit-test

# The strip's words and keys: the star's, the verbs' letters, the strips'
# keys a modal or the bar names, the strip's lead.
_UNFAVOURITE = "Remove favourite"   # the star's words on a card that wears it
_VERB_KEY = {"c": "change", "/": "search", "n": "new", "y": "copy", "x": "delete",
             "p": "window"}
_FAVOURITE_KEY = "f"     # the selected card's star, on every tab that draws one
# The inputs (ui_draw.INPUTS) that type those letters: a gamepad has no C.
_LETTER_INPUTS = ("keys", "tdeck")
_HINT_LEAD = 8       # the margin a hints row leads with, at the font scale
                     # (MOY_UI_HINT_LEAD)
_MENU_KEYS = ("back", "Close")   # the strip under the system menu
_CONFIRM_KEYS = ("confirm", "Choose", "back", "Cancel")   # under the delete confirm


def modal_keys(ws):
    """The keys a home's hint strip names while a system modal holds them:
    the delete confirm's dialog's, the system menu's card's, the bar's while
    the keys are on it, else None (the home's own verbs)."""
    if ws.confirm.open:
        return _CONFIRM_KEYS
    if ws.menu_ui.looked():
        return _MENU_KEYS
    if _ui_draw.on_bar():
        return _ui_draw.BAR_KEYS
    return None


class HomeHints:
    """The hint strip of `LauncherHomeLayer` (its first base)."""

    def _hint_groups(self):
        """The hint strip's two groups: the active tab's verbs on the
        selected card (on the desk, its buttons' and SEARCH), then the tab
        keys; and the verb of each pair. A keyboard types each verb's
        letter, the star last, its words following its state; a gamepad
        shows the verb its confirm does (`launch_selected`), on that key,
        and X for the card's other verbs (`card_verbs`). With the keys on a
        desk button, confirm names that button's verb."""
        items = []
        verbs = []
        zone = self.zone_verbs()
        on = self._button_focus
        if on is not None:
            # the keys on the desk's buttons: confirm presses the one they are on
            buttons = self._desk_buttons()
            on = buttons[min(on, len(buttons) - 1)][0] if buttons else None
        if _ui_draw.hint_kind() not in _LETTER_INPUTS:
            tap = on or self._confirm_verb(zone)
            if tap:
                items.append("confirm")
                items.append(_VERB_HINT[tap][1])
                verbs.append(tap)
            if self.card_verbs():
                items.extend(_VERB_HINT["options"])
                verbs.append("options")
            return items, verbs
        desk = tuple(self._desk_verbs())
        if desk and "new" in zone and "new" not in desk:
            desk = ("new",) + desk           # Make's N, off the card's buttons
        for v in (desk + tuple(v for v in zone if v == "search")) if desk else zone:
            k, words = _VERB_HINT[v]
            if on is not None and (v == on or k == "confirm"):
                if v != on:
                    continue                 # the shelf's tap: no key on the buttons
                k = "confirm"
            items.append(k)
            items.append(words)
            verbs.append(v)
        it = self.favourable()
        if it is not None:
            # the star last, the first to go where the strip runs short (`_hint_rows`)
            items.append(_VERB_HINT["favourite"][0])
            items.append(_UNFAVOURITE if self.ws.carts.is_favorite(it)
                         else _VERB_HINT["favourite"][1])
            verbs.append("favourite")
        return items, verbs

    def _confirm_verb(self, zone):
        """Which of the verbs `zone` the selected card's confirm does: the
        "+ New" card's NEW, a Make card's CHANGE (it opens in the Editor),
        else PLAY or OPEN; "" for none."""
        if self.grid.tab == "make" and "change" in zone:
            return "change"
        return zone[0] if zone[:1] in (("play",), ("open",), ("new",)) else ""

    def _hint_rows(self):
        """[(verb or None, keys, words, tail, spare)]: the hints the strip
        shows. A system modal's keys (`modal_keys`), else the selected
        card's verbs and its star (`_hint_groups`), or while a search is
        open the key that closes it (its field stands in the verbs' place),
        and the tab keys at the strip's end. Where the verbs run into the
        tab keys the engine drops the spare ones, the star first, then
        Duplicate (it stays on Y and in the card's menu; design review
        R4-22)."""
        keys = modal_keys(self.ws)
        if keys is not None:
            return [(None, keys[k], keys[k + 1], False, False) for k in range(0, len(keys), 2)]
        rows = []
        if self._search_open():
            k = self._search_close_items()
            rows.append(("close", k[0], k[1], False, False))
        else:
            items, verbs = self._hint_groups()
            for k in range(len(verbs)):
                rows.append((verbs[k], items[2 * k], items[2 * k + 1], False,
                             verbs[k] in ("copy", "favourite")))
        rows.append(("tabs", "tabs", "Tabs", True, False))
        return rows

    def _draw_hints(self, cv):
        """The home's hint strip (steps 17 and 18): its page in the strip's
        rect, inside the margin `_hint_pad` -- keycaps naming the active
        tab's verbs on the selected card from the left and the tab keys at
        the right (`_hint_rows`) -- on the wallpaper's ink; while search is
        open its field in the verbs' place, which takes the keys while a
        query is typed. Under touch, which has no strip, the page draws the
        search alone on its line (`_search_line`)."""
        th = self.ws.theme_colors
        wall = self._wall()
        if wall is not None:
            th = self._wall_theme(th, wall[0])
        rect = self.grid.foot()[5]
        if rect[3] <= 0:
            rect = self._search_line()
        if rect is not None and rect[2] > 0 and rect[3] > 0:
            pg = self._strip_page()
            # the verbs' target as the frame round the strip left it (a band
            # frame's band host), given back after the strip's page
            t = _ui_host.UI_TARGET
            was = self._was
            was[0] = t[0]
            was[1] = t[1]
            was[2] = t[2]
            was[3] = t[3]
            if self._hint_moved():
                import home_strip_ui
                self._hrows = self._hint_rows()
                pg.run(home_strip_ui.put, action="put")
                home_strip_ui.ui.commit(pg)
            inner = self._hint_inner(rect)
            typing = getattr(self.ws, "search_typing", False)
            self._shost.begin(cv, th, inner, self.grid.desk(), elsewhere=not typing)
            pg.paint(0.0, cv, th, inner, True)
            t[0] = was[0]
            t[1] = was[1]
            t[2] = was[2]
            t[3] = was[3]

    def _strip_page(self):
        """The hint strip's page (`home_strip_ui.strip`) on a host of its
        own, made at the first paint of the strip."""
        pg = self._spage
        if pg is None:
            import uitree_app
            import home_strip_ui
            self._shost = _ui_host.AppHost()
            pg = self._spage = uitree_app.hosted_page(home_strip_ui.strip, self._shost, self, env=self)
            pg.bare = True                   # the home's ground is its ground
            pg.band = False                  # it is the band
            pg.open()
        return pg

    def hints_put(self, s):
        """The strip's hints as its page's rows and its search's state
        (home_strip_ui's `put`): while search is open and no modal holds
        the keys, the query, what the field says empty (that a keyboard is
        needed, where nothing types) and the hints after it."""
        ws = self.ws
        search = self._search_open() and modal_keys(ws) is None
        rows = [dict(id=str(k), keys=r[1], words=r[2], tail=r[3], spare=r[4])
                for k, r in enumerate(self._hrows)]
        s.searching = search
        s.hints = rows
        q = getattr(ws, "search_query", "")
        if s.query != q:
            s.query = q
        typing = getattr(ws, "search_typing", False)
        s.search_hint = ws.no_keyboard_text if typing and not ws.text.can_type() else ""

    def search_typed(self, q):
        """The search field edited (home_strip_ui's `typed`): the grid
        filtered by its query, behind the frame."""
        self.ws.defer(lambda: self.ws.home.set_search_query(q), toast=False)

    def search_done(self):
        """Enter in the search field (home_strip_ui's `done`): typing stops,
        the filtered grid stays up for the keys to browse."""
        self.ws.defer(lambda: self.ws.home.close_search(clear=False), toast=False)

    def _search_keys(self, i):
        """The keys while a query is typed: B and Esc close search, cleared;
        the rest are the search field's (its typing, Backspace, Enter)."""
        ws = self.ws
        k = ws.input.typed
        if i.pressed("b") or k == 27:
            ws.home.close_search(clear=True)
            return True
        if k or i.pressed("a"):
            # (fed where a key came: the frame that draws the field takes it)
            self._strip_page()
            self._shost.keys(i)
            self._sgen += 1                  # (the strip's part draws again: it takes the key)
            ws.mark_dirty()
        return True

    def hint_press(self, rid):
        """A press on a hint (home_strip_ui's `hint`): its verb, behind the frame;
        the tab keys' the next tab."""
        v = self._hrows[int(rid)][0]
        if v == "tabs":
            self.ws.defer(lambda: self.ws.home.step_home_tab(1, self.grid), toast=False)
        elif v == "close":
            self.ws.defer(lambda: self.ws.home.close_search(clear=True), toast=False)
        elif v is not None:
            self.ws.defer(lambda: self._do_verb(v), toast=False)

    def hint_rect(self, verb):
        """(x, y, w, h) of `verb`'s hint where the strip drew it last, or None."""
        if self._spage is None:
            return None
        for k, r in enumerate(self._hrows):
            if r[0] == verb:
                return self._spage.rect_of("%d/hints" % k)
        return None

    def _strip_point(self, px, py, click, down):
        """A pointer sample on the hint strip: a press there goes to its
        page's host, which does the hint it lands on, and the samples after
        it to its release. False where the strip does not have it."""
        if click:
            r = self.grid.foot()[5]
            if r[3] <= 0:
                r = self._search_line()
            self._sptr = self._spage is not None and r is not None and r[3] > 0 and _in(px, py, r)
        if not self._sptr:
            return False
        self._shost.point(px, py, click, down)
        if not down:
            self._sptr = False
        self._sgen += 1                      # (the strip's part draws again: it takes the sample)
        self.ws.mark_dirty()
        return True

    # What the strip's hints were put from (`_hint_moved`).
    _HINT_READS = 10
    _hint_k = None
    _hint_v = None
    _hrows = ()          # [(verb or None, keys, words, tail, spare)] the strip shows (`_hint_rows`)
    _spage = None        # the strip's page and its host (`_strip_page`)
    _shost = None
    _sptr = False        # a press on the strip holds the pointer to its release
    _sgen = 0            # moves with each pointer sample the strip takes
    _was = [None, None, None, None]   # the verbs' target round the strip's paint
    _hin_of = None       # the strip's rect `_hin` was made for, and its page's (`_hint_inner`)
    _hin = None

    def _hint_moved(self):
        """Whether what the strip's hints are made of moved since they were
        put: the tab and the selection, the favourites (the settings' gen),
        the input whose keys they name, the keys' place and a modal's, the
        search, the store's say."""
        ws = self.ws
        g = self.grid
        n = self._HINT_READS
        v = self._hint_v
        k = self._hint_k
        if v is None:
            v = self._hint_v = [None] * n
            k = self._hint_k = [None] * n
        v[0] = g.tab
        v[1] = g.sel
        v[2] = g.items
        v[3] = ws.system.gen()
        v[4] = _ui_draw.hint_kind()
        v[5] = self._button_focus
        v[6] = modal_keys(ws)
        v[7] = getattr(ws, "search_query", "")
        v[8] = getattr(ws, "search_typing", False)
        v[9] = getattr(ws, "can_manage", True)
        i = 0
        while i < n and (v[i] is k[i] or v[i] == k[i]):
            i += 1
        if i == n:
            return False
        i = 0
        while i < n:
            k[i] = v[i]
            i += 1
        return True

    def _wall_theme(self, th, white):
        """`th` with its hint labels' roles white, for the strip over a
        wallpaper: one dict per theme load, so the toolkit's look ring keeps
        its slot."""
        k = getattr(self, "_wall_th", None)
        if k is not None and k[0] is th and k[1] == white:
            return k[2]
        wt = dict(th)
        wt["chrome_ink_dim"] = wt["ink_dim"] = white
        self._wall_th = (th, white, wt)
        return wt

    def _hint_lead(self):
        """The margin a hints row leads with here, at the font scale."""
        return _HINT_LEAD * self.ws.layout.fs

    def _hint_pad(self):
        """The hint strip's margin at either end: the handheld's is the one
        a hints row leads with, the top bar's, the desk's wider."""
        if self.grid.desk():
            return max(24 // _lb.render_scale(), self._hint_lead())
        return self._hint_lead()

    def _hint_inner(self, rect):
        """The rect the strip's page draws in: inside the margin
        `_hint_pad`, the engine's band of hints centred on the strip (its
        keys centred as the strip's). Kept while the strip's rect is."""
        if rect is self._hin_of:
            return self._hin
        e = self._hint_pad() - self._hint_lead()
        fs = self.ws.layout.fs
        band = _ui_draw.metrics("value_row")[VR_HINTS_DESK if self.grid.desk() else VR_HINTS] * fs
        self._hin_of = rect
        self._hin = (rect[0] + e, rect[1] + (rect[3] - band) // 2, rect[2] - 2 * e, band)
        return self._hin

    def _hint_keys(self, i):
        """The hint strip's keys, typed (an edge: a held key acts once):
        C, /, N, Y, X and P the verbs it names, Q and E the tabs, F the
        selected card's favourite star."""
        k = self.ws.input.typed
        if not (32 < k < 127):
            return False
        ch = chr(k).lower()
        if ch in ("q", "e"):
            self.ws.home.step_home_tab(-1 if ch == "q" else 1, self.grid)
            return True
        if ch == _FAVOURITE_KEY:
            return self.toggle_favourite()
        v = _VERB_KEY.get(ch)
        if v is None or not (v in self.zone_verbs() or v in self.card_verbs()
                             or (v == "window" and v in self._desk_verbs())):
            return False
        self._do_verb(v)
        return True
