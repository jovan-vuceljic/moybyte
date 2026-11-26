"""The browser's half of a Zero's Wi-Fi: `ws.wifi` on a page a Zero serves,
over the board's sealed `/wifi` (device/zero_wifi.py has the document and
the switch).

The console's Wi-Fi panel, the bar's glyph and the Settings row read this
station as they read a board's own (`device_wifi.DeviceWifi`): `status()`,
`known()`, a scan asked and polled (`scan_poll`), a join asked and polled
(`join`/`joined`), `forget`. What is the page's alone:

  * a join MOVES the board, and the page reaches it over the network it
    leaves, so Settings asks first (`switch_says`, the card's words) and can
    save the network instead (`save`), which moves nothing;
  * the verdict of a move comes back only if the board does: it saves the
    new network only once joined, and a failed one takes it back to the old
    network, where the page finds it again and reads `last`. A move that
    worked leaves the page on the old network with no board: the worker
    waits out the board's windows and then says where it went (worker.js,
    THE MOVE), never as a loss.

SHAPE: update_link's. Requests QUEUE here and the worker does the I/O, one
in flight, and the answer is the board's document; the worker polls it only
while something waits on it (a scan, a move, the panel open) and seldom
otherwise, so the bar stays true.

A cart is never handed this station (`CARTS`): a cart's `wifi.connect`
would move the board from under the page with nobody asked.
"""

import json

from ticks import _ticks_ms, _ticks_diff

CARTS = False
SCAN_GIVE_UP_MS = 20000     # a scan the board never reported ends empty
HELD_MS = 2000              # the panel shows: the board asked this often
IDLE_MS = 30000             # ...and otherwise, for the bar
MOVE_MARGIN_MS = 6000       # past the board's two windows: the move worked


