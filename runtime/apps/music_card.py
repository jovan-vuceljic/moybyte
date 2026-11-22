"""Music's status section (runtime/system/status_items.py, SECTION): the
compact card as a page Music builds. The head -- the art, the title, the
state line, the chevron -- is one stop that opens the app; the transport sits
under it on a 1:2:1 + 1 grid, the two on a card; on the desk the volume
follows under the card.
What plays is drawn from the stream (`music_app.STREAM`); the main button's
icon is this page's state, written on each `item.changed()`."""

import uitree as ui
import uitree_app
import music_app as M

H = 84                      # the card at font scale 1: 6 + head 40 + 6 + transport 26 + 6
H_DESK = 156                # the desk's: 10 + the card (10 + 40 + 10 + 26 + 10) + 10 + the volume's 30 + 10

s = ui.state(main_icon="pause", vol=0)


def _sec():
    return uitree_app.env()


def changed():
    """The item's section moved: the main button's icon."""
    c = M.STREAM.card
    s.main_icon = M.MAIN.get(M.FAILED if c and c["state"] == M.FAILED else
                             M.PAUSED_ if c and c["paused"] else M.PLAYING)[0]
    s.vol = M.level(c)


def opened():
    changed()


def draw_head(cv, x, y, w, h):
    """The head: the art 36 px square, the title, the state line, the
    chevron."""
    c = M.STREAM.card
    if c is None:
        return
    fs = M._fs(cv)
    a = 36 * fs
    M.head(cv, ui.colors(), c, x + 4 * fs, y + (h - a) // 2, w - 8 * fs, a, fs,
           desk=M._lb.metric_class() == M._lb.DESK)


def head_keys(i):
    """Enter on the head opens the app; the arrows move focus."""
    if i.pressed("a") or i.pressed("run"):
        open_app()
        return True
    return False


def head_at(ev):
    if ev.kind == "up":
        open_app()


def open_app():
    _sec().open()


def main():
    M.STREAM.toggle()


def prev():
    M.STREAM.step(-1)


def next_():
    M.STREAM.step(1)


def stop():
    M.STREAM.stop()


def quieter():
    M.STREAM.volume(M.STREAM.volume() - M.VOLUME_STEP)


def louder():
    M.STREAM.volume(M.STREAM.volume() + M.VOLUME_STEP)


ui.hook("opened", opened)
ui.hook("changed", changed)
ui.hook("head_at", head_at, takes="pointer")
ui.hook("vol_set", lambda: M.set_level(s.vol))
ui.action("main", "Play", main)
ui.action("prev", "Previous", prev)
ui.action("next", "Next", next_)
ui.action("stop", "Stop", stop)
ui.action("quieter", "Quieter", quieter)
ui.action("louder", "Louder", louder)


def _card():
    ui.canvas("head", draw_head, keys=head_keys, pointer="head_at")
    with ui.grid(5, 1, gap="s"):
        ui.button("prev", icon="prev", label="")
        ui.button("main", "primary", icon="{main_icon}", label="", span=2)
        ui.button("next", icon="next", label="")
        ui.button("stop", icon="stop", label="")


def page():
    with ui.page(""):
        # each split ends in an empty weighted cell: its last fixed cell keeps its whole size
        with ui.split("col", sizes=(84, "1*"), gap="0", pad="0", shown="!@desk"):
            with ui.group("", look="card"):
                with ui.split("col", sizes=(40, 26, "1*"), gap="s", pad="s"):
                    _card()
                    ui.label("")
            ui.label("")
        with ui.split("col", sizes=(96, 30, "1*"), gap="s", pad="s", shown="@desk"):
            with ui.group("", look="card"):
                with ui.split("col", sizes=(40, 26, "1*"), gap="s", pad="s"):
                    _card()
                    ui.label("")
            with ui.split("row", sizes=(32, 38, "1*", 12, 32), gap="0", pad="0"):
                ui.button("quieter", icon="minus", label="")
                ui.label("", icon="volume")
                ui.slider("", "vol", 0, 10, look="blocks", on="vol_set")
                ui.label("")
                ui.button("louder", icon="plus", label="")
            ui.label("")
