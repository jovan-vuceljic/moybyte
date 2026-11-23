# Map (grep -n a name to jump there):
#   HomeSearch                        the mixin the home's search lives on
#   HomeSearch._search_close_items    the key that closes search, as the strip names it
#   HomeSearch._search_tap            a tap on the search line
"""The home's SEARCH (the Games tab's, the fullscreen home's alone): the
search field is the hint strip's page's (`home_strip_ui.strip`, drawn in
the verbs' place, or on the ground under touch; `home_hints` puts its
state and feeds it the keys while a query is typed). Here: the key that
closes it and a tap on its line. A mixin over `LauncherHomeLayer`, its last
base: it runs while search is open, on an event. Whether search is open
and where its line lies (`_search_open`, `_search_line`) stay on the
class: the band and still frames ask them on every frame. It owns no state
of its own: the query is the console's (`ws.search_query`,
`ws.search_typing`).
"""

import ui as _ui
_in = _ui.rect_in   # one hit-test (ui.rect_in)


class HomeSearch:
    """The search line, its tap and its typing of `LauncherHomeLayer`."""

    def typing(self):
        """A query being typed takes the keyboard."""
        return self.ws.search_typing

    def cancel(self):
        """Mic while a query is typed: the box closes, cleared."""
        if not self.ws.search_typing:
            return False
        self.ws.home.close_search(clear=True)
        return True

    def _search_close_items(self):
        """The strip's way out of search: a field's cancel while typing (the
        T-Deck's Mic, where its K types), else back."""
        return ("cancel" if getattr(self.ws, "search_typing", False) else "back", "Close")

    def _search_tap(self, px, py):
        """A tap on the search line closes search, cleared (under touch its
        only way out but the system menu's Clear search)."""
        line = self._search_line()
        if line is None:
            return False
        tabs = self.hint_rect("tabs")
        x1 = tabs[0] if tabs is not None else line[0] + line[2]
        if not _in(px, py, (line[0], line[1], x1 - line[0], line[3])):
            return False
        self.ws.home.close_search(clear=True)
        return True
