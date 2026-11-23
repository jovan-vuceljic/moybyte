# Map (grep -n a name to jump there):
#   HomeZone                    the mixin the home's part of the bar lives on
#   HomeZone.zone_verbs         the active tab's verbs on the selected card
#   HomeZone.bar_zone           the tabs' row lent to the bar (home_bar_ui.head)
#   HomeZone.head_sync          the open tab written into the row's state
#   HomeZone.zone_open_tab      a tab the row took, opened
#   HomeZone.tab_box            where a tab's cell is on the glass
"""The home's part of the bar (Stage 4, #46 zoned bar): its tabs, a row
lent to the bar (`home_bar_ui.head`, `ui.tools(lend="bar")` holding a
`ui.tabs`) that the bar's zone replays and walks with its own keys
(`bar_zone`, `uitree_editor.BarZone`, drawn by `bar_layer.ZoneLook`), and
the active tab's verbs on the selected card (`zone_verbs`, the
docs/theme_and_shell_2026-11.md §12 table) the hint strip and the card's
menu name. A mixin over `LauncherHomeLayer`, after its hints and details
among the bases; `zone_gen`, the one int the bar's strip cache reads every
frame through the row, stays on the class.
"""

from home_grid import NEW_TILE_TYPE, PSEUDO_TILE_TYPES


class HomeZone:
    """The home's part of the bar of `LauncherHomeLayer`: its tabs and its verbs."""

    def zone_verbs(self):
        """The active tab's verbs on the selected card (§12's table): Games
        PLAY, CHANGE, SEARCH; Mine PLAY, CHANGE; Apps OPEN; Make NEW, CHANGE,
        COPY, DEL. CHANGE, COPY and DEL need a real cart and a store that
        manages projects, and DEL one a Delete takes (`CartManager.deletable`,
        the open-cart menu's own test: a core built-in is copied, never
        deleted); the "+ New"
        card's verb is NEW. SEARCH is the
        fullscreen home's alone."""
        ws = self.ws
        grid = self.grid
        tab = grid.tab
        sel = grid.selected()
        real = sel is not None and sel.get("path") \
            and sel.get("type") not in PSEUDO_TILE_TYPES
        change = bool(real) and bool(getattr(ws, "can_manage", True))
        if tab == "apps":
            return ("open",) if real else ()
        if tab == "make":
            if not getattr(ws, "can_manage", True):
                return ()                        # a read-only store makes nothing
            if not change:
                return ("new",)
            if not ws.carts.deletable(sel):
                return ("new", "change", "copy")
            return ("new", "change", "copy", "delete")
        if sel is not None and sel.get("type") == NEW_TILE_TYPE:
            return ("new",)
        out = ("play", "change") if change else (("play",) if real else ())
        if tab == "games" and self.searchable:
            out = out + ("search",)
        return out

    _zone = None         # the tabs' row (`bar_zone`), made on first ask

    @property
    def bar_zone(self):
        """The bar's zone: the tabs' row (`home_bar_ui.head`) replayed by
        `uitree_editor.BarZone` in the bar's look for a lent row
        (`bar_layer.ZoneLook`) on this home's strip, this layer its host."""
        z = self._zone
        if z is None:
            import ui_host
            import uitree_editor
            import home_bar_ui
            from bar_layer import ZoneLook
            page = uitree_editor.page(home_bar_ui.head, ui_host.AppHost(), self, env=self)
            page.open(hook="none")
            z = self._zone = uitree_editor.BarZone(page, ZoneLook(self.ws, self.strip), host=self)
        return z

    def head_sync(self):
        """The open tab, written into the row's state (before each of its
        passes: a strip drawn, a tap, the bar's keys)."""
        self._zone.engine.run(self._head_write)

    def _head_write(self):
        import home_bar_ui
        tab = self.grid.tab
        if home_bar_ui.s.tab != tab:
            home_bar_ui.s.tab = tab

    def zone_open_tab(self, tab):
        """A tab the row took (a tap, confirm on the bar's keys): opened,
        its cards' keys the home's."""
        self.ws.home.set_home_tab(tab, self.grid)
        self.ws.mark_dirty()

    def tab_box(self, tab):
        """Where tab `tab`'s cell is on the bar, (x, y, w, h) on the
        glass, or None where the bar shows none."""
        bl = self.ws.bar_layer
        got = bl.cell(self.strip, "zone")
        if got is None:
            return None
        bar = got[0]
        zone = bl.lent_zone(self.strip, bar)
        if zone is None:
            return None
        if bl.draws_back(self.strip):
            zone = bl.past_back(zone, bl.zone_is_game(self.strip))
        r = self.bar_zone.box("tab", tab, zone)
        if r is None:
            return None
        return (bar[1][0] + r[0], bar[1][1] + r[1], r[2], r[3])
