"""The status items' rows as a page (`popover.ControlCenter`,
`popover.StatusMenu`, `popover.PowerRows`): on a handheld the control
center -- the console's group (Volume, Brightness, Wi-Fi), then each app's
rows in a group under its app's name, in the bar's order; on the desk one
item's menu, its rows alone, and the battery's popover, the console's group
with the battery's line in place of Wi-Fi. An item's rows are its panel
(`status_items.Panel`, one model a slot); a bare item lists one row, Open,
which opens its app. An item whose section is a page gets a slot, a canvas
its section's height tall, which the host paints with the section's own
engine (`popover._Rows`) and hands the keys while it holds focus."""

import uitree as ui
import uitree_app
import status_items as _status

CAP = _status.CAP
KINDS = ("text", "button", "toggle", "slider")      # status_items' row kinds, in its order

_ROW = ui.model(key="id", id="", kind=ui.enum(*KINDS, init="text"), label="", value="", flag=False, v=0,
                lo=0, hi=1)
_decl = dict(cc=True, power=False, battery="Battery", vol=0, vlo=0, vhi=1, vicon="volume", bri=0, blo=0, bhi=1,
             wicon="wifi", net="Off", light=True, radio=True)
for _k in range(CAP):
    _decl["app%d" % _k] = ""
    _decl["on%d" % _k] = False
    _decl["r%d" % _k] = _ROW
    _decl["pg%d" % _k] = False      # its section is a page: a slot, sh%d tall
    _decl["sh%d" % _k] = 0
s = ui.state(**_decl)


def _host():
    return uitree_app.env()


def _level(key, v):
    _host().level(key, v)


def _vol():
    _level("volume", s.vol)


def _bri():
    _level("brightness", s.bri)


def _wifi():
    _host().wifi()


def _press(row):
    _host().press(row)


def _slot(cv, x, y, w, h):
    """A page section's slot: the host paints the section in it."""


def _slot_keys(g):
    def keys(i):
        return _host().slot_keys(g, i)
    return keys


_SLOT_KEYS = tuple(_slot_keys(g) for g in range(CAP))


ui.action("louder", "Volume", _vol)
ui.action("brighter", "Brightness", _bri)
ui.action("wifi", "Wi-Fi", _wifi)
ui.action("press", "Choose", _press, takes="row")

_CASES = {
    "text": lambda: ui.info("{.label}", "{.value}"),
    "button": lambda: ui.link("press", label="{.label}"),
    "toggle": lambda: ui.toggle("{.label}", ".flag", on="press"),
    "slider": lambda: ui.slider("{.label}", ".v", "{.lo}", "{.hi}", on="press"),
}


def page():
    with ui.page(""):
        with ui.group("", shown="cc || power", look="card"):
            ui.info("{battery}", icon="battery", shown="power")
            ui.slider("Volume", "vol", "{vlo}", "{vhi}", look="steps", icon="{vicon}", on="louder")
            ui.slider("Brightness", "bri", "{blo}", "{bhi}", look="steps", icon="spark", on="brighter",
                      shown="light")
            ui.link("wifi", "{net}", icon="{wicon}", shown="cc && radio")
        for k in range(CAP):
            with ui.group("{app%d}" % k, shown="on%d && !pg%d" % (k, k)):
                ui.rows("r%d" % k, by="kind", cases=_CASES)
            with ui.group("{app%d}" % k, shown="on%d && pg%d" % (k, k)):
                ui.canvas(SLOTS[k], _slot, h="{sh%d}" % k, keys=_SLOT_KEYS[k], mark=False)


SLOTS = tuple("sec%d" % k for k in range(CAP))     # each group's slot's key


# Each slot's rows' ids, made once: "k.r", and "k." a bare item's Open.
_IDS = tuple(tuple("%d.%d" % (k, r) for r in range(_status.ROWS_MAX)) for k in range(CAP))
_OPEN = tuple("%d." % k for k in range(CAP))


def rows_of(it):
    """Item `it`'s rows as the page's model holds them."""
    p = _status.ITEMS.panels[it.k]
    if not p.n:
        return [{"id": _OPEN[it.k], "kind": "button", "label": "Open", "value": "", "flag": False,
                 "v": 0, "lo": 0, "hi": 1}]
    ids = _IDS[it.k]
    return [{"id": ids[r], "kind": KINDS[p.kind[r]], "label": p.label[r], "value": p.value[r],
             "flag": p.v[r] == 1, "v": p.v[r], "lo": p.lo[r], "hi": p.hi[r] if p.hi[r] > p.lo[r] else p.lo[r] + 1}
            for r in range(p.n)]


def put_items(items, named, desk):
    """The groups' states for `items` (the items shown, in order, at most
    CAP): its app's name where `named`, its rows or its page's slot; the
    groups past them hidden."""
    for g in range(CAP):
        it = items[g] if g < len(items) else None
        setattr(s, "on%d" % g, it is not None)
        if it is not None:
            setattr(s, "app%d" % g, (it.app or "") if named else "")
            page = _status.ITEMS.page(it) is not None
            setattr(s, "pg%d" % g, page)
            if page:
                setattr(s, "sh%d" % g, _status.ITEMS.height(it, desk))
            else:
                setattr(s, "r%d" % g, rows_of(it))


def pressed(row):
    """(the item's slot, the row's index, its value) of the page's `row`;
    the index -1 a bare item's Open."""
    k, _, r = row.id.partition(".")
    kind = row.kind
    v = (1 if row.flag else 0) if kind == "toggle" else row.v if kind == "slider" else 1
    return int(k), int(r) if r else -1, v


def poll(host):
    """The host's half as the page shows it (`host.poll`), written only
    where it moved."""
    host.poll(s)


ui.hook("cc_poll", poll, takes="arg")
