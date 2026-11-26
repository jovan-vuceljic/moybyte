"""The browser's half of the Zero's GPIO verbs (#9) -- a QUEUE, never a call.

`pin_write(n, v)` and `pin_read(n)` are cart verbs, so they run inside a frame,
and a frame may not wait on a network round trip: the whole budget at 60fps is
16.7ms and a LAN POST is a good fraction of it -- a cart that blinked an LED
every frame would be a cart running at the wire's speed. That is the mistake
the streaming web view made at a different scale and it is not repeated here.

So a write does not travel. It QUEUES, and the worker's pump ships whatever
accumulated as one batch, in exactly the shape the sync push already uses: ONE
POST in flight, and the next batch coalesces everything that happened while it
was gone. Coalescing is not just an optimisation here -- it is the semantics.
A pin has ONE state, so ten writes to it during one round trip are nine writes
nobody could have observed and one that is the truth.

`pin_read(n)` therefore answers from the LAST ANSWER, not from the pin. The
first call registers interest and returns None (nothing has been read yet);
every batch from then on carries a read for that pin, so the value is at worst
one pump plus one round trip old. The verbs' documented latency lives in
docs/moy_cart_api.md, where a kid's grown-up will find it.

ON THE LIVE SOCKET the same queue rides the board's device channel instead
(native/moy_net/moy_live.c's THE PINS), where the board relays its pins (the
/live probe's "kinds" names "pins") and while the socket is open: each frame's
writes leave right after it as one 'W', not in the next 33ms batch, the pins
`pin_read` asked about are named once ('S'), and the board pushes a watched
pin's level when it changes ('G') rather than this side asking every batch.
The board's ops are /gpio's, so a socket that drops falls back to the batches
with nothing to hand over, and one that opens again says what it drove and
watches.

A pin outside the board's allowlist is REFUSED here as well as there, and says
so once on the console. Once, because the call it came from is in `_update`
and would otherwise print sixty times a second -- which is how a useful message
becomes something people turn off.
"""

import json

PROTOCOL_V = 1

# The page's pins row on the device channel: above every row of the page's
# own handle table (native/moy_net/moy_dev_web.c's, MOY_DEV_HANDLES).
PINS_ROW = 0xFF
# moy_dev's answers (native/moy_kernel/moy_dev.h) a refused write carries.
_WHY = {-7: "not on this board's allowlist", -11: "busy", -8: "not on the socket"}

# How many POSTs may fail back-to-back before this link gives up for good. The
# board went away (unplugged, rebooted, off the network) and a cart must not
# accumulate an unbounded queue of writes for a peer that is not there.
MAX_FAILS = 5


