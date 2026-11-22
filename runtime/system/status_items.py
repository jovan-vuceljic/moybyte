"""App status items (docs/theme_and_shell_2026-11.md §8.6): what an app puts
in the bar with `moybyte.status`, the menu-extra model.

  item = moybyte.status(icon, section, order=0)
                    a status item of the calling process, None where the
                    bar holds CAP already: `icon` a name of the console's
                    icon set, `section` what its menu draws, `order` where it
                    stands among the others (lower first, ties by age)
  item.show(state=ON)   in the bar, its icon in the state's ink: ON the
                    accent, PAUSED the paused ink, ERROR the danger ink
  item.changed()    what the section draws moved: the bar and an open menu
                    draw it again
  item.remove()     out of the bar, its menu closed

A SECTION is the app's part of the shell's surfaces (on the desk the
menu's card, on a handheld its card in the control center,
`runtime/system/cc_ui.py`). A Python program's section is either a page or
rows. A PAGE is a small `uitree` page the app builds with its usual API, a
canvas included:

  section.page             the page's build function; its module's state
                    and handlers are the section's own
  section.height(desk)     its height in pixels at font scale 1, at most
                    SECTION_H_MAX: the slot the shell gives it

The shell gives it a slot in the control center or the desk menu, drawn by
the section's own engine and clipped to the slot; taps and keys inside the
slot reach that engine, run as the item's process, and the menu's focus
enters and leaves the slot but is never held by it. Its module's `changed`
hook, where it declares one, runs on each `item.changed()`. ROWS are an
object of two methods:

  section.panel()          its description (below), read when the item is
                    added and on each `item.changed()`
  section.press(id, value) a row acted: a button's value 1, a toggle's 0 or
                    1, a slider's step; run as the item's process

THE TABLE is the kernel's (native/moy_kernel/moy_status.h, through the
module `moy_evq`): each slot's process, icon, state, order and whether it
shows, written from any task -- a compiled or a Lua program's status rows
run on its own task, VM or no VM (native/moy_app/moy_app.c, how "here") -- and this
face's own writes go through it too. Every item is a preallocated record
(CAP of them) mirroring its slot, read again whenever the table's
generation moved (`sync`, which `shown`, `gen` and `layout_gen` run): a
draw and a quiet frame allocate nothing. The sections stay here, a Python
program's its own and a compiled or Lua program's its Panel. The process's end
sweeps its items (`moybyte.ENDS`).

An item with no section has no menu: its tap opens its app (on the desk
the cell's tap, on a handheld its card's one Open row).

A COMPILED program (a wasm app, a WASI program, an ELF module) and a LUA
program (native/moy_app/moy_app_lua.c) never run Python in the shell, so
they describe their panel through `moybyte.status_panel`, the one status row
the VM serves (`moybyte.panel_of`, through runtime/shell/shell_servers.py's
ConsoleCalls for a compiled program and the console call for a Lua one), and
hear a press as a message. Its handle is the slot's number from 1. A
description, a Python section's too, is lines of text, one row each, at
most ROWS_MAX:

  text <label>[TAB<value>]               a row that shows, no stop
  button <id> <label>                    a row that acts
  toggle <id> <label> <0|1>              a two-state row
  slider <id> <label> <min> <max> <v>    a value from min to max

An id is the program's own word (at most ID_MAX bytes); a label runs to
the numbers that end its line (at most LABEL_MAX characters). A press, a
toggle's change or a slider's step posts the item's process the system's
message STATUS, [item, id, value] (a button's value 1) -- a Python section
hears it as `press` -- and the row keeps the value it moved to until the
program describes the panel again. An empty description is no panel: the
item opens its app.
"""

try:
    import moy_log as _L
except ImportError:
    _L = None
import moy_evq as _E

ON, PAUSED, ERROR = 0, 1, 2      # moy_status.h's MOY_STATUS_*
STATES = (ON, PAUSED, ERROR)
CAP = 4                         # MOY_STATUS_CAP
SHELL = 1

STATUS = "moybyte.status"       # the message a panel's press posts its process
TEXT, BUTTON, TOGGLE, SLIDER = 0, 1, 2, 3
_KINDS = ("text", "button", "toggle", "slider")
_NUMS = (0, 0, 1, 3)            # the numbers that end a kind's line
ROWS_MAX = 8
ID_MAX = 16
LABEL_MAX = 40
SECTION_H_MAX = 160             # a page section's slot, at most, at font scale 1
ICON_MAX = 24                   # MOY_STATUS_ICON


