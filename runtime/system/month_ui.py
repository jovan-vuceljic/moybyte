"""The clock popover's month as a page (`popover.MonthView`): the month
it is paged to, today marked in this month; on the desk and under touch
its head's chevrons page it. The host's half (`month`, `page`) reaches the
handlers as the page's env."""

import uitree as ui
import uitree_app

s = ui.state(y=2026, m=1, today=0)


def prev():
    uitree_app.env().page(-1)


def next_month():
    uitree_app.env().page(1)


def poll(host):
    """The month the host is paged to."""
    s.y = host.y
    s.m = host.m
    s.today = host.d


ui.action("prev", "Previous month", prev)
ui.action("next", "Next month", next_month)
ui.hook("month_poll", poll, takes="arg")


def page():
    with ui.page(""):
        ui.month(year="{y}", month="{m}", today="{today}", prev="prev", next="next")
