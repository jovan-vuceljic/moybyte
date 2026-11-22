"""The TEXT CONSOLE -- a script's screen (step 6 of docs/theme_and_shell_2026-11.md §10).

A script is a cart with no folder, and this is the surface it runs on: a
bounded scrollback that `print()` appends to, and a prompt line under it. Both
are one `uitree` page (`console_page`): the scrollback a lines view, the prompt
a field in the page's foot, whose Enter enters the line.

The shell owns the pixels, not the cart. A script never gets a `_draw`: the
Player takes `TextConsole.draw` as the run's draw hook (`Workstation.run_script`),
so a script cannot paint over the prompt it is reading from, and the surface
composites through the ordinary running-cart path every other cart uses.

## How `input()` works, and why

A script is `type: "script"`, which is tool-shaped: ONE tick per loop frame,
unpaced. The loop cannot block, so `input()` cannot either. It is a POLL:

    name = input("what is your name? ")   # None until a line is entered

The prompt is shown once and stays on the prompt line; every tick until the
person presses enter, `input()` answers None; the tick it lands, it answers the
line -- once -- and the console echoes `prompt + line` into the scrollback. A
script that only prints needs no `_update` at all (its body runs once, like any
cart's); a script that reads writes an `_update` and checks for None.

`_update` MAY be a generator function, which is the linear way to write the
same thing: the driver `next()`s it once per frame, so a bare `yield` means
"wait a frame", and the script ENDS when the generator does.

    def _update(dt):
        name = None
        while name is None:
            name = input("what is your name? ")
            yield
        print("hello " + name)

## The scrollback is a RING

`LINES` rows, preallocated, wrapped to the view's columns AS THEY ARE WRITTEN.
Nothing grows: the oldest row is overwritten, and a resize does not reflow rows
that are already in the ring (a terminal does not either) -- new writes take
the new width.

The log is the page's `ui.text_view` (docs/history/scroll_and_text_2026-10.md §5): a
drag scrolls it by pixels and its release coasts, and while it shows its foot
new rows glide it down to the new foot; scrolled up, it stays where it is.

`on_line` is a REPL's seam: set it and every entered line goes to that
handler instead of an `input()` call.

## The terminal

The Terminal app (`terminal_app.py`) is the C shell's screen face. It keeps
none of this ring: its scrollback is the shell's cell grid in C
(`moy_sh.Screen`), drawn by the C face through the same text view.
"""

import os_log as _os_log
import ui_draw as _ui_draw
import uitree as ui
import uitree_app
import layout_base as _lb

# Where an echoed line's answer starts in its row: what was typed draws in
# `value` (`draw`), and the row as read has no mark.
_ANSWER = "\x01"
_ENDED = "The script ended."
LINE_MAX = 200          # the prompt line's characters

s = ui.state(log=ui.model(key="n", n=0, line=""), ended=False, ask="", line="")


def sync(con):
    """The page's states from the console: the log's rows, the prompt a
    line is read with, and whether the script ended. A frame between two
    `input()` calls, reading nothing, changes none of them."""
    if con._shown_gen != con._gen:
        s.log = con._rows()
    reading = con.reading()
    ended = con.ended and not reading
    if ended != s.ended:
        s.ended = ended
        ui.focus("again" if ended else "line")
    if reading and con._prompt != s.ask:
        s.ask = con._prompt


def send():
    """Enter in the prompt: the line entered."""
    line = s.line
    s.line = ""
    uitree_app.env().submit(line)


def again():
    uitree_app.env()._restart()


def opened():
    s.ended, s.ask, s.line = False, "", ""
    ui.focus("line")


ui.hook("opened", opened)
ui.hook("sync", sync, takes="arg")
ui.action("send", "Send", send)
ui.action("again", "Run again", again)


def console_page():
    with ui.page(""):
        ui.text_view("log", follow=True, syntax="sgr")
        with ui.foot():
            ui.field("{ask}", "line", max=LINE_MAX, on="send", shown="!ended")
            ui.label(_ENDED, tone="dim", shown="ended")
            ui.button("again", shown="ended")