class Item:
    """One status item: its process, icon, section, order and state."""

    def __init__(self, owner, k):
        self._owner = owner
        self.k = k
        self.pid = 0
        self.icon = None
        self.section = None
        self.order = 0
        self.age = 0
        self.state = ON
        self.visible = False
        self.app = ""               # the process's title, its caption

    def show(self, state=ON):
        if self.pid == 0:
            return
        _E.status_show(0, self.k + 1, state if state in STATES else ON)
        self._owner.sync()

    def changed(self):
        if self.pid:
            self._owner.describe(self)
            self._owner._moved(False)

    def remove(self):
        if self.pid:
            self._owner._free(self)


def parse(text):
    """Description `text` as rows (kind, id, label, value, v, lo, hi), or
    None where a line is not one of the four kinds' or there are more than
    ROWS_MAX."""
    out = []
    if not text:
        return out
    for line in text.split("\n"):
        if not line.strip():
            continue
        if len(out) == ROWS_MAX:
            return None
        head = line.split(" ", 1)
        kind = _KINDS.index(head[0]) if head[0] in _KINDS else -1
        if kind < 0 or len(head) < 2:
            return None
        rest = head[1]
        rid = ""
        if kind != TEXT:
            sp = rest.split(" ", 1)
            if len(sp) < 2 or not sp[0] or len(sp[0]) > ID_MAX:
                return None
            rid, rest = sp[0], sp[1]
        nums = []
        n = _NUMS[kind]
        if n:
            sp = rest.rsplit(" ", n)
            if len(sp) != n + 1:
                return None
            try:
                nums = [int(t) for t in sp[1:]]
            except ValueError:
                return None
            rest = sp[0]
        value = ""
        if kind == TEXT and "\t" in rest:
            rest, value = rest.split("\t", 1)
            value = value.strip()[:LABEL_MAX]
        label = rest.strip()[:LABEL_MAX]
        if not label:
            return None
        v, lo, hi = 0, 0, 0
        if kind == BUTTON:
            v = 1
        elif kind == TOGGLE:
            if nums[0] not in (0, 1):
                return None
            v = nums[0]
        elif kind == SLIDER:
            lo, hi, v = nums
            if lo >= hi:
                return None
            v = lo if v < lo else hi if v > hi else v
        out.append((kind, rid, label, value, v, lo, hi))
    return out


class Panel:
    """An item's rows, as its program described them (`cc_ui` draws them).
    One a slot, its rows' records preallocated: a draw allocates nothing, a
    press its message or its section's `press`."""

    def __init__(self, owner, k):
        self._owner = owner
        self.k = k
        self.n = 0
        self.kind = [TEXT] * ROWS_MAX
        self.rid = [""] * ROWS_MAX
        self.label = [""] * ROWS_MAX
        self.value = [""] * ROWS_MAX
        self.v = [0] * ROWS_MAX
        self.lo = [0] * ROWS_MAX
        self.hi = [0] * ROWS_MAX
        # each row's options: an id no other section's row shares

    def set(self, rows):
        n = len(rows)
        for r in range(n):
            (self.kind[r], self.rid[r], self.label[r], self.value[r], self.v[r],
             self.lo[r], self.hi[r]) = rows[r]
        for r in range(n, ROWS_MAX):
            self.rid[r] = self.label[r] = self.value[r] = ""
        self.n = n

    def _press(self, r, v):
        """Row `r` moved to `v`: the item's process hears it, a Python
        section as its `press`, run as the process."""
        self.v[r] = v
        o = self._owner
        it = o.slots[self.k]
        if not it.pid:
            return
        sec = it.section
        if sec is not self:
            o.run_as(it, sec.press, self.rid[r], v)
            return
        if o.post is not None:
            o.post(it.pid, STATUS, (self.k + 1, self.rid[r], v))


