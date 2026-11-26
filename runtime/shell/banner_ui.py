"""The shell's banners as placed pages: `banner`, a toast with its sub line
(the system notice and the notification, each its own page of it),
`badge`, the achievement's (a badge's or a secret's, its shine crossing
it), and `loading`, the flat toast a heavy transition shows until it loads.
Their host (`console_notices.Notices.paint_banner`) writes the words and
places each page where it shows: a banner's card at the top centre of the
page's room, the badge's at its foot, the loading pill filling it. Each
page's toast is keyed `banner` (a secret's `secret`), the name its host
asks its rect by."""

import uitree as ui

s = ui.state(head="", sub="", icon="", burst=0, secret=False)


class NoDamage:
    """A banner page's damage: its layer paints it again every frame it shows."""

    def all(self):
        pass


def banner():
    with ui.page(""):
        ui.toast("{head}", sub="{sub}", icon="{icon}", burst="{burst}", key="banner")


def badge():
    with ui.page(""):
        ui.toast("{head}", sub="{sub}", icon="{icon}", burst="{burst}", look="badge", key="banner",
                 shown="!secret")
        ui.toast("{head}", sub="{sub}", icon="{icon}", burst="{burst}", look="secret", key="secret",
                 shown="secret")


def loading():
    with ui.page(""):
        ui.toast("{head}", icon="{icon}", look="flat", key="banner")
