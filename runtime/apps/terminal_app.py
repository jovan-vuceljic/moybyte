"""The TERMINAL -- the C shell's screen face (docs/os_2026-11/system.md section 1).

The Terminal system app launches the Terminal's face, which is C
(`moy_sh.Face`: native/moy_sh/moy_sh_face.h): a session of native/moy_sh
whose output fills a cell grid, the prompt line under it, the history,
completion, the key rows and their input, drawn through the UI engine. The
kernel's recovery console opens the same face with no VM. This layer hands
it the frame: the host's context and canvas, the content rect under the
bar, and the frame's keys; the face answers what the host owes after it.
A console with no C shell shows one line, a `uitree` page (`none_page`).

THE CLIPBOARD. A mouse's drag over the log selects its cells (the face
draws the selection); Ctrl+Shift+C, or Ctrl+C while there is a selection,
puts its text on the console's clipboard (a browser page's follows it), and
Ctrl+C with none is the shell's interrupt. A paste (`paste`) types its text
whole, as a terminal sends it: a line break is Enter, and a line that waits
holds the rest until its run ends.

THE BOARD'S SHELL. On a page a board serves, the face is a face of the
board's shell (native/moy_sh/moy_sh_link.h), one at a time with SSH's
(native/moy_tty/moy_tty.h, ONE FACE AT A TIME): leaving the Terminal gives
it back (`close`), so the board's face ends and SSH gets in, and the next
open asks for a new one. A console's own session outlives its screen.
"""

import sys as _sys

import ui_draw as _ui_draw
import uitree as ui
import uitree_app
from layers import AppLayer
import layout_base as _lb
from moy_store_base import session_root as _session_root

try:
    import moy_sh as _sh
    _sh.Face
except (ImportError, AttributeError):   # a folder of that name on CPython's path
    try:                    # CPython: the ctypes binding (runtime/host/moy_sh.py)
        from runtime import moy_sh as _sh
    except ImportError:     # the desktop MicroPython: no C shell
        _sh = None

# The site's browser console: the shell itself runs in the page.
_BROWSER_SHELL = (_sh is not None and _sys.platform == "webassembly"
                  and not hasattr(_sh, "link_want"))
# A page a board serves: the face is the board's shell's.
_LINKED = _sh is not None and hasattr(_sh, "link_want")

_HIT, _KEYS = 1, 2                      # the face's input answer
_MODS_AT, _SHIFT = 16, 2                # a key event's modifiers (moy_input.h)
_CTRL_C = 3
_PASTE_FRAME = 2048                     # a paste's bytes one frame types at most
_AGAIN, _DAMAGE = 1, 2                  # its draw answer
_ROWS = (None, "tdeck", "pad", "touch")
_BAR = "\0".join(_ui_draw.BAR_KEYS).encode()
NONE = "No shell on this console."

ui.state()


def _plain(line):
    """A log line without its SGR escapes."""
    out = []
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if c == "\x1b" and i + 1 < n and line[i + 1] == "[":
            i += 2
            while i < n and not ("@" <= line[i] <= "~"):
                i += 1
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def none_page():
    with ui.page(""):
        ui.label(NONE, tone="dim", wrap="word")


class TerminalLayout:
    """The terminal's page: the content rect under the host's bar."""

    MIN_W = 200
    MIN_H = 120

    def __init__(self, w, h, fs=1, windowed=False, cs=None):
        self.w, self.h = int(w), int(h)
        self.fs = max(1, int(fs))
        self.cs = max(self.fs, int(cs)) if cs else self.fs
        self.desk = _lb.metric_class() == _lb.DESK
        self.windowed = bool(windowed)
        self.cx, self.cy, self.cw, self.ch = _lb.content_of(
            self.w, self.h, 0 if windowed else _lb.bar_rows(self.cs))


