"""The shell's banners as placed pages: `banner`, a toast with its sub line
(the achievement unlock, the system notice and the notification, each its
own page of it), and `loading`, the flat toast a heavy transition shows
until it loads. Their host (`console_notices.Notices.paint_banner`) writes
the words and places each page where it shows: a banner's card at the top
centre of the page's room, the loading pill filling it. Each page's toast
is keyed `banner`, the name its host asks its rect by."""

import uitree as ui

s = ui.state(head="", sub="", icon="", burst=0)


class NoDamage:
    """A banner page's damage: its layer paints it again every frame it shows."""

    def all(self):
        pass


def banner():
    with ui.page(""):
        ui.toast("{head}", sub="{sub}", icon="{icon}", burst="{burst}", key="banner")


def loading():
    with ui.page(""):
        ui.toast("{head}", icon="{icon}", look="flat", key="banner")
