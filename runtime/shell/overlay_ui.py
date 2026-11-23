"""The shell's small overlays as placed pages: `tip`, the home chevron's
tooltip, and `saver`, the screen saver's cover. Their hosts
(`launcher_layer.LauncherHomeLayer._draw_back_tip`, `idle_ladder.Saver`) write
their words and place them through `console_notices.Notices`
(`put_overlay`, `paint_overlay`)."""

import uitree as ui

s = ui.state(tip="", title="", time="", side=64, covered=False)

COVER = [None]      # the saver's draw of the cover: f(cv, x, y, w, h)


def cover(cv, x, y, w, h):
    COVER[0](cv, x, y, w, h)


class NoDamage:
    """An overlay page's damage: its host paints it again every frame it shows."""

    def all(self):
        pass


def tip():
    with ui.page(""):
        ui.toast("{tip}", icon="home", look="flat", key="tip")


def saver():
    with ui.page(""):
        ui.label("{time}", tone="dim", align="end")
        ui.row("above", grow=True)                  # the cover and its title at the page's foot
        ui.canvas("cover", cover, h="{side}", shown="covered")
        ui.label("{title}", face="title", align="center")
