"""The browser page around the console: `Workstation.page`, None on a board.

The page keeps no bar of its own (owner, 2026-11-25): what its top bar did
is the console's, in the console's rows -- Full screen where the browser
has it, Add to Home Screen and its card where it has none or is an
iPhone's or an iPad's (whose element full screen keeps the browser's strip),
and Add a file in
the system menu, Download in a cart's menu, Play on the console in a cart's
menu where a console serves the page,
where the carts are kept in Settings -- and the console says what happened
in its own notices and cards. The browser half of each runs in the page.

A console row asks (`toggle_fullscreen`, `add_files`, `save_cart`,
`play_on_console`); the frame carries the asks to the page (`drain`,
web_boot.step's `ask`), and the page does them. A browser grants full
screen and a file chooser only inside a user's gesture, so the page does an
ask at once while the gesture that chose the row is still active, else arms
it and does it in its next pointerup or keydown (page_core.html, THE ASKS).

What the page answers comes back as one event, `page` (web_input), heard
here: whether it is full screen, the sentence on where it keeps the carts,
and anything it has to say (an import's outcome, a lost link)."""


class PageLink:
    """The page's asks and its word back. `served`: a console serves this
    page, so a cart open here can play on its glass. `play(folder)` plays a
    cart (web_boot.open_cart), for an import's card."""

    def __init__(self, served=False, play=None):
        self.served = bool(served)
        self._play = play
        self.fullscreen = False     # the page is full screen, by its word
        self.can_fullscreen = False  # ...and its browser has full screen
        self.app = False            # it runs as a home-screen app
        self.ios = False            # ...on an iPhone or an iPad
        self.host = ""              # the host it was opened at
        self.kept = ""              # where the page keeps the carts, its sentence
        self._asks = []

    def _ask(self, do, **kw):
        kw["do"] = do
        self._asks.append(kw)

    def toggle_fullscreen(self):
        """Full screen, or out of it."""
        self._ask("fullscreen", on=not self.fullscreen)

    def add_files(self):
        """The browser's file chooser, for carts, PICO-8 carts and songs:
        what is chosen imports as a drop on the page does."""
        self._ask("open")

    def save_cart(self, cart):
        """`cart` (a cart dict) downloaded as a .moy zip. False where it has
        no folder."""
        folder = folder_of(cart)
        if folder is not None:
            self._ask("save", cart=folder)
        return folder is not None

    def play_on_console(self, cart):
        """`cart` (a cart dict) played on the glass of the console serving
        the page."""
        folder = folder_of(cart)
        if folder is not None:
            self._ask("pod", cart=folder)

    def home_screen(self, ws):
        """The card that says how to get the true full screen: the page saved
        to the Home Screen, which opens with no browser bars (an iPhone's
        element full screen keeps the browser's strip and Close). A board's page opened at a number is
        saved from the board's .local name, which stays; the app keeps its
        own storage, so it pairs with the board once."""
        rows = [("True full screen, no browser bars:", "plain"),
                ("1. Tap Share in Safari's bar.", "plain"),
                ("2. Choose Add to Home Screen.", "plain"),
                ("3. Open Moybyte from there.", "plain")]
        if self.served:
            if _is_number(self.host):
                rows.append(("Open the board by its .local", "dim"))
                rows.append(("name first: %s can change." % self.host, "dim"))
            rows.append(("The app pairs with it once.", "dim"))
        ws.confirm.tell("Full screen", tuple(rows))

    def drain(self):
        """The asks since the last frame, for the page, or None."""
        if not self._asks:
            return None
        asks, self._asks = self._asks, []
        return asks

    def heard(self, ws, ev):
        """The page's `page` event: `fs` whether it is full screen, `canfs`
        whether its browser has full screen (an iPhone's Safari's has
        none), `app` whether it runs as a home-screen app, `ios` whether on
        an iPhone or an iPad, `host` the host it was opened at, `kept`
        where it keeps the carts, `say` a notice ([title, sub, kind, ms]:
        ms how long it stays up, the notice's own time where absent; 0 takes
        the notice titled `title` down, where it is the one up: a
        conversion's progress, said each second, ends so), `tell`
        a card ([title, [line, tone], ...]), whose Open goes to `go` where it
        names an address (where a Zero that moved went), and `offer` one whose
        Open plays a cart ([title, folder, [line, tone], ...]): an import's
        report."""
        if "fs" in ev:
            self.fullscreen = bool(ev["fs"])
        if "canfs" in ev:
            self.can_fullscreen = bool(ev["canfs"])
        if "app" in ev:
            self.app = bool(ev["app"])
        if "ios" in ev:
            self.ios = bool(ev["ios"])
        if "host" in ev:
            self.host = str(ev["host"] or "")
        if "kept" in ev:
            self.kept = str(ev["kept"] or "")
        say = ev.get("say")
        if say:
            title = str(say[0])
            sub = str(say[1]) if len(say) > 1 else ""
            kind = str(say[2]) if len(say) > 2 else "ok"
            ms = int(say[3]) if len(say) > 3 else None
            if ms == 0:
                ws.notices.withdraw(title)
            elif ms:
                ws.notices.notice(title, sub, kind, ms)
            else:
                ws.notices.notice(title, sub, kind)
        tell = ev.get("tell")
        go = str(ev.get("go") or "")
        if tell and go:
            rows = tuple((str(r[0]), str(r[1]) if len(r) > 1 else "plain") for r in tell[1:])
            ws.confirm.offer(str(tell[0]), rows, lambda: self._ask("go", url=go))
        elif tell:
            rows = tuple((str(r[0]), str(r[1]) if len(r) > 1 else "plain") for r in tell[1:])
            ws.confirm.tell(str(tell[0]), rows)
        offer = ev.get("offer")
        if offer and self._play is not None:
            folder = str(offer[1])
            rows = tuple((str(r[0]), str(r[1]) if len(r) > 1 else "plain") for r in offer[2:])
            ws.confirm.offer(str(offer[0]), rows, lambda: self._play(folder))
        ws.mark_dirty()


def _is_number(host):
    """Whether `host` is an address by number (IPv4 or IPv6), not a name."""
    if ":" in host:
        return True
    parts = host.split(".")
    return len(parts) == 4 and all(p.isdigit() for p in parts)


def folder_of(cart):
    """A cart dict's folder name (its path's last part), or None."""
    path = (cart or {}).get("path")
    if not path:
        return None
    return str(path).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
