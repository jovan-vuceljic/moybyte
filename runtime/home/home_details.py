# Map (grep -n a name to jump there):
#   HomeDetails                   the mixin the home's details and desk buttons live on
#   HomeDetails.card_verbs        the selected card's verbs, its menu's rows
#   HomeDetails._button_focus     the desk pane's button the keys are on
#   HomeDetails._pane_keys        the keys on the desk pane's buttons, its page's
#   HomeDetails._pane_point       the pointer on the desk's hero and pane, their pages'
#   HomeDetails.details_owed      a frame the pane's page owes moves what it shows
#   HomeDetails._desk_buttons     the desk pane's verb buttons, where the page drew them
#   HomeDetails._draw_details     the desk hero and its details: their pages
#   HomeDetails.details_put       what the pages show of the selected card
"""The home's DETAILS: the desk home's hero -- the selected card's picture,
a tap on it the tab's tap -- and what it says of the card beside it -- the
title, the metadata, the description, the facts (`_facts`: plays, the last
day, the maker) and the verb buttons (docs/theme_and_shell_2026-11.md
§8.10) -- two `uitree` pages (`home_ui.hero`, `home_ui.page`), each laid in
its rect of the desk's geometry on a host of its own; and the card's verbs a
card's menu lists (`card_verbs`). A mixin over `LauncherHomeLayer`, after
`HomeHints` among its bases: the hero and the details are drawn on the desk
home's painted frames, never on a band frame. Up from the shelf hands the
pane's page the keys (`_button_focus`): its buttons take them, and the page's
edge hands them on, up to the bar (the shell's, as any page's edge) and down
to the shelf.
"""

import ui_draw as _ui_draw
from home_grid import button_kind, day_words, NEW_TILE_TYPE, PSEUDO_TILE_TYPES, _VERB_HINT
from widgets import rect_in as _in   # one hit-test
_EDGE_UP, _EDGE_DOWN = 1, 2     # uitree_app's EDGE_UP and EDGE_DOWN

_PLAYS = ("play", "open", "window")             # a button that wears the Play glyph
_BUTTON_IDS = ("press/0", "press/1", "press/2", "press/3")   # home_ui's buttons' stops
_NO_RECT = (0, 0, 0, 0)     # a button the page has not drawn yet
_META_SEP = "  \u00b7  "    # between the metadata's parts
DESC_EMS = 48               # the description's measure, this many n's: about 60 characters


def times_words(n):
    """A play count as the home says it."""
    return "Not yet" if not n else ("Once" if n == 1 else "%d times" % n)