class BoardWifi:
    """`ws.wifi` over the serving Zero's /wifi. `doc` is the probe's answer."""

    CARTS = CARTS

    def __init__(self, doc, log=print):
        self._log = log
        self._doc = {}
        self._absorb(doc if isinstance(doc, dict) else {})
        self._queue = []           # bodies the worker POSTs, in order
        self._sent = None          # the body in flight
        self._scan_from = None     # the scan_id a running scan's ask saw
        self._scan_at = 0
        self._join = None          # the join waiting: [ssid, id or None, verdict]
        self._joined = None        # the last join's verdict
        self._says = None          # ...and the card it left, or None
        self._held = False
        self._gone = False         # the board moved where this page cannot reach it
        self._polled = _ticks_ms()

    # -- the station, as the console reads it -------------------------------

    def status(self):
        d = self._doc
        up = bool(d.get("connected"))
        return (up, d.get("ssid") if up else None, d.get("ip") if up else None)

    def known(self):
        return list(self._doc.get("saved") or ())

    def scan(self):
        return [tuple(n) for n in self._doc.get("nets") or ()]

    def scan_poll(self):
        """None while the board scans (the first call asks it), then its
        networks as (ssid, signal %, locked)."""
        if self._scan_from is None:
            self._scan_from = int(self._doc.get("scan_id") or 0)
            self._scan_at = _ticks_ms()
            self._ask({"action": "scan"})
            return None
        d = self._doc
        if int(d.get("scan_id") or 0) > self._scan_from and not d.get("scanning"):
            self._scan_from = None
            return self.scan()
        if _ticks_diff(_ticks_ms(), self._scan_at) >= SCAN_GIVE_UP_MS:
            self._scan_from = None
            return []
        return None

    def switch_says(self, ssid):
        """The question before a join that moves the board, as (title, rows),
        or None where `ssid` is the network it is on."""
        d = self._doc
        here = d.get("ssid") if d.get("connected") else None
        if here == ssid:
            return None
        host = d.get("host") or "the console"
        rows = []
        if here:
            rows.append(("This page reaches the console over %s." % here, "plain"))
        rows.append(("If it joins %s, this page loses it: open %s on %s."
                     % (ssid, host, ssid), "plain"))
        if here:
            rows.append(("If it can't, it comes back to %s and says so here." % here, "dim"))
        return ("Move the console to %s?" % ssid, tuple(rows))

    def join(self, ssid, password=""):
        """Ask the board to move to `ssid`; None until it says (`joined`).
        An empty password is the saved one's."""
        body = {"action": "join", "ssid": str(ssid)}
        if password:
            body["password"] = str(password)
        self._join = [str(ssid), None, None]
        self._says = None
        self._ask(body)
        return None

    def joined(self):
        """None while the move runs, then whether the board joined."""
        j = self._join
        if j is None:
            return self._joined
        if j[2] is None:
            return None
        self._join = None
        self._joined = j[2]
        return j[2]

    def join_says(self):
        """The card the last join left -- (title, rows) -- or None."""
        return self._says

    def save(self, ssid, password=""):
        """Save `ssid` on the board without moving it."""
        ssid = str(ssid)
        self._ask({"action": "add", "ssid": ssid, "password": str(password or "")})
        saved = self._doc.setdefault("saved", [])
        if ssid not in saved:
            saved.append(ssid)
        return True

    def forget(self, ssid):
        """Unsave `ssid` on the board. The board stays on it until it next
        starts: leaving it would leave this page."""
        ssid = str(ssid)
        self._ask({"action": "forget", "ssid": ssid})
        saved = self._doc.get("saved") or []
        if ssid in saved:
            saved.remove(ssid)
        return True

    def connect(self, ssid, password=""):
        """A cart's waited join: refused (this station is never a cart's)."""
        return False

    def moved(self, ssid):
        """The worker waited out a move and the board never answered again:
        it is on `ssid` now, where this page cannot reach it. The station
        says so where it named the network (the bar's popover, the Settings
        row, the panel), the move counts as joined, and nothing more is asked
        of a board that is gone."""
        self._doc = dict(self._doc, connected=True, ssid="moved to %s" % ssid, ip=None,
                         saved=[], nets=[])
        self._gone = True
        self._queue = []
        self._scan_from = None
        if self._join is not None and self._join[2] is None:
            self._join[2] = True
            self._says = None

    def radio_on(self):
        """The panel shows (its wifi lease): the board is asked often."""
        self._held = True
        return True

    def radio_off(self):
        self._held = False

    # -- the pump ------------------------------------------------------------

    def _ask(self, body):
        self._queue.append(json.dumps(body))

    def take_json(self):
        """The next request for the worker to POST, or ""."""
        if self._gone:
            self._queue = []
            return ""
        if self._sent is not None or not self._queue:
            return ""
        self._sent = self._queue.pop(0)
        return self._sent

    def wants_poll(self):
        """Whether the worker should GET the document now."""
        if self._sent is not None or self._gone:
            return False
        waited = _ticks_diff(_ticks_ms(), self._polled)
        if self._scan_from is not None or (self._join is not None and self._join[2] is None):
            want = True
        else:
            want = waited >= (HELD_MS if self._held else IDLE_MS)
        if want:
            self._polled = _ticks_ms()
        return want

    def ack(self, ok, text=""):
        """The board's answer to the request or poll in flight. Returns what
        the worker must know as JSON, or "": `move` when the board left to
        join another network (`ms` its windows, `host` where it will be
        found), `settled` when a move's verdict came back."""
        sent, self._sent = self._sent, None
        try:
            doc = json.loads(text) if text else None
        except ValueError:
            doc = None
        if not isinstance(doc, dict) or "connected" not in doc:
            doc = None
        if doc is not None:
            self._absorb(doc)
        j = self._join
        if j is None or j[2] is not None:
            return ""
        if sent is not None and '"join"' in sent:
            if doc is None or not ok:
                why = (doc or {}).get("message") or "the console did not answer"
                return self._verdict(False, ("Couldn't move the console", (
                    ("%s: %s." % (j[0], why), "plain"),)))
            if doc.get("message") == "already":
                return self._verdict(True, None)
            sw = doc.get("switch") or {}
            j[1] = sw.get("id")
            return json.dumps({"move": {
                "ssid": j[0], "host": doc.get("host") or "",
                "ms": int(doc.get("join_ms") or 0) + int(doc.get("back_ms") or 0)
                + MOVE_MARGIN_MS}})
        last = doc.get("last") if doc is not None else None
        if j[1] is None or not isinstance(last, dict) or last.get("id") != j[1]:
            return ""
        if last.get("ok"):
            return self._verdict(True, None)
        on = last.get("on")
        rows = [("It couldn't join %s: %s." % (j[0], last.get("why") or "no answer"), "plain")]
        if on:
            rows.append(("It is back on %s, and so is this page." % on, "dim"))
        return self._verdict(False, ("Still on %s" % on if on else "Couldn't move the console",
                                     tuple(rows)))

    def _verdict(self, ok, says):
        self._join[2] = ok
        self._says = says
        return json.dumps({"settled": 1, "ok": ok})

    def _absorb(self, doc):
        doc = dict(doc)
        doc.pop("ok", None)
        doc.pop("message", None)
        self._doc = doc