class Items:
    """The bar's status items: CAP records over the kernel's slots, the ones
    shown in order."""

    def __init__(self):
        self.slots = [Item(self, k) for k in range(CAP)]
        self.panels = [Panel(self, k) for k in range(CAP)]
        self._section = [None] * CAP    # a Python item's section, by slot
        # fn(pid, name, args) the moybyte module sets: a message posted to a
        # process from the system (moybyte.WAKES.post)
        self.post = None
        self._shown = []            # the visible items, by order then age
        self._gen = 0               # moves with anything an item shows
        self._layout_gen = 0        # ...and with how many are shown
        self._seen = -1             # the table's generation last read
        # fn(item) the console sets: an item's menu closes with it
        self.closed = None
        # fn(pid) -> the process's title, the console's
        self.title_of = None

    @property
    def shown(self):
        self.sync()
        return self._shown

    @property
    def gen(self):
        self.sync()
        return self._gen

    @property
    def layout_gen(self):
        self.sync()
        return self._layout_gen

    def sync(self):
        """Each record read again from the kernel's slot where the table
        moved: an item freed there (its process's remove or end, from any
        task) closes its menu, one added there (a compiled program's) takes
        its slot's Panel."""
        g = _E.status_gen()
        if g == self._seen:
            return
        self._seen = g
        moved = count = False
        for it in self.slots:
            rec = _E.status_get(it.k + 1)
            if it.pid and (rec is None or rec[4] != it.age):
                cb = self.closed
                if cb is not None:
                    cb(it)
                count = count or it.visible
                moved = True
                it.pid = 0
                it.icon = None
                it.section = None
                it.visible = False
            if rec is None:
                continue
            pid, icon, state, order, age, shown, compiled = rec
            if it.pid == 0:
                it.pid, it.icon, it.order, it.age = pid, icon, order, age
                it.section = self.panels[it.k] if compiled else self._section[it.k]
                self.panels[it.k].set(())
                self.describe(it)
                t = self.title_of
                it.app = (t(pid) if t is not None else "") or ""
                it.state, it.visible = ON, False
                moved = True
            if it.state != state or it.visible != shown:
                count = count or it.visible != shown
                it.state, it.visible = state, shown
                moved = True
        if moved:
            self._moved(count)

    def add(self, pid, icon, section, order=0):
        h = _E.status_add(pid, icon or "", order, False)
        if h <= 0:
            return None
        self._section[h - 1] = section
        self.sync()
        self._section[h - 1] = None
        return self.slots[h - 1]

    def _order(self):
        out = self._shown
        del out[:]
        for it in self.slots:
            if it.pid and it.visible:
                j = len(out)
                while j > 0 and (out[j - 1].order, out[j - 1].age) > (it.order, it.age):
                    j -= 1
                out.insert(j, it)

    def _moved(self, count):
        self._gen = (self._gen + 1) & 0x3fffffff
        if count:
            self._order()
            self._layout_gen = (self._layout_gen + 1) & 0x3fffffff

    def _free(self, it):
        _E.status_remove(0, it.k + 1)
        self.sync()

    def sweep(self, pid):
        """Process `pid` ended: its items leave the bar."""
        _E.status_sweep(pid)
        self.sync()

    def count(self):
        return len(self.shown)

    def at(self, i):
        sh = self.shown
        return sh[i] if 0 <= i < len(sh) else None

    def bare(self, it):
        """Whether item `it` has no menu: no rows described and no page. Its
        tap opens its app."""
        return self.panels[it.k].n == 0 and self.page(it) is None

    def page(self, it):
        """Item `it`'s section page's build function, None for rows."""
        sec = it.section
        return getattr(sec, "page", None) if sec is not None and type(sec) is not Panel else None

    def height(self, it, desk):
        """Item `it`'s page section's slot height at font scale 1."""
        return min(SECTION_H_MAX, max(0, int(self.run_as(it, it.section.height, desk))))

    def rows(self, it):
        """How many rows item `it`'s card lists: a bare item's one, Open."""
        return self.panels[it.k].n or 1

    def run_as(self, it, fn, *a):
        """`fn(*a)` as item `it`'s process."""
        if _L is None:
            return fn(*a)
        was = _L.current()
        _L.current(it.pid)
        try:
            return fn(*a)
        finally:
            _L.current(was)

    def describe(self, it):
        """A Python item's rows read again from its section's `panel()`; a
        description that does not parse lists none."""
        sec = it.section
        if sec is None or type(sec) is Panel:
            return
        if getattr(sec, "page", None) is not None:
            self.panels[it.k].set(())
            return
        rows = parse(self.run_as(it, sec.panel) or "")
        self.panels[it.k].set(rows or ())

    # -- a compiled program's items (moy_app.c's status rows) ----------------

    def of(self, pid, h):
        """Process `pid`'s compiled item of handle `h`, or None."""
        if type(h) is not int or not 1 <= h <= CAP:
            return None
        self.sync()
        it = self.slots[h - 1]
        if it.pid != pid or it.section is not self.panels[h - 1]:
            return None
        return it

    def show_compiled(self, pid, icon, state, order):
        """A compiled program's item shown in `state`, no panel yet, as its
        status_show row makes one: its handle, 0 where the bar holds CAP
        already."""
        h = _E.status_add(pid, icon, order, True)
        if h <= 0:
            return 0
        _E.status_show(pid, h, state)
        self.sync()
        return h


ITEMS = Items()