class HomeDetails:
    """The desk hero's details, its verb buttons and the card's verbs of
    `LauncherHomeLayer`."""

    _dpage = None       # the details pane's page and its host, made at the first desk paint
    _dhost = None
    _hpage = None       # ...and the hero's
    _hhost = None
    _dkey = None        # what the pages show was put at (`_draw_details`)
    _dput = None        # ...and what `details_put` hands them
    _btn = None         # True while the pane's buttons hold the keys
    _dgen = 0           # moves with the input the hero's and the pane's pages take
    _dptr = None        # the host a press on the hero or the pane went to
    _dlag = False       # the pane's page owes the next frame (`details_owed`)
    _dedge = 0          # ...and the edge its keys went past (EDGE_UP, EDGE_DOWN)

    def card_verbs(self):
        """The selected card's verbs beyond its tap, the ONE list every
        input reaches them by: the system menu's card group, a long press
        on the card, a gamepad's X, the desk's buttons. Its favourite star,
        then CHANGE with COPY beside it, then SEND where the console has a
        radio link (runtime/run/link_beam.py), SAVE (to this computer) in
        the browser (`Workstation.page`) and POD (play on the console) where
        a console serves the page, then DEL, where
        the active tab has them (`zone_verbs`)."""
        zone = self.zone_verbs()
        out = []
        if self.favourable() is not None:
            out.append("favourite")
        if "change" in zone:
            out.append("change")
            out.append("copy")
        link = getattr(self.ws, "link", None)
        if link is not None and link.usable():
            it = self.grid.selected()
            if it and it.get("path") and it.get("type") not in PSEUDO_TILE_TYPES:
                out.append("send")
        page = getattr(self.ws, "page", None)
        if page is not None:
            it = self.grid.selected()
            if it and it.get("path") and it.get("type") not in PSEUDO_TILE_TYPES:
                out.append("save")
                if page.served:
                    out.append("pod")
        for v in zone:
            if v == "delete":
                out.append(v)
        return out

    def _desk_verbs(self):
        """The desk home's buttons (step 18): the active tab's tap verb,
        then the card's verbs but its star (the hero wears that), SEND, SAVE
        and POD (its menu's alone). On Make
        a real card's are its own, CHANGE first: NEW makes another cart,
        which the shelf's + tile and N keep. None off the desk."""
        if not (self._carousel() and self.grid.desk()):
            return ()
        zone = self.zone_verbs()
        out = [] if "change" in zone and self.grid.tab == "make" else \
            [v for v in zone[:1] if v in ("play", "open", "new")]
        out.extend(v for v in self.card_verbs() if v not in ("favourite", "send", "save", "pod"))
        return out

    def _details_page(self):
        """The details pane's page (`home_ui.page`) and the hero's
        (`home_ui.hero`), each on its own host, made at the first desk paint:
        a handheld never makes them."""
        pg = self._dpage
        if pg is None:
            import ui_host
            import uitree_app
            import home_ui
            self._dhost = ui_host.AppHost()
            pg = self._dpage = uitree_app.hosted_page(home_ui.page, self._dhost, self, env=self)
            self._hhost = ui_host.AppHost()
            hp = self._hpage = uitree_app.hosted_page(home_ui.hero, self._hhost, self, env=self)
            hp.pictures = self.grid.hero_picture
            for p in (pg, hp):
                p.bare = True                # the home's ground is its ground
                p.band = False               # the hint strip names its keys
                p.open()
        return pg

    @property
    def _button_focus(self):
        """The desk home's button the keys are on (up from the shelf), an
        index into `_desk_buttons` (the pane's page's focus), or None: the
        shelf's card has them."""
        if self._btn is None:
            return None
        f = self._dpage.focused_id() if self._dpage is not None else None
        return _BUTTON_IDS.index(f) if f in _BUTTON_IDS else 0

    @_button_focus.setter
    def _button_focus(self, k):
        # one focus mark a screen: the button's takes it from the card
        if (k is None) != (self._btn is None):
            self._zone_bump = getattr(self, "_zone_bump", 0) + 1
        self._btn = None if k is None else True
        if k is not None:
            self._details_page()
            self._dhost.focus(_BUTTON_IDS[k])
        self._dgen += 1
        g = self._grid_or_none()
        if g is not None:
            g.tab_focus = k is not None or getattr(self, "_on_bar", False)
        self.ws.mark_dirty()

    def _pane_keys(self, i):
        """The keys on the desk home's buttons, the pane's page's: the
        arrows move along them and between their rows where they wrap,
        confirm presses one, B goes back to the shelf; the page's edge hands
        them on (`_draw_details`). False where no button has them, or for
        another key (the strip's letters still act)."""
        if self._btn is None:
            return False
        ws = self.ws
        if not self._desk_verbs():
            self._button_focus = None
            return False
        if i.pressed("b") and ws.ach_ui._konami_pos == 0:
            self._button_focus = None
            return True
        if i.pressed("home"):
            ws.home.home_key()
            return True
        if not (i.steps("left") or i.steps("right") or i.steps("up") or i.steps("down")
                or i.pressed("a") or i.pressed("run")):
            return False
        self._dhost.keys(i)
        self._dgen += 1
        ws.mark_dirty()
        return True

    def _pane_point(self, px, py, click, down):
        """A pointer sample on the desk home's hero or its pane: a press in
        either goes to its page's host (a tap on the hero is the tab's tap,
        on a button its verb), and its release after it, where a press let
        go off its stop taps nothing; the moves between are no drag's.
        False where neither has it."""
        if click:
            self._dptr = None
            if self._dpage is not None and self.grid.items:
                dk = self.grid._geom()[9]
                if _in(px, py, dk[0]):
                    self._dptr = self._hhost
                elif _in(px, py, (dk[1], dk[6], dk[2], dk[5][5])):
                    self._dptr = self._dhost
        h = self._dptr
        if h is None:
            return False
        if not click and down:
            return True                      # (the pages are no drag's: it moves nothing)
        h.point(px, py, click, down)
        if not down:
            self._dptr = None
        self._dgen += 1
        self.ws.mark_dirty()
        return True

    def details_owed(self):
        """At a frame's start, before its parts are keyed: the pane's page
        owes this frame (a press it showed settles), so what it shows moves
        (`_dgen`); a step past its buttons takes the keys off them: up the
        page's edge takes them on to the bar (the router's), down to the
        shelf."""
        if self._dlag:
            self._dlag = False
            self._dgen += 1
        e = self._dedge
        if e:
            self._dedge = 0
            self._button_focus = None

    def hero_press(self):
        """The hero's page's tap: the active tab's tap."""
        self.ws.defer(self._launch)          # #184: start behind the paint

    def all(self):
        """The page's damage: the home draws again."""
        self.ws.mark_dirty()

    def _desk_buttons(self):
        """[(verb, rect, kind)] of the details pane's buttons: the desk's
        verbs (`_desk_verbs`), each where the page drew its place last (an
        empty rect before it has), the first a primary where it plays,
        opens, makes or changes, DEL a danger."""
        verbs = self._desk_verbs()
        if not verbs:
            return []                        # off the desk
        box = self._dhost.box if self._dpage is not None else None
        out = []
        for k, v in enumerate(verbs):
            r = box(_BUTTON_IDS[k]) if box is not None else None
            out.append((v, r if r is not None else _NO_RECT, button_kind(k, v)))
        return out

    def _draw_details(self, cv):
        """The desk home's hero and its details pane beside it (step 18),
        each page in its rect of the desk's geometry: the selected card's
        picture; its title in the `title` face at the pane's scale, its
        metadata, its description, its facts (how often and when it was
        played, the play record's; who made it, its id's), then its
        buttons, the one the keys are on marked. A step past the pane's
        buttons hands the keys on: up to the tabs, down to the shelf."""
        ws = self.ws
        g = self.grid
        if not g.items:
            return
        pg = self._details_page()
        dk = g._geom()[9]
        rect = (dk[1], dk[6], dk[2], dk[5][5])
        i = g.nearest()
        it = g.items[i]
        verbs = self._desk_verbs()
        key = (it, g.tab, tuple(verbs), dk[5][0], dk[7], g.played(it), g.today(), dk[0][2], i)
        if key != self._dkey:
            self._dkey = key
            self._dput = (it, verbs, dk, i)
            import home_ui
            for p in (pg, self._hpage):
                p.run(home_ui.put, action="put")
                home_ui.ui.commit(p)
        th = ws.theme_colors
        self._hhost.begin(cv, th, dk[0], True, elsewhere=True)
        g.paint_hero(self._hpage, cv, th, dk[0])
        on = self._btn is not None
        if not self._dhost.begin(cv, th, rect, True, elsewhere=not on) or self._dptr is not None:
            self._dlag = True                # (a frame owed: the press it shows settles)
            ws.request_frame()
        pg.paint(0.0, cv, th, rect, True)
        e = pg.edge() if on else 0
        if e & (_EDGE_UP | _EDGE_DOWN):
            self._dedge = e                  # (handed on at the next frame's start)
            ws.request_frame()

    def details_put(self, s):
        """What the details pane shows of the selected card (home_ui's `put`)."""
        import home_ui
        it, verbs, dk, i = self._dput
        g = self.grid
        s.hero = home_ui.ui.image.own(str(i))
        s.hero_side = dk[0][2]
        pseudo = it.get("type") in PSEUDO_TILE_TYPES
        s.title = "New" if it.get("type") == NEW_TILE_TYPE else str(it.get("title") or "")
        ts, ms, _ks, _vs, bh, pane, _u = dk[5]
        s.title_scale = ts
        facts_on, meta_on = dk[7]
        facts_on = facts_on and not pseudo
        # what the pane's height holds at the text's scale, each a line and
        # half one apart: the title and the buttons' rows always, the facts (two
        # lines), then the metadata, then two lines of the description
        lh = _ui_draw.font()[2] * self.ws.layout.fs
        step = 3 * lh // 2
        room = pane - _ui_draw.font("title")[2] * ts - bh - dk[8] - lh
        facts_on = facts_on and room >= 2 * step
        room -= 2 * step if facts_on else 0
        meta_on = meta_on and room >= step
        room -= step if meta_on else 0
        s.meta_on, s.facts_on = meta_on, facts_on
        s.meta = _META_SEP.join(g._meta(it, played=False)) if meta_on else ""
        s.desc = "" if pseudo or room < 2 * lh else str(it.get("description") or "")
        s.desc_w = _ui_draw.print_width("n" * DESC_EMS, ms)
        facts = () if pseudo or not facts_on else self._facts(it)
        for k in range(home_ui.FACTS):
            setattr(s, home_ui.FACT_KEYS[k], facts[k][0] if k < len(facts) else "")
            setattr(s, home_ui.FACT_VALUES[k], facts[k][1] if k < len(facts) else "")
        for k in range(home_ui.BUTTONS):
            v = verbs[k] if k < len(verbs) else None
            setattr(s, home_ui.SHOWN[k], v is not None)
            if v is not None:
                setattr(s, home_ui.LABELS[k], _VERB_HINT[v][1])
                setattr(s, home_ui.ICONS[k], "play" if v in _PLAYS else "")
                setattr(s, home_ui.KINDS[k], button_kind(k, v))

    def details_press(self, k):
        """The page's button `k` pressed: its verb, behind the paint, the
        keys back on the shelf but for DEL's (its confirm's Cancel comes
        back to it)."""
        verbs = self._desk_verbs()
        if k < len(verbs):
            self.ws.defer(lambda: self._press_verb(verbs[k]), toast=False)   # (a launch's pill its own)

    def _press_verb(self, v):
        """A pane button's verb, behind the frame that pressed it."""
        if v != "delete" and self._btn is not None:
            self._button_focus = None
        self._do_verb(v)

    def _facts(self, it):
        """The details pane's facts of a cart: (caption, value) pairs."""
        g = self.grid
        rec = g.played(it)
        out = [("Played", times_words(rec[0] if rec is not None else 0))]
        if rec is not None and rec[1]:
            out.append(("Last", day_words(rec[1], g.today())))
        cid = it.get("id") or ""
        if g.own_for is not None and g.own_for(it):
            by = "You"
        elif "." in cid:
            by = cid.split(".", 1)[0]
            by = "Moybyte" if by == "moybyte" else by
        else:
            by = None
        if by:
            out.append(("By", by))
        return out