class TerminalAppLayer(AppLayer):
    """The Terminal: the C shell's screen face (see the section above)."""

    id = "terminal"
    domain = "system"
    TITLE = "Terminal"
    UI = True
    # Esc is a key the shell and its text apps read (vi leaves INSERT on
    # it): the Terminal is left by its window's X, the bar's back and the
    # system key, never by Esc.
    ESC_LEAVES = False

    def __init__(self, ctx, names):
        self.ctx = ctx
        self._surf = ctx.surface
        self._theme = ctx.theme
        self._damage = ctx.damage
        self._install = ctx.install
        self._ui = ctx.ui
        self._clip = ctx.clipboard
        self.face = None            # made at the first open
        self._anchor = None         # where a mouse's drag over the log began
        self._held = 0              # a key the clipboard took, still down
        self._paste = ""            # a paste's text not typed yet
        self._none = None           # the page a console with no shell shows
        sc = self._surf.canvas()
        self.layout = TerminalLayout(sc.w, sc.h, getattr(sc, "font_scale", 1),
                                     self._surf.windowed(), self._surf.chrome_scale())

    # -- the app protocol (docs/app_api_v1.md) ------------------------------------

    def open(self):
        f = self.ensure()
        if f is not None:
            f.open()
        self._ui.reset()
        self._damage.all()

    def relayout(self, w, h, fs, cs=None):
        self.layout = TerminalLayout(w, h, fs, self._surf.windowed(), cs)

    def close(self):
        """Leaving the Terminal: the board's shell given back where the
        face is its (THE BOARD'S SHELL above)."""
        if _LINKED:
            self.close_session()

    def close_session(self):
        """The session given back, its arena and grid with it: the next open
        makes a new one."""
        if self.face is not None:
            self.face.close_session()

    def ensure(self):
        """The face, made the first time it is needed: None where this
        console has no C shell. A host's session and the site's browser
        console (its shell runs in the page) name their files tree: the
        store's folder, /moy in the browser, whose `files` is home. On a
        board-served page the face is the board's shell's
        (native/moy_sh/moy_sh_link.h) and takes no tree."""
        if self.face is None and _sh is not None:
            try:
                if getattr(_sh, "HOST", False) or _BROWSER_SHELL:
                    self.face = _sh.Face(_session_root(self._install.root()))
                else:
                    self.face = _sh.Face()
            except OSError:
                self.face = None
        return self.face

    def row_kind(self):
        """Which key row the page draws: None (a desk, a keyboard), "tdeck",
        "pad" or "touch"."""
        return _ROWS[_sh.face_row(self.layout.desk)] if _sh is not None else None

    # -- input --------------------------------------------------------------------

    def typing(self):
        """The Terminal types, always."""
        return True

    def cancel(self):
        """The board's cancel key (the T-Deck's Mic) for the text app in
        front (`edit`, `top`, `python`): True when it took it; with none in
        front Mic stays the console's key."""
        f = self.face
        if f is not None and f.cancel(self.layout.desk):
            self._damage.all()
            return True
        return False

    def back(self):
        """B and the bar's back while a run is parked are the run's cancel,
        as Ctrl-C is (True: the Terminal stays); with none it is the
        console's back out of the Terminal."""
        f = self.face
        if f is not None and f.busy():
            f.interrupt()
            self._damage.all()
            return True
        return False

    def paste(self, text):
        """A paste: its text typed whole into the shell or the app in
        front, from this frame on (`_typing`). True: the Terminal took it."""
        f = self.face
        if f is None or not text:
            return f is not None
        self._paste += str(text).replace("\r\n", "\n").replace("\r", "\n")
        self._typing()
        return True

    def _typing(self):
        """A paste's next part typed: up to _PASTE_FRAME bytes, and none
        past a line break that started a run that waits."""
        f = self.face
        text = self._paste
        n = 0
        i = 0
        while i < len(text) and n < _PASTE_FRAME and not f.busy():
            c = ord(text[i])
            i += 1
            if c == 0x0A:
                f.key(0x0D)
            elif c == 0x09 or c >= 0x20:
                f.key(c)
            n += 1
        self._paste = text[i:]
        if i:
            self._damage.all()

    def copy(self):
        """The selection's text on the console's clipboard, the selection
        gone: whether there was one."""
        f = self.face
        sel = f.selection() if f is not None else None
        if sel is None:
            return False
        r0, c0, r1, c1 = sel
        lines = f.lines()
        out = []
        for r in range(r0, r1 + 1):
            t = _plain(lines[r]) if r < len(lines) else ""
            out.append(t[c0 if r == r0 else 0:c1 if r == r1 else len(t)].rstrip())
        if self._clip is not None:
            self._clip.put_text("\n".join(out))
        f.select(-1, 0, -1, 0)
        self._damage.all()
        return True

    def _copy_key(self, inp, k):
        """Ctrl+Shift+C, or Ctrl+C over a selection: the copy (True).
        The key held after it types nothing more."""
        if self._held:
            if k == self._held:
                return True
            self._held = 0
        if inp.typed != _CTRL_C:
            return False
        shift = ((getattr(inp, "key_event", 0) or 0) >> _MODS_AT) & _SHIFT
        if not (self.copy() or shift):
            return False
        self._held = k
        return True

    def handle_input(self, inp):
        f = self.face
        if f is None:
            return True
        k = getattr(inp, "last_key", 0) or 0
        if not isinstance(k, int):
            k = ord(k[0]) if k else 0
        if self._copy_key(inp, k):
            k = 0
        elif inp.typed == _CTRL_C:
            self._paste = ""
        if self._paste:
            self._typing()
        n = getattr(inp, "key_repeats", 0)
        r = f.input(self.layout.desk, k, n, inp.repeat_key if n else 0,
                    inp.steps("left"), inp.steps("right"), inp.steps("up"), inp.steps("down"))
        hit = r & _HIT
        if r & _KEYS and self._ui.keys(inp):
            hit = True
        if hit:
            self._damage.all()
        return True

    def handle_pointer(self, px, py, click):
        if self._select(px, py, click):
            return True
        if self._ui.point(px, py, click):
            self._damage.all()
        return True

    def _select(self, px, py, click):
        """A mouse's press on the log and its drag select cells (True: the
        pointer is the selection's); a press anywhere drops the one there."""
        f = self.face
        if f is None:
            return False
        if click:
            had = f.selection() is not None
            f.select(-1, 0, -1, 0)
            mouse = getattr(_ui_draw.POINTER[0], "hovers", False)  # a finger's drag scrolls
            at = _ui_draw.text_at(self._ui, "log", px, py) if mouse else None
            self._anchor = at
            if had:
                self._damage.all()
            return at is not None
        if self._anchor is None:
            return False
        if not getattr(self._surf.pointer(), "down", False):
            self._anchor = None
            return True
        at = _ui_draw.text_at(self._ui, "log", px, py)
        if at is not None:
            a = self._anchor
            was = f.selection()
            f.select(a[0], a[1], at[0], at[1])
            if f.selection() != was:
                self._damage.all()
        return True

    # -- the surface ----------------------------------------------------------------

    def draw(self, dt):
        cv = self._surf.canvas()
        lay = self.layout
        f = self.face
        self._ui.begin(cv, self._theme.colors(), (0, 0, cv.w, cv.h), lay.desk, lay.windowed,
                       f is None or f.elsewhere(lay.desk))
        if f is None:
            if self._none is None:
                self._none = uitree_app.hosted_page(none_page, self._ui, self._damage)
                self._none.open()
            self._none.paint(dt, cv, self._theme.colors(), (lay.cx, lay.cy, lay.cw, lay.ch), lay.desk)
            return
        t = _ui_draw.UI_TARGET
        r = f.draw(t[0], t[1], t[2], lay.cx, lay.cy, lay.cw, lay.ch, lay.fs, lay.desk,
                   _BAR if _ui_draw.on_bar() else None)
        if r & _AGAIN:
            self._ui.again()
        if r & _DAMAGE:
            self._damage.all()


