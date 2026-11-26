"""Settings' Works offline on a page a board serves whose console is online
(board.toml's `[web] console`; the probe of its /official named "offline",
web_boot.official_enable): the browser console's own copy on that board,
its owner's choice (owner, 2026-11-26), which device/zero_host.py's
Offline makes and runtime/carts/web_addon.py's OfficialCarts carries.

The row's word is where the choice stands, read from the board's /official
(its "offline": on, installed, the bytes the copy needs and the store has
free, the install's progress): "Install (≈N MB)" while it is off, the
install's share while it runs, "Remove" once the board serves its own copy.
A press asks the board (`{"action": "offline", "on": ...}`); one the board
refuses (no room) shows its reason, with the sizes, until the next press.
The board is read when Settings first shows the row, then every POLL_MS
while its install or removal runs."""

from carts_link import _read_answer
from ticks import _ticks_ms, _ticks_diff

POLL_MS = 1000


def _mb(n):
    return "%.1f MB" % (n / 1e6)


class ConsoleOffline:
    """`ws.console_offline`: the row's `word()` and `press()` over the
    board's /official (`board`, carts_link.BoardCarts)."""

    def __init__(self, board, ws=None):
        self.board = board
        self.ws = ws
        self.state = None           # the board's "offline" document, once read
        self.said = None            # a refusal's reason, until the next press
        self._answer = None
        self._at = None
        self._pressed = False       # a press before the board's answer: acted on at the answer

    def _ask(self, doc=None):
        self._answer = self.board.ask(doc)
        self._at = _ticks_ms()

    def poll(self):
        """One look at the request in hand: its answer taken when it ended,
        the next GET asked when one is due."""
        a = self._answer
        if a is not None:
            if not a.ready(1) or not a.ended and a.error is None:
                return
            self._answer = None
            status, doc = _read_answer(a)
            if doc is not None and isinstance(doc.get("offline"), dict):
                self.state = doc["offline"]
            if status == 409 and doc is not None and doc.get("message"):
                self.said = str(doc["message"])
            if self._pressed and self.state is not None:
                self._pressed = False
                self.press()
            return
        st = self.state
        if st is None and self._at is None:
            self._ask()
        elif (st is None or st.get("busy")) and _ticks_diff(_ticks_ms(), self._at) >= POLL_MS:
            self._ask()

    def word(self):
        self.poll()
        if self.said:
            return self.said
        st = self.state
        if st is None:
            return "..."
        if st.get("busy"):
            prog = st.get("progress")
            if st.get("on") and prog and prog[1]:
                return "Installing %d%%" % (100 * prog[0] // prog[1])
            return "Installing" if st.get("on") else "Removing"
        if st.get("on") and st.get("installed"):
            return "Remove"
        if st.get("on"):
            return st.get("error") or "Installing"
        need = st.get("needs")
        return "Install (%s)" % ("≈" + _mb(need) if need else "?")

    def press(self):
        """Install where it is off, remove where it is on: at once, or once
        the board's answer is read where it has not been yet; nothing while
        another request is in flight."""
        st = self.state
        if st is None:
            self._pressed = True
            return True
        if self._answer is not None:
            return False
        self.said = None
        self._ask({"action": "offline", "on": not st.get("on")})
        self.state = dict(st, busy=True, on=not st.get("on"))
        return True

