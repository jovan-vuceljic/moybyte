"""The home's row lent to the shell's bar (`tools lend="bar"`, replayed
into the bar's zone by `uitree_editor.BarZone`, drawn by
`bar_layer.ZoneLook`): the home's tabs, the Editor's tab ladder's kind. The
row joins the bar's key walk: the walk moves the bar's focus, confirm or a
tap opens the tab. Where the zone holds every tab named each is a chip;
where it does not, the open one is named and the rest are icons.

The host is the home layer (`home_zone.HomeZone`: the fullscreen home's
and the desk's Projects window's): it writes the open tab into the state
(`head_sync`) and opens the tab the row takes (`zone_open_tab`)."""

import uitree as ui
import uitree_app
from home_grid import HOME_TABS

s = ui.state(tab=ui.enum(*[t for t, _l in HOME_TABS], init=HOME_TABS[0][0]))
ui.labels("TABS", dict(HOME_TABS))
# Each tab's icon, a slot of every icon set (iconsets.SLOTS): the play
# triangle, the player's own folder, the apps' grid, a page under a pencil.
ui.labels("TAB_ICONS", {"games": "play", "mine": "folder", "apps": "app", "make": "projects"})


def _open():
    """A tab taken on the bar (the open one again too)."""
    uitree_app.env().zone_open_tab(s.tab)


ui.action("open_tab", "Open", _open)


def head():
    with ui.page("Home"):
        with ui.tools("head", lend="bar"):
            ui.tabs("tab", "TABS", icons="TAB_ICONS", on="open_tab")
