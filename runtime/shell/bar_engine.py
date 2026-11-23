"""The bars' packing and drawing from the bar pages (`bar_ui`,
`bar_shape_ui`): `pack`
answers what `shell_layout.pack` answers, from the pages' rects: a bar of
the themes' shape (`placed`) the bar page's, a handheld's status cluster
keeping its ring room (`shell_layout.RING_ROOM`); any other bar a shaped
page's (`bar_shape_ui.strip` along a top or bottom bar, `side` down a left
or right one), its widgets the model of `shell_layout.pack`'s cells in the theme's
order. `draw` is a frame of the bar page onto a bar's strip, `draw_shaped`
of a shaped page."""

import bar_shape_ui
import bar_ui
import iconsets as _iconsets
import layout_base as LB
import shell_layout as SL
import status_items as _status
import uitree as S

s = bar_ui.s
ss = bar_shape_ui.s
LEFT = ("menu", "chips", "zone")
RIGHT = ("wifi", "battery", "clock")
_PAGE = [None]
SHOWN = {"menu": "menu_on", "wifi": "wifi_on", "clock": "clock_on"}     # a widget's shown= state, where not its name
_SHOWN = tuple((n, SHOWN.get(n, n)) for n in LEFT + RIGHT if n != "battery")
_DIRTY = [False]                # a state written since the page's store last took the writes
_LAST = [None] * 8              # the bar `_states` wrote last: names, cs, fs, clock_w, sys_len, n, glyph, cluster


def _ordered(names, order):
    j = 0
    for n in names:
        while j < len(order) and order[j] != n:
            j += 1
        if j == len(order):
            return False
        j += 1
    return True


def placed(bar):
    """Whether the engine places `bar` (one of a layout's bars): a top or
    bottom bar of the themes' shape, some of `LEFT` from its start and of
    `RIGHT` from its end, in their order, its zone among them."""
    return (bar[0] in ("top", "bottom") and not bar[3] and "zone" in bar[2]
            and _ordered(bar[2], LEFT) and _ordered(bar[4], RIGHT) and not (len(bar) > 5 and bar[5]))


def _page():
    p = _PAGE[0]
    if p is None:
        import uitree_editor
        p = _PAGE[0] = uitree_editor.page(bar_ui.bar, None, None)
        p.bar = True            # (its tray's icons the zone's size)
        forget()                # (a new page's store holds none of them)
    return p


def forget():
    """What the page was last handed, forgotten: the next draw writes every
    state again. A new page and a new console's bar start here."""
    _WINS[0] = _ITEMS_W[0] = _ITEMS[0] = None
    _SH_MEMO.clear()
    for i in range(len(_LAST)):
        _LAST[i] = None
    _DIRTY[0] = True


def _put(nm, v, st=s):
    """The host's write of what a bar shows into state `st` (the bar
    page's by default; the placement pushes it)."""
    if st._v[nm] != v:
        st._v[nm] = v
        st._ver[nm] += 1
        _DIRTY[0] = True


def _cluster():
    """Whether the bars hold a handheld's status cluster (`shell_layout.pack`'s default)."""
    return LB.metric_class() != LB.DESK