class GpioLink:
    """The queue behind `pin_write`/`pin_read`, and the pump's other end."""

    ROW = PINS_ROW

    def __init__(self, pins, log=print):
        self.pins = tuple(int(p) for p in pins)
        self.dead = False
        self._log = log
        self._writes = {}        # pin -> 0/1, last write wins (see the header)
        self._watch = []         # pins pin_read asked about, in the order asked
        self._level = {}         # pin -> the last level the board reported
        self._sent = None        # the writes the in-flight POST is carrying
        self._fails = 0
        self._told = {}          # pins already complained about
        self.live = False        # the writes ride the live socket (live_open)
        self._driven = {}        # pin -> the level last written, said again at a reopen
        self._opening = False    # the row's open to say
        self._said = None        # the pins watched as the board knows them

    # -- the cart verbs ------------------------------------------------------

    def write(self, n, v):
        """Queue `pin n = v`. True when the pin is one this board will drive."""
        n = self._pin(n)
        if n is None:
            return False
        self._writes[n] = self._driven[n] = 1 if v else 0
        return True

    def read(self, n):
        """The last level the board reported for pin n, or None if it has not
        answered yet. Asking is also what SUBSCRIBES the pin: every batch from
        here on carries a read for it."""
        n = self._pin(n)
        if n is None:
            return None
        if n not in self._watch:
            self._watch.append(n)
        return self._level.get(n)

    def _pin(self, raw):
        if self.dead:
            return None
        try:
            n = int(raw)
        except (TypeError, ValueError):
            n = None
        if n is None or n not in self.pins:
            if raw not in self._told:
                self._told[raw] = True
                self._log("pin %s is not one this board will drive -- it has %s"
                          % (raw, ", ".join(str(p) for p in self.pins)))
            return None
        return n

    # -- the pump ------------------------------------------------------------

    def take_json(self):
        """The next wire batch, or "" -- nothing to say, one already in
        flight, or the writes riding the live socket."""
        if self.dead or self.live or self._sent is not None:
            return ""
        if not self._writes and not self._watch:
            return ""
        ops = []
        for n in sorted(self._writes):
            ops.append({"p": n, "mode": "out", "v": self._writes[n]})
        for n in self._watch:
            ops.append({"p": n, "mode": "read"})
        self._sent = self._writes
        self._writes = {}
        return json.dumps({"v": PROTOCOL_V, "ops": ops})

    def ack(self, ok, text=""):
        """Settle the in-flight batch. `text` is the board's answer body, whose
        `reads` become what `pin_read` returns."""
        sent = self._sent
        self._sent = None
        if not ok:
            self._fails += 1
            if self._fails >= MAX_FAILS:
                self._log("gpio: the board stopped answering -- pin verbs off")
                self.stop()
                return False
            # REQUEUE, but never over a newer write: a value the cart set while
            # this batch was away is the current truth, and replaying the stale
            # one on top of it would make a failed POST turn a pin back.
            for n in sent or ():
                if n not in self._writes:
                    self._writes[n] = sent[n]
            return False
        self._fails = 0
        if text:
            self._absorb(text)
        return True

    def _absorb(self, text):
        try:
            doc = json.loads(text)
        except Exception:            # noqa: BLE001 -- a truncated answer
            return
        if not isinstance(doc, dict):
            return
        reads = doc.get("reads")
        if isinstance(reads, dict):
            for k, v in reads.items():
                try:
                    self._level[int(k)] = 1 if v else 0
                except (TypeError, ValueError):
                    pass
        for err in doc.get("err") or ():
            try:
                self._log("gpio: %s" % err[1])
            except Exception:        # noqa: BLE001 -- an odd err row
                pass

    # -- the live socket ------------------------------------------------------

    def live_open(self, on):
        """The socket opened where the board relays its pins (True), or
        closed (False): the batches stop or take over. An open says the row
        again, every pin this page drove and the pins it watches, since the
        board may have restarted."""
        on = bool(on) and not self.dead
        if on == self.live:
            return
        self.live = on
        self._said = None
        if on:
            self._opening = True
            for n, v in self._driven.items():
                self._writes.setdefault(n, v)

    def take_live(self):
        """The device channel's plaintexts for the board since the last
        frame, in order: the row's open, the frame's writes, the pins
        watched where they changed."""
        out = []
        if not self.live:
            return out
        row = bytes([PINS_ROW])
        if self._opening:
            self._opening = False
            out.append(b"dO" + row + b"\x04pins")
        if self._writes:
            w = bytearray(b"dW" + row)
            for n in sorted(self._writes):
                w += bytes([n, self._writes[n]])
            self._writes = {}
            out.append(bytes(w))
        if self._watch and self._said != self._watch:
            self._said = list(self._watch)
            out.append(b"dS" + row + bytes(self._said))
        return out

    def live_in(self, pl):
        """A device channel plaintext of the pins row: a refusal ('A') said
        on the console, once a pin and reason, or the watched pins' levels
        ('G')."""
        if len(pl) < 3 or pl[2] != PINS_ROW:
            return
        if pl[1:2] == b"G":
            for i, n in enumerate(self._said or ()):
                at = 3 + 4 * i
                if at + 4 > len(pl):
                    break
                v = int.from_bytes(pl[at:at + 4], "little")
                if v >= 0x80000000:
                    self._level.pop(n, None)
                else:
                    self._level[n] = 1 if v else 0
            return
        if pl[1:2] != b"A" or len(pl) < 8:
            return
        rc = int.from_bytes(pl[4:8], "little")
        rc = rc - 0x100000000 if rc >= 0x80000000 else rc
        if rc >= 0:
            return
        if pl[3:4] == b"O":
            self._log("gpio: the board's pins are not on its socket -- batches instead")
            self.live = False
            return
        why = _WHY.get(rc, "refused (%d)" % rc)
        key = (pl[8] if len(pl) > 8 else None, rc)
        if key not in self._told:
            self._told[key] = True
            self._log("gpio: pin %s: %s" % (key[0], why))

    def stop(self):
        """Go inert for good. The cart still HOLDS these verbs -- availability
        was decided once, before it started -- so they have to keep answering,
        and what they answer from here is "no"."""
        self.dead = True
        self.live = False
        self._writes = {}
        self._watch = []
        self._sent = None
