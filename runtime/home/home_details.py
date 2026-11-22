# Map (grep -n a name to jump there):
#   HomeDetails                   the mixin the home's details and desk buttons live on
#   HomeDetails.card_verbs        the selected card's verbs, its menu's rows
#   HomeDetails._desk_buttons     the desk pane's verb buttons, where the page drew them
#   HomeDetails._draw_details     the desk hero's details: the page in the pane
#   HomeDetails.details_put       what the page shows of the selected card
#   HomeDetails._details_tap      a tap on the desk pane's buttons
"""The home's DETAILS: what the desk home says of the selected card beside
its hero -- the title, the metadata, the description, the facts (`_facts`:
plays, the last day, the maker) and the verb buttons
(docs/theme_and_shell_2026-11.md §8.10), a `uitree` page (`home_ui.page`)
laid in the pane on a host of its own -- with the buttons' tap, and the
card's verbs a card's menu lists (`card_verbs`). A mixin over
`LauncherHomeLayer`, after `HomeHints` among its bases: the details are drawn
on the desk home's painted frames, never on a band frame. The keys stay the
layer's: the button they are on (`_button_focus`) is handed to the page's
host as its focus, and with them on the shelf the page shows none.
"""

import ui as _ui
import ui_draw as _ui_draw
from home_grid import day_words, NEW_TILE_TYPE, PSEUDO_TILE_TYPES, _VERB_HINT
_in = _ui.rect_in   # one hit-test (ui.rect_in)

_PRIMARY = ("play", "open", "new", "change")    # a first button that is the tab's tap
_PLAYS = ("play", "open", "window")             # a button that wears the Play glyph
_BUTTON_IDS = ("press/0", "press/1", "press/2", "press/3")   # home_ui's buttons' stops
_NO_RECT = (0, 0, 0, 0)     # a button the page has not drawn yet
_META_SEP = "  \u00b7  "    # between the metadata's parts
_TITLE_AIR = 8              # glass pixels under the title, over the metadata


def times_words(n):
    """A play count as the home says it."""
    return "Not yet" if not n else ("Once" if n == 1 else "%d times" % n)


def _kind(k, verb):
    """The look of the pane's `k`th button, `verb`'s."""
    return "primary" if k == 0 and verb in _PRIMARY else ("danger" if verb == "delete" else "normal")