# Lua has no `input` of its own and libmoy owns `print` (the DRAW verb), so a
# registered Python `print` would never reach the cart -- lua_ext.LIBMOY_VERBS
# denies it by name, correctly. The console's two verbs therefore register
# under reserved names and this prelude binds them over the top, in the same
# window PRELUDE_HANDLES uses: after registration, before the cart loads. Both
# Lua glue (device/moycore_glue.py, the host's too) execs whatever
# `_moy_prelude` the namespace carries.
LUA_PRELUDE = """
do
  local say, ask = __moy_say, __moy_ask
  print = function(...)
    local n = select("#", ...)
    local parts = {}
    for i = 1, n do parts[i] = tostring((select(i, ...))) end
    say(table.concat(parts, " "))
  end
  input = function(prompt) return ask(prompt) end
end
"""

# A capability a script's manifest does not name has no name in its namespace
# (runtime/shell/system_api.py). That is a NameError inside the cart, which is the
# right mechanism and the wrong words for a kid, so these names get a sentence
# instead when one escapes into the console.
GATED = {
    "wifi": "the internet",
    "net": "playing with a friend",
    "carts": "making carts",
    "artwork": "the drawing store",
    "shell": "the console itself",
}


class TextConsole:
    """The script surface: a scrollback ring, a prompt line, and the two verbs
    a script talks to them with."""

    LINES = 200          # scrollback capacity, in WRAPPED rows
    MIN_COLS = 8
    NEEDS = ("damage", "theme", "surface")

    def __init__(self, ctx, names, inp, served, restart):
        """`ctx` its AppContext; `inp()` the console's input state; `served()`
        the run the shell serves (procs.Run: the canvas the script draws on
        and its Player); `restart()` runs the script that ended again."""
        self._damage = ctx.damage
        self._theme = ctx.theme
        self._surface = ctx.surface
        self._inp = inp
        self._served = served
        self._restart = restart
        self.NAMES = names
        self.cols = 38
        self._cap = self.LINES
        self._buf = [""] * self._cap
        self._start = 0
        self._n = 0
        self._dropped = 0         # the rows the ring wrote over: its first row's running number
        self._open = False        # the newest row is unterminated (print(end=""))
        self._gen = 0             # moves with every write: the view's rows are made again
        self._shown = []          # ...the rows as the log's text view takes them
        self._shown_gen = -1
        self._armed = False       # a script is waiting on a line
        self._prompt = ""
        self._answer = None       # the entered line, until the script takes it
        self.on_line = None       # #115: a REPL takes every line instead
        self.title = ""
        self.ended = False        # the script's run is over (its prompt band says so)
        # the page's UI context: the log's text view (a drag scrolls it and
        # its release coasts, new rows glide it to its foot) and the hints
        self._host = _ui_draw.AppHost()
        self.page = uitree_app.hosted_page(console_page, self._host, self._damage, gen=True, env=self)
        self._seen = None         # (rows, reading, ended) the page was last given

    # -- the ring -------------------------------------------------------------

    def clear(self):
        for i in range(self._cap):
            self._buf[i] = ""
        self._start = 0
        self._n = 0
        self._dropped = 0
        self._open = False
        self._gen += 1

    def count(self):
        return self._n

    def row(self, i):
        """Row `i`, oldest first."""
        if i < 0 or i >= self._n:
            return ""
        return self._buf[(self._start + i) % self._cap].replace(_ANSWER, "")

    def text(self):
        """The whole scrollback as one string -- what a test reads."""
        return "\n".join(self.row(i) for i in range(self._n))

    def _push(self, row):
        self._gen += 1
        if self._n < self._cap:
            self._buf[(self._start + self._n) % self._cap] = row
            self._n += 1
            return
        self._buf[self._start] = row
        self._start = (self._start + 1) % self._cap
        self._dropped += 1

    def _last(self):
        return self._buf[(self._start + self._n - 1) % self._cap]

    def _set_last(self, row):
        self._gen += 1
        self._buf[(self._start + self._n - 1) % self._cap] = row

    def _rows(self):
        """The log as its text view takes it, made again after a write: an
        echoed line's prompt in the dim ink and its answer in `value` (SGR
        2 and 36, `ui.text_view`'s), each row keyed by its running number."""
        if self._shown_gen != self._gen:
            out = []
            for i in range(self._n):
                raw = self._buf[(self._start + i) % self._cap]
                cut = raw.find(_ANSWER)
                if cut >= 0:
                    raw = "\x1b[2m" + raw[:cut] + "\x1b[0;36m" + raw[cut + 1:] + "\x1b[0m"
                out.append({"n": self._dropped + i, "line": raw})
            self._shown = out
            self._shown_gen = self._gen
        return self._shown

    def _append(self, seg):
        """Add `seg` to the open row, opening rows as it fills them."""
        while seg:
            if not self._open or self._n == 0:
                self._push("")
                self._open = True
            room = self.cols - len(self._last())
            if room <= 0:
                self._open = False        # the row is full -> wrap
                continue
            self._set_last(self._last() + seg[:room])
            seg = seg[room:]

    def write(self, text):
        """Append raw text (newlines break rows, everything wraps at `cols`)."""
        text = str(text)
        i = 0
        n = len(text)
        while i <= n:
            j = text.find("\n", i)
            self._append(text[i:] if j < 0 else text[i:j])
            if j < 0:
                break
            if not self._open:
                self._push("")            # a bare newline is a blank row
            self._open = False
            i = j + 1
        self._dirty()

    # -- the prompt -----------------------------------------------------------

    def reading(self):
        """True when the console is taking a line -- a script inside `input()`,
        or a REPL with an `on_line` handler."""
        return self._armed or self.on_line is not None

    def ask(self, prompt=""):
        """`input()`: the line, or None until one is entered."""
        if self._answer is not None:
            line = self._answer
            self._answer = None
            self._armed = False
            self._prompt = ""
            return line
        if not self._armed:
            self._armed = True
            self._prompt = str(prompt)
            self._dirty()
        return None

    def submit(self, line):
        """Enter: echo `line`, then hand it to `on_line` or to `input()`."""
        self.write(self._prompt + _ANSWER + line + "\n")
        if self.on_line is not None:
            self._armed = False
            self._prompt = ""
            self.on_line(line)
        elif self._armed:
            self._answer = line
        return line

    def line(self):
        """The prompt line as typed so far."""
        return self.page.s._v["line"]

    # -- the run --------------------------------------------------------------

    def start(self, title, lang="python"):
        """A fresh run: empty scrollback, no pending line, no REPL handler."""
        self.clear()
        self._armed = False
        self._prompt = ""
        self._answer = None
        self.on_line = None
        self.title = str(title)
        self._host.reset()                # the log's view starts afresh, at its foot
        self.page.open()
        self._seen = None
        self.ended = False

    def api(self):
        """The names a cart with the `console` permission gets. `print` SHADOWS
        the draw verb of the same name: a script's screen is this, not a
        raster, and both tiers say so with the same word. What a script
        prints is also its process's record in the OS log, and on serial."""
        def _print(*args, **kw):
            sep = kw.get("sep", " ")
            end = kw.get("end", "\n")
            self._say(sep.join(str(a) for a in args) + end)

        def _input(prompt=""):
            return self.ask(prompt)

        return {"print": _print, "input": _input,
                # Lua: registered under reserved names, bound by the prelude.
                "__moy_say": lambda s="": self._say(str(s) + "\n"),
                "__moy_ask": lambda prompt="": self.ask(prompt or ""),
                "_moy_prelude": LUA_PRELUDE}

    def _say(self, text):
        self.write(text)
        _os_log.printed(text)

    def driver(self, update):
        """Wrap the script's `_update` as the shell-owned tick.

        Every frame it pumps the keyboard and the pointer FIRST -- a script that
        never ticks (a body that only printed) still gets a live prompt -- then
        runs the script. A generator `_update` is stepped once per frame and
        ends the run when it finishes; a raise is printed into the console
        rather than thrown at the Player, because the console IS this run's
        error surface (there is no folder to open in the Editor)."""
        state = [update, None]        # [callable, live generator]

        def _step(gen):
            try:
                next(gen)
            except StopIteration:
                state[0] = state[1] = None
            except Exception as exc:  # noqa: BLE001 -- into the console
                state[0] = state[1] = None
                self.crash(exc)

        def _tick(dt):
            self.pump()
            fn, gen = state
            if gen is not None:
                _step(gen)
                return
            if fn is None:
                if not self.ended and not self.reading():
                    self.ended = True     # a body that only printed, or a run that stopped
                    self._dirty()
                return
            try:
                got = fn(dt)
            except Exception as exc:  # noqa: BLE001 -- into the console
                state[0] = None
                self.crash(exc)
                return
            if hasattr(got, "__next__"):
                # A GENERATOR `_update`. Calling it ran none of its body, so
                # its first step belongs to THIS frame -- otherwise a script
                # whose first line is an `input()` shows no prompt until the
                # frame after the one that started it.
                state[0] = None
                state[1] = got
                _step(got)
        return _tick

    def crash(self, exc):
        """A script's failure, in the console. `exc` may be an exception or the
        text the Player already turned one into."""
        text = exc if isinstance(exc, str) else _err_text(exc)
        if not isinstance(exc, str):
            _os_log.crashed(None, exc, text)
        name = _missing_name(text)
        self.write("\n" + text + "\n")
        if name in GATED:
            self.write("a script can't use %s (%s)\n" % (name, GATED[name]))
        self._dirty()

    # -- input pump (the tick's, not a Layer's) -------------------------------

    def pump(self):
        """Take this frame's keys and pointer. Called from the tick the
        Player runs, because that is what a script IS -- the console is not a
        content Layer of its own, it is the running cart's surface."""
        inp = self._inp()
        self._sync()
        self.page.keys(inp)
        gp = getattr(inp, "game_pointer", None)
        if gp is not None:
            self._pointer(gp[0], gp[1], bool(gp[2]), bool(gp[3]) if len(gp) > 3 else False)
        if not self._host.still():
            self._dirty()                       # the log coasts or glides

    def _pointer(self, px, py, click, down):
        if self._host.point(px, py, click, down):   # a drag scrolls the log, a tap takes a stop
            self._dirty()

    # -- the surface ----------------------------------------------------------

    def _dirty(self):
        self._damage.all()

    def _sync(self):
        """The page told what moved since it was last told: the rows, the
        prompt, the run's end."""
        seen = (self._gen, self.reading(), self.ended, self._prompt)
        if seen != self._seen:
            self._seen = seen
            pg = self.page
            pg.run(sync, self, action="sync")
            ui.commit(pg)

    def draw(self):
        """The run's draw hook: the page, on whatever surface the Player
        bound for this script (docs/history/look_2026-10.md step 33), in the
        content rect under the host's strip, the rows wrapped at the view's
        columns. Takes no arguments -- it is called exactly where a cart's
        `_draw` would be. The shell's pixels, not the script's: its fonts
        and its colours, whatever the app-cart boundary is at."""
        cv = self._served().canvas
        fs = max(1, int(getattr(cv, "font_scale", 1) or 1))
        rect = self._surface.content_rect()
        self.cols = max(self.MIN_COLS, (rect[2] - 16 * fs) // (_ui_draw.font("mono")[1] * fs))
        moved = self._shown_gen != self._gen
        self._sync()
        if moved:
            # rows came: a log at its foot moves to the new foot, the frame's shift
            _ui_draw.text_aim(self._host, "log", -1, self._n)
        # On a desk the run's canvas is its window's own, which the run alone
        # draws (`AppFace.holds`): it holds the page as the last frame left it.
        pl = self._served().player
        own = pl is not None and pl.face.holds(cv)
        was = _ui_draw.cart_text(False)
        if own:
            _ui_draw.window_frame(2)
        try:
            th = self._theme.colors()
            desk = _lb.metric_class() == _lb.DESK
            self._host.begin(cv, th, rect, desk)
            self.page.paint(0, cv, th, rect, desk)
        finally:
            if own:
                _ui_draw.window_frame(0)
            _ui_draw.cart_text(was)


def _err_text(exc):
    """An exception as one line, never raising itself (the Player's rule: a
    cart whose `__str__` raises must not become a silent hang)."""
    try:
        return "%s: %s" % (type(exc).__name__, exc)
    except Exception:  # noqa: BLE001
        return "error"


def _missing_name(text):
    """The identifier a NameError names, or "" -- both tiers spell it in
    quotes ("name 'wifi' isn't defined")."""
    a = text.find("'")
    b = text.find("'", a + 1)
    return text[a + 1:b] if 0 <= a < b else ""