def _row(rect, cs, row):
    """Where a page lies in a bar at `rect`, in the bar's coordinates: the
    bar whole (the themes' bar on a desk), or its icon row (`row`: a
    handheld's, and any strip's), BAR_ROWS units across its middle, so an
    item's icon and the system button are the chrome scale's (a bar item's
    icon is the largest multiple of 16 its row holds)."""
    if not row:
        return (0, 0, rect[2], rect[3])
    h = min(rect[3], LB.BAR_ROWS * cs)
    return (0, (rect[3] - h) // 2, rect[2], h)


def _place(rect, names, cs, fs, clock_w, sys_len, n_items, cluster):
    page = _states(names, cs, fs, clock_w, sys_len, n_items, cluster=cluster)
    page.unit = cs
    page.place(_row(rect, cs, cluster), desk=True)
    return page


_WINS = [None]                  # the `wins` rows last written (the window manager's, kept while they stand)
SEL = [-1]                      # the status item whose menu is open (the bar layer's), -1 none
PAUSED = ["ink_dim"]            # a paused item's ink as a tone: the look's content role (the bar layer's)
_ITEMS = [None, -1, -2, None, -1]   # the `items` rows, and the items' gen, SEL, PAUSED and count they show
_ITEMS_W = [None]               # the `items` rows last written
_KEYS = tuple(str(k) for k in range(_status.CAP))


def _items(n):
    """The `items` rows for `n` status items (`status_items.ITEMS` in its
    order, an item it does not hold yet as the app glyph in the accent): its
    key its index, its icon the set's slot or the app glyph where the set
    has none, its tone its state's ink, the one whose menu is open marked.
    The list is kept while all of that stands."""
    it = _status.ITEMS
    g = it.gen
    c = _ITEMS
    if c[0] is not None and c[1] == g and c[2] == SEL[0] and c[3] is PAUSED[0] and c[4] == n:
        return c[0]
    rows = []
    for k in range(n):
        x = it.at(k)
        icon = x.icon if x is not None else None
        st = x.state if x is not None else _status.ON
        rows.append({"k": _KEYS[k], "icon": icon if icon in _iconsets.SLOT else "app",
                     "on": k == SEL[0],
                     "tone": "danger" if st == _status.ERROR else PAUSED[0] if st == _status.PAUSED
                     else "accent"})
    c[0], c[1], c[2], c[3], c[4] = rows, g, SEL[0], PAUSED[0], n
    return rows


def _states(names, cs, fs, clock_w, sys_len, n_items, glyph=None, wins=None, cluster=False):
    """The page's states written for a bar of widgets `names`; `wins` the
    chips' rows where given (a list the window manager keeps while it
    stands: written again only when it is another); `cluster`, a handheld's
    status cluster, its ring's room round it. The bar written last again
    (`names` the same list) writes nothing."""
    page = _page()
    page._bind()
    n = min(n_items, _status.CAP) if "wifi" in names or "battery" in names else 0
    items = _items(n)
    L = _LAST
    if (L[0] is names and L[1] == cs and L[2] == fs and L[3] == clock_w and L[4] == sys_len
            and L[5] == n and L[6] is glyph and L[7] == cluster and (wins is None or wins is _WINS[0])
            and items is _ITEMS_W[0]):
        return page
    if wins is not None and wins is not _WINS[0]:
        _WINS[0] = wins
        s._v["wins"] = S._check(s._t["wins"], wins, "s.wins")
        s._ver["wins"] += 1
        _DIRTY[0] = True
    if items is not _ITEMS_W[0]:
        _ITEMS_W[0] = items
        s._v["items"] = S._check(s._t["items"], items, "s.items")
        s._ver["items"] += 1
        _DIRTY[0] = True
    sg = max(6 * cs, 4 * fs)        # a gap between inks (an icon item is its ink wide)
    _put("sg", sg)
    _put("cw", clock_w)
    _put("sys_w", sys_len or 16 * cs)
    # a handheld's cluster: RING_ROOM round it, CLOCK_CLEAR more before the clock
    ring = SL.RING_ROOM * fs if cluster else 0
    _put("ring", ring)
    _put("cg", SL.CLOCK_CLEAR * fs if cluster else sg)
    _put("cluster", "wifi" in names or "battery" in names)
    tray = False
    for nm, st in _SHOWN:
        _put(st, nm in names)
    for nm in RIGHT:
        tray = tray or nm in names
    if glyph is not None:
        _put("batt_icon", "battery" in names and not glyph)
        _put("batt_glyph", "battery" in names and glyph)
    elif "battery" not in names or not (s._v["batt_icon"] or s._v["batt_glyph"]):
        _put("batt_icon", "battery" in names)
        _put("batt_glyph", False)
    _put("tray", tray)
    L[0], L[1], L[2], L[3], L[4], L[5], L[6], L[7] = names, cs, fs, clock_w, sys_len, n, glyph, cluster
    return page


def pack(w, h, rows, cs, fs, clock_w, text_w=None, of=None, sys_len=0, cluster=None, items=None):
    """`shell_layout.pack`'s answer, the engine placing every bar of `of`
    where it places them all (`placed`)."""
    if of is None:
        of = LB.bars()
    n_items = SL.ITEMS[0] if items is None else items
    if cluster is None:
        cluster = _cluster()
    packed = None
    for b in of:
        if not placed(b):
            packed = SL.pack(w, h, rows, cs, fs, clock_w, text_w, of, sys_len, cluster, items)
            break
    rects = LB.bar_rects_of(w, h, rows, of)
    ic = 16 * cs
    out = []
    used = []
    for i in range(len(of)):
        bar, rect = of[i], rects[i]
        if not placed(bar):
            used.append(shaped(packed[i][0], packed[i][3]))
            out.append(_shaped_bar(packed[i], cs, fs, clock_w, sys_len, n_items))
            continue
        names = bar[2] + bar[4]
        page = _place(rect, names, cs, fs, clock_w, sys_len, n_items, cluster)
        thick = rect[3]
        iy = 1 + (thick - LB.BAR_ROWS * cs) // 2
        cells = []
        for name in LEFT + ("status",) + RIGHT:
            if name == "status":
                r = _items_span(page, n_items) if s._v["items"] else None
            else:
                r = page.rect_of("battery_st" if name == "battery" and s._v["batt_glyph"] else name)
            if r is None or (name != "status" and name not in names):
                continue
            x, _y, cw, _h = r
            if name in ("menu", "zone", "status", "wifi", "battery"):
                r = (x, iy, cw, ic)
            else:
                r = (x, 0, cw, thick)
            slot = 0 if name in LEFT else 2
            cells.append((name, r, n_items if name == "status" else None, slot))
        out.append((bar[0], rect, (thick - LB.BAR_ROWS * fs) // 2, tuple(cells)))
    for sh in list(_SHAPED):
        if sh not in used:
            _SHAPED.pop(sh).forget()        # (a shaped page no bar of these draws holds no store)
            _SH_MEMO.pop(sh, None)
    return tuple(out)


def _items_span(page, n):
    """The status items' cell: the span of the page's `n` item cells."""
    x0 = x1 = None
    for k in range(min(n, _status.CAP)):
        r = page.rect_of(_KEYS[k] + "/item")
        if r is not None:
            x0 = r[0] if x0 is None else min(x0, r[0])
            x1 = r[0] + r[2] if x1 is None else max(x1, r[0] + r[2])
            y, h = r[1], r[3]
    return None if x0 is None else (x0, y, x1 - x0, h)


def item_rects(rect, names, cs, fs, clock_w, sys_len, n_items, out):
    """The status items of a bar at `rect` (a packed bar of the page's
    shape): their rects in its bar's coordinates into `out` (cleared), in
    the items' order."""
    page = _place(rect, names, cs, fs, clock_w, sys_len, n_items, _cluster())
    del out[:]
    for k in range(min(n_items, _status.CAP)):
        r = page.rect_of(_KEYS[k] + "/item")
        if r is not None:
            out.append(r)
    return out


def chip_rects(rect, names, cs, fs, clock_w, sys_len, n_items, wins, out):
    """The chips of a bar at `rect` (a packed bar of the page's shape) for
    the window manager's rows `wins`: [(kind, rect)] into `out` (cleared)
    on the canvas the bar lies on, a chip the row's fit rule dropped left
    out."""
    cluster = _cluster()
    page = _states(names, cs, fs, clock_w, sys_len, n_items, wins=wins, cluster=cluster)
    page.unit = cs
    page.place(_row(rect, cs, cluster), desk=True)
    del out[:]
    for row in wins:
        k = row["k"]
        r = page.rect_of(k + "/chip")
        if r is not None:
            out.append((k, (rect[0] + r[0], rect[1] + r[1], r[2], r[3])))
    return out


def item_key(k):
    """The id of status item `k`'s stop on the page."""
    return _KEYS[k] + "/item"


def chip_key(kind):
    """The id of window `kind`'s chip's stop on the page."""
    return kind + "/chip"


def fire(stop):
    """The action of the page's stop `stop` (an id `_page_stop` named: a
    widget's name, `item_key(k)`) run as the page runs it."""
    page = _page()
    page._bind()
    acts = page.actions
    if stop.endswith("/item"):
        k = stop[:-5]
        for row in s._v["items"]:
            if row.k == k:
                page.run_action(acts["item"], (row,), "the bar's keys")
                return
        return
    if stop.endswith("/chip"):
        k = stop[:-5]
        for row in s._v["wins"]:
            if row.k == k:
                page.run_action(acts["chip"], (row,), "the bar's keys")
                return
        return
    page.run_action(acts[stop], (), "the bar's keys")


class _NoDamage:
    """The page's damage: a bar's strip is drawn again when its key moves
    (`BarLayer._draw_bar`), never because the page asked."""

    def all(self):
        pass

    def add(self, *a):
        pass


_CTX = [None]                   # the bar's own toolkit context (its stops, its kept state)
_D = [None]


def _ui_draw():
    D = _D[0]
    if D is None:
        import ui_draw as D
        _D[0] = D
    return D
_ROW_AT = [0, 0, None, 0]       # a handheld bar's scale and height, its icon row's rect, its offset
_ORIGIN = [0, 0]                # where the page is drawn on its canvas: the bar's origin there


def draw(cv, th, rect, names, cs, fs, clock_w, sys_len, n_items, wicon, time, glyph, clip=None,
         wins=None, focus=None):
    """A frame of the bar page drawn onto `cv` at `rect` (a bar's, on its
    strip at 0, 0 or on a canvas the bar lies on), placed as `pack` placed
    it, the canvases drawn by `bar_ui.PAINT` in the bar's own coordinates.
    `clip` (on `cv`, which the caller has clipped to it): the part drawn
    again, every draw inside it, and `cv` left clipped to it. The
    toolkit's target the host's frame set is given back. `focus`: the id
    of the page's stop the keys are on (its bar item draws the focus mark),
    None while they are elsewhere."""
    cluster = _cluster()
    page = _states(names, cs, fs, clock_w, sys_len, n_items, glyph, wins, cluster)
    oy = 0
    if cluster:
        m = _ROW_AT
        k = m[2]
        if k is None or m[0] != cs or m[1] != rect[3] or k[0] != rect[0] or k[2] != rect[2] \
                or k[1] - m[3] != rect[1]:
            row = _row(rect, cs, cluster)
            m[0], m[1], m[3] = cs, rect[3], row[1]
            m[2] = (rect[0], rect[1] + row[1], rect[2], row[3])
        rect, oy = m[2], m[3]       # (kept while the bar's place stands)
    _put("wicon", wicon)
    _put("time", time)
    if _DIRTY[0]:
        _DIRTY[0] = False
        _commit(page)
    return _frame(page, cv, th, rect, oy, cs, clip, focus)


def _commit(page):
    pushed = getattr(page, "committed", None)
    if pushed is not None:
        pushed()                # the C engine's store takes the writes


def _frame(page, cv, th, rect, oy, cs, clip, focus):
    if page._damage is None:
        page._damage = _NoDamage()
    D = _ui_draw()
    ctx = _CTX[0]
    if ctx is None:
        ctx = _CTX[0] = D.ui_context()
    t = D.UI_TARGET
    a, b, c, d = t[0], t[1], t[2], t[3]
    _ORIGIN[0] = rect[0]
    _ORIGIN[1] = rect[1] - oy
    page.clip_to = clip
    try:
        if focus is not None:
            D.focus_on(ctx, focus)
        D.ui_frame(ctx, cv, th, rect=rect, desk=True, elsewhere=focus is None)
        page.unit = cs
        page.bare = True
        page.band = False       # the keys' names are the host's strip's (`ui_draw.BAR_KEYS`)
        page.paint(0, cv, th, rect, True)
    finally:
        page.clip_to = None
        t[0], t[1], t[2], t[3] = a, b, c, d
        if clip is not None:
            cv.clip(clip[0], clip[1], clip[2], clip[3])
    return page


# -- a bar of any other shape (`bar_shape_ui.strip`, `bar_shape_ui.side`) --------------
#
# Its widgets are the packed cells' (shell_layout.pack's names, slots and
# texts, in the theme's order), each slot a model's rows; where they lie is
# the page's, which `pack` reads back into the cells.

_SHAPED = {}                    # "strip" / "side": its page
_SH_ROW_AT = [0, 0, None, 0]    # a strip's scale and height, its icon row's rect, its offset
_SH_MEMO = {}                   # "strip" / "side": the cells, the `wins` and the `items` rows its store took
_SH_KEYS = tuple(tuple("%d.%d" % (j, i) for i in range(16)) for j in range(3))
_SLOTS = ("lead", "mid", "tail")
SHOW_X = _SHOW_X = [True]       # whether the shaped page's close widget shows its X
_ICON = ("menu", "close", "wifi", "battery")
_SIDE_FILLS = ("zone", "chips", "spacer")     # the widgets that fill down a side bar (its title a line)
# A widget's node on the shaped page: its bar item's (`widget`) where not this
_NODE = {"chips": "chips", "zone": "zone", "spacer": "spacer", "close": "close_x",
         "title": "label#0", "text": "label#0", "separator": "rule#0"}


def shaped(edge, cells):
    """Which shaped page draws a packed bar: "side" a left or right bar,
    "strip" a top or bottom bar the themes' page does not draw (`placed`),
    None that page's."""
    if edge in ("left", "right"):
        return "side"
    side = 0
    zone = False
    for name, _r, _t, slot in cells:
        if name in LEFT:
            if slot != 0 or side:
                return "strip"
            zone = zone or name == "zone"
        elif name in RIGHT or name == "status":
            if slot != 2:
                return "strip"
            side = 1
        else:
            return "strip"
    return None if zone else "strip"


def _shaped_page(sh):
    p = _SHAPED.get(sh)
    if p is None:
        import uitree_editor
        p = _SHAPED[sh] = uitree_editor.page(bar_shape_ui.side if sh == "side" else bar_shape_ui.strip, None, None)
        p.bar = True
        _SH_MEMO.pop(sh, None)
    return p


def _slot_row(k, kind, text):
    return {"k": k, "kind": kind, "text": text}


def _shaped_states(sh, cells, rect, cs, fs, clock_w, sys_len, n_items, glyph=None, wins=None):
    """The shaped page `sh` with its states written for packed `cells` on
    a bar at `rect` (kept while the same cells, items, windows and
    battery stand). Down a side bar the system button's cell is its tile's
    height (`layout_base.sys_tile`)."""
    page = _shaped_page(sh)
    page._bind()
    items = _items(0 if sh == "side" else min(n_items, _status.CAP))
    L = _SH_MEMO.get(sh)
    if L is None:
        L = _SH_MEMO[sh] = [None, None, None]
    if wins is not None and wins is not L[1]:
        L[1] = wins
        ss._v["wins"] = S._check(ss._t["wins"], wins, "s.wins")
        ss._ver["wins"] += 1
    if items is not L[2]:
        L[2] = items
        ss._v["items"] = S._check(ss._t["items"], items, "s.items")
        ss._ver["items"] += 1
    if L[0] is not cells:
        slots = ([], [], [])
        n = [0, 0, 0]
        for name, _r, text, slot in cells:
            if name == "status":
                if items:
                    slots[slot].append(_slot_row("st", "status", ""))
                continue
            slots[slot].append(_slot_row(_SH_KEYS[slot][min(n[slot], 15)], name, text or ""))
            n[slot] += 1
        # a strip's middle centred on it; the fills between the ends where
        # nothing else fills (and down a side bar either side of a middle
        # holding a fixed widget)
        fills = _SIDE_FILLS if sh == "side" else SL.FLEX
        gaps = True
        for row in slots[0] + slots[1] + slots[2]:
            gaps = gaps and row["kind"] not in fills
        if sh == "side":
            for row in slots[1]:
                gaps = gaps or row["kind"] not in fills
        else:
            gaps = gaps and not slots[1]
        _put("gaps", gaps, ss)
        _put("middle", bool(slots[1]), ss)
        for j in range(3):
            nm = _SLOTS[j]
            ss._v[nm] = S._check(ss._t[nm], slots[j], "s." + nm)
            ss._ver[nm] += 1
        L[0] = cells
    sg = max(6 * cs, 4 * fs)
    _put("sg", sg, ss)
    _put("cw", clock_w, ss)
    if sh == "side":
        sys_len = LB.sys_tile(rect[2])[1]
    _put("sys_w", sys_len or 16 * cs, ss)
    if glyph is not None:
        _put("batt_icon", not glyph, ss)
        _put("batt_glyph", bool(glyph), ss)
    page.unit = cs
    return page


def _cell_rect(page, sh, name, key, r, thick, cs):
    """A packed cell's rect read off shaped page `page` (bar coordinates),
    across the bar as `shell_layout.pack` sets it; `r` (its packing's)
    where the page places none of it."""
    side = sh == "side"
    if name == "battery":
        got = page.rect_of(key + "/widget") or page.rect_of(key + "/battery_st")
    elif name == "status":
        got = _items_span(page, len(ss._v["items"]))
    elif name == "chips" and side:
        got = None
        for row in ss._v["wins"]:
            c = page.rect_of(row.k + "/chip")
            if c is not None:
                got = c if got is None else (got[0], got[1], got[2], c[1] + c[3] - got[1])
        if got is None:
            return (r[0], r[1], r[2], 0)
    else:
        got = page.rect_of(key + "/" + _NODE.get(name, "widget"))
    if got is None:
        return r if name == "zone" else (r[0], r[1], 0, 0)
    ic = 16 * cs
    x, y, w, h = got
    if side:
        if name in _ICON:
            return ((thick - ic) // 2, y + (h - ic) // 2, ic, ic)
        return (0, y, thick, h)
    if name in _ICON or name in ("zone", "title", "separator", "status"):
        return (x, 1 + (thick - LB.BAR_ROWS * cs) // 2, w, ic)
    return (x, 0, w, thick)


def _shaped_bar(packed, cs, fs, clock_w, sys_len, n_items):
    """Packed bar `packed` (shell_layout.pack's) with its cells where the
    shaped page places them."""
    edge, rect, dy, cells = packed
    sh = shaped(edge, cells)
    page = _shaped_states(sh, cells, rect, cs, fs, clock_w, sys_len, n_items)
    _commit(page)
    page.place(_row(rect, cs, sh == "strip"), desk=True)
    thick = rect[2] if sh == "side" else rect[3]
    out = []
    n = [0, 0, 0]
    for name, r, text, slot in cells:
        if name == "status":
            key = ""
        else:
            key = _SH_KEYS[slot][min(n[slot], 15)]
            n[slot] += 1
        out.append((name, _cell_rect(page, sh, name, key, r, thick, cs), text, slot))
    return (edge, rect, dy, tuple(out))


def draw_shaped(cv, th, rect, edge, cells, cs, fs, clock_w, sys_len, n_items, wicon, time, glyph,
                title, show_x, clip=None, wins=None):
    """A frame of the shaped page that draws packed bar `cells` (`shaped`)
    onto `cv` at `rect`, as `draw` draws the bar page; `title` its title
    widget's words, `show_x` whether its close widget shows its X
    (`bar_ui.PAINT`'s to draw)."""
    _SHOW_X[0] = show_x
    sh = shaped(edge, cells)
    page = _shaped_states(sh, cells, rect, cs, fs, clock_w, sys_len, n_items,
                          glyph, wins)
    _put("wicon", wicon, ss)
    _put("time", time, ss)
    _put("title", title, ss)
    _commit(page)
    oy = 0
    if sh == "strip":
        m = _SH_ROW_AT
        k = m[2]
        if k is None or m[0] != cs or m[1] != rect[3] or k[0] != rect[0] or k[2] != rect[2] \
                or k[1] - m[3] != rect[1]:
            row = _row(rect, cs, True)
            m[0], m[1], m[3] = cs, rect[3], row[1]
            m[2] = (rect[0], rect[1] + row[1], rect[2], row[3])
        rect, oy = m[2], m[3]       # (kept while the bar's place stands)
    return _frame(page, cv, th, rect, oy, cs, clip, None)


def shaped_item_rects(rect, edge, cells, cs, fs, clock_w, sys_len, n_items, out):
    """The status items of shaped packed bar `cells` at `rect`: their
    rects in its bar's coordinates into `out` (cleared), in their order."""
    sh = shaped(edge, cells)
    page = _shaped_states(sh, cells, rect, cs, fs, clock_w, sys_len, n_items)
    _commit(page)
    page.place(_row(rect, cs, edge in ("top", "bottom")), desk=True)
    del out[:]
    for k in range(min(n_items, _status.CAP)):
        r = page.rect_of(_KEYS[k] + "/item")
        if r is not None:
            out.append(r)
    return out


def shaped_chip_rects(rect, edge, cells, cs, fs, clock_w, sys_len, n_items, wins, out):
    """The chips of shaped packed bar `cells` at `rect` for the window
    manager's rows `wins`: [(kind, rect)] into `out` (cleared) on the
    canvas the bar lies on, a chip the fit rule dropped left out."""
    sh = shaped(edge, cells)
    page = _shaped_states(sh, cells, rect, cs, fs, clock_w, sys_len, n_items,
                          wins=wins)
    _commit(page)
    page.place(_row(rect, cs, edge in ("top", "bottom")), desk=True)
    del out[:]
    for row in wins:
        k = row["k"]
        r = page.rect_of(k + "/chip")
        if r is not None:
            out.append((k, (rect[0] + r[0], rect[1] + r[1], r[2], r[3])))
    return out