class HomeDetails:
    """The desk hero's details, its verb buttons and the card's verbs of
    `LauncherHomeLayer`."""

    _dpage = None       # the details pane's page and its host, made at the first desk paint
    _dhost = None
    _dkey = None        # what the page shows was put at (`_draw_details`)
    _dput = None        # ...and what `details_put` hands it

    def card_verbs(self):
        """The selected card's verbs beyond its tap, the ONE list every
        input reaches them by: the system menu's card group, a long press
        on the card, a gamepad's X, the desk's buttons. Its favourite star,
        then CHANGE with COPY beside it, then SEND where the console has a
        radio link (runtime/run/link_beam.py), then DEL, where
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
        for v in zone:
            if v == "delete":
                out.append(v)
        return out

    def _desk_verbs(self):
        """The desk home's buttons (step 18): the active tab's tap verb,
        then the card's verbs but its star (the hero wears that) and SEND
        (its menu's alone). On Make
        a real card's are its own, CHANGE first: NEW makes another cart,
        which the shelf's + tile and N keep. None off the desk."""
        if not (self._carousel() and self.grid.desk()):
            return ()
        zone = self.zone_verbs()
        out = [] if "change" in zone and self.grid.tab == "make" else \
            [v for v in zone[:1] if v in ("play", "open", "new")]
        out.extend(v for v in self.card_verbs() if v not in ("favourite", "send"))
        return out

    def _details_page(self):
        """The details pane's page (`home_ui.page`) on its own host, made at
        the first desk paint: a handheld never makes one."""
        pg = self._dpage
        if pg is None:
            import ui_host
            import uitree_app
            import home_ui
            self._dhost = ui_host.AppHost()
            pg = self._dpage = uitree_app.hosted_page(home_ui.page, self._dhost, self, env=self)
            pg.bare = True                   # the home's ground is its ground
            pg.band = False                  # the hint strip names its keys
            pg.open()
        return pg

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
            out.append((v, r if r is not None else _NO_RECT, _kind(k, v)))
        return out

    def _details_tap(self, px, py):
        """A press on the desk home's hero (the active tab's tap) or one of
        its buttons."""
        g = self.grid
        if not g.items:
            return False
        if _in(px, py, g.hero_rect()):
            self._tab_focus = False
            self.ws.defer(self._launch)          # #184: start behind the paint
            return True
        for v, r, _k in self._desk_buttons():
            if _in(px, py, r):
                self._do_verb(v)
                return True
        return False

    def _draw_details(self, cv):
        """The desk home's details pane beside the hero (step 18), the page
        laid in the pane: the selected card's title in the `title` face at
        the pane's scale, its metadata, its description, its facts (how
        often and when it was played, the play record's; who made it, its
        id's), then its buttons, the one the keys are on marked."""
        ws = self.ws
        g = self.grid
        if not g.items:
            return
        pg = self._details_page()
        dk = g._geom()[9]
        rect = (dk[1], dk[6], dk[2], dk[5][5])
        it = g.items[g.nearest()]
        verbs = self._desk_verbs()
        key = (it, g.tab, tuple(verbs), dk[5][0], dk[7], g.played(it), g.today())
        if key != self._dkey:
            self._dkey = key
            self._dput = (it, verbs, dk)
            import home_ui
            pg.run(home_ui.put, action="put")
            home_ui.ui.commit(pg)
        on = self._button_focus
        host = self._dhost
        if on is not None and verbs:
            host.focus(_BUTTON_IDS[min(on, len(verbs) - 1)])
        host.begin(cv, ws.theme_colors, rect, True, elsewhere=on is None)
        pg.paint(0.0, cv, ws.theme_colors, rect, True)

    def details_put(self, s):
        """What the details pane shows of the selected card (home_ui's `put`)."""
        import home_ui
        it, verbs, dk = self._dput
        g = self.grid
        pseudo = it.get("type") in PSEUDO_TILE_TYPES
        s.title = "New" if it.get("type") == NEW_TILE_TYPE else str(it.get("title") or "")
        s.title_h = _ui_draw.font("title")[2] * dk[5][0] + _TITLE_AIR // dk[5][6]
        facts_on, meta_on = dk[7]
        facts_on = facts_on and not pseudo
        # what the pane's height holds at the text's scale, each a line and
        # half one apart, the facts and the buttons two: the title and the
        # buttons always, the facts, then the metadata, then two lines of
        # the description where there is room for them
        lh = _ui_draw.font()[2] * self.ws.layout.fs
        step = 3 * lh // 2
        room = dk[5][5] - s.title_h - 2 * step
        facts_on = facts_on and room >= 2 * step
        room -= 2 * step if facts_on else 0
        meta_on = meta_on and room >= step
        room -= step if meta_on else 0
        s.meta_on, s.facts_on = meta_on, facts_on
        s.meta = _META_SEP.join(g._meta(it, played=False)) if meta_on else ""
        s.desc = "" if pseudo or room < 2 * lh else str(it.get("description") or "")
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
                setattr(s, home_ui.KINDS[k], _kind(k, v))

    def details_press(self, k):
        """The page's button `k` pressed: its verb."""
        verbs = self._desk_verbs()
        if k < len(verbs):
            self._do_verb(verbs[k])

    def draw_title(self, cv, x, y, w, h):
        """The details' title (the page's canvas): the `title` face at the
        pane's scale, cut with an ellipsis to the pane."""
        ts = self.grid._geom()[9][5][0]
        name = self._dpage.s.title
        was = _ui_draw.print_font(_ui_draw.font("title")[0])
        cv.print_scaled(_ui_draw.print_ellipsis(name, w, ts), x, y, self.ws.theme_colors["ink"], ts)
        if was is not None:
            _ui_draw.print_font(was)

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
